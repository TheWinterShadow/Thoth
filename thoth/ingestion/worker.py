"""Ingestion worker HTTP server for Cloud Run.

This module provides HTTP endpoints for ingestion operations:
- /health: Health check
- /clone-handbook: Clone GitLab handbook to GCS
- /ingest: Start ingestion job (returns job_id)
- /ingest-batch: Process a specific file batch (for Cloud Tasks)
- /merge-batches: Consolidate batch LanceDB tables into main store
- /jobs/{job_id}: Get job status
"""

import asyncio
import logging
import os
from typing import Any
import uuid

from google.cloud import storage  # type: ignore[attr-defined]
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route
import uvicorn

from thoth.ingestion.job_manager import Job, JobManager, JobStats, JobStatus
from thoth.ingestion.pipeline import IngestionPipeline, PipelineStats
from thoth.ingestion.task_queue import TaskQueueClient
from thoth.shared.health import HealthCheck
from thoth.shared.sources.config import SourceConfig, SourceRegistry
from thoth.shared.utils.logger import (
    configure_root_logger,
    extract_trace_id_from_header,
    get_job_logger,
    set_trace_context,
    setup_logger,
)
from thoth.shared.vector_store import VectorStore

# Configure root logger for the application
configure_root_logger(level=logging.INFO)
logger = setup_logger(__name__)

# Batch prefix pattern for parallel processing (GCS path under bucket)
BATCH_PREFIX_PATTERN = "lancedb_batch_"


# Global instances (lazy initialized)
class _Singletons:
    source_registry: SourceRegistry | None = None
    job_manager: JobManager | None = None
    task_queue: TaskQueueClient | None = None


def get_source_registry() -> SourceRegistry:
    """Return the global SourceRegistry singleton (creates on first call).

    Returns:
        SourceRegistry with handbook, dnd, personal configs and env overrides.
    """
    if _Singletons.source_registry is None:
        _Singletons.source_registry = SourceRegistry()
    return _Singletons.source_registry


def get_job_manager() -> JobManager:
    """Return the global JobManager singleton (creates on first call).

    Uses GCP_PROJECT_ID from the environment for Firestore. Returns the same
    instance for all callers so job state is shared across endpoints.

    Returns:
        JobManager instance.
    """
    if _Singletons.job_manager is None:
        project_id = os.getenv("GCP_PROJECT_ID")
        _Singletons.job_manager = JobManager(project_id=project_id)
    return _Singletons.job_manager


def get_task_queue() -> TaskQueueClient:
    """Return the global TaskQueueClient singleton (creates on first call).

    Used to enqueue batch tasks to Cloud Tasks. Returns the same instance
    for all callers.

    Returns:
        TaskQueueClient instance (reads queue config from env).
    """
    if _Singletons.task_queue is None:
        _Singletons.task_queue = TaskQueueClient()
    return _Singletons.task_queue


# =============================================================================
# Health Check
# =============================================================================


async def health_check(_request: Request) -> JSONResponse:
    """Health check endpoint."""
    status = HealthCheck.get_health_status()
    return JSONResponse(status, status_code=200 if status["status"] == "healthy" else 503)


# =============================================================================
# Clone Handbook
# =============================================================================


async def clone_handbook(_request: Request) -> JSONResponse:
    """Clone the GitLab handbook repo to GCS for ingestion (one-time setup).

    Uses the pipeline's GCSRepoSync to clone the repo into the configured
    bucket/prefix. Requires GCS_BUCKET_NAME and pipeline configured for GCS.

    Returns:
        JSONResponse with status and message; 200 on success, 4xx/5xx on error.
    """
    try:
        logger.info("Clone handbook to GCS triggered")

        pipeline = IngestionPipeline()
        if not pipeline.gcs_repo_sync:
            return JSONResponse(
                {
                    "status": "error",
                    "message": "GCS repo sync not configured (not in Cloud Run environment)",
                },
                status_code=400,
            )

        # Clone and upload to GCS
        result = await asyncio.get_event_loop().run_in_executor(
            None,
            pipeline.gcs_repo_sync.clone_to_gcs,
            False,  # force=False
        )

        return JSONResponse({"status": "success", **result})
    except Exception as e:
        logger.exception("Failed to clone handbook to GCS")
        return JSONResponse({"status": "error", "message": str(e)}, status_code=500)


