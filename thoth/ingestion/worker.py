"""Ingestion worker HTTP server for Cloud Run.

This module provides the HTTP application with routing to workflow endpoints.
All business logic has been extracted to the flows/ package for modularity:
- health.py: Health check endpoint
- clone.py: Clone handbook to GCS
- ingest.py: Main ingestion workflow (file listing, batching, Cloud Tasks)
- batch.py: Batch processing with idempotency checks
- merge.py: Merge isolated batch LanceDB tables into main store
- job_status.py: Job status and listing endpoints

The worker maintains singleton instances for shared services:
- SourceRegistry: Multi-source configuration (handbook, dnd, personal)
- JobManager: Firestore job tracking with sub-job aggregation
- TaskQueueClient: Cloud Tasks batch distribution
"""

import logging
import os

from starlette.applications import Starlette
from starlette.routing import Route
import uvicorn

from thoth.ingestion import flows
from thoth.shared.utils.logger import configure_root_logger, setup_logger

# Configure root logger for the application
configure_root_logger(level=logging.INFO)
logger = setup_logger(__name__)

# Batch prefix pattern for parallel processing (GCS path under bucket)
BATCH_PREFIX_PATTERN = "lancedb_batch_"


# =============================================================================
# Application Setup
# =============================================================================


def create_app() -> Starlette:
    """Create the Starlette application with all routes."""
    routes = [
        # Health
        Route("/health", endpoint=flows.health_check),
        Route("/", endpoint=flows.health_check),
        # Handbook clone
        Route("/clone-handbook", endpoint=flows.clone_handbook, methods=["POST"]),
        # Ingestion
        Route("/ingest", endpoint=flows.ingest, methods=["POST"]),
        Route("/ingest-batch", endpoint=flows.process_batch, methods=["POST"]),
        Route("/merge-batches", endpoint=flows.merge_batches, methods=["POST"]),
        # Job status
        Route("/jobs/{job_id}", endpoint=flows.get_job_status),
        Route("/jobs", endpoint=flows.list_jobs),
    ]

    return Starlette(debug=False, routes=routes)


def main() -> None:
    """Run the uvicorn server."""
    port = int(os.getenv("PORT", "8080"))
    app = create_app()

    logger.info("Starting ingestion worker on port %d", port)
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="info")  # nosec B104


if __name__ == "__main__":
    main()
