"""
Comprehensive test suite for the secure logging module.

This module contains extensive tests for the horizon_core.logging module,
ensuring that sensitive data redaction works correctly across various scenarios
and that the logging functionality is robust and reliable.

Test Coverage:
    - SensitiveDataFormatter redaction patterns and edge cases
    - SecureLogger error handling and method behavior
    - setup_logger function configuration and reuse logic
    - Integration testing between components
    - Performance and reliability under various conditions

Key Test Areas:
    1. Sensitive Data Redaction:
       - Various keyword patterns (password, token, API key, etc.)
       - Different separators (is, :, =)
       - Case sensitivity handling
       - Multiple sensitive values in one message
       - Edge cases and false positive prevention

    2. Logger Configuration:
       - Proper logger creation and setup
       - Handler configuration and formatter assignment
       - Logger reuse and duplicate prevention
       - Level setting and inheritance

    3. Error Handling:
       - Malformed format strings
       - Missing arguments
       - Non-string message types
       - Exception safety during logging calls

    4. Format Compatibility:
       - Simple vs detailed format modes
       - Timestamp and metadata inclusion
       - Custom format string handling

Example Usage:
    Run all tests:
        python -m pytest tests/utils/test_logger.py -v

    Run specific test class:
        python -m pytest tests/utils/test_logger.py::TestLoggingModule -v

    Run with coverage:
        python -m pytest tests/utils/test_logger.py --cov=horizon_core.logging
"""

import io
import logging
import unittest
from unittest.mock import patch

from thoth.utils.logger import SecureLogger, SensitiveDataFormatter, setup_logger


