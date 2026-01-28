"""Command-line interface for Thoth ingestion pipeline.

This module provides a Click-based CLI for running the ingestion pipeline,
checking status, and managing the vector store.
"""

import logging
from pathlib import Path
import signal
import sys
import time
from typing import Any

import click
from rich.console import Console
from rich.panel import Panel
from rich.progress import (
    BarColumn,
    Progress,
    SpinnerColumn,
    TaskProgressColumn,
    TextColumn,
    TimeRemainingColumn,
)
from rich.table import Table

from thoth.ingestion.chunker import MarkdownChunker
from thoth.ingestion.pipeline import IngestionPipeline
from thoth.ingestion.repo_manager import HandbookRepoManager
from thoth.shared.embedder import Embedder
from thoth.shared.monitoring import Monitor, create_default_health_checks
from thoth.shared.scheduler import SyncScheduler
from thoth.shared.utils.logger import setup_logger
from thoth.shared.vector_store import VectorStore

console = Console()


def _setup_monitor_and_scheduler(
    pipeline: IngestionPipeline,
    db_path: str | None,
) -> tuple[Monitor, SyncScheduler]:
    """Set up monitoring and scheduler with callbacks.

    Args:
        pipeline: Configured pipeline instance
        db_path: Database path

    Returns:
        Tuple of (monitor, scheduler)
    """
    # Set up monitoring
    repo_manager = pipeline.repo_manager
    vector_store_path = Path(db_path or "./handbook_vectors")
    repo_path = repo_manager.clone_path

    monitor = Monitor()

    # Register default health checks
    default_checks = create_default_health_checks(
        vector_store_path=vector_store_path,
        repo_path=repo_path,
    )
    for name, check_func in default_checks.items():
        monitor.register_health_check(name, check_func)

    # Set up scheduler
    scheduler = SyncScheduler(pipeline=pipeline)

    # Add monitoring callbacks
    def on_success(stats: dict[str, Any]) -> None:
        monitor.record_sync_success(
            files_processed=stats["processed_files"],
            chunks_created=stats["total_chunks"],
            duration=stats["duration_seconds"],
        )
        console.print(f"[green]✓ Sync completed: {stats['processed_files']} files processed[/green]")

    def on_failure(error: Exception) -> None:
        monitor.record_sync_failure(error)
        console.print(f"[red]✗ Sync failed: {error}[/red]")

    scheduler.add_success_callback(on_success)
    scheduler.add_failure_callback(on_failure)

    return monitor, scheduler


def _display_final_stats(monitor: Monitor) -> None:
    """Display final scheduler statistics.

    Args:
        monitor: Monitor instance with collected metrics
    """
    metrics = monitor.get_metrics()
    console.print("\n[bold]Final Statistics:[/bold]")
    metrics_table = Table(show_header=False, box=None, padding=(0, 2))
    metrics_table.add_column("Key", style="dim")
    metrics_table.add_column("Value")

    metrics_table.add_row("Total Syncs", str(metrics["sync_count"]))
    metrics_table.add_row("Successful", str(metrics["sync_success_count"]))
    metrics_table.add_row("Failed", str(metrics["sync_failure_count"]))
    metrics_table.add_row("Success Rate", f"{monitor.get_success_rate():.1f}%")

    console.print(metrics_table)


def setup_pipeline(
    repo_url: str | None,
    clone_path: str | None,
    db_path: str | None,
    collection: str | None,
) -> IngestionPipeline:
    """Set up the ingestion pipeline with given configuration.

    Args:
        repo_url: Repository URL (None for default)
        clone_path: Local clone path (None for default)
        db_path: Database path (None for default)
        collection: Collection name (None for default)

    Returns:
        Configured IngestionPipeline instance
    """
    # Set up logging
    logger = setup_logger("thoth", level=logging.INFO)

    # Initialize components
    repo_manager = HandbookRepoManager(
        repo_url=repo_url or "https://gitlab.com/gitlab-com/content-sites/handbook.git",
        clone_path=Path(clone_path) if clone_path else None,
        logger=logger,
    )

    chunker = MarkdownChunker(logger=logger)
    embedder = Embedder(model_name="all-MiniLM-L6-v2", batch_size=32)

    vector_store = VectorStore(
        persist_directory=db_path or "./handbook_vectors",
        collection_name=collection or "thoth_documents",
        embedder=embedder,
    )

    return IngestionPipeline(
        repo_manager=repo_manager,
        chunker=chunker,
        embedder=embedder,
        vector_store=vector_store,
        logger_instance=logger,
    )


