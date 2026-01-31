"""Document parsers for multi-format ingestion.

This module provides a unified interface for parsing different document
formats (Markdown, PDF, plain text, Word documents).

Example:
    >>> from thoth.ingestion.parsers import ParserFactory
    >>> from pathlib import Path
    >>>
    >>> doc = ParserFactory.parse(Path("document.pdf"))
    >>> print(doc.content)
"""

from pathlib import Path
from typing import ClassVar

from thoth.ingestion.parsers.base import DocumentParser, ParsedDocument
from thoth.ingestion.parsers.docx import DocxParser
from thoth.ingestion.parsers.markdown import MarkdownParser
from thoth.ingestion.parsers.pdf import PDFParser
from thoth.ingestion.parsers.text import TextParser
from thoth.shared.utils.logger import setup_logger

logger = setup_logger(__name__)

__all__ = [
    "DocumentParser",
    "DocxParser",
    "MarkdownParser",
    "PDFParser",
    "ParsedDocument",
    "ParserFactory",
    "TextParser",
]


class ParserFactory:
    """Factory for creating and using document parsers.

    This factory maintains a registry of available parsers and provides
    methods to parse files using the appropriate parser based on file
    extension.

    Example:
        >>> # Parse a single file
        >>> doc = ParserFactory.parse(Path("notes.md"))
        >>>
        >>> # Get parser for a specific file
        >>> parser = ParserFactory.get_parser(Path("document.pdf"))
        >>> if parser:
        ...     doc = parser.parse(Path("document.pdf"))
        >>>
        >>> # Check supported extensions
        >>> extensions = ParserFactory.supported_extensions()
        >>> print(extensions)  # ['.md', '.markdown', '.mdown', '.pdf', '.txt', ...]
    """

    # Registry of parser classes
    _parser_classes: ClassVar[list[type[DocumentParser]]] = [
        MarkdownParser,
        PDFParser,
        TextParser,
        DocxParser,
    ]

    # Cache of parser instances
    _parser_instances: ClassVar[dict[str, DocumentParser]] = {}

    @classmethod
    def get_parser(cls, file_path: Path) -> DocumentParser | None:
        """Get appropriate parser for a file.

        Args:
            file_path: Path to the file to parse

        Returns:
            DocumentParser instance if a suitable parser exists, None otherwise
        """
        extension = file_path.suffix.lower()

        # Check cache first
        if extension in cls._parser_instances:
            return cls._parser_instances[extension]

        # Find and cache parser
        for parser_class in cls._parser_classes:
            parser = parser_class()
            if parser.can_parse(file_path):
                # Cache for all supported extensions
                for ext in parser.supported_extensions:
                    cls._parser_instances[ext.lower()] = parser
                return parser

        return None

    @classmethod
    def parse(cls, file_path: Path) -> ParsedDocument:
        """Parse a file using the appropriate parser.

        Args:
            file_path: Path to the file to parse

        Returns:
            ParsedDocument with extracted content and metadata

        Raises:
            ValueError: If no parser is available for the file type
            FileNotFoundError: If file doesn't exist
        """
        parser = cls.get_parser(file_path)

        if parser is None:
            supported = cls.supported_extensions()
            msg = f"No parser available for '{file_path.suffix}'. Supported: {supported}"
            raise ValueError(msg)

        logger.debug("Parsing %s with %s", file_path, parser.name)
        return parser.parse(file_path)

    @classmethod
    def parse_content(cls, content: bytes, source_path: str, extension: str) -> ParsedDocument:
        """Parse content bytes using a parser for the given extension.

        Args:
            content: Raw file content as bytes
            source_path: Original source path for metadata
            extension: File extension (e.g., '.pdf')

        Returns:
            ParsedDocument with extracted content and metadata

        Raises:
            ValueError: If no parser is available for the extension
        """
        # Create a fake path to find the right parser
        fake_path = Path(f"file{extension}")
        parser = cls.get_parser(fake_path)

        if parser is None:
            supported = cls.supported_extensions()
            msg = f"No parser available for '{extension}'. Supported: {supported}"
            raise ValueError(msg)

        logger.debug("Parsing content for %s with %s", source_path, parser.name)
        return parser.parse_content(content, source_path)

    @classmethod
    def supported_extensions(cls) -> list[str]:
        """Get all supported file extensions.

        Returns:
            List of supported extensions including the dot (e.g., ['.md', '.pdf'])
        """
        extensions = []
        for parser_class in cls._parser_classes:
            parser = parser_class()
            extensions.extend(parser.supported_extensions)
        return sorted(set(extensions))

    @classmethod
    def can_parse(cls, file_path: Path) -> bool:
        """Check if any parser can handle the given file.

        Args:
            file_path: Path to check

        Returns:
            True if a parser is available for the file
        """
        return cls.get_parser(file_path) is not None

    @classmethod
    def register_parser(cls, parser_class: type[DocumentParser]) -> None:
        """Register a new parser class.

        Args:
            parser_class: Parser class to register
        """
        if parser_class not in cls._parser_classes:
            cls._parser_classes.append(parser_class)
            # Clear cache to include new parser
            cls._parser_instances.clear()
            logger.info("Registered parser: %s", parser_class.__name__)