async def ingest(request: Request) -> JSONResponse:
    """Start an ingestion job.

    Creates a job record and starts background processing.
    Returns immediately with job_id for status tracking.

    Request body:
        source: Source identifier (required) - 'handbook', 'dnd', or 'personal'
        force: Force full re-ingestion (optional, default: false)

    Returns:
        202 Accepted with job_id for status polling
    """
    # Extract trace context from Cloud Run headers for log correlation
    trace_header = request.headers.get("X-Cloud-Trace-Context")
    trace_id = extract_trace_id_from_header(trace_header)
    set_trace_context(trace_id, os.getenv("GCP_PROJECT_ID"))

    try:
        body = await request.json()
        source_name = body.get("source")

        logger.info(
            "Received ingestion request",
            extra={"source": source_name, "body": body, "trace_id": trace_id},
        )

        if not source_name:
            return JSONResponse(
                {
                    "status": "error",
                    "message": "Missing required 'source' parameter. Valid sources: handbook, dnd, personal",
                },
                status_code=400,
            )

        # Validate source
        registry = get_source_registry()
        source_config = registry.get(source_name)

        if source_config is None:
            valid_sources = registry.list_sources()
            return JSONResponse(
                {
                    "status": "error",
                    "message": f"Unknown source '{source_name}'. Valid sources: {valid_sources}",
                },
                status_code=400,
            )

        # Create job
        job_manager = get_job_manager()
        job = job_manager.create_job(source_name, source_config.collection_name)

        # Start background processing
        task = asyncio.create_task(_run_ingestion_job(job, source_config, body))
        # Keep reference to prevent garbage collection
        task.add_done_callback(lambda _: None)

        return JSONResponse(
            {
                "status": "accepted",
                "job_id": job.job_id,
                "source": source_name,
                "collection_name": source_config.collection_name,
                "message": f"Ingestion job created. Use GET /jobs/{job.job_id} to check status.",
            },
            status_code=202,
        )

    except Exception as e:
        logger.exception("Failed to create ingestion job")
        return JSONResponse({"status": "error", "message": str(e)}, status_code=500)


