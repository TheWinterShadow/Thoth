"""Lambda handler for refresh service.

This service handles scheduled and manual refreshes of RAG data sources,
completely separate from the MCP server to ensure failures don't affect
the core MCP functionality.
"""

import json
import logging
import os
from pathlib import Path
import tempfile
from typing import Any

from thoth.ingestion.vector_store import VectorStore

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:  # noqa: ARG001
    """AWS Lambda handler for refresh service.

    Handles EventBridge scheduled events and manual invocations to refresh
    RAG data sources and sync to S3.

    Args:
        event: Lambda event from EventBridge or manual invocation
        context: Lambda context object (unused but required by Lambda interface)

    Returns:
        Response dict with refresh status
    """
    try:
        # Get configuration from environment
        s3_bucket_name = os.getenv("S3_BUCKET_NAME")
        sync_type = event.get("sync_type", "full")

        if not s3_bucket_name:
            error_msg = "S3_BUCKET_NAME environment variable not set"
            logger.error(error_msg)
            return {
                "statusCode": 500,
                "body": json.dumps({"error": error_msg}),
            }

        logger.info(f"Starting refresh service - sync_type: {sync_type}")

        # Initialize vector store (use secure temp directory)
        temp_db_path = str(Path(tempfile.gettempdir()) / "chroma_db")
        vector_store = VectorStore(
            persist_directory=temp_db_path,
            collection_name="thoth_documents",
            s3_bucket_name=s3_bucket_name,
        )

        # Perform refresh based on sync type
        if sync_type == "incremental":
            logger.info("Performing incremental sync")
            # TODO: Implement incremental sync logic
            result = {"status": "incremental_sync_completed", "files_processed": 0}
        else:
            logger.info("Performing full sync")
            # TODO: Implement full sync logic
            result = {"status": "full_sync_completed", "files_processed": 0}

        # Sync to S3
        sync_result = vector_store.sync_to_s3(s3_prefix="chroma_db")
        logger.info(f"Synced to S3: {sync_result}")

        return {
            "statusCode": 200,
            "body": json.dumps(
                {
                    "status": "success",
                    "sync_type": sync_type,
                    "result": result,
                    "s3_sync": sync_result,
                }
            ),
        }

    except Exception as e:
        logger.exception("Error in refresh service")
        return {
            "statusCode": 500,
            "body": json.dumps({"error": str(e)}),
        }
