"""Tests for refresh service handler."""

import json
import os
from unittest.mock import MagicMock, patch

from thoth.refresh.handler import handler


def test_refresh_handler_success(lambda_event, lambda_context):
    """Test successful refresh."""
    os.environ["S3_BUCKET_NAME"] = "test-bucket"

    event = {
        "sync_type": "full",
    }

    with (
        patch("thoth.refresh.handler.S3Sync") as mock_s3_sync,
        patch("thoth.refresh.handler.VectorStore") as mock_vector_store,
    ):
        mock_s3 = MagicMock()
        mock_s3_sync.return_value = mock_s3

        mock_store = MagicMock()
        mock_store.sync_to_s3.return_value = {"uploaded_files": 10}
        mock_vector_store.return_value = mock_store

        response = handler(event, lambda_context)

        assert response["statusCode"] == 200
        body = json.loads(response["body"])
        assert body["status"] == "success"


def test_refresh_handler_missing_bucket(lambda_event, lambda_context):
    """Test refresh with missing bucket."""
    if "S3_BUCKET_NAME" in os.environ:
        del os.environ["S3_BUCKET_NAME"]

    event = {"sync_type": "full"}

    response = handler(event, lambda_context)

    assert response["statusCode"] == 500
    body = json.loads(response["body"])
    assert "error" in body


def test_refresh_handler_error(lambda_event, lambda_context):
    """Test refresh error handling."""
    os.environ["S3_BUCKET_NAME"] = "test-bucket"

    event = {"sync_type": "full"}

    with patch("thoth.refresh.handler.S3Sync") as mock_s3_sync:
        mock_s3_sync.side_effect = Exception("Test error")

        response = handler(event, lambda_context)

        assert response["statusCode"] == 500
        body = json.loads(response["body"])
        assert "error" in body