async def _run_ingestion_job(job: Job, source_config: SourceConfig, params: dict[str, Any]) -> None:
    """Run ingestion job by enqueueing batches to Cloud Tasks.

    This function:
    1. Syncs repository files from GCS
    2. Discovers all files to process
    3. Splits into batches and enqueues to Cloud Tasks
    4. Updates job status in Firestore

    The actual processing happens in /ingest-batch endpoint called by Cloud Tasks.
    """
    # Set trace context to job_id for log correlation in GCP
    if job.job_id:
        set_trace_context(job.job_id.replace("-", ""), os.getenv("GCP_PROJECT_ID"))

    job_manager = get_job_manager()
    task_queue = get_task_queue()

    # Create job-scoped logger for correlation
    job_logger = get_job_logger(
        logger,
        job_id=job.job_id,
        source=source_config.name,
        collection=source_config.collection_name,
    )

    try:
        job_manager.mark_running(job)
        job_logger.info(
            "Starting ingestion job",
            extra={
                "job_id": job.job_id,
                "source": source_config.name,
                "collection": source_config.collection_name,
                "params": params,
            },
        )

        # Create pipeline to access GCS sync and file discovery
        pipeline = IngestionPipeline(
            collection_name=source_config.collection_name,
            source_config=source_config,
            logger_instance=job_logger,
        )

        # Step 1: List files from GCS (fast operation - no downloading)
        force: bool = params.get("force", False)

        gcs_sync = pipeline.gcs_repo_sync
        if gcs_sync:
            job_logger.info("Listing files from GCS bucket...")
            # List files directly from GCS without downloading
            file_list = await asyncio.get_event_loop().run_in_executor(
                None,
                gcs_sync.list_files_in_gcs,
            )
            job_logger.info(
                "File listing complete",
                extra={
                    "total_files": len(file_list),
                },
            )
        else:
            # Fallback to local repo manager for development/testing
            job_logger.info("GCS not configured, discovering files from local repository...")
            file_list = await asyncio.get_event_loop().run_in_executor(
                None,
                pipeline.get_file_list,
            )

        if not file_list:
            job_logger.warning("No files found to process")
            job_stats = JobStats(
                total_files=0,
                processed_files=0,
                failed_files=0,
                total_chunks=0,
                total_documents=0,
            )
            job_manager.mark_completed(job, job_stats)
            return

        job_logger.info("Found %d files to process", len(file_list))

        # Step 3: Check if Cloud Tasks is configured
        if not task_queue.is_configured():
            job_logger.warning("Cloud Tasks not configured - falling back to direct processing")
            # Fall back to direct processing (for local dev or if Tasks not set up)
            await _run_direct_ingestion(job, pipeline, file_list, force, job_logger)
            return

        # Step 4: Calculate batches and create sub-jobs
        batch_size = int(os.getenv("BATCH_SIZE", "100"))
        total_files = len(file_list)
        num_batches = (total_files + batch_size - 1) // batch_size

        # Update parent job with total batches
        job.total_batches = num_batches
        job.stats = JobStats(total_files=total_files)
        job_manager.update_job(job)

        job_logger.info(
            "Creating sub-jobs for batches",
            extra={
                "total_files": total_files,
                "batch_size": batch_size,
                "num_batches": num_batches,
            },
        )

        # Create sub-jobs for each batch in Firestore
        sub_jobs = []
        for i in range(num_batches):
            start_idx = i * batch_size
            end_idx = min((i + 1) * batch_size, total_files)
            batch_file_count = end_idx - start_idx

            sub_job = job_manager.create_sub_job(
                parent_job=job,
                batch_index=i,
                total_files=batch_file_count,
            )
            sub_jobs.append(sub_job)

        job_logger.info("Created %d sub-jobs in Firestore", len(sub_jobs))

        # Step 5: Enqueue batches to Cloud Tasks (blocking HTTP calls run in executor).
        job_logger.info("Enqueueing batches to Cloud Tasks")

        enqueue_result = await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: task_queue.enqueue_batches(
                job_id=job.job_id,
                file_list=file_list,
                collection_name=source_config.collection_name,
                source=source_config.name,
                batch_size=batch_size,
            ),
        )

        job_logger.info(
            "Batches enqueued successfully",
            extra={
                "num_batches": enqueue_result["num_batches"],
                "enqueued": enqueue_result["enqueued"],
                "failed": enqueue_result["failed"],
            },
        )

        # Note: Job completion will be handled by /merge-batches or final batch

    except Exception as e:
        job_logger.exception(
            "Job failed",
            extra={"error_type": type(e).__name__, "error_message": str(e)},
        )
        job_manager.mark_failed(job, str(e))


async def _run_direct_ingestion(
    job: Job,
    pipeline: IngestionPipeline,
    _file_list: list[str],  # Not used - pipeline.run() discovers files
    force: bool,
    job_logger: Any,
) -> None:
    """Fallback: process all files directly without Cloud Tasks.

    Used when Cloud Tasks is not configured (local development).
    """
    job_manager = get_job_manager()

    job_logger.info("Running direct ingestion (no Cloud Tasks)")

    stats: PipelineStats = await asyncio.get_event_loop().run_in_executor(
        None,
        lambda: pipeline.run(force_reclone=force, incremental=not force),
    )

    # Update job with results
    job_stats = JobStats(
        total_files=stats.total_files,
        processed_files=stats.processed_files,
        failed_files=stats.failed_files,
        total_chunks=stats.total_chunks,
        total_documents=stats.total_documents,
    )
    job_manager.mark_completed(job, job_stats)

    job_logger.info(
        "Direct ingestion completed",
        extra={
            "total_files": stats.total_files,
            "files_processed": stats.processed_files,
            "failed": stats.failed_files,
            "chunks_created": stats.total_chunks,
            "duration_ms": int(stats.duration_seconds * 1000),
        },
    )

    # LanceDB on GCS is already synced; sync_to_gcs returns status or None for local
    sync_result = pipeline.vector_store.sync_to_gcs(f"lancedb_{pipeline.collection_name}")
    if sync_result:
        job_logger.info(
            "Collection synced to GCS",
            extra={"uri": sync_result.get("uri", "")},
        )