@click.group()
@click.version_option()
def cli() -> None:
    """Thoth - GitLab Handbook Ingestion Pipeline.

    Ingest, process, and index the GitLab handbook for semantic search.
    """


@cli.command()
@click.option(
    "--repo-url",
    default=None,
    help="Repository URL (default: GitLab handbook)",
)
@click.option(
    "--clone-path",
    default=None,
    help="Local path to clone repository (default: ~/.thoth/handbook)",
)
@click.option(
    "--db-path",
    default=None,
    help="Database path (default: ./handbook_vectors)",
)
@click.option(
    "--collection",
    default=None,
    help="Collection name (default: thoth_documents)",
)
@click.option(
    "--force",
    is_flag=True,
    help="Force re-clone of repository",
)
@click.option(
    "--full",
    is_flag=True,
    help="Process all files (disable incremental mode)",
)
@click.option(
    "--batch-size",
    default=50,
    type=int,
    help="Number of files to process per batch (default: 50)",
)
def ingest(
    repo_url: str | None,
    clone_path: str | None,
    db_path: str | None,
    collection: str | None,
    force: bool,
    full: bool,
    batch_size: int,
) -> None:
    """Run the ingestion pipeline to index the GitLab handbook.

    This command will:
    1. Clone or update the GitLab handbook repository
    2. Discover and process markdown files
    3. Generate chunks and embeddings
    4. Store in the vector database

    By default, runs in incremental mode (only processes changed files).
    Use --full to process all files regardless of changes.
    """
    console.print(Panel.fit("🔮 Thoth Ingestion Pipeline", style="bold magenta"))

    try:
        # Set up pipeline
        pipeline = setup_pipeline(repo_url, clone_path, db_path, collection)
        pipeline.batch_size = batch_size

        # Create progress display
        with Progress(
            SpinnerColumn(),
            TextColumn("[bold blue]{task.description}"),
            BarColumn(),
            TaskProgressColumn(),
            TimeRemainingColumn(),
            console=console,
        ) as progress:
            task = progress.add_task("Initializing...", total=100)

            def progress_callback(current: int, total: int, message: str) -> None:
                """Update progress bar."""
                progress.update(task, completed=current, total=total, description=message)

            # Run pipeline
            console.print("\n[bold]Starting ingestion...[/bold]")
            stats = pipeline.run(
                force_reclone=force,
                incremental=not full,
                progress_callback=progress_callback,
            )

        # Display results
        console.print("\n[bold green]✓ Ingestion Complete![/bold green]\n")

        table = Table(show_header=True, header_style="bold cyan")
        table.add_column("Metric", style="dim")
        table.add_column("Value", justify="right")

        table.add_row("Files Processed", f"{stats.processed_files:,}")
        table.add_row("Files Failed", f"{stats.failed_files:,}" if stats.failed_files > 0 else "0")
        table.add_row("Total Chunks", f"{stats.total_chunks:,}")
        table.add_row("Total Documents", f"{stats.total_documents:,}")
        table.add_row("Duration", f"{stats.duration_seconds:.2f}s")
        table.add_row("Throughput (files/sec)", f"{stats.files_per_second:.2f}")
        table.add_row("Throughput (chunks/sec)", f"{stats.chunks_per_second:.2f}")

        console.print(table)

        if stats.failed_files > 0:
            console.print(
                f"\n[yellow]⚠ {stats.failed_files} file(s) failed to process. Check logs for details.[/yellow]"
            )

    except RuntimeError as e:
        console.print(f"\n[bold red]✗ Error:[/bold red] {e}")
        raise click.Abort from e


