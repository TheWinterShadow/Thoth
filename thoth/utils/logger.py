"""Secure Logging Utilities - Standardized logging with automatic sensitive data redaction.

This module provides a secure logging framework for HorizonSec tools that automatically
detects and redacts sensitive information from log messages to prevent data leaks.

The module includes:
- SecureLogger: A logger class that extends Python's standard logging.Logger
- SensitiveDataFormatter: A formatter that redacts sensitive patterns from log messages
- setup_logger: A convenience function to create pre-configured secure loggers

Key Features:
- Automatic detection of sensitive patterns (passwords, API keys, tokens, etc.)
- Case-insensitive pattern matching with word boundary detection
- Graceful error handling for malformed log messages
- Support for both detailed and simple log formats
- Prevention of duplicate handlers when creating multiple loggers with the same name

Security Considerations:
- All sensitive data is replaced with "[REDACTED]" before being written to logs
- Redaction happens at the formatter level, ensuring no sensitive data reaches log handlers
- Word boundary matching prevents false positives on partial keyword matches
- Multiple sensitive values in a single message are all properly redacted

Example:
    >>> from horizon_core import setup_logger
    >>> import logging
    >>>
    >>> logger = setup_logger("myapp", level=logging.INFO)
    >>> logger.info("User password is secret123")  # Logs: "User password is [REDACTED]"
    >>> logger.info("API key: abc123def")          # Logs: "API key: [REDACTED]"
"""

from logging import INFO, NOTSET, Formatter, Logger, LogRecord, StreamHandler, getLogger
import re
from typing import Any, ClassVar

# Default log format - includes timestamp, logger name, level, and message
DEFAULT_FORMAT = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"

# Simple log format - just level and message (useful for console output)
SIMPLE_FORMAT = "%(levelname)s: %(message)s"


class SensitiveDataFormatter(Formatter):
    """Custom formatter that automatically redacts sensitive information from log messages.

    This formatter extends the standard logging.Formatter to provide automatic detection
    and redaction of sensitive data patterns before log messages are written to any handler.

    The formatter uses regex patterns with word boundaries to ensure accurate detection
    while avoiding false positives. It supports case-insensitive matching and handles
    multiple common patterns for sensitive data.

    Attributes:
        SENSITIVE_KEYWORDS (list): List of keywords that are considered sensitive.
                                 These keywords trigger redaction when found in specific patterns.

    Supported Patterns:
        - "keyword is value" format: "password is secret123" → "password is [REDACTED]"
        - "keyword: value" format: "API key: abc123" → "API key: [REDACTED]"
        - "keyword=value" format: "token=xyz789" → "token=[REDACTED]"

    Example:
        >>> formatter = SensitiveDataFormatter("%(levelname)s: %(message)s")
        >>> record = logging.LogRecord("test", logging.INFO, "", 0, "password is secret", (), None)
        >>> formatted = formatter.format(record)
        >>> print(formatted)  # "INFO: password is [REDACTED]"
    """

    # Keywords that indicate sensitive information
    # These are matched with word boundaries to prevent false positives
    SENSITIVE_KEYWORDS: ClassVar[list[str]] = [
        "password",  # User passwords
        "passwd",  # Alternative password spelling
        "pwd",  # Short form of password
        "secret",  # Generic secrets
        "token",  # Authentication tokens
        "apikey",  # API keys (single word)
        "api_key",  # API keys (underscore separated)
        "auth",  # Authentication data
        "authorization",  # Authorization headers/data
        "credential",  # Generic credentials
        "key",  # Generic keys (private keys, etc.)
        "private",  # Private keys/data
        "session",  # Session identifiers
        "cookie",  # HTTP cookies
        "jwt",  # JSON Web Tokens
        "bearer",  # Bearer tokens
        "oauth",  # OAuth tokens/data
    ]

    def format(self, record: LogRecord) -> str:
        """Format the log record and redact any sensitive information.

        This method first formats the log record using the parent formatter,
        then applies regex patterns to detect and redact sensitive data.

        Args:
            record (logging.LogRecord): The log record to format and redact.

        Returns:
            str: The formatted log message with sensitive data redacted.

        Note:
            Redaction is performed using regex substitution with case-insensitive matching.
            Multiple sensitive values in the same message will all be redacted.
        """
        # First, format the record using the standard formatter
        # This gives us the complete log message with timestamp, level, etc.
        formatted = super().format(record)

        # Define redaction patterns for different sensitive data formats
        # Each pattern captures: (keyword)(separator)(value) and replaces value with [REDACTED]
        patterns = [
            # Pattern 1: "keyword is value" (e.g., "User password is secret123")
            # \b ensures word boundary, \s+ matches one or more spaces
            (
                r"\b({})(\s+is\s+)(\S+)".format("|".join(self.SENSITIVE_KEYWORDS)),
                r"\1\2[REDACTED]",
            ),
            # Pattern 2: "keyword: value" (e.g., "API key: abcdefghijklmnop")
            # \s* allows optional spaces around the colon
            (
                r"\b({})(\s*:\s+)(\S+)".format("|".join(self.SENSITIVE_KEYWORDS)),
                r"\1\2[REDACTED]",
            ),
            # Pattern 3: "keyword=value" (e.g., "Authorization token=xyz789")
            # \s* allows optional spaces around the equals sign
            (
                r"\b({})(\s*=\s*)(\S+)".format("|".join(self.SENSITIVE_KEYWORDS)),
                r"\1\2[REDACTED]",
            ),
        ]

        # Apply each redaction pattern to the formatted message
        # Use IGNORECASE flag to catch variations in capitalization
        for pattern, replacement in patterns:
            formatted = re.sub(pattern, replacement, formatted, flags=re.IGNORECASE)

        return formatted


