"""Ingestion worker HTTP server for Cloud Run.

This module provides HTTP endpoints for ingestion operations:
- /health: Health check
- /clone-handbook: Clone GitLab handbook to GCS
- /ingest: Start ingestion job (returns job_id)
- /ingest-batch: Process a specific file batch (for Cloud Tasks)
- /merge-batches: Consolidate batch ChromaDBs
- /jobs/{job_id}: Get job status
"""

import asyncio
import logging
import os
from typing import Any
import uuid

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route
import uvicorn

from thoth.ingestion.job_manager import Job, JobManager, JobStats, JobStatus
from thoth.ingestion.pipeline import IngestionPipeline, PipelineStats
from thoth.shared.health import HealthCheck
from thoth.shared.sources.config import SourceConfig, SourceRegistry

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Batch prefix pattern for parallel processing
BATCH_PREFIX_PATTERN = "chroma_db_batch_"


# Global instances (lazy initialized)
class _Singletons:
    source_registry: SourceRegistry | None = None
    job_manager: JobManager | None = None


def get_source_registry() -> SourceRegistry:
    """Get or create the source registry singleton."""
    if _Singletons.source_registry is None:
        _Singletons.source_registry = SourceRegistry()
    return _Singletons.source_registry


def get_job_manager() -> JobManager:
    """Get or create the job manager singleton."""
    if _Singletons.job_manager is None:
        project_id = os.getenv("GCP_PROJECT_ID")
        _Singletons.job_manager = JobManager(project_id=project_id)
    return _Singletons.job_manager


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
    """Clone GitLab handbook repository to GCS (one-time setup)."""
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
    try:
        body = await request.json()
        source_name = body.get("source")

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


async def _run_ingestion_job(job: Job, source_config: SourceConfig, params: dict) -> None:
    """Run ingestion job in background.

    Updates job status in Firestore as processing progresses.
    """
    job_manager = get_job_manager()

    try:
        job_manager.mark_running(job)

        # Create pipeline for this source
        pipeline = IngestionPipeline(
            collection_name=source_config.collection_name,
            source_config=source_config,
        )

        # Run ingestion
        force = params.get("force", False)
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

        # Sync to GCS
        gcs_prefix = f"chroma_db_{source_config.collection_name}"
        await asyncio.get_event_loop().run_in_executor(
            None,
            pipeline.vector_store.sync_to_gcs,
            gcs_prefix,
        )
        logger.info("Synced collection '%s' to GCS prefix '%s'", source_config.collection_name, gcs_prefix)

    except Exception as e:
        logger.exception("Job %s failed", job.job_id)
        job_manager.mark_failed(job, str(e))


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

    try:
        job_manager = get_job_manager()
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


