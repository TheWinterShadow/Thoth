"""Tests for GitLab API client."""

from datetime import UTC, datetime, timedelta
import os
import time
import unittest
from unittest.mock import Mock, patch

import requests

from thoth.ingestion.gitlab_api import (
    CacheEntry,
    GitLabAPIClient,
    GitLabAPIError,
)


class TestCacheEntry(unittest.TestCase):
    """Tests for CacheEntry class."""

    def test_cache_entry_not_expired(self):
        """Test cache entry is not expired within TTL."""
        entry = CacheEntry({"data": "test"}, ttl=60)
        self.assertFalse(entry.is_expired())

    def test_cache_entry_expired(self):
        """Test cache entry expires after TTL."""
        entry = CacheEntry({"data": "test"}, ttl=0)
        time.sleep(0.1)
        self.assertTrue(entry.is_expired())

    def test_cache_entry_data(self):
        """Test cache entry stores data correctly."""
        test_data = {"key": "value", "list": [1, 2, 3]}
        entry = CacheEntry(test_data, ttl=60)
        self.assertEqual(entry.data, test_data)


class TestGitLabAPIClient(unittest.TestCase):
    """Tests for GitLabAPIClient class."""

    def setUp(self):
        """Set up test fixtures."""
        # Mock environment variables to prevent CI environment from interfering
        self.env_patcher = patch.dict("os.environ", {}, clear=False)
        self.env_mock = self.env_patcher.start()
        # Ensure GITLAB_TOKEN and GITLAB_BASE_URL are not set
        os.environ.pop("GITLAB_TOKEN", None)
        os.environ.pop("GITLAB_BASE_URL", None)

        self.client = GitLabAPIClient(
            token="test-token",
            base_url="https://gitlab.com/api/v4",
            timeout=30,
            max_retries=3,
        )
        self.mock_response = self._create_mock_response()

    def tearDown(self):
        """Clean up test fixtures."""
        self.env_patcher.stop()

    def _create_mock_response(self):
        """Create mock response."""
        response = Mock()
        response.status_code = 200
        response.headers = {
            "RateLimit-Remaining": "100",
            "RateLimit-Reset": str(int((datetime.now(tz=UTC) + timedelta(hours=1)).timestamp())),
        }
        response.json.return_value = {"data": "test"}
        response.content = b'{"data": "test"}'
        return response

    def test_client_initialization(self):
        """Test client initializes correctly."""
        self.assertEqual(self.client.token, "test-token")
        self.assertEqual(self.client.base_url, "https://gitlab.com/api/v4")
        self.assertEqual(self.client.timeout, 30)
        self.assertEqual(self.client.session.headers["PRIVATE-TOKEN"], "test-token")

    def test_client_without_token(self):
        """Test client can be created without token."""
        client = GitLabAPIClient()
        self.assertIsNone(client.token)
        self.assertNotIn("PRIVATE-TOKEN", client.session.headers)

    def test_cache_key_generation(self):
        """Test cache key generation."""
        key1 = self.client._get_cache_key("/projects/123")
        key2 = self.client._get_cache_key("/projects/123", {"page": 1, "per_page": 10})
        key3 = self.client._get_cache_key("/projects/123", {"per_page": 10, "page": 1})

        self.assertEqual(key1, "/projects/123")
        self.assertEqual(key2, key3)
        self.assertIn("page=1", key2)
        self.assertIn("per_page=10", key2)

    def test_cache_operations(self):
        """Test cache add, get, and expiry."""
        cache_key = "test_key"
        test_data = {"test": "data"}

        self.client._add_to_cache(cache_key, test_data, ttl=1)
        cached = self.client._get_from_cache(cache_key)
        self.assertEqual(cached, test_data)

        time.sleep(2)
        expired = self.client._get_from_cache(cache_key)
        self.assertIsNone(expired)

    def test_clear_cache(self):
        """Test cache clearing."""
        self.client._add_to_cache("key1", {"data": 1})
        self.client._add_to_cache("key2", {"data": 2})
        self.assertEqual(len(self.client._cache), 2)

        self.client.clear_cache()
        self.assertEqual(len(self.client._cache), 0)

    @patch("requests.Session.request")
    def test_make_request_success(self, mock_request):
        """Test successful API request."""
        mock_request.return_value = self.mock_response

        result = self.client.get("/projects/123")

        self.assertEqual(result, {"data": "test"})
        mock_request.assert_called_once()
        self.assertEqual(self.client._rate_limit_remaining, 100)

    @patch("requests.Session.request")
    def test_caching_get_request(self, mock_request):
        """Test GET request caching."""
        mock_request.return_value = self.mock_response

        result1 = self.client.get("/projects/123", use_cache=True)
        self.assertEqual(mock_request.call_count, 1)

        result2 = self.client.get("/projects/123", use_cache=True)
        self.assertEqual(mock_request.call_count, 1)
        self.assertEqual(result1, result2)

    @patch("requests.Session.request")
    def test_rate_limit_handling(self, mock_request):
        """Test rate limit handling."""
        rate_limit_response = Mock()
        rate_limit_response.status_code = 429
        rate_limit_response.headers = {"Retry-After": "1"}

        success_response = Mock()
        success_response.status_code = 200
        success_response.headers = {
            "RateLimit-Remaining": "100",
            "RateLimit-Reset": str(int((datetime.now(tz=UTC) + timedelta(hours=1)).timestamp())),
        }
        success_response.json.return_value = {"data": "test"}
        success_response.content = b'{"data": "test"}'

        mock_request.side_effect = [rate_limit_response, success_response]

        result = self.client.get("/projects/123", use_cache=False)

        self.assertEqual(result, {"data": "test"})
        self.assertEqual(mock_request.call_count, 2)

    @patch("requests.Session.request")
    def test_http_error_handling(self, mock_request):
        """Test HTTP error handling."""
        mock_request.side_effect = requests.exceptions.HTTPError("404 Not Found")

        with self.assertRaises(GitLabAPIError):
            self.client.get("/projects/999")

    @patch("requests.Session.request")
    def test_get_project(self, mock_request):
        """Test get_project method."""
        response = self._create_mock_response()
        response.json.return_value = {
            "id": 123,
            "name": "test-project",
            "path": "test-project",
        }
        mock_request.return_value = response

        result = self.client.get_project("123")

        self.assertEqual(result["id"], 123)
        self.assertEqual(result["name"], "test-project")

    @patch("requests.Session.request")
    def test_get_commits(self, mock_request):
        """Test get_commits method."""
        response = self._create_mock_response()
        response.json.return_value = [
            {"id": "abc123", "message": "commit 1"},
            {"id": "def456", "message": "commit 2"},
        ]
        mock_request.return_value = response

        result = self.client.get_commits("123", ref="main", since="2024-01-01")

        self.assertEqual(len(result), 2)
        call_kwargs = mock_request.call_args[1]
        self.assertEqual(call_kwargs["params"]["since"], "2024-01-01")

    @patch("requests.Session.request")
    def test_get_current_user(self, mock_request):
        """Test get_current_user method."""
        response = self._create_mock_response()
        response.json.return_value = {
            "id": 1,
            "username": "testuser",
        }
        mock_request.return_value = response

        result = self.client.get_current_user()

        self.assertEqual(result["username"], "testuser")

    def test_get_current_user_without_token(self):
        """Test get_current_user fails without token."""
        client = GitLabAPIClient()

        with self.assertRaises(GitLabAPIError) as exc_info:
            client.get_current_user()

        self.assertIn("Authentication token required", str(exc_info.exception))

    def test_get_rate_limit_info(self):
        """Test get_rate_limit_info method."""
        self.client._rate_limit_remaining = 50
        self.client._rate_limit_reset = datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC)

        info = self.client.get_rate_limit_info()

        self.assertEqual(info["remaining"], 50)
        self.assertIn("2024-01-01", info["reset_at"])


if __name__ == "__main__":
    unittest.main()