@cli.command()
@click.option(
    "--clone-path",
    default=None,
    help="Local path to repository (default: ~/.thoth/handbook)",
)
@click.option(
    "--db-path",
    default=None,
    help="Database path (default: ./handbook_vectors)",
)
@click.option(
    "--collection",
    default=None,
    help="Collection name (default: thoth_documents)",
)
def status(
    clone_path: str | None,
    db_path: str | None,
    collection: str | None,
) -> None:
    """Show current pipeline status and statistics."""
    console.print(Panel.fit("📊 Pipeline Status", style="bold cyan"))

    try:
        pipeline = setup_pipeline(None, clone_path, db_path, collection)
        status_info = pipeline.get_status()

        # Repository info
        console.print("\n[bold]Repository:[/bold]")
        repo_table = Table(show_header=False, box=None, padding=(0, 2))
        repo_table.add_column("Key", style="dim")
        repo_table.add_column("Value")

        repo_table.add_row("Path", status_info["repo_path"])
        repo_table.add_row("Exists", "✓ Yes" if status_info["repo_exists"] else "✗ No")

        console.print(repo_table)

        # State info
        state = status_info["state"]
        console.print("\n[bold]Pipeline State:[/bold]")
        state_table = Table(show_header=False, box=None, padding=(0, 2))
        state_table.add_column("Key", style="dim")
        state_table.add_column("Value")

        state_table.add_row("Last Commit", state["last_commit"] or "None")
        state_table.add_row("Processed Files", f"{len(state['processed_files']):,}")
        state_table.add_row("Failed Files", f"{len(state['failed_files']):,}")
        state_table.add_row("Total Chunks", f"{state['total_chunks']:,}")
        state_table.add_row("Total Documents", f"{state['total_documents']:,}")
        state_table.add_row("Completed", "✓ Yes" if state["completed"] else "✗ No")

        if state["start_time"]:
            state_table.add_row("Start Time", state["start_time"])
        if state["last_update_time"]:
            state_table.add_row("Last Update", state["last_update_time"])

        console.print(state_table)

        # Vector store info
        console.print("\n[bold]Vector Store:[/bold]")
        store_table = Table(show_header=False, box=None, padding=(0, 2))
        store_table.add_column("Key", style="dim")
        store_table.add_column("Value")

        store_table.add_row("Collection", status_info["vector_store_collection"])
        store_table.add_row("Document Count", f"{status_info['vector_store_count']:,}")

        console.print(store_table)

        # Failed files detail
        if state["failed_files"]:
            console.print("\n[bold yellow]Failed Files:[/bold yellow]")
            failed_table = Table(show_header=True, header_style="bold yellow")
            failed_table.add_column("File", style="dim")
            failed_table.add_column("Error")

            for file, error in list(state["failed_files"].items())[:10]:
                failed_table.add_row(file, error[:80] + "..." if len(error) > 80 else error)

            console.print(failed_table)

            if len(state["failed_files"]) > 10:
                console.print(f"[dim]... and {len(state['failed_files']) - 10} more[/dim]")

    except RuntimeError as e:
        console.print(f"\n[bold red]✗ Error:[/bold red] {e}")
        raise click.Abort from e


