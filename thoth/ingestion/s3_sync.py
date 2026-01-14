"""Amazon S3 sync module for vector database persistence.

This module provides functionality to sync ChromaDB vector database
to/from Amazon S3 for persistence and disaster recovery.
"""

from datetime import datetime, timezone
import logging
from pathlib import Path
import shutil
from typing import Any

logger = logging.getLogger(__name__)

try:
    import boto3
    from botocore.exceptions import BotoCoreError, ClientError

    S3_AVAILABLE = True
except ImportError:
    S3_AVAILABLE = False
    logger.warning("boto3 not installed. S3 sync will not be available.")


class S3SyncError(Exception):
    """Raised when S3 sync operations fail."""


class S3Sync:
    """Manages synchronization of ChromaDB data with Amazon S3.

    This class handles uploading and downloading ChromaDB persistence
    directories to/from S3 buckets for backup and restore operations.
    """

    def __init__(
        self,
        bucket_name: str,
        region: str | None = None,
        aws_access_key_id: str | None = None,
        aws_secret_access_key: str | None = None,
    ):
        """Initialize S3 sync manager.

        Args:
            bucket_name: Name of the S3 bucket for storage
            region: Optional AWS region (defaults to us-east-1)
            aws_access_key_id: Optional AWS access key ID
                If not provided, uses IAM role or environment variables
            aws_secret_access_key: Optional AWS secret access key
                If not provided, uses IAM role or environment variables

        Raises:
            S3SyncError: If boto3 is not installed or bucket doesn't exist
        """
        if not S3_AVAILABLE:
            msg = "boto3 package is not installed. Install with: pip install boto3"
            raise S3SyncError(msg)

        self.bucket_name = bucket_name
        self.region = region or "us-east-1"

        try:
            # Initialize S3 client
            session = boto3.Session(
                aws_access_key_id=aws_access_key_id,
                aws_secret_access_key=aws_secret_access_key,
                region_name=self.region,
            )
            self.s3_client = session.client("s3")
            self.s3_resource = session.resource("s3")
            self.bucket = self.s3_resource.Bucket(bucket_name)

            # Verify bucket exists
            try:
                self.s3_client.head_bucket(Bucket=bucket_name)
            except ClientError as e:
                error_code = e.response.get("Error", {}).get("Code", "")
                if error_code == "404":
                    msg = f"Bucket '{bucket_name}' does not exist"
                    raise S3SyncError(msg) from e
                raise

            logger.info(f"Initialized S3 sync with bucket: {bucket_name}")
        except (ClientError, BotoCoreError) as e:
            msg = f"Failed to initialize S3 client: {e}"
            raise S3SyncError(msg) from e

    def upload_directory(
        self,
        local_path: str | Path,
        s3_prefix: str = "chroma_db",
        exclude_patterns: list[str] | None = None,
    ) -> int:
        """Upload a local directory to S3.

        Args:
            local_path: Path to local directory to upload
            s3_prefix: Prefix (folder path) in S3 bucket
            exclude_patterns: Optional list of filename patterns to exclude

        Returns:
            Number of files uploaded

        Raises:
            S3SyncError: If upload fails
        """
        local_path = Path(local_path)

        if not local_path.exists():
            msg = f"Local path does not exist: {local_path}"
            raise S3SyncError(msg)

        if not local_path.is_dir():
            msg = f"Local path is not a directory: {local_path}"
            raise S3SyncError(msg)

        uploaded_count = 0

        try:
            logger.info(f"Starting upload from {local_path} to s3://{self.bucket_name}/{s3_prefix}")

            # Walk through directory and upload each file
            for file_path in local_path.rglob("*"):
                if file_path.is_file():
                    # Check if file should be excluded
                    patterns = exclude_patterns if exclude_patterns is not None else []
                    should_exclude = any(pattern in str(file_path) for pattern in patterns)
                    if should_exclude:
                        logger.debug(f"Excluding file: {file_path}")
                        continue

                    # Calculate relative path for S3
                    relative_path = file_path.relative_to(local_path)
                    s3_key = f"{s3_prefix}/{relative_path}".replace("\\", "/")

                    # Upload file
                    self.s3_client.upload_file(str(file_path), self.bucket_name, s3_key)
                    uploaded_count += 1
                    logger.debug(f"Uploaded: {s3_key}")

            logger.info(f"Successfully uploaded {uploaded_count} files to S3")
            return uploaded_count

        except (ClientError, BotoCoreError) as e:
            msg = f"Failed to upload directory: {e}"
            raise S3SyncError(msg) from e

    def download_directory(
        self,
        s3_prefix: str,
        local_path: str | Path,
        clean_local: bool = False,
    ) -> int:
        """Download a directory from S3 to local storage.

        Args:
            s3_prefix: Prefix (folder path) in S3 bucket
            local_path: Path to local directory for download
            clean_local: If True, remove local directory before download

        Returns:
            Number of files downloaded

        Raises:
            S3SyncError: If download fails
        """
        local_path = Path(local_path)

        # Clean local directory if requested
        if clean_local and local_path.exists():
            logger.info(f"Cleaning local directory: {local_path}")
            shutil.rmtree(local_path)

        # Create local directory
        local_path.mkdir(parents=True, exist_ok=True)

        downloaded_count = 0

        try:
            logger.info(f"Starting download from s3://{self.bucket_name}/{s3_prefix} to {local_path}")

            # List all objects with the prefix
            paginator = self.s3_client.get_paginator("list_objects_v2")
            pages = paginator.paginate(Bucket=self.bucket_name, Prefix=s3_prefix)

            for page in pages:
                if "Contents" not in page:
                    logger.warning(f"No files found with prefix: {s3_prefix}")
                    return 0

                # Download each object
                for obj in page["Contents"]:
                    s3_key = obj["Key"]

                    # Skip directory markers (keys ending with /)
                    if s3_key.endswith("/"):
                        continue

                    # Calculate local file path
                    relative_path = s3_key[len(s3_prefix) :].lstrip("/")
                    file_path = local_path / relative_path

                    # Create parent directories
                    file_path.parent.mkdir(parents=True, exist_ok=True)

                    # Download file
                    self.s3_client.download_file(self.bucket_name, s3_key, str(file_path))
                    downloaded_count += 1
                    logger.debug(f"Downloaded: {s3_key}")

            logger.info(f"Successfully downloaded {downloaded_count} files from S3")
            return downloaded_count

        except (ClientError, BotoCoreError) as e:
            msg = f"Failed to download directory: {e}"
            raise S3SyncError(msg) from e

    def sync_to_s3(
        self,
        local_path: str | Path,
        s3_prefix: str = "chroma_db",
    ) -> dict[str, Any]:
        """Sync local ChromaDB directory to S3 (upload).

        Args:
            local_path: Path to local ChromaDB directory
            s3_prefix: Prefix in S3 bucket

        Returns:
            Dictionary with sync statistics

        Raises:
            S3SyncError: If sync fails
        """
        logger.info(f"Syncing to S3: {local_path} -> s3://{self.bucket_name}/{s3_prefix}")

        uploaded = self.upload_directory(local_path, s3_prefix)

        return {
            "uploaded_files": uploaded,
            "direction": "to_s3",
            "bucket": self.bucket_name,
            "prefix": s3_prefix,
        }

    def sync_from_s3(
        self,
        s3_prefix: str,
        local_path: str | Path,
        clean_local: bool = False,
    ) -> dict[str, Any]:
        """Sync ChromaDB directory from S3 to local (download).

        Args:
            s3_prefix: Prefix in S3 bucket
            local_path: Path to local ChromaDB directory
            clean_local: If True, remove local directory before sync

        Returns:
            Dictionary with sync statistics

        Raises:
            S3SyncError: If sync fails
        """
        logger.info(f"Syncing from S3: s3://{self.bucket_name}/{s3_prefix} -> {local_path}")

        downloaded = self.download_directory(s3_prefix, local_path, clean_local)

        return {
            "downloaded_files": downloaded,
            "direction": "from_s3",
            "bucket": self.bucket_name,
            "prefix": s3_prefix,
        }

    def backup_to_s3(
        self,
        local_path: str | Path,
        backup_name: str | None = None,
    ) -> str:
        """Create a timestamped backup in S3.

        Args:
            local_path: Path to local ChromaDB directory
            backup_name: Optional backup name (defaults to timestamp)

        Returns:
            S3 prefix of the backup

        Raises:
            S3SyncError: If backup fails
        """
        if backup_name is None:
            timestamp = datetime.now(tz=timezone.utc).strftime("%Y%m%d_%H%M%S")
            backup_name = f"backup_{timestamp}"

        s3_prefix = f"backups/{backup_name}"

        logger.info(f"Creating backup: {backup_name}")
        self.upload_directory(local_path, s3_prefix)

        logger.info(f"Backup created at: s3://{self.bucket_name}/{s3_prefix}")
        return s3_prefix

    def restore_from_backup(
        self,
        backup_name: str,
        local_path: str | Path,
        clean_local: bool = True,
    ) -> int:
        """Restore ChromaDB from an S3 backup.

        Args:
            backup_name: Name of the backup to restore
            local_path: Path to local ChromaDB directory
            clean_local: If True, remove local directory before restore

        Returns:
            Number of files restored

        Raises:
            S3SyncError: If restore fails
        """
        s3_prefix = f"backups/{backup_name}"

        logger.info(f"Restoring backup: {backup_name}")
        result = self.sync_from_s3(s3_prefix, local_path, clean_local)

        logger.info(f"Restored {result['downloaded_files']} files from backup")
        downloaded = result["downloaded_files"]
        if isinstance(downloaded, int):
            return downloaded
        return 0

    def list_backups(self) -> list[str]:
        """List available backups in S3.

        Returns:
            List of backup names

        Raises:
            S3SyncError: If listing fails
        """
        try:
            paginator = self.s3_client.get_paginator("list_objects_v2")
            pages = paginator.paginate(Bucket=self.bucket_name, Prefix="backups/", Delimiter="/")

            # Extract unique backup names
            backup_names = set()
            for page in pages:
                if "CommonPrefixes" in page:
                    for prefix in page["CommonPrefixes"]:
                        # Extract backup name from path like "backups/backup_20240112_120000/"
                        parts = prefix["Prefix"].rstrip("/").split("/")
                        if len(parts) >= 2 and parts[0] == "backups":
                            backup_names.add(parts[1])

            return sorted(backup_names)

        except (ClientError, BotoCoreError) as e:
            msg = f"Failed to list backups: {e}"
            raise S3SyncError(msg) from e
