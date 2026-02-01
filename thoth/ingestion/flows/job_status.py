"""Job status and listing endpoints."""

from starlette.requests import Request
from starlette.responses import JSONResponse

from thoth.ingestion.job_manager import JobStatus
from thoth.ingestion.singletons import get_job_manager
from thoth.shared.utils.logger import setup_logger

logger = setup_logger(__name__)


async def get_job_status(request: Request) -> JSONResponse:
    """Get job status by ID.

    Returns current status, statistics, and error information if failed.
    """
    job_id = request.path_params.get("job_id")

    if not job_id:
        return JSONResponse(
            {"status": "error", "message": "Missing job_id"},
            status_code=400,
        )

    # Check if sub-jobs should be included
    include_sub_jobs = request.query_params.get("include_sub_jobs", "true").lower() == "true"

    try:
        job_manager = get_job_manager()

        if include_sub_jobs:
            # Get job with aggregated sub-job info
            job_data = job_manager.get_job_with_sub_jobs(job_id)
            if job_data is None:
                return JSONResponse(
                    {"status": "error", "message": f"Job not found: {job_id}"},
                    status_code=404,
                )
            return JSONResponse(job_data)

        # Get just the job without sub-jobs
        job = job_manager.get_job(job_id)
        if job is None:
            return JSONResponse(
                {"status": "error", "message": f"Job not found: {job_id}"},
                status_code=404,
            )
        return JSONResponse(job.to_dict())

    except Exception as e:
        logger.exception("Failed to get job status")
        return JSONResponse({"status": "error", "message": str(e)}, status_code=500)


async def list_jobs(request: Request) -> JSONResponse:
    """List recent jobs with optional filtering.

    Query parameters:
        source: Filter by source name
        status: Filter by status (pending, running, completed, failed)
        limit: Maximum number of jobs (default: 50)
    """
    try:
        source = request.query_params.get("source")
        status_str = request.query_params.get("status")
        limit = int(request.query_params.get("limit", "50"))

        status = JobStatus(status_str) if status_str else None

        job_manager = get_job_manager()
        jobs = job_manager.list_jobs(source=source, status=status, limit=limit)

        return JSONResponse(
            {
                "status": "success",
                "jobs": [job.to_dict() for job in jobs],
                "count": len(jobs),
            }
        )

    except Exception as e:
        logger.exception("Failed to list jobs")
        return JSONResponse({"status": "error", "message": str(e)}, status_code=500)
