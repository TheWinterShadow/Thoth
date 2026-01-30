"""Tests for base parser module."""

from pathlib import Path

import pytest

from thoth.ingestion.parsers.base import DocumentParser, ParsedDocument


class TestParsedDocument:
    """Tests for ParsedDocument dataclass."""

    def test_parsed_document_creation(self):
        """Test creating a ParsedDocument."""
        doc = ParsedDocument(
            content="Test content",
            metadata={"key": "value"},
            source_path="/path/to/file.md",
            format="markdown",
        )

        assert doc.content == "Test content"
        assert doc.metadata == {"key": "value"}
        assert doc.source_path == "/path/to/file.md"
        assert doc.format == "markdown"

    def test_parsed_document_empty_metadata(self):
        """Test ParsedDocument with empty metadata."""
        doc = ParsedDocument(
            content="Content",
            metadata={},
            source_path="/path/to/file.txt",
            format="text",
        )

        assert doc.metadata == {}

    def test_parsed_document_complex_metadata(self):
        """Test ParsedDocument with complex metadata."""
        metadata = {
            "title": "Document Title",
            "author": "Test Author",
            "tags": ["tag1", "tag2"],
            "page_count": 5,
        }
        doc = ParsedDocument(
            content="Content",
            metadata=metadata,
            source_path="/path/to/file.pdf",
            format="pdf",
        )

        assert doc.metadata["title"] == "Document Title"
        assert doc.metadata["tags"] == ["tag1", "tag2"]
        assert doc.metadata["page_count"] == 5


class TestDocumentParser:
    """Tests for DocumentParser abstract base class."""

    def test_cannot_instantiate_abc(self):
        """Test that DocumentParser cannot be instantiated directly."""
        with pytest.raises(TypeError):
            DocumentParser()

    def test_subclass_must_implement_methods(self):
        """Test that subclasses must implement abstract methods."""

        class IncompleteParser(DocumentParser):
            pass

        with pytest.raises(TypeError):
            IncompleteParser()

    def test_valid_subclass(self):
        """Test that a valid subclass can be created."""

        class ValidParser(DocumentParser):
            @property
            def supported_extensions(self) -> list[str]:
                return [".test"]

            def parse(self, file_path: Path) -> ParsedDocument:
                return ParsedDocument(
                    content="test",
                    metadata={},
                    source_path=str(file_path),
                    format="test",
                )

            def parse_content(self, content: bytes, source_path: str) -> ParsedDocument:
                return ParsedDocument(
                    content=content.decode(),
                    metadata={},
                    source_path=source_path,
                    format="test",
                )

        parser = ValidParser()
        assert parser.supported_extensions == [".test"]
