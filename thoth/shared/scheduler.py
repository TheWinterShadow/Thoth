"""Scheduler for automated synchronization tasks.

This module provides scheduling functionality for periodic sync operations
using APScheduler. It supports configurable intervals, manual triggers, and
job status monitoring.
"""

from collections.abc import Callable
from datetime import datetime, timezone
import logging
from typing import Any

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from thoth.ingestion.pipeline import IngestionPipeline
from thoth.shared.utils.logger import setup_logger

__all__ = ["SyncScheduler"]
logger = logging.getLogger(__name__)


class SyncScheduler:
    """Manages scheduled synchronization jobs.

    This class wraps APScheduler to provide convenient scheduling of sync
    operations with monitoring hooks and manual trigger support.

    Attributes:
        pipeline: The ingestion pipeline to run on schedule
        scheduler: APScheduler BackgroundScheduler instance
        job_id: Unique identifier for the scheduled job
        logger: Logger instance for recording events
    """

    def __init__(
        self,
        pipeline: IngestionPipeline,
        logger_instance: logging.Logger | None = None,
        job_id: str = "sync_job",
    ):
        """Initialize the sync scheduler.

        Args:
            pipeline: Configured IngestionPipeline instance
            logger_instance: Optional logger instance
            job_id: Unique identifier for the scheduled job
        """
        self.pipeline = pipeline
        self.scheduler = BackgroundScheduler()
        self.job_id = job_id
        self.logger = logger_instance or setup_logger(__name__)
        self._on_success_callbacks: list[Callable[[dict[str, Any]], None]] = []
        self._on_failure_callbacks: list[Callable[[Exception], None]] = []

    def add_interval_job(
        self,
        interval_minutes: int = 60,
        start_immediately: bool = False,
    ) -> None:
        """Schedule a sync job to run at regular intervals.

        Args:
            interval_minutes: Minutes between sync runs (default: 60)
            start_immediately: Whether to run the job immediately on schedule (default: False)
        """
        if interval_minutes <= 0:
            self.logger.error(
                "Invalid interval_minutes value: %s. The interval must be greater than 0.",
                interval_minutes,
            )
            msg = f"interval_minutes must be greater than 0, got {interval_minutes}"
            raise ValueError(msg)
        trigger = IntervalTrigger(minutes=interval_minutes)

        self.scheduler.add_job(
            func=self._run_sync,
            trigger=trigger,
            id=self.job_id,
            name="Periodic Handbook Sync",
            replace_existing=True,
        )

        self.logger.info(f"Scheduled sync job to run every {interval_minutes} minutes")

        if start_immediately:
            self.trigger_manual_sync()

    def add_cron_job(
        self,
        hour: int = 0,
        minute: int = 0,
        day_of_week: str = "*",
    ) -> None:
        """Schedule a sync job using a cron-like schedule.

        Args:
            hour: Hour of day to run (0-23)
            minute: Minute of hour to run (0-59)
            day_of_week: Days to run (0-6 for Mon-Sun, or * for all)
        """
        trigger = CronTrigger(
            hour=hour,
            minute=minute,
            day_of_week=day_of_week,
        )

        self.scheduler.add_job(
            func=self._run_sync,
            trigger=trigger,
            id=self.job_id,
            name="Cron Handbook Sync",
            replace_existing=True,
        )

        self.logger.info(f"Scheduled sync job (cron): hour={hour}, minute={minute}, day_of_week={day_of_week}")

    def start(self) -> None:
        """Start the scheduler.

        This will begin running scheduled jobs. The scheduler runs in the
        background and does not block.
        """
        if not self.scheduler.running:
            self.scheduler.start()
            self.logger.info("Scheduler started")
        else:
            self.logger.warning("Scheduler is already running")

    def stop(self, wait: bool = True) -> None:
        """Stop the scheduler.

        Args:
            wait: Whether to wait for running jobs to complete
        """
        if self.scheduler.running:
            self.scheduler.shutdown(wait=wait)
            self.logger.info("Scheduler stopped")
        else:
            self.logger.warning("Scheduler is not running")

    def trigger_manual_sync(self) -> dict[str, Any]:
        """Manually trigger a sync operation immediately.

        Returns:
            Dictionary containing sync statistics and status
        """
        self.logger.info("Manual sync triggered")
        return self._run_sync()

    def get_job_status(self) -> dict[str, Any]:
        """Get the current status of the scheduled job.

        Returns:
            Dictionary with job status information:
                - scheduled: Whether job is scheduled
                - next_run_time: Next scheduled run (if scheduled)
                - running: Whether scheduler is running
        """
        job = self.scheduler.get_job(self.job_id)

        status = {
            "scheduled": job is not None,
            "next_run_time": None,
            "running": self.scheduler.running,
        }

        if job:
            status["next_run_time"] = job.next_run_time.isoformat() if job.next_run_time else None

        return status

    def add_success_callback(
        self,
        callback: Callable[[dict[str, Any]], None],
    ) -> None:
        """Add a callback to be called when sync succeeds.

        Args:
            callback: Function that takes sync stats dict as argument
        """
        self._on_success_callbacks.append(callback)

    def add_failure_callback(
        self,
        callback: Callable[[Exception], None],
    ) -> None:
        """Add a callback to be called when sync fails.

        Args:
            callback: Function that takes exception as argument
        """
        self._on_failure_callbacks.append(callback)

    def _run_sync(self) -> dict[str, Any]:
        """Internal method to run the sync pipeline.

        Executes the pipeline and calls registered callbacks on success/failure.

        Returns:
            Dictionary containing sync statistics
        """
        self.logger.info("Starting scheduled sync operation")
        start_time = datetime.now(timezone.utc)

        try:
            # Run the pipeline in incremental mode
            stats = self.pipeline.run(
                force_reclone=False,
                incremental=True,
            )

            # Convert stats to dict
            stats_dict = {
                "success": True,
                "start_time": start_time.isoformat(),
                "end_time": datetime.now(timezone.utc).isoformat(),
                "processed_files": stats.processed_files,
                "failed_files": stats.failed_files,
                "total_chunks": stats.total_chunks,
                "total_documents": stats.total_documents,
                "duration_seconds": stats.duration_seconds,
            }

            self.logger.info(f"Sync completed successfully: {stats.processed_files} files processed")

            # Call success callbacks
            for success_callback in self._on_success_callbacks:
                try:
                    success_callback(stats_dict)
                except Exception:
                    self.logger.exception("Error in success callback")

            return stats_dict

        except Exception as e:
            self.logger.exception("Sync operation failed")

            # Call failure callbacks
            for failure_callback in self._on_failure_callbacks:
                try:
                    failure_callback(e)
                except Exception:
                    self.logger.exception("Error in failure callback")

            # Re-raise to allow APScheduler to handle it
            raise

    def pause_job(self) -> None:
        """Pause the scheduled job without stopping the scheduler."""
        job = self.scheduler.get_job(self.job_id)
        if job:
            job.pause()
            self.logger.info("Job paused")
        else:
            self.logger.warning("No job to pause")

    def resume_job(self) -> None:
        """Resume a paused job."""
        job = self.scheduler.get_job(self.job_id)
        if job:
            job.resume()
            self.logger.info("Job resumed")
        else:
            self.logger.warning("No job to resume")

    def remove_job(self) -> None:
        """Remove the scheduled job."""
        if self.scheduler.get_job(self.job_id):
            self.scheduler.remove_job(self.job_id)
            self.logger.info("Job removed")
        else:
            self.logger.warning("No job to remove")
