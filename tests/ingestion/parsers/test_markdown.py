"""Tests for markdown parser."""

from pathlib import Path
import tempfile

import pytest

from thoth.ingestion.parsers.markdown import MarkdownParser


@pytest.fixture
def parser():
    """Create a MarkdownParser instance."""
    return MarkdownParser()


@pytest.fixture
def sample_markdown():
    """Sample markdown content with frontmatter."""
    return """---
title: Test Document
author: Test Author
tags:
  - test
  - markdown
---

# Main Title

This is the introduction.

## Section 1

Content for section 1.

### Subsection 1.1

More detailed content.

## Section 2

Final section content.
"""


@pytest.fixture
def markdown_without_frontmatter():
    """Markdown content without frontmatter."""
    return """# Simple Document

Just some content without frontmatter.

## Section

More content here.
"""


class TestMarkdownParser:
    """Tests for MarkdownParser class."""

    def test_supported_extensions(self, parser):
        """Test supported extensions."""
        extensions = parser.supported_extensions

        assert ".md" in extensions
        assert ".markdown" in extensions

    def test_parse_file(self, parser, sample_markdown):
        """Test parsing a markdown file."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as tmp:
            tmp.write(sample_markdown)
            tmp_path = Path(tmp.name)

        try:
            result = parser.parse(tmp_path)

            assert result.content
            assert result.format == "markdown"
            assert result.source_path == str(tmp_path)
            assert "title" in result.metadata
            assert result.metadata["title"] == "Test Document"
            assert result.metadata["author"] == "Test Author"
        finally:
            tmp_path.unlink()

    def test_parse_file_not_found(self, parser):
        """Test parsing a non-existent file."""
        with pytest.raises(FileNotFoundError):
            parser.parse(Path("/nonexistent/file.md"))

    def test_parse_content(self, parser, sample_markdown):
        """Test parsing markdown content from bytes."""
        content = sample_markdown.encode("utf-8")
        result = parser.parse_content(content, "/test/file.md")

        assert result.content
        assert result.format == "markdown"
        assert result.source_path == "/test/file.md"
        assert result.metadata["title"] == "Test Document"

    def test_parse_without_frontmatter(self, parser, markdown_without_frontmatter):
        """Test parsing markdown without frontmatter."""
        content = markdown_without_frontmatter.encode("utf-8")
        result = parser.parse_content(content, "/test/simple.md")

        assert result.content
        assert "# Simple Document" in result.content
        assert result.metadata["source_path"] == "/test/simple.md"

    def test_frontmatter_extraction(self, parser, sample_markdown):
        """Test YAML frontmatter extraction."""
        content = sample_markdown.encode("utf-8")
        result = parser.parse_content(content, "/test/file.md")

        assert "title" in result.metadata
        assert "author" in result.metadata
        # Note: Simple frontmatter parser doesn't handle lists, just key: value pairs

    def test_frontmatter_removed_from_content(self, parser, sample_markdown):
        """Test that frontmatter is removed from content."""
        content = sample_markdown.encode("utf-8")
        result = parser.parse_content(content, "/test/file.md")

        # Frontmatter should be removed
        assert "---" not in result.content.split("\n")[0]
        # But main content should remain
        assert "# Main Title" in result.content

    def test_empty_content(self, parser):
        """Test parsing empty content."""
        result = parser.parse_content(b"", "/test/empty.md")

        assert result.content == ""

    def test_whitespace_only_content(self, parser):
        """Test parsing whitespace-only content."""
        result = parser.parse_content(b"   \n  \n  ", "/test/whitespace.md")

        assert result.content.strip() == ""

    def test_invalid_frontmatter(self, parser):
        """Test parsing with invalid YAML frontmatter."""
        content = b"""---
invalid: yaml: content: here
---

# Title

Content
"""
        # Should not raise, should just skip frontmatter
        result = parser.parse_content(content, "/test/invalid.md")

        assert result.content

    def test_unicode_content(self, parser):
        """Test parsing unicode content."""
        content = """---
title: Unicode Test
---

# Unicode Content

Chinese: 中文
Japanese: 日本語
Emoji: 🎉
"""
        result = parser.parse_content(content.encode("utf-8"), "/test/unicode.md")

        assert "中文" in result.content
        assert "日本語" in result.content
        assert "🎉" in result.content

    def test_metadata_source_path(self, parser, sample_markdown):
        """Test that source_path is in metadata."""
        content = sample_markdown.encode("utf-8")
        result = parser.parse_content(content, "/test/file.md")

        assert "source_path" in result.metadata
        assert result.metadata["source_path"] == "/test/file.md"
