"""Ingestion worker HTTP server for Cloud Run.

This module provides HTTP endpoints for ingestion operations:
- /clone-to-gcs: Clone repository to GCS
- /ingest: Trigger parallel batch ingestion
- /ingest-batch: Process a specific file batch
- /health: Health check
"""

import asyncio
import json
import logging
import os

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route
import uvicorn

from thoth.ingestion.pipeline import IngestionPipeline
from thoth.shared.health import HealthCheck

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def health_check(_request: Request) -> JSONResponse:
    """Health check endpoint."""
    status = HealthCheck.get_health_status()
    return JSONResponse(status, status_code=200 if status["status"] == "healthy" else 503)


async def clone_to_gcs(_request: Request) -> JSONResponse:
    """Clone repository to GCS (one-time setup)."""
    try:
        logger.info("Clone to GCS triggered via HTTP endpoint")

        pipeline = IngestionPipeline()
        if not pipeline.gcs_repo_sync:
            return JSONResponse(
                {"status": "error", "message": "GCS repo sync not configured (not in Cloud Run environment)"},
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
        logger.exception("Failed to clone repository to GCS")
        return JSONResponse({"status": "error", "message": str(e)}, status_code=500)


async def process_batch(request: Request) -> JSONResponse:
    """Process a specific batch of files."""
    try:
        body = await request.json()
        start_index = body.get("start_index")
        end_index = body.get("end_index")
        file_list = body.get("file_list")

        if start_index is None or end_index is None:
            return JSONResponse({"status": "error", "message": "Missing start_index or end_index"}, status_code=400)

        logger.info("Processing batch: files %d-%d", start_index, end_index)

        # Run ingestion in executor to avoid blocking
        pipeline = IngestionPipeline()
        result = await asyncio.get_event_loop().run_in_executor(
            None,
            pipeline.process_file_batch,
            start_index,
            end_index,
            file_list,
        )

        # Sync vector store to GCS after batch processing
        sync_result = await asyncio.get_event_loop().run_in_executor(
            None,
            pipeline.vector_store.sync_to_gcs,
            "chroma_db",
        )
        if sync_result:
            logger.info("Synced vector store to GCS: %d files", sync_result.get("uploaded_files", 0))

        return JSONResponse({"status": "success", **result})
    except Exception as e:
        logger.exception("Failed to process batch")
        return JSONResponse({"status": "error", "message": str(e)}, status_code=500)


async def sync_vector_store(_request: Request) -> JSONResponse:
    """Manually sync vector store to GCS."""
    try:
        logger.info("Manual vector store sync triggered")

        pipeline = IngestionPipeline()
        result = await asyncio.get_event_loop().run_in_executor(
            None,
            pipeline.vector_store.sync_to_gcs,
            "chroma_db",
        )

        if result:
            return JSONResponse({"status": "success", **result})
        return JSONResponse({"status": "error", "message": "GCS sync not configured"}, status_code=400)
    except Exception as e:
        logger.exception("Failed to sync vector store")
        return JSONResponse({"status": "error", "message": str(e)}, status_code=500)


async def trigger_ingestion(_request: Request) -> JSONResponse:
    """Trigger handbook ingestion by creating Cloud Tasks for parallel processing."""
    try:
        from google.cloud import tasks_v2  # noqa: PLC0415

        logger.info("Ingestion triggered via HTTP endpoint")

        # Get configuration from environment
        project_id = os.getenv("GCP_PROJECT_ID")
        location = os.getenv("CLOUD_TASKS_LOCATION", "us-central1")
        queue_name = os.getenv("CLOUD_TASKS_QUEUE", "thoth-ingestion-queue")
        service_url = os.getenv("CLOUD_RUN_SERVICE_URL")

        if not project_id or not service_url:
            msg = "Missing required environment variables: GCP_PROJECT_ID, CLOUD_RUN_SERVICE_URL"
            raise ValueError(msg)

        # Get file list
        pipeline = IngestionPipeline()
        logger.info("Calling get_file_list()...")
        try:
            file_list = await asyncio.get_event_loop().run_in_executor(None, pipeline.get_file_list)
            total_files = len(file_list)
            logger.info("Found %d files to process", total_files)
        except Exception:
            logger.exception("Error getting file list")
            raise

        # Create Cloud Tasks client
        client = tasks_v2.CloudTasksClient()
        parent = client.queue_path(project_id, location, queue_name)

        # Determine batch size (configurable via env)
        batch_size = int(os.getenv("BATCH_SIZE", "100"))
        num_batches = (total_files + batch_size - 1) // batch_size

        logger.info("Creating %d tasks for %d files (batch size: %d)", num_batches, total_files, batch_size)

        # Create tasks for each batch
        task_names = []
        for i in range(num_batches):
            start_idx = i * batch_size
            end_idx = min((i + 1) * batch_size, total_files)

            # Create task payload
            payload = {
                "start_index": start_idx,
                "end_index": end_idx,
                "file_list": file_list,  # Include file list to avoid re-discovery
            }

            # Create HTTP task
            task = tasks_v2.Task(
                http_request=tasks_v2.HttpRequest(
                    http_method=tasks_v2.HttpMethod.POST,
                    url=f"{service_url}/ingest-batch",
                    headers={"Content-Type": "application/json"},
                    body=json.dumps(payload).encode(),
                    oidc_token=tasks_v2.OidcToken(service_account_email=os.getenv("SERVICE_ACCOUNT_EMAIL")),
                )
            )

            # Submit task
            response = client.create_task(request={"parent": parent, "task": task})
            task_names.append(response.name)

        logger.info("Successfully created %d tasks", len(task_names))

        return JSONResponse(
            {
                "status": "success",
                "message": f"Ingestion started with {len(task_names)} parallel tasks",
                "total_files": total_files,
                "num_tasks": len(task_names),
                "batch_size": batch_size,
            }
        )
    except Exception as e:
        logger.exception("Failed to trigger ingestion")
        return JSONResponse({"status": "error", "message": str(e)}, status_code=500)


def main() -> None:
    """Main entry point for ingestion worker."""
    logger.info("Starting Thoth Ingestion Worker (Cloud Run)")

    # Create Starlette app with ingestion routes
    routes = [
        Route("/health", endpoint=health_check),
        Route("/", endpoint=health_check),
        Route("/clone-to-gcs", endpoint=clone_to_gcs, methods=["POST"]),
        Route("/ingest", endpoint=trigger_ingestion, methods=["POST"]),
        Route("/ingest-batch", endpoint=process_batch, methods=["POST"]),
        Route("/sync-vector-store", endpoint=sync_vector_store, methods=["POST"]),
    ]

    app = Starlette(routes=routes)

    # Run Uvicorn server
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
