"""Document chunking for multi-format ingestion.

This module provides intelligent chunking of documents that:
- Respects document structure (headers, paragraphs, sections)
- Maintains context through overlapping chunks
- Extracts metadata for each chunk
- Produces appropriately sized chunks (500-1000 tokens)
- Supports multiple formats via DocumentChunker

Research findings and strategy:
- Chunk size: 500-1000 tokens (balances context and granularity)
- Overlap: 100-200 tokens (ensures context continuity)
- Structure preservation: Split at header/paragraph boundaries when possible
- Metadata: File path, header hierarchy, timestamps, chunk IDs, source, format
"""

from dataclasses import dataclass, field
from datetime import datetime
import hashlib
import logging
from pathlib import Path
import re
from typing import Any

from thoth.shared.utils.logger import setup_logger

# Constants
DEFAULT_MIN_CHUNK_SIZE = 500  # Minimum tokens per chunk
DEFAULT_MAX_CHUNK_SIZE = 1000  # Maximum tokens per chunk
DEFAULT_OVERLAP_SIZE = 150  # Overlap size in tokens
APPROX_TOKENS_PER_CHAR = 0.25  # Approximate conversion (4 chars per token)

# Error messages
MSG_INVALID_FILE = "Invalid file path: {path}"
MSG_CHUNK_FAILED = "Failed to chunk file: {path}"
MSG_EMPTY_CONTENT = "Empty content provided for chunking"
MSG_INVALID_OVERLAP = "Overlap size must be less than minimum chunk size"


@dataclass
class ChunkMetadata:
    """Metadata for a document chunk."""

    chunk_id: str
    file_path: str
    chunk_index: int
    total_chunks: int
    headers: list[str] = field(default_factory=list)
    start_line: int = 0
    end_line: int = 0
    token_count: int = 0
    char_count: int = 0
    timestamp: str = field(default_factory=lambda: datetime.now().astimezone().isoformat())
    overlap_with_previous: bool = False
    overlap_with_next: bool = False
    source: str = ""  # Source identifier (e.g., 'handbook', 'dnd', 'personal')
    format: str = ""  # Document format (e.g., 'markdown', 'pdf', 'text', 'docx')

    def to_dict(self) -> dict[str, Any]:
        """Convert metadata to a dict suitable for vector store metadata columns.

        Ensures all values are store-compatible types (str, int, float, bool).
        Lists (e.g., headers) are converted to comma-separated strings.

        Returns:
            Dict with chunk_id, file_path, chunk_index, total_chunks, headers (str),
            start_line, end_line, token_count, char_count, timestamp, overlap flags,
            source, format.
        """

        def sanitize_value(value: Any) -> str | int | float | bool:
            """Convert a value to a type supported by LanceDB/vector store metadata."""
            if isinstance(value, (str, int, float, bool)):
                return value
            if isinstance(value, list):
                # Convert lists to comma-separated strings
                return ", ".join(str(v) for v in value)
            if value is None:
                return ""
            # Convert anything else to string
            return str(value)

        raw_dict = {
            "chunk_id": self.chunk_id,
            "file_path": self.file_path,
            "chunk_index": self.chunk_index,
            "total_chunks": self.total_chunks,
            "headers": ", ".join(self.headers) if self.headers else "",
            "start_line": self.start_line,
            "end_line": self.end_line,
            "token_count": self.token_count,
            "char_count": self.char_count,
            "timestamp": self.timestamp,
            "overlap_with_previous": self.overlap_with_previous,
            "overlap_with_next": self.overlap_with_next,
            "source": self.source,
            "format": self.format,
        }

        # Sanitize all values so metadata is compatible with LanceDB/vector store.
        return {k: sanitize_value(v) for k, v in raw_dict.items()}


