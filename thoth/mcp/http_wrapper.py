"""HTTP wrapper for MCP server to work with Cloud Run.

This module provides both health check endpoints and SSE transport
for the MCP server to enable remote connections from clients like Claude Desktop.

Authentication is handled at the Cloud Run ingress level via IAM.
"""

from http.server import BaseHTTPRequestHandler, HTTPServer
import json
from typing import Any

from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route
import uvicorn

from thoth.mcp.server.server import ThothMCPServer
from thoth.shared.health import HealthCheck
from thoth.shared.utils.logger import configure_root_logger, setup_logger

configure_root_logger()
logger = setup_logger(__name__)


class HealthHTTPHandler(BaseHTTPRequestHandler):
    """HTTP request handler for health checks (standalone health server).

    Serves GET /health and GET / with JSON health status. Used when running
    a health-only server. Authentication is handled at Cloud Run ingress via IAM.
    """

    def do_GET(self) -> None:
        """Handle GET: /health and / return JSON health status; others 404."""
        if self.path in {"/health", "/"}:
            try:
                status = HealthCheck.get_health_status()
                self.send_response(200 if status["status"] == "healthy" else 503)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps(status).encode())
            except Exception as e:
                logger.exception("Health check failed")
                self.send_response(500)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"status": "error", "message": str(e)}).encode())
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A002
        """Override to use logging instead of print."""
        logger.info("%s - %s", self.address_string(), format % args)


def run_health_server(port: int = 8080) -> None:
    """Run a blocking HTTP server that only serves health checks.

    Binds to 0.0.0.0:port and serves GET /health and GET / with JSON health
    status. Exits on KeyboardInterrupt.

    Args:
        port: TCP port to listen on (default: 8080).

    Returns:
        None. Runs until interrupted.
    """
    server = HTTPServer(("0.0.0.0", port), HealthHTTPHandler)  # nosec B104
    logger.info("HTTP health server listening on port %d", port)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        logger.info("Health server shutting down")
        server.shutdown()


def main() -> None:
    """Main entry point for MCP server on Cloud Run (SSE + health).

    Creates ThothMCPServer, wraps it in an SSE Starlette app, adds /health and /
    routes, and runs Uvicorn on port 8080. Use this when deploying the MCP
    server to Cloud Run.

    Returns:
        None. Runs until process is killed.
    """
    logger.info("Starting Thoth MCP Server (Cloud Run mode with SSE)")

    # Create MCP server instance
    mcp_server = ThothMCPServer()
    sse_app = mcp_server.get_sse_app()

    # Add health check route to SSE app
    async def health_check(_request: Request) -> JSONResponse:
        status = HealthCheck.get_health_status()
        return JSONResponse(status, status_code=200 if status["status"] == "healthy" else 503)

    # Add health routes to existing SSE routes
    sse_app.routes.append(Route("/health", endpoint=health_check))
    sse_app.routes.append(Route("/", endpoint=health_check))

    # Run Uvicorn server with ASGI app
    logger.info("Starting Uvicorn server on port 8080")
    uvicorn.run(
        sse_app,
        host="0.0.0.0",  # nosec B104 - Required for Cloud Run
        port=8080,
        log_level="info",
        access_log=True,
    )


if __name__ == "__main__":
    main()
