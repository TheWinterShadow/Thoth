"""Tests for the scheduler module."""

from unittest.mock import MagicMock

import pytest

from thoth.scheduler import SyncScheduler


@pytest.fixture
def mock_pipeline():
    """Create a mock pipeline for testing."""
    pipeline = MagicMock()

    # Mock stats object
    stats = MagicMock()
    stats.processed_files = 10
    stats.failed_files = 0
    stats.total_chunks = 50
    stats.total_documents = 100
    stats.duration_seconds = 5.0

    pipeline.run.return_value = stats

    return pipeline


@pytest.fixture
def scheduler(mock_pipeline):
    """Create a scheduler instance for testing."""
    return SyncScheduler(pipeline=mock_pipeline, job_id="test_job")


class TestSyncScheduler:
    """Test suite for SyncScheduler."""

    def test_initialization(self, mock_pipeline):
        """Test scheduler initialization."""
        scheduler = SyncScheduler(
            pipeline=mock_pipeline,
            job_id="custom_job",
        )

        assert scheduler.pipeline == mock_pipeline
        assert scheduler.job_id == "custom_job"
        assert scheduler.scheduler is not None
        assert not scheduler.scheduler.running

    def test_add_interval_job(self, scheduler):
        """Test adding an interval-based job."""
        scheduler.add_interval_job(interval_minutes=30)

        job = scheduler.scheduler.get_job(scheduler.job_id)
        assert job is not None
        assert job.name == "Periodic Handbook Sync"

    def test_add_cron_job(self, scheduler):
        """Test adding a cron-based job."""
        scheduler.add_cron_job(hour=2, minute=30)

        job = scheduler.scheduler.get_job(scheduler.job_id)
        assert job is not None
        assert job.name == "Cron Handbook Sync"

    def test_start_stop_scheduler(self, scheduler):
        """Test starting and stopping the scheduler."""
        scheduler.add_interval_job(interval_minutes=60)

        scheduler.start()
        assert scheduler.scheduler.running

        scheduler.stop(wait=False)
        assert not scheduler.scheduler.running

    def test_manual_trigger(self, scheduler, mock_pipeline):
        """Test manually triggering a sync."""
        result = scheduler.trigger_manual_sync()

        assert result["success"] is True
        assert result["processed_files"] == 10
        assert result["total_chunks"] == 50
        mock_pipeline.run.assert_called_once()

    def test_get_job_status_no_job(self, scheduler):
        """Test getting status when no job is scheduled."""
        status = scheduler.get_job_status()

        assert status["scheduled"] is False
        assert status["next_run_time"] is None
        assert status["running"] is False

    def test_get_job_status_with_job(self, scheduler):
        """Test getting status when job is scheduled."""
        scheduler.add_interval_job(interval_minutes=60)
        scheduler.start()

        status = scheduler.get_job_status()

        assert status["scheduled"] is True
        assert status["running"] is True

        scheduler.stop(wait=False)

    def test_success_callback(self, scheduler, mock_pipeline):
        """Test that success callbacks are called."""
        callback_called = False
        callback_data = None

        def callback(stats):
            nonlocal callback_called, callback_data
            callback_called = True
            callback_data = stats

        scheduler.add_success_callback(callback)
        scheduler.trigger_manual_sync()

        assert callback_called
        assert callback_data["success"] is True
        assert callback_data["processed_files"] == 10

    def test_failure_callback(self, scheduler, mock_pipeline):
        """Test that failure callbacks are called on error."""
        mock_pipeline.run.side_effect = RuntimeError("Sync failed")

        callback_called = False
        callback_error = None

        def callback(error):
            nonlocal callback_called, callback_error
            callback_called = True
            callback_error = error

        scheduler.add_failure_callback(callback)

        with pytest.raises(RuntimeError):
            scheduler.trigger_manual_sync()

        assert callback_called
        assert isinstance(callback_error, RuntimeError)
        assert str(callback_error) == "Sync failed"

    def test_pause_resume_job(self, scheduler):
        """Test pausing and resuming a job."""
        scheduler.add_interval_job(interval_minutes=60)
        scheduler.start()

        scheduler.pause_job()
        job = scheduler.scheduler.get_job(scheduler.job_id)
        # Job should still exist but be paused
        assert job is not None

        scheduler.resume_job()
        job = scheduler.scheduler.get_job(scheduler.job_id)
        assert job is not None

        scheduler.stop(wait=False)

    def test_remove_job(self, scheduler):
        """Test removing a job."""
        scheduler.add_interval_job(interval_minutes=60)

        scheduler.remove_job()
        job = scheduler.scheduler.get_job(scheduler.job_id)
        assert job is None

    def test_multiple_callbacks(self, scheduler):
        """Test that multiple callbacks are all called."""
        callback1_called = False
        callback2_called = False

        def callback1(stats):
            nonlocal callback1_called
            callback1_called = True

        def callback2(stats):
            nonlocal callback2_called
            callback2_called = True

        scheduler.add_success_callback(callback1)
        scheduler.add_success_callback(callback2)
        scheduler.trigger_manual_sync()

        assert callback1_called
        assert callback2_called

    def test_callback_error_handling(self, scheduler):
        """Test that errors in callbacks don't break the sync."""

        def bad_callback(stats):
            msg = "Callback error"
            raise ValueError(msg)

        def good_callback(stats):
            pass  # Should still be called

        scheduler.add_success_callback(bad_callback)
        scheduler.add_success_callback(good_callback)

        # Should not raise even though callback fails
        result = scheduler.trigger_manual_sync()
        assert result["success"] is True

    def test_start_immediately(self, scheduler, mock_pipeline):
        """Test that start_immediately triggers immediate sync."""
        scheduler.add_interval_job(
            interval_minutes=60,
            start_immediately=True,
        )

        # Should have called run immediately
        mock_pipeline.run.assert_called_once()
