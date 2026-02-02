"""Thoth MCP Tools - Tool definitions for the MCP server.

This module contains all MCP tool definitions using FastMCP decorators.
Add new tools here to extend the MCP server capabilities.
"""

import os

from mcp.server.fastmcp import FastMCP

from thoth.shared.utils.logger import setup_logger
from thoth.shared.vector_store import VectorStore

logger = setup_logger(__name__)

# Initialize FastMCP instance
mcp = FastMCP("ThothHandbookServer")

# Global vector store (initialized lazily)
_vector_store: VectorStore | None = None


def get_vector_store() -> VectorStore:
    """Get or initialize the vector store."""
    global _vector_store  # noqa: PLW0603 - Intentional singleton pattern for Cloud Run
    if _vector_store is None:
        gcs_bucket = os.getenv("GCS_BUCKET_NAME")
        gcs_project = os.getenv("GCP_PROJECT_ID")

        logger.info("Initializing VectorStore for handbook_documents")
        _vector_store = VectorStore(
            persist_directory="/tmp/lancedb",  # nosec B108 - Temp storage for Cloud Run
            collection_name="handbook_documents",
            gcs_bucket_name=gcs_bucket,
            gcs_project_id=gcs_project,
        )
        doc_count = _vector_store.get_document_count()
        logger.info("Loaded handbook_documents: %d documents", doc_count)

    return _vector_store


# =============================================================================
# MCP Tools
# =============================================================================


@mcp.tool()
def list_tools() -> str:
    """List all available MCP tools and their descriptions.

    Returns:
        Formatted list of available tools with descriptions
    """
    tools_info = [
        (
            "search_handbook",
            "Search the GitLab Handbook for relevant content using semantic search",
        ),
        ("list_tools", "List all available MCP tools and their descriptions"),
        ("list_topics", "List all unique topics/sections available in the handbook"),
    ]

    output_parts = ["Available MCP Tools:\n"]
    for name, description in tools_info:
        output_parts.append(f"  - {name}: {description}")

    return "\n".join(output_parts)


@mcp.tool()
def list_topics() -> str:
    """List all unique topics/sections available in the handbook collection.

    Returns:
        Formatted list of topics with document counts
    """
    vector_store = get_vector_store()
    doc_count = vector_store.get_document_count()

    if doc_count == 0:
        return "The handbook collection is empty. No topics available."

    # Get all documents to extract unique sections
    results = vector_store.get_documents(limit=10000)

    if not results["metadatas"]:
        return "No metadata available to extract topics."

    # Count documents per section/topic
    section_counts: dict[str, int] = {}
    file_paths: set[str] = set()

    for metadata in results["metadatas"]:
        section = metadata.get("section", "Unknown")
        file_path = metadata.get("file_path", "")

        if section:
            section_counts[section] = section_counts.get(section, 0) + 1
        if file_path:
            file_paths.add(file_path)

    # Sort sections by count (descending)
    sorted_sections = sorted(section_counts.items(), key=lambda x: x[1], reverse=True)

    output_parts = [
        "Handbook Topics and Sections:\n",
        f"Total documents: {doc_count}",
        f"Total unique files: {len(file_paths)}",
        f"Total sections: {len(sorted_sections)}\n",
        "Sections (by document count):",
    ]

    for section, count in sorted_sections[:50]:  # Limit to top 50
        chunk_word = "chunk" if count == 1 else "chunks"
        output_parts.append(f"  - {section} ({count} {chunk_word})")

    if len(sorted_sections) > 50:
        output_parts.append(f"  ... and {len(sorted_sections) - 50} more sections")

    return "\n".join(output_parts)


@mcp.tool()
def search_handbook(query: str, num_results: int = 5) -> str:
    """Search the GitLab Handbook for relevant content.

    Args:
        query: Natural language search query
        num_results: Number of results to return (default: 5, max: 20)

    Returns:
        Formatted search results with relevant handbook sections
    """
    num_results = min(max(1, num_results), 20)

    vector_store = get_vector_store()
    results = vector_store.search_similar(query=query, n_results=num_results)

    if not results["documents"]:
        return "No results found for your query."

    output_parts = [f"Found {len(results['documents'])} results:\n"]

    for i, (doc, metadata, distance) in enumerate(
        zip(
            results["documents"],
            results["metadatas"],
            results["distances"],
            strict=True,
        )
    ):
        file_path = metadata.get("file_path", "Unknown")
        section = metadata.get("section", "")
        similarity = 1 - distance  # Convert distance to similarity score

        output_parts.append(f"--- Result {i + 1} (similarity: {similarity:.2f}) ---")
        output_parts.append(f"Source: {file_path}")
        if section:
            output_parts.append(f"Section: {section}")
        output_parts.append(f"\n{doc}\n")

    return "\n".join(output_parts)
