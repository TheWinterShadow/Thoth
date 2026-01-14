"""Lambda handler for MCP Server on AWS Lambda."""

import json
import logging
from typing import Any

from thoth.mcp_server.server import ThothMCPServer

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:  # noqa: ARG001
    """AWS Lambda handler for MCP Server.

    Handles API Gateway HTTP API events and routes them to the appropriate
    MCP server endpoints.

    Args:
        event: Lambda event from API Gateway
        context: Lambda context object (unused but required by Lambda interface)

    Returns:
        API Gateway HTTP API response
    """
    try:
        # Extract request information
        request_context = event.get("requestContext", {})
        http_method = request_context.get("http", {}).get("method", "GET")
        path = event.get("rawPath", "/")

        logger.info(f"Received {http_method} request to {path}")

        # Initialize server (can be cached in production)
        ThothMCPServer(
            name="thoth-mcp-server",
            version="1.0.0",
        )

        # Route based on path
        if path == "/health":
            return {
                "statusCode": 200,
                "headers": {"Content-Type": "application/json"},
                "body": json.dumps({"status": "healthy", "service": "thoth-mcp-server"}),
            }

        if path == "/sse" and http_method == "GET":
            # SSE endpoint - return connection info
            # Note: Full SSE support requires response streaming or polling
            return {
                "statusCode": 200,
                "headers": {
                    "Content-Type": "text/event-stream",
                    "Cache-Control": "no-cache",
                    "Connection": "keep-alive",
                },
                "body": 'data: {"type":"connection","status":"ready"}\n\n',
            }

        if path == "/messages" and http_method == "POST":
            # Handle MCP messages
            body = event.get("body", "{}")
            if isinstance(body, str):
                body = json.loads(body)

            # Process MCP message
            # This is a simplified handler - full implementation would
            # integrate with the MCP server's message handling
            return {
                "statusCode": 200,
                "headers": {"Content-Type": "application/json"},
                "body": json.dumps(
                    {
                        "jsonrpc": "2.0",
                        "id": body.get("id"),
                        "result": {"message": "MCP message processed"},
                    }
                ),
            }

        return {
            "statusCode": 404,
            "headers": {"Content-Type": "application/json"},
            "body": json.dumps({"error": "Not found"}),
        }

    except Exception as e:
        logger.exception("Error processing request")
        return {
            "statusCode": 500,
            "headers": {"Content-Type": "application/json"},
            "body": json.dumps({"error": str(e)}),
        }
