"""Job manager for tracking ingestion jobs using Firestore.

This module provides job tracking and status management for ingestion
operations using Google Cloud Firestore as the backend.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
import os
from typing import Any
import uuid

from thoth.shared.utils.logger import setup_logger

logger = setup_logger(__name__)


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
        job_id: Unique job identifier (UUID)
        status: Current job status
        source: Source identifier (e.g., 'handbook', 'dnd')
        collection_name: Target ChromaDB collection
        started_at: Job start timestamp
        completed_at: Job completion timestamp (if finished)
        stats: Job statistics
        error: Error message (if failed)
    """

    job_id: str
    status: JobStatus
    source: str
    collection_name: str
    started_at: datetime
    completed_at: datetime | None = None
    stats: JobStats = field(default_factory=JobStats)
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert job to Firestore-compatible dictionary."""
        return {
            "job_id": self.job_id,
            "status": self.status.value,
            "source": self.source,
            "collection_name": self.collection_name,
            "started_at": self.started_at.isoformat(),
            "completed_at": (self.completed_at.isoformat() if self.completed_at else None),
            "stats": self.stats.to_dict(),
            "error": self.error,
        }

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
        )

    @property
    def is_finished(self) -> bool:
        """Check if job has finished (completed or failed)."""
        return self.status in (JobStatus.COMPLETED, JobStatus.FAILED)

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
                self._collection = self._db.collection(self.COLLECTION_NAME)  # type: ignore[attr-defined]
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

    def create_job(self, source: str, collection_name: str) -> Job:
        """Create a new job and persist to Firestore.

        Args:
            source: Source identifier (e.g., 'handbook', 'dnd')
            collection_name: Target ChromaDB collection

        Returns:
            Created Job instance
        """
        job = Job(
            job_id=str(uuid.uuid4()),
            status=JobStatus.PENDING,
            source=source,
            collection_name=collection_name,
            started_at=datetime.now(timezone.utc),
        )

        self.collection.document(job.job_id).set(job.to_dict())
        logger.info("Created job %s for source '%s'", job.job_id, source)
        return job

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
        job.completed_at = datetime.now(timezone.utc)
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
        job.completed_at = datetime.now(timezone.utc)
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
        cutoff = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
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
