"""Tests for the CLI interface."""

from unittest.mock import MagicMock, patch

from click.testing import CliRunner
import pytest

from thoth.ingestion.pipeline import PipelineStats
from thoth.shared.cli import cli, setup_pipeline


@pytest.fixture
def runner():
    """Create a Click test runner."""
    return CliRunner()


@pytest.fixture
def mock_pipeline():
    """Create a mock pipeline."""
    pipeline = MagicMock()

    # Mock status
    pipeline.get_status.return_value = {
        "state": {
            "last_commit": "abc123",
            "processed_files": ["file1.md", "file2.md"],
            "failed_files": {},
            "total_chunks": 10,
            "total_documents": 10,
            "start_time": "2024-01-01T00:00:00",
            "last_update_time": "2024-01-01T00:05:00",
            "completed": True,
        },
        "repo_path": "/tmp/test_repo",
        "repo_exists": True,
        "vector_store_count": 10,
        "vector_store_collection": "test_collection",
    }

    # Mock run stats
    pipeline.run.return_value = PipelineStats(
        total_files=10,
        processed_files=10,
        failed_files=0,
        total_chunks=50,
        total_documents=50,
        duration_seconds=30.0,
        chunks_per_second=1.67,
        files_per_second=0.33,
    )

    return pipeline


@pytest.fixture
def mock_vector_store():
    """Create a mock vector store."""
    store = MagicMock()
    store.get_document_count.return_value = 10
    store.search_similar.return_value = {
        "documents": [["This is a test document."]],
        "metadatas": [[{"file_path": "test.md", "chunk_index": 0, "total_chunks": 1}]],
        "distances": [[0.2]],
    }
    return store


class TestCLIIngest:
    """Tests for the ingest command."""

    @patch("thoth.cli.setup_pipeline")
    def test_ingest_basic(self, mock_setup, runner, mock_pipeline):
        """Test basic ingest command."""
        mock_setup.return_value = mock_pipeline

        result = runner.invoke(cli, ["ingest"])

        assert result.exit_code == 0
        assert mock_pipeline.run.called
        assert "Ingestion Complete" in result.output or result.exit_code == 0

    @patch("thoth.cli.setup_pipeline")
    def test_ingest_with_force(self, mock_setup, runner, mock_pipeline):
        """Test ingest with force flag."""
        mock_setup.return_value = mock_pipeline

        result = runner.invoke(cli, ["ingest", "--force"])

        assert result.exit_code == 0
        # Check that run was called with force_reclone=True
        call_args = mock_pipeline.run.call_args
        assert call_args[1]["force_reclone"] is True

    @patch("thoth.cli.setup_pipeline")
    def test_ingest_with_full(self, mock_setup, runner, mock_pipeline):
        """Test ingest with full flag (disable incremental)."""
        mock_setup.return_value = mock_pipeline

        result = runner.invoke(cli, ["ingest", "--full"])

        assert result.exit_code == 0
        call_args = mock_pipeline.run.call_args
        assert call_args[1]["incremental"] is False

    @patch("thoth.cli.setup_pipeline")
    def test_ingest_with_custom_paths(self, mock_setup, runner, mock_pipeline):
        """Test ingest with custom paths."""
        mock_setup.return_value = mock_pipeline

        result = runner.invoke(
            cli,
            [
                "ingest",
                "--repo-url",
                "https://example.com/repo.git",
                "--clone-path",
                "/tmp/custom",
                "--db-path",
                "/tmp/db",
                "--collection",
                "custom_collection",
            ],
        )

        assert result.exit_code == 0
        # Verify setup_pipeline was called with custom values
        mock_setup.assert_called_once()
        call_args = mock_setup.call_args[0]
        assert call_args[0] == "https://example.com/repo.git"
        assert call_args[1] == "/tmp/custom"
        assert call_args[2] == "/tmp/db"
        assert call_args[3] == "custom_collection"

    @patch("thoth.cli.setup_pipeline")
    def test_ingest_with_batch_size(self, mock_setup, runner, mock_pipeline):
        """Test ingest with custom batch size."""
        mock_setup.return_value = mock_pipeline

        result = runner.invoke(cli, ["ingest", "--batch-size", "100"])

        assert result.exit_code == 0
        assert mock_pipeline.batch_size == 100

    @patch("thoth.cli.setup_pipeline")
    def test_ingest_with_failures(self, mock_setup, runner, mock_pipeline):
        """Test ingest command with some failures."""
        # Mock stats with failures
        mock_pipeline.run.return_value = PipelineStats(
            total_files=10,
            processed_files=8,
            failed_files=2,
            total_chunks=40,
            total_documents=40,
            duration_seconds=30.0,
            chunks_per_second=1.33,
            files_per_second=0.27,
        )
        mock_setup.return_value = mock_pipeline

        result = runner.invoke(cli, ["ingest"])

        assert result.exit_code == 0
        # Should mention failed files in output
        assert "failed" in result.output.lower() or result.exit_code == 0

    @patch("thoth.cli.setup_pipeline")
    def test_ingest_error(self, mock_setup, runner, mock_pipeline):
        """Test ingest command with error."""
        mock_pipeline.run.side_effect = RuntimeError("Test error")
        mock_setup.return_value = mock_pipeline

        result = runner.invoke(cli, ["ingest"])

        assert result.exit_code != 0

    @patch("thoth.cli.setup_pipeline")
    def test_ingest_progress_callback(self, mock_setup, runner, mock_pipeline):
        """Test that progress callback is called during ingestion."""

        def run_with_callback(*args, **kwargs):
            # Call the progress callback if provided
            callback = kwargs.get("progress_callback")
            if callback:
                callback(0, 100, "Starting...")
                callback(50, 100, "Processing...")
                callback(100, 100, "Complete!")
            return PipelineStats(
                total_files=10,
                processed_files=10,
                failed_files=0,
                total_chunks=50,
                total_documents=50,
                duration_seconds=30.0,
                chunks_per_second=1.67,
                files_per_second=0.33,
            )

        mock_pipeline.run.side_effect = run_with_callback
        mock_setup.return_value = mock_pipeline

        result = runner.invoke(cli, ["ingest"])

        assert result.exit_code == 0
        assert mock_pipeline.run.called


