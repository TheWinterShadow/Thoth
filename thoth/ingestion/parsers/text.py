"""Plain text document parser.

This module provides parsing for plain text files.
"""

import logging
from pathlib import Path

from thoth.ingestion.parsers.base import DocumentParser, ParsedDocument

logger = logging.getLogger(__name__)


class TextParser(DocumentParser):
    """Parser for plain text files.

    Supports:
    - Plain text files (.txt, .text)
    - UTF-8 encoding with fallback to latin-1
    """

    @property
    def supported_extensions(self) -> list[str]:
        """Return supported text extensions."""
        return [".txt", ".text"]

    def parse(self, file_path: Path) -> ParsedDocument:
        """Parse a plain text file.

        Args:
            file_path: Path to the text file

        Returns:
            ParsedDocument with content

        Raises:
            FileNotFoundError: If file doesn't exist
        """
        if not file_path.exists():
            msg = f"File not found: {file_path}"
            raise FileNotFoundError(msg)

        content = file_path.read_bytes()
        return self.parse_content(content, str(file_path))

    def parse_content(self, content: bytes, source_path: str) -> ParsedDocument:
        """Parse text content from bytes.

        Args:
            content: Raw file content as bytes
            source_path: Original source path for metadata

        Returns:
            ParsedDocument with content
        """
        try:
            text = content.decode("utf-8")
        except UnicodeDecodeError:
            # Try with latin-1 as fallback
            text = content.decode("latin-1")
            logger.warning("File %s not valid UTF-8, used latin-1 fallback", source_path)

        # Basic metadata
        metadata = {
            "source_path": source_path,
            "char_count": len(text),
            "line_count": text.count("\n") + 1,
        }

        return ParsedDocument(
            content=text,
            metadata=metadata,
            source_path=source_path,
            format="text",
        )
