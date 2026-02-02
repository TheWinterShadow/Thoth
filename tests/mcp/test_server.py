"""Unit tests for Thoth MCP Server."""

import unittest
from unittest.mock import patch

from starlette.testclient import TestClient

from thoth.mcp.server import app, main


class TestHealthEndpoint(unittest.TestCase):
    """Test suite for health check endpoint."""

    def setUp(self):
        """Set up test client."""
        self.client = TestClient(app)

    @patch("thoth.mcp.server.HealthCheck.get_health_status")
    def test_health_endpoint_healthy(self, mock_health):
        """Test health endpoint returns 200 when healthy."""
        mock_health.return_value = {"status": "healthy", "details": {}}

        response = self.client.get("/health")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "healthy")

    @patch("thoth.mcp.server.HealthCheck.get_health_status")
    def test_health_endpoint_unhealthy(self, mock_health):
        """Test health endpoint returns 503 when unhealthy."""
        mock_health.return_value = {"status": "unhealthy", "error": "test"}

        response = self.client.get("/health")
        self.assertEqual(response.status_code, 503)

    @patch("thoth.mcp.server.HealthCheck.get_health_status")
    def test_root_endpoint_returns_health(self, mock_health):
        """Test root endpoint returns health status."""
        mock_health.return_value = {"status": "healthy"}

        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)


class TestAppStructure(unittest.TestCase):
    """Test suite for app structure."""

    def test_app_exists(self):
        """Test that app is created."""
        self.assertIsNotNone(app)

    def test_app_has_routes(self):
        """Test that app has expected routes."""
        route_paths = [r.path for r in app.routes]
        self.assertIn("/health", route_paths)
        self.assertIn("/", route_paths)
        self.assertIn("/mcp", route_paths)

    def test_mcp_is_mounted(self):
        """Test that MCP SSE app is mounted at /mcp."""
        mcp_route = None
        for route in app.routes:
            if hasattr(route, "path") and route.path == "/mcp":
                mcp_route = route
                break

        self.assertIsNotNone(mcp_route)


class TestMainFunction(unittest.TestCase):
    """Test suite for main function."""

    @patch("thoth.mcp.server.uvicorn.run")
    def test_main_runs_uvicorn(self, mock_run):
        """Test that main function starts uvicorn."""
        main()

        mock_run.assert_called_once()
        call_kwargs = mock_run.call_args.kwargs
        self.assertEqual(call_kwargs["host"], "0.0.0.0")
        self.assertEqual(call_kwargs["port"], 8080)


if __name__ == "__main__":
    unittest.main()
