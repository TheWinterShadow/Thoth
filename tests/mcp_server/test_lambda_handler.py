"""Tests for Lambda handler."""

import json
from unittest.mock import patch

from thoth.mcp_server.lambda_handler import handler


def test_health_endpoint(lambda_event, lambda_context):
    """Test health endpoint."""
    event = lambda_event.copy()
    event["rawPath"] = "/health"
    event["requestContext"]["http"]["method"] = "GET"

    response = handler(event, lambda_context)

    assert response["statusCode"] == 200
    body = json.loads(response["body"])
    assert body["status"] == "healthy"


def test_sse_endpoint(lambda_event, lambda_context):
    """Test SSE endpoint."""
    event = lambda_event.copy()
    event["rawPath"] = "/sse"
    event["requestContext"]["http"]["method"] = "GET"

    response = handler(event, lambda_context)

    assert response["statusCode"] == 200
    assert response["headers"]["Content-Type"] == "text/event-stream"


def test_messages_endpoint(lambda_event, lambda_context):
    """Test messages endpoint."""
    event = lambda_event.copy()
    event["rawPath"] = "/messages"
    event["requestContext"]["http"]["method"] = "POST"
    event["body"] = json.dumps({"id": "test-id", "method": "test"})

    response = handler(event, lambda_context)

    assert response["statusCode"] == 200
    body = json.loads(response["body"])
    assert "jsonrpc" in body


def test_not_found(lambda_event, lambda_context):
    """Test 404 for unknown paths."""
    event = lambda_event.copy()
    event["rawPath"] = "/unknown"
    event["requestContext"]["http"]["method"] = "GET"

    response = handler(event, lambda_context)

    assert response["statusCode"] == 404


def test_error_handling(lambda_event, lambda_context):
    """Test error handling."""
    event = lambda_event.copy()
    event["rawPath"] = "/messages"
    event["requestContext"]["http"]["method"] = "POST"
    event["body"] = "invalid json"

    with patch("thoth.mcp_server.lambda_handler.ThothMCPServer") as mock_server:
        mock_server.side_effect = Exception("Test error")

        response = handler(event, lambda_context)

        assert response["statusCode"] == 500
        body = json.loads(response["body"])
        assert "error" in body
