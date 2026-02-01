"""Clone handbook repository to GCS."""

import asyncio

from starlette.requests import Request
from starlette.responses import JSONResponse

from thoth.ingestion.pipeline import IngestionPipeline
from thoth.shared.utils.logger import setup_logger

logger = setup_logger(__name__)


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
