"""Tests for PDF parser."""

from pathlib import Path
import sys
from unittest.mock import MagicMock, patch

import pytest

from thoth.ingestion.parsers.pdf import PDFParser


@pytest.fixture
def parser():
    """Create a PDFParser instance."""
    return PDFParser()


@pytest.fixture
def mock_fitz():
    """Create a mock fitz module."""
    return MagicMock()


class TestPDFParser:
    """Tests for PDFParser class."""

    def test_supported_extensions(self, parser):
        """Test supported extensions."""
        extensions = parser.supported_extensions

        assert ".pdf" in extensions
        assert len(extensions) == 1

    def test_parse_file_not_found(self, parser):
        """Test parsing a non-existent file."""
        with pytest.raises(FileNotFoundError):
            parser.parse(Path("/nonexistent/file.pdf"))

    def test_parse_content_basic(self, parser, mock_fitz):
        """Test parsing PDF content."""
        # Mock the fitz module
        mock_doc = MagicMock()
        mock_doc.__len__ = MagicMock(return_value=2)
        mock_doc.metadata = {"title": "Test PDF", "author": "Test Author"}

        mock_page1 = MagicMock()
        mock_page1.get_text.return_value = "Page 1 content"

        mock_page2 = MagicMock()
        mock_page2.get_text.return_value = "Page 2 content"

        mock_doc.__getitem__ = MagicMock(side_effect=lambda i: [mock_page1, mock_page2][i])
        mock_fitz.open.return_value = mock_doc

        with patch.dict(sys.modules, {"fitz": mock_fitz}):
            result = parser.parse_content(b"fake pdf content", "/test/file.pdf")

        assert "[Page 1]" in result.content
        assert "Page 1 content" in result.content
        assert "[Page 2]" in result.content
        assert "Page 2 content" in result.content
        assert result.format == "pdf"
        assert result.source_path == "/test/file.pdf"
        assert result.metadata["title"] == "Test PDF"
        assert result.metadata["author"] == "Test Author"
        assert result.metadata["page_count"] == 2

    def test_parse_content_empty_pages(self, parser, mock_fitz):
        """Test parsing PDF with empty pages."""
        mock_doc = MagicMock()
        mock_doc.__len__ = MagicMock(return_value=3)
        mock_doc.metadata = {}

        mock_page1 = MagicMock()
        mock_page1.get_text.return_value = "Content on page 1"

        mock_page2 = MagicMock()
        mock_page2.get_text.return_value = "   "  # Whitespace only

        mock_page3 = MagicMock()
        mock_page3.get_text.return_value = "Content on page 3"

        mock_doc.__getitem__ = MagicMock(side_effect=lambda i: [mock_page1, mock_page2, mock_page3][i])
        mock_fitz.open.return_value = mock_doc

        with patch.dict(sys.modules, {"fitz": mock_fitz}):
            result = parser.parse_content(b"fake pdf content", "/test/file.pdf")

        # Empty page should be skipped
        assert "[Page 1]" in result.content
        assert "[Page 2]" not in result.content  # Empty page skipped
        assert "[Page 3]" in result.content

    def test_parse_content_metadata_cleanup(self, parser, mock_fitz):
        """Test that empty metadata values are removed."""
        mock_doc = MagicMock()
        mock_doc.__len__ = MagicMock(return_value=1)
        mock_doc.metadata = {
            "title": "Valid Title",
            "author": "",  # Empty, should be removed
            "subject": None,  # None, should be removed
            "creator": "PDF Creator",
        }

        mock_page = MagicMock()
        mock_page.get_text.return_value = "Content"

        mock_doc.__getitem__ = MagicMock(return_value=mock_page)
        mock_fitz.open.return_value = mock_doc

        with patch.dict(sys.modules, {"fitz": mock_fitz}):
            result = parser.parse_content(b"fake pdf content", "/test/file.pdf")

        assert result.metadata["title"] == "Valid Title"
        assert result.metadata.get("creator") == "PDF Creator"
        assert "author" not in result.metadata  # Empty value removed

    def test_parse_content_no_metadata(self, parser, mock_fitz):
        """Test parsing PDF with no metadata."""
        mock_doc = MagicMock()
        mock_doc.__len__ = MagicMock(return_value=1)
        mock_doc.metadata = None

        mock_page = MagicMock()
        mock_page.get_text.return_value = "Content"

        mock_doc.__getitem__ = MagicMock(return_value=mock_page)
        mock_fitz.open.return_value = mock_doc

        with patch.dict(sys.modules, {"fitz": mock_fitz}):
            result = parser.parse_content(b"fake pdf content", "/test/file.pdf")

        assert result.metadata["source_path"] == "/test/file.pdf"
        assert result.metadata["page_count"] == 1

    def test_document_close(self, parser, mock_fitz):
        """Test that document is closed after parsing."""
        mock_doc = MagicMock()
        mock_doc.__len__ = MagicMock(return_value=1)
        mock_doc.metadata = {}

        mock_page = MagicMock()
        mock_page.get_text.return_value = "Content"

        mock_doc.__getitem__ = MagicMock(return_value=mock_page)
        mock_fitz.open.return_value = mock_doc

        with patch.dict(sys.modules, {"fitz": mock_fitz}):
            parser.parse_content(b"fake pdf content", "/test/file.pdf")

        # Verify close was called
        mock_doc.close.assert_called_once()
