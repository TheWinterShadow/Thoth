"""Tests for the monitoring module."""

from datetime import datetime
import json
from pathlib import Path
import tempfile

import pytest

from thoth.monitoring import (
    HealthCheck,
    HealthStatus,
    Metrics,
    Monitor,
    create_default_health_checks,
)


class TestHealthStatus:
    """Test suite for HealthStatus enum."""

    def test_health_statuses(self):
        """Test that all expected statuses exist."""
        assert HealthStatus.HEALTHY.value == "healthy"
        assert HealthStatus.DEGRADED.value == "degraded"
        assert HealthStatus.UNHEALTHY.value == "unhealthy"
        assert HealthStatus.UNKNOWN.value == "unknown"


class TestHealthCheck:
    """Test suite for HealthCheck dataclass."""

    def test_health_check_creation(self):
        """Test creating a health check."""
        check = HealthCheck(
            name="test_check",
            status=HealthStatus.HEALTHY,
            message="All good",
        )

        assert check.name == "test_check"
        assert check.status == HealthStatus.HEALTHY
        assert check.message == "All good"
        assert isinstance(check.timestamp, datetime)

    def test_health_check_to_dict(self):
        """Test converting health check to dictionary."""
        check = HealthCheck(
            name="test_check",
            status=HealthStatus.DEGRADED,
            message="Warning",
            metadata={"key": "value"},
        )

        result = check.to_dict()

        assert result["name"] == "test_check"
        assert result["status"] == "degraded"
        assert result["message"] == "Warning"
        assert "timestamp" in result
        assert result["metadata"] == {"key": "value"}


class TestMetrics:
    """Test suite for Metrics dataclass."""

    def test_metrics_initialization(self):
        """Test default metrics initialization."""
        metrics = Metrics()

        assert metrics.sync_count == 0
        assert metrics.sync_success_count == 0
        assert metrics.sync_failure_count == 0
        assert metrics.last_sync_time is None
        assert metrics.last_sync_duration == 0.0
        assert metrics.total_files_processed == 0
        assert metrics.total_chunks_created == 0
        assert len(metrics.errors) == 0

    def test_metrics_to_dict(self):
        """Test converting metrics to dictionary."""
        metrics = Metrics(
            sync_count=10,
            sync_success_count=8,
            sync_failure_count=2,
        )

        result = metrics.to_dict()

        assert result["sync_count"] == 10
        assert result["sync_success_count"] == 8
        assert result["sync_failure_count"] == 2
        assert result["last_sync_time"] is None