@cli.command()
@click.option(
    "--clone-path",
    default=None,
    help="Local path to repository (default: ~/.thoth/handbook)",
)
@click.option(
    "--db-path",
    default=None,
    help="Database path (default: ./handbook_vectors)",
)
@click.option(
    "--collection",
    default=None,
    help="Collection name (default: thoth_documents)",
)
@click.option(
    "--keep-repo",
    is_flag=True,
    help="Keep the cloned repository (only reset database and state)",
)
@click.confirmation_option(prompt="Are you sure you want to reset the pipeline?")
def reset(
    clone_path: str | None,
    db_path: str | None,
    collection: str | None,
    keep_repo: bool,
) -> None:
    """Reset the pipeline state and vector database.

    This will clear all processed data and start fresh.
    Use --keep-repo to preserve the cloned repository.
    """
    console.print(Panel.fit("🔄 Reset Pipeline", style="bold yellow"))

    try:
        pipeline = setup_pipeline(None, clone_path, db_path, collection)

        with console.status("[bold yellow]Resetting pipeline...", spinner="dots"):
            pipeline.reset(keep_repo=keep_repo)

        console.print("\n[bold green]✓ Pipeline reset successfully![/bold green]")

        if keep_repo:
            console.print("[dim]Repository preserved. Vector store and state cleared.[/dim]")
        else:
            console.print("[dim]Repository, vector store, and state cleared.[/dim]")

    except RuntimeError as e:
        console.print(f"\n[bold red]✗ Error:[/bold red] {e}")
        raise click.Abort from e


@cli.command()
@click.option(
    "--db-path",
    default=None,
    help="Database path (default: ./handbook_vectors)",
)
@click.option(
    "--collection",
    default=None,
    help="Collection name (default: thoth_documents)",
)
@click.option(
    "--query",
    "-q",
    required=True,
    help="Query text to search for",
)
@click.option(
    "--limit",
    "-n",
    default=5,
    type=int,
    help="Number of results to return (default: 5)",
)
def search(
    db_path: str | None,
    collection: str | None,
    query: str,
    limit: int,
) -> None:
    """Search the indexed handbook for relevant content.

    Example: thoth search -q "How to contribute to GitLab?" -n 3
    """
    console.print(Panel.fit(f"🔍 Searching: {query}", style="bold blue"))

    try:
        # Set up vector store
        embedder = Embedder(model_name="all-MiniLM-L6-v2")
        vector_store = VectorStore(
            persist_directory=db_path or "./handbook_vectors",
            collection_name=collection or "thoth_documents",
            embedder=embedder,
        )

        # Check if there are any documents
        count = vector_store.get_document_count()
        if count == 0:
            console.print("\n[yellow]⚠ No documents found in the vector store. Run 'thoth ingest' first.[/yellow]")
            return

        # Perform search
        with console.status("[bold blue]Searching...", spinner="dots"):
            results = vector_store.search_similar(query, n_results=limit)

        # Display results
        if not results or not results["documents"]:
            console.print("\n[yellow]No results found.[/yellow]")
            return

        console.print(f"\n[bold]Found {len(results['documents'][0])} results:[/bold]\n")

        for i, (doc, metadata, distance) in enumerate(
            zip(
                results["documents"][0],
                results["metadatas"][0],
                results["distances"][0],
                strict=True,
            ),
            1,
        ):
            similarity = 1 - distance  # Convert distance to similarity

            console.print(
                Panel(
                    f"[bold]File:[/bold] {metadata.get('file_path', 'Unknown')}\n"
                    f"[bold]Chunk:[/bold] {metadata.get('chunk_index', '?')}/{metadata.get('total_chunks', '?')}\n"
                    f"[bold]Similarity:[/bold] {similarity:.2%}\n\n"
                    f"{doc[:500]}{'...' if len(doc) > 500 else ''}",
                    title=f"Result {i}",
                    border_style="blue",
                )
            )

    except RuntimeError as e:
        console.print(f"\n[bold red]✗ Error:[/bold red] {e}")
        raise click.Abort from e


