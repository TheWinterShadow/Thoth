"""Tests for parser factory."""

from pathlib import Path

import pytest

from thoth.ingestion.parsers import ParserFactory
from thoth.ingestion.parsers.docx import DocxParser
from thoth.ingestion.parsers.markdown import MarkdownParser
from thoth.ingestion.parsers.pdf import PDFParser
from thoth.ingestion.parsers.text import TextParser


class TestParserFactory:
    """Tests for ParserFactory class."""

    def test_get_parser_markdown(self):
        """Test getting parser for markdown files."""
        parser = ParserFactory.get_parser(Path("test.md"))
        assert isinstance(parser, MarkdownParser)

        parser = ParserFactory.get_parser(Path("test.markdown"))
        assert isinstance(parser, MarkdownParser)

    def test_get_parser_text(self):
        """Test getting parser for text files."""
        parser = ParserFactory.get_parser(Path("test.txt"))
        assert isinstance(parser, TextParser)

        parser = ParserFactory.get_parser(Path("test.text"))
        assert isinstance(parser, TextParser)

    def test_get_parser_pdf(self):
        """Test getting parser for PDF files."""
        parser = ParserFactory.get_parser(Path("test.pdf"))
        assert isinstance(parser, PDFParser)

    def test_get_parser_docx(self):
        """Test getting parser for DOCX files."""
        parser = ParserFactory.get_parser(Path("test.docx"))
        assert isinstance(parser, DocxParser)

    def test_get_parser_case_insensitive(self):
        """Test that extension matching is case-insensitive."""
        parser = ParserFactory.get_parser(Path("test.MD"))
        assert isinstance(parser, MarkdownParser)

        parser = ParserFactory.get_parser(Path("test.PDF"))
        assert isinstance(parser, PDFParser)

        parser = ParserFactory.get_parser(Path("test.TXT"))
        assert isinstance(parser, TextParser)

        parser = ParserFactory.get_parser(Path("test.DOCX"))
        assert isinstance(parser, DocxParser)

    def test_get_parser_unknown_extension(self):
        """Test getting parser for unknown extension."""
        parser = ParserFactory.get_parser(Path("test.xyz"))
        assert parser is None

        parser = ParserFactory.get_parser(Path("test.jpg"))
        assert parser is None

        parser = ParserFactory.get_parser(Path("test.html"))
        assert parser is None

    def test_supported_extensions(self):
        """Test getting all supported extensions."""
        extensions = ParserFactory.supported_extensions()

        assert isinstance(extensions, list)
        assert ".md" in extensions
        assert ".markdown" in extensions
        assert ".txt" in extensions
        assert ".text" in extensions
        assert ".pdf" in extensions
        assert ".docx" in extensions

    def test_supported_extensions_no_duplicates(self):
        """Test that supported extensions list has no duplicates."""
        extensions = ParserFactory.supported_extensions()

        assert len(extensions) == len(set(extensions))

    def test_can_parse(self):
        """Test checking if file can be parsed."""
        assert ParserFactory.can_parse(Path("test.md"))
        assert ParserFactory.can_parse(Path("test.markdown"))
        assert ParserFactory.can_parse(Path("test.txt"))
        assert ParserFactory.can_parse(Path("test.pdf"))
        assert ParserFactory.can_parse(Path("test.docx"))

        assert not ParserFactory.can_parse(Path("test.xyz"))
        assert not ParserFactory.can_parse(Path("test.jpg"))

    def test_can_parse_case_insensitive(self):
        """Test that can_parse is case-insensitive."""
        assert ParserFactory.can_parse(Path("test.MD"))
        assert ParserFactory.can_parse(Path("test.Pdf"))
        assert ParserFactory.can_parse(Path("test.TXT"))

    def test_parser_instances_cached(self):
        """Test that parser instances are cached."""
        # Clear cache first
        ParserFactory._parser_instances.clear()

        parser1 = ParserFactory.get_parser(Path("test.md"))
        parser2 = ParserFactory.get_parser(Path("another.md"))

        # Should be same cached instance
        assert parser1 is parser2

    def test_parse_content(self):
        """Test parsing content bytes."""
        content = b"# Test\n\nSome content"
        result = ParserFactory.parse_content(content, "/test/file.md", ".md")

        assert result.content
        assert result.source_path == "/test/file.md"

    def test_parse_content_unknown_extension(self):
        """Test parsing content with unknown extension."""
        with pytest.raises(ValueError, match="No parser available"):
            ParserFactory.parse_content(b"content", "/test/file.xyz", ".xyz")

    def test_empty_extension_file(self):
        """Test getting parser for file without extension."""
        parser = ParserFactory.get_parser(Path("noextension"))
        assert parser is None
