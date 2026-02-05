"""Main ingestion workflow.

Handles the /ingest endpoint which:
1. Lists files from GCS
2. Creates sub-jobs for each batch
3. Enqueues batches to Cloud Tasks for parallel processing
"""

import asyncio
import os
from pathlib import Path
from typing import Any

from starlette.requests import Request
from starlette.responses import JSONResponse

from thoth.ingestion.gcs_repo_sync import GCSRepoSync
from thoth.ingestion.job_manager import Job, JobStats
from thoth.ingestion.pipeline import IngestionPipeline, PipelineStats
from thoth.ingestion.singletons import (
    get_job_manager,
    get_source_registry,
    get_task_queue,
)
from thoth.shared.sources.config import SourceConfig
from thoth.shared.utils.logger import (
    extract_trace_id_from_header,
    get_job_logger,
    set_trace_context,
    setup_logger,
)

logger = setup_logger(__name__)


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


async def _discover_files_from_gcs(
    gcs_bucket: str,
    source_config: SourceConfig,
    job_logger: Any,
) -> list[str]:
    """Discover files from GCS bucket.

    Args:
        gcs_bucket: GCS bucket name
        source_config: Source configuration with gcs_prefix
        job_logger: Logger instance for job correlation

    Returns:
        List of file paths in GCS
    """
    repo_url = os.getenv("GITLAB_BASE_URL", "https://gitlab.com") + "/gitlab-com/content-sites/handbook.git"
    gcs_sync = GCSRepoSync(
        bucket_name=gcs_bucket,
        repo_url=repo_url,
        gcs_prefix=source_config.gcs_prefix,
        local_path=Path(f"/tmp/{source_config.name}"),  # nosec B108
        logger_instance=job_logger,
    )
    job_logger.info("Listing files from GCS bucket...")
    file_list = await asyncio.get_event_loop().run_in_executor(
        None,
        gcs_sync.list_files_in_gcs,
    )
    job_logger.info(
        "File listing complete",
        extra={"total_files": len(file_list)},
    )
    return file_list


async def _discover_files_locally(
    source_config: SourceConfig,
    job_logger: Any,
) -> list[str]:
    """Fallback: discover files from local repository.

    Returns:
        List of file paths
    """
    job_logger.info("GCS not configured, discovering files from local repository...")
    pipeline = IngestionPipeline(
        collection_name=source_config.collection_name,
        source_config=source_config,
        logger_instance=job_logger,
    )
    return await asyncio.get_event_loop().run_in_executor(
        None,
        pipeline.get_file_list,
    )


def _create_sub_jobs_for_batches(
    job_manager: Any,
    job: Job,
    file_list: list[str],
    batch_size: int,
    job_logger: Any,
) -> list[Job]:
    """Create Firestore sub-jobs for each batch.

    Returns:
        List of created sub-jobs
    """
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
    return sub_jobs


async def _enqueue_batches_to_cloud_tasks(
    task_queue: Any,
    job: Job,
    file_list: list[str],
    source_config: SourceConfig,
    batch_size: int,
    job_logger: Any,
) -> Any:
    """Enqueue batches to Cloud Tasks for parallel processing.

    Returns:
        Dictionary with enqueue results
    """
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
    return enqueue_result


async def _run_ingestion_job(job: Job, source_config: SourceConfig, params: dict[str, Any]) -> None:
    """Run ingestion job by enqueueing batches to Cloud Tasks.

    This function:
    1. Lists files from GCS (no downloading)
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

        # Step 1: Discover files
        force: bool = params.get("force", False)
        gcs_bucket = os.getenv("GCS_BUCKET_NAME")
        gcs_project = os.getenv("GCP_PROJECT_ID")

        if gcs_bucket and gcs_project:
            file_list = await _discover_files_from_gcs(gcs_bucket, source_config, job_logger)
        else:
            file_list = await _discover_files_locally(source_config, job_logger)

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

        # Step 2: Check if Cloud Tasks is configured
        if not task_queue.is_configured():
            job_logger.warning("Cloud Tasks not configured - falling back to direct processing")
            # Fall back to direct processing (for local dev or if Tasks not set up)
            pipeline = IngestionPipeline(
                collection_name=source_config.collection_name,
                source_config=source_config,
                logger_instance=job_logger,
            )
            await _run_direct_ingestion(job, pipeline, file_list, force, job_logger)
            return

        # Step 3: Calculate batches and create sub-jobs
        batch_size = int(os.getenv("BATCH_SIZE", "100"))
        _create_sub_jobs_for_batches(job_manager, job, file_list, batch_size, job_logger)

        # Step 4: Enqueue batches to Cloud Tasks
        await _enqueue_batches_to_cloud_tasks(
            task_queue,
            job,
            file_list,
            source_config,
            batch_size,
            job_logger,
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
            "processed": stats.processed_files,
            "failed": stats.failed_files,
        },
    )
