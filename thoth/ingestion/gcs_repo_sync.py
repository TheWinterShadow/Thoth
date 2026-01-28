"""GCS-based repository synchronization for Cloud Run.

This module handles syncing the GitLab handbook between GCS and local storage:
1. Clone repository to GCS (once, or on updates)
2. Sync from GCS to local /tmp on Cloud Run startup
"""

import logging
from pathlib import Path
import shutil
import tempfile
from typing import Any

from git import Repo
from google.cloud import storage  # type: ignore[attr-defined]

logger = logging.getLogger(__name__)


class GCSRepoSync:
    """Manages repository synchronization between GCS and local storage."""

    def __init__(
        self,
        bucket_name: str,
        repo_url: str,
        gcs_prefix: str = "handbook",
        local_path: Path | None = None,
    ):
        """Initialize GCS repository sync.

        Args:
            bucket_name: GCS bucket name
            repo_url: Git repository URL
            gcs_prefix: Prefix/folder in GCS bucket for repository files
            local_path: Local path to sync to (defaults to /tmp/handbook)
        """
        self.bucket_name = bucket_name
        self.repo_url = repo_url
        self.gcs_prefix = gcs_prefix.strip("/")
        self.local_path = local_path or Path("/tmp/handbook")  # nosec B108 - Cloud Run requires /tmp
        self.storage_client = storage.Client()
        self.bucket = self.storage_client.bucket(bucket_name)

    def clone_to_gcs(self, force: bool = False) -> dict[str, Any]:
        """Clone repository and upload to GCS.

        This should be run once initially, or when you want to refresh
        the repository in GCS.

        Args:
            force: If True, re-clone even if files exist in GCS

        Returns:
            Dictionary with stats about the clone operation
        """
        logger.info("Cloning repository to GCS: %s", self.repo_url)

        # Check if already exists in GCS
        if not force:
            blobs = list(self.bucket.list_blobs(prefix=f"{self.gcs_prefix}/", max_results=1))
            if blobs:
                logger.info("Repository already exists in GCS. Use force=True to re-clone.")
                return {
                    "status": "exists",
                    "message": "Repository already in GCS",
                }

        # Clone to temporary directory
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir) / "repo"
            logger.info("Cloning to temporary directory: %s", tmp_path)
            Repo.clone_from(self.repo_url, str(tmp_path))

            # Upload all files to GCS
            logger.info("Uploading repository to GCS bucket: %s/%s", self.bucket_name, self.gcs_prefix)
            uploaded = 0

            for file_path in tmp_path.rglob("*"):
                if file_path.is_file() and ".git" not in str(file_path):
                    relative_path = file_path.relative_to(tmp_path)
                    blob_name = f"{self.gcs_prefix}/{relative_path}"

                    blob = self.bucket.blob(blob_name)
                    blob.upload_from_filename(str(file_path))
                    uploaded += 1

                    if uploaded % 100 == 0:
                        logger.info("Uploaded %d files...", uploaded)

            logger.info("Successfully uploaded %d files to GCS", uploaded)

            return {
                "status": "success",
                "files_uploaded": uploaded,
                "gcs_path": f"gs://{self.bucket_name}/{self.gcs_prefix}",
            }

    def sync_to_local(self, force: bool = False) -> dict[str, Any]:
        """Sync repository from GCS to local storage.

        This is called on Cloud Run startup to get the latest repository files.

        Args:
            force: If True, delete and re-download even if local files exist

        Returns:
            Dictionary with stats about the sync operation
        """
        # Check if already synced (has markdown files, not just directory exists)
        if not force and self.is_synced():
            logger.info("Local repository already synced at %s", self.local_path)
            file_count = sum(1 for _ in self.local_path.rglob("*.md"))
            return {
                "status": "exists",
                "local_path": str(self.local_path),
                "file_count": file_count,
            }

        # Clean up if forcing re-download
        if self.local_path.exists() and force:
            logger.info("Removing existing local repository: %s", self.local_path)
            shutil.rmtree(self.local_path)

        # Create local directory
        self.local_path.mkdir(parents=True, exist_ok=True)
        logger.info("Syncing repository from GCS to %s", self.local_path)

        # Download all blobs
        downloaded = 0
        blobs = self.bucket.list_blobs(prefix=f"{self.gcs_prefix}/")

        for blob in blobs:
            # Skip directory markers
            if blob.name.endswith("/"):
                continue

            # Calculate local file path
            # Remove prefix + "/"
            relative_path = blob.name[len(self.gcs_prefix) + 1 :]
            local_file = self.local_path / relative_path

            # Create parent directories
            local_file.parent.mkdir(parents=True, exist_ok=True)

            # Download file
            blob.download_to_filename(str(local_file))
            downloaded += 1

            if downloaded % 100 == 0:
                logger.info("Downloaded %d files...", downloaded)

        logger.info("Successfully synced %d files from GCS to local", downloaded)

        # Create completion marker to signal sync is done
        completion_marker = self.local_path / ".sync_complete"
        completion_marker.touch()
        logger.info("Created sync completion marker at %s", completion_marker)

        return {
            "status": "success",
            "files_downloaded": downloaded,
            "local_path": str(self.local_path),
        }

    def get_local_path(self) -> Path:
        """Get the local path where repository is synced.

        Returns:
            Path to local repository
        """
        return self.local_path

    def is_synced(self) -> bool:
        """Check if repository is synced locally.

        Returns:
            True if local repository exists and sync is complete
        """
        if not self.local_path.exists():
            return False

        # Check for sync completion marker (created after successful sync)
        completion_marker = self.local_path / ".sync_complete"
        return completion_marker.exists()
