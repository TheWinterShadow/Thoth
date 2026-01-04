"""Tests for the markdown chunker."""

from pathlib import Path
import tempfile

import pytest

from thoth.ingestion.chunker import (
    MSG_EMPTY_CONTENT,
    Chunk,
    ChunkMetadata,
    MarkdownChunker,
)


@pytest.fixture
def chunker():
    """Create a MarkdownChunker instance."""
    return MarkdownChunker(
        min_chunk_size=100,
        max_chunk_size=300,
        overlap_size=50,
    )


@pytest.fixture
def sample_markdown():
    """Sample markdown content for testing."""
    return """# Main Title

This is an introduction paragraph.

## Section 1

This is the first section with some content.
It has multiple lines.

### Subsection 1.1

More detailed content here.

## Section 2

This is the second section.

### Subsection 2.1

Even more content.

### Subsection 2.2

Additional content here.

## Section 3

Final section with content.
"""


@pytest.fixture
def large_markdown():
    """Large markdown content that requires splitting."""
    sections = [
        f"""## Section {i}

This is section {i} with substantial content. {"Lorem ipsum dolor sit amet. " * 20}

### Subsection {i}.1

More content here. {"Additional text to make it longer. " * 15}

### Subsection {i}.2

Even more content. {"Extra padding text here. " * 15}
"""
        for i in range(10)
    ]
    return "# Large Document\n\n" + "\n".join(sections)


class TestChunkMetadata:
    """Tests for ChunkMetadata class."""

    def test_metadata_creation(self):
        """Test creating metadata."""
        metadata = ChunkMetadata(
            chunk_id="test_123",
            file_path="/path/to/file.md",
            chunk_index=0,
            total_chunks=5,
            headers=["Main", "Section 1"],
            start_line=1,
            end_line=10,
            token_count=250,
            char_count=1000,
        )

        assert metadata.chunk_id == "test_123"
        assert metadata.file_path == "/path/to/file.md"
        assert metadata.chunk_index == 0
        assert metadata.total_chunks == 5
        assert metadata.headers == ["Main", "Section 1"]
        assert metadata.start_line == 1
        assert metadata.end_line == 10
        assert metadata.token_count == 250
        assert metadata.char_count == 1000
        assert not metadata.overlap_with_previous
        assert not metadata.overlap_with_next

    def test_metadata_to_dict(self):
        """Test converting metadata to dictionary."""
        metadata = ChunkMetadata(
            chunk_id="test_123",
            file_path="/path/to/file.md",
            chunk_index=0,
            total_chunks=5,
        )

        result = metadata.to_dict()

        assert isinstance(result, dict)
        assert result["chunk_id"] == "test_123"
        assert result["file_path"] == "/path/to/file.md"
        assert result["chunk_index"] == 0
        assert result["total_chunks"] == 5
        assert "timestamp" in result


class TestChunk:
    """Tests for Chunk class."""

    def test_chunk_creation(self):
        """Test creating a chunk."""
        metadata = ChunkMetadata(
            chunk_id="test_123",
            file_path="/path/to/file.md",
            chunk_index=0,
            total_chunks=1,
        )
        chunk = Chunk(content="Test content", metadata=metadata)

        assert chunk.content == "Test content"
        assert chunk.metadata == metadata

    def test_chunk_to_dict(self):
        """Test converting chunk to dictionary."""
        metadata = ChunkMetadata(
            chunk_id="test_123",
            file_path="/path/to/file.md",
            chunk_index=0,
            total_chunks=1,
        )
        chunk = Chunk(content="Test content", metadata=metadata)

        result = chunk.to_dict()

        assert isinstance(result, dict)
        assert result["content"] == "Test content"
        assert isinstance(result["metadata"], dict)
        assert result["metadata"]["chunk_id"] == "test_123"


