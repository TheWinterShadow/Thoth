"""Monitoring and health check system for Thoth.

This module provides metrics tracking, health status monitoring, and alerting
hooks for the ingestion pipeline and scheduled operations.
"""

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
import json
from pathlib import Path
import shutil
import threading
from typing import Any

from thoth.shared.utils.logger import logging, setup_logger

logger = setup_logger(__name__)

__all__ = [
    "HealthCheck",
    "HealthStatus",
    "Metrics",
    "Monitor",
    "create_default_health_checks",
]


class HealthStatus(Enum):
    """Enumeration of possible health statuses."""

    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"
    UNKNOWN = "unknown"


@dataclass
class HealthCheck:
    """Represents a health check result.

    Attributes:
        name: Name of the health check
        status: Health status result
        message: Human-readable status message
        timestamp: When the check was performed
        metadata: Additional check-specific data
    """

    name: str
    status: HealthStatus
    message: str
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert this health check result to a JSON-serializable dict.

        Returns:
            Dict with name, status (str), message, timestamp (ISO), metadata.
        """
        return {
            "name": self.name,
            "status": self.status.value,
            "message": self.message,
            "timestamp": self.timestamp.isoformat(),
            "metadata": self.metadata,
        }


@dataclass
class Metrics:
    """Tracks operational metrics.

    Attributes:
        sync_count: Total number of sync operations
        sync_success_count: Number of successful syncs
        sync_failure_count: Number of failed syncs
        last_sync_time: Timestamp of last sync attempt
        last_sync_duration: Duration of last sync in seconds
        total_files_processed: Cumulative files processed
        total_chunks_created: Cumulative chunks created
        errors: List of recent error messages
    """

    sync_count: int = 0
    sync_success_count: int = 0
    sync_failure_count: int = 0
    last_sync_time: datetime | None = None
    last_sync_duration: float = 0.0
    total_files_processed: int = 0
    total_chunks_created: int = 0
    errors: list[dict[str, str]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Convert metrics to a JSON-serializable dict for APIs or export.

        Returns:
            Dict with sync counts, last sync time/duration, totals, error_count, recent_errors.
        """
        return {
            "sync_count": self.sync_count,
            "sync_success_count": self.sync_success_count,
            "sync_failure_count": self.sync_failure_count,
            "last_sync_time": (self.last_sync_time.isoformat() if self.last_sync_time else None),
            "last_sync_duration": self.last_sync_duration,
            "total_files_processed": self.total_files_processed,
            "total_chunks_created": self.total_chunks_created,
            "error_count": len(self.errors),
            "recent_errors": self.errors[-10:],  # Last 10 errors
        }


