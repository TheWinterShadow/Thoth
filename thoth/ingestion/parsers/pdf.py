"""PDF document parser.

This module provides parsing for PDF files using PyMuPDF (fitz).
"""

import logging
from pathlib import Path

from thoth.ingestion.parsers.base import DocumentParser, ParsedDocument

logger = logging.getLogger(__name__)


class PDFParser(DocumentParser):
    """Parser for PDF files using PyMuPDF.

    Supports:
    - PDF files (.pdf)
    - Text extraction with page numbers
    - Basic metadata extraction (title, author, page count)
    """

    @property
    def supported_extensions(self) -> list[str]:
        """Return supported PDF extensions."""
        return [".pdf"]

    def parse(self, file_path: Path) -> ParsedDocument:
        """Parse a PDF file.

        Args:
            file_path: Path to the PDF file

        Returns:
            ParsedDocument with extracted text and metadata

        Raises:
            FileNotFoundError: If file doesn't exist
            ImportError: If PyMuPDF is not installed
        """
        if not file_path.exists():
            msg = f"File not found: {file_path}"
            raise FileNotFoundError(msg)

        content = file_path.read_bytes()
        return self.parse_content(content, str(file_path))

    def parse_content(self, content: bytes, source_path: str) -> ParsedDocument:
        """Parse PDF content from bytes.

        Args:
            content: Raw PDF content as bytes
            source_path: Original source path for metadata

        Returns:
            ParsedDocument with extracted text and metadata
        """
        try:
            import fitz  # PyMuPDF  # noqa: PLC0415
        except ImportError as e:
            msg = "PyMuPDF is required for PDF parsing. Install with: pip install PyMuPDF"
            raise ImportError(msg) from e

        # Open PDF from bytes
        doc = fitz.open(stream=content, filetype="pdf")

        try:
            text_parts = []

            for page_num in range(len(doc)):
                page = doc[page_num]
                text = page.get_text()

                if text.strip():
                    # Add page marker for context
                    text_parts.append(f"[Page {page_num + 1}]\n{text}")

            # Extract metadata
            pdf_metadata = doc.metadata or {}
            metadata = {
                "source_path": source_path,
                "page_count": len(doc),
                "title": pdf_metadata.get("title", ""),
                "author": pdf_metadata.get("author", ""),
                "subject": pdf_metadata.get("subject", ""),
                "creator": pdf_metadata.get("creator", ""),
                "producer": pdf_metadata.get("producer", ""),
            }

            # Remove empty metadata values
            metadata = {k: v for k, v in metadata.items() if v}

            combined_text = "\n\n".join(text_parts)

            return ParsedDocument(
                content=combined_text,
                metadata=metadata,
                source_path=source_path,
                format="pdf",
            )

        finally:
            doc.close()