async def process_batch(request: Request) -> JSONResponse:
    """Process a specific batch of files (called by Cloud Tasks).

    Each batch is stored in a unique GCS prefix to avoid conflicts during
    parallel processing. Use /merge-batches to consolidate.
    """
    try:
        body = await request.json()
        start_index = body.get("start_index")
        end_index = body.get("end_index")
        file_list = body.get("file_list")
        collection_name = body.get("collection_name", "handbook_documents")
        batch_id = body.get("batch_id")

        if start_index is None or end_index is None:
            return JSONResponse(
                {"status": "error", "message": "Missing start_index or end_index"},
                status_code=400,
            )

        # Generate batch ID if not provided
        if batch_id is None:
            batch_id = f"{start_index}_{end_index}_{uuid.uuid4().hex[:8]}"

        logger.info("Processing batch %s: files %d-%d", batch_id, start_index, end_index)

        # Get source config if available
        registry = get_source_registry()
        source_config = None
        for cfg in registry.list_configs():
            if cfg.collection_name == collection_name:
                source_config = cfg
                break

        # Run ingestion in executor
        pipeline = IngestionPipeline(collection_name=collection_name, source_config=source_config)
        result = await asyncio.get_event_loop().run_in_executor(
            None,
            pipeline.process_file_batch,
            start_index,
            end_index,
            file_list,
        )

        # Sync to unique GCS prefix
        batch_gcs_prefix = f"{BATCH_PREFIX_PATTERN}{collection_name}_{batch_id}"
        sync_result = await asyncio.get_event_loop().run_in_executor(
            None,
            pipeline.vector_store.sync_to_gcs,
            batch_gcs_prefix,
        )

        if sync_result:
            logger.info(
                "Synced batch %s to GCS prefix '%s': %d files",
                batch_id,
                batch_gcs_prefix,
                sync_result.get("uploaded_files", 0),
            )

        return JSONResponse(
            {
                "status": "success",
                "batch_id": batch_id,
                "gcs_prefix": batch_gcs_prefix,
                **result,
            }
        )

    except Exception as e:
        logger.exception("Failed to process batch")
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
    gcs_sync: Any,
    main_store: Any,
) -> int:
    """Process a single batch and merge into main store. Returns document count."""
    import shutil  # noqa: PLC0415

    import chromadb  # noqa: PLC0415
    from chromadb.config import Settings  # noqa: PLC0415

    logger.info("Processing batch: %s", batch_prefix_name)
    batch_local_path = f"/tmp/batch_{batch_prefix_name}"  # nosec B108

    # Create a callable for run_in_executor
    def download_batch() -> None:
        gcs_sync.download_directory(batch_prefix_name, batch_local_path, clean_local=True)

    await asyncio.get_event_loop().run_in_executor(None, download_batch)

    batch_client = chromadb.PersistentClient(
        path=batch_local_path,
        settings=Settings(anonymized_telemetry=False),
    )

    try:
        batch_collection = batch_client.get_collection(name=collection_name)
        batch_docs = batch_collection.get(include=["documents", "metadatas", "embeddings"])  # type: ignore[list-item]

        if batch_docs["ids"]:
            main_store.add_documents(
                documents=batch_docs["documents"],
                metadatas=batch_docs["metadatas"],
                ids=batch_docs["ids"],
                embeddings=batch_docs["embeddings"],
            )
            doc_count = len(batch_docs["ids"])
            logger.info("Merged %d documents from %s", doc_count, batch_prefix_name)
            return doc_count
    except (ValueError, KeyError, RuntimeError) as e:
        logger.warning("Failed to extract from batch %s: %s", batch_prefix_name, e)
        raise
    finally:
        shutil.rmtree(batch_local_path, ignore_errors=True)

    return 0


def _cleanup_batch_from_gcs(batch_prefix_name: str, gcs_sync: Any) -> bool:
    """Delete a batch prefix from GCS. Returns True if successful."""
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
    """Merge all batch ChromaDBs into the main collection.

    This endpoint consolidates parallel batch processing results.
    Call after all batch tasks have completed.
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

        # List and extract batch prefixes
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

        # Create main vector store
        main_store = VectorStore(
            persist_directory=f"/tmp/chroma_db_merged_{collection_name}",  # nosec B108
            collection_name=collection_name,
            gcs_bucket_name=gcs_bucket,
            gcs_project_id=gcs_project,
        )

        # Process all batches
        total_documents = 0
        merged_batches = []

        for batch_prefix_name in sorted(batch_prefixes):
            try:
                doc_count = await _process_single_batch(batch_prefix_name, collection_name, gcs_sync, main_store)
                total_documents += doc_count
                merged_batches.append(batch_prefix_name)
            except (ValueError, KeyError, RuntimeError):
                continue

        # Sync merged store
        final_prefix = f"chroma_db_{collection_name}"
        await asyncio.get_event_loop().run_in_executor(
            None,
            main_store.sync_to_gcs,
            final_prefix,
        )
        logger.info("Synced merged collection to GCS: %s", final_prefix)

        # Cleanup batch prefixes
        deleted_batches = [b for b in merged_batches if _cleanup_batch_from_gcs(b, gcs_sync)] if cleanup else []

        return JSONResponse(
            {
                "status": "success",
                "collection_name": collection_name,
                "batches_merged": len(merged_batches),
                "total_documents": total_documents,
                "batches_cleaned": len(deleted_batches) if cleanup else 0,
                "final_gcs_prefix": final_prefix,
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
