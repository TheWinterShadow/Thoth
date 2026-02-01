"""Health check endpoint."""

from starlette.requests import Request
from starlette.responses import JSONResponse

from thoth.shared.health import HealthCheck


async def health_check(_request: Request) -> JSONResponse:
    """Health check endpoint.

    Returns service health status.
    """
    status = HealthCheck.get_health_status()
    return JSONResponse(status)
