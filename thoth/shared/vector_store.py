"""Vector store module for managing document embeddings using ChromaDB.

This module provides a wrapper around ChromaDB for storing and querying
document embeddings with CRUD operations and optional GCS backup.
"""

import importlib.util
import logging
from pathlib import Path
from typing import Any, cast

import chromadb
from chromadb.config import Settings

from thoth.shared.embedder import Embedder
from thoth.shared.utils.logger import setup_logger

logger = setup_logger(__name__)


class VectorStore:
    """Vector store for managing document embeddings using ChromaDB.

    Provides CRUD operations for document storage, similarity search,
    and optional Google Cloud Storage backup/restore.
    """

    def __init__(
        self,
        persist_directory: str = "./chroma_db",
        collection_name: str = "thoth_documents",
        embedder: Embedder | None = None,
        gcs_bucket_name: str | None = None,
        gcs_project_id: str | None = None,
        logger_instance: logging.Logger | logging.LoggerAdapter | None = None,
    ):
        """Initialize the ChromaDB vector store.

        Args:
            persist_directory: Directory path for ChromaDB persistence
            collection_name: Name of the ChromaDB collection
            embedder: Optional Embedder instance for generating embeddings.
                If not provided, a default Embedder with all-MiniLM-L6-v2 will be created.
            gcs_bucket_name: Optional GCS bucket name for cloud backup
            gcs_project_id: Optional GCP project ID for GCS
            logger_instance: Optional logger instance to use.
        """
        self.persist_directory = Path(persist_directory)
        self.collection_name = collection_name
        self.logger = logger_instance or logger

        # Initialize or use provided embedder
        self.embedder = embedder or Embedder(model_name="all-MiniLM-L6-v2", logger_instance=self.logger)

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

        # Initialize GCS sync if bucket is provided
        self.gcs_sync = None
        if gcs_bucket_name:
            # Check if GCS module is available
            if importlib.util.find_spec("google.cloud.storage") is not None:
                try:
                    from thoth.shared.gcs_sync import GCSSync  # noqa: PLC0415

                    self.gcs_sync = GCSSync(
                        bucket_name=gcs_bucket_name,
                        project_id=gcs_project_id,
                        logger_instance=self.logger,
                    )
                    self.logger.info(f"GCS sync enabled with bucket: {gcs_bucket_name}")
                except ImportError as e:
                    self.logger.warning(f"Failed to initialize GCS sync: {e}")
                    self.gcs_sync = None
            else:
                self.logger.warning("google-cloud-storage not installed, GCS sync disabled")
                self.gcs_sync = None

        self.logger.info(f"Initialized VectorStore with collection '{collection_name}' at '{persist_directory}'")
        self.logger.info(f"Using embedder: {self.embedder.model_name}")

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
            self.logger.warning("No documents provided to add_documents")
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
            self.logger.info(f"Generating embeddings for {len(documents)} documents")
            embeddings = self.embedder.embed(documents, show_progress=True)

        # Upsert documents to collection (add or update if ID exists)
        self.collection.upsert(
            documents=documents,
            metadatas=cast("Any", metadatas),
            ids=ids,
            embeddings=cast("Any", embeddings),
        )

        self.logger.info(f"Upserted {len(documents)} documents to collection")

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
            query_embeddings=cast("Any", [query_embedding]),
            n_results=n_results,
            where=where,
            where_document=cast("Any", where_document),
        )

        # Flatten results (ChromaDB returns nested lists)
        flattened_results = {
            "ids": results["ids"][0] if results["ids"] else [],
            "documents": results["documents"][0] if results["documents"] else [],
            "metadatas": results["metadatas"][0] if results["metadatas"] else [],
            "distances": results["distances"][0] if results["distances"] else [],
        }

        result_count = len(cast("list", flattened_results["ids"]))
        self.logger.info(f"Search returned {result_count} results for query: '{query[:50]}...'")

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
        self.logger.info(f"Deleted documents matching {delete_desc}")

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
                self.logger.info(f"No documents found for file path: {file_path}")
                return 0

            # Delete all documents with matching file_path
            self.collection.delete(where={"file_path": file_path})

            self.logger.info(f"Deleted {count} documents for file path: {file_path}")
            return count

        except Exception:
            self.logger.exception(f"Failed to delete documents for file path: {file_path}")
            raise

    def get_document_count(self) -> int:
        """Get the total number of documents in the collection.

        Returns:
            Number of documents in the collection
        """
        return int(self.collection.count())

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

        self.logger.info(f"Retrieved {len(results['ids'])} documents")

        return dict(results)

    def reset(self) -> None:
        """Reset the collection by deleting all documents.

        Warning: This operation cannot be undone.
        """
        self.client.delete_collection(name=self.collection_name)
        self.collection = self.client.get_or_create_collection(
            name=self.collection_name, metadata={"hnsw:space": "cosine"}
        )
        self.logger.warning(f"Reset collection '{self.collection_name}'")

    def backup_to_gcs(self, backup_name: str | None = None) -> str | None:
        """Backup vector store to Google Cloud Storage.

        Args:
            backup_name: Optional name for the backup (defaults to timestamp)

        Returns:
            GCS prefix of the backup, or None if GCS sync not configured

        Raises:
            Exception: If backup fails
        """
        if not self.gcs_sync:
            self.logger.warning("GCS sync not configured. Cannot backup to GCS.")
            return None

        try:
            prefix = self.gcs_sync.backup_to_gcs(self.persist_directory, backup_name=backup_name)
            self.logger.info(f"Successfully backed up to GCS: {prefix}")
            return prefix
        except Exception:
            self.logger.exception("Failed to backup to GCS")
            raise

    def restore_from_gcs(
        self,
        backup_name: str | None = None,
        gcs_prefix: str | None = None,
    ) -> int:
        """Restore vector store from Google Cloud Storage.

        Args:
            backup_name: Name of backup to restore (looks in backups/ folder)
            gcs_prefix: Direct GCS prefix to restore from

        Returns:
            Number of files restored

        Raises:
            ValueError: If neither backup_name nor gcs_prefix is provided
            Exception: If restore fails
        """
        if not self.gcs_sync:
            self.logger.warning("GCS sync not configured. Cannot restore from GCS.")
            return 0

        try:
            if backup_name:
                count = self.gcs_sync.restore_from_backup(backup_name, self.persist_directory, clean_local=True)
            elif gcs_prefix:
                result = self.gcs_sync.sync_from_gcs(gcs_prefix, self.persist_directory, clean_local=True)
                downloaded = result["downloaded_files"]
                count = downloaded if isinstance(downloaded, int) else 0
            else:
                msg = "Must provide either backup_name or gcs_prefix"
                raise ValueError(msg)

            self.logger.info(f"Successfully restored {count} files from GCS")

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
            self.logger.exception("Failed to restore from GCS")
            raise

    def sync_to_gcs(self, gcs_prefix: str = "chroma_db") -> dict | None:
        """Sync vector store to Google Cloud Storage.

        Args:
            gcs_prefix: Prefix in GCS bucket (default: chroma_db)

        Returns:
            Sync statistics dict, or None if GCS sync not configured

        Raises:
            Exception: If sync fails
        """
        if not self.gcs_sync:
            self.logger.warning("GCS sync not configured. Cannot sync to GCS.")
            return None

        try:
            result = self.gcs_sync.sync_to_gcs(self.persist_directory, gcs_prefix=gcs_prefix)
            self.logger.info(f"Successfully synced to GCS: {result}")
            return result
        except Exception:
            self.logger.exception("Failed to sync to GCS")
            raise

    def list_gcs_backups(self) -> list[str]:
        """List available backups in Google Cloud Storage.

        Returns:
            List of backup names, or empty list if GCS sync not configured

        Raises:
            Exception: If listing fails
        """
        if not self.gcs_sync:
            self.logger.warning("GCS sync not configured.")
            return []

        try:
            backups = self.gcs_sync.list_backups()
            self.logger.info(f"Found {len(backups)} backups in GCS")
            return backups
        except Exception:
            self.logger.exception("Failed to list GCS backups")
            raise