class TestMarkdownChunker:
    """Tests for MarkdownChunker class."""

    def test_chunker_initialization(self):
        """Test chunker initialization."""
        chunker = MarkdownChunker(
            min_chunk_size=100,
            max_chunk_size=500,
            overlap_size=50,
        )

        assert chunker.min_chunk_size == 100
        assert chunker.max_chunk_size == 500
        assert chunker.overlap_size == 50

    def test_invalid_overlap_size(self):
        """Test that overlap size must be less than min chunk size."""
        with pytest.raises(ValueError, match="Overlap size must be less"):
            MarkdownChunker(min_chunk_size=100, max_chunk_size=500, overlap_size=150)

    def test_chunk_text_basic(self, chunker, sample_markdown):
        """Test basic text chunking."""
        chunks = chunker.chunk_text(sample_markdown, "test.md")

        assert len(chunks) > 0
        assert all(isinstance(chunk, Chunk) for chunk in chunks)
        assert all(chunk.content.strip() for chunk in chunks)

        # Verify metadata
        for i, chunk in enumerate(chunks):
            assert chunk.metadata.chunk_index == i
            assert chunk.metadata.total_chunks == len(chunks)
            assert chunk.metadata.file_path == "test.md"
            assert chunk.metadata.token_count > 0
            assert chunk.metadata.char_count == len(chunk.content)

    def test_chunk_text_empty(self, chunker):
        """Test chunking empty text."""
        chunks = chunker.chunk_text("", "test.md")
        assert chunks == []

        chunks = chunker.chunk_text("   \n  \n  ", "test.md")
        assert chunks == []

    def test_chunk_file(self, chunker, sample_markdown):
        """Test chunking a file."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as tmp:
            tmp.write(sample_markdown)
            tmp_path = Path(tmp.name)

        try:
            chunks = chunker.chunk_file(tmp_path)

            assert len(chunks) > 0
            assert all(isinstance(chunk, Chunk) for chunk in chunks)
        finally:
            tmp_path.unlink()

    def test_chunk_file_not_found(self, chunker):
        """Test chunking non-existent file."""
        with pytest.raises(FileNotFoundError):
            chunker.chunk_file(Path("/nonexistent/file.md"))

    def test_chunk_file_empty(self, chunker):
        """Test chunking empty file."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as tmp:
            tmp.write("")
            tmp_path = Path(tmp.name)

        try:
            with pytest.raises(ValueError, match=MSG_EMPTY_CONTENT):
                chunker.chunk_file(tmp_path)
        finally:
            tmp_path.unlink()

    def test_header_extraction(self, chunker, sample_markdown):
        """Test that headers are properly extracted."""
        chunks = chunker.chunk_text(sample_markdown, "test.md")

        # At least one chunk should have headers
        assert any(chunk.metadata.headers for chunk in chunks)

        # Check that headers are hierarchical
        for chunk in chunks:
            if chunk.metadata.headers:
                # Headers should be strings
                assert all(isinstance(h, str) for h in chunk.metadata.headers)

    def test_chunk_size_constraints(self, chunker, large_markdown):
        """Test that chunks respect size constraints."""
        chunks = chunker.chunk_text(large_markdown, "test.md")

        for chunk in chunks:
            # Most chunks should be within the target range
            # (some may be slightly over if a single section is large)
            assert chunk.metadata.token_count <= chunker.max_chunk_size * 1.5

    def test_overlapping_chunks(self, chunker, sample_markdown):
        """Test that chunks have proper overlaps."""
        chunks = chunker.chunk_text(sample_markdown, "test.md")

        if len(chunks) > 1:
            # First chunk should not overlap with previous
            assert not chunks[0].metadata.overlap_with_previous
            # Last chunk should not overlap with next
            assert not chunks[-1].metadata.overlap_with_next

            # Middle chunks should have both overlaps marked
            for chunk in chunks[1:-1]:
                assert chunk.metadata.overlap_with_previous
                assert chunk.metadata.overlap_with_next

            # Check that overlap content is actually included
            for i in range(1, len(chunks)):
                current_content = chunks[i].content
                previous_content = chunks[i - 1].content

                # Current chunk should start with some text from previous chunk
                # (This is a heuristic check)
                if chunks[i].metadata.overlap_with_previous:
                    # Extract some words from end of previous chunk
                    prev_words = previous_content.split()[-10:]
                    curr_words = current_content.split()[:20]

                    # At least some overlap should exist
                    overlap_found = any(word in curr_words for word in prev_words)
                    assert overlap_found

    def test_chunk_ids_unique(self, chunker, sample_markdown):
        """Test that chunk IDs are unique."""
        chunks = chunker.chunk_text(sample_markdown, "test.md")

        chunk_ids = [chunk.metadata.chunk_id for chunk in chunks]
        assert len(chunk_ids) == len(set(chunk_ids))

    def test_line_numbers(self, chunker, sample_markdown):
        """Test that line numbers are tracked."""
        chunks = chunker.chunk_text(sample_markdown, "test.md")

        for chunk in chunks:
            assert chunk.metadata.start_line >= 0
            assert chunk.metadata.end_line >= chunk.metadata.start_line

    def test_split_by_headers(self, chunker):
        """Test header-based splitting."""
        text = """# Title

Content here.

## Section 1

Section 1 content.

### Subsection 1.1

Subsection content.

## Section 2

Section 2 content.
"""
        sections = chunker._split_by_headers(text)

        assert len(sections) > 0
        # Check that headers are properly tracked
        for section in sections:
            assert "headers" in section
            assert "content" in section
            assert isinstance(section["headers"], list)

    def test_token_estimation(self, chunker):
        """Test token estimation."""
        # Empty text
        assert chunker._estimate_tokens("") == 0

        # Short text (approximately 4 chars per token)
        text = "hello world"
        estimated = chunker._estimate_tokens(text)
        assert estimated > 0
        assert estimated == int(len(text) * 0.25)

        # Longer text
        long_text = "word " * 100
        estimated = chunker._estimate_tokens(long_text)
        assert estimated > 0

    def test_markdown_structure_preservation(self, chunker):
        """Test that markdown structure is preserved in chunks."""
        text = """# Main Title

## Section 1

- List item 1
- List item 2

```python
def hello():
    print("world")
```

## Section 2

> Quote here

**Bold text**
"""
        chunks = chunker.chunk_text(text, "test.md")

        # Combine all chunks and verify structure elements are preserved
        all_content = "\n".join(chunk.content for chunk in chunks)

        # Check for various markdown elements
        assert "#" in all_content  # Headers
        assert "-" in all_content or "•" in all_content  # Lists
        assert "```" in all_content or "def hello" in all_content  # Code blocks

    def test_large_section_splitting(self, chunker):
        """Test splitting of very large sections."""
        # Create a section larger than max chunk size
        large_section_text = "This is a very long line. " * 100

        text = f"""# Title

## Large Section

{large_section_text}

## Next Section

Small content.
"""
        chunks = chunker.chunk_text(text, "test.md")

        # Should produce multiple chunks
        assert len(chunks) > 1

        # All chunks should be reasonably sized (accounting for overlap)
        # Overlaps can make chunks larger, so allow for 2x max size
        for chunk in chunks:
            assert chunk.metadata.token_count <= chunker.max_chunk_size * 2.5

    def test_timestamp_generation(self, chunker, sample_markdown):
        """Test that timestamps are generated."""
        chunks = chunker.chunk_text(sample_markdown, "test.md")

        for chunk in chunks:
            assert chunk.metadata.timestamp
            # Should be ISO format
            assert "T" in chunk.metadata.timestamp or "-" in chunk.metadata.timestamp

    def test_multiple_header_levels(self, chunker):
        """Test handling of multiple header levels."""
        text = """# H1

## H2

### H3

#### H4

##### H5

###### H6

Regular text.
"""
        chunks = chunker.chunk_text(text, "test.md")

        # Should handle all header levels
        assert len(chunks) > 0

        # At least one chunk should have a header hierarchy
        has_hierarchy = any(len(chunk.metadata.headers) > 1 for chunk in chunks)
        assert has_hierarchy or len(chunks) == 1

    def test_no_headers(self, chunker):
        """Test chunking text with no headers."""
        text = """Just regular text without any headers.

Multiple paragraphs.

But no headers at all.
"""
        chunks = chunker.chunk_text(text, "test.md")

        assert len(chunks) > 0
        # Chunks without headers should have empty header lists
        for chunk in chunks:
            assert isinstance(chunk.metadata.headers, list)