class TestMonitor:
    """Test suite for Monitor class."""

    @pytest.fixture
    def monitor(self):
        """Create a monitor instance for testing."""
        return Monitor()

    def test_initialization(self):
        """Test monitor initialization."""
        monitor = Monitor(max_errors=50)

        assert isinstance(monitor.metrics, Metrics)
        assert monitor.max_errors == 50
        assert len(monitor.health_checks) == 0
        assert len(monitor.alert_callbacks) == 0

    def test_record_sync_start(self, monitor):
        """Test recording sync start."""
        monitor.record_sync_start()

        assert monitor.metrics.sync_count == 1
        assert monitor.metrics.last_sync_time is not None

    def test_record_sync_success(self, monitor):
        """Test recording successful sync."""
        monitor.record_sync_success(
            files_processed=10,
            chunks_created=50,
            duration=5.5,
        )

        assert monitor.metrics.sync_success_count == 1
        assert monitor.metrics.total_files_processed == 10
        assert monitor.metrics.total_chunks_created == 50
        assert monitor.metrics.last_sync_duration == 5.5

    def test_record_sync_failure(self, monitor):
        """Test recording sync failure."""
        error = RuntimeError("Test error")
        monitor.record_sync_failure(error)

        assert monitor.metrics.sync_failure_count == 1
        assert len(monitor.metrics.errors) == 1
        assert monitor.metrics.errors[0]["type"] == "RuntimeError"
        assert monitor.metrics.errors[0]["message"] == "Test error"

    def test_error_limit(self):
        """Test that error list is limited to max_errors."""
        monitor = Monitor(max_errors=5)

        # Add more errors than the limit
        for i in range(10):
            monitor.record_sync_failure(RuntimeError(f"Error {i}"))

        # Should only keep last 5
        assert len(monitor.metrics.errors) == 5
        assert monitor.metrics.errors[0]["message"] == "Error 5"
        assert monitor.metrics.errors[-1]["message"] == "Error 9"

    def test_register_health_check(self, monitor):
        """Test registering a health check."""

        def check_func():
            return HealthCheck(
                name="test",
                status=HealthStatus.HEALTHY,
                message="OK",
            )

        monitor.register_health_check("test_check", check_func)

        assert "test_check" in monitor.health_checks

    def test_run_health_checks(self, monitor):
        """Test running health checks."""

        def check1():
            return HealthCheck(
                name="check1",
                status=HealthStatus.HEALTHY,
                message="OK",
            )

        def check2():
            return HealthCheck(
                name="check2",
                status=HealthStatus.DEGRADED,
                message="Warning",
            )

        monitor.register_health_check("check1", check1)
        monitor.register_health_check("check2", check2)

        results = monitor.run_health_checks()

        assert len(results) == 2
        assert results["check1"].status == HealthStatus.HEALTHY
        assert results["check2"].status == HealthStatus.DEGRADED

    def test_get_overall_health_healthy(self, monitor):
        """Test overall health when all checks are healthy."""

        def healthy_check():
            return HealthCheck(
                name="test",
                status=HealthStatus.HEALTHY,
                message="OK",
            )

        monitor.register_health_check("check1", healthy_check)
        monitor.register_health_check("check2", healthy_check)

        overall = monitor.get_overall_health()
        assert overall == HealthStatus.HEALTHY

    def test_get_overall_health_degraded(self, monitor):
        """Test overall health when one check is degraded."""

        def healthy_check():
            return HealthCheck(
                name="test",
                status=HealthStatus.HEALTHY,
                message="OK",
            )

        def degraded_check():
            return HealthCheck(
                name="test",
                status=HealthStatus.DEGRADED,
                message="Warning",
            )

        monitor.register_health_check("check1", healthy_check)
        monitor.register_health_check("check2", degraded_check)

        overall = monitor.get_overall_health()
        assert overall == HealthStatus.DEGRADED

    def test_get_overall_health_unhealthy(self, monitor):
        """Test overall health when one check is unhealthy."""

        def healthy_check():
            return HealthCheck(
                name="test",
                status=HealthStatus.HEALTHY,
                message="OK",
            )

        def unhealthy_check():
            return HealthCheck(
                name="test",
                status=HealthStatus.UNHEALTHY,
                message="Error",
            )

        monitor.register_health_check("check1", healthy_check)
        monitor.register_health_check("check2", unhealthy_check)

        overall = monitor.get_overall_health()
        assert overall == HealthStatus.UNHEALTHY

    def test_get_health_report(self, monitor):
        """Test getting comprehensive health report."""

        def check_func():
            return HealthCheck(
                name="test",
                status=HealthStatus.HEALTHY,
                message="OK",
            )

        monitor.register_health_check("test_check", check_func)

        report = monitor.get_health_report()

        assert "overall_status" in report
        assert "timestamp" in report
        assert "checks" in report
        assert "test_check" in report["checks"]

    def test_get_metrics(self, monitor):
        """Test getting metrics snapshot."""
        monitor.record_sync_start()
        monitor.record_sync_success(5, 25, 3.0)

        metrics = monitor.get_metrics()

        assert metrics["sync_count"] == 1
        assert metrics["sync_success_count"] == 1
        assert metrics["total_files_processed"] == 5

    def test_add_alert_callback(self, monitor):
        """Test adding alert callbacks."""
        callback_called = False

        def callback(alert_type, data):
            nonlocal callback_called
            callback_called = True

        monitor.add_alert_callback(callback)
        monitor.record_sync_failure(RuntimeError("Test"))

        assert callback_called

    def test_alert_on_unhealthy_check(self, monitor):
        """Test that alerts are triggered on unhealthy checks."""
        alert_triggered = False
        alert_data = None

        def callback(alert_type, data):
            nonlocal alert_triggered, alert_data
            alert_triggered = True
            alert_data = data

        def unhealthy_check():
            return HealthCheck(
                name="test",
                status=HealthStatus.UNHEALTHY,
                message="Error",
            )

        monitor.add_alert_callback(callback)
        monitor.register_health_check("test_check", unhealthy_check)
        monitor.run_health_checks()

        assert alert_triggered
        assert alert_data["type"] == "health_check_failed"

    def test_reset_metrics(self, monitor):
        """Test resetting metrics."""
        monitor.record_sync_start()
        monitor.record_sync_success(5, 25, 3.0)

        monitor.reset_metrics()

        assert monitor.metrics.sync_count == 0
        assert monitor.metrics.sync_success_count == 0
        assert monitor.metrics.total_files_processed == 0

    def test_export_metrics(self, monitor):
        """Test exporting metrics to file."""
        monitor.record_sync_start()
        monitor.record_sync_success(5, 25, 3.0)

        with tempfile.TemporaryDirectory() as tmpdir:
            filepath = Path(tmpdir) / "metrics.json"
            monitor.export_metrics(filepath)

            assert filepath.exists()

            with filepath.open() as f:
                data = json.load(f)

            assert data["sync_count"] == 1
            assert data["total_files_processed"] == 5

    def test_get_success_rate(self, monitor):
        """Test calculating success rate."""
        # No syncs yet
        assert monitor.get_success_rate() == 0.0

        # All successful
        monitor.record_sync_start()
        monitor.record_sync_success(5, 25, 3.0)
        assert monitor.get_success_rate() == 100.0

        # One failure
        monitor.record_sync_start()
        monitor.record_sync_failure(RuntimeError("Test"))
        assert monitor.get_success_rate() == 50.0

    def test_health_check_exception_handling(self, monitor):
        """Test that exceptions in health checks are handled."""

        def bad_check():
            msg = "Check failed"
            raise RuntimeError(msg)

        monitor.register_health_check("bad_check", bad_check)
        results = monitor.run_health_checks()

        assert "bad_check" in results
        assert results["bad_check"].status == HealthStatus.UNKNOWN


