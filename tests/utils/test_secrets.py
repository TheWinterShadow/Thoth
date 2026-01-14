"""Tests for Secrets Manager client."""

import os
from unittest.mock import patch

from thoth.utils.secrets import SecretManagerClient


def test_get_secret_from_secrets_manager(secrets_manager_client):
    """Test getting secret from Secrets Manager."""
    # Create a secret
    secrets_manager_client.create_secret(
        Name="thoth/dev/test-secret",
        SecretString="test-value",
    )

    client = SecretManagerClient(region="us-east-1")
    value = client.get_secret("thoth/dev/test-secret")

    assert value == "test-value"


def test_get_secret_fallback_to_env(secrets_manager_client):
    """Test fallback to environment variable."""
    os.environ["THOTH_DEV_TEST_SECRET"] = "env-value"

    client = SecretManagerClient(region="us-east-1")
    # Mock client to return None (simulating failure)
    with patch.object(client, "_get_client", return_value=None):
        value = client.get_secret("thoth/dev/test-secret")

    assert value == "env-value"
    del os.environ["THOTH_DEV_TEST_SECRET"]


def test_get_gitlab_token(secrets_manager_client):
    """Test getting GitLab token."""
    secrets_manager_client.create_secret(
        Name="thoth/dev/gitlab-token",
        SecretString="test-token",
    )

    client = SecretManagerClient(region="us-east-1")
    token = client.get_gitlab_token()

    assert token == "test-token"


def test_get_gitlab_url_default(secrets_manager_client):
    """Test getting GitLab URL with default."""
    client = SecretManagerClient(region="us-east-1")
    # Mock client to return None (no secret found)
    with patch.object(client, "_get_client", return_value=None):
        url = client.get_gitlab_url()

    assert url == "https://gitlab.com"
