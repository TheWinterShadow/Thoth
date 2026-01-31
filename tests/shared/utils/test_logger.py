"""Comprehensive test suite for the structured logging module.

This module contains extensive tests for the thoth.shared.utils.logger module,
ensuring that:
- Structured JSON logging works correctly for GCP Cloud Logging
- Sensitive data redaction works across various scenarios
- JobLoggerAdapter properly adds context to all log messages
- Backward compatibility is maintained with SecureLogger

Test Coverage:
    - GCPStructuredFormatter JSON output and field population
    - SimpleFormatter text output with redaction
    - JobLoggerAdapter context injection
    - Trace context handling
    - Sensitive data redaction patterns
    - setup_logger configuration
    - Backward compatibility (SecureLogger, SensitiveDataFormatter)
"""

import io
import json
import logging
import os
import unittest
from unittest.mock import patch

from thoth.shared.utils.logger import (
    GCPStructuredFormatter,
    JobLoggerAdapter,
    SecureLogger,
    SensitiveDataFormatter,
    SimpleFormatter,
    configure_root_logger,
    extract_trace_id_from_header,
    get_job_logger,
    get_trace_context,
    set_trace_context,
    setup_logger,
)


class TestGCPStructuredFormatter(unittest.TestCase):
    """Test the GCPStructuredFormatter JSON output."""

    def setUp(self) -> None:
        """Set up test fixtures."""
        self.formatter = GCPStructuredFormatter()

    def test_basic_json_output(self) -> None:
        """Test that formatter produces valid JSON."""
        record = logging.LogRecord(
            name="test.logger",
            level=logging.INFO,
            pathname="/app/thoth/test.py",
            lineno=42,
            msg="Test message",
            args=(),
            exc_info=None,
        )
        record.funcName = "test_function"

        formatted = self.formatter.format(record)

        # Should be valid JSON
        parsed = json.loads(formatted)
        self.assertIsInstance(parsed, dict)

    def test_standard_fields(self) -> None:
        """Test that standard fields are populated correctly."""
        record = logging.LogRecord(
            name="test.logger",
            level=logging.WARNING,
            pathname="/app/thoth/module/file.py",
            lineno=100,
            msg="Warning message",
            args=(),
            exc_info=None,
        )
        record.funcName = "my_function"

        formatted = self.formatter.format(record)
        parsed = json.loads(formatted)

        # Check standard fields
        self.assertEqual(parsed["severity"], "WARNING")
        self.assertEqual(parsed["logger"], "test.logger")
        self.assertIn("Warning message", parsed["message"])
        self.assertIn("timestamp", parsed)

    def test_verbose_source_location(self) -> None:
        """Test that verbose source location fields are included."""
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="/app/thoth/ingestion/pipeline.py",
            lineno=456,
            msg="Test",
            args=(),
            exc_info=None,
        )
        record.funcName = "_process_file"

        formatted = self.formatter.format(record)
        parsed = json.loads(formatted)

        # Check verbose fields
        self.assertEqual(parsed["lineno"], 456)
        self.assertEqual(parsed["funcName"], "_process_file")
        self.assertIn("pipeline.py", parsed["filename"])
        self.assertEqual(parsed["module"], "pipeline")

    def test_gcp_source_location(self) -> None:
        """Test that GCP sourceLocation field is properly formatted."""
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="/app/thoth/ingestion/worker.py",
            lineno=123,
            msg="Test",
            args=(),
            exc_info=None,
        )
        record.funcName = "process_batch"

        formatted = self.formatter.format(record)
        parsed = json.loads(formatted)

        source_location = parsed.get("logging.googleapis.com/sourceLocation")
        self.assertIsNotNone(source_location)
        self.assertIn("thoth/ingestion/worker.py", source_location["file"])
        self.assertEqual(source_location["line"], "123")
        self.assertEqual(source_location["function"], "process_batch")

    def test_sensitive_data_redaction(self) -> None:
        """Test that sensitive data is redacted in JSON output."""
        sensitive_messages = [
            ("password is secret123", "secret123"),
            ("API key: abcdefghijklmnop", "abcdefghijklmnop"),
            ("token=xyz789", "xyz789"),
        ]

        for msg, sensitive_value in sensitive_messages:
            record = logging.LogRecord(
                name="test",
                level=logging.INFO,
                pathname="",
                lineno=0,
                msg=msg,
                args=(),
                exc_info=None,
            )

            formatted = self.formatter.format(record)
            parsed = json.loads(formatted)

            self.assertNotIn(sensitive_value, parsed["message"])
            self.assertIn("[REDACTED]", parsed["message"])

    def test_job_context_fields(self) -> None:
        """Test that job context fields are included when present."""
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="",
            lineno=0,
            msg="Processing",
            args=(),
            exc_info=None,
        )
        record.job_id = "job_abc123"
        record.source = "handbook"
        record.collection = "handbook_docs"
        record.operation = "chunking"

        formatted = self.formatter.format(record)
        parsed = json.loads(formatted)

        self.assertEqual(parsed["job_id"], "job_abc123")
        self.assertEqual(parsed["source"], "handbook")
        self.assertEqual(parsed["collection"], "handbook_docs")
        self.assertEqual(parsed["operation"], "chunking")

    def test_metrics_fields(self) -> None:
        """Test that metrics fields are included when present."""
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="",
            lineno=0,
            msg="Completed",
            args=(),
            exc_info=None,
        )
        record.files_processed = 42
        record.chunks_created = 156
        record.duration_ms = 1250

        formatted = self.formatter.format(record)
        parsed = json.loads(formatted)

        self.assertEqual(parsed["files_processed"], 42)
        self.assertEqual(parsed["chunks_created"], 156)
        self.assertEqual(parsed["duration_ms"], 1250)

    def test_gcp_labels(self) -> None:
        """Test that GCP labels are populated from job context."""
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="",
            lineno=0,
            msg="Test",
            args=(),
            exc_info=None,
        )
        record.job_id = "job_xyz"
        record.source = "dnd"

        formatted = self.formatter.format(record)
        parsed = json.loads(formatted)

        labels = parsed.get("logging.googleapis.com/labels")
        self.assertIsNotNone(labels)
        self.assertEqual(labels["job_id"], "job_xyz")
        self.assertEqual(labels["source"], "dnd")