# =============================================================================
# Job Status
# =============================================================================


async def get_job_status(request: Request) -> JSONResponse:
    """Get job status by ID.

    Returns current status, statistics, and error information if failed.
    """
    job_id = request.path_params.get("job_id")

    if not job_id:
        return JSONResponse(
            {"status": "error", "message": "Missing job_id"},
            status_code=400,
        )

    # Check if sub-jobs should be included
    include_sub_jobs = request.query_params.get("include_sub_jobs", "true").lower() == "true"

    try:
        job_manager = get_job_manager()

        if include_sub_jobs:
            # Get job with aggregated sub-job info
            job_data = job_manager.get_job_with_sub_jobs(job_id)
            if job_data is None:
                return JSONResponse(
                    {"status": "error", "message": f"Job not found: {job_id}"},
                    status_code=404,
                )
            return JSONResponse(job_data)
        # Get just the job without sub-jobs
        job = job_manager.get_job(job_id)
        if job is None:
            return JSONResponse(
                {"status": "error", "message": f"Job not found: {job_id}"},
                status_code=404,
            )
        return JSONResponse(job.to_dict())

    except Exception as e:
        logger.exception("Failed to get job status")
        return JSONResponse({"status": "error", "message": str(e)}, status_code=500)


async def list_jobs(request: Request) -> JSONResponse:
    """List recent jobs with optional filtering.

    Query parameters:
        source: Filter by source name
        status: Filter by status (pending, running, completed, failed)
        limit: Maximum number of jobs (default: 50)
    """
    try:
        source = request.query_params.get("source")
        status_str = request.query_params.get("status")
        limit = int(request.query_params.get("limit", "50"))

        status = JobStatus(status_str) if status_str else None

        job_manager = get_job_manager()
        jobs = job_manager.list_jobs(source=source, status=status, limit=limit)

        return JSONResponse(
            {
                "status": "success",
                "jobs": [job.to_dict() for job in jobs],
                "count": len(jobs),
            }
        )

    except Exception as e:
        logger.exception("Failed to list jobs")
        return JSONResponse({"status": "error", "message": str(e)}, status_code=500)


# =============================================================================
# Batch Processing (for Cloud Tasks)
# =============================================================================


