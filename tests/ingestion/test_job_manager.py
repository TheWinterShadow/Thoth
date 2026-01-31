"""Tests for job manager module."""

from datetime import datetime, timezone
import sys
from unittest.mock import MagicMock, patch

from thoth.ingestion.job_manager import (
    Job,
    JobManager,
    JobStats,
    JobStatus,
)


class TestJobStatus:
    """Tests for JobStatus enum."""

    def test_status_values(self):
        """Test JobStatus enum values."""
        assert JobStatus.PENDING.value == "pending"
        assert JobStatus.RUNNING.value == "running"
        assert JobStatus.COMPLETED.value == "completed"
        assert JobStatus.FAILED.value == "failed"

    def test_status_from_string(self):
        """Test creating status from string."""
        assert JobStatus("pending") == JobStatus.PENDING
        assert JobStatus("running") == JobStatus.RUNNING
        assert JobStatus("completed") == JobStatus.COMPLETED
        assert JobStatus("failed") == JobStatus.FAILED


class TestJobStats:
    """Tests for JobStats dataclass."""

    def test_default_values(self):
        """Test default JobStats values."""
        stats = JobStats()

        assert stats.total_files == 0
        assert stats.processed_files == 0
        assert stats.failed_files == 0
        assert stats.total_chunks == 0
        assert stats.total_documents == 0

    def test_custom_values(self):
        """Test JobStats with custom values."""
        stats = JobStats(
            total_files=100,
            processed_files=95,
            failed_files=5,
            total_chunks=500,
            total_documents=1000,
        )

        assert stats.total_files == 100
        assert stats.processed_files == 95
        assert stats.failed_files == 5
        assert stats.total_chunks == 500
        assert stats.total_documents == 1000

    def test_to_dict(self):
        """Test converting stats to dictionary."""
        stats = JobStats(
            total_files=50,
            processed_files=45,
            failed_files=5,
            total_chunks=200,
            total_documents=400,
        )

        result = stats.to_dict()

        assert isinstance(result, dict)
        assert result["total_files"] == 50
        assert result["processed_files"] == 45
        assert result["failed_files"] == 5
        assert result["total_chunks"] == 200
        assert result["total_documents"] == 400

    def test_from_dict(self):
        """Test creating stats from dictionary."""
        data = {
            "total_files": 100,
            "processed_files": 90,
            "failed_files": 10,
            "total_chunks": 300,
            "total_documents": 600,
        }

        stats = JobStats.from_dict(data)

        assert stats.total_files == 100
        assert stats.processed_files == 90
        assert stats.failed_files == 10

    def test_from_dict_missing_keys(self):
        """Test from_dict with missing keys uses defaults."""
        data = {"total_files": 50}

        stats = JobStats.from_dict(data)

        assert stats.total_files == 50
        assert stats.processed_files == 0  # Default


class TestJob:
    """Tests for Job dataclass."""

    def test_job_creation(self):
        """Test creating a Job."""
        now = datetime.now(timezone.utc)
        job = Job(
            job_id="test-123",
            status=JobStatus.PENDING,
            source="handbook",
            collection_name="handbook_documents",
            started_at=now,
        )

        assert job.job_id == "test-123"
        assert job.status == JobStatus.PENDING
        assert job.source == "handbook"
        assert job.collection_name == "handbook_documents"
        assert job.started_at == now
        assert job.completed_at is None
        assert job.error is None

    def test_job_to_dict(self):
        """Test converting job to dictionary."""
        now = datetime.now(timezone.utc)
        job = Job(
            job_id="test-456",
            status=JobStatus.RUNNING,
            source="dnd",
            collection_name="dnd_documents",
            started_at=now,
            stats=JobStats(total_files=10, processed_files=5),
        )

        result = job.to_dict()

        assert isinstance(result, dict)
        assert result["job_id"] == "test-456"
        assert result["status"] == "running"
        assert result["source"] == "dnd"
        assert result["collection_name"] == "dnd_documents"
        assert "started_at" in result
        assert "stats" in result
        assert result["stats"]["total_files"] == 10

    def test_job_from_dict(self):
        """Test creating job from dictionary."""
        data = {
            "job_id": "test-789",
            "status": "completed",
            "source": "personal",
            "collection_name": "personal_documents",
            "started_at": "2024-01-15T10:00:00+00:00",
            "completed_at": "2024-01-15T10:30:00+00:00",
            "stats": {"total_files": 100, "processed_files": 100},
            "error": None,
        }

        job = Job.from_dict(data)

        assert job.job_id == "test-789"
        assert job.status == JobStatus.COMPLETED
        assert job.source == "personal"
        assert job.stats.total_files == 100

    def test_job_with_error(self):
        """Test job with error."""
        job = Job(
            job_id="error-job",
            status=JobStatus.FAILED,
            source="handbook",
            collection_name="handbook_documents",
            started_at=datetime.now(timezone.utc),
            error="Something went wrong",
        )

        assert job.status == JobStatus.FAILED
        assert job.error == "Something went wrong"


