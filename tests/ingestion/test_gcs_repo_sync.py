"""Unit tests for thoth.ingestion.gcs_repo_sync module."""

from pathlib import Path
from unittest.mock import MagicMock, patch

# Import with mocked storage to avoid requiring GCS credentials
with patch("thoth.ingestion.gcs_repo_sync.storage"):
    from thoth.ingestion.gcs_repo_sync import GCSRepoSync


class TestGCSRepoSync:
    """Test cases for GCSRepoSync functionality."""

    @patch("thoth.ingestion.gcs_repo_sync.storage")
    def test_init(self, mock_storage):
        """Test GCSRepoSync initialization."""
        sync = GCSRepoSync(
            bucket_name="test-bucket",
            repo_url="https://gitlab.com/test/repo.git",
            repo_name="test-repo",
            local_path=Path("/tmp/test"),  # nosec B108
        )

        assert sync.bucket_name == "test-bucket"
        assert sync.repo_url == "https://gitlab.com/test/repo.git"
        assert sync.repo_name == "test-repo"
        assert sync.local_path == Path("/tmp/test")  # nosec B108

    @patch("thoth.ingestion.gcs_repo_sync.storage")
    @patch("thoth.ingestion.gcs_repo_sync.subprocess")
    def test_clone_to_gcs(self, mock_subprocess, mock_storage):
        """Test cloning repository to GCS."""
        mock_subprocess.run.return_value = MagicMock(returncode=0)
        mock_bucket = MagicMock()
        mock_storage.Client.return_value.bucket.return_value = mock_bucket

        sync = GCSRepoSync(
            "test-bucket",
            "https://gitlab.com/test/repo.git",
            "test-repo",
            Path("/tmp/test"),  # nosec B108
        )

        result = sync.clone_to_gcs()

        assert result["status"] == "success"
        assert "files_uploaded" in result
        mock_subprocess.run.assert_called()

    @patch("thoth.ingestion.gcs_repo_sync.storage")
    def test_sync_to_local(self, mock_storage):
        """Test syncing from GCS to local."""
        mock_bucket = MagicMock()
        mock_blob = MagicMock()
        mock_bucket.list_blobs.return_value = [mock_blob]
        mock_storage.Client.return_value.bucket.return_value = mock_bucket

        sync = GCSRepoSync(
            "test-bucket",
            "https://gitlab.com/test/repo.git",
            "test-repo",
            Path("/tmp/test"),  # nosec B108
        )

        with patch.object(Path, "mkdir"), patch.object(Path, "exists", return_value=False):
            result = sync.sync_to_local()

        assert result["status"] == "success"
        assert "files_downloaded" in result

    @patch("thoth.ingestion.gcs_repo_sync.storage")
    def test_is_synced(self, mock_storage):
        """Test checking if local repository is synced."""
        sync = GCSRepoSync(
            "test-bucket",
            "https://gitlab.com/test/repo.git",
            "test-repo",
            Path("/tmp/test"),  # nosec B108
        )

        with (
            patch.object(Path, "exists", return_value=True),
            patch("thoth.ingestion.gcs_repo_sync.list", return_value=[Path("/tmp/test/file.txt")]),  # nosec B108
        ):
            assert sync.is_synced() is True

    @patch("thoth.ingestion.gcs_repo_sync.storage")
    def test_is_synced_empty_directory(self, mock_storage):
        """Test is_synced returns False for empty directory."""
        sync = GCSRepoSync(
            "test-bucket",
            "https://gitlab.com/test/repo.git",
            "test-repo",
            Path("/tmp/test"),  # nosec B108
        )

        with (
            patch.object(Path, "exists", return_value=True),
            patch("thoth.ingestion.gcs_repo_sync.list", return_value=[]),
        ):
            assert sync.is_synced() is False

    @patch("thoth.ingestion.gcs_repo_sync.storage")
    def test_get_local_path(self, mock_storage):
        """Test getting local path."""
        sync = GCSRepoSync(
            "test-bucket",
            "https://gitlab.com/test/repo.git",
            "test-repo",
            Path("/tmp/test"),  # nosec B108
        )

        assert sync.get_local_path() == Path("/tmp/test")  # nosec B108


class TestGCSRepoSyncErrorHandling:
    """Test error handling in GCSRepoSync."""

    @patch("thoth.ingestion.gcs_repo_sync.storage")
    @patch("thoth.ingestion.gcs_repo_sync.subprocess")
    def test_clone_to_gcs_git_failure(self, mock_subprocess, mock_storage):
        """Test handling git clone failures."""
        mock_subprocess.run.return_value = MagicMock(returncode=1, stderr="Git error")

        sync = GCSRepoSync(
            "test-bucket",
            "https://gitlab.com/test/repo.git",
            "test-repo",
            Path("/tmp/test"),  # nosec B108
        )

        result = sync.clone_to_gcs()

        assert result["status"] == "error"
        assert "message" in result

    @patch("thoth.ingestion.gcs_repo_sync.storage")
    def test_sync_to_local_gcs_failure(self, mock_storage):
        """Test handling GCS download failures."""
        mock_storage.Client.return_value.bucket.side_effect = Exception("GCS error")

        sync = GCSRepoSync(
            "test-bucket",
            "https://gitlab.com/test/repo.git",
            "test-repo",
            Path("/tmp/test"),  # nosec B108
        )

        result = sync.sync_to_local()

        assert result["status"] == "error"
