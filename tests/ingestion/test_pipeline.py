"""Tests for the ingestion pipeline orchestrator."""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from thoth.ingestion.chunker import Chunk, ChunkMetadata
from thoth.ingestion.pipeline import IngestionPipeline, PipelineState, PipelineStats


@pytest.fixture
def mock_repo_manager():
    """Create a mock repository manager."""
    manager = MagicMock()
    manager.clone_path = Path("/tmp/test_repo")
    manager.clone_handbook.return_value = Path("/tmp/test_repo")
    manager.update_repository.return_value = True
    manager.get_current_commit.return_value = "abc123"
    manager.get_changed_files.return_value = []
    manager.save_metadata.return_value = True
    return manager


@pytest.fixture
def mock_chunker():
    """Create a mock chunker."""
    chunker = MagicMock()

    # Create sample chunks
    def create_chunks(file_path):
        metadata = ChunkMetadata(
            chunk_id=f"chunk_{file_path.stem}_0",
            file_path=str(file_path),
            chunk_index=0,
            total_chunks=1,
            token_count=100,
            char_count=400,
        )
        return [Chunk(content="Test content", metadata=metadata)]

    chunker.chunk_file.side_effect = create_chunks
    return chunker


@pytest.fixture
def mock_embedder():
    """Create a mock embedder."""
    embedder = MagicMock()
    embedder.embed.return_value = [[0.1, 0.2, 0.3]]
    embedder.embed_single.return_value = [0.1, 0.2, 0.3]
    return embedder


@pytest.fixture
def mock_vector_store():
    """Create a mock vector store."""
    store = MagicMock()
    store.collection_name = "test_collection"
    store.add_documents.return_value = None
    store.get_document_count.return_value = 0
    store.reset.return_value = None
    return store


@pytest.fixture
def temp_state_file(tmp_path):
    """Create a temporary state file path."""
    return tmp_path / "test_state.json"


@pytest.fixture
def pipeline(mock_repo_manager, mock_chunker, mock_embedder, mock_vector_store, temp_state_file):
    """Create a pipeline instance with mocked components."""
    return IngestionPipeline(
        repo_manager=mock_repo_manager,
        chunker=mock_chunker,
        embedder=mock_embedder,
        vector_store=mock_vector_store,
        state_file=temp_state_file,
        batch_size=2,
    )


class TestPipelineState:
    """Tests for PipelineState class."""

    def test_to_dict(self):
        """Test converting state to dictionary."""
        state = PipelineState(
            last_commit="abc123",
            processed_files=["file1.md", "file2.md"],
            failed_files={"file3.md": "Error message"},
            total_chunks=10,
            total_documents=10,
            completed=True,
        )

        state_dict = state.to_dict()
        assert state_dict["last_commit"] == "abc123"
        assert state_dict["processed_files"] == ["file1.md", "file2.md"]
        assert state_dict["failed_files"] == {"file3.md": "Error message"}
        assert state_dict["total_chunks"] == 10
        assert state_dict["completed"] is True

    def test_from_dict(self):
        """Test creating state from dictionary."""
        data = {
            "last_commit": "abc123",
            "processed_files": ["file1.md"],
            "failed_files": {},
            "total_chunks": 5,
            "total_documents": 5,
            "completed": False,
        }

        state = PipelineState.from_dict(data)
        assert state.last_commit == "abc123"
        assert state.processed_files == ["file1.md"]
        assert state.total_chunks == 5
        assert state.completed is False