class TestSimpleFormatter(unittest.TestCase):
    """Test the SimpleFormatter text output."""

    def setUp(self) -> None:
        """Set up test fixtures."""
        self.formatter = SimpleFormatter()

    def test_basic_format(self) -> None:
        """Test basic text formatting."""
        record = logging.LogRecord(
            name="test.logger",
            level=logging.INFO,
            pathname="/app/test.py",
            lineno=10,
            msg="Test message",
            args=(),
            exc_info=None,
        )
        record.funcName = "test_func"

        formatted = self.formatter.format(record)

        self.assertIn("test.logger", formatted)
        self.assertIn("INFO", formatted)
        self.assertIn("Test message", formatted)
        self.assertIn("test_func", formatted)
        self.assertIn("10", formatted)

    def test_sensitive_data_redaction(self) -> None:
        """Test that sensitive data is redacted in text output."""
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="",
            lineno=0,
            msg="password is secret123",
            args=(),
            exc_info=None,
        )

        formatted = self.formatter.format(record)

        self.assertNotIn("secret123", formatted)
        self.assertIn("[REDACTED]", formatted)


class TestJobLoggerAdapter(unittest.TestCase):
    """Test the JobLoggerAdapter context injection."""

    def setUp(self) -> None:
        """Set up test fixtures."""
        # Create a logger with a handler we can inspect
        self.base_logger = logging.Logger("test.job")
        self.base_logger.setLevel(logging.DEBUG)
        self.stream = io.StringIO()
        handler = logging.StreamHandler(self.stream)
        handler.setFormatter(GCPStructuredFormatter())
        self.base_logger.addHandler(handler)

    def test_context_injection(self) -> None:
        """Test that job context is injected into log messages."""
        adapter = JobLoggerAdapter(
            self.base_logger,
            job_id="job_test123",
            source="handbook",
            collection="handbook_docs",
        )

        adapter.info("Test message")

        output = self.stream.getvalue()
        parsed = json.loads(output.strip())

        self.assertEqual(parsed["job_id"], "job_test123")
        self.assertEqual(parsed["source"], "handbook")
        self.assertEqual(parsed["collection"], "handbook_docs")

    def test_extra_merge(self) -> None:
        """Test that extra fields are merged with context."""
        adapter = JobLoggerAdapter(
            self.base_logger,
            job_id="job_123",
            source="handbook",
        )

        adapter.info("Processing", extra={"file_path": "readme.md", "chunks_created": 5})

        output = self.stream.getvalue()
        parsed = json.loads(output.strip())

        # Job context should be present
        self.assertEqual(parsed["job_id"], "job_123")
        # Extra fields should also be present
        self.assertEqual(parsed.get("file_path"), "readme.md")
        self.assertEqual(parsed.get("chunks_created"), 5)

    def test_with_operation(self) -> None:
        """Test creating child logger with operation context."""
        adapter = JobLoggerAdapter(
            self.base_logger,
            job_id="job_456",
            source="dnd",
        )

        chunk_logger = adapter.with_operation("chunking")
        chunk_logger.info("Chunking file")

        output = self.stream.getvalue()
        parsed = json.loads(output.strip())

        self.assertEqual(parsed["job_id"], "job_456")
        self.assertEqual(parsed["operation"], "chunking")


