"""Singleton management for ingestion worker services.

This module provides singleton instances for shared services to avoid
circular imports between worker.py and flows modules.
"""

import os

from thoth.ingestion.job_manager import JobManager
from thoth.ingestion.task_queue import TaskQueueClient
from thoth.shared.sources.config import SourceRegistry


class _Singletons:
    """Internal singleton storage."""

    source_registry: SourceRegistry | None = None
    job_manager: JobManager | None = None
    task_queue: TaskQueueClient | None = None


def get_source_registry() -> SourceRegistry:
    """Return the global SourceRegistry singleton (creates on first call).

    Returns:
        SourceRegistry instance.
    """
    if _Singletons.source_registry is None:
        _Singletons.source_registry = SourceRegistry()
    return _Singletons.source_registry


def get_job_manager() -> JobManager:
    """Return the global JobManager singleton (creates on first call).

    Returns:
        JobManager instance.
    """
    if _Singletons.job_manager is None:
        project_id = os.getenv("GCP_PROJECT_ID")
        _Singletons.job_manager = JobManager(project_id=project_id)
    return _Singletons.job_manager


def get_task_queue() -> TaskQueueClient:
    """Return the global TaskQueueClient singleton (creates on first call).

    Returns:
        TaskQueueClient instance (reads queue config from env).
    """
    if _Singletons.task_queue is None:
        _Singletons.task_queue = TaskQueueClient()
    return _Singletons.task_queue