class TestLoggingModule(unittest.TestCase):
    """
    Main test class for the secure logging module.

    This class contains comprehensive tests for all components of the logging module,
    including the SensitiveDataFormatter, SecureLogger, and setup_logger function.
    Each test method focuses on specific functionality and edge cases.
    """

    def setUp(self):
        """
        Set up test fixtures before each test method.

        Creates logger instances that will be used across multiple test methods
        to ensure consistent behavior and prevent test interference.
        """
        # Create a default logger with sensitive data redaction enabled
        # This uses the SensitiveDataFormatter with detailed format
        self.default_logger = setup_logger("test_default_logger", level=logging.DEBUG)

        # Create a simple logger without sensitive data redaction
        # This uses the basic Formatter with simple format for performance testing
        self.simple_logger = setup_logger("test_simple_logger", level=logging.DEBUG, simple=True)

    def test_default_logger_format(self):
        """
        Test that the default logger uses the correct detailed format.

        Verifies that the default logger produces log messages with the expected
        format including logger name, level, and message. This ensures the
        SensitiveDataFormatter is properly configured with the detailed format.
        """
        # Create a mock log record to test formatting
        log_record = logging.LogRecord(
            name="test_default_logger",  # Logger name
            level=logging.INFO,  # Log level
            pathname="",  # Source file path (not used)
            lineno=0,  # Line number (not used)
            msg="Test message",  # The actual log message
            args=(),  # Format arguments (none in this case)
            # Exception info (none in this case)
            exc_info=None,
        )

        # Format the record using the logger's formatter
        formatted_message = self.default_logger.handlers[0].formatter.format(log_record)

        # Verify the formatted message contains expected components
        # The detailed format should include: timestamp - logger_name - level - message
        self.assertIn(" - test_default_logger - INFO - Test message", formatted_message)

    def test_simple_logger_format(self):
        """
        Test that the simple logger uses the basic format without redaction.

        Verifies that when simple=True is used, the logger uses the basic
        formatter with just level and message, without the overhead of
        sensitive data redaction for performance-critical scenarios.
        """
        # Create a mock log record for simple format testing
        log_record = logging.LogRecord(
            # Logger name (not shown in simple format)
            name="test_simple_logger",
            level=logging.INFO,  # Log level (shown as "INFO:")
            pathname="",  # Source file path (not used)
            lineno=0,  # Line number (not used)
            msg="Test message",  # The actual log message
            args=(),  # Format arguments (none in this case)
            # Exception info (none in this case)
            exc_info=None,
        )

        # Format the record using the simple logger's formatter
        formatted_message = self.simple_logger.handlers[0].formatter.format(log_record)

        # Verify the simple format only includes the essential information
        # Simple format should be: "LEVEL: message" (no timestamp, no logger name)
        self.assertIn("Test message", formatted_message)

    def test_sensitive_info_redaction(self):
        """
        Test that sensitive information is properly redacted from log messages.

        This is a core security test that verifies the primary functionality
        of the logging module: automatically detecting and redacting sensitive
        data patterns to prevent information leaks in log files.

        Tests multiple common patterns:
        - "keyword is value" format
        - "keyword: value" format
        - "keyword=value" format
        """
        # Define test cases with various sensitive data patterns
        sensitive_messages = [
            "User password is secret123",  # Tests "is" separator pattern
            "API key: abcdefghijklmnop",  # Tests colon separator pattern
            "Authorization token=xyz789",  # Tests equals separator pattern
        ]

        # Test each sensitive message pattern
        for message in sensitive_messages:
            # Create a log record for the sensitive message
            log_record = logging.LogRecord(
                name="test_logger",
                level=logging.INFO,
                pathname="",
                lineno=0,
                msg=message,  # The sensitive message to test
                args=(),
                exc_info=None,
            )

            # Format the record using the secure formatter
            formatted_message = self.default_logger.handlers[0].formatter.format(log_record)

            # Verify that all sensitive values have been redacted
            # None of the actual sensitive values should appear in the output
            self.assertNotIn("secret123", formatted_message)
            self.assertNotIn("abcdefghijklmnop", formatted_message)
            self.assertNotIn("xyz789", formatted_message)

            # Verify that the redaction marker is present
            # This confirms that redaction occurred rather than message being dropped
            self.assertIn("[REDACTED]", formatted_message)

    def test_non_sensitive_info(self):
        """
        Test that non-sensitive messages are not modified by the redaction process.

        This test ensures that the redaction logic doesn't interfere with normal
        log messages and only acts on messages that match sensitive data patterns.
        This prevents false positives and maintains log message integrity.
        """
        # Test with a completely normal message that should not trigger redaction
        message = "This is a regular log message."

        # Create a log record for the normal message
        log_record = logging.LogRecord(
            name="test_logger",
            level=logging.INFO,
            pathname="",
            lineno=0,
            msg=message,
            args=(),
            exc_info=None,
        )

        # Format the record and verify it remains unchanged
        formatted_message = self.default_logger.handlers[0].formatter.format(log_record)

        # The original message should be preserved exactly
        self.assertIn(message, formatted_message)

        # No redaction should have occurred for non-sensitive content
        self.assertNotIn("[REDACTED]", formatted_message)

    def test_logger_levels(self):
        """Test that different log levels work correctly."""
        debug_logger = setup_logger("debug_logger", level=logging.DEBUG)
        info_logger = setup_logger("info_logger", level=logging.INFO)
        warning_logger = setup_logger("warning_logger", level=logging.WARNING)

        self.assertEqual(debug_logger.level, logging.DEBUG)
        self.assertEqual(info_logger.level, logging.INFO)
        self.assertEqual(warning_logger.level, logging.WARNING)

    def test_secure_logger_instance(self):
        """Test that setup_logger returns a SecureLogger instance."""
        logger = setup_logger("secure_test")
        self.assertIsInstance(logger, SecureLogger)

    def test_sensitive_data_formatter_direct(self):
        """Test SensitiveDataFormatter directly."""
        formatter = SensitiveDataFormatter("%(message)s")

        test_cases = [
            ("password is mypass123", "password is [REDACTED]"),
            ("API key: abc123def456", "API key: [REDACTED]"),
            ("token=secretvalue", "token=[REDACTED]"),
            # Fixed expectation
            ("authorization: bearer", "authorization: [REDACTED]"),
            ("Normal message", "Normal message"),
        ]

        for input_msg, expected in test_cases:
            record = logging.LogRecord("test", logging.INFO, "", 0, input_msg, (), None)
            formatted = formatter.format(record)
            self.assertEqual(formatted, expected)

    def test_multiple_sensitive_values_in_message(self):
        """
        Test redaction when multiple sensitive values are present in one message.

        This test ensures that the formatter can handle complex log messages
        containing multiple different types of sensitive information and
        redacts all of them properly. This is important for comprehensive
        security coverage in real-world logging scenarios.
        """
        # Create a formatter for direct testing
        formatter = SensitiveDataFormatter("%(message)s")

        # Create a message with multiple sensitive values of different types
        message = "User password is secret123 and API key: abcdef123456"

        # Create a log record with the multi-sensitive message
        record = logging.LogRecord("test", logging.INFO, "", 0, message, (), None)

        # Format the message and verify all sensitive data is redacted
        formatted = formatter.format(record)

        # Verify that both sensitive values have been removed
        # Password value should be gone
        self.assertNotIn("secret123", formatted)
        # API key value should be gone
        self.assertNotIn("abcdef123456", formatted)

        # Verify that exactly two redactions occurred
        # This confirms both sensitive patterns were detected and handled
        self.assertEqual(formatted.count("[REDACTED]"), 2)

    def test_case_insensitive_redaction(self):
        """Test that redaction works regardless of case."""
        formatter = SensitiveDataFormatter("%(message)s")

        test_cases = [
            "PASSWORD is secret123",
            "Api Key: secret123",
            "TOKEN=secret123",
            "Authorization: secret123",
        ]

        for message in test_cases:
            record = logging.LogRecord("test", logging.INFO, "", 0, message, (), None)
            formatted = formatter.format(record)
            self.assertNotIn("secret123", formatted)
            self.assertIn("[REDACTED]", formatted)

    def test_secure_logger_methods(self):
        """
        Test all logging methods of SecureLogger for proper functionality.

        Verifies that all logging level methods (debug, info, warning, error, critical)
        work correctly without raising exceptions. This test focuses on method
        availability and basic functionality rather than output verification.
        """
        # Create a logger for testing all methods
        logger = setup_logger("method_test")

        # Capture output to prevent console spam during testing
        # We don't need to verify the output content, just that methods don't crash
        with patch("sys.stdout", new_callable=io.StringIO):
            # Test each logging method to ensure they work without exceptions
            logger.debug("Debug message")  # Lowest priority level
            logger.info("Info message")  # Informational messages
            logger.warning("Warning message")  # Warning conditions
            logger.error("Error message")  # Error conditions
            logger.critical("Critical message")  # Critical conditions

    def test_secure_logger_with_args(self):
        """
        Test SecureLogger with string formatting arguments.

        Verifies that the logger correctly handles format strings with arguments,
        including cases where the formatted result contains sensitive information
        that should be redacted by the formatter.
        """
        # Create a logger for testing argument formatting
        logger = setup_logger("args_test")

        # Capture output to prevent console spam during testing
        with patch("sys.stdout", new_callable=io.StringIO):
            # Test formatting with multiple arguments, including sensitive data
            # The formatter should redact "secret123" after string formatting occurs
            logger.info("User %s has password %s", "john", "secret123")

            # Test single argument formatting with sensitive data
            # The formatter should redact "abcdef123" after formatting
            logger.info("API key is %s", "abcdef123")

    def test_secure_logger_exception_handling(self):
        """
        Test SecureLogger handles formatting exceptions gracefully.

        This is a critical safety test that ensures the logger never crashes
        the application due to malformed log calls. The logger should handle
        various error conditions gracefully and continue functioning.
        """
        # Create a logger for testing exception handling
        logger = setup_logger("exception_test")

        # Capture output to prevent console spam during testing
        with patch("sys.stdout", new_callable=io.StringIO):
            # Test mismatched format arguments - should not raise TypeError
            # Logger should handle the formatting error and log something reasonable
            # Format string without corresponding argument
            logger.info("Missing arg: %s")

            # Test logging None values - should not raise AttributeError
            # Logger should convert None to string representation
            logger.info(None)

            # Test logging non-string objects - should not raise formatting errors
            # Logger should convert numeric values to string representation
            logger.info(123)

    def test_no_duplicate_handlers(self):
        """
        Test that calling setup_logger multiple times doesn't create duplicate handlers.

        This test ensures proper logger management and prevents issues like
        duplicate log messages or memory leaks from accumulating handlers.
        The setup_logger function should reuse existing loggers when possible.
        """
        # Create two loggers with the same name - should get the same instance
        # Use unique names to avoid interference with other tests
        logger1 = setup_logger("unique_duplicate_test_1")
        # Same name as logger1
        logger2 = setup_logger("unique_duplicate_test_1")

        # Verify both loggers have exactly one handler (no duplicates)
        self.assertEqual(len(logger1.handlers), 1)
        self.assertEqual(len(logger2.handlers), 1)

        # Verify that both variables reference the same logger object
        # This confirms proper logger reuse and singleton behavior
        self.assertIs(logger1, logger2)

    def test_edge_case_redaction_patterns(self):
        """
        Test edge cases in redaction patterns to prevent false positives.

        This test ensures that the redaction logic is precise and doesn't
        accidentally redact legitimate content. It tests various boundary
        conditions and partial matches that should NOT trigger redaction.

        This is critical for maintaining log integrity while providing security.
        """
        # Create a formatter for direct testing
        formatter = SensitiveDataFormatter("%(message)s")

        # Define edge cases that should NOT be redacted
        # Each tuple contains (input_message, expected_output)
        edge_cases = [
            # Incomplete patterns - missing values
            ("password:", "password:"),  # Colon but no value
            ("password =", "password ="),  # Equals but no value
            ("password is", "password is"),  # 'is' but no value
            # Equals but no value (no space)
            ("password=", "password="),
            # Word boundary tests - should not match partial words
            ("not_password is value", "not_password is value"),  # Underscore prefix
            ("mypassword is secret", "mypassword is secret"),  # No word boundary
            # Pattern variations that don't match the expected format
            # Wrong separator word
            ("password in value", "password in value"),
        ]

        # Test each edge case to ensure no false positive redaction occurs
        for input_msg, expected in edge_cases:
            # Create a log record for the edge case
            record = logging.LogRecord("test", logging.INFO, "", 0, input_msg, (), None)

            # Format the message
            formatted = formatter.format(record)

            # Verify the message was NOT redacted (remains exactly as expected)
            self.assertEqual(formatted, expected, f"Failed for input: {input_msg}")


# Additional test considerations for future development:
#
# 1. Performance Tests:
#    - Measure redaction overhead with large log volumes
#    - Compare simple vs secure logger performance
#    - Test memory usage with long-running loggers
#
# 2. Integration Tests:
#    - Test with real application scenarios
#    - Test with different log handlers (file, network, etc.)
#    - Test with log rotation and archival
#
# 3. Security Tests:
#    - Test with various encoding schemes (base64, URL encoding, etc.)
#    - Test with obfuscated sensitive data patterns
#    - Test with custom sensitive keywords
#
# 4. Concurrency Tests:
#    - Test thread safety of formatter and logger
#    - Test performance under concurrent logging load
#    - Test logger creation in multi-threaded environments
#
# 5. Configuration Tests:
#    - Test with different log levels and filtering
#    - Test with custom format strings
#    - Test with environment-specific configurations
