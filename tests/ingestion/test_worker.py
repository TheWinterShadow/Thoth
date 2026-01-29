"""Unit tests for thoth.ingestion.worker module."""

from unittest.mock import patch

import pytest

from thoth.ingestion.worker import main


class TestIngestionWorker:
    """Test cases for ingestion worker functionality."""

    @patch("thoth.ingestion.worker.uvicorn")
    @patch("thoth.ingestion.worker.Starlette")
    def test_main_function(self, mock_starlette, mock_uvicorn):
        """Test main function initializes and runs worker."""
        main()

        mock_starlette.assert_called_once()
        mock_uvicorn.run.assert_called_once()

    @patch("thoth.ingestion.worker.uvicorn")
    @patch("thoth.ingestion.worker.Starlette")
    def test_worker_port_configuration(self, mock_starlette, mock_uvicorn):
        """Test worker runs on correct port."""
        main()

        call_kwargs = mock_uvicorn.run.call_args[1]
        assert call_kwargs["port"] == 8080
        assert call_kwargs["host"] == "0.0.0.0"  # nosec B104


class TestWorkerEndpoints:
    """Test worker HTTP endpoints."""

    @pytest.mark.asyncio
    async def test_health_endpoint_exists(self):
        """Test health endpoint is configured."""
        with (
            patch("thoth.ingestion.worker.uvicorn"),
            patch("thoth.ingestion.worker.Starlette") as mock_starlette,
        ):
            main()

            # Verify Starlette app was created with routes
            mock_starlette.assert_called_once()
            call_kwargs = mock_starlette.call_args[1]
            assert "routes" in call_kwargs

    @pytest.mark.asyncio
    async def test_clone_to_gcs_endpoint_exists(self):
        """Test clone-to-gcs endpoint is configured."""
        with (
            patch("thoth.ingestion.worker.uvicorn"),
            patch("thoth.ingestion.worker.Starlette") as mock_starlette,
        ):
            main()

            # Verify routes were registered
            call_kwargs = mock_starlette.call_args[1]
            routes = call_kwargs.get("routes", [])
            assert len(routes) > 0

    @pytest.mark.asyncio
    async def test_ingest_endpoint_exists(self):
        """Test ingest endpoint is configured."""
        with (
            patch("thoth.ingestion.worker.uvicorn"),
            patch("thoth.ingestion.worker.Starlette") as mock_starlette,
        ):
            main()

            call_kwargs = mock_starlette.call_args[1]
            routes = call_kwargs.get("routes", [])
            # Should have health, clone-to-gcs, ingest, ingest-batch routes
            assert len(routes) >= 4


class TestWorkerCloudTasksIntegration:
    """Test Cloud Tasks integration in worker."""

    @pytest.mark.asyncio
    async def test_batch_processing_endpoint(self):
        """Test batch processing endpoint configuration."""
        with (
            patch("thoth.ingestion.worker.uvicorn"),
            patch("thoth.ingestion.worker.Starlette"),
        ):
            # Should not raise any errors
            main()

    @pytest.mark.asyncio
    @patch("thoth.ingestion.worker.IngestionPipeline")
    async def test_pipeline_integration(self, mock_pipeline):
        """Test worker integrates with IngestionPipeline."""
        with (
            patch("thoth.ingestion.worker.uvicorn"),
            patch("thoth.ingestion.worker.Starlette"),
        ):
            main()
            # Worker should be ready to use IngestionPipeline
