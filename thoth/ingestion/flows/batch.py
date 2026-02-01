"""Batch processing workflow.

Handles the /ingest-batch endpoint which processes a specific batch of files
in parallel. Each batch writes to its own isolated LanceDB table.
"""

import asyncio
import os
from typing import Any
import uuid

from google.cloud import storage  # type: ignore[attr-defined]
from starlette.requests import Request
from starlette.responses import JSONResponse

from thoth.ingestion.job_manager import JobStats
from thoth.ingestion.pipeline import IngestionPipeline
from thoth.ingestion.singletons import get_job_manager, get_source_registry
from thoth.shared.utils.logger import (
    extract_trace_id_from_header,
    get_job_logger,
    set_trace_context,
    setup_logger,
)
from thoth.shared.vector_store import VectorStore

logger = setup_logger(__name__)

# Batch prefix pattern for GCS storage isolation
BATCH_PREFIX_PATTERN = "lancedb_batch_"


def _parse_batch_request(
    body: dict,
) -> tuple[str | None, int | None, int | None, list[str], str, str | None, str]:
    """Parse and extract batch request parameters.

    Returns:
        Tuple of (job_id, start_index, end_index, file_list, collection_name, batch_id, source)
    """
    job_id = body.get("job_id")
    start_index = body.get("start_index")
    end_index = body.get("end_index")
    file_list = body.get("file_list", [])
    collection_name = body.get("collection_name", "handbook_documents")
    batch_id = body.get("batch_id")
    source = body.get("source", "unknown")

    return job_id, start_index, end_index, file_list, collection_name, batch_id, source


def _check_batch_exists(
    gcs_bucket: str,
    gcs_project: str,
    batch_gcs_prefix: str,
    batch_logger: Any,
) -> bool:
    """Check if batch already exists in GCS (idempotency check).

    Returns:
        True if batch exists and should be skipped, False otherwise
    """
    storage_client = storage.Client(project=gcs_project)
    bucket = storage_client.bucket(gcs_bucket)

    existing_blobs = list(bucket.list_blobs(prefix=f"{batch_gcs_prefix}/", max_results=1))
    if existing_blobs:
        batch_logger.info(
            "Batch already exists, skipping processing (idempotent)",
            extra={"gcs_prefix": batch_gcs_prefix},
        )
        return True
    return False


async def _process_batch_files(
    pipeline: IngestionPipeline,
    start_index: int,
    end_index: int,
    file_list: list[str],
) -> dict:
    """Execute batch file processing.

    Returns:
        Processing result dictionary with successful/failed counts
    """
    return await asyncio.get_event_loop().run_in_executor(
        None,
        pipeline.process_file_batch,
        start_index,
        end_index,
        file_list,
    )


def _create_batch_pipeline(
    collection_name: str,
    source_config: Any,
    batch_gcs_prefix: str,
    gcs_bucket: str | None,
    gcs_project: str | None,
    batch_logger: Any,
) -> IngestionPipeline:
    """Create ingestion pipeline for batch processing.

    Returns:
        Configured IngestionPipeline instance
    """
    if gcs_bucket and gcs_project:
        batch_store = VectorStore(
            collection_name=collection_name,
            gcs_bucket_name=gcs_bucket,
            gcs_project_id=gcs_project,
            gcs_prefix_override=batch_gcs_prefix,
        )
        return IngestionPipeline(
            collection_name=collection_name,
            source_config=source_config,
            vector_store=batch_store,
            logger_instance=batch_logger,
        )
    # Local/dev mode
    return IngestionPipeline(
        collection_name=collection_name,
        source_config=source_config,
        logger_instance=batch_logger,
    )


def _update_sub_job_completion(
    job_manager: Any,
    sub_job: Any,
    result: dict,
    file_count: int,
    batch_id: str,
    batch_logger: Any,
) -> None:
    """Update sub-job status in Firestore after completion."""
    batch_stats = JobStats(
        total_files=file_count,
        processed_files=result.get("successful", 0),
        failed_files=result.get("failed", 0),
        total_chunks=result.get("successful", 0),
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


def _lookup_sub_job(
    job_manager: Any,
    job_id: str | None,
    batch_id: str | None,
    batch_logger: Any,
) -> Any:
    """Look up and mark sub-job as running in Firestore.

    Returns:
        Sub-job object if found, None otherwise
    """
    sub_job = None
    if job_id and batch_id:
        sub_job = job_manager.get_job(batch_id)
        if sub_job:
            job_manager.mark_running(sub_job)
            batch_logger.info("Marked sub-job %s as running", batch_id)
    return sub_job


def _get_source_config(registry: Any, collection_name: str) -> Any:
    """Look up source configuration by collection name.

    Returns:
        SourceConfig if found, None otherwise
    """
    for cfg in registry.list_configs():
        if cfg.collection_name == collection_name:
            return cfg
    return None


async def process_batch(request: Request) -> JSONResponse:
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
        job_id, start_index, end_index, file_list, collection_name, batch_id, source = _parse_batch_request(body)

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

        file_count = len(file_list)
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
        sub_job = _lookup_sub_job(job_manager, job_id, batch_id, batch_logger)

        # Get source config if available
        registry = get_source_registry()
        source_config = _get_source_config(registry, collection_name)

        # Batch writes to its own GCS prefix (no merge yet)
        gcs_bucket = os.getenv("GCS_BUCKET_NAME")
        gcs_project = os.getenv("GCP_PROJECT_ID")
        batch_gcs_prefix = f"{BATCH_PREFIX_PATTERN}{collection_name}_{batch_id}"

        # Idempotency check: skip if batch already exists
        if gcs_bucket and gcs_project and _check_batch_exists(gcs_bucket, gcs_project, batch_gcs_prefix, batch_logger):
            # Mark sub-job as completed if it exists
            if sub_job:
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

        # Create pipeline for batch processing
        pipeline = _create_batch_pipeline(
            collection_name,
            source_config,
            batch_gcs_prefix,
            gcs_bucket,
            gcs_project,
            batch_logger,
        )

        # Process the batch
        result = await _process_batch_files(pipeline, start_index, end_index, file_list)

        # With LanceDB, batch data is already in GCS at batch_gcs_prefix
        if gcs_bucket and gcs_project:
            batch_logger.info(
                "Batch written to GCS",
                extra={"gcs_prefix": batch_gcs_prefix},
            )

        # Update sub-job status in Firestore
        if sub_job:
            _update_sub_job_completion(job_manager, sub_job, result, file_count, batch_id, batch_logger)

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
