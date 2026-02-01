"""Cloud Tasks client for batch ingestion processing.

This module provides a client for enqueueing ingestion batches to Cloud Tasks,
enabling parallel processing of large document collections.
"""

from dataclasses import dataclass
import json
import os
from typing import Any

from google.cloud import tasks_v2
from google.protobuf import timestamp_pb2

from thoth.shared.utils.logger import setup_logger

logger = setup_logger(__name__)


@dataclass
class BatchTask:
    """Represents a batch processing task."""

    job_id: str
    batch_id: str
    start_index: int
    end_index: int
    collection_name: str
    source: str
    file_list: list[str] | None = None  # Optional pre-computed file list


class TaskQueueClient:
    """Client for enqueueing tasks to Cloud Tasks."""

    def __init__(
        self,
        project_id: str | None = None,
        location: str | None = None,
        queue_name: str | None = None,
        service_url: str | None = None,
        service_account_email: str | None = None,
    ):
        """Initialize the Cloud Tasks client.

        Args:
            project_id: GCP project ID (default: from GCP_PROJECT_ID env)
            location: Cloud Tasks location/region (default: from CLOUD_TASKS_LOCATION env)
            queue_name: Cloud Tasks queue name (default: from CLOUD_TASKS_QUEUE env)
            service_url: Cloud Run service URL for callbacks (default: from CLOUD_RUN_SERVICE_URL env)
            service_account_email: Service account for OIDC auth (default: from SERVICE_ACCOUNT_EMAIL env)
        """
        self.project_id = project_id or os.getenv("GCP_PROJECT_ID")
        self.location = location or os.getenv("CLOUD_TASKS_LOCATION", "us-central1")
        self.queue_name = queue_name or os.getenv("CLOUD_TASKS_QUEUE")
        self.service_url = service_url or os.getenv("CLOUD_RUN_SERVICE_URL")
        self.service_account_email = service_account_email or os.getenv("SERVICE_ACCOUNT_EMAIL")

        if not all([self.project_id, self.queue_name, self.service_url]):
            logger.warning(
                "Cloud Tasks not fully configured. Missing: project_id=%s, queue_name=%s, service_url=%s",
                bool(self.project_id),
                bool(self.queue_name),
                bool(self.service_url),
            )

        self._client: tasks_v2.CloudTasksClient | None = None

    @property
    def client(self) -> tasks_v2.CloudTasksClient:
        """Lazy-initialize the Cloud Tasks client."""
        if self._client is None:
            self._client = tasks_v2.CloudTasksClient()
        return self._client

    @property
    def queue_path(self) -> str:
        """Get the full queue path."""
        if not self.project_id or not self.location or not self.queue_name:
            msg = "Cloud Tasks not configured: missing project_id, location, or queue_name"
            raise ValueError(msg)
        return self.client.queue_path(self.project_id, self.location, self.queue_name)

    def is_configured(self) -> bool:
        """Check if Cloud Tasks is properly configured."""
        return all([self.project_id, self.queue_name, self.service_url])

    def enqueue_batch(
        self,
        batch: BatchTask,
        delay_seconds: int = 0,
    ) -> str | None:
        """Enqueue a batch processing task.

        Args:
            batch: BatchTask with batch details
            delay_seconds: Optional delay before task execution

        Returns:
            Task name if successful, None if failed
        """
        if not self.is_configured():
            logger.error("Cloud Tasks not configured, cannot enqueue batch")
            return None

        try:
            # Build the request payload
            payload = {
                "job_id": batch.job_id,
                "batch_id": batch.batch_id,
                "start_index": batch.start_index,
                "end_index": batch.end_index,
                "collection_name": batch.collection_name,
                "source": batch.source,
            }

            # Include file list if provided (for smaller batches)
            if batch.file_list is not None:
                payload["file_list"] = batch.file_list

            # Build the HTTP request
            if not self.service_url:
                logger.error("service_url is not configured")
                return None
            url = f"{self.service_url.rstrip('/')}/ingest-batch"

            task: dict[str, Any] = {
                "http_request": {
                    "http_method": tasks_v2.HttpMethod.POST,
                    "url": url,
                    "headers": {"Content-Type": "application/json"},
                    "body": json.dumps(payload).encode(),
                }
            }

            # Add OIDC token for authentication
            if self.service_account_email:
                task["http_request"]["oidc_token"] = {
                    "service_account_email": self.service_account_email,
                    "audience": self.service_url,
                }

            # Add schedule time if delay specified
            if delay_seconds > 0:
                schedule_time = timestamp_pb2.Timestamp()
                schedule_time.FromSeconds(int(timestamp_pb2.Timestamp().GetCurrentTime().seconds) + delay_seconds)
                task["schedule_time"] = schedule_time

            # Create the task
            response = self.client.create_task(request={"parent": self.queue_path, "task": task})

            logger.info(
                "Enqueued batch task",
                extra={
                    "task_name": response.name,
                    "batch_id": batch.batch_id,
                    "start_index": batch.start_index,
                    "end_index": batch.end_index,
                },
            )

            return response.name

        except Exception as e:
            logger.exception(
                "Failed to enqueue batch task",
                extra={
                    "batch_id": batch.batch_id,
                    "error": str(e),
                },
            )
            return None

    def enqueue_batches(
        self,
        job_id: str,
        file_list: list[str],
        collection_name: str,
        source: str,
        batch_size: int = 100,
    ) -> dict[str, Any]:
        """Split file list into batches and enqueue all.

        Args:
            job_id: Job ID for tracking
            file_list: List of file paths to process
            collection_name: Target ChromaDB collection
            source: Source name (handbook, dnd, personal)
            batch_size: Number of files per batch

        Returns:
            Dictionary with enqueueing results
        """
        total_files = len(file_list)
        num_batches = (total_files + batch_size - 1) // batch_size

        logger.info(
            "Enqueueing %d batches for %d files",
            num_batches,
            total_files,
            extra={
                "job_id": job_id,
                "total_files": total_files,
                "batch_size": batch_size,
                "num_batches": num_batches,
            },
        )

        enqueued = 0
        failed = 0
        task_names = []

        for i in range(num_batches):
            start_index = i * batch_size
            end_index = min((i + 1) * batch_size, total_files)
            batch_id = f"{job_id}_{i:04d}"

            batch = BatchTask(
                job_id=job_id,
                batch_id=batch_id,
                start_index=start_index,
                end_index=end_index,
                collection_name=collection_name,
                source=source,
                # Pass only the slice for this batch (already sliced)
                file_list=file_list[start_index:end_index],
            )

            task_name = self.enqueue_batch(batch)
            if task_name:
                enqueued += 1
                task_names.append(task_name)
            else:
                failed += 1

        result = {
            "total_files": total_files,
            "batch_size": batch_size,
            "num_batches": num_batches,
            "enqueued": enqueued,
            "failed": failed,
            "task_names": task_names,
        }

        logger.info(
            "Batch enqueueing complete",
            extra={"job_id": job_id, **result},
        )

        return result
