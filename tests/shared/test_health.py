"""Unit tests for thoth.shared.health module."""

from unittest.mock import MagicMock, patch

from thoth.shared.health import HealthCheck


class TestHealthCheck:
    """Test cases for HealthCheck functionality."""

    @patch("thoth.shared.health.Path")
    def test_get_health_status_healthy(self, mock_path):
        """Test health status returns healthy when all checks pass."""
        # Mock Path.exists() to return True for all checks
        mock_path_instance = MagicMock()
        mock_path_instance.exists.return_value = True
        mock_path.return_value = mock_path_instance

        status = HealthCheck.get_health_status()

        assert status["status"] == "healthy"
        assert "timestamp" in status

    def test_health_check_structure(self):
        """Test health check returns expected structure."""
        status = HealthCheck.get_health_status()

        assert isinstance(status, dict)
        assert "status" in status
        assert "timestamp" in status
        assert status["status"] in ["healthy", "degraded", "unhealthy"]

    @patch("thoth.shared.health.Path")
    def test_chroma_db_check(self, mock_path):
        """Test ChromaDB health check."""
        mock_path_instance = MagicMock()
        mock_path_instance.exists.return_value = True
        mock_path.return_value = mock_path_instance

        # This tests that the health check doesn't crash
        status = HealthCheck.get_health_status()
        assert status is not None


class TestHealthCheckIntegration:
    """Integration tests for health check system."""

    def test_health_check_cli_exists(self):
        """Test that health_check_cli function exists."""
        # Verify the class has the method we expect
        assert hasattr(HealthCheck, "get_health_status")

    def test_multiple_health_checks(self):
        """Test running health check multiple times."""
        status1 = HealthCheck.get_health_status()
        status2 = HealthCheck.get_health_status()

        # Both should return valid status
        assert status1["status"] in ["healthy", "degraded", "unhealthy"]
        assert status2["status"] in ["healthy", "degraded", "unhealthy"]
