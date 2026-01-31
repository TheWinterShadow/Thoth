"""Structured Logging Utilities for GCP Cloud Logging and Grafana Loki.

This module provides a structured JSON logging framework that is compatible with:
- Google Cloud Logging (Cloud Run, GKE, Cloud Functions)
- Grafana Loki
- Any JSON-aware log aggregation system

Key Features:
- Structured JSON output with consistent field schema
- GCP Cloud Logging special fields (sourceLocation, trace, labels)
- Job/request correlation via JobLoggerAdapter
- Automatic sensitive data redaction
- Verbose source location (file, line, function)
- Metrics-ready numeric fields for dashboards

Example:
    >>> from thoth.shared.utils.logger import setup_logger, get_job_logger
    >>>
    >>> # Basic usage
    >>> logger = setup_logger("myapp")
    >>> logger.info("Server started", extra={"port": 8080})
    >>>
    >>> # Job-scoped logging
    >>> job_logger = get_job_logger(logger, job_id="job_123", source="handbook")
    >>> job_logger.info("Processing file", extra={"file_path": "docs/readme.md"})
"""

from collections.abc import MutableMapping
from contextvars import ContextVar
from datetime import datetime, timezone
import logging
import os
import re
from typing import Any, ClassVar, cast

from pythonjsonlogger.json import JsonFormatter as jsonlogger_JsonFormatter

# Context variable for trace ID (extracted from Cloud Run headers)
_trace_context: ContextVar[str | None] = ContextVar("trace_context", default=None)

# GCP Project ID for trace URL construction
_gcp_project_id: ContextVar[str | None] = ContextVar("gcp_project_id", default=None)


def set_trace_context(trace_id: str | None, project_id: str | None = None) -> None:
    """Set the trace context for the current request/task.

    Call this at the start of each request handler to enable log correlation.

    Args:
        trace_id: The trace ID from X-Cloud-Trace-Context header
        project_id: GCP project ID for constructing full trace URL
    """
    _trace_context.set(trace_id)
    if project_id:
        _gcp_project_id.set(project_id)


def get_trace_context() -> str | None:
    """Get the current trace context."""
    return _trace_context.get()


def extract_trace_id_from_header(header_value: str | None) -> str | None:
    """Extract trace ID from X-Cloud-Trace-Context header.

    The header format is: TRACE_ID/SPAN_ID;o=TRACE_TRUE

    Args:
        header_value: The X-Cloud-Trace-Context header value

    Returns:
        The trace ID portion, or None if header is missing/invalid
    """
    if not header_value:
        return None
    # Extract just the trace ID (before the /)
    return header_value.split("/")[0] if "/" in header_value else header_value


