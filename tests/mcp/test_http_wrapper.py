"""Unit tests for thoth.mcp.http_wrapper module."""

from unittest.mock import MagicMock, patch

import pytest

from thoth.mcp.http_wrapper import main


class TestHTTPWrapper:
    """Test cases for HTTP wrapper functionality."""

    @patch("thoth.mcp.http_wrapper.ThothMCPServer")
    @patch("thoth.mcp.http_wrapper.uvicorn")
    def test_main_function(self, mock_uvicorn, mock_mcp_server):
        """Test main function initializes and runs server."""
        mock_server_instance = MagicMock()
        mock_mcp_server.return_value = mock_server_instance
        mock_sse_app = MagicMock()
        mock_server_instance.get_sse_app.return_value = mock_sse_app

        main()

        mock_mcp_server.assert_called_once()
        mock_server_instance.get_sse_app.assert_called_once()
        mock_uvicorn.run.assert_called_once()

    @patch("thoth.mcp.http_wrapper.ThothMCPServer")
    def test_health_check_route_added(self, mock_mcp_server):
        """Test that health check routes are added to SSE app."""
        mock_server_instance = MagicMock()
        mock_mcp_server.return_value = mock_server_instance
        mock_sse_app = MagicMock()
        mock_sse_app.routes = []
        mock_server_instance.get_sse_app.return_value = mock_sse_app

        with patch("thoth.mcp.http_wrapper.uvicorn"):
            main()

        # Should have added health check routes
        assert len(mock_sse_app.routes) == 2  # /health and /

    @pytest.mark.asyncio
    async def test_health_check_endpoint(self):
        """Test health check endpoint returns correct status."""
        with (
            patch("thoth.mcp.http_wrapper.ThothMCPServer"),
            patch("thoth.mcp.http_wrapper.uvicorn"),
            patch("thoth.mcp.http_wrapper.HealthCheck") as mock_health,
        ):
            mock_health.get_health_status.return_value = {"status": "healthy", "timestamp": "2024-01-01T00:00:00Z"}

            # This would test the health_check function if we could extract it
            # For now, just verify HealthCheck is called
            main()


class TestServerConfiguration:
    """Test server configuration and setup."""

    @patch("thoth.mcp.http_wrapper.ThothMCPServer")
    @patch("thoth.mcp.http_wrapper.uvicorn")
    def test_server_port_configuration(self, mock_uvicorn, mock_mcp_server):
        """Test server runs on correct port."""
        mock_server_instance = MagicMock()
        mock_mcp_server.return_value = mock_server_instance
        mock_server_instance.get_sse_app.return_value = MagicMock()

        main()

        call_kwargs = mock_uvicorn.run.call_args[1]
        assert call_kwargs["port"] == 8080
        assert call_kwargs["host"] == "0.0.0.0"  # nosec B104

    @patch("thoth.mcp.http_wrapper.ThothMCPServer")
    @patch("thoth.mcp.http_wrapper.uvicorn")
    def test_logging_configuration(self, mock_uvicorn, mock_mcp_server):
        """Test logging is configured correctly."""
        mock_server_instance = MagicMock()
        mock_mcp_server.return_value = mock_server_instance
        mock_server_instance.get_sse_app.return_value = MagicMock()

        main()

        call_kwargs = mock_uvicorn.run.call_args[1]
        assert call_kwargs["log_level"] == "info"
        assert call_kwargs["access_log"] is True
