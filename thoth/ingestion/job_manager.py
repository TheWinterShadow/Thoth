"""Job manager for tracking ingestion jobs using Firestore.

This module provides job tracking and status management for ingestion
operations using Google Cloud Firestore as the backend.
"""

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
import os
from typing import Any
import urllib.parse
import uuid

from thoth.shared.utils.logger import setup_logger

logger = setup_logger(__name__)


def get_job_logs_url(
    job_id: str,
    project_id: str | None = None,
    service_name: str = "thoth-ingestion-worker",
) -> str:
    """Generate Cloud Logging URL for a specific job.

    Args:
        job_id: Job identifier to filter logs
        project_id: GCP project ID (defaults to environment variable)
        service_name: Cloud Run service name

    Returns:
        URL to view logs in GCP Console
    """
    project = project_id or os.getenv("GCP_PROJECT_ID", "thoth-dev-485501")

    # Build log filter query
    filter_parts = [
        'resource.type="cloud_run_revision"',
        f'resource.labels.service_name="{service_name}"',
        f'jsonPayload.job_id="{job_id}"',
    ]
    filter_query = "\n".join(filter_parts)

    # URL encode the filter
    encoded_filter = urllib.parse.quote(filter_query)

    return f"https://console.cloud.google.com/logs/query;query={encoded_filter}?project={project}"


