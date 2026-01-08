"""Command-line interface for Thoth ingestion pipeline.

This module provides a Click-based CLI for running the ingestion pipeline,
checking status, and managing the vector store.
"""

import logging
from pathlib import Path

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
from thoth.ingestion.embedder import Embedder
from thoth.ingestion.pipeline import IngestionPipeline
from thoth.ingestion.repo_manager import HandbookRepoManager
from thoth.ingestion.vector_store import VectorStore
from thoth.utils.logger import setup_logger

console = Console()


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


if __name__ == "__main__":
    cli()
