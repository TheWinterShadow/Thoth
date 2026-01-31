"""Google Cloud Storage sync module for vector database persistence.

This module provides functionality to sync ChromaDB vector database
to/from Google Cloud Storage for persistence and disaster recovery.
"""

from datetime import datetime, timezone
import logging
import os
from pathlib import Path
import shutil

from thoth.shared.utils.logger import setup_logger

logger = setup_logger(__name__)

try:
    from google.cloud import storage  # type: ignore[attr-defined]
    from google.cloud.exceptions import GoogleCloudError

    GCS_AVAILABLE = True
except ImportError:
    GCS_AVAILABLE = False
    logger.warning("google-cloud-storage not installed. GCS sync will not be available.")


class GCSSyncError(Exception):
    """Raised when GCS sync operations fail."""


class GCSSync:
    """Manages synchronization of ChromaDB data with Google Cloud Storage.

    This class handles uploading and downloading ChromaDB persistence
    directories to/from GCS buckets for backup and restore operations.
    """

    def __init__(
        self,
        bucket_name: str,
        project_id: str | None = None,
        credentials_path: str | None = None,
        logger_instance: logging.Logger | logging.LoggerAdapter | None = None,
    ):
        """Initialize GCS sync manager.

        Args:
            bucket_name: Name of the GCS bucket for storage
            project_id: Optional GCP project ID (defaults to environment)
            credentials_path: Optional path to service account JSON key file
                If not provided, uses Application Default Credentials
            logger_instance: Optional logger instance to use.

        Raises:
            GCSSyncError: If google-cloud-storage is not installed
        """
        self.logger = logger_instance or logger
        if not GCS_AVAILABLE:
            msg = "google-cloud-storage package is not installed. Install with: pip install google-cloud-storage"
            raise GCSSyncError(msg)

        self.bucket_name = bucket_name
        self.project_id = project_id

        # Set credentials if provided
        if credentials_path:
            os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = credentials_path

        try:
            # Initialize storage client
            self.client = storage.Client(project=project_id)
            self.bucket = self.client.bucket(bucket_name)

            # Verify bucket exists
            if not self.bucket.exists():
                msg = f"Bucket '{bucket_name}' does not exist"
                raise GCSSyncError(msg)

            self.logger.info(f"Initialized GCS sync with bucket: {bucket_name}")
        except GoogleCloudError as e:
            msg = f"Failed to initialize GCS client: {e}"
            raise GCSSyncError(msg) from e

    def upload_directory(
        self,
        local_path: str | Path,
        gcs_prefix: str = "chroma_db",
        exclude_patterns: list[str] | None = None,
    ) -> int:
        """Upload a local directory to GCS.

        Args:
            local_path: Path to local directory to upload
            gcs_prefix: Prefix (folder path) in GCS bucket
            exclude_patterns: Optional list of filename patterns to exclude

        Returns:
            Number of files uploaded

        Raises:
            GCSSyncError: If upload fails
        """
        local_path = Path(local_path)

        if not local_path.exists():
            msg = f"Local path does not exist: {local_path}"
            raise GCSSyncError(msg)

        if not local_path.is_dir():
            msg = f"Local path is not a directory: {local_path}"
            raise GCSSyncError(msg)

        uploaded_count = 0

        try:
            self.logger.info(f"Starting upload from {local_path} to gs://{self.bucket_name}/{gcs_prefix}")

            # Walk through directory and upload each file
            for file_path in local_path.rglob("*"):
                if file_path.is_file():
                    # Check if file should be excluded
                    patterns = exclude_patterns if exclude_patterns is not None else []
                    should_exclude = any(pattern in str(file_path) for pattern in patterns)
                    if should_exclude:
                        self.logger.debug(f"Excluding file: {file_path}")
                        continue

                    # Calculate relative path for GCS
                    relative_path = file_path.relative_to(local_path)
                    blob_name = f"{gcs_prefix}/{relative_path}".replace("\\", "/")

                    # Upload file
                    blob = self.bucket.blob(blob_name)
                    blob.upload_from_filename(str(file_path))
                    uploaded_count += 1
                    self.logger.debug(f"Uploaded: {blob_name}")

            self.logger.info(f"Successfully uploaded {uploaded_count} files to GCS")
            return uploaded_count

        except GoogleCloudError as e:
            msg = f"Failed to upload directory: {e}"
            raise GCSSyncError(msg) from e

    def download_directory(
        self,
        gcs_prefix: str,
        local_path: str | Path,
        clean_local: bool = False,
    ) -> int:
        """Download a directory from GCS to local storage.

        Args:
            gcs_prefix: Prefix (folder path) in GCS bucket
            local_path: Path to local directory for download
            clean_local: If True, remove local directory before download

        Returns:
            Number of files downloaded

        Raises:
            GCSSyncError: If download fails
        """
        local_path = Path(local_path)

        # Clean local directory if requested
        if clean_local and local_path.exists():
            self.logger.info(f"Cleaning local directory: {local_path}")
            shutil.rmtree(local_path)

        # Create local directory
        local_path.mkdir(parents=True, exist_ok=True)

        downloaded_count = 0

        try:
            self.logger.info(f"Starting download from gs://{self.bucket_name}/{gcs_prefix} to {local_path}")

            # List all blobs with the prefix
            blobs = list(self.bucket.list_blobs(prefix=gcs_prefix))

            if not blobs:
                self.logger.warning(f"No files found with prefix: {gcs_prefix}")
                return 0

            # Download each blob
            for blob in blobs:
                # Skip directory markers (blobs ending with /)
                if blob.name.endswith("/"):
                    continue

                # Calculate local file path
                relative_path = blob.name[len(gcs_prefix) :].lstrip("/")
                file_path = local_path / relative_path

                # Create parent directories
                file_path.parent.mkdir(parents=True, exist_ok=True)

                # Download file
                blob.download_to_filename(str(file_path))
                downloaded_count += 1
                self.logger.debug(f"Downloaded: {blob.name}")

            self.logger.info(f"Successfully downloaded {downloaded_count} files from GCS")
            return downloaded_count

        except GoogleCloudError as e:
            msg = f"Failed to download directory: {e}"
            raise GCSSyncError(msg) from e

    def sync_to_gcs(
        self,
        local_path: str | Path,
        gcs_prefix: str = "chroma_db",
    ) -> dict[str, int | str]:
        """Sync local ChromaDB directory to GCS (upload).

        Args:
            local_path: Path to local ChromaDB directory
            gcs_prefix: Prefix in GCS bucket

        Returns:
            Dictionary with sync statistics

        Raises:
            GCSSyncError: If sync fails
        """
        self.logger.info(f"Syncing to GCS: {local_path} -> gs://{self.bucket_name}/{gcs_prefix}")

        uploaded = self.upload_directory(local_path, gcs_prefix)

        return {
            "uploaded_files": uploaded,
            "direction": "to_gcs",
            "bucket": self.bucket_name,
            "prefix": gcs_prefix,
        }

    def sync_from_gcs(
        self,
        gcs_prefix: str,
        local_path: str | Path,
        clean_local: bool = False,
    ) -> dict[str, int | str]:
        """Sync ChromaDB directory from GCS to local (download).

        Args:
            gcs_prefix: Prefix in GCS bucket
            local_path: Path to local ChromaDB directory
            clean_local: If True, remove local directory before sync

        Returns:
            Dictionary with sync statistics

        Raises:
            GCSSyncError: If sync fails
        """
        self.logger.info(f"Syncing from GCS: gs://{self.bucket_name}/{gcs_prefix} -> {local_path}")

        downloaded = self.download_directory(gcs_prefix, local_path, clean_local)

        return {
            "downloaded_files": downloaded,
            "direction": "from_gcs",
            "bucket": self.bucket_name,
            "prefix": gcs_prefix,
        }

    def backup_to_gcs(
        self,
        local_path: str | Path,
        backup_name: str | None = None,
    ) -> str:
        """Create a timestamped backup in GCS.

        Args:
            local_path: Path to local ChromaDB directory
            backup_name: Optional backup name (defaults to timestamp)

        Returns:
            GCS prefix of the backup

        Raises:
            GCSSyncError: If backup fails
        """
        if backup_name is None:
            timestamp = datetime.now(tz=timezone.utc).strftime("%Y%m%d_%H%M%S")
            backup_name = f"backup_{timestamp}"

        gcs_prefix = f"backups/{backup_name}"

        self.logger.info(f"Creating backup: {backup_name}")
        self.upload_directory(local_path, gcs_prefix)

        self.logger.info(f"Backup created at: gs://{self.bucket_name}/{gcs_prefix}")
        return gcs_prefix

    def restore_from_backup(
        self,
        backup_name: str,
        local_path: str | Path,
        clean_local: bool = True,
    ) -> int:
        """Restore ChromaDB from a GCS backup.

        Args:
            backup_name: Name of the backup to restore
            local_path: Path to local ChromaDB directory
            clean_local: If True, remove local directory before restore

        Returns:
            Number of files restored

        Raises:
            GCSSyncError: If restore fails
        """
        gcs_prefix = f"backups/{backup_name}"

        self.logger.info(f"Restoring backup: {backup_name}")
        result = self.sync_from_gcs(gcs_prefix, local_path, clean_local)

        self.logger.info(f"Restored {result['downloaded_files']} files from backup")
        downloaded = result["downloaded_files"]
        if isinstance(downloaded, int):
            return downloaded
        return 0

    def list_backups(self) -> list[str]:
        """List available backups in GCS.

        Returns:
            List of backup names

        Raises:
            GCSSyncError: If listing fails
        """
        try:
            blobs = self.bucket.list_blobs(prefix="backups/")

            # Extract unique backup names
            backup_names = set()
            for blob in blobs:
                # Extract backup name from path like "backups/backup_20240112_120000/..."
                parts = blob.name.split("/")
                if len(parts) >= 2 and parts[0] == "backups":
                    backup_names.add(parts[1])

            return sorted(backup_names)

        except GoogleCloudError as e:
            msg = f"Failed to list backups: {e}"
            raise GCSSyncError(msg) from e
