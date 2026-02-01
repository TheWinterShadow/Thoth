"""Vector store module for managing document embeddings using LanceDB.

This module provides a wrapper around LanceDB for storing and querying
document embeddings with CRUD operations and native GCS support.
"""

import logging
from pathlib import Path
from typing import Any

import lancedb
import pyarrow as pa

from thoth.shared.embedder import Embedder
from thoth.shared.utils.logger import setup_logger

logger = setup_logger(__name__)


def _document_schema(vector_dim: int) -> pa.Schema:
    """Build PyArrow schema for the LanceDB document table.

    Defines columns: id, text, vector (fixed-size list of float32), and
    metadata fields (file_path, section, chunk_index, total_chunks, source,
    format, timestamp). Used when creating a new table.

    Args:
        vector_dim: Length of each embedding vector (must match embedder output).

    Returns:
        PyArrow schema for the document table.
    """
    return pa.schema(
        [
            pa.field("id", pa.string()),
            pa.field("text", pa.string()),
            pa.field("vector", pa.list_(pa.float32(), vector_dim)),
            pa.field("file_path", pa.string()),
            pa.field("section", pa.string()),
            pa.field("chunk_index", pa.int64()),
            pa.field("total_chunks", pa.int64()),
            pa.field("source", pa.string()),
            pa.field("format", pa.string()),
            pa.field("timestamp", pa.string()),
        ]
    )


def _arrow_table_to_doc_result(
    tbl: pa.Table,
    meta_exclude: tuple[str, ...] = ("id", "text", "vector"),
    distance_col: str = "_distance",
) -> tuple[list[str], list[str], list[dict[str, Any]], list[float] | None]:
    """Convert a LanceDB/Arrow result table into Chroma-style result lists.

    Extracts id and text columns as lists, builds a list of metadata dicts from
    all columns except id, text, vector, and the distance column (if present).
    Used after similarity search or table scans to normalize output.

    Args:
        tbl: PyArrow table from table.to_arrow() or search.to_arrow().
        meta_exclude: Column names to exclude from metadata (default: id, text, vector).
        distance_col: Name of the distance column from similarity search; excluded from metadata.

    Returns:
        Tuple of (ids, documents, metadatas, distances). distances is None when
        the table has no distance column (e.g., from get_documents).
    """
    if tbl.num_rows == 0:
        return [], [], [], [] if distance_col in tbl.column_names else None
    d = tbl.to_pydict()
    ids = d["id"]
    documents = d["text"]
    meta_cols = [c for c in tbl.column_names if c not in (*meta_exclude, distance_col)]
    metadatas = [dict(zip(meta_cols, [d[c][i] for c in meta_cols], strict=True)) for i in range(tbl.num_rows)]
    distances = d.get(distance_col)
    return (
        ids,
        documents,
        metadatas,
        distances if distance_col in tbl.column_names else None,
    )


def _where_to_sql(where: dict[str, Any]) -> str:
    """Convert a Chroma-style metadata filter dict into a LanceDB SQL WHERE clause.

    Supports string, int, float, bool, and None values; and dict operators
    ($eq, $ne, $gt, $gte, $lt, $lte). Escapes single quotes in string values.
    Used for search_similar and delete_documents filters.

    Args:
        where: Dict of column name -> value or column name -> {operator: value}.

    Returns:
        SQL WHERE expression string (e.g., "section = 'intro' AND chunk_index >= 0").
    """
    conditions = []
    for key, value in where.items():
        if isinstance(value, str):
            # Escape single quotes in value
            escaped = value.replace("'", "''")
            conditions.append(f"{key} = '{escaped}'")
        elif isinstance(value, (int, float)):
            conditions.append(f"{key} = {value}")
        elif isinstance(value, bool):
            conditions.append(f"{key} = {'true' if value else 'false'}")
        elif value is None:
            conditions.append(f"{key} IS NULL")
        elif isinstance(value, dict):
            for op, val in value.items():
                sql_op = {
                    "$eq": "=",
                    "$ne": "!=",
                    "$gt": ">",
                    "$gte": ">=",
                    "$lt": "<",
                    "$lte": "<=",
                }.get(op, "=")
                if isinstance(val, str):
                    escaped = val.replace("'", "''")
                    conditions.append(f"{key} {sql_op} '{escaped}'")
                elif val is None:
                    if sql_op == "=":
                        conditions.append(f"{key} IS NULL")
                    else:
                        conditions.append(f"{key} {sql_op} NULL")
                else:
                    conditions.append(f"{key} {sql_op} {val}")
    return " AND ".join(conditions)


