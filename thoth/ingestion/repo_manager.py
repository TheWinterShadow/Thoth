"""Repository manager for cloning and tracking the GitLab handbook."""

import json
import logging
from pathlib import Path
import shutil
import time
from typing import Any

from git import GitCommandError, InvalidGitRepositoryError, Repo

# Constants
DEFAULT_REPO_URL = "https://gitlab.com/gitlab-com/content-sites/handbook.git"
DEFAULT_CLONE_PATH = Path.home() / ".thoth" / "handbook"
METADATA_FILE = "repo_metadata.json"

# Error messages as constants
MSG_REPO_EXISTS = "Repository already exists at {path}. Use force=True to re-clone."
MSG_CLONE_FAILED = "Failed to clone repository after {attempts} attempts"
MSG_UPDATE_FAILED = "Failed to update repository"
MSG_NO_REPO = "No repository found at {path}. Clone the repository first."
MSG_METADATA_SAVE_FAILED = "Failed to save metadata"
MSG_METADATA_LOAD_FAILED = "Failed to load metadata"
MSG_DIFF_FAILED = "Failed to get changed files"


class HandbookRepoManager:
    """Manages the GitLab handbook repository."""

    def __init__(
        self,
        repo_url: str = DEFAULT_REPO_URL,
        clone_path: Path | None = None,
        logger: logging.Logger | None = None,
    ):
        """Initialize the repository manager.

        Args:
            repo_url: URL of the GitLab handbook repository
            clone_path: Local path to clone/store the repository
            logger: Logger instance for logging messages
        """
        self.repo_url = repo_url
        self.clone_path = clone_path or DEFAULT_CLONE_PATH
        self.metadata_path = self.clone_path.parent / METADATA_FILE
        self.logger = logger or logging.getLogger(__name__)

    def is_valid_repo(self) -> bool:
        """Check if clone_path contains a valid git repository.

        Returns:
            True if valid repo exists, False otherwise
        """
        if not self.clone_path.exists():
            return False
        try:
            repo = Repo(str(self.clone_path))
            # Try to access head to verify it's a valid initialized repo
            _ = repo.head
            return True
        except (InvalidGitRepositoryError, ValueError):
            return False

    def clone_handbook(
        self,
        force: bool = False,
        max_retries: int = 3,
        retry_delay: int = 5,
    ) -> Path:
        """Clone the GitLab handbook repository.

        Args:
            force: If True, remove existing repository and re-clone
            max_retries: Maximum number of clone attempts
            retry_delay: Delay in seconds between retries

        Returns:
            Path to the cloned repository

        Raises:
            RuntimeError: If repository exists and force=False
            GitCommandError: If cloning fails after all retries
        """
        # Only raise error if a VALID repo exists and force=False
        if self.is_valid_repo() and not force:
            msg = MSG_REPO_EXISTS.format(path=self.clone_path)
            raise RuntimeError(msg)

        # Remove directory if it exists (whether valid repo or not)
        if self.clone_path.exists():
            self.logger.info("Removing existing directory at %s", self.clone_path)
            shutil.rmtree(self.clone_path)

        self.clone_path.parent.mkdir(parents=True, exist_ok=True)

        return self._clone_with_retry(max_retries, retry_delay)

    def _clone_with_retry(self, max_retries: int, retry_delay: int) -> Path:
        """Clone repository with retry logic.

        Args:
            max_retries: Maximum number of attempts
            retry_delay: Delay in seconds between attempts

        Returns:
            Path to cloned repository

        Raises:
            GitCommandError: If all attempts fail
        """
        last_error = None

        for attempt in range(1, max_retries + 1):
            try:
                self.logger.info("Cloning repository (attempt %d/%d)...", attempt, max_retries)
                Repo.clone_from(self.repo_url, str(self.clone_path))
                self.logger.info("Successfully cloned repository to %s", self.clone_path)
                return self.clone_path
            except GitCommandError as e:
                last_error = e
                self.logger.warning("Clone attempt %d/%d failed: %s", attempt, max_retries, e)
                if attempt < max_retries:
                    self.logger.info("Retrying in %d seconds...", retry_delay)
                    time.sleep(retry_delay)

        msg = MSG_CLONE_FAILED.format(attempts=max_retries)
        self.logger.exception("All clone attempts failed")
        raise GitCommandError(msg, 1) from last_error

    def update_repository(self) -> bool:
        """Update the repository by pulling latest changes.

        Returns:
            True if update successful, False otherwise

        Raises:
            RuntimeError: If repository doesn't exist
        """
        if not self.clone_path.exists():
            msg = MSG_NO_REPO.format(path=self.clone_path)
            raise RuntimeError(msg)

        try:
            repo = Repo(str(self.clone_path))
            self.logger.info("Pulling latest changes from %s", self.repo_url)
            origin = repo.remotes.origin
            origin.pull()
            self.logger.info("Successfully updated repository")
            return True
        except (GitCommandError, InvalidGitRepositoryError):
            self.logger.exception(MSG_UPDATE_FAILED)
            return False

    def get_current_commit(self) -> str | None:
        """Get the current commit SHA of the repository.

        Returns:
            Commit SHA as string, or None if error occurs

        Raises:
            RuntimeError: If repository doesn't exist
        """
        if not self.clone_path.exists():
            msg = MSG_NO_REPO.format(path=self.clone_path)
            raise RuntimeError(msg)

        try:
            repo = Repo(str(self.clone_path))
            commit_sha = repo.head.commit.hexsha
            self.logger.info("Current commit: %s", commit_sha)
            return commit_sha
        except (GitCommandError, InvalidGitRepositoryError):
            self.logger.exception("Failed to get current commit")
            return None

    def save_metadata(self, commit_sha: str) -> bool:
        """Save repository metadata to a JSON file.

        Args:
            commit_sha: Current commit SHA to save

        Returns:
            True if save successful, False otherwise
        """
        metadata = {
            "commit_sha": commit_sha,
            "clone_path": str(self.clone_path),
            "repo_url": self.repo_url,
        }

        try:
            self.metadata_path.parent.mkdir(parents=True, exist_ok=True)
            with self.metadata_path.open("w") as f:
                json.dump(metadata, f, indent=2)
            self.logger.info("Saved metadata to %s", self.metadata_path)
            return True
        except (OSError, TypeError):
            self.logger.exception(MSG_METADATA_SAVE_FAILED)
            return False

    def load_metadata(self) -> dict[str, Any] | None:
        """Load repository metadata from JSON file.

        Returns:
            Metadata dictionary with commit_sha, clone_path, repo_url, or None if error
        """
        if not self.metadata_path.exists():
            self.logger.warning("Metadata file not found at %s", self.metadata_path)
            return None

        try:
            with self.metadata_path.open() as f:
                metadata: dict[str, Any] = json.load(f)
            self.logger.info("Loaded metadata from %s", self.metadata_path)
            return metadata
        except (OSError, json.JSONDecodeError):
            self.logger.exception(MSG_METADATA_LOAD_FAILED)
            return None

    def get_changed_files(self, since_commit: str) -> list[str] | None:
        """Get list of files changed since a specific commit.

        Args:
            since_commit: Commit SHA to compare against

        Returns:
            List of changed file paths, or None if error occurs

        Raises:
            RuntimeError: If repository doesn't exist
        """
        if not self.clone_path.exists():
            msg = MSG_NO_REPO.format(path=self.clone_path)
            raise RuntimeError(msg)

        try:
            repo = Repo(str(self.clone_path))
            diff_output = repo.git.diff("--name-only", since_commit, "HEAD")

            if not diff_output:
                self.logger.info("No files changed since commit %s", since_commit)
                return []

            changed_files: list[str] = diff_output.strip().split("\n")
            self.logger.info(
                "Found %d changed files since commit %s",
                len(changed_files),
                since_commit,
            )
            return changed_files
        except (GitCommandError, InvalidGitRepositoryError):
            self.logger.exception(MSG_DIFF_FAILED)
            return None

    def get_file_changes(self, since_commit: str) -> dict[str, list[str]] | None:
        """Get categorized file changes since a specific commit.

        Args:
            since_commit: Commit SHA to compare against

        Returns:
            Dictionary with keys 'added', 'modified', 'deleted' containing
            lists of file paths, or None if error occurs

        Raises:
            RuntimeError: If repository doesn't exist
        """
        if not self.clone_path.exists():
            msg = MSG_NO_REPO.format(path=self.clone_path)
            raise RuntimeError(msg)

        try:
            repo = Repo(str(self.clone_path))

            # Get diff with status information
            diff_output = repo.git.diff("--name-status", since_commit, "HEAD")

            if not diff_output:
                self.logger.info("No files changed since commit %s", since_commit)
                return {"added": [], "modified": [], "deleted": []}

            # Parse the diff output
            added_files: list[str] = []
            modified_files: list[str] = []
            deleted_files: list[str] = []

            for line in diff_output.strip().split("\n"):
                if not line:
                    continue

                parts = line.split("\t", 1)
                if len(parts) != 2:
                    continue

                status = parts[0]
                file_path = parts[1]

                # Handle different status codes
                if status.startswith("A"):
                    added_files.append(file_path)
                elif status.startswith("M"):
                    modified_files.append(file_path)
                elif status.startswith("D"):
                    deleted_files.append(file_path)
                elif status.startswith(("R", "C")):  # Renamed or Copied
                    self._handle_rename_or_copy(status, file_path, deleted_files, added_files, modified_files)
                else:
                    # Unknown status, treat as modified
                    modified_files.append(file_path)

            self.logger.info(
                "Found %d added, %d modified, %d deleted files since commit %s",
                len(added_files),
                len(modified_files),
                len(deleted_files),
                since_commit,
            )

            return {
                "added": added_files,
                "modified": modified_files,
                "deleted": deleted_files,
            }
        except (GitCommandError, InvalidGitRepositoryError):
            self.logger.exception(MSG_DIFF_FAILED)
            return None

    def _handle_rename_or_copy(
        self,
        status: str,
        file_path: str,
        deleted_files: list[str],
        added_files: list[str],
        modified_files: list[str],
    ) -> None:
        """Handle renamed or copied files.

        Args:
            status: Git status code (R or C)
            file_path: File path(s) from git diff
            deleted_files: List to append deleted file paths
            added_files: List to append added file paths
            modified_files: List to append modified file paths (fallback)
        """
        if status.startswith("R"):  # Renamed
            # Renamed files have format: R<score>\toldpath\tnewpath
            # Treat as delete old + add new
            if "\t" in file_path:
                old_path, new_path = file_path.split("\t", 1)
                deleted_files.append(old_path)
                added_files.append(new_path)
            else:
                # Fallback: treat as modified
                modified_files.append(file_path)
        elif status.startswith("C"):  # Copied
            # Copied files have format: C<score>\tsourcepath\tnewpath
            # Treat as add new, keep source intact
            if "\t" in file_path:
                _source_path, new_path = file_path.split("\t", 1)
                added_files.append(new_path)
            else:
                # Fallback: treat as modified to avoid malformed added paths
                modified_files.append(file_path)