class TestIngestionPipeline:
    """Tests for IngestionPipeline class."""

    def test_initialization(self, pipeline):
        """Test pipeline initialization."""
        assert pipeline.repo_manager is not None
        assert pipeline.chunker is not None
        assert pipeline.embedder is not None
        assert pipeline.vector_store is not None
        assert pipeline.batch_size == 2
        assert isinstance(pipeline.state, PipelineState)

    def test_load_state_no_file(self, pipeline):
        """Test loading state when no file exists."""
        state = pipeline._load_state()
        assert isinstance(state, PipelineState)
        assert state.last_commit is None
        assert len(state.processed_files) == 0

    def test_load_state_existing_file(
        self,
        temp_state_file,
        mock_vector_store,
        mock_repo_manager,
        mock_chunker,
        mock_embedder,
    ):
        """Test loading state from existing file."""
        # Create state file
        state_data = {
            "last_commit": "abc123",
            "processed_files": ["file1.md"],
            "failed_files": {},
            "total_chunks": 5,
            "total_documents": 5,
            "completed": False,
        }
        with temp_state_file.open("w", encoding="utf-8") as f:
            json.dump(state_data, f)

        # Create pipeline (which loads state) with mocked components
        pipeline = IngestionPipeline(
            state_file=temp_state_file,
            repo_manager=mock_repo_manager,
            chunker=mock_chunker,
            embedder=mock_embedder,
            vector_store=mock_vector_store,
        )
        assert pipeline.state.last_commit == "abc123"
        assert pipeline.state.processed_files == ["file1.md"]
        assert pipeline.state.total_chunks == 5

    def test_save_state(self, pipeline):
        """Test saving state to file."""
        pipeline.state.last_commit = "abc123"
        pipeline.state.processed_files = ["file1.md"]
        pipeline._save_state()

        # Verify file was created
        assert pipeline.state_file.exists()

        # Load and verify contents
        with pipeline.state_file.open(encoding="utf-8") as f:
            data = json.load(f)

        assert data["last_commit"] == "abc123"
        assert data["processed_files"] == ["file1.md"]

    def test_discover_markdown_files(self, pipeline, tmp_path):
        """Test discovering markdown files."""
        # Create test files
        test_dir = tmp_path / "test_repo"
        test_dir.mkdir()
        (test_dir / "file1.md").touch()
        (test_dir / "file2.md").touch()
        (test_dir / "subdir").mkdir()
        (test_dir / "subdir" / "file3.md").touch()
        (test_dir / "notmd.txt").touch()

        files = pipeline._discover_markdown_files(test_dir)

        assert len(files) == 3
        assert all(f.suffix == ".md" for f in files)

    def test_process_file(self, pipeline, tmp_path):
        """Test processing a single file."""
        test_file = tmp_path / "test.md"
        test_file.write_text("# Test content")

        chunks = pipeline._process_file(test_file)

        assert len(chunks) > 0
        assert pipeline.chunker.chunk_file.called

    def test_process_batch_success(self, pipeline, tmp_path):
        """Test processing a batch of files successfully."""
        # Create test files
        file1 = tmp_path / "file1.md"
        file2 = tmp_path / "file2.md"
        file1.write_text("# File 1")
        file2.write_text("# File 2")

        # Update mock to use relative paths
        pipeline.repo_manager.clone_path = tmp_path

        successful, failed = pipeline._process_batch([file1, file2])

        assert successful == 2
        assert failed == 0
        assert len(pipeline.state.processed_files) == 2

    def test_process_batch_with_failures(self, pipeline, tmp_path):
        """Test processing a batch with some failures."""
        file1 = tmp_path / "file1.md"
        file2 = tmp_path / "file2.md"
        file1.write_text("# File 1")
        file2.write_text("# File 2")

        # Make second file fail
        def chunk_side_effect(file_path):
            if file_path == file2:
                msg = "Test error"
                raise ValueError(msg)
            metadata = ChunkMetadata(
                chunk_id=f"chunk_{file_path.stem}_0",
                file_path=str(file_path),
                chunk_index=0,
                total_chunks=1,
            )
            return [Chunk(content="Test content", metadata=metadata)]

        pipeline.chunker.chunk_file.side_effect = chunk_side_effect
        pipeline.repo_manager.clone_path = tmp_path

        successful, failed = pipeline._process_batch([file1, file2])

        assert successful == 1
        assert failed == 1
        assert len(pipeline.state.failed_files) == 1

    def test_process_batch_with_callback(self, pipeline, tmp_path):
        """Test processing batch with progress callback."""
        file1 = tmp_path / "file1.md"
        file1.write_text("# File 1")
        pipeline.repo_manager.clone_path = tmp_path

        callback_calls = []

        def callback(current, total, message):
            callback_calls.append((current, total, message))

        pipeline._process_batch([file1], progress_callback=callback)

        assert len(callback_calls) > 0
        assert callback_calls[0][1] == 1  # Total should be 1

    @patch("thoth.ingestion.pipeline.IngestionPipeline._discover_markdown_files")
    def test_run_full_pipeline(self, mock_discover, pipeline, tmp_path):
        """Test running the full pipeline."""
        # Setup mocks
        file1 = tmp_path / "file1.md"
        file1.write_text("# File 1")
        mock_discover.return_value = [file1]

        pipeline.repo_manager.clone_path = tmp_path

        # Run pipeline
        stats = pipeline.run(force_reclone=False, incremental=False)

        # Verify results
        assert isinstance(stats, PipelineStats)
        assert stats.processed_files >= 0
        assert stats.total_files >= 0
        assert pipeline.state.completed is True
        assert pipeline.repo_manager.save_metadata.called

    @patch("thoth.ingestion.pipeline.IngestionPipeline._discover_markdown_files")
    def test_run_incremental(self, mock_discover, pipeline, tmp_path):
        """Test running pipeline in incremental mode."""
        file1 = tmp_path / "file1.md"
        file1.write_text("# File 1")
        mock_discover.return_value = [file1]

        # Set up previous state
        pipeline.state.last_commit = "old_commit"
        pipeline.repo_manager.get_changed_files.return_value = ["file1.md"]
        pipeline.repo_manager.clone_path = tmp_path

        # Run pipeline
        stats = pipeline.run(incremental=True)

        assert pipeline.repo_manager.get_changed_files.called
        assert isinstance(stats, PipelineStats)

    def test_reset_keep_repo(self, pipeline):
        """Test resetting pipeline while keeping repository."""
        pipeline.state.processed_files = ["file1.md"]
        pipeline.state.total_chunks = 10

        pipeline.reset(keep_repo=True)

        assert pipeline.vector_store.reset.called
        assert len(pipeline.state.processed_files) == 0
        assert pipeline.state.total_chunks == 0

    @patch("shutil.rmtree")
    def test_reset_remove_repo(self, mock_rmtree, pipeline, tmp_path):
        """Test resetting pipeline and removing repository."""
        pipeline.repo_manager.clone_path = tmp_path
        pipeline.repo_manager.clone_path.mkdir(parents=True, exist_ok=True)

        pipeline.reset(keep_repo=False)

        assert pipeline.vector_store.reset.called
        assert mock_rmtree.called

    def test_get_status(self, pipeline):
        """Test getting pipeline status."""
        pipeline.state.processed_files = ["file1.md", "file2.md"]
        pipeline.state.total_chunks = 10
        pipeline.vector_store.get_document_count.return_value = 10

        status = pipeline.get_status()

        assert "state" in status
        assert "repo_path" in status
        assert "vector_store_count" in status
        assert status["vector_store_count"] == 10
        assert status["state"]["total_chunks"] == 10


