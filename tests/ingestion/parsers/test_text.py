"""Tests for text parser."""

from pathlib import Path
import tempfile

import pytest

from thoth.ingestion.parsers.text import TextParser


@pytest.fixture
def parser():
    """Create a TextParser instance."""
    return TextParser()


@pytest.fixture
def sample_text():
    """Sample text content."""
    return """This is a sample text file.

It has multiple lines.
And some content.

Final paragraph here.
"""


class TestTextParser:
    """Tests for TextParser class."""

    def test_supported_extensions(self, parser):
        """Test supported extensions."""
        extensions = parser.supported_extensions

        assert ".txt" in extensions
        assert ".text" in extensions

    def test_parse_file(self, parser, sample_text):
        """Test parsing a text file."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as tmp:
            tmp.write(sample_text)
            tmp_path = Path(tmp.name)

        try:
            result = parser.parse(tmp_path)

            assert result.content == sample_text
            assert result.format == "text"
            assert result.source_path == str(tmp_path)
        finally:
            tmp_path.unlink()

    def test_parse_file_not_found(self, parser):
        """Test parsing a non-existent file."""
        with pytest.raises(FileNotFoundError):
            parser.parse(Path("/nonexistent/file.txt"))

    def test_parse_content(self, parser, sample_text):
        """Test parsing text content from bytes."""
        content = sample_text.encode("utf-8")
        result = parser.parse_content(content, "/test/file.txt")

        assert result.content == sample_text
        assert result.format == "text"
        assert result.source_path == "/test/file.txt"

    def test_metadata(self, parser, sample_text):
        """Test metadata generation."""
        content = sample_text.encode("utf-8")
        result = parser.parse_content(content, "/test/file.txt")

        assert "source_path" in result.metadata
        assert "char_count" in result.metadata
        assert "line_count" in result.metadata
        assert result.metadata["char_count"] == len(sample_text)
        assert result.metadata["line_count"] == sample_text.count("\n") + 1

    def test_empty_content(self, parser):
        """Test parsing empty content."""
        result = parser.parse_content(b"", "/test/empty.txt")

        assert result.content == ""
        assert result.metadata["char_count"] == 0
        assert result.metadata["line_count"] == 1

    def test_single_line(self, parser):
        """Test parsing single line without newline."""
        result = parser.parse_content(b"Single line", "/test/single.txt")

        assert result.content == "Single line"
        assert result.metadata["line_count"] == 1

    def test_unicode_content(self, parser):
        """Test parsing unicode content."""
        content = "Unicode: 中文 日本語 🎉"
        result = parser.parse_content(content.encode("utf-8"), "/test/unicode.txt")

        assert "中文" in result.content
        assert "日本語" in result.content
        assert "🎉" in result.content

    def test_latin1_fallback(self, parser):
        """Test latin-1 fallback for non-UTF-8 content."""
        # Create content that's valid latin-1 but not valid UTF-8
        content = bytes([0xE9, 0xE8, 0xE0])  # é è à in latin-1
        result = parser.parse_content(content, "/test/latin1.txt")

        # Should successfully decode
        assert len(result.content) == 3

    def test_special_characters(self, parser):
        """Test parsing special characters."""
        content = "Special chars: @#$%^&*()_+{}|:<>?\n\t\r"
        result = parser.parse_content(content.encode("utf-8"), "/test/special.txt")

        assert "@#$%^&*()" in result.content
        assert "\t" in result.content