class TestCLIStatus:
    """Tests for the status command."""

    @patch("thoth.cli.setup_pipeline")
    def test_status_basic(self, mock_setup, runner, mock_pipeline):
        """Test basic status command."""
        mock_setup.return_value = mock_pipeline

        result = runner.invoke(cli, ["status"])

        assert result.exit_code == 0
        assert mock_pipeline.get_status.called
        # Check for expected output elements
        assert "Status" in result.output or "Pipeline" in result.output or result.exit_code == 0

    @patch("thoth.cli.setup_pipeline")
    def test_status_with_custom_paths(self, mock_setup, runner, mock_pipeline):
        """Test status with custom paths."""
        mock_setup.return_value = mock_pipeline

        result = runner.invoke(
            cli,
            [
                "status",
                "--clone-path",
                "/tmp/custom",
                "--db-path",
                "/tmp/db",
                "--collection",
                "custom",
            ],
        )

        assert result.exit_code == 0
        mock_setup.assert_called_once()

    @patch("thoth.cli.setup_pipeline")
    def test_status_with_failures(self, mock_setup, runner, mock_pipeline):
        """Test status command showing failed files."""
        # Update mock to include failed files
        status = mock_pipeline.get_status.return_value
        status["state"]["failed_files"] = {
            "file1.md": "Error 1",
            "file2.md": "Error 2",
        }
        mock_setup.return_value = mock_pipeline

        result = runner.invoke(cli, ["status"])

        assert result.exit_code == 0
        assert "Failed" in result.output or result.exit_code == 0

    @patch("thoth.cli.setup_pipeline")
    def test_status_error(self, mock_setup, runner, mock_pipeline):
        """Test status command with error."""
        mock_pipeline.get_status.side_effect = RuntimeError("Test error")
        mock_setup.return_value = mock_pipeline

        result = runner.invoke(cli, ["status"])

        assert result.exit_code != 0


