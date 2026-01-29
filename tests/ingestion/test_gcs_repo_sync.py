"""Unit tests for thoth.ingestion.gcs_repo_sync module."""

from pathlib import Path
import tempfile
from unittest.mock import MagicMock, patch

from git.exc import GitCommandError
import pytest

# Import with mocked storage to avoid requiring GCS credentials
with patch("thoth.ingestion.gcs_repo_sync.storage"):
    from thoth.ingestion.gcs_repo_sync import GCSRepoSync


class TestGCSRepoSync:
    """Test cases for GCSRepoSync functionality."""

    @patch("thoth.ingestion.gcs_repo_sync.storage")
    def test_init(self, mock_storage):
        """Test GCSRepoSync initialization."""
        mock_bucket = MagicMock()
        mock_storage.Client.return_value.bucket.return_value = mock_bucket

        sync = GCSRepoSync(
            bucket_name="test-bucket",
            repo_url="https://gitlab.com/test/repo.git",
            gcs_prefix="test-prefix",
            local_path=Path("/tmp/test"),  # nosec B108
        )

        assert sync.bucket_name == "test-bucket"
        assert sync.repo_url == "https://gitlab.com/test/repo.git"
        assert sync.gcs_prefix == "test-prefix"
        assert sync.local_path == Path("/tmp/test")  # nosec B108

    @patch("thoth.ingestion.gcs_repo_sync.Repo")
    @patch("thoth.ingestion.gcs_repo_sync.storage")
    def test_clone_to_gcs(self, mock_storage, mock_repo):
        """Test cloning repository to GCS."""
        mock_bucket = MagicMock()
        mock_bucket.list_blobs.return_value = []  # No existing files
        mock_blob = MagicMock()
        mock_bucket.blob.return_value = mock_blob
        mock_storage.Client.return_value.bucket.return_value = mock_bucket

        sync = GCSRepoSync(
            "test-bucket",
            "https://gitlab.com/test/repo.git",
            "handbook",
            Path("/tmp/test"),  # nosec B108
        )

        # Mock the clone to create some files
        with patch("tempfile.TemporaryDirectory") as mock_tmpdir:
            mock_tmpdir.return_value.__enter__.return_value = "/tmp/fake_tmpdir"  # nosec B108
            with patch("pathlib.Path.rglob") as mock_rglob:
                mock_file = MagicMock()
                mock_file.is_file.return_value = True
                mock_file.relative_to.return_value = Path("file.md")
                mock_file.__str__ = lambda _: "/tmp/fake_tmpdir/repo/file.md"  # nosec B108
                mock_rglob.return_value = [mock_file]

                result = sync.clone_to_gcs()

        assert result["status"] in ["success", "exists"]

    @patch("thoth.ingestion.gcs_repo_sync.storage")
    def test_sync_to_local(self, mock_storage):
        """Test syncing from GCS to local."""
        mock_bucket = MagicMock()
        mock_blob = MagicMock()
        mock_blob.name = "handbook/file.md"
        mock_bucket.list_blobs.return_value = [mock_blob]
        mock_storage.Client.return_value.bucket.return_value = mock_bucket

        # Use a real temp directory that gets cleaned up
        with tempfile.TemporaryDirectory() as tmpdir:
            sync = GCSRepoSync(
                "test-bucket",
                "https://gitlab.com/test/repo.git",
                "handbook",
                Path(tmpdir) / "test",
            )

            result = sync.sync_to_local()

            assert result["status"] == "success"
            assert "files_downloaded" in result

    @patch("thoth.ingestion.gcs_repo_sync.storage")
    def test_is_synced(self, mock_storage):
        """Test checking if local repository is synced."""
        mock_bucket = MagicMock()
        mock_storage.Client.return_value.bucket.return_value = mock_bucket

        sync = GCSRepoSync(
            "test-bucket",
            "https://gitlab.com/test/repo.git",
            "handbook",
            Path("/tmp/test"),  # nosec B108
        )

        # Test when directory exists and has completion marker
        with (
            patch.object(Path, "exists", return_value=True),
        ):
            # Mock the completion marker check
            sync.local_path = MagicMock()
            sync.local_path.exists.return_value = True
            marker = MagicMock()
            marker.exists.return_value = True
            sync.local_path.__truediv__ = MagicMock(return_value=marker)

            assert sync.is_synced() is True

    @patch("thoth.ingestion.gcs_repo_sync.storage")
    def test_is_synced_no_marker(self, mock_storage):
        """Test is_synced returns False when completion marker missing."""
        mock_bucket = MagicMock()
        mock_storage.Client.return_value.bucket.return_value = mock_bucket

        sync = GCSRepoSync(
            "test-bucket",
            "https://gitlab.com/test/repo.git",
            "handbook",
            Path("/tmp/test"),  # nosec B108
        )

        # Mock directory exists but no completion marker
        sync.local_path = MagicMock()
        sync.local_path.exists.return_value = True
        marker = MagicMock()
        marker.exists.return_value = False
        sync.local_path.__truediv__ = MagicMock(return_value=marker)

        assert sync.is_synced() is False

    @patch("thoth.ingestion.gcs_repo_sync.storage")
    def test_get_local_path(self, mock_storage):
        """Test getting local path."""
        mock_bucket = MagicMock()
        mock_storage.Client.return_value.bucket.return_value = mock_bucket

        sync = GCSRepoSync(
            "test-bucket",
            "https://gitlab.com/test/repo.git",
            "handbook",
            Path("/tmp/test"),  # nosec B108
        )

        assert sync.get_local_path() == Path("/tmp/test")  # nosec B108


class TestGCSRepoSyncErrorHandling:
    """Test error handling in GCSRepoSync."""

    @patch("thoth.ingestion.gcs_repo_sync.Repo")
    @patch("thoth.ingestion.gcs_repo_sync.storage")
    def test_clone_to_gcs_git_failure(self, mock_storage, mock_repo):
        """Test handling git clone failures."""
        mock_bucket = MagicMock()
        mock_bucket.list_blobs.return_value = []  # No existing files
        mock_storage.Client.return_value.bucket.return_value = mock_bucket

        # Make git clone fail
        mock_repo.clone_from.side_effect = GitCommandError("clone", "Git error")

        sync = GCSRepoSync(
            "test-bucket",
            "https://gitlab.com/test/repo.git",
            "handbook",
            Path("/tmp/test"),  # nosec B108
        )

        with pytest.raises(GitCommandError):
            sync.clone_to_gcs()

    @patch("thoth.ingestion.gcs_repo_sync.storage")
    def test_sync_init_gcs_failure(self, mock_storage):
        """Test handling GCS initialization failures."""
        mock_storage.Client.side_effect = Exception("GCS error")

        with pytest.raises(Exception, match="GCS error"):
            GCSRepoSync(
                "test-bucket",
                "https://gitlab.com/test/repo.git",
                "handbook",
                Path("/tmp/test"),  # nosec B108
            )
