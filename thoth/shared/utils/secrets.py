"""Google Cloud Secret Manager integration for secure credential management."""

from functools import lru_cache
import os
from typing import Any

from thoth.shared.utils.logger import setup_logger

logger = setup_logger(__name__)


class SecretManagerClient:
    """Client for reading secrets from Google Cloud Secret Manager.

    Provides lazy-initialization of the Secret Manager API client and
    fallback to environment variables when the API is unavailable or
    when running locally. Used for GitLab tokens, GCP credentials, etc.
    """

    def __init__(self, project_id: str | None = None):
        """Initialize the Secret Manager client (API not called until first use).

        Args:
            project_id: GCP project ID for Secret Manager. If None, uses the
                GCP_PROJECT_ID environment variable.

        Returns:
            None.
        """
        self.project_id = project_id or os.getenv("GCP_PROJECT_ID")
        self._client: Any = None

    def _get_client(self) -> Any:
        """Lazy-load the Secret Manager API client (or None if unavailable).

        On first call, attempts to import and instantiate
        google.cloud.secretmanager.SecretManagerServiceClient. If the package
        is missing or initialization fails, returns None and callers fall back
        to environment variables.

        Returns:
            SecretManagerServiceClient instance, or None if unavailable.
        """
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
    """Return the global SecretManagerClient singleton, creating it if needed.

    Uses a module-level variable so that all callers share the same client
    and lazy-initialization happens only once.

    Returns:
        The global SecretManagerClient instance.
    """
    global _secret_manager  # noqa: PLW0603
    if _secret_manager is None:
        _secret_manager = SecretManagerClient()
    return _secret_manager
