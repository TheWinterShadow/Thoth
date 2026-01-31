"""Unit tests for thoth.shared.health module."""

from unittest.mock import MagicMock, patch

from thoth.shared.health import HealthCheck


class TestHealthCheck:
    """Test cases for HealthCheck functionality."""

    def test_get_health_status_healthy(self):
        """Test health status returns healthy when all checks pass."""
        status = HealthCheck.get_health_status()

        assert status["status"] == "healthy"
        assert "python_version" in status
        assert "python_ok" in status
        assert status["python_ok"] is True

    def test_health_check_structure(self):
        """Test health check returns expected structure."""
        status = HealthCheck.get_health_status()

        assert isinstance(status, dict)
        assert "status" in status
        assert "python_version" in status
        assert "imports" in status
        assert "storage" in status
        assert "gcs" in status
        assert status["status"] in ["healthy", "degraded", "unhealthy"]

    def test_check_imports(self):
        """Test imports check returns expected structure."""
        imports = HealthCheck.check_imports()

        assert isinstance(imports, dict)
        assert "lancedb" in imports
        assert "torch" in imports
        assert "sentence_transformers" in imports
        assert "mcp" in imports

    def test_check_python_version(self):
        """Test Python version check."""
        result = HealthCheck.check_python_version()
        assert result is True  # Test should run on Python 3.10+

    @patch("thoth.shared.health.Path")
    def test_check_storage(self, mock_path):
        """Test storage check."""
        mock_path_instance = MagicMock()
        mock_path_instance.exists.return_value = True
        mock_path.return_value = mock_path_instance

        storage_status = HealthCheck.check_storage()
        assert isinstance(storage_status, dict)
        assert "data_dir_exists" in storage_status


class TestHealthCheckIntegration:
    """Integration tests for health check system."""

    def test_is_healthy(self):
        """Test is_healthy method."""
        result = HealthCheck.is_healthy()
        assert isinstance(result, bool)
        assert result is True  # Should be healthy in test environment

    def test_multiple_health_checks(self):
        """Test running health check multiple times."""
        status1 = HealthCheck.get_health_status()
        status2 = HealthCheck.get_health_status()

        # Both should return valid status
        assert status1["status"] in ["healthy", "degraded", "unhealthy"]
        assert status2["status"] in ["healthy", "degraded", "unhealthy"]

    def test_gcs_config_check(self):
        """Test GCS config check."""
        gcs_status = HealthCheck.check_gcs_config()

        assert isinstance(gcs_status, dict)
        assert "gcs_bucket_configured" in gcs_status
        assert "gcp_project_configured" in gcs_status
        assert "gcs_credentials_file_exists" in gcs_status