@cli.command()
@click.option(
    "--repo-url",
    default=None,
    help="Repository URL (default: GitLab handbook)",
)
@click.option(
    "--clone-path",
    default=None,
    help="Local path to clone repository (default: ~/.thoth/handbook)",
)
@click.option(
    "--db-path",
    default=None,
    help="Database path (default: ./handbook_vectors)",
)
@click.option(
    "--collection",
    default=None,
    help="Collection name (default: thoth_documents)",
)
@click.option(
    "--interval",
    default=60,
    type=int,
    help="Sync interval in minutes (default: 60)",
)
@click.option(
    "--cron-hour",
    type=int,
    help="Hour to run (0-23) for cron-style scheduling",
)
@click.option(
    "--cron-minute",
    default=0,
    type=int,
    help="Minute to run (0-59) for cron-style scheduling",
)
@click.option(
    "--start-immediately",
    is_flag=True,
    help="Run sync immediately on start",
)
def schedule(
    repo_url: str | None,
    clone_path: str | None,
    db_path: str | None,
    collection: str | None,
    interval: int,
    cron_hour: int | None,
    cron_minute: int,
    start_immediately: bool,
) -> None:
    """Start the scheduler for automated syncs.

    By default, syncs run every 60 minutes. Use --interval to change frequency,
    or use --cron-hour and --cron-minute for cron-style scheduling.

    Examples:
        # Run every 30 minutes
        thoth schedule --interval 30

        # Run daily at 2:30 AM
        thoth schedule --cron-hour 2 --cron-minute 30

        # Run every hour, starting immediately
        thoth schedule --start-immediately

    Press Ctrl+C to stop the scheduler.
    """
    console.print(Panel.fit("⏰ Thoth Scheduler", style="bold magenta"))

    try:
        # Set up pipeline
        pipeline = setup_pipeline(repo_url, clone_path, db_path, collection)

        # Set up monitoring and scheduler
        monitor, scheduler = _setup_monitor_and_scheduler(pipeline, db_path)

        # Configure schedule
        if cron_hour is not None:
            scheduler.add_cron_job(hour=cron_hour, minute=cron_minute)
            console.print(f"[cyan]Scheduled daily at {cron_hour:02d}:{cron_minute:02d}[/cyan]")
        else:
            scheduler.add_interval_job(
                interval_minutes=interval,
                start_immediately=start_immediately,
            )
            console.print(f"[cyan]Scheduled every {interval} minutes[/cyan]")

        # Start scheduler
        scheduler.start()
        console.print("[green]Scheduler started[/green]")

        # Display status
        status = scheduler.get_job_status()
        if status["next_run_time"]:
            console.print(f"Next run: {status['next_run_time']}")

        console.print("\n[dim]Press Ctrl+C to stop...[/dim]\n")

        # Set up signal handler for graceful shutdown
        def signal_handler(_sig: int, _frame: Any) -> None:
            console.print("\n[yellow]Stopping scheduler...[/yellow]")
            scheduler.stop()
            console.print("[green]Scheduler stopped[/green]")
            _display_final_stats(monitor)
            sys.exit(0)

        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)

        # Keep running
        while True:
            time.sleep(1)

    except RuntimeError as e:
        console.print(f"\n[bold red]✗ Error:[/bold red] {e}")
        raise click.Abort from e