class TestTraceContext(unittest.TestCase):
    """Test trace context handling for Cloud Run."""

    def test_extract_trace_id_from_header(self) -> None:
        """Test extracting trace ID from X-Cloud-Trace-Context header."""
        # Standard format
        header = "105445aa7843bc8bf206b12000100000/1;o=1"
        trace_id = extract_trace_id_from_header(header)
        self.assertEqual(trace_id, "105445aa7843bc8bf206b12000100000")

        # Without span
        header = "105445aa7843bc8bf206b12000100000"
        trace_id = extract_trace_id_from_header(header)
        self.assertEqual(trace_id, "105445aa7843bc8bf206b12000100000")

        # None
        trace_id = extract_trace_id_from_header(None)
        self.assertIsNone(trace_id)

        # Empty
        trace_id = extract_trace_id_from_header("")
        self.assertIsNone(trace_id)

    def test_set_and_get_trace_context(self) -> None:
        """Test setting and getting trace context."""
        # Clear any existing context
        set_trace_context(None)
        self.assertIsNone(get_trace_context())

        # Set context
        set_trace_context("trace123")
        self.assertEqual(get_trace_context(), "trace123")

        # Clear again
        set_trace_context(None)
        self.assertIsNone(get_trace_context())


class TestSetupLogger(unittest.TestCase):
    """Test the setup_logger function."""

    def test_creates_logger(self) -> None:
        """Test that setup_logger creates a working logger."""
        logger = setup_logger("test.setup.create")
        self.assertIsNotNone(logger)
        self.assertEqual(logger.name, "test.setup.create")

    def test_logger_level(self) -> None:
        """Test that logger level is set correctly."""
        logger = setup_logger("test.setup.level", level=logging.DEBUG)
        self.assertEqual(logger.level, logging.DEBUG)

        logger2 = setup_logger("test.setup.level2", level=logging.WARNING)
        self.assertEqual(logger2.level, logging.WARNING)

    def test_simple_mode(self) -> None:
        """Test that simple mode uses SimpleFormatter."""
        logger = setup_logger("test.setup.simple", simple=True)
        self.assertIsInstance(logger.handlers[0].formatter, SimpleFormatter)

    def test_json_mode(self) -> None:
        """Test that JSON mode uses GCPStructuredFormatter."""
        logger = setup_logger("test.setup.json", json_output=True)
        self.assertIsInstance(logger.handlers[0].formatter, GCPStructuredFormatter)

    def test_no_duplicate_handlers(self) -> None:
        """Test that calling setup_logger twice doesn't create duplicate handlers."""
        logger1 = setup_logger("test.setup.nodupe")
        handler_count1 = len(logger1.handlers)

        logger2 = setup_logger("test.setup.nodupe")
        handler_count2 = len(logger2.handlers)

        self.assertEqual(handler_count1, handler_count2)
        self.assertIs(logger1, logger2)

    @patch.dict(os.environ, {"GCS_BUCKET_NAME": "test-bucket", "GCP_PROJECT_ID": "test-project"})
    def test_auto_json_in_cloud_run(self) -> None:
        """Test that JSON output is auto-enabled in Cloud Run environment."""
        # Clear any cached logger
        logger_name = "test.setup.cloudrun"
        existing = logging.getLogger(logger_name)
        existing.handlers.clear()

        logger = setup_logger(logger_name)
        self.assertIsInstance(logger.handlers[0].formatter, GCPStructuredFormatter)


class TestGetJobLogger(unittest.TestCase):
    """Test the get_job_logger helper function."""

    def test_creates_adapter(self) -> None:
        """Test that get_job_logger creates a JobLoggerAdapter."""
        base_logger = setup_logger("test.getjob")
        job_logger = get_job_logger(base_logger, job_id="job_789", source="personal")

        self.assertIsInstance(job_logger, JobLoggerAdapter)
        self.assertEqual(job_logger.extra["job_id"], "job_789")
        self.assertEqual(job_logger.extra["source"], "personal")