class VectorStore:
    """Vector store for document embeddings using LanceDB.

    Provides add/search/delete/get operations for document chunks with
    metadata (file_path, section, chunk_index, source, format). Supports
    local paths or GCS via gs:// URIs. Uses an Embedder for query and
    document embeddings; defaults to sentence-transformers all-MiniLM-L6-v2.
    """

    def __init__(
        self,
        persist_directory: str = "./lancedb",
        collection_name: str = "thoth_documents",
        embedder: Embedder | None = None,
        gcs_bucket_name: str | None = None,
        gcs_project_id: str | None = None,  # noqa: ARG002 - kept for API compatibility
        gcs_prefix_override: str | None = None,
        logger_instance: logging.Logger | logging.LoggerAdapter | None = None,
    ):
        """Initialize the LanceDB vector store.

        Args:
            persist_directory: Local path or base path for LanceDB. Ignored when
                gcs_bucket_name is set (then URI is gs://bucket/lancedb or override).
            collection_name: Name of the table (collection).
            embedder: Optional Embedder instance. If not provided, a default
                Embedder with all-MiniLM-L6-v2 will be created.
            gcs_bucket_name: Optional GCS bucket; when set, store uses gs://bucket/...
            gcs_project_id: Optional GCP project ID (unused; kept for API compatibility).
            gcs_prefix_override: Optional GCS path under bucket (e.g. lancedb_batch_xyz).
                When set with gcs_bucket_name, URI is gs://bucket/gcs_prefix_override.
            logger_instance: Optional logger instance.
        """
        self.collection_name = collection_name
        self.logger = logger_instance or logger
        self.embedder = embedder or Embedder(model_name="all-MiniLM-L6-v2", logger_instance=self.logger)
        self._vector_dim = self.embedder.get_embedding_dimension()

        if gcs_bucket_name:
            path = gcs_prefix_override if gcs_prefix_override else "lancedb"
            self.uri = f"gs://{gcs_bucket_name}/{path}"
            self.logger.info("Using LanceDB with GCS URI: %s", self.uri)
        else:
            self.uri = str(Path(persist_directory).resolve())
            Path(self.uri).mkdir(parents=True, exist_ok=True)

        self.db = lancedb.connect(self.uri)
        table_names = list(self.db.list_tables())
        if self.collection_name in table_names:
            self.table = self.db.open_table(self.collection_name)
        else:
            schema = _document_schema(self._vector_dim)
            try:
                self.table = self.db.create_table(self.collection_name, schema=schema, mode="create")
            except ValueError as e:
                # Handle GCS eventual consistency: table may exist but not appear in list_tables()
                if "already exists" in str(e):
                    self.logger.info("Table '%s' already exists, opening it", self.collection_name)
                    self.table = self.db.open_table(self.collection_name)
                else:
                    raise
        self.logger.info(
            "Initialized VectorStore with table '%s' at '%s'",
            collection_name,
            self.uri,
        )
        self.logger.info("Using embedder: %s", self.embedder.model_name)

    def add_documents(
        self,
        documents: list[str],
        metadatas: list[dict[str, Any]] | None = None,
        ids: list[str] | None = None,
        embeddings: list[list[float]] | None = None,
    ) -> None:
        """Add or update documents in the table.

        Args:
            documents: List of document texts.
            metadatas: Optional list of metadata dicts per document.
            ids: Optional list of IDs; auto-generated if not provided.
            embeddings: Optional pre-computed embeddings.

        Raises:
            ValueError: If list lengths do not match.
        """
        if not documents:
            self.logger.warning("No documents provided to add_documents")
            return
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
            existing_count = self.get_document_count()
            ids = [f"doc_{existing_count + i}" for i in range(len(documents))]
        if embeddings is None:
            self.logger.info("Generating embeddings for %d documents", len(documents))
            embeddings = self.embedder.embed(documents, show_progress=True)

        # Build one record per document with required schema fields and metadata.
        records = []
        for i, (doc_id, text, embedding) in enumerate(zip(ids, documents, embeddings, strict=True)):
            meta = metadatas[i] if metadatas else {}
            records.append(
                {
                    "id": doc_id,
                    "text": text,
                    "vector": embedding,
                    "file_path": meta.get("file_path", ""),
                    "section": meta.get("section") or "",
                    "chunk_index": meta.get("chunk_index", 0),
                    "total_chunks": meta.get("total_chunks", 1),
                    "source": meta.get("source", ""),
                    "format": meta.get("format", "markdown"),
                    "timestamp": meta.get("timestamp", ""),
                }
            )
        # Upsert: update existing rows by id, insert new ones (idempotent for re-ingestion).
        self.table.merge_insert("id").when_matched_update_all().when_not_matched_insert_all().execute(records)
        self.logger.info("Upserted %d documents to table", len(documents))

    def search_similar(
        self,
        query: str,
        n_results: int = 5,
        where: dict[str, Any] | None = None,
        where_document: dict[str, Any] | None = None,
        query_embedding: list[float] | None = None,
    ) -> dict[str, Any]:
        """Search for similar documents by embedding.

        Args:
            query: Query text.
            n_results: Maximum number of results.
            where: Optional metadata filter (Chroma-style dict).
            where_document: Unused; kept for API compatibility.
            query_embedding: Optional pre-computed query embedding.

        Returns:
            Dict with ids, documents, metadatas, distances.
        """
        _ = where_document  # LanceDB does not support document-content filter in same way
        if query_embedding is None:
            query_embedding = self.embedder.embed_single(query)
        # Cosine distance: lower is more similar; limit results and optionally filter by metadata.
        search = self.table.search(query_embedding).metric("cosine").limit(n_results)
        if where:
            filter_expr = _where_to_sql(where)
            search = search.where(filter_expr)
        tbl = search.to_arrow()
        if tbl.num_rows == 0:
            return {"ids": [], "documents": [], "metadatas": [], "distances": []}
        ids, documents, metadatas, distances = _arrow_table_to_doc_result(tbl)
        return {
            "ids": ids,
            "documents": documents,
            "metadatas": metadatas,
            "distances": distances if distances is not None else [],
        }

    def delete_documents(self, ids: list[str] | None = None, where: dict[str, Any] | None = None) -> None:
        """Delete documents by ids or where filter.

        Args:
            ids: Optional list of document IDs.
            where: Optional metadata filter.

        Raises:
            ValueError: If neither ids nor where is provided.
        """
        if ids is None and where is None:
            msg = "Must provide either 'ids' or 'where' parameter"
            raise ValueError(msg)
        if ids:
            escaped_ids = [str(i).replace("'", "''") for i in ids]
            id_list = ", ".join(f"'{e}'" for e in escaped_ids)
            self.table.delete(f"id IN ({id_list})")
        else:
            if where is None:
                msg = "Where filter provided to delete_documents, but not supported by LanceDB"
                raise ValueError(msg)
            filter_expr = _where_to_sql(where)
            self.table.delete(filter_expr)
        self.logger.info("Deleted documents matching filter")

    def delete_by_file_path(self, file_path: str) -> int:
        """Delete all documents with the given file_path metadata.

        Args:
            file_path: File path to match.

        Returns:
            Number of documents deleted.
        """
        escaped = file_path.replace("'", "''")
        tbl = self.table.to_arrow()
        if "file_path" not in tbl.column_names:
            return 0
        file_paths = tbl.column("file_path")
        count = sum(1 for i in range(tbl.num_rows) if file_paths[i].as_py() == file_path)
        if count == 0:
            self.logger.info("No documents found for file path: %s", file_path)
            return 0
        self.table.delete(f"file_path = '{escaped}'")
        self.logger.info("Deleted %d documents for file path: %s", count, file_path)
        return int(count)

    def get_document_count(self) -> int:
        """Return the number of documents (rows) in the table.

        Returns:
            Non-negative integer count of rows.
        """
        return int(self.table.count_rows())

    def get_documents(
        self,
        ids: list[str] | None = None,
        where: dict[str, Any] | None = None,
        limit: int | None = None,
    ) -> dict[str, Any]:
        """Retrieve documents by ids, where filter, or full scan with limit.

        Args:
            ids: Optional list of IDs.
            where: Optional metadata filter.
            limit: Optional maximum number of documents.

        Returns:
            Dict with ids, documents, metadatas.
        """
        tbl = self.table.to_arrow()
        if tbl.num_rows == 0:
            return {"ids": [], "documents": [], "metadatas": []}
        d = tbl.to_pydict()
        row_indices = list(range(tbl.num_rows))
        if ids:
            id_set = set(ids)
            row_indices = [i for i in row_indices if d["id"][i] in id_set]
        if where:
            for key, value in where.items():
                if key not in tbl.column_names:
                    continue
                if isinstance(value, (str, int, float)):
                    row_indices = [i for i in row_indices if d[key][i] == value]
        if limit is not None:
            row_indices = row_indices[:limit]
        if not row_indices:
            return {"ids": [], "documents": [], "metadatas": []}
        meta_cols = [c for c in tbl.column_names if c not in ("id", "text", "vector")]
        result_ids = [d["id"][i] for i in row_indices]
        result_docs = [d["text"][i] for i in row_indices]
        result_metas = [dict(zip(meta_cols, [d[c][i] for c in meta_cols], strict=True)) for i in row_indices]
        return {
            "ids": result_ids,
            "documents": result_docs,
            "metadatas": result_metas,
        }

    def reset(self) -> None:
        """Drop and recreate the table (all data removed)."""
        self.db.drop_table(self.collection_name)
        schema = _document_schema(self._vector_dim)
        self.table = self.db.create_table(self.collection_name, schema=schema, mode="create")
        self.logger.warning("Reset table '%s'", self.collection_name)

    def backup_to_gcs(self, backup_name: str | None = None) -> str | None:
        """No-op when using GCS URI; data is already in GCS. Returns URI or None."""
        if self.uri.startswith("gs://"):
            return self.uri
        self.logger.warning(f"Backup [{backup_name}] to GCS not applicable for local store")
        return None

    def restore_from_gcs(
        self,
        backup_name: str | None = None,
        gcs_prefix: str | None = None,
    ) -> int:
        """Reconnect to store; when URI is GCS, data is already current. Returns doc count."""
        _ = backup_name
        _ = gcs_prefix
        self.db = lancedb.connect(self.uri)
        self.table = self.db.open_table(self.collection_name)
        return self.get_document_count()

    def sync_to_gcs(self, gcs_prefix: str = "lancedb") -> dict | None:
        """When using GCS URI, sync is implicit. Returns status dict or None."""
        _ = gcs_prefix
        if self.uri.startswith("gs://"):
            return {"status": "auto-synced", "uri": self.uri}
        self.logger.warning("Sync to GCS not applicable for local store")
        return None

    def list_gcs_backups(self) -> list[str]:
        """No discrete backups when using LanceDB on GCS; return empty list."""
        return []