async def process_batch(request: Request) -> JSONResponse:  # noqa: PLR0912, PLR0915
    """Process a specific batch of files (called by Cloud Tasks).

    Each batch is stored in a unique GCS prefix to avoid conflicts during
    parallel processing. Use /merge-batches to consolidate.
    """
    # Extract trace context for log correlation
    trace_header = request.headers.get("X-Cloud-Trace-Context")
    trace_id = extract_trace_id_from_header(trace_header)
    set_trace_context(trace_id, os.getenv("GCP_PROJECT_ID"))

    try:
        body = await request.json()
        job_id = body.get("job_id")  # Parent job ID for tracking
        start_index = body.get("start_index")
        end_index = body.get("end_index")
        file_list = body.get("file_list")
        collection_name = body.get("collection_name", "handbook_documents")
        batch_id = body.get("batch_id")
        source = body.get("source", "unknown")

        if start_index is None or end_index is None:
            return JSONResponse(
                {"status": "error", "message": "Missing start_index or end_index"},
                status_code=400,
            )

        # Generate batch ID if not provided
        if batch_id is None:
            batch_id = f"{start_index}_{end_index}_{uuid.uuid4().hex[:8]}"

        # Create batch-scoped logger with job_id for correlation
        batch_logger = get_job_logger(
            logger,
            job_id=job_id or batch_id,
            source=source,
            collection=collection_name,
            operation="batch_processing",
        )

        file_count = len(file_list) if file_list else 0
        batch_logger.info(
            "Processing batch task",
            extra={
                "job_id": job_id,
                "batch_id": batch_id,
                "start_index": start_index,
                "end_index": end_index,
                "file_count": file_count,
            },
        )

        # Look up sub-job in Firestore (if job_id provided)
        job_manager = get_job_manager()
        sub_job = None
        if job_id and batch_id:
            # Sub-job ID format: {parent_job_id}_{batch_index:04d}
            sub_job = job_manager.get_job(batch_id)
            if sub_job:
                job_manager.mark_running(sub_job)
                batch_logger.info("Marked sub-job %s as running", batch_id)

        # Get source config if available
        registry = get_source_registry()
        source_config = None
        for cfg in registry.list_configs():
            if cfg.collection_name == collection_name:
                source_config = cfg
                break

        # Batch writes to its own GCS prefix (no merge yet)
        gcs_bucket = os.getenv("GCS_BUCKET_NAME")
        gcs_project = os.getenv("GCP_PROJECT_ID")
        batch_gcs_prefix = f"{BATCH_PREFIX_PATTERN}{collection_name}_{batch_id}"

        # Idempotency check: skip if batch already exists (duplicate run/retry)
        if gcs_bucket and gcs_project:
            storage_client = storage.Client(project=gcs_project)
            bucket = storage_client.bucket(gcs_bucket)

            # Check if batch LanceDB already exists
            existing_blobs = list(bucket.list_blobs(prefix=f"{batch_gcs_prefix}/", max_results=1))
            if existing_blobs:
                batch_logger.info(
                    "Batch already exists, skipping processing (idempotent)",
                    extra={"gcs_prefix": batch_gcs_prefix},
                )

                # Mark sub-job as completed if it exists
                if sub_job:
                    job_manager = get_job_manager()
                    # Use approximate stats since we're skipping
                    batch_stats = JobStats(
                        total_files=file_count,
                        processed_files=file_count,
                        failed_files=0,
                        total_chunks=file_count,
                        total_documents=file_count,
                    )
                    job_manager.mark_sub_job_completed(sub_job, batch_stats)

                return JSONResponse(
                    {
                        "status": "success",
                        "batch_id": batch_id,
                        "job_id": job_id,
                        "message": "Batch already processed (duplicate run)",
                        "gcs_prefix": batch_gcs_prefix,
                        "skipped": True,
                    }
                )

            batch_store = VectorStore(
                collection_name=collection_name,
                gcs_bucket_name=gcs_bucket,
                gcs_project_id=gcs_project,
                gcs_prefix_override=batch_gcs_prefix,
            )
            pipeline = IngestionPipeline(
                collection_name=collection_name,
                source_config=source_config,
                vector_store=batch_store,
                logger_instance=batch_logger,
            )
        else:
            pipeline = IngestionPipeline(
                collection_name=collection_name,
                source_config=source_config,
                logger_instance=batch_logger,
            )

        result = await asyncio.get_event_loop().run_in_executor(
            None,
            pipeline.process_file_batch,
            start_index,
            end_index,
            file_list,
        )

        # With LanceDB, batch data is already in GCS at batch_gcs_prefix
        if gcs_bucket and gcs_project:
            batch_logger.info(
                "Batch written to GCS",
                extra={"gcs_prefix": batch_gcs_prefix},
            )

        # Update sub-job status in Firestore
        if sub_job:
            batch_stats = JobStats(
                total_files=file_count,
                processed_files=result.get("successful", 0),
                failed_files=result.get("failed", 0),
                total_chunks=result.get("successful", 0),  # Approximate
                total_documents=result.get("successful", 0),
            )
            job_manager.mark_sub_job_completed(sub_job, batch_stats)
            batch_logger.info(
                "Sub-job completed",
                extra={
                    "sub_job_id": batch_id,
                    "processed": batch_stats.processed_files,
                    "failed": batch_stats.failed_files,
                },
            )

        batch_logger.info(
            "Batch processing completed",
            extra={
                "successful": result.get("successful", 0),
                "failed": result.get("failed", 0),
                "duration_ms": int(result.get("duration_seconds", 0) * 1000),
            },
        )

        return JSONResponse(
            {
                "status": "success",
                "batch_id": batch_id,
                "job_id": job_id,
                "sub_job_id": batch_id if sub_job else None,
                "gcs_prefix": batch_gcs_prefix,
                **result,
            }
        )

    except Exception as e:
        # Mark sub-job as failed if we have one
        if "sub_job" in dir() and sub_job:
            try:
                job_manager = get_job_manager()
                job_manager.mark_sub_job_failed(sub_job, str(e))
            except Exception:  # noqa: BLE001
                logger.warning("Failed to mark sub-job as failed")

        logger.exception(
            "Failed to process batch",
            extra={"error_type": type(e).__name__, "error_message": str(e)},
        )
        return JSONResponse({"status": "error", "message": str(e)}, status_code=500)


