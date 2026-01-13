"""HTTP wrapper for MCP server to work with Cloud Run.

This module provides a simple HTTP server that keeps the container alive
and provides a health endpoint for Cloud Run probes. The MCP server itself
uses stdio transport and is not directly accessible via HTTP.
"""

import asyncio
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import logging
import sys
import threading
from typing import Any

from thoth.health import HealthCheck

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class HealthHTTPHandler(BaseHTTPRequestHandler):
    """Simple HTTP handler for health checks."""

    def do_GET(self) -> None:
        """Handle GET requests."""
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
    """Run HTTP health server.

    Args:
        port: Port to listen on (default: 8080)
    """
    server = HTTPServer(("0.0.0.0", port), HealthHTTPHandler)  # nosec B104
    logger.info("HTTP health server listening on port %d", port)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        logger.info("Health server shutting down")
        server.shutdown()


def main() -> None:
    """Main entry point for Cloud Run deployment."""
    logger.info("Starting Thoth MCP Server (Cloud Run mode)")

    # Start HTTP health server in background thread
    health_thread = threading.Thread(target=run_health_server, daemon=True)
    health_thread.start()

    # Keep the main thread alive
    try:
        # Just sleep forever - the container stays alive for health checks
        # MCP server functionality would need a different invocation method
        # (e.g., triggered via Cloud Functions or Cloud Run Jobs)
        while True:
            asyncio.run(asyncio.sleep(60))
    except KeyboardInterrupt:
        logger.info("Shutting down")
        sys.exit(0)


if __name__ == "__main__":
    main()