class GCPStructuredFormatter(jsonlogger_JsonFormatter):
    """JSON formatter compatible with GCP Cloud Logging and Grafana Loki.

    This formatter produces structured JSON logs with:
    - Standard fields (timestamp, severity, message, logger)
    - Verbose source location (pathname, filename, lineno, funcName)
    - GCP special fields (sourceLocation, trace, labels)
    - Custom context fields (job_id, source, operation, etc.)
    - Automatic sensitive data redaction

    The output is compatible with:
    - GCP Cloud Logging (jsonPayload with special field recognition)
    - Grafana Loki (JSON parsing and label extraction)
    - Any JSON-aware log aggregation system

    Example output:
        {
            "timestamp": "2026-01-30T10:15:30.123456Z",
            "severity": "INFO",
            "message": "Processing file",
            "logger": "thoth.ingestion.pipeline",
            "pathname": "/app/thoth/ingestion/pipeline.py",
            "filename": "pipeline.py",
            "lineno": 456,
            "funcName": "_process_file",
            "module": "pipeline",
            "logging.googleapis.com/sourceLocation": {
                "file": "thoth/ingestion/pipeline.py",
                "line": "456",
                "function": "_process_file"
            },
            "job_id": "job_xyz789",
            "source": "handbook"
        }
    """

    # Keywords that indicate sensitive information
    SENSITIVE_KEYWORDS: ClassVar[list[str]] = [
        "password",
        "passwd",
        "pwd",
        "secret",
        "token",
        "apikey",
        "api_key",
        "auth",
        "authorization",
        "credential",
        "key",
        "private",
        "session",
        "cookie",
        "jwt",
        "bearer",
        "oauth",
    ]

    # Compiled regex patterns for sensitive data redaction
    _redaction_patterns: ClassVar[list[tuple[re.Pattern[str], str]]] = []

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        """Initialize the formatter with GCP-compatible settings."""
        # Use a simple format string - we'll build the JSON ourselves
        super().__init__(*args, **kwargs)

        # Compile redaction patterns once
        if not GCPStructuredFormatter._redaction_patterns:
            keywords_pattern = "|".join(self.SENSITIVE_KEYWORDS)
            GCPStructuredFormatter._redaction_patterns = [
                (
                    re.compile(rf"\b({keywords_pattern})(\s+is\s+)(\S+)", re.IGNORECASE),
                    r"\1\2[REDACTED]",
                ),
                (
                    re.compile(rf"\b({keywords_pattern})(\s*:\s+)(\S+)", re.IGNORECASE),
                    r"\1\2[REDACTED]",
                ),
                (
                    re.compile(rf"\b({keywords_pattern})(\s*=\s*)(\S+)", re.IGNORECASE),
                    r"\1\2[REDACTED]",
                ),
            ]

    def _redact_sensitive_data(self, message: str) -> str:
        """Redact sensitive data from a message string."""
        for pattern, replacement in self._redaction_patterns:
            message = pattern.sub(replacement, message)
        return message

    def add_fields(  # noqa: PLR0912
        self,
        log_record: dict[str, Any],
        record: logging.LogRecord,
        message_dict: dict[str, Any],
    ) -> None:
        """Add custom fields to the JSON log record.

        This method is called by python-json-logger to populate the log record.
        We add all our custom fields here.
        """
        super().add_fields(log_record, record, message_dict)

        # === Standard Fields ===
        log_record["timestamp"] = datetime.now(timezone.utc).isoformat()
        log_record["severity"] = record.levelname
        log_record["logger"] = record.name

        # Redact sensitive data from message
        if "message" in log_record:
            log_record["message"] = self._redact_sensitive_data(str(log_record["message"]))

        # === Verbose Source Location ===
        log_record["pathname"] = record.pathname
        log_record["filename"] = record.filename
        log_record["lineno"] = record.lineno
        log_record["funcName"] = record.funcName
        log_record["module"] = record.module

        # === GCP Special Fields ===
        # sourceLocation - makes logs clickable in GCP Console
        # Use relative path for cleaner display
        relative_path = record.pathname
        if "/thoth/" in relative_path:
            relative_path = "thoth/" + relative_path.split("/thoth/", 1)[1]

        log_record["logging.googleapis.com/sourceLocation"] = {
            "file": relative_path,
            "line": str(record.lineno),
            "function": record.funcName,
        }

        # Trace correlation
        trace_id = get_trace_context()
        project_id = _gcp_project_id.get() or os.getenv("GCP_PROJECT_ID")
        if trace_id and project_id:
            log_record["logging.googleapis.com/trace"] = f"projects/{project_id}/traces/{trace_id}"

        # === Job Context Fields (from extra) ===
        # These are added via extra={} or JobLoggerAdapter
        context_fields = [
            "job_id",
            "source",
            "collection",
            "operation",
            "batch_id",
            "request_id",
        ]
        for field in context_fields:
            if hasattr(record, field):
                value = getattr(record, field)
                if value is not None:
                    log_record[field] = value

        # === Metrics Fields (from extra) ===
        metric_fields = [
            "files_processed",
            "chunks_created",
            "duration_ms",
            "total_files",
            "successful",
            "failed",
            "documents_count",
        ]
        for field in metric_fields:
            if hasattr(record, field):
                value = getattr(record, field)
                if value is not None:
                    log_record[field] = value

        # === Error Context (from extra) ===
        error_fields = ["error_type", "error_message", "file_path", "stack_trace"]
        for field in error_fields:
            if hasattr(record, field):
                value = getattr(record, field)
                if value is not None:
                    log_record[field] = self._redact_sensitive_data(str(value)) if isinstance(value, str) else value

        # === GCP Labels (for filtering) ===
        # Build labels from job context
        labels: dict[str, str] = {}
        if hasattr(record, "job_id") and record.job_id:
            labels["job_id"] = str(record.job_id)
        if hasattr(record, "source") and record.source:
            labels["source"] = str(record.source)
        if hasattr(record, "operation") and record.operation:
            labels["operation"] = str(record.operation)

        if labels:
            log_record["logging.googleapis.com/labels"] = labels

        # === Process/Thread Info ===
        log_record["process"] = record.process
        log_record["processName"] = record.processName
        log_record["thread"] = record.thread
        log_record["threadName"] = record.threadName

        # Remove None values to keep logs clean
        keys_to_remove = [k for k, v in log_record.items() if v is None]
        for key in keys_to_remove:
            del log_record[key]


