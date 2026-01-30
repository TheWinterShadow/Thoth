"""Markdown document parser.

This module provides parsing for Markdown files with support for
YAML frontmatter extraction.
"""

import logging
from pathlib import Path
import re

from thoth.ingestion.parsers.base import DocumentParser, ParsedDocument

logger = logging.getLogger(__name__)


class MarkdownParser(DocumentParser):
    """Parser for Markdown files.

    Supports:
    - Standard Markdown (.md, .markdown, .mdown)
    - YAML frontmatter extraction
    - UTF-8 encoding
    """

    @property
    def supported_extensions(self) -> list[str]:
        """Return supported Markdown extensions."""
        return [".md", ".markdown", ".mdown"]

    def parse(self, file_path: Path) -> ParsedDocument:
        """Parse a Markdown file.

        Args:
            file_path: Path to the Markdown file

        Returns:
            ParsedDocument with content and metadata

        Raises:
            FileNotFoundError: If file doesn't exist
            UnicodeDecodeError: If file isn't valid UTF-8
        """
        if not file_path.exists():
            msg = f"File not found: {file_path}"
            raise FileNotFoundError(msg)

        content = file_path.read_bytes()
        return self.parse_content(content, str(file_path))

    def parse_content(self, content: bytes, source_path: str) -> ParsedDocument:
        """Parse Markdown content from bytes.

        Args:
            content: Raw file content as bytes
            source_path: Original source path for metadata

        Returns:
            ParsedDocument with content and extracted metadata
        """
        try:
            text = content.decode("utf-8")
        except UnicodeDecodeError:
            # Try with latin-1 as fallback
            text = content.decode("latin-1")
            logger.warning("File %s not valid UTF-8, used latin-1 fallback", source_path)

        # Extract YAML frontmatter if present
        metadata = self._extract_frontmatter(text)
        metadata["source_path"] = source_path

        # Remove frontmatter from content
        clean_content = self._remove_frontmatter(text)

        return ParsedDocument(
            content=clean_content,
            metadata=metadata,
            source_path=source_path,
            format="markdown",
        )

    def _extract_frontmatter(self, text: str) -> dict:
        """Extract YAML frontmatter if present.

        YAML frontmatter is delimited by --- at the start of the file:
        ---
        title: My Document
        author: John Doe
        ---

        Args:
            text: Full document text

        Returns:
            Dictionary of frontmatter key-value pairs
        """
        # Match YAML frontmatter at the beginning of the file
        pattern = r"^---\s*\n(.*?)\n---\s*\n"
        match = re.match(pattern, text, re.DOTALL)

        if not match:
            return {}

        frontmatter_text = match.group(1)
        metadata = {}

        # Parse simple key: value pairs (not full YAML parsing to avoid dependency)
        for raw_line in frontmatter_text.split("\n"):
            line = raw_line.strip()
            if ":" in line and not line.startswith("#"):
                key, _, value = line.partition(":")
                key = key.strip()
                value = value.strip().strip('"').strip("'")
                if key and value:
                    metadata[key] = value

        return metadata

    def _remove_frontmatter(self, text: str) -> str:
        """Remove YAML frontmatter from text.

        Args:
            text: Full document text

        Returns:
            Text with frontmatter removed
        """
        pattern = r"^---\s*\n.*?\n---\s*\n"
        return re.sub(pattern, "", text, count=1, flags=re.DOTALL)