class TestBackwardCompatibility(unittest.TestCase):
    """Test backward compatibility with old API."""

    def test_secure_logger_exists(self) -> None:
        """Test that SecureLogger class is still available."""
        logger = SecureLogger("test.compat.secure")
        self.assertIsInstance(logger, logging.Logger)

    def test_sensitive_data_formatter_alias(self) -> None:
        """Test that SensitiveDataFormatter is aliased to SimpleFormatter."""
        formatter = SensitiveDataFormatter()
        self.assertIsInstance(formatter, SimpleFormatter)

    def test_secure_logger_methods(self) -> None:
        """Test that SecureLogger has all standard logging methods."""
        logger = SecureLogger("test.compat.methods")
        handler = logging.StreamHandler(io.StringIO())
        logger.addHandler(handler)

        # All methods should work without errors
        logger.debug("Debug message")
        logger.info("Info message")
        logger.warning("Warning message")
        logger.error("Error message")
        logger.critical("Critical message")

    def test_secure_logger_safe_formatting(self) -> None:
        """Test that SecureLogger handles malformed format strings."""
        logger = SecureLogger("test.compat.format")
        handler = logging.StreamHandler(io.StringIO())
        logger.addHandler(handler)

        # Should not raise exceptions
        logger.info("Missing arg: %s")
        logger.info(None)
        logger.info(123)


class TestSensitiveDataRedaction(unittest.TestCase):
    """Test sensitive data redaction patterns."""

    def setUp(self) -> None:
        """Set up test fixtures."""
        self.formatter = GCPStructuredFormatter()

    def test_password_patterns(self) -> None:
        """Test various password patterns."""
        patterns = [
            ("password is secret123", "secret123"),
            ("PASSWORD: mypass", "mypass"),
            ("passwd=abc123", "abc123"),
            ("pwd is test", "test"),
        ]

        for msg, sensitive in patterns:
            record = logging.LogRecord("test", logging.INFO, "", 0, msg, (), None)
            formatted = self.formatter.format(record)
            parsed = json.loads(formatted)
            self.assertNotIn(sensitive, parsed["message"], f"Failed for: {msg}")

    def test_token_patterns(self) -> None:
        """Test various token patterns."""
        patterns = [
            ("token is abc123", "abc123"),
            ("API token: xyz789", "xyz789"),
            ("bearer=mytoken", "mytoken"),
            ("jwt: eyJhbGc", "eyJhbGc"),
        ]

        for msg, sensitive in patterns:
            record = logging.LogRecord("test", logging.INFO, "", 0, msg, (), None)
            formatted = self.formatter.format(record)
            parsed = json.loads(formatted)
            self.assertNotIn(sensitive, parsed["message"], f"Failed for: {msg}")

    def test_case_insensitive_redaction(self) -> None:
        """Test that redaction is case insensitive."""
        patterns = [
            "PASSWORD is secret",
            "Password: secret",
            "password=secret",
            "TOKEN is secret",
            "Token: secret",
        ]

        for msg in patterns:
            record = logging.LogRecord("test", logging.INFO, "", 0, msg, (), None)
            formatted = self.formatter.format(record)
            parsed = json.loads(formatted)
            self.assertNotIn("secret", parsed["message"], f"Failed for: {msg}")
            self.assertIn("[REDACTED]", parsed["message"], f"No redaction for: {msg}")

    def test_non_sensitive_not_redacted(self) -> None:
        """Test that non-sensitive data is not redacted."""
        messages = [
            "This is a regular log message",
            "Processing file readme.md",
            "Completed 42 chunks in 1.5 seconds",
            "Error: file not found",
        ]

        for msg in messages:
            record = logging.LogRecord("test", logging.INFO, "", 0, msg, (), None)
            formatted = self.formatter.format(record)
            parsed = json.loads(formatted)
            self.assertEqual(parsed["message"], msg)
            self.assertNotIn("[REDACTED]", parsed["message"])

    def test_multiple_sensitive_values(self) -> None:
        """Test redaction of multiple sensitive values in one message."""
        msg = "User password is secret123 and API key: abcdef"
        record = logging.LogRecord("test", logging.INFO, "", 0, msg, (), None)
        formatted = self.formatter.format(record)
        parsed = json.loads(formatted)

        self.assertNotIn("secret123", parsed["message"])
        self.assertNotIn("abcdef", parsed["message"])
        self.assertEqual(parsed["message"].count("[REDACTED]"), 2)


class TestConfigureRootLogger(unittest.TestCase):
    """Test the configure_root_logger function."""

    def test_configures_root_logger(self) -> None:
        """Test that configure_root_logger sets up the root logger."""
        configure_root_logger(level=logging.WARNING)
        root = logging.getLogger()
        self.assertEqual(root.level, logging.WARNING)

    def test_removes_existing_handlers(self) -> None:
        """Test that existing handlers are removed."""
        root = logging.getLogger()

        # Add some handlers
        root.addHandler(logging.StreamHandler())
        root.addHandler(logging.StreamHandler())

        configure_root_logger()

        # Should have exactly one handler now
        self.assertEqual(len(root.handlers), 1)


if __name__ == "__main__":
    unittest.main()