@dataclass
class Chunk:
    """Represents a chunk of markdown content with metadata."""

    content: str
    metadata: ChunkMetadata

    def to_dict(self) -> dict[str, Any]:
        """Convert chunk to dictionary."""
        return {
            "content": self.content,
            "metadata": self.metadata.to_dict(),
        }


class MarkdownChunker:
    """Intelligent markdown-aware chunking.

    This chunker respects markdown structure and maintains context through
    overlapping chunks. It extracts metadata for each chunk to enable
    efficient retrieval and context-aware processing.
    """

    def __init__(
        self,
        min_chunk_size: int = DEFAULT_MIN_CHUNK_SIZE,
        max_chunk_size: int = DEFAULT_MAX_CHUNK_SIZE,
        overlap_size: int = DEFAULT_OVERLAP_SIZE,
        logger: logging.Logger | logging.LoggerAdapter | None = None,
    ):
        """Initialize the markdown chunker.

        Args:
            min_chunk_size: Minimum chunk size in tokens
            max_chunk_size: Maximum chunk size in tokens
            overlap_size: Number of tokens to overlap between chunks
            logger: Logger instance
        """
        self.min_chunk_size = min_chunk_size
        self.max_chunk_size = max_chunk_size
        self.overlap_size = overlap_size
        self.logger = logger or setup_logger(__name__)

        # Validate configuration
        if self.overlap_size >= self.min_chunk_size:
            msg = MSG_INVALID_OVERLAP
            raise ValueError(msg)

    def chunk_file(self, file_path: Path) -> list[Chunk]:
        """Chunk a markdown file.

        Args:
            file_path: Path to the markdown file

        Returns:
            List of chunks with metadata

        Raises:
            FileNotFoundError: If file doesn't exist
            ValueError: If file is empty or invalid
        """
        if not file_path.exists():
            raise FileNotFoundError(MSG_INVALID_FILE.format(path=file_path))

        try:
            content = file_path.read_text(encoding="utf-8")
            if not content.strip():
                raise ValueError(MSG_EMPTY_CONTENT)

            return self.chunk_text(content, str(file_path))

        except Exception:
            self.logger.exception(MSG_CHUNK_FAILED.format(path=file_path))
            raise

    def chunk_text(self, text: str, source_path: str = "") -> list[Chunk]:
        """Chunk markdown text content.

        Args:
            text: Markdown text to chunk
            source_path: Source file path for metadata

        Returns:
            List of chunks with metadata
        """
        self.logger.debug(f"Chunking text from {source_path} ({len(text)} chars)")
        if not text.strip():
            return []

        # Split into sections by headers
        sections = self._split_by_headers(text)

        # Group sections into chunks
        chunk_groups = self._group_into_chunks(sections)

        # Create chunks with metadata
        chunks = self._create_chunks(chunk_groups, source_path)

        self.logger.debug(f"Created {len(chunks)} chunks for {source_path}")
        # Add overlaps
        return self._add_overlaps(chunks)

    def _split_by_headers(self, text: str) -> list[dict[str, Any]]:
        """Split text into sections by markdown headers.

        Args:
            text: Markdown text

        Returns:
            List of sections with header information
        """
        sections = []
        lines = text.split("\n")
        current_section: dict[str, Any] = {
            "headers": [],
            "content": [],
            "start_line": 0,
        }
        header_stack: list[tuple[int, str]] = []  # (level, text)

        for line_num, line in enumerate(lines, start=1):
            # Check if line is a header
            header_match = re.match(r"^(#{1,6})\s+(.+)$", line)

            if header_match:
                # Save previous section if it has content
                if current_section["content"]:
                    current_section["end_line"] = line_num - 1
                    sections.append(current_section)

                # Update header stack
                level = len(header_match.group(1))
                header_text = header_match.group(2).strip()

                # Pop headers of same or greater level
                while header_stack and header_stack[-1][0] >= level:
                    header_stack.pop()

                # Add new header
                header_stack.append((level, header_text))

                # Start new section
                current_section = {
                    "headers": [h[1] for h in header_stack],
                    "content": [line],
                    "start_line": line_num,
                }
            else:
                current_section["content"].append(line)

        # Add final section
        if current_section["content"]:
            current_section["end_line"] = len(lines)
            sections.append(current_section)

        return sections

    def _group_into_chunks(self, sections: list[dict[str, Any]]) -> list[list[dict[str, Any]]]:
        """Group sections into appropriately sized chunks.

        Args:
            sections: List of sections from _split_by_headers

        Returns:
            List of chunk groups (each group is a list of sections)
        """
        chunks: list[list[dict[str, Any]]] = []
        current_chunk: list[dict[str, Any]] = []
        current_token_count = 0

        for section in sections:
            section_text = "\n".join(section["content"])
            section_tokens = self._estimate_tokens(section_text)

            # If section alone exceeds max size, split it further
            if section_tokens > self.max_chunk_size:
                # Save current chunk if not empty
                if current_chunk:
                    chunks.append(current_chunk)
                    current_chunk = []
                    current_token_count = 0

                # Split large section
                split_sections = self._split_large_section(section)
                chunks.extend([split_section] for split_section in split_sections)

                continue

            # Check if adding this section would exceed max size
            if current_token_count + section_tokens > self.max_chunk_size:
                # Only save if we meet minimum size or it's our only option
                if current_token_count >= self.min_chunk_size or not current_chunk:
                    chunks.append(current_chunk)
                    current_chunk = [section]
                    current_token_count = section_tokens
                else:
                    # Add section anyway if we haven't met minimum
                    current_chunk.append(section)
                    current_token_count += section_tokens
            else:
                current_chunk.append(section)
                current_token_count += section_tokens

        # Add final chunk
        if current_chunk:
            chunks.append(current_chunk)

        return chunks

    def _split_large_section(self, section: dict[str, Any]) -> list[dict[str, Any]]:
        """Split a large section that exceeds max chunk size.

        Args:
            section: Section to split

        Returns:
            List of smaller sections
        """
        content_lines = section["content"]
        sections: list[dict[str, Any]] = []
        current_lines: list[str] = []
        current_tokens = 0
        start_line = section["start_line"]

        for _i, line in enumerate(content_lines):
            line_tokens = self._estimate_tokens(line)

            if current_tokens + line_tokens > self.max_chunk_size and current_lines:
                # Create a section from current lines
                sections.append(
                    {
                        "headers": section["headers"],
                        "content": current_lines,
                        "start_line": start_line,
                        "end_line": start_line + len(current_lines) - 1,
                    }
                )
                current_lines = [line]
                current_tokens = line_tokens
                start_line += len(sections[-1]["content"])
            else:
                current_lines.append(line)
                current_tokens += line_tokens

        # Add remaining lines
        if current_lines:
            sections.append(
                {
                    "headers": section["headers"],
                    "content": current_lines,
                    "start_line": start_line,
                    "end_line": start_line + len(current_lines) - 1,
                }
            )

        return sections

    def _create_chunks(self, chunk_groups: list[list[dict[str, Any]]], source_path: str) -> list[Chunk]:
        """Create Chunk objects with metadata.

        Args:
            chunk_groups: Grouped sections
            source_path: Source file path

        Returns:
            List of Chunk objects
        """
        chunks = []
        total_chunks = len(chunk_groups)

        for idx, group in enumerate(chunk_groups):
            # Combine all sections in the group
            content_lines = []
            headers: list[str] = []
            start_line = float("inf")
            end_line = 0

            for section in group:
                content_lines.extend(section["content"])
                if section["headers"] and not headers:
                    headers = section["headers"]
                start_line = min(start_line, section.get("start_line", 0))
                end_line = max(end_line, section.get("end_line", 0))

            content = "\n".join(content_lines)
            token_count = self._estimate_tokens(content)

            # Generate chunk ID
            chunk_id = self._generate_chunk_id(source_path, idx, content)

            # Create metadata
            metadata = ChunkMetadata(
                chunk_id=chunk_id,
                file_path=source_path,
                chunk_index=idx,
                total_chunks=total_chunks,
                headers=headers,
                start_line=int(start_line) if start_line != float("inf") else 0,
                end_line=end_line,
                token_count=token_count,
                char_count=len(content),
            )

            chunks.append(Chunk(content=content, metadata=metadata))

        return chunks

    def _add_overlaps(self, chunks: list[Chunk]) -> list[Chunk]:
        """Add overlapping content between chunks.

        Args:
            chunks: List of chunks

        Returns:
            List of chunks with overlaps
        """
        if len(chunks) <= 1:
            return chunks

        overlapped_chunks = []

        for i, chunk in enumerate(chunks):
            content = chunk.content
            metadata = chunk.metadata

            # Add overlap from previous chunk
            if i > 0:
                prev_content = chunks[i - 1].content
                overlap = self._get_overlap_text(prev_content, is_end=True)
                if overlap:
                    content = overlap + "\n\n" + content
                    metadata.overlap_with_previous = True

            # Add overlap to next chunk (mark metadata only)
            if i < len(chunks) - 1:
                metadata.overlap_with_next = True

            # Update token and char counts
            metadata.token_count = self._estimate_tokens(content)
            metadata.char_count = len(content)

            overlapped_chunks.append(Chunk(content=content, metadata=metadata))

        return overlapped_chunks

    def _get_overlap_text(self, text: str, is_end: bool = True) -> str:
        """Extract overlap text from the end or beginning of content.

        Args:
            text: Text to extract from
            is_end: If True, extract from end; if False, extract from beginning

        Returns:
            Overlap text
        """
        target_tokens = self.overlap_size
        lines = text.split("\n")

        if is_end:
            lines = list(reversed(lines))

        overlap_lines: list[str] = []
        current_tokens = 0

        for line in lines:
            line_tokens = self._estimate_tokens(line)
            if current_tokens + line_tokens > target_tokens and overlap_lines:
                break
            overlap_lines.append(line)
            current_tokens += line_tokens

        if is_end:
            overlap_lines = list(reversed(overlap_lines))

        return "\n".join(overlap_lines)

    def _estimate_tokens(self, text: str) -> int:
        """Estimate token count for text.

        Uses simple approximation: ~4 characters per token.

        Args:
            text: Text to estimate

        Returns:
            Estimated token count
        """
        return int(len(text) * APPROX_TOKENS_PER_CHAR)

    def _generate_chunk_id(self, file_path: str, index: int, content: str) -> str:
        """Generate unique ID for a chunk.

        Args:
            file_path: Source file path
            index: Chunk index
            content: Chunk content

        Returns:
            Unique chunk ID
        """
        # Create hash from file path, index, and content snippet
        hash_input = f"{file_path}:{index}:{content[:100]}"
        hash_digest = hashlib.sha256(hash_input.encode()).hexdigest()
        return f"chunk_{index}_{hash_digest[:8]}"