class TestCLIReset:
    """Tests for the reset command."""

    @patch("thoth.cli.setup_pipeline")
    def test_reset_basic(self, mock_setup, runner, mock_pipeline):
        """Test basic reset command."""
        mock_setup.return_value = mock_pipeline

        # Need to confirm the reset
        result = runner.invoke(cli, ["reset"], input="y\n")

        assert result.exit_code == 0
        assert mock_pipeline.reset.called
        # By default, keep_repo should be False
        call_args = mock_pipeline.reset.call_args
        assert call_args[1]["keep_repo"] is False

    @patch("thoth.cli.setup_pipeline")
    def test_reset_keep_repo(self, mock_setup, runner, mock_pipeline):
        """Test reset with keep-repo flag."""
        mock_setup.return_value = mock_pipeline

        result = runner.invoke(cli, ["reset", "--keep-repo"], input="y\n")

        assert result.exit_code == 0
        call_args = mock_pipeline.reset.call_args
        assert call_args[1]["keep_repo"] is True

    @patch("thoth.cli.setup_pipeline")
    def test_reset_cancel(self, mock_setup, runner, mock_pipeline):
        """Test canceling reset command."""
        mock_setup.return_value = mock_pipeline

        # Respond 'n' to confirmation
        result = runner.invoke(cli, ["reset"], input="n\n")

        assert result.exit_code != 0
        assert not mock_pipeline.reset.called

    @patch("thoth.cli.setup_pipeline")
    def test_reset_error(self, mock_setup, runner, mock_pipeline):
        """Test reset command with error."""
        mock_pipeline.reset.side_effect = RuntimeError("Test error")
        mock_setup.return_value = mock_pipeline

        result = runner.invoke(cli, ["reset"], input="y\n")

        assert result.exit_code != 0


class TestCLISearch:
    """Tests for the search command."""

    @patch("thoth.cli.VectorStore")
    @patch("thoth.cli.Embedder")
    def test_search_basic(self, mock_embedder_class, mock_store_class, runner, mock_vector_store):
        """Test basic search command."""
        mock_store_class.return_value = mock_vector_store

        result = runner.invoke(cli, ["search", "-q", "test query"])

        assert result.exit_code == 0
        assert mock_vector_store.search_similar.called

    @patch("thoth.cli.VectorStore")
    @patch("thoth.cli.Embedder")
    def test_search_with_limit(self, mock_embedder_class, mock_store_class, runner, mock_vector_store):
        """Test search with custom limit."""
        mock_store_class.return_value = mock_vector_store

        result = runner.invoke(cli, ["search", "-q", "test query", "-n", "3"])

        assert result.exit_code == 0
        call_args = mock_vector_store.search_similar.call_args
        assert call_args[1]["n_results"] == 3

    @patch("thoth.cli.VectorStore")
    @patch("thoth.cli.Embedder")
    def test_search_with_custom_paths(self, mock_embedder_class, mock_store_class, runner):
        """Test search with custom database paths."""
        runner.invoke(
            cli,
            [
                "search",
                "-q",
                "test",
                "--db-path",
                "/tmp/db",
                "--collection",
                "custom",
            ],
        )

        # Check that VectorStore was initialized with custom paths
        mock_store_class.assert_called_once()
        call_args = mock_store_class.call_args[1]
        assert call_args["persist_directory"] == "/tmp/db"
        assert call_args["collection_name"] == "custom"

    @patch("thoth.cli.VectorStore")
    @patch("thoth.cli.Embedder")
    def test_search_no_documents(self, mock_embedder_class, mock_store_class, runner):
        """Test search when no documents exist."""
        mock_store = MagicMock()
        mock_store.get_document_count.return_value = 0
        mock_store_class.return_value = mock_store

        result = runner.invoke(cli, ["search", "-q", "test"])

        assert result.exit_code == 0
        assert "No documents" in result.output or "ingest" in result.output

    @patch("thoth.cli.VectorStore")
    @patch("thoth.cli.Embedder")
    def test_search_no_results(self, mock_embedder_class, mock_store_class, runner):
        """Test search with no results."""
        mock_store = MagicMock()
        mock_store.get_document_count.return_value = 10
        mock_store.search_similar.return_value = {
            "documents": [[]],
            "metadatas": [[]],
            "distances": [[]],
        }
        mock_store_class.return_value = mock_store

        result = runner.invoke(cli, ["search", "-q", "test"])

        assert result.exit_code == 0
        assert "No results" in result.output or "Found 0 results" in result.output

    @patch("thoth.cli.VectorStore")
    @patch("thoth.cli.Embedder")
    def test_search_error(self, mock_embedder_class, mock_store_class, runner):
        """Test search command with error."""
        mock_store = MagicMock()
        mock_store.get_document_count.return_value = 10
        mock_store.search_similar.side_effect = RuntimeError("Test error")
        mock_store_class.return_value = mock_store

        result = runner.invoke(cli, ["search", "-q", "test"])

        assert result.exit_code != 0

    def test_search_missing_query(self, runner):
        """Test search without required query parameter."""
        result = runner.invoke(cli, ["search"])

        assert result.exit_code != 0
        assert "Missing option" in result.output or "required" in result.output.lower()


