"""Handbook RAG plugin for semantic search over handbook content."""

import logging
import os
from pathlib import Path
import tempfile
from typing import Any

from thoth.ingestion.vector_store import VectorStore
from thoth.mcp_server.plugins.base import BaseRAGPlugin

logger = logging.getLogger(__name__)


class HandbookRAGPlugin(BaseRAGPlugin):
    """RAG plugin for handbook content using ChromaDB vector store."""

    def __init__(self, name: str = "handbook", version: str = "1.0.0"):
        """Initialize handbook RAG plugin.

        Args:
            name: Plugin name
            version: Plugin version
        """
        super().__init__(name, version)
        self.vector_store: VectorStore | None = None
        self.config: dict[str, Any] = {}

    def initialize(self, config: dict[str, Any] | None = None) -> None:
        """Initialize the handbook RAG plugin.

        Args:
            config: Configuration dictionary with:
                - persist_directory: Path to ChromaDB directory (default: /tmp/chroma_db)
                - collection_name: ChromaDB collection name (default: thoth_documents)
                - s3_bucket_name: Optional S3 bucket for backup
                - s3_region: Optional AWS region for S3
        """
        self.config = config or {}

        # Get configuration values
        # Use secure temp directory if not specified
        default_temp_dir = str(Path(tempfile.gettempdir()) / "chroma_db")
        persist_directory = self.config.get(
            "persist_directory",
            os.getenv("CHROMA_DB_PATH", default_temp_dir),
        )
        collection_name = self.config.get("collection_name", "thoth_documents")
        s3_bucket_name = self.config.get("s3_bucket_name") or os.getenv("S3_BUCKET_NAME")
        s3_region = self.config.get("s3_region") or os.getenv("AWS_REGION", "us-east-1")

        # Initialize vector store
        try:
            self.vector_store = VectorStore(
                persist_directory=persist_directory,
                collection_name=collection_name,
                s3_bucket_name=s3_bucket_name,
                s3_region=s3_region,
            )
            logger.info(f"Initialized HandbookRAGPlugin with collection '{collection_name}'")
        except Exception:
            logger.exception("Failed to initialize vector store")
            raise

    def cleanup(self) -> None:
        """Clean up plugin resources."""
        self.vector_store = None
        logger.info("Cleaned up HandbookRAGPlugin")

    def search(
        self,
        query: str,
        n_results: int = 5,
        filters: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        """Perform semantic search over handbook content.

        Args:
            query: Search query text
            n_results: Number of results to return
            filters: Optional metadata filters (where clause)

        Returns:
            List of search results with 'text', 'metadata', 'score' keys
        """
        if not self.vector_store:
            msg = "Plugin not initialized. Call initialize() first."
            raise RuntimeError(msg)

        try:
            # Perform semantic search using vector store
            results = self.vector_store.search_similar(
                query=query,
                n_results=n_results,
                where=filters,
            )

            # Format results into standardized structure
            # Convert ChromaDB result format to our plugin's expected format
            formatted_results = []
            for i, doc_id in enumerate(results.get("ids", [])):
                # Extract document text, handling missing entries gracefully
                doc_text = results.get("documents", [])[i] if i < len(results.get("documents", [])) else ""
                # Extract metadata, handling missing entries gracefully
                doc_metadata = results.get("metadatas", [])[i] if i < len(results.get("metadatas", [])) else {}
                # Convert distance to similarity score (1.0 - distance)
                # Higher scores indicate better matches
                similarity_score = (
                    1.0 - results.get("distances", [])[i] if i < len(results.get("distances", [])) else 0.0
                )
                formatted_results.append(
                    {
                        "id": doc_id,
                        "text": doc_text,
                        "metadata": doc_metadata,
                        "score": similarity_score,
                    }
                )

            return formatted_results

        except Exception:
            logger.exception("Search failed")
            raise

    def get_vector_store(self) -> Any:
        """Get the underlying vector store instance.

        Returns:
            VectorStore instance
        """
        return self.vector_store
