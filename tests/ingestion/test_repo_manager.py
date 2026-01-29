"""Tests for the repository manager module."""

import json
import logging
from pathlib import Path
import unittest
from unittest.mock import MagicMock, mock_open, patch

from git import GitCommandError, InvalidGitRepositoryError

from thoth.ingestion.repo_manager import (
    DEFAULT_CLONE_PATH,
    DEFAULT_REPO_URL,
    HandbookRepoManager,
)


class TestHandbookRepoManager(unittest.TestCase):
    """Test cases for HandbookRepoManager class."""

    def setUp(self):
        """Set up test fixtures."""
        self.test_repo_url = "https://gitlab.com/test/repo.git"
        self.test_clone_path = Path("/tmp/test_handbook")
        self.manager = HandbookRepoManager(
            repo_url=self.test_repo_url,
            clone_path=self.test_clone_path,
            logger=logging.getLogger("test"),
        )

    def test_init_default_values(self):
        """Test initialization with default values."""
        manager = HandbookRepoManager()
        self.assertEqual(manager.repo_url, DEFAULT_REPO_URL)
        self.assertEqual(manager.clone_path, DEFAULT_CLONE_PATH)
        self.assertIsInstance(manager.logger, logging.Logger)

    def test_init_custom_values(self):
        """Test initialization with custom values."""
        self.assertEqual(self.manager.repo_url, self.test_repo_url)
        self.assertEqual(self.manager.clone_path, self.test_clone_path)

    @patch("thoth.ingestion.repo_manager.Repo")
    @patch("thoth.ingestion.repo_manager.shutil.rmtree")
    def test_clone_handbook_success(self, mock_rmtree, mock_repo_class):
        """Test successful repository cloning."""
        mock_repo = MagicMock()
        mock_repo_class.clone_from.return_value = mock_repo

        result = self.manager.clone_handbook()

        mock_repo_class.clone_from.assert_called_once_with(self.test_repo_url, str(self.test_clone_path))
        self.assertEqual(result, self.test_clone_path)
        mock_rmtree.assert_not_called()

    @patch("thoth.ingestion.repo_manager.Repo")
    @patch("thoth.ingestion.repo_manager.shutil.rmtree")
    @patch.object(Path, "exists")
    def test_clone_handbook_force_removes_existing(self, mock_exists, mock_rmtree, mock_repo_class):
        """Test force cloning removes existing repository."""
        mock_exists.return_value = True
        mock_repo = MagicMock()
        mock_repo_class.clone_from.return_value = mock_repo

        result = self.manager.clone_handbook(force=True)

        mock_rmtree.assert_called_once_with(self.test_clone_path)
        mock_repo_class.clone_from.assert_called_once()
        self.assertEqual(result, self.test_clone_path)

    @patch("thoth.ingestion.repo_manager.Repo")
    @patch.object(Path, "exists")
    def test_clone_handbook_raises_when_exists_no_force(self, mock_exists, mock_repo_class):
        """Test that cloning raises error when repository exists without force."""
        mock_exists.return_value = True
        # Mock Repo to indicate a valid repo exists at the path
        mock_repo = MagicMock()
        mock_repo.head = MagicMock()  # Make it look like a valid repo
        mock_repo_class.return_value = mock_repo

        with self.assertRaises(RuntimeError) as context:
            self.manager.clone_handbook(force=False)

        self.assertIn("already exists", str(context.exception))

    @patch("thoth.ingestion.repo_manager.Repo")
    @patch("thoth.ingestion.repo_manager.time.sleep")
    def test_clone_handbook_retry_success(self, mock_sleep, mock_repo_class):
        """Test cloning succeeds on retry."""
        mock_repo_class.clone_from.side_effect = [
            GitCommandError("clone", 1),
            MagicMock(),
        ]

        result = self.manager.clone_handbook(max_retries=2, retry_delay=1)

        self.assertEqual(mock_repo_class.clone_from.call_count, 2)
        mock_sleep.assert_called_once_with(1)
        self.assertEqual(result, self.test_clone_path)

    @patch("thoth.ingestion.repo_manager.Repo")
    @patch("thoth.ingestion.repo_manager.time.sleep")
    def test_clone_handbook_all_retries_fail(self, mock_sleep, mock_repo_class):
        """Test cloning fails after all retries."""
        mock_repo_class.clone_from.side_effect = GitCommandError("clone", 1)

        with self.assertRaises(GitCommandError):
            self.manager.clone_handbook(max_retries=3, retry_delay=1)

        self.assertEqual(mock_repo_class.clone_from.call_count, 3)
        self.assertEqual(mock_sleep.call_count, 2)

    @patch("thoth.ingestion.repo_manager.Repo")
    @patch.object(Path, "exists")
    def test_update_repository_success(self, mock_exists, mock_repo_class):
        """Test successful repository update."""
        mock_exists.return_value = True
        mock_repo = MagicMock()
        mock_origin = MagicMock()
        mock_repo.remotes.origin = mock_origin
        mock_repo_class.return_value = mock_repo

        result = self.manager.update_repository()

        self.assertTrue(result)
        mock_origin.pull.assert_called_once()

    @patch.object(Path, "exists")
    def test_update_repository_no_repo(self, mock_exists):
        """Test update fails when repository doesn't exist."""
        mock_exists.return_value = False

        with self.assertRaises(RuntimeError) as context:
            self.manager.update_repository()

        self.assertIn("No repository found", str(context.exception))

    @patch("thoth.ingestion.repo_manager.Repo")
    @patch.object(Path, "exists")
    def test_update_repository_git_error(self, mock_exists, mock_repo_class):
        """Test update handles Git errors gracefully."""
        mock_exists.return_value = True
        mock_repo_class.side_effect = GitCommandError("pull", 1)

        result = self.manager.update_repository()

        self.assertFalse(result)

    @patch("thoth.ingestion.repo_manager.Repo")
    @patch.object(Path, "exists")
    def test_update_repository_invalid_repo(self, mock_exists, mock_repo_class):
        """Test update handles invalid repository gracefully."""
        mock_exists.return_value = True
        mock_repo_class.side_effect = InvalidGitRepositoryError()

        result = self.manager.update_repository()

        self.assertFalse(result)

    @patch("thoth.ingestion.repo_manager.Repo")
    @patch.object(Path, "exists")
    def test_get_current_commit_success(self, mock_exists, mock_repo_class):
        """Test successfully getting current commit."""
        mock_exists.return_value = True
        mock_repo = MagicMock()
        mock_repo.head.commit.hexsha = "abc123def456"
        mock_repo_class.return_value = mock_repo

        commit_sha = self.manager.get_current_commit()

        self.assertEqual(commit_sha, "abc123def456")

    @patch.object(Path, "exists")
    def test_get_current_commit_no_repo(self, mock_exists):
        """Test getting commit fails when repository doesn't exist."""
        mock_exists.return_value = False

        with self.assertRaises(RuntimeError) as context:
            self.manager.get_current_commit()

        self.assertIn("No repository found", str(context.exception))

    @patch("thoth.ingestion.repo_manager.Repo")
    @patch.object(Path, "exists")
    def test_get_current_commit_git_error(self, mock_exists, mock_repo_class):
        """Test getting commit handles Git errors gracefully."""
        mock_exists.return_value = True
        mock_repo_class.side_effect = GitCommandError("log", 1)

        commit_sha = self.manager.get_current_commit()

        self.assertIsNone(commit_sha)

    @patch("thoth.ingestion.repo_manager.Repo")
    @patch.object(Path, "exists")
    def test_get_current_commit_invalid_repo(self, mock_exists, mock_repo_class):
        """Test getting commit handles invalid repository gracefully."""
        mock_exists.return_value = True
        mock_repo_class.side_effect = InvalidGitRepositoryError()

        commit_sha = self.manager.get_current_commit()

        self.assertIsNone(commit_sha)

    @patch.object(Path, "open", new_callable=mock_open)
    @patch.object(Path, "mkdir")
    def test_save_metadata_success(self, mock_mkdir, mock_file):
        """Test successfully saving metadata."""
        result = self.manager.save_metadata("abc123")

        self.assertTrue(result)
        mock_mkdir.assert_called_once_with(parents=True, exist_ok=True)
        mock_file.assert_called_once()

    @patch.object(Path, "open", new_callable=mock_open)
    @patch.object(Path, "mkdir")
    def test_save_metadata_writes_correct_data(self, mock_mkdir, mock_file):
        """Test metadata contains correct data."""
        self.manager.save_metadata("abc123")

        # Get the write calls
        handle = mock_file()
        written_data = "".join(call[0][0] for call in handle.write.call_args_list)
        metadata = json.loads(written_data)

        self.assertEqual(metadata["commit_sha"], "abc123")
        self.assertEqual(metadata["clone_path"], str(self.test_clone_path))
        self.assertEqual(metadata["repo_url"], self.test_repo_url)

    @patch.object(Path, "open", side_effect=OSError("Write failed"))
    @patch.object(Path, "mkdir")
    def test_save_metadata_handles_errors(self, mock_mkdir, mock_file):
        """Test save metadata handles errors gracefully."""
        result = self.manager.save_metadata("abc123")

        self.assertFalse(result)

    @patch.object(Path, "open", new_callable=mock_open, read_data='{"commit_sha": "abc123"}')
    @patch.object(Path, "exists")
    def test_load_metadata_success(self, mock_exists, mock_file):
        """Test successfully loading metadata."""
        mock_exists.return_value = True

        metadata = self.manager.load_metadata()

        self.assertIsNotNone(metadata)
        self.assertEqual(metadata["commit_sha"], "abc123")

    @patch.object(Path, "exists")
    def test_load_metadata_file_not_found(self, mock_exists):
        """Test loading metadata when file doesn't exist."""
        mock_exists.return_value = False

        metadata = self.manager.load_metadata()

        self.assertIsNone(metadata)

    @patch.object(Path, "open", side_effect=OSError("Read failed"))
    @patch.object(Path, "exists")
    def test_load_metadata_handles_errors(self, mock_exists, mock_file):
        """Test load metadata handles errors gracefully."""
        mock_exists.return_value = True

        metadata = self.manager.load_metadata()

        self.assertIsNone(metadata)

    @patch.object(Path, "open", new_callable=mock_open, read_data="invalid json")
    @patch.object(Path, "exists")
    def test_load_metadata_invalid_json(self, mock_exists, mock_file):
        """Test load metadata handles invalid JSON gracefully."""
        mock_exists.return_value = True

        metadata = self.manager.load_metadata()

        self.assertIsNone(metadata)

    @patch("thoth.ingestion.repo_manager.Repo")
    @patch.object(Path, "exists")
    def test_get_changed_files_success(self, mock_exists, mock_repo_class):
        """Test successfully getting changed files."""
        mock_exists.return_value = True
        mock_repo = MagicMock()
        mock_repo.git.diff.return_value = "file1.txt\nfile2.txt\nfile3.txt"
        mock_repo_class.return_value = mock_repo

        changed_files = self.manager.get_changed_files("old_commit_sha")

        self.assertEqual(len(changed_files), 3)
        self.assertIn("file1.txt", changed_files)
        self.assertIn("file2.txt", changed_files)
        self.assertIn("file3.txt", changed_files)
        mock_repo.git.diff.assert_called_once_with("--name-only", "old_commit_sha", "HEAD")

    @patch("thoth.ingestion.repo_manager.Repo")
    @patch.object(Path, "exists")
    def test_get_changed_files_no_changes(self, mock_exists, mock_repo_class):
        """Test getting changed files when no changes exist."""
        mock_exists.return_value = True
        mock_repo = MagicMock()
        mock_repo.git.diff.return_value = ""
        mock_repo_class.return_value = mock_repo

        changed_files = self.manager.get_changed_files("old_commit_sha")

        self.assertEqual(changed_files, [])

    @patch.object(Path, "exists")
    def test_get_changed_files_no_repo(self, mock_exists):
        """Test getting changed files fails when repository doesn't exist."""
        mock_exists.return_value = False

        with self.assertRaises(RuntimeError) as context:
            self.manager.get_changed_files("old_commit_sha")

        self.assertIn("No repository found", str(context.exception))

    @patch("thoth.ingestion.repo_manager.Repo")
    @patch.object(Path, "exists")
    def test_get_changed_files_git_error(self, mock_exists, mock_repo_class):
        """Test getting changed files handles Git errors gracefully."""
        mock_exists.return_value = True
        mock_repo_class.side_effect = GitCommandError("diff", 1)

        changed_files = self.manager.get_changed_files("old_commit_sha")

        self.assertIsNone(changed_files)

    @patch("thoth.ingestion.repo_manager.Repo")
    @patch.object(Path, "exists")
    def test_get_changed_files_invalid_repo(self, mock_exists, mock_repo_class):
        """Test getting changed files handles invalid repository gracefully."""
        mock_exists.return_value = True
        mock_repo_class.side_effect = InvalidGitRepositoryError()

        changed_files = self.manager.get_changed_files("old_commit_sha")

        self.assertIsNone(changed_files)


if __name__ == "__main__":
    unittest.main()