class TestPipelineStats:
    """Tests for PipelineStats class."""

    def test_stats_creation(self):
        """Test creating pipeline stats."""
        stats = PipelineStats(
            total_files=100,
            processed_files=95,
            failed_files=5,
            total_chunks=1000,
            total_documents=1000,
            duration_seconds=60.0,
            chunks_per_second=16.67,
            files_per_second=1.58,
        )

        assert stats.total_files == 100
        assert stats.processed_files == 95
        assert stats.failed_files == 5
        assert stats.total_chunks == 1000
        assert stats.duration_seconds == 60.0


class TestPipelineIntegration:
    """Integration tests for the pipeline."""

    def test_pipeline_with_real_components(self, tmp_path):
        """Test pipeline with real (non-mocked) components where possible."""
        # This would be an integration test that uses actual components
        # For now, we'll skip this as it requires real dependencies

    def test_pipeline_error_recovery(self, pipeline, tmp_path):
        """Test that pipeline can recover from errors."""
        file1 = tmp_path / "file1.md"
        file2 = tmp_path / "file2.md"
        file1.write_text("# File 1")
        file2.write_text("# File 2")

        # Make processing fail for file2
        def chunk_side_effect(file_path):
            if file_path == file2:
                msg = "Test error"
                raise ValueError(msg)
            metadata = ChunkMetadata(
                chunk_id=f"chunk_{file_path.stem}_0",
                file_path=str(file_path),
                chunk_index=0,
                total_chunks=1,
            )
            return [Chunk(content="Test content", metadata=metadata)]

        pipeline.chunker.chunk_file.side_effect = chunk_side_effect
        pipeline.repo_manager.clone_path = tmp_path

        # Process and verify partial success
        successful, failed = pipeline._process_batch([file1, file2])

        assert successful == 1
        assert failed == 1
        assert "file2.md" in pipeline.state.failed_files