@cli.command()
@click.option(
    "--clone-path",
    default=None,
    help="Local path to repository (default: ~/.thoth/handbook)",
)
@click.option(
    "--db-path",
    default=None,
    help="Database path (default: ./handbook_vectors)",
)
def health(
    clone_path: str | None,
    db_path: str | None,
) -> None:
    """Check system health status.

    Runs health checks on key components and displays the results.
    """
    console.print(Panel.fit("🏥 Health Check", style="bold cyan"))

    try:
        # Set up paths
        vector_store_path = Path(db_path or "./handbook_vectors")
        repo_manager = HandbookRepoManager(
            repo_url="https://gitlab.com/gitlab-com/content-sites/handbook.git",
            clone_path=Path(clone_path) if clone_path else None,
        )
        repo_path = repo_manager.clone_path

        # Set up monitor
        monitor = Monitor()

        # Register default health checks
        default_checks = create_default_health_checks(
            vector_store_path=vector_store_path,
            repo_path=repo_path,
        )
        for name, check_func in default_checks.items():
            monitor.register_health_check(name, check_func)

        # Run health checks
        report = monitor.get_health_report()

        # Display overall status
        overall = report["overall_status"]
        status_colors = {
            "healthy": "green",
            "degraded": "yellow",
            "unhealthy": "red",
            "unknown": "dim",
        }
        status_symbols = {
            "healthy": "✓",
            "degraded": "⚠",
            "unhealthy": "✗",
            "unknown": "?",
        }

        color = status_colors.get(overall, "white")
        symbol = status_symbols.get(overall, "?")

        console.print(f"\n[bold {color}]{symbol} Overall Status: {overall.upper()}[/bold {color}]\n")

        # Display individual checks
        checks_table = Table(show_header=True, header_style="bold")
        checks_table.add_column("Component", style="bold")
        checks_table.add_column("Status", justify="center")
        checks_table.add_column("Message")

        for name, check_data in report["checks"].items():
            status = check_data["status"]
            color = status_colors.get(status, "white")
            symbol = status_symbols.get(status, "?")

            checks_table.add_row(
                name.replace("_", " ").title(),
                f"[{color}]{symbol} {status}[/{color}]",
                check_data["message"],
            )

        console.print(checks_table)

        # Exit with appropriate code
        if overall == "unhealthy":
            sys.exit(1)
        elif overall == "degraded":
            sys.exit(2)
        else:
            sys.exit(0)

    except Exception as e:
        console.print(f"\n[bold red]✗ Error:[/bold red] {e}")
        raise click.Abort from e


@cli.command()
@click.option(
    "--repo-url",
    default=None,
    help="Repository URL (default: GitLab handbook)",
)
@click.option(
    "--clone-path",
    default=None,
    help="Local path to repository (default: ~/.thoth/handbook)",
)
@click.option(
    "--db-path",
    default=None,
    help="Database path (default: ./handbook_vectors)",
)
@click.option(
    "--collection",
    default=None,
    help="Collection name (default: thoth_documents)",
)
def sync(
    repo_url: str | None,
    clone_path: str | None,
    db_path: str | None,
    collection: str | None,
) -> None:
    """Manually trigger a sync operation.

    This is useful for testing the scheduler or running a one-off sync.
    """
    console.print(Panel.fit("🔄 Manual Sync", style="bold blue"))

    try:
        # Set up pipeline
        pipeline = setup_pipeline(repo_url, clone_path, db_path, collection)

        # Set up monitoring
        monitor = Monitor()
        monitor.record_sync_start()

        # Run sync
        with Progress(
            SpinnerColumn(),
            TextColumn("[bold blue]{task.description}"),
            BarColumn(),
            TaskProgressColumn(),
            TimeRemainingColumn(),
            console=console,
        ) as progress:
            task = progress.add_task("Syncing...", total=100)

            def progress_callback(current: int, total: int, message: str) -> None:
                progress.update(task, completed=current, total=total, description=message)

            try:
                stats = pipeline.run(
                    force_reclone=False,
                    incremental=True,
                    progress_callback=progress_callback,
                )

                monitor.record_sync_success(
                    files_processed=stats.processed_files,
                    chunks_created=stats.total_chunks,
                    duration=stats.duration_seconds,
                )

                console.print("\n[bold green]✓ Sync completed successfully![/bold green]\n")

                # Display stats
                stats_table = Table(show_header=False, box=None, padding=(0, 2))
                stats_table.add_column("Metric", style="dim")
                stats_table.add_column("Value")

                stats_table.add_row("Files Processed", f"{stats.processed_files:,}")
                stats_table.add_row("Total Chunks", f"{stats.total_chunks:,}")
                stats_table.add_row("Duration", f"{stats.duration_seconds:.2f}s")

                console.print(stats_table)

            except Exception as e:
                monitor.record_sync_failure(e)
                raise

    except RuntimeError as e:
        console.print(f"\n[bold red]✗ Error:[/bold red] {e}")
        raise click.Abort from e


if __name__ == "__main__":
    cli()