class Monitor:
    """Monitoring system for tracking metrics and health status.

    This class provides centralized monitoring with thread-safe metric
    collection, health checks, and alerting capabilities.

    Attributes:
        metrics: Current operational metrics
        health_checks: Dictionary of registered health checks
        alert_callbacks: List of functions to call on alerts
        logger: Logger instance
    """

    def __init__(
        self,
        logger_instance: logging.Logger | None = None,
        max_errors: int = 100,
    ):
        """Initialize the monitoring system.

        Args:
            logger_instance: Optional logger instance
            max_errors: Maximum number of errors to retain
        """
        self.metrics = Metrics()
        self.health_checks: dict[str, Callable[[], HealthCheck]] = {}
        self.alert_callbacks: list[Callable[[str, dict[str, Any]], None]] = []
        self.logger = logger_instance or setup_logger(__name__)
        self.max_errors = max_errors
        self._lock = threading.Lock()

    def record_sync_start(self) -> None:
        """Record the start of a sync operation (thread-safe)."""
        with self._lock:  # Protects metrics from concurrent scheduler/CLI updates
            self.metrics.sync_count += 1
            self.metrics.last_sync_time = datetime.now(UTC)
            self.logger.debug("Sync operation started")

    def record_sync_success(
        self,
        files_processed: int,
        chunks_created: int,
        duration: float,
    ) -> None:
        """Record a successful sync operation.

        Args:
            files_processed: Number of files processed
            chunks_created: Number of chunks created
            duration: Duration in seconds
        """
        with self._lock:
            self.metrics.sync_success_count += 1
            self.metrics.last_sync_duration = duration
            self.metrics.total_files_processed += files_processed
            self.metrics.total_chunks_created += chunks_created

            self.logger.info(
                f"Sync success recorded: {files_processed} files, {chunks_created} chunks, {duration:.2f}s"
            )

    def record_sync_failure(self, error: Exception) -> None:
        """Record a failed sync operation.

        Args:
            error: Exception that caused the failure
        """
        with self._lock:
            self.metrics.sync_failure_count += 1

            error_info = {
                "timestamp": datetime.now(UTC).isoformat(),
                "type": type(error).__name__,
                "message": str(error),
            }

            self.metrics.errors.append(error_info)

            # Trim errors list if it exceeds max
            if len(self.metrics.errors) > self.max_errors:
                self.metrics.errors = self.metrics.errors[-self.max_errors :]

            self.logger.error(f"Sync failure recorded: {error}")

            # Trigger alert
            self._trigger_alert("sync_failure", error_info)

    def register_health_check(
        self,
        name: str,
        check_function: Callable[[], HealthCheck],
    ) -> None:
        """Register a health check function.

        Args:
            name: Unique name for the health check
            check_function: Function that returns a HealthCheck
        """
        self.health_checks[name] = check_function
        self.logger.debug(f"Registered health check: {name}")

    def run_health_checks(self) -> dict[str, HealthCheck]:
        """Run all registered health checks.

        Returns:
            Dictionary mapping check names to results
        """
        results = {}

        for name, check_func in self.health_checks.items():
            try:
                result = check_func()
                results[name] = result

                if result.status == HealthStatus.UNHEALTHY:
                    self._trigger_alert(
                        "health_check_failed",
                        result.to_dict(),
                    )

            except Exception as e:
                self.logger.exception(f"Health check '{name}' failed")
                results[name] = HealthCheck(
                    name=name,
                    status=HealthStatus.UNKNOWN,
                    message=f"Check failed with error: {e}",
                )

        return results

    def get_overall_health(self) -> HealthStatus:
        """Determine overall system health based on all checks.

        Returns:
            Overall HealthStatus
        """
        results = self.run_health_checks()

        if not results:
            return HealthStatus.UNKNOWN

        statuses = [check.status for check in results.values()]

        if HealthStatus.UNHEALTHY in statuses:
            return HealthStatus.UNHEALTHY
        if HealthStatus.DEGRADED in statuses:
            return HealthStatus.DEGRADED
        if HealthStatus.UNKNOWN in statuses:
            return HealthStatus.UNKNOWN
        return HealthStatus.HEALTHY

    def get_health_report(self) -> dict[str, Any]:
        """Generate a comprehensive health report.

        Returns:
            Dictionary containing overall health and individual checks
        """
        health_checks = self.run_health_checks()
        overall_status = self.get_overall_health()

        return {
            "overall_status": overall_status.value,
            "timestamp": datetime.now(UTC).isoformat(),
            "checks": {name: check.to_dict() for name, check in health_checks.items()},
        }

    def get_metrics(self) -> dict[str, Any]:
        """Get current metrics snapshot.

        Returns:
            Dictionary containing current metrics
        """
        with self._lock:
            return self.metrics.to_dict()

    def add_alert_callback(
        self,
        callback: Callable[[str, dict[str, Any]], None],
    ) -> None:
        """Add a callback function for alerts.

        The callback will be called with (alert_type, data) when alerts trigger.

        Args:
            callback: Function to call on alerts
        """
        self.alert_callbacks.append(callback)
        self.logger.debug("Alert callback registered")

    def _trigger_alert(self, alert_type: str, data: dict[str, Any]) -> None:
        """Trigger an alert by calling all registered callbacks.

        Args:
            alert_type: Type of alert (e.g., "sync_failure")
            data: Additional data about the alert
        """
        alert_info = {
            "type": alert_type,
            "timestamp": datetime.now(UTC).isoformat(),
            "data": data,
        }

        self.logger.warning(f"Alert triggered: {alert_type}")

        for callback in self.alert_callbacks:
            try:
                callback(alert_type, alert_info)
            except Exception:
                self.logger.exception("Error in alert callback")

    def reset_metrics(self) -> None:
        """Reset all metrics to initial values."""
        with self._lock:
            self.metrics = Metrics()
            self.logger.info("Metrics reset")

    def export_metrics(self, filepath: Path) -> None:
        """Export metrics to a JSON file.

        Args:
            filepath: Path to export file
        """
        metrics_data = self.get_metrics()

        with filepath.open("w") as f:
            json.dump(metrics_data, f, indent=2)

        self.logger.info(f"Metrics exported to {filepath}")

    def get_success_rate(self) -> float:
        """Calculate sync success rate.

        Returns:
            Success rate as a percentage (0-100)
        """
        with self._lock:
            if self.metrics.sync_count == 0:
                return 0.0

            return (self.metrics.sync_success_count / self.metrics.sync_count) * 100