# =============================================================================
# Merge Batches
# =============================================================================


def _extract_batch_prefixes(blobs: list) -> set[str]:
    """Extract unique batch prefix names from GCS blob list."""
    batch_prefixes = set()
    for blob in blobs:
        parts = blob.name.split("/")
        if parts:
            batch_prefixes.add(parts[0])
    return batch_prefixes


async def _process_single_batch(
    batch_prefix_name: str,
    collection_name: str,
    gcs_bucket: str,
    main_store: Any,
) -> int:
    """Read a single LanceDB batch from GCS and merge into main store. Returns document count."""
    import lancedb  # noqa: PLC0415

    logger.info("Processing batch: %s", batch_prefix_name)
    batch_uri = f"gs://{gcs_bucket}/{batch_prefix_name}"

    def merge_batch() -> int:
        """Run in executor: connect to batch LanceDB on GCS and add rows to main store."""
        db = lancedb.connect(batch_uri)
        if collection_name not in list(db.list_tables()):
            logger.warning("Batch %s has no table %s", batch_prefix_name, collection_name)
            return 0
        table = db.open_table(collection_name)
        tbl = table.to_arrow()
        if tbl.num_rows == 0:
            return 0
        d = tbl.to_pydict()
        meta_cols = [c for c in tbl.column_names if c not in ("id", "text", "vector")]
        metadatas = [dict(zip(meta_cols, [d[c][i] for c in meta_cols], strict=True)) for i in range(tbl.num_rows)]
        vec_col = d["vector"]
        vectors = [v.tolist() if hasattr(v, "tolist") else list(v) for v in vec_col]
        main_store.add_documents(
            documents=d["text"],
            metadatas=metadatas,
            ids=d["id"],
            embeddings=vectors,
        )
        return int(tbl.num_rows)

    try:
        # Run merge in thread pool; LanceDB I/O is blocking.
        doc_count = await asyncio.get_event_loop().run_in_executor(None, merge_batch)
        if doc_count > 0:
            logger.info("Merged %d documents from %s", doc_count, batch_prefix_name)
        return int(doc_count)
    except (ValueError, KeyError, RuntimeError, OSError) as e:
        logger.warning("Failed to merge batch %s: %s", batch_prefix_name, e)
        raise


def _cleanup_batch_from_gcs(batch_prefix_name: str, gcs_sync: Any) -> bool:
    """Delete all blobs under a batch prefix in GCS (after merge).

    Args:
        batch_prefix_name: GCS prefix (e.g., lancedb_batch_handbook_documents_0).
        gcs_sync: GCSSync instance with bucket access.

    Returns:
        True if all blobs were deleted, False on error.
    """
    try:
        blobs_to_delete = list(gcs_sync.bucket.list_blobs(prefix=f"{batch_prefix_name}/"))
        for blob in blobs_to_delete:
            blob.delete()
        logger.info("Deleted batch from GCS: %s", batch_prefix_name)
        return True
    except (OSError, RuntimeError) as e:
        logger.warning("Failed to delete batch %s: %s", batch_prefix_name, e)
        return False