class TestDefaultHealthChecks:
    """Test suite for default health check functions."""

    def test_create_default_health_checks(self):
        """Test creating default health checks."""
        with tempfile.TemporaryDirectory() as tmpdir:
            vector_store_path = Path(tmpdir) / "vector_store"
            repo_path = Path(tmpdir) / "repo"

            checks = create_default_health_checks(
                vector_store_path=vector_store_path,
                repo_path=repo_path,
            )

            assert "vector_store" in checks
            assert "repository" in checks
            assert "disk_space" in checks

    def test_vector_store_check_missing(self):
        """Test vector store check when store doesn't exist."""
        with tempfile.TemporaryDirectory() as tmpdir:
            vector_store_path = Path(tmpdir) / "nonexistent"
            repo_path = Path(tmpdir) / "repo"

            checks = create_default_health_checks(
                vector_store_path=vector_store_path,
                repo_path=repo_path,
            )

            result = checks["vector_store"]()
            assert result.status == HealthStatus.UNHEALTHY

    def test_vector_store_check_exists(self):
        """Test vector store check when store exists."""
        with tempfile.TemporaryDirectory() as tmpdir:
            vector_store_path = Path(tmpdir) / "vector_store"
            vector_store_path.mkdir()
            repo_path = Path(tmpdir) / "repo"

            checks = create_default_health_checks(
                vector_store_path=vector_store_path,
                repo_path=repo_path,
            )

            result = checks["vector_store"]()
            assert result.status == HealthStatus.HEALTHY

    def test_repository_check_missing(self):
        """Test repository check when repo doesn't exist."""
        with tempfile.TemporaryDirectory() as tmpdir:
            vector_store_path = Path(tmpdir) / "vector_store"
            repo_path = Path(tmpdir) / "nonexistent"

            checks = create_default_health_checks(
                vector_store_path=vector_store_path,
                repo_path=repo_path,
            )

            result = checks["repository"]()
            assert result.status == HealthStatus.DEGRADED

    def test_repository_check_exists(self):
        """Test repository check when repo exists."""
        with tempfile.TemporaryDirectory() as tmpdir:
            vector_store_path = Path(tmpdir) / "vector_store"
            repo_path = Path(tmpdir) / "repo"
            repo_path.mkdir()
            (repo_path / ".git").mkdir()

            checks = create_default_health_checks(
                vector_store_path=vector_store_path,
                repo_path=repo_path,
            )

            result = checks["repository"]()
            assert result.status == HealthStatus.HEALTHY

    def test_disk_space_check(self):
        """Test disk space check."""
        with tempfile.TemporaryDirectory() as tmpdir:
            vector_store_path = Path(tmpdir) / "vector_store"
            vector_store_path.mkdir()
            repo_path = Path(tmpdir) / "repo"

            checks = create_default_health_checks(
                vector_store_path=vector_store_path,
                repo_path=repo_path,
            )

            result = checks["disk_space"]()
            # Should have metadata about disk space
            assert "free_gb" in result.metadata
            assert "total_gb" in result.metadata
            assert "percent_free" in result.metadata
