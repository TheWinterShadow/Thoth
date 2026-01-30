"""Tests for DOCX parser."""

from pathlib import Path
import sys
from unittest.mock import MagicMock, patch

import pytest

from thoth.ingestion.parsers.docx import DocxParser


@pytest.fixture
def parser():
    """Create a DocxParser instance."""
    return DocxParser()


@pytest.fixture
def mock_document_class():
    """Create a mock Document class."""
    return MagicMock()


class TestDocxParser:
    """Tests for DocxParser class."""

    def test_supported_extensions(self, parser):
        """Test supported extensions."""
        extensions = parser.supported_extensions

        assert ".docx" in extensions
        assert len(extensions) == 1

    def test_parse_file_not_found(self, parser):
        """Test parsing a non-existent file."""
        with pytest.raises(FileNotFoundError):
            parser.parse(Path("/nonexistent/file.docx"))

    def test_parse_content_basic(self, parser, mock_document_class):
        """Test parsing DOCX content."""
        # Mock the Document
        mock_doc = MagicMock()
        mock_doc.paragraphs = [
            MagicMock(text="First paragraph"),
            MagicMock(text="Second paragraph"),
            MagicMock(text=""),  # Empty paragraph
            MagicMock(text="Third paragraph"),
        ]
        mock_doc.tables = []
        mock_doc.core_properties = MagicMock(
            title="Test Document",
            author="Test Author",
            subject="Test Subject",
            keywords="test, keywords",
        )

        mock_document_class.return_value = mock_doc

        # Mock the docx module
        mock_docx = MagicMock()
        mock_docx.Document = mock_document_class

        with patch.dict(sys.modules, {"docx": mock_docx}):
            result = parser.parse_content(b"fake docx content", "/test/file.docx")

        assert "First paragraph" in result.content
        assert "Second paragraph" in result.content
        assert "Third paragraph" in result.content
        assert result.format == "docx"
        assert result.source_path == "/test/file.docx"
        assert result.metadata["title"] == "Test Document"
        assert result.metadata["author"] == "Test Author"

    def test_parse_content_empty_document(self, parser, mock_document_class):
        """Test parsing empty DOCX."""
        mock_doc = MagicMock()
        mock_doc.paragraphs = []
        mock_doc.tables = []
        mock_doc.core_properties = MagicMock(
            title=None,
            author=None,
            subject=None,
            keywords=None,
        )

        mock_document_class.return_value = mock_doc

        mock_docx = MagicMock()
        mock_docx.Document = mock_document_class

        with patch.dict(sys.modules, {"docx": mock_docx}):
            result = parser.parse_content(b"fake docx content", "/test/empty.docx")

        assert result.content == ""
        # paragraph_count is 0 but gets filtered out as empty value
        assert result.metadata.get("paragraph_count") in (0, None)

    def test_parse_content_metadata_cleanup(self, parser, mock_document_class):
        """Test that empty metadata values are removed."""
        mock_doc = MagicMock()
        mock_doc.paragraphs = [MagicMock(text="Content")]
        mock_doc.tables = []
        mock_doc.core_properties = MagicMock(
            title="Valid Title",
            author="",  # Empty
            subject=None,  # None
            keywords="valid, keywords",
        )

        mock_document_class.return_value = mock_doc

        mock_docx = MagicMock()
        mock_docx.Document = mock_document_class

        with patch.dict(sys.modules, {"docx": mock_docx}):
            result = parser.parse_content(b"fake docx content", "/test/file.docx")

        assert result.metadata["title"] == "Valid Title"
        assert result.metadata["keywords"] == "valid, keywords"
        assert "author" not in result.metadata  # Empty removed

    def test_parse_content_whitespace_paragraphs(self, parser, mock_document_class):
        """Test that whitespace-only paragraphs are handled."""
        mock_doc = MagicMock()
        mock_doc.paragraphs = [
            MagicMock(text="Real content"),
            MagicMock(text="   "),  # Whitespace only
            MagicMock(text="\n\t"),  # Only newlines/tabs
            MagicMock(text="More content"),
        ]
        mock_doc.tables = []
        mock_doc.core_properties = MagicMock(
            title=None,
            author=None,
            subject=None,
            keywords=None,
        )

        mock_document_class.return_value = mock_doc

        mock_docx = MagicMock()
        mock_docx.Document = mock_document_class

        with patch.dict(sys.modules, {"docx": mock_docx}):
            result = parser.parse_content(b"fake docx content", "/test/file.docx")

        assert "Real content" in result.content
        assert "More content" in result.content

    def test_paragraph_count_metadata(self, parser, mock_document_class):
        """Test that paragraph count is in metadata."""
        mock_doc = MagicMock()
        mock_doc.paragraphs = [
            MagicMock(text="Para 1"),
            MagicMock(text="Para 2"),
            MagicMock(text="Para 3"),
        ]
        mock_doc.tables = []
        mock_doc.core_properties = MagicMock(
            title=None,
            author=None,
            subject=None,
            keywords=None,
        )

        mock_document_class.return_value = mock_doc

        mock_docx = MagicMock()
        mock_docx.Document = mock_document_class

        with patch.dict(sys.modules, {"docx": mock_docx}):
            result = parser.parse_content(b"fake docx content", "/test/file.docx")

        assert result.metadata["paragraph_count"] == 3

    def test_content_extraction(self, parser, mock_document_class):
        """Test that content is properly extracted."""
        mock_doc = MagicMock()
        mock_doc.paragraphs = [MagicMock(text="  Test content here  ")]  # With whitespace to strip
        mock_doc.tables = []
        mock_doc.core_properties = MagicMock(
            title=None,
            author=None,
            subject=None,
            keywords=None,
        )

        mock_document_class.return_value = mock_doc

        mock_docx = MagicMock()
        mock_docx.Document = mock_document_class

        with patch.dict(sys.modules, {"docx": mock_docx}):
            result = parser.parse_content(b"fake docx content", "/test/file.docx")

        assert result.content == "Test content here"  # Stripped
        assert result.metadata["paragraph_count"] == 1

    def test_document_receives_bytesio(self, parser, mock_document_class):
        """Test that Document receives BytesIO from content."""
        mock_doc = MagicMock()
        mock_doc.paragraphs = [MagicMock(text="Content")]
        mock_doc.tables = []
        mock_doc.core_properties = MagicMock(
            title=None,
            author=None,
            subject=None,
            keywords=None,
        )

        mock_document_class.return_value = mock_doc

        mock_docx = MagicMock()
        mock_docx.Document = mock_document_class

        content = b"fake docx content"
        with patch.dict(sys.modules, {"docx": mock_docx}):
            parser.parse_content(content, "/test/file.docx")

        # Verify Document was called with a BytesIO-like object
        mock_document_class.assert_called_once()
        call_args = mock_document_class.call_args[0]
        assert hasattr(call_args[0], "read")  # BytesIO-like