def setup_logger(name: str, level: int = INFO, simple: bool = False) -> Logger:
    """Creates and configures a secure logger with automatic sensitive data redaction.

    This function is the main entry point for creating secure loggers in the application.
    It handles logger reuse, prevents duplicate handlers, and configures appropriate
    formatters based on the security requirements.

    Args:
        name (str): Name of the logger. Should be unique within the application.
                   Common practice is to use __name__ from the calling module.
        level (int): Logging level threshold. Only messages at or above this level
                    will be processed. Defaults to logging.INFO.
                    Common values: logging.DEBUG, logging.INFO, logging.WARNING,
                    logging.ERROR, logging.CRITICAL
        simple (bool): If True, uses a simple format with just level and message.
                      If False (default), uses detailed format with timestamp,
                      logger name, level, and message. Simple format does NOT
                      include sensitive data redaction.

    Returns:
        logging.Logger: A configured SecureLogger instance with automatic
                       sensitive data redaction (unless simple=True).

    Note:
        - If a logger with the same name already exists and is a SecureLogger,
          it will be returned without modification
        - When simple=True, sensitive data redaction is NOT applied for performance
        - The logger uses StreamHandler to output to stderr by default

    Example:
        >>> logger = setup_logger("myapp", level=logging.DEBUG)
        >>> logger.info("Database password is secret123")  # Redacted output
        >>>
        >>> simple_logger = setup_logger("console", simple=True)
        >>> simple_logger.info("Quick message")  # No redaction, faster output
    """
    # Check if a logger with this name already exists and is properly configured
    # This prevents creating duplicate handlers and maintains logger singleton behavior
    existing_logger = getLogger(name)
    if existing_logger.handlers and isinstance(existing_logger, SecureLogger):
        return existing_logger

    # Clear any existing handlers to prevent duplicate log messages
    # This ensures clean state when reconfiguring loggers
    existing_logger.handlers.clear()

    # Create a new SecureLogger instance with the specified name
    # SecureLogger extends Python's Logger with security-aware methods
    logger = SecureLogger(name)
    logger.setLevel(level)

    # Create a console handler for output to stderr
    handler = StreamHandler()

    # Configure formatter based on security requirements
    # Simple format: no sensitive data redaction for performance
    # Secure format: includes automatic sensitive data redaction
    formatter = Formatter(SIMPLE_FORMAT) if simple else SensitiveDataFormatter(DEFAULT_FORMAT)

    # Attach formatter to handler and handler to logger
    handler.setFormatter(formatter)
    logger.addHandler(handler)

    # Register the logger in Python's logger registry
    # This ensures proper logger hierarchy and name-based retrieval
    Logger.manager.loggerDict[name] = logger

    return logger


