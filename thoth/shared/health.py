"""Health check logic for Cloud Run and local deployments.

This module provides checks for Python version, critical imports (LanceDB,
sentence-transformers, MCP), storage writability, and GCS configuration.
Used by the /health endpoint and monitoring to report service readiness.
"""

import importlib.util
import json
import os
from pathlib import Path
import sys
from typing import Any

from thoth.shared.utils.logger import setup_logger

logger = setup_logger(__name__)


class HealthCheck:
    """Static health checks for Python, imports, storage, and GCS config.

    Used by the HTTP health endpoint to return a single status dict; each
    check returns a bool or a dict of sub-checks. Overall status is healthy
    only when Python version and critical imports (lancedb, mcp) pass.
    """

    @staticmethod
    def check_python_version() -> bool:
        """Return True if Python version is in the supported range (3.10 to 3.12).

        Returns:
            True when 3.10 <= version < 3.13 (LanceDB/sentence-transformers compatibility).
        """
        # Python 3.13+ not yet fully supported by some deps (e.g., OnnxRuntime).
        return (3, 10) <= sys.version_info < (3, 13)

    @staticmethod
    def check_imports() -> dict[str, bool]:
        """Check that critical runtime dependencies can be imported.

        Returns:
            Dict of module name -> True if importable (lancedb, torch, sentence_transformers, mcp).
        """
        checks = {}

        checks["lancedb"] = importlib.util.find_spec("lancedb") is not None
        checks["torch"] = importlib.util.find_spec("torch") is not None
        checks["sentence_transformers"] = importlib.util.find_spec("sentence_transformers") is not None
        checks["mcp"] = importlib.util.find_spec("mcp") is not None

        return checks

    @staticmethod
    def check_storage() -> dict[str, bool]:
        """Check storage availability."""
        checks = {}

        # Check data directories
        data_dir = Path("/app/data")
        checks["data_dir_exists"] = data_dir.exists()
        checks["data_dir_writable"] = os.access(str(data_dir), os.W_OK) if data_dir.exists() else False

        return checks

    @staticmethod
    def check_gcs_config() -> dict[str, bool]:
        """Check that GCS env vars and credentials are configured.

        Returns:
            Dict with gcs_bucket_configured, gcp_project_configured,
            gcs_credentials_file_exists (when GOOGLE_APPLICATION_CREDENTIALS is set).
        """
        checks = {}
        checks["gcs_bucket_configured"] = bool(os.getenv("GCS_BUCKET_NAME"))
        checks["gcp_project_configured"] = bool(os.getenv("GCP_PROJECT_ID"))

        # Check if credentials are available
        creds_env = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
        if creds_env:
            creds_path = Path(creds_env)
            checks["gcs_credentials_file_exists"] = creds_path.exists()
        else:
            # May be using metadata server in Cloud Run
            checks["gcs_credentials_file_exists"] = False

        return checks

    @classmethod
    def get_health_status(cls) -> dict[str, Any]:
        """Return a full health status dict for the /health endpoint.

        Aggregates Python version, import checks (lancedb, torch, sentence_transformers, mcp),
        storage writability, and GCS config. Overall status is 'healthy' only when
        Python version and critical imports (lancedb, mcp) all pass.

        Returns:
            Dict with keys: status ('healthy'|'unhealthy'), python_version, python_ok,
            imports, storage, gcs.
        """
        status = {
            "status": "healthy",
            "python_version": f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
            "python_ok": cls.check_python_version(),
            "imports": cls.check_imports(),
            "storage": cls.check_storage(),
            "gcs": cls.check_gcs_config(),
        }

        # Determine overall health: Python OK and critical imports (lancedb, mcp) must pass.
        imports_status = status["imports"]
        critical_checks = [
            status["python_ok"],
            (imports_status.get("lancedb", False) if isinstance(imports_status, dict) else False),
            (imports_status.get("mcp", False) if isinstance(imports_status, dict) else False),
        ]

        if not all(critical_checks):
            status["status"] = "unhealthy"

        return status

    @classmethod
    def is_healthy(cls) -> bool:
        """Quick health check.

        Returns:
            True if service is healthy, False otherwise
        """
        status = cls.get_health_status()
        return bool(status["status"] == "healthy")


def health_check_cli() -> None:
    """Print health status to stdout and exit with 0 if healthy, 1 if unhealthy."""
    status = HealthCheck.get_health_status()

    # Print for CLI use (this is intentional for the CLI tool)
    print(json.dumps(status, indent=2))  # noqa: T201

    if status["status"] == "healthy":
        print("\n✓ Service is healthy")  # noqa: T201
        sys.exit(0)
    else:
        print("\n✗ Service is unhealthy")  # noqa: T201
        sys.exit(1)


if __name__ == "__main__":
    health_check_cli()
