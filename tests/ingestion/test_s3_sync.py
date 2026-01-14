"""Tests for S3 sync module."""

import pytest

from thoth.ingestion.s3_sync import S3Sync, S3SyncError


def test_s3_sync_init(s3_client, s3_bucket):
    """Test S3Sync initialization."""
    sync = S3Sync(bucket_name=s3_bucket)
    assert sync.bucket_name == s3_bucket


def test_s3_sync_init_bucket_not_found(s3_client):
    """Test S3Sync initialization with non-existent bucket."""
    with pytest.raises(S3SyncError, match="does not exist"):
        S3Sync(bucket_name="non-existent-bucket")


def test_upload_directory(s3_client, s3_bucket, tmp_path):
    """Test uploading a directory to S3."""
    # Create test files
    test_dir = tmp_path / "test_dir"
    test_dir.mkdir()
    (test_dir / "file1.txt").write_text("content1")
    (test_dir / "file2.txt").write_text("content2")
    (test_dir / "subdir").mkdir()
    (test_dir / "subdir" / "file3.txt").write_text("content3")

    sync = S3Sync(bucket_name=s3_bucket)
    count = sync.upload_directory(test_dir, s3_prefix="test")

    assert count == 3
    # Verify files in S3
    objects = s3_client.list_objects_v2(Bucket=s3_bucket, Prefix="test/")
    assert objects["KeyCount"] == 3


def test_download_directory(s3_client, s3_bucket, tmp_path):
    """Test downloading a directory from S3."""
    # Upload files first
    test_dir = tmp_path / "upload"
    test_dir.mkdir()
    (test_dir / "file1.txt").write_text("content1")

    sync = S3Sync(bucket_name=s3_bucket)
    sync.upload_directory(test_dir, s3_prefix="test")

    # Download to different location
    download_dir = tmp_path / "download"
    count = sync.download_directory("test", download_dir)

    assert count == 1
    assert (download_dir / "file1.txt").exists()
    assert (download_dir / "file1.txt").read_text() == "content1"


def test_backup_to_s3(s3_client, s3_bucket, tmp_path):
    """Test creating a backup in S3."""
    test_dir = tmp_path / "test"
    test_dir.mkdir()
    (test_dir / "file.txt").write_text("content")

    sync = S3Sync(bucket_name=s3_bucket)
    prefix = sync.backup_to_s3(test_dir, backup_name="test-backup")

    assert prefix.startswith("backups/test-backup")
    # Verify backup exists
    objects = s3_client.list_objects_v2(Bucket=s3_bucket, Prefix=prefix)
    assert objects["KeyCount"] > 0


def test_list_backups(s3_client, s3_bucket, tmp_path):
    """Test listing backups."""
    test_dir = tmp_path / "test"
    test_dir.mkdir()
    (test_dir / "file.txt").write_text("content")

    sync = S3Sync(bucket_name=s3_bucket)
    sync.backup_to_s3(test_dir, backup_name="backup1")
    sync.backup_to_s3(test_dir, backup_name="backup2")

    backups = sync.list_backups()
    assert "backup1" in backups
    assert "backup2" in backups
