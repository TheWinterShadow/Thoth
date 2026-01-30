"""Base classes for document parsers.

This module defines the abstract interface for document parsers and
the ParsedDocument data structure used across all parser implementations.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class ParsedDocument:
    """Result of parsing a document.

    Attributes:
        content: Extracted text content from the document
        metadata: Dictionary of metadata extracted from the document
        source_path: Original file path or identifier
        format: Document format identifier (e.g., 'markdown', 'pdf', 'text', 'docx')
    """

    content: str
    metadata: dict[str, Any] = field(default_factory=dict)
    source_path: str = ""
    format: str = ""

    def __post_init__(self) -> None:
        """Validate parsed document after initialization."""
        if not self.format:
            msg = "Document format must be specified"
            raise ValueError(msg)


class DocumentParser(ABC):
    """Abstract base class for document parsers.

    All document parsers must implement this interface to ensure
    consistent behavior across different file formats.

    Example:
        >>> parser = MarkdownParser()
        >>> if parser.can_parse(Path("doc.md")):
        ...     doc = parser.parse(Path("doc.md"))
        ...     print(doc.content)
    """

    @property
    @abstractmethod
    def supported_extensions(self) -> list[str]:
        """Return list of supported file extensions.

        Returns:
            List of extensions including the dot (e.g., ['.md', '.markdown'])
        """

    @abstractmethod
    def parse(self, file_path: Path) -> ParsedDocument:
        """Parse a document file and return structured content.

        Args:
            file_path: Path to the document file

        Returns:
            ParsedDocument with extracted text and metadata

        Raises:
            ValueError: If file format is not supported
            FileNotFoundError: If file doesn't exist
            IOError: If file cannot be read
        """

    @abstractmethod
    def parse_content(self, content: bytes, source_path: str) -> ParsedDocument:
        """Parse document content from bytes.

        This method allows parsing content that has already been loaded
        into memory, useful for processing files from cloud storage.

        Args:
            content: Raw file content as bytes
            source_path: Original source path for metadata

        Returns:
            ParsedDocument with extracted text and metadata
        """

    def can_parse(self, file_path: Path) -> bool:
        """Check if this parser can handle the given file.

        Args:
            file_path: Path to check

        Returns:
            True if this parser supports the file's extension
        """
        return file_path.suffix.lower() in [ext.lower() for ext in self.supported_extensions]

    @property
    def name(self) -> str:
        """Return the parser name.

        Returns:
            Human-readable parser name
        """
        return self.__class__.__name__