class TestChunkerEdgeCases:
    """Tests for edge cases."""

    def test_single_line(self):
        """Test chunking single line."""
        chunker = MarkdownChunker(min_chunk_size=10, max_chunk_size=100, overlap_size=5)
        chunks = chunker.chunk_text("Single line of text.", "test.md")

        assert len(chunks) == 1
        assert chunks[0].content == "Single line of text."

    def test_only_headers(self):
        """Test chunking text with only headers."""
        chunker = MarkdownChunker(min_chunk_size=10, max_chunk_size=100, overlap_size=5)
        text = """# Header 1

## Header 2

### Header 3
"""
        chunks = chunker.chunk_text(text, "test.md")

        assert len(chunks) > 0

    def test_special_characters(self):
        """Test handling of special characters."""
        chunker = MarkdownChunker(min_chunk_size=10, max_chunk_size=100, overlap_size=5)
        text = """# Title with émojis 🚀

Content with special chars: @#$%^&*()

## Section with λ and π

More content.
"""
        chunks = chunker.chunk_text(text, "test.md")

        assert len(chunks) > 0
        # Special characters should be preserved
        all_content = "\n".join(chunk.content for chunk in chunks)
        assert "🚀" in all_content or "@#$%" in all_content

    def test_mixed_line_endings(self):
        """Test handling of mixed line endings."""
        chunker = MarkdownChunker(min_chunk_size=10, max_chunk_size=100, overlap_size=5)
        # Mix \n and \r\n
        text = "# Title\n\nContent here.\r\n\n## Section\r\nMore content."

        chunks = chunker.chunk_text(text, "test.md")
        assert len(chunks) > 0

    def test_very_small_chunks(self):
        """Test with very small chunk sizes."""
        chunker = MarkdownChunker(min_chunk_size=10, max_chunk_size=30, overlap_size=5)
        text = """# Title

This is some content that should be split into multiple small chunks.

## Section

More content here.
"""
        chunks = chunker.chunk_text(text, "test.md")

        # May produce one or more chunks depending on content size
        assert len(chunks) >= 1
        # Even small chunks should have metadata
        for chunk in chunks:
            assert chunk.metadata.chunk_id
            assert chunk.metadata.token_count > 0

    def test_unicode_content(self):
        """Test handling of unicode content."""
        chunker = MarkdownChunker(min_chunk_size=50, max_chunk_size=200, overlap_size=25)
        text = """# 中文标题

这是中文内容。

## Русский заголовок

Русский текст.

## عربي

نص عربي.
"""
        chunks = chunker.chunk_text(text, "test.md")

        assert len(chunks) > 0
        # Unicode should be preserved
        all_content = "\n".join(chunk.content for chunk in chunks)
        assert any(ord(c) > 127 for c in all_content)