class SimpleFormatter(logging.Formatter):
    """Simple text formatter for local development/debugging.

    Uses a human-readable format without JSON structure.
    Still includes sensitive data redaction.
    """

    # Same sensitive keywords as GCPStructuredFormatter
    SENSITIVE_KEYWORDS: ClassVar[list[str]] = GCPStructuredFormatter.SENSITIVE_KEYWORDS

    def __init__(self, fmt: str | None = None, **kwargs: Any) -> None:
        """Initialize with default format if not provided."""
        if fmt is None:
            fmt = "%(asctime)s - %(name)s - %(levelname)s - %(funcName)s:%(lineno)d - %(message)s"
        super().__init__(fmt, **kwargs)

        # Compile redaction patterns
        self._patterns: list[tuple[re.Pattern[str], str]] = []
        keywords_pattern = "|".join(self.SENSITIVE_KEYWORDS)
        self._patterns = [
            (
                re.compile(rf"\b({keywords_pattern})(\s+is\s+)(\S+)", re.IGNORECASE),
                r"\1\2[REDACTED]",
            ),
            (
                re.compile(rf"\b({keywords_pattern})(\s*:\s+)(\S+)", re.IGNORECASE),
                r"\1\2[REDACTED]",
            ),
            (
                re.compile(rf"\b({keywords_pattern})(\s*=\s*)(\S+)", re.IGNORECASE),
                r"\1\2[REDACTED]",
            ),
        ]

    def format(self, record: logging.LogRecord) -> str:
        """Format the record with sensitive data redaction."""
        formatted = super().format(record)
        for pattern, replacement in self._patterns:
            formatted = pattern.sub(replacement, formatted)
        return formatted


class JobLoggerAdapter(logging.LoggerAdapter):
    """Logger adapter that automatically includes job context in all log messages.

    This adapter enriches log messages with job-specific context like job_id,
    source, and collection. Use this when processing a specific job to ensure
    all logs can be correlated.

    Example:
        >>> base_logger = setup_logger("thoth.worker")
        >>> job_logger = JobLoggerAdapter(base_logger, job_id="job_123", source="handbook")
        >>> job_logger.info("Processing started")
        >>> job_logger.info("File processed", extra={"file_path": "readme.md"})
    """

    def __init__(
        self,
        logger: logging.Logger,
        job_id: str,
        source: str | None = None,
        collection: str | None = None,
        **extra_context: Any,
    ) -> None:
        """Initialize the job logger adapter.

        Args:
            logger: The base logger to wrap
            job_id: Unique identifier for the job/run
            source: Source being processed (e.g., "handbook", "dnd")
            collection: Collection name being used
            **extra_context: Additional context to include in all logs
        """
        context = {
            "job_id": job_id,
            "source": source,
            "collection": collection,
            **extra_context,
        }
        # Remove None values
        context = {k: v for k, v in context.items() if v is not None}
        super().__init__(logger, context)

    def process(self, msg: str, kwargs: MutableMapping[str, Any]) -> tuple[str, MutableMapping[str, Any]]:
        """Process the log message to include job context.

        Args:
            msg: The log message
            kwargs: Keyword arguments for the log call

        Returns:
            Tuple of (message, kwargs) with context added to extra
        """
        # Merge our context into extra
        extra = kwargs.get("extra", {})
        if self.extra:
            extra.update(self.extra)
        kwargs["extra"] = extra
        return msg, kwargs

    def with_operation(self, operation: str) -> "JobLoggerAdapter":
        """Create a child logger for a specific operation.

        Args:
            operation: The operation name (e.g., "chunking", "embedding", "storing")

        Returns:
            A new JobLoggerAdapter with the operation context added
        """
        current_extra = self.extra or {}
        return JobLoggerAdapter(
            self.logger,
            job_id=cast("str", current_extra.get("job_id", "unknown")),
            source=cast("str | None", current_extra.get("source")),
            collection=cast("str | None", current_extra.get("collection")),
            operation=operation,
        )


# Legacy alias for backward compatibility
class SecureLogger(logging.Logger):
    """Legacy SecureLogger class for backward compatibility.

    New code should use setup_logger() which returns a standard Logger
    with GCPStructuredFormatter attached.

    This class is maintained for backward compatibility with existing code
    that checks isinstance(logger, SecureLogger).
    """

    SENSITIVE_KEYWORDS: ClassVar[list[str]] = GCPStructuredFormatter.SENSITIVE_KEYWORDS

    def __init__(self, name: str, level: int = logging.NOTSET) -> None:
        """Initialize the SecureLogger."""
        super().__init__(name, level)

    def _safe_format(self, msg: Any, args: tuple[Any, ...]) -> str:
        """Safely format a message with arguments."""
        try:
            return msg % args if args and isinstance(msg, str) else str(msg)
        except (TypeError, ValueError):
            return str(msg)

    def debug(self, msg: Any, *args: Any, **kwargs: Any) -> None:
        """Log a debug message with safe formatting."""
        super().debug(self._safe_format(msg, args), **kwargs)

    def info(self, msg: Any, *args: Any, **kwargs: Any) -> None:
        """Log an info message with safe formatting."""
        super().info(self._safe_format(msg, args), **kwargs)

    def warning(self, msg: Any, *args: Any, **kwargs: Any) -> None:
        """Log a warning message with safe formatting."""
        super().warning(self._safe_format(msg, args), **kwargs)

    def error(self, msg: Any, *args: Any, **kwargs: Any) -> None:
        """Log an error message with safe formatting."""
        super().error(self._safe_format(msg, args), **kwargs)

    def critical(self, msg: Any, *args: Any, **kwargs: Any) -> None:
        """Log a critical message with safe formatting."""
        super().critical(self._safe_format(msg, args), **kwargs)


