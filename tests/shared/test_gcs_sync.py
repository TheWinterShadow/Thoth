"""Tests for GCS sync module."""

from pathlib import Path
import tempfile
from unittest.mock import Mock, patch

import pytest

from thoth.shared.gcs_sync import GCSSync, GCSSyncError


@pytest.fixture
def mock_storage_client():
    """Mock Google Cloud Storage client."""
    with patch("thoth.shared.gcs_sync.storage") as mock_storage:
        mock_client = Mock()
        mock_bucket = Mock()
        mock_bucket.exists.return_value = True
        mock_client.bucket.return_value = mock_bucket
        mock_storage.Client.return_value = mock_client
        yield mock_storage, mock_client, mock_bucket


@pytest.fixture
def temp_directory():
    """Create a temporary directory with test files."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir_path = Path(tmpdir)

        # Create test files
        (tmpdir_path / "test1.txt").write_text("content1")
        (tmpdir_path / "test2.txt").write_text("content2")

        # Create subdirectory
        subdir = tmpdir_path / "subdir"
        subdir.mkdir()
        (subdir / "test3.txt").write_text("content3")

        yield tmpdir_path


class TestGCSSync:
    """Test cases for GCSSync class."""

    def test_init_success(self, mock_storage_client):
        """Test successful initialization."""
        mock_storage, _mock_client, mock_bucket = mock_storage_client

        gcs_sync = GCSSync(bucket_name="test-bucket")

        assert gcs_sync.bucket_name == "test-bucket"
        mock_storage.Client.assert_called_once()
        mock_bucket.exists.assert_called_once()

    def test_init_bucket_not_exists(self, mock_storage_client):
        """Test initialization fails when bucket doesn't exist."""
        _mock_storage, _mock_client, mock_bucket = mock_storage_client
        mock_bucket.exists.return_value = False

        with pytest.raises(GCSSyncError, match="does not exist"):
            GCSSync(bucket_name="nonexistent-bucket")

    def test_init_without_gcs_available(self):
        """Test initialization fails when google-cloud-storage not installed."""
        with (
            patch("thoth.shared.gcs_sync.GCS_AVAILABLE", False),
            pytest.raises(GCSSyncError, match="not installed"),
        ):
            GCSSync(bucket_name="test-bucket")

    def test_upload_directory_success(self, mock_storage_client, temp_directory):
        """Test successful directory upload."""
        _mock_storage, _mock_client, mock_bucket = mock_storage_client
        mock_blob = Mock()
        mock_bucket.blob.return_value = mock_blob

        gcs_sync = GCSSync(bucket_name="test-bucket")
        count = gcs_sync.upload_directory(temp_directory, "test_prefix")

        assert count == 3  # 3 files created in fixture
        assert mock_blob.upload_from_filename.call_count == 3

    def test_upload_directory_not_exists(self, mock_storage_client):
        """Test upload fails when directory doesn't exist."""
        gcs_sync = GCSSync(bucket_name="test-bucket")

        with pytest.raises(GCSSyncError, match="does not exist"):
            gcs_sync.upload_directory("/nonexistent/path")

    def test_upload_directory_not_directory(self, mock_storage_client, temp_directory):
        """Test upload fails when path is not a directory."""
        gcs_sync = GCSSync(bucket_name="test-bucket")
        file_path = temp_directory / "test1.txt"

        with pytest.raises(GCSSyncError, match="not a directory"):
            gcs_sync.upload_directory(file_path)

    def test_upload_directory_with_exclusions(self, mock_storage_client, temp_directory):
        """Test directory upload with file exclusions."""
        _mock_storage, _mock_client, mock_bucket = mock_storage_client

        mock_blob = Mock()
        mock_bucket.blob.return_value = mock_blob

        gcs_sync = GCSSync(bucket_name="test-bucket")
        count = gcs_sync.upload_directory(temp_directory, "test_prefix", exclude_patterns=["test2.txt"])

        # Should only upload 2 files (excluding test2.txt)
        assert count == 2

    def test_download_directory_success(self, mock_storage_client):
        """Test successful directory download."""
        _mock_storage, _mock_client, mock_bucket = mock_storage_client

        # Mock blob listing
        mock_blob1 = Mock()
        mock_blob1.name = "test_prefix/file1.txt"
        mock_blob2 = Mock()
        mock_blob2.name = "test_prefix/subdir/file2.txt"

        mock_bucket.list_blobs.return_value = [mock_blob1, mock_blob2]

        with tempfile.TemporaryDirectory() as tmpdir:
            gcs_sync = GCSSync(bucket_name="test-bucket")
            count = gcs_sync.download_directory("test_prefix", tmpdir)

            assert count == 2
            assert mock_blob1.download_to_filename.called
            assert mock_blob2.download_to_filename.called

    def test_download_directory_clean_local(self, mock_storage_client, temp_directory):
        """Test directory download with local cleanup."""
        _mock_storage, _mock_client, mock_bucket = mock_storage_client
        mock_bucket.list_blobs.return_value = []

        # Verify directory exists before
        assert temp_directory.exists()

        gcs_sync = GCSSync(bucket_name="test-bucket")
        gcs_sync.download_directory("test_prefix", temp_directory, clean_local=True)

        # Directory should exist after (recreated)
        assert temp_directory.exists()

    def test_download_directory_no_files(self, mock_storage_client):
        """Test download when no files found with prefix."""
        _mock_storage, _mock_client, mock_bucket = mock_storage_client
        mock_bucket.list_blobs.return_value = []

        with tempfile.TemporaryDirectory() as tmpdir:
            gcs_sync = GCSSync(bucket_name="test-bucket")
            count = gcs_sync.download_directory("empty_prefix", tmpdir)

            assert count == 0

    def test_sync_to_gcs(self, mock_storage_client, temp_directory):
        """Test sync to GCS."""
        _mock_storage, _mock_client, mock_bucket = mock_storage_client
        mock_blob = Mock()
        mock_bucket.blob.return_value = mock_blob

        gcs_sync = GCSSync(bucket_name="test-bucket")
        result = gcs_sync.sync_to_gcs(temp_directory, "sync_prefix")

        assert result["direction"] == "to_gcs"
        assert result["uploaded_files"] == 3
        assert result["bucket"] == "test-bucket"
        assert result["prefix"] == "sync_prefix"

    def test_sync_from_gcs(self, mock_storage_client):
        """Test sync from GCS."""
        _mock_storage, _mock_client, mock_bucket = mock_storage_client
        mock_bucket.list_blobs.return_value = []

        with tempfile.TemporaryDirectory() as tmpdir:
            gcs_sync = GCSSync(bucket_name="test-bucket")
            result = gcs_sync.sync_from_gcs("sync_prefix", tmpdir)

            assert result["direction"] == "from_gcs"
            assert result["bucket"] == "test-bucket"

    def test_backup_to_gcs(self, mock_storage_client, temp_directory):
        """Test creating a backup."""
        _mock_storage, _mock_client, mock_bucket = mock_storage_client
        mock_blob = Mock()
        mock_bucket.blob.return_value = mock_blob

        gcs_sync = GCSSync(bucket_name="test-bucket")
        prefix = gcs_sync.backup_to_gcs(temp_directory, "test_backup")

        assert prefix == "backups/test_backup"

    def test_backup_to_gcs_auto_name(self, mock_storage_client, temp_directory):
        """Test creating a backup with automatic naming."""
        _mock_storage, _mock_client, mock_bucket = mock_storage_client
        mock_blob = Mock()
        mock_bucket.blob.return_value = mock_blob

        gcs_sync = GCSSync(bucket_name="test-bucket")
        prefix = gcs_sync.backup_to_gcs(temp_directory)

        # Should start with backups/backup_ and have timestamp
        assert prefix.startswith("backups/backup_")

    def test_restore_from_backup(self, mock_storage_client):
        """Test restoring from backup."""
        _mock_storage, _mock_client, mock_bucket = mock_storage_client
        mock_bucket.list_blobs.return_value = []

        with tempfile.TemporaryDirectory() as tmpdir:
            gcs_sync = GCSSync(bucket_name="test-bucket")
            count = gcs_sync.restore_from_backup("test_backup", tmpdir)

            assert count == 0  # No files in mock

    def test_list_backups(self, mock_storage_client):
        """Test listing available backups."""
        _mock_storage, _mock_client, mock_bucket = mock_storage_client

        # Mock backup blobs
        mock_blob1 = Mock()
        mock_blob1.name = "backups/backup_20240101_120000/file1.txt"
        mock_blob2 = Mock()
        mock_blob2.name = "backups/backup_20240102_120000/file2.txt"
        mock_blob3 = Mock()
        mock_blob3.name = "backups/backup_20240101_120000/file3.txt"

        mock_bucket.list_blobs.return_value = [mock_blob1, mock_blob2, mock_blob3]

        gcs_sync = GCSSync(bucket_name="test-bucket")
        backups = gcs_sync.list_backups()

        assert len(backups) == 2
        assert "backup_20240101_120000" in backups
        assert "backup_20240102_120000" in backups
