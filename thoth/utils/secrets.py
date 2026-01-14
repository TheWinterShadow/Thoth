"""AWS Secrets Manager integration for secure credential management."""

from functools import lru_cache
import logging
import os
from typing import Any

try:
    import boto3
except ImportError:
    boto3 = None  # type: ignore[assignment, unused-ignore]

logger = logging.getLogger(__name__)


class SecretManagerClient:
    """Client for accessing secrets from AWS Secrets Manager."""

    def __init__(self, region: str | None = None):
        """Initialize Secrets Manager client.

        Args:
            region: AWS region. If not provided, will use AWS_REGION env var or us-east-1.
        """
        self.region = region or os.getenv("AWS_REGION", "us-east-1")
        self._client: Any = None

    def _get_client(self) -> Any:
        """Lazy load the Secrets Manager client."""
        if self._client is None:
            try:
                if boto3 is None:
                    logger.warning("boto3 not installed. Falling back to environment variables.")
                    self._client = False  # Mark as unavailable
                else:
                    self._client = boto3.client("secretsmanager", region_name=self.region)
            except Exception as e:  # noqa: BLE001
                logger.warning("Failed to initialize Secrets Manager client: %s", e)
                self._client = False
        return self._client if self._client else None

    @lru_cache(  # noqa: B019 - Acceptable for singleton pattern with limited cache size
        maxsize=32
    )
    def get_secret(self, secret_name: str, version_stage: str = "AWSCURRENT") -> str | None:
        """Get a secret value from Secrets Manager.

        Args:
            secret_name: The name or ARN of the secret to retrieve
            version_stage: The version stage of the secret (default: "AWSCURRENT")

        Returns:
            The secret value as a string, or None if not found
        """
        client = self._get_client()

        if not client:
            # Fallback to environment variables
            env_var = secret_name.upper().replace("-", "_").replace("/", "_")
            value = os.getenv(env_var)
            if value:
                logger.debug("Using environment variable fallback for secret")
            return value

        try:
            # Get the secret value
            response = client.get_secret_value(SecretId=secret_name, VersionStage=version_stage)

            # Return the secret string
            secret_string: str = response.get("SecretString", "")
            logger.debug("Successfully retrieved secret from Secrets Manager")
            return secret_string

        except Exception as e:  # noqa: BLE001
            logger.warning("Failed to retrieve secret from Secrets Manager: %s", e)
            # Fallback to environment variable
            env_var = secret_name.upper().replace("-", "_").replace("/", "_")
            return os.getenv(env_var)

    def get_gitlab_token(self) -> str | None:
        """Get GitLab access token.

        Returns:
            GitLab token or None
        """
        # Try multiple possible secret names
        secret_names = [
            "thoth/dev/gitlab-token",
            "thoth/gitlab-token",
            "gitlab-token",
        ]
        for secret_name in secret_names:
            token = self.get_secret(secret_name)
            if token:
                return token
        return None

    def get_gitlab_url(self) -> str:
        """Get GitLab base URL.

        Returns:
            GitLab URL (defaults to https://gitlab.com)
        """
        # Try multiple possible secret names
        secret_names = [
            "thoth/dev/gitlab-url",
            "thoth/gitlab-url",
            "gitlab-url",
        ]
        for secret_name in secret_names:
            url = self.get_secret(secret_name)
            if url:
                return url
        return "https://gitlab.com"

    def get_api_key(self) -> str | None:
        """Get API key for HTTP endpoint authentication.

        Returns:
            API key or None
        """
        # Try multiple possible secret names
        secret_names = [
            "thoth/dev/api-key",
            "thoth/api-key",
            "api-key",
        ]
        for secret_name in secret_names:
            api_key = self.get_secret(secret_name)
            if api_key:
                return api_key
        return None


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