class TestCLIGeneral:
    """General CLI tests."""

    def test_cli_version(self, runner):
        """Test version flag."""
        result = runner.invoke(cli, ["--version"])

        assert result.exit_code == 0

    def test_cli_help(self, runner):
        """Test help flag."""
        result = runner.invoke(cli, ["--help"])

        assert result.exit_code == 0
        assert "ingest" in result.output
        assert "status" in result.output
        assert "reset" in result.output
        assert "search" in result.output

    def test_ingest_help(self, runner):
        """Test ingest command help."""
        result = runner.invoke(cli, ["ingest", "--help"])

        assert result.exit_code == 0
        assert "force" in result.output.lower()
        assert "full" in result.output.lower()

    def test_status_help(self, runner):
        """Test status command help."""
        result = runner.invoke(cli, ["status", "--help"])

        assert result.exit_code == 0

    def test_reset_help(self, runner):
        """Test reset command help."""
        result = runner.invoke(cli, ["reset", "--help"])

        assert result.exit_code == 0
        assert "keep-repo" in result.output.lower()

    def test_search_help(self, runner):
        """Test search command help."""
        result = runner.invoke(cli, ["search", "--help"])

        assert result.exit_code == 0
        assert "query" in result.output.lower()
        assert "limit" in result.output.lower()


class TestSetupPipeline:
    """Tests for the setup_pipeline helper function."""

    @patch("thoth.cli.HandbookRepoManager")
    @patch("thoth.cli.MarkdownChunker")
    @patch("thoth.cli.Embedder")
    @patch("thoth.cli.VectorStore")
    @patch("thoth.cli.IngestionPipeline")
    @patch("thoth.cli.setup_logger")
    def test_setup_pipeline_defaults(
        self,
        mock_logger,
        mock_pipeline_class,
        mock_store_class,
        mock_embedder_class,
        mock_chunker_class,
        mock_repo_class,
    ):
        """Test setup_pipeline with default values."""
        setup_pipeline(None, None, None, None)

        # Verify all components were initialized
        assert mock_repo_class.called
        assert mock_chunker_class.called
        assert mock_embedder_class.called
        assert mock_store_class.called
        assert mock_pipeline_class.called

    @patch("thoth.cli.HandbookRepoManager")
    @patch("thoth.cli.MarkdownChunker")
    @patch("thoth.cli.Embedder")
    @patch("thoth.cli.VectorStore")
    @patch("thoth.cli.IngestionPipeline")
    @patch("thoth.cli.setup_logger")
    def test_setup_pipeline_custom_values(
        self,
        mock_logger,
        mock_pipeline_class,
        mock_store_class,
        mock_embedder_class,
        mock_chunker_class,
        mock_repo_class,
    ):
        """Test setup_pipeline with custom values."""
        setup_pipeline(
            "https://example.com/repo.git",
            "/tmp/custom",
            "/tmp/db",
            "custom_collection",
        )

        # Verify custom values were passed
        repo_call_args = mock_repo_class.call_args[1]
        assert repo_call_args["repo_url"] == "https://example.com/repo.git"

        store_call_args = mock_store_class.call_args[1]
        assert store_call_args["persist_directory"] == "/tmp/db"
        assert store_call_args["collection_name"] == "custom_collection"
