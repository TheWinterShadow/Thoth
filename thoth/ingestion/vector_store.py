"""Vector store module for managing document embeddings using ChromaDB.

This module provides a wrapper around ChromaDB for storing and querying
document embeddings with CRUD operations and optional S3 backup.
"""

import importlib.util
import logging
from pathlib import Path
from typing import Any

import chromadb
from chromadb.config import Settings

from thoth.ingestion.embedder import Embedder

logger = logging.getLogger(__name__)


class VectorStore:
    """Vector store for managing document embeddings using ChromaDB.

    Provides CRUD operations for document storage, similarity search,
    and optional Amazon S3 backup/restore.
    """

    def __init__(
        self,
        persist_directory: str = "./chroma_db",
        collection_name: str = "thoth_documents",
        embedder: Embedder | None = None,
        s3_bucket_name: str | None = None,
        s3_region: str | None = None,
    ):
        """Initialize the ChromaDB vector store.

        Args:
            persist_directory: Directory path for ChromaDB persistence
            collection_name: Name of the ChromaDB collection
            embedder: Optional Embedder instance for generating embeddings.
                If not provided, a default Embedder with all-MiniLM-L6-v2 will be created.
            s3_bucket_name: Optional S3 bucket name for cloud backup
            s3_region: Optional AWS region for S3 (defaults to us-east-1)
        """
        self.persist_directory = Path(persist_directory)
        self.collection_name = collection_name

        # Initialize or use provided embedder
        self.embedder = embedder or Embedder(model_name="all-MiniLM-L6-v2")

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

        # Initialize S3 sync if bucket is provided
        self.s3_sync = None
        if s3_bucket_name:
            # Check if S3 module is available
            if importlib.util.find_spec("boto3") is not None:
                try:
                    from thoth.ingestion.s3_sync import S3Sync  # noqa: PLC0415

                    self.s3_sync = S3Sync(
                        bucket_name=s3_bucket_name,
                        region=s3_region,
                    )
                    logger.info(f"S3 sync enabled with bucket: {s3_bucket_name}")
                except ImportError as e:
                    logger.warning(f"Failed to initialize S3 sync: {e}")
                    self.s3_sync = None
            else:
                logger.warning("boto3 not installed, S3 sync disabled")
                self.s3_sync = None

        logger.info(f"Initialized VectorStore with collection '{collection_name}' at '{persist_directory}'")
        logger.info(f"Using embedder: {self.embedder.model_name}")

    def add_documents(
        self,
        documents: list[str],
        metadatas: list[dict[str, Any]] | None = None,
        ids: list[str] | None = None,
        embeddings: list[list[float]] | None = None,
    ) -> None:
        """Add documents to the vector store.

        Args:
            documents: List of document texts to add
            metadatas: Optional list of metadata dicts for each document
            ids: Optional list of unique IDs for each document.
                 If not provided, IDs will be auto-generated.
            embeddings: Optional pre-computed embeddings. If not provided,
                embeddings will be generated using the configured Embedder.

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

        if embeddings and len(embeddings) != len(documents):
            msg = f"Number of embeddings ({len(embeddings)}) must match number of documents ({len(documents)})"
            raise ValueError(msg)

        if ids is None:
            # Get current count to generate sequential IDs
            current_count = self.collection.count()
            ids = [f"doc_{current_count + i}" for i in range(len(documents))]

        # Generate embeddings if not provided
        if embeddings is None:
            logger.info(f"Generating embeddings for {len(documents)} documents")
            embeddings = self.embedder.embed(documents, show_progress=True)

        # Add documents to collection
        self.collection.add(
            documents=documents,
            metadatas=metadatas,  # type: ignore[arg-type]
            ids=ids,
            embeddings=embeddings,  # type: ignore[arg-type]
        )

        logger.info(f"Added {len(documents)} documents to collection")

    def search_similar(
        self,
        query: str,
        n_results: int = 5,
        where: dict[str, Any] | None = None,
        where_document: dict[str, Any] | None = None,
        query_embedding: list[float] | None = None,
    ) -> dict[str, Any]:
        """Search for similar documents using semantic similarity.

        Args:
            query: Query text to search for
            n_results: Number of results to return (default: 5)
            where: Optional metadata filter conditions
            where_document: Optional document content filter conditions
            query_embedding: Optional pre-computed query embedding. If not provided,
                embedding will be generated from the query text.

        Returns:
            Dict containing:
                - ids: List of document IDs
                - documents: List of document texts
                - metadatas: List of metadata dicts
                - distances: List of distance scores
        """
        # Generate query embedding if not provided
        if query_embedding is None:
            query_embedding = self.embedder.embed_single(query)

        results = self.collection.query(
            query_embeddings=[query_embedding],  # type: ignore[arg-type]
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

    def delete_by_file_path(self, file_path: str) -> int:
        """Delete all documents associated with a specific file path.

        Args:
            file_path: The file path to match in metadata

        Returns:
            Number of documents deleted

        Raises:
            Exception: If deletion fails
        """
        try:
            # First, get count of documents to delete
            existing = self.collection.get(where={"file_path": file_path})
            count = len(existing["ids"])

            if count == 0:
                logger.info(f"No documents found for file path: {file_path}")
                return 0

            # Delete all documents with matching file_path
            self.collection.delete(where={"file_path": file_path})

            logger.info(f"Deleted {count} documents for file path: {file_path}")
            return count

        except Exception:
            logger.exception(f"Failed to delete documents for file path: {file_path}")
            raise

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

    def backup_to_s3(self, backup_name: str | None = None) -> str | None:
        """Backup vector store to Amazon S3.

        Args:
            backup_name: Optional name for the backup (defaults to timestamp)

        Returns:
            S3 prefix of the backup, or None if S3 sync not configured

        Raises:
            Exception: If backup fails
        """
        if not self.s3_sync:
            logger.warning("S3 sync not configured. Cannot backup to S3.")
            return None

        try:
            prefix = self.s3_sync.backup_to_s3(self.persist_directory, backup_name=backup_name)
            logger.info(f"Successfully backed up to S3: {prefix}")
            return prefix
        except Exception:
            logger.exception("Failed to backup to S3")
            raise

    def restore_from_s3(
        self,
        backup_name: str | None = None,
        s3_prefix: str | None = None,
    ) -> int:
        """Restore vector store from Amazon S3.

        Args:
            backup_name: Name of backup to restore (looks in backups/ folder)
            s3_prefix: Direct S3 prefix to restore from

        Returns:
            Number of files restored

        Raises:
            ValueError: If neither backup_name nor s3_prefix is provided
            Exception: If restore fails
        """
        if not self.s3_sync:
            logger.warning("S3 sync not configured. Cannot restore from S3.")
            return 0

        try:
            if backup_name:
                count = self.s3_sync.restore_from_backup(backup_name, self.persist_directory, clean_local=True)
            elif s3_prefix:
                result = self.s3_sync.sync_from_s3(s3_prefix, self.persist_directory, clean_local=True)
                downloaded = result["downloaded_files"]
                count = downloaded if isinstance(downloaded, int) else 0
            else:
                msg = "Must provide either backup_name or s3_prefix"
                raise ValueError(msg)

            logger.info(f"Successfully restored {count} files from S3")

            # Reinitialize ChromaDB client after restore
            self.client = chromadb.PersistentClient(
                path=str(self.persist_directory),
                settings=Settings(anonymized_telemetry=False, allow_reset=True),
            )
            self.collection = self.client.get_or_create_collection(
                name=self.collection_name, metadata={"hnsw:space": "cosine"}
            )

            return count
        except Exception:
            logger.exception("Failed to restore from GCS")
            raise

    def sync_to_s3(self, s3_prefix: str = "chroma_db") -> dict | None:
        """Sync vector store to Amazon S3.

        Args:
            s3_prefix: Prefix in S3 bucket (default: chroma_db)

        Returns:
            Sync statistics dict, or None if S3 sync not configured

        Raises:
            Exception: If sync fails
        """
        if not self.s3_sync:
            logger.warning("S3 sync not configured. Cannot sync to S3.")
            return None

        try:
            result = self.s3_sync.sync_to_s3(self.persist_directory, s3_prefix=s3_prefix)
            logger.info(f"Successfully synced to S3: {result}")
            return result
        except Exception:
            logger.exception("Failed to sync to S3")
            raise

    def list_s3_backups(self) -> list[str]:
        """List available backups in Amazon S3.

        Returns:
            List of backup names, or empty list if S3 sync not configured

        Raises:
            Exception: If listing fails
        """
        if not self.s3_sync:
            logger.warning("S3 sync not configured.")
            return []

        try:
            backups = self.s3_sync.list_backups()
            logger.info(f"Found {len(backups)} backups in S3")
            return backups
        except Exception:
            logger.exception("Failed to list S3 backups")
            raise
