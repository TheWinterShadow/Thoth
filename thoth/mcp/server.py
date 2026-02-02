"""Thoth MCP Server - HTTP server for MCP protocol.

This module handles web traffic and endpoint setup.
MCP tools are defined in tools.py.
"""

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Mount, Route
import uvicorn

from thoth.mcp.tools import mcp
from thoth.shared.health import HealthCheck
from thoth.shared.utils.logger import configure_root_logger, setup_logger

configure_root_logger()
logger = setup_logger(__name__)


async def health_check(_request: Request) -> JSONResponse:
    """Return health status."""
    status = HealthCheck.get_health_status()
    return JSONResponse(status, status_code=200 if status["status"] == "healthy" else 503)


# Create Starlette app with SSE and health routes
app = Starlette(
    routes=[
        Route("/health", endpoint=health_check),
        Route("/", endpoint=health_check),
        Mount("/mcp", app=mcp.sse_app()),
    ]
)


def main() -> None:
    """Run the MCP server."""
    logger.info("Starting Thoth MCP Server")
    uvicorn.run(
        app,
        host="0.0.0.0",  # nosec B104 - Required for Cloud Run
        port=8080,
        log_level="info",
    )


if __name__ == "__main__":
    main()
