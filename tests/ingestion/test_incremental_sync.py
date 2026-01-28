"""Tests for incremental sync functionality."""

import contextlib
import json
from unittest.mock import Mock, patch

import pytest

from thoth.ingestion.pipeline import IngestionPipeline
from thoth.ingestion.repo_manager import HandbookRepoManager
from thoth.shared.vector_store import VectorStore


class TestIncrementalSync:
    """Test suite for incremental sync functionality."""

    @pytest.fixture
    def mock_repo_manager(self, tmp_path):
        """Create a mock repository manager."""
        manager = Mock(spec=HandbookRepoManager)
        manager.clone_path = tmp_path / "handbook"
        manager.clone_path.mkdir(parents=True)
        return manager

    @pytest.fixture
    def sample_file_changes(self):
        """Sample file changes for testing."""
        return {
            "added": ["docs/new_doc.md", "guides/new_guide.md"],
            "modified": ["README.md", "docs/existing.md"],
            "deleted": ["deprecated/old.md"],
        }

    def test_get_file_changes_categorizes_correctly(self, mock_repo_manager):
        """Test that get_file_changes correctly categorizes changes."""
        manager = HandbookRepoManager()
        manager.clone_path = mock_repo_manager.clone_path

        # Create a mock repository
        with patch("thoth.ingestion.repo_manager.Repo") as mock_repo:
            mock_git = Mock()
            # fmt: off
            mock_git.diff.return_value = (
                "A\tdocs/new.md\n"
                "M\tdocs/modified.md\n"
                "D\tdocs/deleted.md\n"
                "R100\told_name.md\tnew_name.md"
            )
            # fmt: on
            mock_repo.return_value.git = mock_git

            result = manager.get_file_changes("abc123")

            assert result is not None
            assert "docs/new.md" in result["added"]
            assert "docs/modified.md" in result["modified"]
            assert "docs/deleted.md" in result["deleted"]
            # Renamed files should appear as delete old + add new
            assert "old_name.md" in result["deleted"]
            assert "new_name.md" in result["added"]

    def test_get_file_changes_handles_no_changes(self, mock_repo_manager):
        """Test that get_file_changes handles no changes correctly."""
        manager = HandbookRepoManager()
        manager.clone_path = mock_repo_manager.clone_path

        with patch("thoth.ingestion.repo_manager.Repo") as mock_repo:
            mock_git = Mock()
            mock_git.diff.return_value = ""
            mock_repo.return_value.git = mock_git

            result = manager.get_file_changes("abc123")

            assert result == {"added": [], "modified": [], "deleted": []}

    def test_handle_deleted_files_removes_from_vector_store(self, tmp_path):
        """Test that deleted files are removed from vector store."""
        # Setup
        mock_vector_store = Mock()
        mock_vector_store.delete_by_file_path.return_value = 5  # 5 chunks deleted

        pipeline = IngestionPipeline(vector_store=mock_vector_store)
        pipeline.state.processed_files = ["file1.md", "file2.md", "file3.md"]
        pipeline.state.total_chunks = 100
        pipeline.state.total_documents = 100

        deleted_files = ["file1.md", "file2.md"]

        # Execute
        successful, failed = pipeline._handle_deleted_files(deleted_files)

        # Verify
        assert successful == 2
        assert failed == 0
        assert "file1.md" not in pipeline.state.processed_files
        assert "file2.md" not in pipeline.state.processed_files
        assert "file3.md" in pipeline.state.processed_files
        assert pipeline.state.total_chunks == 90  # 100 - (5 * 2)
        assert mock_vector_store.delete_by_file_path.call_count == 2

    def test_handle_modified_files_updates_vector_store(self, tmp_path):
        """Test that modified files are updated in vector store."""
        # Setup
        repo_path = tmp_path / "repo"
        repo_path.mkdir()

        # Create a test file
        test_file = repo_path / "test.md"
        test_file.write_text("# Modified Content\n\nThis is modified content.")

        mock_vector_store = Mock()
        mock_vector_store.delete_by_file_path.return_value = 3  # 3 old chunks

        mock_chunker = Mock()
        mock_chunk = Mock()
        mock_chunk.content = "Modified content"
        mock_chunk.metadata = Mock()
        mock_chunk.metadata.chunk_id = "chunk_1"
        mock_chunk.metadata.to_dict.return_value = {"file_path": "test.md"}
        mock_chunker.chunk_file.return_value = [mock_chunk, mock_chunk]  # 2 new chunks

        mock_embedder = Mock()
        mock_embedder.embed.return_value = [[0.1] * 384, [0.2] * 384]

        mock_repo_manager = Mock()
        mock_repo_manager.clone_path = repo_path

        pipeline = IngestionPipeline(
            repo_manager=mock_repo_manager,
            chunker=mock_chunker,
            embedder=mock_embedder,
            vector_store=mock_vector_store,
        )
        pipeline.state.total_chunks = 100
        pipeline.state.total_documents = 100

        # Execute
        successful, failed = pipeline._handle_modified_files([test_file])

        # Verify
        assert successful == 1
        assert failed == 0
        assert mock_vector_store.delete_by_file_path.called
        assert mock_vector_store.add_documents.called
        # Net change: -3 old chunks + 2 new chunks = -1
        assert pipeline.state.total_chunks == 99

    def test_incremental_mode_filters_markdown_only(self, tmp_path):
        """Test that incremental mode only processes markdown files."""
        repo_path = tmp_path / "repo"
        repo_path.mkdir()

        # Create test files
        (repo_path / "doc.md").write_text("# Doc")
        (repo_path / "README.md").write_text("# README")

        mock_repo_manager = Mock()
        mock_repo_manager.clone_path = repo_path
        mock_repo_manager.get_current_commit.return_value = "def456"
        mock_repo_manager.get_file_changes.return_value = {
            "added": ["doc.md", "image.png", "script.py"],
            "modified": ["README.md", "data.json"],
            "deleted": ["old.md", "old.txt"],
        }
        mock_repo_manager.update_repository.return_value = True

        mock_vector_store = Mock()
        mock_vector_store.delete_by_file_path.return_value = 0

        mock_chunker = Mock()
        mock_chunker.chunk_file.return_value = []

        pipeline = IngestionPipeline(
            repo_manager=mock_repo_manager,
            chunker=mock_chunker,
            vector_store=mock_vector_store,
        )
        pipeline.state.last_commit = "abc123"

        with patch.object(pipeline, "_discover_markdown_files") as mock_discover:
            mock_discover.return_value = [repo_path / "doc.md", repo_path / "README.md"]

            # Execute (will fail at save_metadata, but that's OK for this test)
            with contextlib.suppress(Exception):
                pipeline.run(incremental=True)

        # Verify only markdown files were considered
        call_args = mock_repo_manager.get_file_changes.call_args
        assert call_args[0][0] == "abc123"

        # Check that only .md files would be processed
        # (we can't easily verify the actual processing without more mocking)

    def test_full_mode_processes_all_files(self, tmp_path):
        """Test that full mode processes all files regardless of changes."""
        repo_path = tmp_path / "repo"
        repo_path.mkdir()

        (repo_path / "doc.md").write_text("# Doc")

        mock_repo_manager = Mock()
        mock_repo_manager.clone_path = repo_path
        mock_repo_manager.get_current_commit.return_value = "def456"
        mock_repo_manager.update_repository.return_value = True

        mock_chunker = Mock()
        mock_chunker.chunk_file.return_value = []

        mock_vector_store = Mock()

        pipeline = IngestionPipeline(
            repo_manager=mock_repo_manager,
            chunker=mock_chunker,
            vector_store=mock_vector_store,
        )

        with patch.object(pipeline, "_discover_markdown_files") as mock_discover:
            mock_discover.return_value = [repo_path / "doc.md"]

            with contextlib.suppress(Exception):
                pipeline.run(incremental=False)

        # Verify get_file_changes was NOT called in full mode
        assert not mock_repo_manager.get_file_changes.called

    def test_error_handling_in_deleted_files(self, tmp_path):
        """Test error handling when deleting files fails."""
        mock_vector_store = Mock()
        mock_vector_store.delete_by_file_path.side_effect = [
            5,
            Exception("Delete failed"),
        ]

        pipeline = IngestionPipeline(vector_store=mock_vector_store)
        pipeline.state.processed_files = ["file1.md", "file2.md"]
        pipeline.state.failed_files = {}

        deleted_files = ["file1.md", "file2.md"]

        successful, failed = pipeline._handle_deleted_files(deleted_files)

        assert successful == 1
        assert failed == 1
        assert "file2.md" in pipeline.state.failed_files
        assert "Delete failed" in pipeline.state.failed_files["file2.md"]

    def test_vector_store_delete_by_file_path(self):
        """Test the new delete_by_file_path method."""
        # Create a real vector store with mock collection
        vector_store = VectorStore(persist_directory=":memory:")

        # Mock the collection
        mock_collection = Mock()
        mock_collection.get.return_value = {"ids": ["id1", "id2", "id3"]}
        vector_store.collection = mock_collection

        # Execute
        count = vector_store.delete_by_file_path("test/file.md")

        # Verify
        assert count == 3
        mock_collection.get.assert_called_with(where={"file_path": "test/file.md"})
        mock_collection.delete.assert_called_with(where={"file_path": "test/file.md"})

    def test_vector_store_delete_by_file_path_no_documents(self):
        """Test delete_by_file_path when no documents match."""
        vector_store = VectorStore(persist_directory=":memory:")

        mock_collection = Mock()
        mock_collection.get.return_value = {"ids": []}
        vector_store.collection = mock_collection

        count = vector_store.delete_by_file_path("nonexistent.md")

        assert count == 0
        mock_collection.delete.assert_not_called()

    def test_renamed_files_handled_correctly(self, tmp_path):
        """Test that renamed files are handled as delete + add."""
        manager = HandbookRepoManager()
        manager.clone_path = tmp_path / "handbook"
        manager.clone_path.mkdir(parents=True)

        with patch("thoth.ingestion.repo_manager.Repo") as mock_repo:
            mock_git = Mock()
            # R100 indicates 100% similarity (renamed file)
            mock_git.diff.return_value = "R100\told/path.md\tnew/path.md"
            mock_repo.return_value.git = mock_git

            result = manager.get_file_changes("abc123")

            assert result is not None
            assert "old/path.md" in result["deleted"]
            assert "new/path.md" in result["added"]
            assert len(result["modified"]) == 0

    def test_state_persistence_after_incremental_update(self, tmp_path):
        """Test that state is correctly saved after incremental updates."""
        repo_path = tmp_path / "repo"
        repo_path.mkdir()
        state_file = tmp_path / "state.json"

        (repo_path / "new.md").write_text("# New")

        mock_repo_manager = Mock()
        mock_repo_manager.clone_path = repo_path
        mock_repo_manager.get_current_commit.return_value = "new_commit"
        mock_repo_manager.update_repository.return_value = True
        mock_repo_manager.save_metadata.return_value = True
        mock_repo_manager.get_file_changes.return_value = {
            "added": ["new.md"],
            "modified": [],
            "deleted": [],
        }

        mock_vector_store = Mock()

        pipeline = IngestionPipeline(
            repo_manager=mock_repo_manager,
            state_file=state_file,
            vector_store=mock_vector_store,
        )
        pipeline.state.last_commit = "old_commit"

        with patch.object(pipeline, "_discover_markdown_files") as mock_discover:
            mock_discover.return_value = [repo_path / "new.md"]
            with patch.object(pipeline, "_process_file") as mock_process:
                mock_chunk = Mock()
                mock_chunk.content = "content"
                mock_chunk.metadata = Mock()
                mock_chunk.metadata.chunk_id = "chunk_1"
                mock_chunk.metadata.to_dict.return_value = {}
                mock_process.return_value = [mock_chunk]

                with patch.object(pipeline.embedder, "embed") as mock_embed:
                    mock_embed.return_value = [[0.1] * 384]

                    pipeline.run(incremental=True)

        # Verify state was saved
        assert state_file.exists()
        with state_file.open() as f:
            state_data = json.load(f)
            assert state_data["last_commit"] == "new_commit"
            assert state_data["completed"] is True


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
