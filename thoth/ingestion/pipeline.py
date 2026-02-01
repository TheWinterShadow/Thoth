"""Ingestion pipeline orchestrator for Thoth.

This module provides the main pipeline coordinator that integrates all ingestion
components (repo manager, chunker, embedder, vector store) into a complete
end-to-end ingestion workflow with progress tracking, error handling, and resume logic.
"""

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
import json
import logging
import os
from pathlib import Path
import shutil
from typing import Any

from thoth.ingestion.chunker import Chunk, DocumentChunker, MarkdownChunker
from thoth.ingestion.gcs_repo_sync import GCSRepoSync
from thoth.ingestion.parsers import ParserFactory
from thoth.ingestion.repo_manager import HandbookRepoManager
from thoth.shared.embedder import Embedder
from thoth.shared.sources.config import SourceConfig
from thoth.shared.utils.logger import setup_logger
from thoth.shared.vector_store import VectorStore

logger = setup_logger(__name__)

# Constants
DEFAULT_STATE_FILE = "pipeline_state.json"
DEFAULT_BATCH_SIZE = 50  # Process files in batches


@dataclass
class PipelineState:
    """Mutable state for a single pipeline run (resume and progress tracking).

    Persisted to pipeline_state.json so runs can resume after interruption.
    Tracks last processed commit, file lists, chunk counts, and completion flag.

    Attributes:
        last_commit: Last Git commit processed (for incremental sync).
        processed_files: List of file paths successfully processed.
        failed_files: Dict of file_path -> error_message for failed files.
        total_chunks: Total chunks created this run.
        total_documents: Total documents (chunks) added to the vector store.
        start_time: ISO timestamp when run started.
        last_update_time: ISO timestamp of last state save.
        completed: True when the run finished without error.
    """

    last_commit: str | None = None
    processed_files: list[str] = field(default_factory=list)
    failed_files: dict[str, str] = field(default_factory=dict)  # file_path -> error_message
    total_chunks: int = 0
    total_documents: int = 0
    start_time: str | None = None
    last_update_time: str | None = None
    completed: bool = False

    def to_dict(self) -> dict[str, Any]:
        """Serialize state to a dict for JSON persistence.

        Returns:
            Dict with last_commit, processed_files, failed_files, total_chunks,
            total_documents, start_time, last_update_time, completed.
        """
        return {
            "last_commit": self.last_commit,
            "processed_files": self.processed_files,
            "failed_files": self.failed_files,
            "total_chunks": self.total_chunks,
            "total_documents": self.total_documents,
            "start_time": self.start_time,
            "last_update_time": self.last_update_time,
            "completed": self.completed,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "PipelineState":
        """Deserialize state from a dict (e.g., from pipeline_state.json).

        Args:
            data: Dict with keys matching PipelineState attributes.

        Returns:
            PipelineState instance with restored values.
        """
        return cls(
            last_commit=data.get("last_commit"),
            processed_files=data.get("processed_files", []),
            failed_files=data.get("failed_files", {}),
            total_chunks=data.get("total_chunks", 0),
            total_documents=data.get("total_documents", 0),
            start_time=data.get("start_time"),
            last_update_time=data.get("last_update_time"),
            completed=data.get("completed", False),
        )


@dataclass
class PipelineStats:
    """Read-only statistics from a completed pipeline run.

    Returned by run() and used for logging and monitoring. All counts and
    rates are computed at the end of the run.

    Attributes:
        total_files: Total files discovered for processing.
        processed_files: Files successfully processed.
        failed_files: Files that failed (with errors).
        total_chunks: Chunks created and stored.
        total_documents: Documents (chunks) in the vector store after run.
        duration_seconds: Elapsed time in seconds.
        chunks_per_second: Throughput (chunks / duration).
        files_per_second: Throughput (files / duration).
    """

    total_files: int
    processed_files: int
    failed_files: int
    total_chunks: int
    total_documents: int
    duration_seconds: float
    chunks_per_second: float
    files_per_second: float


class IngestionPipeline:
    """Orchestrates the complete ingestion pipeline.

    This class coordinates:
    1. Repository cloning/updating
    2. Markdown file discovery
    3. Document chunking
    4. Embedding generation
    5. Vector store insertion

    With features:
    - Progress tracking and reporting
    - Resume capability from interruptions
    - Error handling and logging
    - Batch processing for efficiency
    """

    def __init__(
        self,
        repo_manager: HandbookRepoManager | None = None,
        chunker: MarkdownChunker | None = None,
        embedder: Embedder | None = None,
        vector_store: VectorStore | None = None,
        state_file: Path | None = None,
        batch_size: int = DEFAULT_BATCH_SIZE,
        logger_instance: logging.Logger | logging.LoggerAdapter | None = None,
        collection_name: str = "thoth_documents",
        source_config: SourceConfig | None = None,
    ):
        """Initialize the ingestion pipeline.

        Args:
            repo_manager: Repository manager instance (creates default if None)
            chunker: Markdown chunker instance (creates default if None)
            embedder: Embedder instance (creates default if None)
            vector_store: Vector store instance (creates default if None)
            state_file: Path to state file for resume capability
            batch_size: Number of files to process in each batch
            logger_instance: Logger instance for logging
            collection_name: Name of the vector store table (collection) to use
            source_config: Source configuration for multi-source support
        """
        self.logger = logger_instance or logger
        self.source_config = source_config
        self.repo_manager = repo_manager or HandbookRepoManager(logger=self.logger)
        self.chunker = chunker or MarkdownChunker(logger=self.logger)
        self.document_chunker = DocumentChunker(logger=self.logger)  # Generalized chunker for all formats
        self.embedder = embedder or Embedder(logger_instance=self.logger)
        # Use collection name from source config if provided
        self.collection_name = source_config.collection_name if source_config else collection_name
        self.source_name = source_config.name if source_config else ""

        # Initialize GCS repo sync if in Cloud Run environment
        self.gcs_repo_sync = None
        gcs_bucket = os.getenv("GCS_BUCKET_NAME")
        gcs_project = os.getenv("GCP_PROJECT_ID")

        if gcs_bucket and gcs_project:
            # Cloud Run: use GCS for repository storage
            self.logger.info("Cloud Run detected - using GCS for repository sync")
            repo_url = os.getenv("GITLAB_BASE_URL", "https://gitlab.com") + "/gitlab-com/content-sites/handbook.git"
            self.gcs_repo_sync = GCSRepoSync(
                bucket_name=gcs_bucket,
                repo_url=repo_url,
                gcs_prefix="handbook",
                local_path=Path("/tmp/handbook"),  # nosec B108 - Cloud Run requires /tmp
                logger_instance=self.logger,
            )

        # Auto-configure vector store for Cloud Run environment
        if vector_store is None:
            if gcs_bucket and gcs_project:
                # Cloud Run: use /tmp for local cache and sync with GCS
                self.logger.info(f"Cloud Run detected - using GCS bucket: {gcs_bucket}")
                self.vector_store = VectorStore(
                    persist_directory="/tmp/lancedb",  # nosec B108 - Cloud Run uses GCS URI
                    collection_name=collection_name,
                    gcs_bucket_name=gcs_bucket,
                    gcs_project_id=gcs_project,
                    logger_instance=self.logger,
                )
            else:
                # Local: use default lancedb directory
                self.vector_store = VectorStore(collection_name=collection_name, logger_instance=self.logger)
        else:
            self.vector_store = vector_store

        self.state_file = state_file or (self.repo_manager.clone_path.parent / DEFAULT_STATE_FILE)
        self.batch_size = batch_size

        self.state = self._load_state()

    @property
    def effective_repo_path(self) -> Path:
        """Get the effective repository path (GCS local path or repo_manager clone path)."""
        if self.gcs_repo_sync:
            return self.gcs_repo_sync.local_path
        return self.repo_manager.clone_path

    def _load_state(self) -> PipelineState:
        """Load pipeline state from disk.

        Returns:
            PipelineState instance (empty if no saved state)
        """
        if not self.state_file.exists():
            self.logger.info("No previous state found, starting fresh")
            return PipelineState()

        try:
            with self.state_file.open(encoding="utf-8") as f:
                data = json.load(f)
            state = PipelineState.from_dict(data)
            self.logger.info(
                "Loaded previous state: %d processed files, %d failed files",
                len(state.processed_files),
                len(state.failed_files),
            )
            return state
        except (OSError, json.JSONDecodeError) as e:
            self.logger.warning("Failed to load state file: %s. Starting fresh.", e)
            return PipelineState()

    def _save_state(self) -> None:
        """Save current pipeline state to disk."""
        self.state.last_update_time = datetime.now(UTC).isoformat()

        try:
            self.state_file.parent.mkdir(parents=True, exist_ok=True)
            with self.state_file.open("w", encoding="utf-8") as f:
                json.dump(self.state.to_dict(), f, indent=2)
            self.logger.debug("Saved pipeline state to %s", self.state_file)
        except OSError:
            self.logger.exception("Failed to save state file")

    def _discover_markdown_files(self, repo_path: Path) -> list[Path]:
        """Discover all markdown files in the repository.

        Args:
            repo_path: Path to the repository

        Returns:
            List of markdown file paths
        """
        self.logger.info("Discovering markdown files in %s", repo_path)
        markdown_files = list(repo_path.rglob("*.md"))
        self.logger.info("Found %d markdown files", len(markdown_files))
        return markdown_files

    def _discover_source_files(self, source_path: Path) -> list[Path]:
        """Discover all supported files for the configured source.

        This method discovers files based on the source_config's supported formats.
        If no source_config is set, falls back to markdown-only discovery.

        Args:
            source_path: Path to search for files

        Returns:
            List of file paths matching supported formats
        """
        if not self.source_config:
            # Fallback to markdown-only for backward compatibility
            return self._discover_markdown_files(source_path)

        self.logger.info(
            "Discovering files in %s for source '%s' (formats: %s)",
            source_path,
            self.source_config.name,
            self.source_config.supported_formats,
        )

        all_files: list[Path] = []
        for ext in self.source_config.supported_formats:
            # Remove leading dot if present for glob pattern
            pattern = f"*{ext}" if ext.startswith(".") else f"*.{ext}"
            files = list(source_path.rglob(pattern))
            all_files.extend(files)
            self.logger.debug("Found %d %s files", len(files), ext)

        self.logger.info(
            "Found %d total files for source '%s'",
            len(all_files),
            self.source_config.name,
        )
        return all_files

    def get_file_list(self) -> list[str]:
        """Get list of all markdown files for batch processing.

        Returns:
            List of file paths relative to repo root
        """
        # Use GCS sync if in Cloud Run environment
        if self.gcs_repo_sync:
            self.logger.info("Using GCS repository sync")
            if not self.gcs_repo_sync.is_synced():
                self.logger.info("Syncing repository from GCS to local...")
                result = self.gcs_repo_sync.sync_to_local()
                self.logger.info("Sync result: %s", result)
            else:
                self.logger.info("Repository already synced locally")

            repo_path = self.gcs_repo_sync.get_local_path()
        else:
            # Local environment: use traditional git clone
            clone_path = self.repo_manager.clone_path
            self.logger.info("Checking if repository exists at: %s", clone_path)
            if not clone_path.exists():
                self.logger.info("Repository not found, cloning...")
                try:
                    self.repo_manager.clone_handbook()
                    self.logger.info("Repository cloned successfully to: %s", clone_path)
                except Exception:
                    self.logger.exception("Failed to clone repository")
                    raise
            else:
                self.logger.info("Repository already exists at: %s", clone_path)

            repo_path = self.repo_manager.clone_path

        # Discover files
        markdown_files = self._discover_markdown_files(repo_path)

        # Convert to relative paths
        return [str(f.relative_to(repo_path)) for f in markdown_files]

    def process_file_batch(
        self,
        start_index: int,
        end_index: int,
        file_list: list[str] | None = None,
    ) -> dict[str, Any]:
        """Process a specific batch of files by index range.

        Args:
            start_index: Starting index (inclusive)
            end_index: Ending index (exclusive)
            file_list: Optional pre-computed file list. If None, discovers files.

        Returns:
            Statistics dictionary with processed/failed counts
        """
        self.logger.info("Processing batch %d-%d of files", start_index, end_index)

        # Get file list if not provided
        if file_list is None:
            file_list = self.get_file_list()

        # Validate indices
        if start_index < 0 or end_index > len(file_list) or start_index >= end_index:
            msg = f"Invalid batch range: {start_index}-{end_index} for {len(file_list)} files"
            raise ValueError(msg)

        # Get batch slice
        batch_files = file_list[start_index:end_index]

        # Determine repo path and download files if using GCS
        if self.gcs_repo_sync:
            # Download ONLY the files in this batch (parallel downloads)
            self.logger.info("Downloading %d files from GCS for this batch", len(batch_files))
            repo_path = self.gcs_repo_sync.download_batch_files(batch_files)
        else:
            # Use local clone for development/testing
            repo_path = self.repo_manager.clone_path

        # Convert to Path objects
        file_paths = [repo_path / f for f in batch_files]

        # Process the batch
        start_time = datetime.now(UTC)
        successful, failed = self._process_batch(file_paths)
        end_time = datetime.now(UTC)

        duration = (end_time - start_time).total_seconds()

        stats = {
            "start_index": start_index,
            "end_index": end_index,
            "total_files": len(batch_files),
            "successful": successful,
            "failed": failed,
            "duration_seconds": duration,
        }

        self.logger.info(
            "Batch %d-%d complete: %d successful, %d failed in %.2fs",
            start_index,
            end_index,
            successful,
            failed,
            duration,
        )

        return stats

    def _process_file(self, file_path: Path) -> list[Chunk]:
        """Process a single file into chunks.

        Supports multiple file formats through the parser system:
        - Markdown (.md) - uses MarkdownChunker for structure-aware chunking
        - PDF (.pdf) - extracts text with page markers
        - Text (.txt) - simple text extraction
        - Word (.docx) - extracts paragraphs and tables

        Args:
            file_path: Path to the file

        Returns:
            List of chunks from the file

        Raises:
            Exception: If processing fails
        """
        self.logger.debug("Processing file: %s", file_path)

        try:
            # Determine if we should use the new parser system
            extension = file_path.suffix.lower()

            if extension in [".md", ".markdown", ".mdown"]:
                # Use existing markdown chunker for backward compatibility
                chunks = self.chunker.chunk_file(file_path)
                # Add source and format metadata
                for chunk in chunks:
                    chunk.metadata.source = self.source_name
                    chunk.metadata.format = "markdown"
            elif ParserFactory.can_parse(file_path):
                # Use parser system for other formats
                parsed_doc = ParserFactory.parse(file_path)
                chunks = self.document_chunker.chunk_document(
                    content=parsed_doc.content,
                    source_path=str(file_path),
                    source=self.source_name,
                    doc_format=parsed_doc.format,
                )
            else:
                self.logger.warning("No parser available for %s, skipping", file_path)
                return []

            self.logger.debug("Generated %d chunks from %s", len(chunks), file_path)
            return chunks
        except Exception:
            self.logger.exception("Failed to process file %s", file_path)
            raise

    def _process_batch(
        self,
        files: list[Path],
        progress_callback: Callable[[int, int, str], None] | None = None,
    ) -> tuple[int, int]:
        """Process a batch of markdown files.

        Args:
            files: List of file paths to process
            progress_callback: Optional callback(current, total, status_msg) for progress updates

        Returns:
            Tuple of (successful_count, failed_count)
        """
        successful = 0
        failed = 0
        total_batch_chunks = 0

        for i, file_path in enumerate(files):
            # Skip if already processed
            file_str = str(file_path.relative_to(self.effective_repo_path))
            if file_str in self.state.processed_files:
                self.logger.debug("Skipping already processed file: %s", file_str)
                successful += 1
                continue

            try:
                # Process file into chunks
                chunks = self._process_file(file_path)

                if not chunks:
                    self.logger.warning("No chunks generated from %s", file_str)
                    self.state.processed_files.append(file_str)
                    successful += 1
                    continue

                # Extract content and metadata for vector store
                documents = [chunk.content for chunk in chunks]
                metadatas = [chunk.metadata.to_dict() for chunk in chunks]
                ids = [chunk.metadata.chunk_id for chunk in chunks]

                # Sanitize metadatas to ensure ChromaDB compatibility
                # Convert any list values to comma-separated strings
                def sanitize_metadata(meta: dict[str, Any]) -> dict[str, Any]:
                    """Ensure all metadata values are ChromaDB-compatible (str, int, float, bool)."""
                    sanitized: dict[str, Any] = {}
                    for key, value in meta.items():
                        if isinstance(value, list):
                            sanitized[key] = ", ".join(str(v) for v in value)
                        elif isinstance(value, (str, int, float, bool)):
                            sanitized[key] = value
                        elif value is None:
                            sanitized[key] = ""
                        else:
                            sanitized[key] = str(value)
                    return sanitized

                metadatas = [sanitize_metadata(m) for m in metadatas]

                # Generate embeddings and store
                embeddings = self.embedder.embed(documents, show_progress=False)
                self.vector_store.add_documents(
                    documents=documents,
                    metadatas=metadatas,
                    ids=ids,
                    embeddings=embeddings,
                )

                # Update state
                self.state.processed_files.append(file_str)
                self.state.total_chunks += len(chunks)
                self.state.total_documents += len(chunks)
                total_batch_chunks += len(chunks)
                successful += 1

                if progress_callback:
                    progress_callback(
                        i + 1,
                        len(files),
                        f"Processed {file_str} ({len(chunks)} chunks)",
                    )

            except Exception as e:
                self.logger.exception("Failed to process file %s", file_str)
                self.state.failed_files[file_str] = str(e)
                failed += 1

                if progress_callback:
                    progress_callback(
                        i + 1,
                        len(files),
                        f"Failed to process {file_str}",
                    )

        self.logger.info(
            "Batch complete: %d successful, %d failed, %d chunks added",
            successful,
            failed,
            total_batch_chunks,
        )
        return successful, failed

    def _handle_deleted_files(self, deleted_files: list[str]) -> tuple[int, int]:
        """Handle deleted files by removing their documents from vector store.

        Args:
            deleted_files: List of deleted file paths (relative to repo)

        Returns:
            Tuple of (successful_count, failed_count)
        """
        successful = 0
        failed = 0

        for file_path in deleted_files:
            try:
                # Delete all documents associated with this file
                deleted_count = self.vector_store.delete_by_file_path(file_path)

                # Remove from processed files list
                if file_path in self.state.processed_files:
                    self.state.processed_files.remove(file_path)

                # Update statistics, ensuring counters do not go negative
                self.state.total_chunks = max(0, self.state.total_chunks - deleted_count)
                self.state.total_documents = max(0, self.state.total_documents - deleted_count)

                self.logger.info(
                    "Deleted %d documents for removed file: %s",
                    deleted_count,
                    file_path,
                )
                successful += 1

            except Exception as e:
                self.logger.exception("Failed to handle deleted file %s", file_path)
                self.state.failed_files[file_path] = f"Delete failed: {e}"
                failed += 1

        return successful, failed

    def _handle_modified_files(
        self,
        modified_files: list[Path],
        progress_callback: Callable[[int, int, str], None] | None = None,
    ) -> tuple[int, int]:
        """Handle modified files by updating their documents in vector store.

        Args:
            modified_files: List of modified file paths
            progress_callback: Optional callback for progress updates

        Returns:
            Tuple of (successful_count, failed_count)
        """
        successful = 0
        failed = 0
        total_chunks = 0

        for i, file_path in enumerate(modified_files):
            file_str = str(file_path.relative_to(self.effective_repo_path))

            try:
                # Step 1: Delete old documents for this file
                deleted_count = self.vector_store.delete_by_file_path(file_str)
                self.logger.debug(
                    "Deleted %d old documents for modified file: %s",
                    deleted_count,
                    file_str,
                )

                # Step 2: Process the updated file
                chunks = self._process_file(file_path)

                if not chunks:
                    self.logger.warning("No chunks generated from modified file %s", file_str)
                    # Still mark as successful since we deleted old content
                    if file_str not in self.state.processed_files:
                        self.state.processed_files.append(file_str)
                    successful += 1
                    # Update statistics to account for deleted chunks when no new chunks are added
                    self.state.total_chunks -= deleted_count
                    self.state.total_documents -= deleted_count
                    continue

                # Step 3: Add new documents
                documents = [chunk.content for chunk in chunks]
                metadatas = [chunk.metadata.to_dict() for chunk in chunks]
                ids = [chunk.metadata.chunk_id for chunk in chunks]

                embeddings = self.embedder.embed(documents, show_progress=False)
                self.vector_store.add_documents(
                    documents=documents,
                    metadatas=metadatas,
                    ids=ids,
                    embeddings=embeddings,
                )

                # Update state
                if file_str not in self.state.processed_files:
                    self.state.processed_files.append(file_str)

                # Update chunk counts (net change)
                self.state.total_chunks += len(chunks) - deleted_count
                self.state.total_documents += len(chunks) - deleted_count
                total_chunks += len(chunks)

                successful += 1

                if progress_callback:
                    progress_callback(
                        i + 1,
                        len(modified_files),
                        f"Updated {file_str} ({len(chunks)} chunks)",
                    )

            except Exception as e:
                self.logger.exception("Failed to handle modified file %s", file_str)
                self.state.failed_files[file_str] = f"Modify failed: {e}"
                failed += 1

                if progress_callback:
                    progress_callback(
                        i + 1,
                        len(modified_files),
                        f"Failed to update {file_str}",
                    )

        self.logger.info(
            "Modified files processed: %d successful, %d failed, %d new chunks",
            successful,
            failed,
            total_chunks,
        )
        return successful, failed

    def run(  # noqa: PLR0912, PLR0915
        self,
        force_reclone: bool = False,
        incremental: bool = True,
        progress_callback: Callable[[int, int, str], None] | None = None,
    ) -> PipelineStats:
        """Run the complete ingestion pipeline.

        Args:
            force_reclone: If True, force re-sync from GCS (or re-clone if no GCS)
            incremental: If True, only process files not already in state
            progress_callback: Optional callback(current, total, status_msg) for progress

        Returns:
            PipelineStats with execution statistics

        Raises:
            RuntimeError: If pipeline fails
        """
        start_time = datetime.now(UTC)
        self.state.start_time = start_time.isoformat()
        self.logger.info("Starting ingestion pipeline")

        try:
            # Step 1: Get repository files (from GCS or local clone)
            if progress_callback:
                progress_callback(0, 100, "Syncing repository...")

            if self.gcs_repo_sync:
                # Cloud Run: sync from GCS (never clone directly)
                self.logger.info("Syncing repository from GCS...")
                sync_result = self.gcs_repo_sync.sync_to_local(force=force_reclone)
                self.logger.info(
                    "GCS sync complete: %s (%s files)",
                    sync_result.get("status"),
                    sync_result.get("files_downloaded", sync_result.get("file_count", "?")),
                )
                repo_path = self.gcs_repo_sync.get_local_path()
                # GCS sync doesn't have git history, use a placeholder commit
                current_commit = "gcs-sync"
            else:
                # Local environment: use traditional git clone
                if not self.repo_manager.is_valid_repo() or force_reclone:
                    self.logger.info("Cloning repository...")
                    self.repo_manager.clone_handbook(force=force_reclone)
                else:
                    self.logger.info("Updating repository...")
                    self.repo_manager.update_repository()

                commit_or_none = self.repo_manager.get_current_commit()
                if not commit_or_none:
                    msg = "Failed to get current commit"
                    raise RuntimeError(msg)
                current_commit = commit_or_none
                repo_path = self.repo_manager.clone_path

            # Step 2: Discover files to process
            if progress_callback:
                progress_callback(10, 100, "Discovering markdown files...")

            all_files = self._discover_markdown_files(repo_path)

            # Initialize file lists
            files_to_process: list[Path] = []
            deleted_files: list[str] = []
            added_files_list: list[Path] = []
            modified_files_list: list[Path] = []

            # Filter files for incremental processing
            # For GCS mode: use file-based incremental (skip already processed files)
            # For git mode: use commit-based incremental (diff against last commit)
            use_git_incremental = (
                incremental
                and self.state.last_commit
                and self.state.last_commit != "gcs-sync"
                and not self.gcs_repo_sync
            )

            if use_git_incremental and self.state.last_commit:
                # Git-based incremental: use commit diff
                file_changes = self.repo_manager.get_file_changes(self.state.last_commit)
                if file_changes is not None:
                    # Filter for markdown files only
                    added_md = [f for f in file_changes["added"] if f.endswith(".md")]
                    modified_md = [f for f in file_changes["modified"] if f.endswith(".md")]
                    deleted_md = [f for f in file_changes["deleted"] if f.endswith(".md")]

                    # Convert to Path objects for added and modified
                    added_files_list = [repo_path / f for f in added_md if (repo_path / f).exists()]
                    modified_files_list = [repo_path / f for f in modified_md if (repo_path / f).exists()]

                    files_to_process = added_files_list + modified_files_list
                    deleted_files = deleted_md

                    self.logger.info(
                        "Git incremental mode: %d added, %d modified, %d deleted",
                        len(added_files_list),
                        len(modified_files_list),
                        len(deleted_files),
                    )
                else:
                    self.logger.warning("Failed to get file changes, processing all files")
                    files_to_process = all_files
                    added_files_list = all_files
                    modified_files_list = []
            elif incremental and self.state.processed_files:
                # File-based incremental: skip already processed files
                # This works for both GCS mode and when git diff fails
                processed_set = set(self.state.processed_files)
                added_files_list = [f for f in all_files if str(f.relative_to(repo_path)) not in processed_set]
                files_to_process = added_files_list
                modified_files_list = []
                self.logger.info(
                    "File-based incremental: %d new files to process (%d already done)",
                    len(added_files_list),
                    len(processed_set),
                )
            else:
                files_to_process = all_files
                added_files_list = all_files
                modified_files_list = []
                self.logger.info("Full mode: processing all %d files", len(all_files))

            # Step 3: Handle file changes incrementally
            if progress_callback:
                progress_callback(20, 100, "Processing file changes...")

            total_successful = 0
            total_failed = 0

            # Step 3a: Handle deleted files
            if deleted_files:
                self.logger.info("Processing %d deleted files", len(deleted_files))
                if progress_callback:
                    progress_callback(25, 100, f"Removing {len(deleted_files)} deleted files...")

                deleted_success, deleted_failed = self._handle_deleted_files(deleted_files)
                total_successful += deleted_success
                total_failed += deleted_failed
                self._save_state()

            # Step 3b: Handle modified files (update)
            if incremental and self.state.last_commit and modified_files_list:
                self.logger.info("Processing %d modified files", len(modified_files_list))

                for batch_start in range(0, len(modified_files_list), self.batch_size):
                    batch_end = min(batch_start + self.batch_size, len(modified_files_list))
                    batch = modified_files_list[batch_start:batch_end]

                    self.logger.info(
                        "Processing modified batch %d-%d of %d files",
                        batch_start + 1,
                        batch_end,
                        len(modified_files_list),
                    )

                    def make_modified_callback(
                        start: int,
                    ) -> Callable[[int, int, str], None] | None:
                        if progress_callback is None:
                            return None
                        total_changes = len(deleted_files) + len(modified_files_list) + len(added_files_list)
                        base_progress = 25 + int(len(deleted_files) / max(total_changes, 1) * 30)
                        return lambda c, _t, m: progress_callback(
                            base_progress + int((start + c) / len(modified_files_list) * 25),
                            100,
                            m,
                        )

                    successful, failed = self._handle_modified_files(
                        batch,
                        progress_callback=make_modified_callback(batch_start),
                    )

                    total_successful += successful
                    total_failed += failed
                    self._save_state()

            # Step 3c: Handle added files (new) - process normally
            if added_files_list:
                self.logger.info("Processing %d added/new files", len(added_files_list))

                for batch_start in range(0, len(added_files_list), self.batch_size):
                    batch_end = min(batch_start + self.batch_size, len(added_files_list))
                    batch = added_files_list[batch_start:batch_end]

                    self.logger.info(
                        "Processing added batch %d-%d of %d files",
                        batch_start + 1,
                        batch_end,
                        len(added_files_list),
                    )

                    def make_added_callback(
                        start: int,
                    ) -> Callable[[int, int, str], None] | None:
                        if progress_callback is None:
                            return None
                        if incremental and self.state.last_commit:
                            total_changes = len(deleted_files) + len(modified_files_list) + len(added_files_list)
                            base_progress = 25 + int(
                                (len(deleted_files) + len(modified_files_list)) / max(total_changes, 1) * 55
                            )
                            return lambda c, _t, m: progress_callback(
                                base_progress + int((start + c) / len(added_files_list) * 20),
                                100,
                                m,
                            )
                        # Full mode
                        return lambda c, _t, m: progress_callback(
                            20 + int((start + c) / len(added_files_list) * 70),
                            100,
                            m,
                        )

                    successful, failed = self._process_batch(
                        batch,
                        progress_callback=make_added_callback(batch_start),
                    )

                    total_successful += successful
                    total_failed += failed
                    self._save_state()

            # Step 4: Finalize
            self.state.last_commit = current_commit
            self.state.completed = True
            self._save_state()
            self.repo_manager.save_metadata(current_commit)

            if progress_callback:
                progress_callback(100, 100, "Pipeline complete!")

            # Calculate statistics
            end_time = datetime.now(UTC)
            duration = (end_time - start_time).total_seconds()

            total_files_processed = (
                len(added_files_list) + len(modified_files_list) + len(deleted_files)
                if incremental and self.state.last_commit
                else len(files_to_process)
            )

            stats = PipelineStats(
                total_files=total_files_processed,
                processed_files=total_successful,
                failed_files=total_failed,
                total_chunks=self.state.total_chunks,
                total_documents=self.state.total_documents,
                duration_seconds=duration,
                chunks_per_second=(self.state.total_chunks / duration if duration > 0 else 0),
                files_per_second=total_successful / duration if duration > 0 else 0,
            )

            self.logger.info("Pipeline completed successfully")
            self.logger.info("  Files processed: %d", stats.processed_files)
            self.logger.info("  Files failed: %d", stats.failed_files)
            self.logger.info("  Total chunks: %d", stats.total_chunks)
            self.logger.info("  Duration: %.2f seconds", stats.duration_seconds)
            self.logger.info(
                "  Throughput: %.2f files/sec, %.2f chunks/sec",
                stats.files_per_second,
                stats.chunks_per_second,
            )

            return stats

        except Exception as e:
            self.logger.exception("Pipeline failed")
            self._save_state()
            msg = f"Pipeline execution failed: {e}"
            raise RuntimeError(msg) from e

    def reset(self, keep_repo: bool = True) -> None:
        """Reset pipeline state and optionally vector store.

        Args:
            keep_repo: If True, keep the cloned repository, else remove it
        """
        self.logger.info("Resetting pipeline state")

        # Reset vector store
        self.vector_store.reset()
        self.logger.info("Vector store reset")

        # Remove state file
        if self.state_file.exists():
            self.state_file.unlink()
            self.logger.info("Removed state file")

        # Remove repository if requested
        if not keep_repo and self.repo_manager.clone_path.exists():
            shutil.rmtree(self.repo_manager.clone_path)
            self.logger.info("Removed repository")

        # Reset internal state
        self.state = PipelineState()
        self.logger.info("Pipeline reset complete")

    def get_status(self) -> dict[str, Any]:
        """Get current pipeline status.

        Returns:
            Dictionary with current status information
        """
        return {
            "state": self.state.to_dict(),
            "repo_path": str(self.repo_manager.clone_path),
            "repo_exists": self.repo_manager.clone_path.exists(),
            "vector_store_count": self.vector_store.get_document_count(),
            "vector_store_collection": self.vector_store.collection_name,
        }