class TestJobManager:
    """Tests for JobManager class."""

    def _create_mock_firestore(self):
        """Create a mock firestore module and client."""
        mock_firestore = MagicMock()
        mock_db = MagicMock()
        mock_firestore.Client.return_value = mock_db
        return mock_firestore, mock_db

    def test_init_with_project_id(self):
        """Test initialization with project ID."""
        mock_firestore, _mock_db = self._create_mock_firestore()
        mock_google_cloud = MagicMock()
        mock_google_cloud.firestore = mock_firestore

        with patch.dict(
            sys.modules,
            {
                "google.cloud": mock_google_cloud,
                "google.cloud.firestore": mock_firestore,
            },
        ):
            manager = JobManager(project_id="test-project")
            # Access collection to trigger initialization
            _ = manager.collection

        mock_firestore.Client.assert_called_once_with(project="test-project")

    def test_init_lazy(self):
        """Test that initialization is lazy."""
        manager = JobManager(project_id="test-project")
        # DB should be None until first access
        assert manager._db is None

    def test_create_job(self):
        """Test creating a new job."""
        mock_firestore, _mock_db = self._create_mock_firestore()
        mock_google_cloud = MagicMock()
        mock_google_cloud.firestore = mock_firestore

        with patch.dict(
            sys.modules,
            {
                "google.cloud": mock_google_cloud,
                "google.cloud.firestore": mock_firestore,
            },
        ):
            manager = JobManager(project_id="test-project")
            job = manager.create_job("handbook", "handbook_documents")

        assert job.source == "handbook"
        assert job.collection_name == "handbook_documents"
        assert job.status == JobStatus.PENDING
        assert job.job_id  # Should have a UUID

    def test_get_job(self):
        """Test getting a job by ID."""
        mock_firestore, mock_db = self._create_mock_firestore()
        mock_doc = MagicMock()
        mock_doc.exists = True
        started_at = datetime.now(timezone.utc)
        mock_doc.to_dict.return_value = {
            "job_id": "test-job",
            "status": "running",
            "source": "handbook",
            "collection_name": "handbook_documents",
            "started_at": started_at.isoformat(),  # String format for serialization
            "stats": {},
        }
        mock_db.collection.return_value.document.return_value.get.return_value = mock_doc

        mock_google_cloud = MagicMock()
        mock_google_cloud.firestore = mock_firestore

        with patch.dict(
            sys.modules,
            {
                "google.cloud": mock_google_cloud,
                "google.cloud.firestore": mock_firestore,
            },
        ):
            manager = JobManager(project_id="test-project")
            job = manager.get_job("test-job")

        assert job is not None
        assert job.job_id == "test-job"
        assert job.status == JobStatus.RUNNING

    def test_get_job_not_found(self):
        """Test getting a non-existent job."""
        mock_firestore, mock_db = self._create_mock_firestore()
        mock_doc = MagicMock()
        mock_doc.exists = False
        mock_db.collection.return_value.document.return_value.get.return_value = mock_doc

        mock_google_cloud = MagicMock()
        mock_google_cloud.firestore = mock_firestore

        with patch.dict(
            sys.modules,
            {
                "google.cloud": mock_google_cloud,
                "google.cloud.firestore": mock_firestore,
            },
        ):
            manager = JobManager(project_id="test-project")
            job = manager.get_job("nonexistent")

        assert job is None

    def test_mark_running(self):
        """Test marking a job as running."""
        mock_firestore, _mock_db = self._create_mock_firestore()
        mock_google_cloud = MagicMock()
        mock_google_cloud.firestore = mock_firestore

        with patch.dict(
            sys.modules,
            {
                "google.cloud": mock_google_cloud,
                "google.cloud.firestore": mock_firestore,
            },
        ):
            manager = JobManager(project_id="test-project")
            job = Job(
                job_id="test-job",
                status=JobStatus.PENDING,
                source="handbook",
                collection_name="handbook_documents",
                started_at=datetime.now(timezone.utc),
            )

            manager.mark_running(job)

        assert job.status == JobStatus.RUNNING

    def test_mark_completed(self):
        """Test marking a job as completed."""
        mock_firestore, _mock_db = self._create_mock_firestore()
        mock_google_cloud = MagicMock()
        mock_google_cloud.firestore = mock_firestore

        with patch.dict(
            sys.modules,
            {
                "google.cloud": mock_google_cloud,
                "google.cloud.firestore": mock_firestore,
            },
        ):
            manager = JobManager(project_id="test-project")
            job = Job(
                job_id="test-job",
                status=JobStatus.RUNNING,
                source="handbook",
                collection_name="handbook_documents",
                started_at=datetime.now(timezone.utc),
            )
            stats = JobStats(total_files=100, processed_files=100)

            manager.mark_completed(job, stats)

        assert job.status == JobStatus.COMPLETED
        assert job.stats == stats
        assert job.completed_at is not None

    def test_mark_failed(self):
        """Test marking a job as failed."""
        mock_firestore, _mock_db = self._create_mock_firestore()
        mock_google_cloud = MagicMock()
        mock_google_cloud.firestore = mock_firestore

        with patch.dict(
            sys.modules,
            {
                "google.cloud": mock_google_cloud,
                "google.cloud.firestore": mock_firestore,
            },
        ):
            manager = JobManager(project_id="test-project")
            job = Job(
                job_id="test-job",
                status=JobStatus.RUNNING,
                source="handbook",
                collection_name="handbook_documents",
                started_at=datetime.now(timezone.utc),
            )

            manager.mark_failed(job, "Processing error")

        assert job.status == JobStatus.FAILED
        assert job.error == "Processing error"
        assert job.completed_at is not None

    def test_list_jobs(self):
        """Test listing jobs."""
        mock_firestore, mock_db = self._create_mock_firestore()

        # Create mock documents with proper to_dict methods
        def make_doc(job_id, status, source, collection_name):
            doc = MagicMock()
            started_at = datetime.now(timezone.utc)
            doc.to_dict.return_value = {
                "job_id": job_id,
                "status": status,
                "source": source,
                "collection_name": collection_name,
                "started_at": started_at.isoformat(),
                "stats": {},
            }
            return doc

        mock_docs = [
            make_doc("job-1", "completed", "handbook", "handbook_documents"),
            make_doc("job-2", "running", "dnd", "dnd_documents"),
        ]

        # Set up mock collection to return a chainable query
        mock_collection = MagicMock()
        mock_collection.order_by.return_value.limit.return_value.stream.return_value = mock_docs
        mock_db.collection.return_value = mock_collection

        mock_google_cloud = MagicMock()
        mock_google_cloud.firestore = mock_firestore

        with patch.dict(
            sys.modules,
            {
                "google.cloud": mock_google_cloud,
                "google.cloud.firestore": mock_firestore,
            },
        ):
            manager = JobManager(project_id="test-project")
            jobs = manager.list_jobs()

        assert len(jobs) == 2

    def test_list_jobs_with_filter(self):
        """Test listing jobs with source filter."""
        mock_firestore, mock_db = self._create_mock_firestore()

        # Set up mock collection to return a chainable query
        mock_collection = MagicMock()
        mock_query = mock_collection.where.return_value
        mock_query.where.return_value = mock_query  # Handle multiple where clauses
        mock_query.order_by.return_value.limit.return_value.stream.return_value = []
        mock_db.collection.return_value = mock_collection

        mock_google_cloud = MagicMock()
        mock_google_cloud.firestore = mock_firestore

        with patch.dict(
            sys.modules,
            {
                "google.cloud": mock_google_cloud,
                "google.cloud.firestore": mock_firestore,
            },
        ):
            manager = JobManager(project_id="test-project")
            jobs = manager.list_jobs(source="handbook", status=JobStatus.COMPLETED)

        # Verify collection was queried
        assert mock_collection.where.called
        assert len(jobs) == 0