class SecureLogger(Logger):
    """A security-enhanced logger that provides safe handling of log messages.

    SecureLogger extends Python's standard Logger class to provide additional
    safety measures for log message processing. While the actual sensitive data
    redaction is handled by SensitiveDataFormatter, this logger provides
    robust error handling to prevent logging failures from crashing applications.

    Key Features:
        - Graceful handling of malformed log messages
        - Safe string formatting with automatic fallbacks
        - Prevention of exceptions during log message processing
        - Compatibility with all standard logging methods

    The logger handles various edge cases:
        - Mismatched format strings and arguments
        - Non-string message objects
        - None values and other unexpected types
        - Encoding issues and special characters

    Attributes:
        SENSITIVE_KEYWORDS (list): Legacy list of sensitive keywords.
                                 Note: This is kept for backward compatibility
                                 but actual redaction is handled by the formatter.

    Example:
        >>> logger = SecureLogger("myapp")
        >>> logger.info("Normal message")  # Works normally
        >>> logger.info("Message with %s", "argument")  # Safe formatting
        >>> logger.info(None)  # Gracefully handles None
        >>> logger.info("Missing arg: %s")  # Won't crash on missing args
    """

    # Legacy sensitive keywords list - kept for backward compatibility
    # Note: Actual sensitive data redaction is now handled by SensitiveDataFormatter
    SENSITIVE_KEYWORDS: ClassVar[list[str]] = [
        "password",  # User passwords
        "passwd",  # Alternative password spelling
        "pwd",  # Short form of password
        "secret",  # Generic secrets
        "token",  # Authentication tokens
        "apikey",  # API keys (single word)
        "api_key",  # API keys (underscore separated)
        "auth",  # Authentication data
        "authorization",  # Authorization headers/data
        "credential",  # Generic credentials
        "key",  # Generic keys (private keys, etc.)
        "private",  # Private keys/data
        "session",  # Session identifiers
        "cookie",  # HTTP cookies
        "jwt",  # JSON Web Tokens
        "bearer",  # Bearer tokens
        "oauth",  # OAuth tokens/data
    ]

    def __init__(self, name: str, level: int = NOTSET) -> None:
        """Initialize the SecureLogger with the specified name and level.

        Args:
            name (str): Name of the logger, typically the module name.
            level (int): Minimum logging level. Defaults to NOTSET (inherits from parent).
        """
        super().__init__(name, level)

    def _redact(self, message: str) -> str:
        """Legacy method for redacting sensitive information from messages.

        Note: This method is maintained for backward compatibility but is no longer
        used in the current implementation. Sensitive data redaction is now handled
        by the SensitiveDataFormatter at the formatter level, which is more efficient
        and provides better coverage.

        Args:
            message (str): The message to potentially redact.

        Returns:
            str: The message unchanged (redaction now happens at formatter level).
        """
        # Redaction now happens at the formatter level for better performance
        # and more comprehensive pattern matching
        return message

    def debug(self, msg: Any, *args: Any, **kwargs: Any) -> None:
        """Log a debug message with safe formatting and error handling.

        Args:
            msg: The message to log. Can be a string, format string, or any object.
            *args: Arguments for string formatting if msg is a format string.
            **kwargs: Additional keyword arguments passed to the parent logger.

        Note:
            If string formatting fails, the message is converted to string safely.
            This prevents logging calls from raising exceptions in production code.
        """
        try:
            # Attempt string formatting if args are provided and msg is a string
            formatted = msg % args if args and isinstance(msg, str) else msg
        except (TypeError, ValueError):
            # Handle formatting errors gracefully - convert to string representation
            formatted = str(msg)
        super().debug(str(formatted), **kwargs)

    def info(self, msg: Any, *args: Any, **kwargs: Any) -> None:
        """Log an info message with safe formatting and error handling.

        Args:
            msg: The message to log. Can be a string, format string, or any object.
            *args: Arguments for string formatting if msg is a format string.
            **kwargs: Additional keyword arguments passed to the parent logger.

        Note:
            If string formatting fails, the message is converted to string safely.
            This prevents logging calls from raising exceptions in production code.
        """
        try:
            # Attempt string formatting if args are provided and msg is a string
            formatted = msg % args if args and isinstance(msg, str) else msg
        except (TypeError, ValueError):
            # Handle formatting errors gracefully - convert to string representation
            formatted = str(msg)
        super().info(str(formatted), **kwargs)

    def warning(self, msg: Any, *args: Any, **kwargs: Any) -> None:
        """Log a warning message with safe formatting and error handling.

        Args:
            msg: The message to log. Can be a string, format string, or any object.
            *args: Arguments for string formatting if msg is a format string.
            **kwargs: Additional keyword arguments passed to the parent logger.

        Note:
            If string formatting fails, the message is converted to string safely.
            This prevents logging calls from raising exceptions in production code.
        """
        try:
            # Attempt string formatting if args are provided and msg is a string
            formatted = msg % args if args and isinstance(msg, str) else msg
        except (TypeError, ValueError):
            # Handle formatting errors gracefully - convert to string representation
            formatted = str(msg)
        super().warning(str(formatted), **kwargs)

    def error(self, msg: Any, *args: Any, **kwargs: Any) -> None:
        """Log an error message with safe formatting and error handling.

        Args:
            msg: The message to log. Can be a string, format string, or any object.
            *args: Arguments for string formatting if msg is a format string.
            **kwargs: Additional keyword arguments passed to the parent logger.

        Note:
            If string formatting fails, the message is converted to string safely.
            This prevents logging calls from raising exceptions in production code.
        """
        try:
            # Attempt string formatting if args are provided and msg is a string
            formatted = msg % args if args and isinstance(msg, str) else msg
        except (TypeError, ValueError):
            # Handle formatting errors gracefully - convert to string representation
            formatted = str(msg)
        super().error(str(formatted), **kwargs)

    def critical(self, msg: Any, *args: Any, **kwargs: Any) -> None:
        """Log a critical message with safe formatting and error handling.

        Args:
            msg: The message to log. Can be a string, format string, or any object.
            *args: Arguments for string formatting if msg is a format string.
            **kwargs: Additional keyword arguments passed to the parent logger.

        Note:
            If string formatting fails, the message is converted to string safely.
            This prevents logging calls from raising exceptions in production code.
        """
        try:
            # Attempt string formatting if args are provided and msg is a string
            formatted = msg % args if args and isinstance(msg, str) else msg
        except (TypeError, ValueError):
            # Handle formatting errors gracefully - convert to string representation
            formatted = str(msg)
        super().critical(str(formatted), **kwargs)
