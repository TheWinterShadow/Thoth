"""Google Cloud Secret Manager integration for secure credential management."""

from functools import lru_cache
import os
from typing import Any

from thoth.shared.utils.logger import setup_logger

logger = setup_logger(__name__)


class SecretManagerClient:
    """Client for accessing secrets from Google Cloud Secret Manager."""

    def __init__(self, project_id: str | None = None):
        """Initialize Secret Manager client.

        Args:
            project_id: GCP project ID. If not provided, will use GCP_PROJECT_ID env var.
        """
        self.project_id = project_id or os.getenv("GCP_PROJECT_ID")
        self._client: Any = None

    def _get_client(self) -> Any:
        """Lazy load the Secret Manager client."""
        if self._client is None:
            try:
                from google.cloud import secretmanager  # noqa: PLC0415

                self._client = secretmanager.SecretManagerServiceClient()
            except ImportError:
                logger.warning("google-cloud-secret-manager not installed. Falling back to environment variables.")
                self._client = False  # Mark as unavailable
            except Exception as e:  # noqa: BLE001
                logger.warning("Failed to initialize Secret Manager client: %s", e)
                self._client = False
        return self._client if self._client else None

    @lru_cache(  # noqa: B019 - Acceptable for singleton pattern with limited cache size
        maxsize=32
    )
    def get_secret(self, secret_id: str, version: str = "latest") -> str | None:
        """Get a secret value from Secret Manager.

        Args:
            secret_id: The ID of the secret to retrieve
            version: The version of the secret (default: "latest")

        Returns:
            The secret value as a string, or None if not found
        """
        client = self._get_client()

        if not client:
            # Fallback to environment variables
            env_var = secret_id.upper().replace("-", "_")
            value = os.getenv(env_var)
            if value:
                logger.debug("Using environment variable fallback for secret")
            return value

        if not self.project_id:
            logger.warning("GCP_PROJECT_ID not set, cannot access Secret Manager")
            return None

        try:
            # Build the resource name of the secret version
            name = f"projects/{self.project_id}/secrets/{secret_id}/versions/{version}"

            # Access the secret version
            response = client.access_secret_version(request={"name": name})

            # Return the decoded payload
            payload: str = response.payload.data.decode("UTF-8")
            logger.debug("Successfully retrieved secret from Secret Manager")
            return payload

        except Exception as e:  # noqa: BLE001
            logger.warning("Failed to retrieve secret from Secret Manager: %s", e)
            # Fallback to environment variable
            env_var = secret_id.upper().replace("-", "_")
            return os.getenv(env_var)

    def get_gitlab_token(self) -> str | None:
        """Get GitLab access token.

        Returns:
            GitLab token or None
        """
        return self.get_secret("gitlab-token")

    def get_gitlab_url(self) -> str:
        """Get GitLab base URL.

        Returns:
            GitLab URL (defaults to https://gitlab.com)
        """
        return self.get_secret("gitlab-url") or "https://gitlab.com"

    def get_google_credentials(self) -> str | None:
        """Get Google application credentials JSON.

        Returns:
            Credentials JSON string or None
        """
        return self.get_secret("google-application-credentials")


# Global instance for convenience
_secret_manager: SecretManagerClient | None = None


def get_secret_manager() -> SecretManagerClient:
    """Get or create the global SecretManagerClient instance.

    Returns:
        SecretManagerClient instance
    """
    global _secret_manager  # noqa: PLW0603
    if _secret_manager is None:
        _secret_manager = SecretManagerClient()
    return _secret_manager