async def merge_batches(request: Request) -> JSONResponse:
    """Merge all batch LanceDB tables from GCS into the main store.

    Expects JSON body: collection_name (optional), cleanup (optional, default True).
    Lists GCS prefixes matching lancedb_batch_{collection}_*, connects to each
    LanceDB URI, and adds documents to the main store. Optionally deletes batch
    prefixes from GCS after merge.

    Returns:
        JSONResponse with status, merged_count, batches_merged, batches_cleaned.
    """
    try:
        body = await request.json()
        collection_name = body.get("collection_name", "handbook_documents")
        cleanup = body.get("cleanup", True)

        logger.info("Starting merge for collection: %s", collection_name)

        from thoth.shared.gcs_sync import GCSSync  # noqa: PLC0415
        from thoth.shared.vector_store import VectorStore  # noqa: PLC0415

        gcs_bucket = os.getenv("GCS_BUCKET_NAME")
        gcs_project = os.getenv("GCP_PROJECT_ID")

        if not gcs_bucket or not gcs_project:
            return JSONResponse(
                {"status": "error", "message": "GCS not configured"},
                status_code=400,
            )

        gcs_sync = GCSSync(bucket_name=gcs_bucket, project_id=gcs_project)

        batch_prefix = f"{BATCH_PREFIX_PATTERN}{collection_name}_"
        blobs = list(gcs_sync.bucket.list_blobs(prefix=batch_prefix))
        batch_prefixes = _extract_batch_prefixes(blobs)

        if not batch_prefixes:
            return JSONResponse(
                {
                    "status": "success",
                    "message": "No batches found to merge",
                    "batches_merged": 0,
                }
            )

        logger.info("Found %d batches to merge", len(batch_prefixes))

        main_store = VectorStore(
            persist_directory="/tmp/lancedb",  # nosec B108 - unused when GCS set
            collection_name=collection_name,
            gcs_bucket_name=gcs_bucket,
            gcs_project_id=gcs_project,
        )

        total_documents = 0
        merged_batches = []

        for batch_prefix_name in sorted(batch_prefixes):
            try:
                doc_count = await _process_single_batch(batch_prefix_name, collection_name, gcs_bucket, main_store)
                total_documents += doc_count
                merged_batches.append(batch_prefix_name)
            except (ValueError, KeyError, RuntimeError, OSError):
                continue

        # Main store is already at gs://bucket/lancedb; no sync needed

        deleted_batches = [b for b in merged_batches if _cleanup_batch_from_gcs(b, gcs_sync)] if cleanup else []

        return JSONResponse(
            {
                "status": "success",
                "collection_name": collection_name,
                "batches_merged": len(merged_batches),
                "total_documents": total_documents,
                "batches_cleaned": len(deleted_batches) if cleanup else 0,
                "final_uri": main_store.uri,
            }
        )

    except Exception as e:
        logger.exception("Failed to merge batches")
        return JSONResponse({"status": "error", "message": str(e)}, status_code=500)


# =============================================================================
# Application Setup
# =============================================================================


def create_app() -> Starlette:
    """Create the Starlette application with all routes."""
    routes = [
        # Health
        Route("/health", endpoint=health_check),
        Route("/", endpoint=health_check),
        # Handbook clone
        Route("/clone-handbook", endpoint=clone_handbook, methods=["POST"]),
        # Ingestion
        Route("/ingest", endpoint=ingest, methods=["POST"]),
        Route("/ingest-batch", endpoint=process_batch, methods=["POST"]),
        Route("/merge-batches", endpoint=merge_batches, methods=["POST"]),
        # Jobs
        Route("/jobs", endpoint=list_jobs, methods=["GET"]),
        Route("/jobs/{job_id}", endpoint=get_job_status, methods=["GET"]),
    ]

    return Starlette(routes=routes)


def main() -> None:
    """Main entry point for ingestion worker."""
    logger.info("Starting Thoth Ingestion Worker (Cloud Run)")

    app = create_app()

    logger.info("Starting Uvicorn server on port 8080")
    uvicorn.run(
        app,
        host="0.0.0.0",  # nosec B104 - Required for Cloud Run
        port=8080,
        log_level="info",
        access_log=True,
    )


if __name__ == "__main__":
    main()
