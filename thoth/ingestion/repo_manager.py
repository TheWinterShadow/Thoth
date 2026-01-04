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
        if self.clone_path.exists() and not force:
            msg = MSG_REPO_EXISTS.format(path=self.clone_path)
            raise RuntimeError(msg)

        if force and self.clone_path.exists():
            self.logger.info("Removing existing repository at %s", self.clone_path)
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

                # Clean up any partially cloned repository before retrying
                if self.clone_path.exists():
                    try:
                        self.logger.info(
                            "Removing partially cloned repository at %s", self.clone_path
                        )
                        shutil.rmtree(self.clone_path)
                    except OSError as cleanup_error:
                        self.logger.warning(
                            "Failed to remove partially cloned repository at %s: %s",
                            self.clone_path,
                            cleanup_error,
                        )
                if attempt < max_retries:
                    self.logger.info("Retrying in %d seconds...", retry_delay)
                    time.sleep(retry_delay)

        msg = MSG_CLONE_FAILED.format(attempts=max_retries)
        self.logger.exception("All clone attempts failed: %s", msg)
        if last_error is not None:
            raise last_error
        raise RuntimeError(msg)

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
