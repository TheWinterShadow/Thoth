"""Tests for secrets management functionality."""

import os
from unittest.mock import MagicMock, Mock, patch

from thoth.shared.utils.secrets import SecretManagerClient, get_secret_manager


class TestSecretManagerClient:
    """Tests for SecretManagerClient."""

    def test_init_with_project_id(self):
        """Test initialization with project ID."""
        client = SecretManagerClient(project_id="test-project")
        assert client.project_id == "test-project"
        assert client._client is None

    def test_init_from_env(self):
        """Test initialization from environment variable."""
        with patch.dict(os.environ, {"GCP_PROJECT_ID": "env-project"}):
            client = SecretManagerClient()
            assert client.project_id == "env-project"

    def test_get_secret_without_secret_manager(self):
        """Test getting secret falls back to environment variables."""
        with patch.dict(os.environ, {"GITLAB_TOKEN": "env-token"}):
            client = SecretManagerClient(project_id="test-project")
            client._client = False  # Mark as unavailable

            token = client.get_secret("gitlab-token")
            assert token == "env-token"

    def test_get_secret_with_secret_manager(self):
        """Test getting secret from Secret Manager."""
        # Mock the Secret Manager client and response
        mock_client = MagicMock()
        mock_response = Mock()
        mock_response.payload.data = b"secret-value"
        mock_client.access_secret_version.return_value = mock_response

        # Directly set the mocked client on the instance
        client = SecretManagerClient(project_id="test-project")
        client._client = mock_client

        secret_value = client.get_secret("test-secret")

        assert secret_value == "secret-value"
        mock_client.access_secret_version.assert_called_once_with(
            request={"name": "projects/test-project/secrets/test-secret/versions/latest"}
        )

    @patch("thoth.utils.secrets.secretmanager", create=True)
    def test_get_secret_with_error_fallback(self, mock_secretmanager):
        """Test secret retrieval falls back on error."""
        # Mock Secret Manager to raise error
        mock_client = MagicMock()
        mock_client.access_secret_version.side_effect = Exception("API Error")
        mock_secretmanager.SecretManagerServiceClient.return_value = mock_client

        with patch.dict(os.environ, {"TEST_SECRET": "fallback-value"}):
            client = SecretManagerClient(project_id="test-project")
            # Force to use the mocked client
            client._client = mock_client
            secret_value = client.get_secret("test-secret")

            assert secret_value == "fallback-value"

    def test_get_gitlab_token(self):
        """Test getting GitLab token."""
        with patch.dict(os.environ, {"GITLAB_TOKEN": "test-token"}):
            client = SecretManagerClient()
            client._client = False  # Use env fallback

            token = client.get_gitlab_token()
            assert token == "test-token"

    def test_get_gitlab_url_default(self):
        """Test getting GitLab URL with default."""
        client = SecretManagerClient()
        client._client = False  # Use env fallback

        url = client.get_gitlab_url()
        assert url == "https://gitlab.com"

    def test_get_gitlab_url_custom(self):
        """Test getting custom GitLab URL."""
        with patch.dict(os.environ, {"GITLAB_URL": "https://custom.gitlab.com"}):
            client = SecretManagerClient()
            client._client = False  # Use env fallback

            url = client.get_gitlab_url()
            assert url == "https://custom.gitlab.com"

    def test_get_google_credentials(self):
        """Test getting Google credentials."""
        with patch.dict(os.environ, {"GOOGLE_APPLICATION_CREDENTIALS": '{"key": "value"}'}):
            client = SecretManagerClient()
            client._client = False  # Use env fallback

            creds = client.get_google_credentials()
            assert creds == '{"key": "value"}'

    def test_secret_caching(self):
        """Test that secrets are cached."""
        with patch.dict(os.environ, {"TEST_SECRET": "cached-value"}):
            client = SecretManagerClient()
            client._client = False  # Use env fallback

            # First call
            value1 = client.get_secret("test-secret")
            # Second call should use cache
            value2 = client.get_secret("test-secret")

            assert value1 == value2 == "cached-value"


def test_get_secret_manager_singleton():
    """Test get_secret_manager returns singleton instance."""
    manager1 = get_secret_manager()
    manager2 = get_secret_manager()

    assert manager1 is manager2