# Legacy alias
SensitiveDataFormatter = SimpleFormatter


def setup_logger(
    name: str,
    level: int = logging.INFO,
    simple: bool = False,
    json_output: bool | None = None,
) -> logging.Logger:
    """Create and configure a logger with structured JSON output.

    This function creates a logger that outputs structured JSON logs compatible
    with GCP Cloud Logging and Grafana Loki. By default, it auto-detects whether
    to use JSON output based on the environment.

    Args:
        name: Name of the logger (typically __name__)
        level: Logging level (default: INFO)
        simple: If True, use simple text format instead of JSON (for local dev)
        json_output: Explicit control over JSON output. If None, auto-detects:
                    - True in Cloud Run (GCS_BUCKET_NAME set)
                    - True if LOG_FORMAT=json
                    - False otherwise (local development)

    Returns:
        Configured logger instance

    Example:
        >>> logger = setup_logger(__name__)
        >>> logger.info("Server started", extra={"port": 8080})

        >>> # With job context
        >>> logger.info("Processing", extra={"job_id": "abc123", "source": "handbook"})
    """
    # Check if logger already exists and is configured
    existing_logger = logging.getLogger(name)
    if existing_logger.handlers:
        # Logger already configured, just update level if different
        if existing_logger.level != level:
            existing_logger.setLevel(level)
        return existing_logger

    # Auto-detect JSON output mode
    if json_output is None:
        # Use JSON in Cloud Run or if explicitly requested
        in_cloud_run = bool(os.getenv("GCS_BUCKET_NAME") and os.getenv("GCP_PROJECT_ID"))
        explicit_json = os.getenv("LOG_FORMAT", "").lower() == "json"
        json_output = in_cloud_run or explicit_json

    # For backward compatibility, simple=True forces text output
    if simple:
        json_output = False

    # Create logger (use SecureLogger for backward compatibility checks)
    logger = SecureLogger(name, level)

    # Create handler
    handler = logging.StreamHandler()

    # Choose formatter based on output mode
    formatter = GCPStructuredFormatter() if json_output else SimpleFormatter()

    handler.setFormatter(formatter)
    logger.addHandler(handler)

    # Register in logger manager
    logging.Logger.manager.loggerDict[name] = logger

    return logger


def get_job_logger(
    base_logger: logging.Logger,
    job_id: str,
    source: str | None = None,
    collection: str | None = None,
    **extra_context: Any,
) -> JobLoggerAdapter:
    """Create a job-scoped logger adapter.

    This is the recommended way to create loggers for job processing.
    All log messages will automatically include the job context.

    Args:
        base_logger: The base logger (from setup_logger)
        job_id: Unique identifier for the job
        source: Source being processed (e.g., "handbook")
        collection: Collection name
        **extra_context: Additional context fields

    Returns:
        JobLoggerAdapter with job context

    Example:
        >>> logger = setup_logger("thoth.worker")
        >>> job_logger = get_job_logger(logger, job_id="job_123", source="handbook")
        >>> job_logger.info("Starting ingestion")
        >>> job_logger.info("Processed file", extra={"file_path": "readme.md", "chunks_created": 15})
    """
    return JobLoggerAdapter(
        base_logger,
        job_id=job_id,
        source=source,
        collection=collection,
        **extra_context,
    )


def configure_root_logger(level: int = logging.INFO, json_output: bool | None = None) -> None:
    """Configure the root logger for the application.

    Call this once at application startup to configure global logging behavior.

    Args:
        level: Root logging level
        json_output: Whether to use JSON output (auto-detects if None)
    """
    root_logger = logging.getLogger()
    root_logger.setLevel(level)

    # Remove existing handlers
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)

    # Auto-detect JSON output mode
    if json_output is None:
        in_cloud_run = bool(os.getenv("GCS_BUCKET_NAME") and os.getenv("GCP_PROJECT_ID"))
        explicit_json = os.getenv("LOG_FORMAT", "").lower() == "json"
        json_output = in_cloud_run or explicit_json

    # Add new handler
    handler = logging.StreamHandler()
    if json_output:
        handler.setFormatter(GCPStructuredFormatter())
    else:
        handler.setFormatter(SimpleFormatter())

    root_logger.addHandler(handler)