class JobStatus(Enum):
    """Job status enumeration."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class JobStats:
    """Statistics for a job.

    Attributes:
        total_files: Total number of files to process
        processed_files: Number of files successfully processed
        failed_files: Number of files that failed processing
        total_chunks: Total number of chunks created
        total_documents: Total number of documents stored
    """

    total_files: int = 0
    processed_files: int = 0
    failed_files: int = 0
    total_chunks: int = 0
    total_documents: int = 0

    def to_dict(self) -> dict[str, int]:
        """Convert stats to dictionary."""
        return {
            "total_files": self.total_files,
            "processed_files": self.processed_files,
            "failed_files": self.failed_files,
            "total_chunks": self.total_chunks,
            "total_documents": self.total_documents,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "JobStats":
        """Create JobStats from dictionary."""
        return cls(
            total_files=data.get("total_files", 0),
            processed_files=data.get("processed_files", 0),
            failed_files=data.get("failed_files", 0),
            total_chunks=data.get("total_chunks", 0),
            total_documents=data.get("total_documents", 0),
        )


@dataclass
class Job:
    """Represents an ingestion job.

    Attributes:
        job_id: Unique job identifier (UUID or parent_id_NNNN for sub-jobs)
        status: Current job status
        source: Source identifier (e.g., 'handbook', 'dnd')
        collection_name: Target LanceDB collection
        started_at: Job start timestamp
        completed_at: Job completion timestamp (if finished)
        stats: Job statistics
        error: Error message (if failed)
        parent_job_id: Parent job ID (for sub-jobs/batches)
        batch_index: Batch number within parent job (for sub-jobs)
        total_batches: Total number of batches (for parent jobs)
        completed_batches: Number of completed batches (for parent jobs)
    """

    job_id: str
    status: JobStatus
    source: str
    collection_name: str
    started_at: datetime
    completed_at: datetime | None = None
    stats: JobStats = field(default_factory=JobStats)
    error: str | None = None
    parent_job_id: str | None = None
    batch_index: int | None = None
    total_batches: int | None = None
    completed_batches: int = 0

    def to_dict(self) -> dict[str, Any]:
        """Convert job to Firestore-compatible dictionary."""
        data: dict[str, Any] = {
            "job_id": self.job_id,
            "status": self.status.value,
            "source": self.source,
            "collection_name": self.collection_name,
            "started_at": self.started_at.isoformat(),
            "completed_at": (self.completed_at.isoformat() if self.completed_at else None),
            "stats": self.stats.to_dict(),
            "error": self.error,
            "logs_url": get_job_logs_url(self.job_id),
        }
        # Only include batch fields if relevant
        if self.parent_job_id is not None:
            data["parent_job_id"] = self.parent_job_id
        if self.batch_index is not None:
            data["batch_index"] = self.batch_index
        if self.total_batches is not None:
            data["total_batches"] = self.total_batches
        if self.completed_batches > 0 or self.total_batches is not None:
            data["completed_batches"] = self.completed_batches
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Job":
        """Create Job from Firestore document dictionary."""
        return cls(
            job_id=data["job_id"],
            status=JobStatus(data["status"]),
            source=data["source"],
            collection_name=data["collection_name"],
            started_at=datetime.fromisoformat(data["started_at"]),
            completed_at=(datetime.fromisoformat(data["completed_at"]) if data.get("completed_at") else None),
            stats=JobStats.from_dict(data.get("stats", {})),
            error=data.get("error"),
            parent_job_id=data.get("parent_job_id"),
            batch_index=data.get("batch_index"),
            total_batches=data.get("total_batches"),
            completed_batches=data.get("completed_batches", 0),
        )

    @property
    def is_finished(self) -> bool:
        """Check if job has finished (completed or failed)."""
        return self.status in (JobStatus.COMPLETED, JobStatus.FAILED)

    @property
    def is_sub_job(self) -> bool:
        """Check if this is a sub-job (batch) of a parent job."""
        return self.parent_job_id is not None

    @property
    def duration_seconds(self) -> float | None:
        """Get job duration in seconds if finished."""
        if self.completed_at:
            return (self.completed_at - self.started_at).total_seconds()
        return None


class JobManager:
    """Manages job state in Firestore.

    This class provides CRUD operations for ingestion jobs stored in
    Google Cloud Firestore. Jobs are stored in the 'thoth_jobs' collection.

    Example:
        >>> manager = JobManager()
        >>> job = manager.create_job("handbook", "handbook_documents")
        >>> print(job.job_id)
        >>> manager.mark_running(job)
        >>> # ... do work ...
        >>> manager.mark_completed(job, stats)
    """

    COLLECTION_NAME = "thoth_jobs"

    def __init__(self, project_id: str | None = None) -> None:
        """Initialize job manager with Firestore.

        Args:
            project_id: GCP project ID (uses default/env if not specified)
        """
        self._project_id = project_id or os.getenv("GCP_PROJECT_ID")
        self._db = None
        self._collection = None

    def _ensure_initialized(self) -> None:
        """Lazily initialize Firestore client."""
        if self._db is None:
            try:
                from google.cloud import firestore  # type: ignore[attr-defined]  # noqa: PLC0415

                self._db = firestore.Client(project=self._project_id)
                self._collection = self._db.collection(  # type: ignore[attr-defined]
                    self.COLLECTION_NAME
                )
                logger.info(
                    "Initialized JobManager with Firestore (project: %s)",
                    self._project_id,
                )
            except ImportError as e:
                msg = "google-cloud-firestore is required. Install with: pip install google-cloud-firestore"
                raise ImportError(msg) from e

    @property
    def collection(self) -> Any:
        """Get the Firestore collection reference."""
        self._ensure_initialized()
        return self._collection

    def create_job(
        self,
        source: str,
        collection_name: str,
        total_batches: int | None = None,
    ) -> Job:
        """Create a new job and persist to Firestore.

        Args:
            source: Source identifier (e.g., 'handbook', 'dnd')
            collection_name: Target LanceDB collection
            total_batches: Number of batches (for parent jobs with sub-jobs)

        Returns:
            Created Job instance
        """
        job = Job(
            job_id=str(uuid.uuid4()),
            status=JobStatus.PENDING,
            source=source,
            collection_name=collection_name,
            started_at=datetime.now(UTC),
            total_batches=total_batches,
        )

        self.collection.document(job.job_id).set(job.to_dict())
        logger.info("Created job %s for source '%s'", job.job_id, source)
        return job

    def create_sub_job(
        self,
        parent_job: Job,
        batch_index: int,
        total_files: int = 0,
    ) -> Job:
        """Create a sub-job (batch) for a parent job.

        Sub-job IDs are formatted as {parent_job_id}_{batch_index:04d}
        for easy identification and sorting.

        Args:
            parent_job: Parent job instance
            batch_index: Batch number (0-based)
            total_files: Number of files in this batch

        Returns:
            Created sub-job instance
        """
        sub_job_id = f"{parent_job.job_id}_{batch_index:04d}"

        sub_job = Job(
            job_id=sub_job_id,
            status=JobStatus.PENDING,
            source=parent_job.source,
            collection_name=parent_job.collection_name,
            started_at=datetime.now(UTC),
            parent_job_id=parent_job.job_id,
            batch_index=batch_index,
            stats=JobStats(total_files=total_files),
        )

        self.collection.document(sub_job.job_id).set(sub_job.to_dict())
        logger.info(
            "Created sub-job %s (batch %d of %d)",
            sub_job.job_id,
            batch_index + 1,
            parent_job.total_batches or "?",
        )
        return sub_job

    def get_job(self, job_id: str) -> Job | None:
        """Retrieve a job by ID.

        Args:
            job_id: Job identifier

        Returns:
            Job instance or None if not found
        """
        doc = self.collection.document(job_id).get()
        if doc.exists:
            return Job.from_dict(doc.to_dict())
        return None

    def update_job(self, job: Job) -> None:
        """Update job state in Firestore.

        Args:
            job: Job instance with updated state
        """
        self.collection.document(job.job_id).set(job.to_dict())
        logger.debug("Updated job %s: status=%s", job.job_id, job.status.value)

    def mark_running(self, job: Job) -> None:
        """Mark job as running.

        Args:
            job: Job to update
        """
        job.status = JobStatus.RUNNING
        self.update_job(job)
        logger.info("Job %s marked as running", job.job_id)

    def mark_completed(self, job: Job, stats: JobStats | None = None) -> None:
        """Mark job as completed with statistics.

        Args:
            job: Job to update
            stats: Optional final statistics
        """
        job.status = JobStatus.COMPLETED
        job.completed_at = datetime.now(UTC)
        if stats:
            job.stats = stats
        self.update_job(job)
        logger.info(
            "Job %s completed: %d files processed",
            job.job_id,
            job.stats.processed_files,
        )

    def mark_failed(self, job: Job, error: str) -> None:
        """Mark job as failed with error message.

        Args:
            job: Job to update
            error: Error message describing the failure
        """
        job.status = JobStatus.FAILED
        job.completed_at = datetime.now(UTC)
        job.error = error
        self.update_job(job)
        logger.error("Job %s failed: %s", job.job_id, error)

    def update_stats(self, job: Job, stats: JobStats) -> None:
        """Update job statistics (for progress tracking).

        Args:
            job: Job to update
            stats: Updated statistics
        """
        job.stats = stats
        self.update_job(job)

    def list_jobs(
        self,
        source: str | None = None,
        status: JobStatus | None = None,
        limit: int = 50,
    ) -> list[Job]:
        """List jobs with optional filtering.

        Args:
            source: Filter by source
            status: Filter by status
            limit: Maximum number of jobs to return

        Returns:
            List of Job instances, ordered by start time descending
        """
        query = self.collection

        if source:
            query = query.where("source", "==", source)
        if status:
            query = query.where("status", "==", status.value)

        query = query.order_by("started_at", direction="DESCENDING").limit(limit)

        return [Job.from_dict(doc.to_dict()) for doc in query.stream()]

    def delete_job(self, job_id: str) -> bool:
        """Delete a job from Firestore.

        Args:
            job_id: Job identifier to delete

        Returns:
            True if job was deleted, False if not found
        """
        doc_ref = self.collection.document(job_id)
        doc = doc_ref.get()

        if doc.exists:
            doc_ref.delete()
            logger.info("Deleted job %s", job_id)
            return True
        return False

    def cleanup_old_jobs(self, days: int = 30) -> int:
        """Delete jobs older than specified days.

        Args:
            days: Age threshold in days

        Returns:
            Number of jobs deleted
        """
        cutoff = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
        cutoff = cutoff.replace(day=cutoff.day - days)

        # Query old jobs
        query = self.collection.where("started_at", "<", cutoff.isoformat())

        deleted = 0
        for doc in query.stream():
            doc.reference.delete()
            deleted += 1

        if deleted:
            logger.info("Cleaned up %d old jobs (older than %d days)", deleted, days)

        return deleted

    def get_sub_jobs(self, parent_job_id: str) -> list[Job]:
        """Get all sub-jobs for a parent job.

        Args:
            parent_job_id: Parent job identifier

        Returns:
            List of sub-jobs, ordered by batch_index
        """
        query = self.collection.where("parent_job_id", "==", parent_job_id)
        query = query.order_by("batch_index")

        return [Job.from_dict(doc.to_dict()) for doc in query.stream()]

    def get_job_with_sub_jobs(self, job_id: str) -> dict[str, Any] | None:
        """Get a job with its sub-jobs and aggregated statistics.

        Args:
            job_id: Job identifier

        Returns:
            Dictionary with job details and sub-jobs, or None if not found
        """
        job = self.get_job(job_id)
        if job is None:
            return None

        result = job.to_dict()

        # If this is a parent job with batches, include sub-job info
        if job.total_batches is not None and job.total_batches > 0:
            sub_jobs = self.get_sub_jobs(job_id)

            # Aggregate statistics from sub-jobs
            total_processed = 0
            total_failed = 0
            total_chunks = 0
            completed_count = 0
            failed_count = 0
            running_count = 0
            pending_count = 0

            sub_job_summaries = []
            for sub_job in sub_jobs:
                total_processed += sub_job.stats.processed_files
                total_failed += sub_job.stats.failed_files
                total_chunks += sub_job.stats.total_chunks

                if sub_job.status == JobStatus.COMPLETED:
                    completed_count += 1
                elif sub_job.status == JobStatus.FAILED:
                    failed_count += 1
                elif sub_job.status == JobStatus.RUNNING:
                    running_count += 1
                else:
                    pending_count += 1

                sub_job_summaries.append(
                    {
                        "job_id": sub_job.job_id,
                        "batch_index": sub_job.batch_index,
                        "status": sub_job.status.value,
                        "stats": sub_job.stats.to_dict(),
                        "error": sub_job.error,
                        "logs_url": get_job_logs_url(sub_job.job_id),
                    }
                )

            # Update aggregated stats in result
            result["stats"]["processed_files"] = total_processed
            result["stats"]["failed_files"] = total_failed
            result["stats"]["total_chunks"] = total_chunks
            result["stats"]["total_documents"] = total_chunks

            result["batch_summary"] = {
                "total": job.total_batches,
                "completed": completed_count,
                "failed": failed_count,
                "running": running_count,
                "pending": pending_count,
            }
            result["sub_jobs"] = sub_job_summaries

        return result

    def mark_sub_job_completed(
        self,
        sub_job: Job,
        stats: JobStats | None = None,
    ) -> Job | None:
        """Mark a sub-job as completed and update parent job progress.

        Args:
            sub_job: Sub-job to mark as completed
            stats: Optional final statistics for the sub-job

        Returns:
            Updated parent job, or None if no parent
        """
        # Mark sub-job as completed
        self.mark_completed(sub_job, stats)

        # Update parent job if exists
        if sub_job.parent_job_id:
            parent_job = self.get_job(sub_job.parent_job_id)
            if parent_job:
                parent_job.completed_batches += 1

                # Aggregate stats from this sub-job into parent
                if stats:
                    parent_job.stats.processed_files += stats.processed_files
                    parent_job.stats.failed_files += stats.failed_files
                    parent_job.stats.total_chunks += stats.total_chunks
                    parent_job.stats.total_documents += stats.total_documents

                # Check if all batches are done
                if parent_job.total_batches and parent_job.completed_batches >= parent_job.total_batches:
                    parent_job.status = JobStatus.COMPLETED
                    parent_job.completed_at = datetime.now(UTC)
                    logger.info(
                        "Parent job %s completed: all %d batches done",
                        parent_job.job_id,
                        parent_job.total_batches,
                    )

                self.update_job(parent_job)
                return parent_job

        return None

    def mark_sub_job_failed(self, sub_job: Job, error: str) -> Job | None:
        """Mark a sub-job as failed and update parent job.

        Args:
            sub_job: Sub-job to mark as failed
            error: Error message

        Returns:
            Updated parent job, or None if no parent
        """
        # Mark sub-job as failed
        self.mark_failed(sub_job, error)

        # Update parent job if exists
        if sub_job.parent_job_id:
            parent_job = self.get_job(sub_job.parent_job_id)
            if parent_job:
                # Increment completed count (failed still counts as "done")
                parent_job.completed_batches += 1
                parent_job.stats.failed_files += 1  # Track batch as failed

                # Check if all batches are done
                if parent_job.total_batches and parent_job.completed_batches >= parent_job.total_batches:
                    # If any batch failed, mark parent as failed too
                    parent_job.status = JobStatus.FAILED
                    parent_job.completed_at = datetime.now(UTC)
                    parent_job.error = f"One or more batches failed. Last error: {error}"
                    logger.error(
                        "Parent job %s failed: batch %s failed",
                        parent_job.job_id,
                        sub_job.job_id,
                    )

                self.update_job(parent_job)
                return parent_job

        return None