def create_default_health_checks(
    vector_store_path: Path,
    repo_path: Path,
) -> dict[str, Callable[[], HealthCheck]]:
    """Create default health check functions for common components.

    Args:
        vector_store_path: Path to vector store database
        repo_path: Path to repository

    Returns:
        Dictionary of health check functions
    """

    def check_vector_store() -> HealthCheck:
        """Check if vector store is accessible and valid."""
        try:
            if not vector_store_path.exists():
                return HealthCheck(
                    name="vector_store",
                    status=HealthStatus.UNHEALTHY,
                    message="Vector store does not exist",
                )

            # Check if it's a directory
            if not vector_store_path.is_dir():
                return HealthCheck(
                    name="vector_store",
                    status=HealthStatus.UNHEALTHY,
                    message="Vector store path is not a directory",
                )

            return HealthCheck(
                name="vector_store",
                status=HealthStatus.HEALTHY,
                message="Vector store is accessible",
                metadata={"path": str(vector_store_path)},
            )

        except (OSError, ValueError) as e:
            return HealthCheck(
                name="vector_store",
                status=HealthStatus.UNHEALTHY,
                message=f"Error checking vector store: {e}",
            )

    def check_repository() -> HealthCheck:
        """Check if repository is present and valid."""
        try:
            if not repo_path.exists():
                return HealthCheck(
                    name="repository",
                    status=HealthStatus.DEGRADED,
                    message="Repository not cloned",
                )

            # Check for .git directory
            git_dir = repo_path / ".git"
            if not git_dir.exists():
                return HealthCheck(
                    name="repository",
                    status=HealthStatus.UNHEALTHY,
                    message="Repository directory exists but is not a git repo",
                )

            return HealthCheck(
                name="repository",
                status=HealthStatus.HEALTHY,
                message="Repository is valid",
                metadata={"path": str(repo_path)},
            )

        except (OSError, ValueError) as e:
            return HealthCheck(
                name="repository",
                status=HealthStatus.UNHEALTHY,
                message=f"Error checking repository: {e}",
            )

    def check_disk_space() -> HealthCheck:
        """Check available disk space."""
        try:
            stats = shutil.disk_usage(vector_store_path.parent)
            free_gb = stats.free / (1024**3)
            total_gb = stats.total / (1024**3)
            percent_free = (stats.free / stats.total) * 100

            if percent_free < 5:
                status = HealthStatus.UNHEALTHY
                message = f"Critical: Only {free_gb:.1f}GB free"
            elif percent_free < 15:
                status = HealthStatus.DEGRADED
                message = f"Warning: Only {free_gb:.1f}GB free"
            else:
                status = HealthStatus.HEALTHY
                message = f"Sufficient space: {free_gb:.1f}GB free"

            return HealthCheck(
                name="disk_space",
                status=status,
                message=message,
                metadata={
                    "free_gb": round(free_gb, 2),
                    "total_gb": round(total_gb, 2),
                    "percent_free": round(percent_free, 2),
                },
            )

        except (OSError, ValueError) as e:
            return HealthCheck(
                name="disk_space",
                status=HealthStatus.UNKNOWN,
                message=f"Error checking disk space: {e}",
            )

    return {
        "vector_store": check_vector_store,
        "repository": check_repository,
        "disk_space": check_disk_space,
    }
