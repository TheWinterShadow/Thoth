"""Health check endpoint for Cloud Run deployments."""

import importlib.util
import json
import os
from pathlib import Path
import sys
from typing import Any

from thoth.shared.utils.logger import setup_logger

logger = setup_logger(__name__)


class HealthCheck:
    """Health check functionality for monitoring service health."""

    @staticmethod
    def check_python_version() -> bool:
        """Check if Python version is acceptable."""
        # ChromaDB/OnnxRuntime does not yet support Python 3.13
        return (3, 10) <= sys.version_info < (3, 13)

    @staticmethod
    def check_imports() -> dict[str, bool]:
        """Check if critical imports are available."""
        checks = {}

        checks["chromadb"] = importlib.util.find_spec("chromadb") is not None
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
        """Check GCS configuration."""
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
        """Get comprehensive health status.

        Returns:
            Dictionary with health check results
        """
        status = {
            "status": "healthy",
            "python_version": f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
            "python_ok": cls.check_python_version(),
            "imports": cls.check_imports(),
            "storage": cls.check_storage(),
            "gcs": cls.check_gcs_config(),
        }

        # Determine overall health
        imports_status = status["imports"]
        critical_checks = [
            status["python_ok"],
            (imports_status.get("chromadb", False) if isinstance(imports_status, dict) else False),
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
    """CLI command for health check."""
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