class DocumentChunker:
    """Generalized document chunker for multi-format support.

    This chunker uses MarkdownChunker for markdown files and provides
    generic paragraph-based chunking for other formats (PDF, text, docx).

    Example:
        >>> from thoth.ingestion.parsers import ParserFactory
        >>> chunker = DocumentChunker()
        >>> parsed_doc = ParserFactory.parse(Path("document.pdf"))
        >>> chunks = chunker.chunk_document(parsed_doc, source="dnd")
    """

    def __init__(
        self,
        min_chunk_size: int = DEFAULT_MIN_CHUNK_SIZE,
        max_chunk_size: int = DEFAULT_MAX_CHUNK_SIZE,
        overlap_size: int = DEFAULT_OVERLAP_SIZE,
        logger: logging.Logger | logging.LoggerAdapter | None = None,
    ):
        """Initialize the document chunker.

        Args:
            min_chunk_size: Minimum chunk size in tokens
            max_chunk_size: Maximum chunk size in tokens
            overlap_size: Number of tokens to overlap between chunks
            logger: Logger instance
        """
        self.min_chunk_size = min_chunk_size
        self.max_chunk_size = max_chunk_size
        self.overlap_size = overlap_size
        self.logger = logger or setup_logger(__name__)

        # Use MarkdownChunker for markdown-specific processing
        self._markdown_chunker = MarkdownChunker(
            min_chunk_size=min_chunk_size,
            max_chunk_size=max_chunk_size,
            overlap_size=overlap_size,
            logger=self.logger,
        )

    def chunk_document(
        self,
        content: str,
        source_path: str,
        source: str = "",
        doc_format: str = "",
    ) -> list[Chunk]:
        """Chunk a document based on its format.

        Args:
            content: Document text content
            source_path: Source file path for metadata
            source: Source identifier (e.g., 'handbook', 'dnd')
            doc_format: Document format (e.g., 'markdown', 'pdf', 'text', 'docx')

        Returns:
            List of chunks with metadata including source and format
        """
        self.logger.debug(f"Chunking document {source_path} (format: {doc_format}, length: {len(content)})")
        if not content.strip():
            return []

        # Use markdown-aware chunking for markdown format
        if doc_format == "markdown":
            chunks = self._markdown_chunker.chunk_text(content, source_path)
        else:
            # Use generic paragraph-based chunking for other formats
            chunks = self._chunk_plain_text(content, source_path)

        # Add source and format to all chunk metadata
        for chunk in chunks:
            chunk.metadata.source = source
            chunk.metadata.format = doc_format

        self.logger.debug(f"Created {len(chunks)} chunks for {source_path}")
        return chunks

    def chunk_file(self, file_path: Path, source: str = "", doc_format: str = "markdown") -> list[Chunk]:
        """Chunk a file directly (for backward compatibility).

        Args:
            file_path: Path to the file
            source: Source identifier
            doc_format: Document format

        Returns:
            List of chunks with metadata
        """
        if not file_path.exists():
            raise FileNotFoundError(MSG_INVALID_FILE.format(path=file_path))

        content = file_path.read_text(encoding="utf-8")
        return self.chunk_document(content, str(file_path), source, doc_format)

    def _chunk_plain_text(self, text: str, source_path: str) -> list[Chunk]:
        """Chunk plain text by paragraphs.

        This is used for non-markdown formats (PDF, text, docx).

        Args:
            text: Plain text content
            source_path: Source file path for metadata

        Returns:
            List of chunks
        """
        # Split by double newlines (paragraphs) or page markers
        paragraphs = re.split(r"\n\n+|\[Page \d+\]\n", text)
        paragraphs = [p.strip() for p in paragraphs if p.strip()]

        if not paragraphs:
            return []

        # Group paragraphs into chunks
        chunk_groups = self._group_paragraphs(paragraphs)

        # Create chunks with metadata
        chunks = []
        total_chunks = len(chunk_groups)

        for idx, para_group in enumerate(chunk_groups):
            content = "\n\n".join(para_group)
            token_count = self._estimate_tokens(content)
            chunk_id = self._generate_chunk_id(source_path, idx, content)

            metadata = ChunkMetadata(
                chunk_id=chunk_id,
                file_path=source_path,
                chunk_index=idx,
                total_chunks=total_chunks,
                headers=[],  # Non-markdown formats don't have headers
                token_count=token_count,
                char_count=len(content),
            )

            chunks.append(Chunk(content=content, metadata=metadata))

        # Add overlaps
        return self._add_overlaps(chunks)

    def _group_paragraphs(self, paragraphs: list[str]) -> list[list[str]]:
        """Group paragraphs into appropriately sized chunks.

        Args:
            paragraphs: List of paragraphs

        Returns:
            List of paragraph groups
        """
        groups: list[list[str]] = []
        current_group: list[str] = []
        current_tokens = 0

        for para in paragraphs:
            para_tokens = self._estimate_tokens(para)

            # If paragraph alone exceeds max size, split it
            if para_tokens > self.max_chunk_size:
                if current_group:
                    groups.append(current_group)
                    current_group = []
                    current_tokens = 0

                # Split large paragraph by sentences
                split_paras = self._split_large_paragraph(para)
                groups.extend([[sp] for sp in split_paras])
                continue

            # Check if adding this paragraph exceeds max size
            if current_tokens + para_tokens > self.max_chunk_size:
                if current_tokens >= self.min_chunk_size:
                    groups.append(current_group)
                    current_group = [para]
                    current_tokens = para_tokens
                else:
                    current_group.append(para)
                    current_tokens += para_tokens
            else:
                current_group.append(para)
                current_tokens += para_tokens

        if current_group:
            groups.append(current_group)

        return groups

    def _split_large_paragraph(self, paragraph: str) -> list[str]:
        """Split a large paragraph by sentences.

        Args:
            paragraph: Large paragraph to split

        Returns:
            List of smaller text segments
        """
        # Simple sentence splitting
        sentences = re.split(r"(?<=[.!?])\s+", paragraph)
        segments: list[str] = []
        current_segment: list[str] = []
        current_tokens = 0

        for sentence in sentences:
            sentence_tokens = self._estimate_tokens(sentence)

            if current_tokens + sentence_tokens > self.max_chunk_size and current_segment:
                segments.append(" ".join(current_segment))
                current_segment = [sentence]
                current_tokens = sentence_tokens
            else:
                current_segment.append(sentence)
                current_tokens += sentence_tokens

        if current_segment:
            segments.append(" ".join(current_segment))

        return segments

    def _add_overlaps(self, chunks: list[Chunk]) -> list[Chunk]:
        """Add overlapping content between chunks.

        Args:
            chunks: List of chunks

        Returns:
            List of chunks with overlaps
        """
        if len(chunks) <= 1:
            return chunks

        overlapped_chunks = []

        for i, chunk in enumerate(chunks):
            content = chunk.content
            metadata = chunk.metadata

            # Add overlap from previous chunk
            if i > 0:
                prev_content = chunks[i - 1].content
                overlap = self._get_overlap_text(prev_content)
                if overlap:
                    content = overlap + "\n\n" + content
                    metadata.overlap_with_previous = True

            # Mark overlap with next
            if i < len(chunks) - 1:
                metadata.overlap_with_next = True

            # Update counts
            metadata.token_count = self._estimate_tokens(content)
            metadata.char_count = len(content)

            overlapped_chunks.append(Chunk(content=content, metadata=metadata))

        return overlapped_chunks

    def _get_overlap_text(self, text: str) -> str:
        """Extract overlap text from the end of content.

        Args:
            text: Text to extract overlap from

        Returns:
            Overlap text
        """
        target_tokens = self.overlap_size
        lines = text.split("\n")
        lines = list(reversed(lines))

        overlap_lines: list[str] = []
        current_tokens = 0

        for line in lines:
            line_tokens = self._estimate_tokens(line)
            if current_tokens + line_tokens > target_tokens and overlap_lines:
                break
            overlap_lines.append(line)
            current_tokens += line_tokens

        return "\n".join(reversed(overlap_lines))

    def _estimate_tokens(self, text: str) -> int:
        """Estimate token count for text."""
        return int(len(text) * APPROX_TOKENS_PER_CHAR)

    def _generate_chunk_id(self, file_path: str, index: int, content: str) -> str:
        """Generate unique ID for a chunk."""
        hash_input = f"{file_path}:{index}:{content[:100]}"
        hash_digest = hashlib.sha256(hash_input.encode()).hexdigest()
        return f"chunk_{index}_{hash_digest[:8]}"
