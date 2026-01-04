"""Vector store module for managing document embeddings using ChromaDB.

This module provides a wrapper around ChromaDB for storing and querying
document embeddings with CRUD operations.
"""

import logging
from pathlib import Path
from typing import Any

import chromadb
from chromadb.config import Settings

logger = logging.getLogger(__name__)


class VectorStore:
    """Vector store for managing document embeddings using ChromaDB.

    Provides CRUD operations for document storage and similarity search.
    """

    def __init__(
        self,
        persist_directory: str = "./chroma_db",
        collection_name: str = "thoth_documents",
    ):
        """Initialize the ChromaDB vector store.

        Args:
            persist_directory: Directory path for ChromaDB persistence
            collection_name: Name of the ChromaDB collection
        """
        self.persist_directory = Path(persist_directory)
        self.collection_name = collection_name

        # Create persist directory if it doesn't exist
        self.persist_directory.mkdir(parents=True, exist_ok=True)

        # Initialize ChromaDB client with persistence
        self.client = chromadb.PersistentClient(
            path=str(self.persist_directory),
            settings=Settings(anonymized_telemetry=False, allow_reset=True),
        )

        # Get or create collection
        self.collection = self.client.get_or_create_collection(
            name=self.collection_name, metadata={"hnsw:space": "cosine"}
        )

        logger.info(f"Initialized VectorStore with collection '{collection_name}' at '{persist_directory}'")

    def add_documents(
        self,
        documents: list[str],
        metadatas: list[dict[str, Any]] | None = None,
        ids: list[str] | None = None,
    ) -> None:
        """Add documents to the vector store.

        Args:
            documents: List of document texts to add
            metadatas: Optional list of metadata dicts for each document
            ids: Optional list of unique IDs for each document.
                 If not provided, IDs will be auto-generated.

        Raises:
            ValueError: If list lengths don't match
        """
        if not documents:
            logger.warning("No documents provided to add_documents")
            return

        # Validate input lengths
        if metadatas and len(metadatas) != len(documents):
            msg = f"Number of metadatas ({len(metadatas)}) must match number of documents ({len(documents)})"
            raise ValueError(msg)

        if ids and len(ids) != len(documents):
            msg = f"Number of ids ({len(ids)}) must match number of documents ({len(documents)})"
            raise ValueError(msg)
        if ids is None:
            # Get current count to generate sequential IDs
            current_count = self.collection.count()
            ids = [f"doc_{current_count + i}" for i in range(len(documents))]

        # Add documents to collection
        self.collection.add(
            documents=documents,
            metadatas=metadatas,  # type: ignore[arg-type]
            ids=ids,
        )

        logger.info(f"Added {len(documents)} documents to collection")

    def search_similar(
        self,
        query: str,
        n_results: int = 5,
        where: dict[str, Any] | None = None,
        where_document: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Search for similar documents using semantic similarity.

        Args:
            query: Query text to search for
            n_results: Number of results to return (default: 5)
            where: Optional metadata filter conditions
            where_document: Optional document content filter conditions

        Returns:
            Dict containing:
                - ids: List of document IDs
                - documents: List of document texts
                - metadatas: List of metadata dicts
                - distances: List of distance scores
        """
        results = self.collection.query(
            query_texts=[query],
            n_results=n_results,
            where=where,
            where_document=where_document,  # type: ignore[arg-type]
        )

        # Flatten results (ChromaDB returns nested lists)
        flattened_results = {
            "ids": results["ids"][0] if results["ids"] else [],
            "documents": results["documents"][0] if results["documents"] else [],
            "metadatas": results["metadatas"][0] if results["metadatas"] else [],
            "distances": results["distances"][0] if results["distances"] else [],
        }

        result_count = len(flattened_results["ids"])  # type: ignore[arg-type]
        logger.info(f"Search returned {result_count} results for query: '{query[:50]}...'")

        return flattened_results

    def delete_documents(self, ids: list[str] | None = None, where: dict[str, Any] | None = None) -> None:
        """Delete documents from the vector store.

        Args:
            ids: Optional list of document IDs to delete
            where: Optional metadata filter for documents to delete

        Raises:
            ValueError: If neither ids nor where is provided
        """
        if ids is None and where is None:
            msg = "Must provide either 'ids' or 'where' parameter"
            raise ValueError(msg)

        self.collection.delete(ids=ids, where=where)

        delete_desc = f"ids={ids}" if ids else f"where={where}"
        logger.info(f"Deleted documents matching {delete_desc}")

    def get_document_count(self) -> int:
        """Get the total number of documents in the collection.

        Returns:
            Number of documents in the collection
        """
        return self.collection.count()

    def get_documents(
        self,
        ids: list[str] | None = None,
        where: dict[str, Any] | None = None,
        limit: int | None = None,
    ) -> dict[str, Any]:
        """Retrieve documents from the vector store.

        Args:
            ids: Optional list of document IDs to retrieve
            where: Optional metadata filter
            limit: Optional maximum number of documents to return

        Returns:
            Dict containing:
                - ids: List of document IDs
                - documents: List of document texts
                - metadatas: List of metadata dicts
        """
        results = self.collection.get(ids=ids, where=where, limit=limit)

        logger.info(f"Retrieved {len(results['ids'])} documents")

        return results  # type: ignore[return-value]

    def reset(self) -> None:
        """Reset the collection by deleting all documents.

        Warning: This operation cannot be undone.
        """
        self.client.delete_collection(name=self.collection_name)
        self.collection = self.client.get_or_create_collection(
            name=self.collection_name, metadata={"hnsw:space": "cosine"}
        )
        logger.warning(f"Reset collection '{self.collection_name}'")
