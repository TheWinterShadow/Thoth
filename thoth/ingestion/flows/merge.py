"""Merge batches workflow.

Handles the /merge-batches endpoint which consolidates all batch LanceDB
tables into the main store after parallel processing completes.
"""

import asyncio
import os
from typing import Any

import lancedb
from starlette.requests import Request
from starlette.responses import JSONResponse

from thoth.shared.gcs_sync import GCSSync
from thoth.shared.utils.logger import setup_logger
from thoth.shared.vector_store import VectorStore

logger = setup_logger(__name__)

# Batch prefix pattern for GCS storage isolation
BATCH_PREFIX_PATTERN = "lancedb_batch_"


def _extract_batch_prefixes(blobs: list) -> set[str]:
    """Extract unique batch prefix names from GCS blob list."""
    batch_prefixes = set()
    for blob in blobs:
        parts = blob.name.split("/")
        if parts:
            batch_prefixes.add(parts[0])
    return batch_prefixes


async def _process_single_batch(
    batch_prefix_name: str,
    collection_name: str,
    gcs_bucket: str,
    main_store: Any,
) -> int:
    """Read a single LanceDB batch from GCS and merge into main store.

    Returns:
        Number of documents merged
    """
    logger.info("Processing batch: %s", batch_prefix_name)
    batch_uri = f"gs://{gcs_bucket}/{batch_prefix_name}"

    def merge_batch() -> int:
        """Run in executor: connect to batch LanceDB on GCS and add rows to main store."""
        db = lancedb.connect(batch_uri)
        if collection_name not in list(db.list_tables()):
            logger.warning("Batch %s has no table %s", batch_prefix_name, collection_name)
            return 0

        table = db.open_table(collection_name)
        tbl = table.to_arrow()

        if tbl.num_rows == 0:
            return 0

        # Extract data from Arrow table
        d = tbl.to_pydict()
        meta_cols = [c for c in tbl.column_names if c not in ("id", "text", "vector")]
        metadatas = [dict(zip(meta_cols, [d[c][i] for c in meta_cols], strict=True)) for i in range(tbl.num_rows)]
        vec_col = d["vector"]
        vectors = [v.tolist() if hasattr(v, "tolist") else list(v) for v in vec_col]

        # Add to main store
        main_store.add_documents(
            documents=d["text"],
            metadatas=metadatas,
            ids=d["id"],
            embeddings=vectors,
        )
        return int(tbl.num_rows)

    try:
        # Run merge in thread pool; LanceDB I/O is blocking
        doc_count = await asyncio.get_event_loop().run_in_executor(None, merge_batch)
        if doc_count > 0:
            logger.info("Merged %d documents from %s", doc_count, batch_prefix_name)
        return int(doc_count)
    except (ValueError, KeyError, RuntimeError, OSError) as e:
        logger.warning("Failed to merge batch %s: %s", batch_prefix_name, e)
        raise


def _cleanup_batch_from_gcs(batch_prefix_name: str, gcs_sync: GCSSync) -> bool:
    """Delete all blobs under a batch prefix in GCS (after merge).

    Args:
        batch_prefix_name: GCS prefix (e.g., lancedb_batch_handbook_documents_0)
        gcs_sync: GCSSync instance with bucket access

    Returns:
        True if all blobs were deleted, False on error
    """
    try:
        blobs_to_delete = list(gcs_sync.bucket.list_blobs(prefix=f"{batch_prefix_name}/"))
        for blob in blobs_to_delete:
            blob.delete()
        logger.info("Deleted batch from GCS: %s", batch_prefix_name)
        return True
    except (OSError, RuntimeError) as e:
        logger.warning("Failed to delete batch %s: %s", batch_prefix_name, e)
        return False


async def merge_batches(request: Request) -> JSONResponse:
    """Merge all batch LanceDB tables from GCS into the main store.

    Expects JSON body:
        collection_name: Collection to merge (optional, default: handbook_documents)
        cleanup: Delete batches after merge (optional, default: True)

    Returns:
        JSONResponse with status, merged_count, batches_merged, batches_cleaned
    """
    try:
        body = await request.json()
        collection_name = body.get("collection_name", "handbook_documents")
        cleanup = body.get("cleanup", True)

        logger.info("Starting merge for collection: %s", collection_name)

        gcs_bucket = os.getenv("GCS_BUCKET_NAME")
        gcs_project = os.getenv("GCP_PROJECT_ID")

        if not gcs_bucket or not gcs_project:
            return JSONResponse(
                {"status": "error", "message": "GCS not configured"},
                status_code=400,
            )

        gcs_sync = GCSSync(bucket_name=gcs_bucket, project_id=gcs_project)

        # Find all batch prefixes for this collection
        batch_prefix = f"{BATCH_PREFIX_PATTERN}{collection_name}_"
        blobs = list(gcs_sync.bucket.list_blobs(prefix=batch_prefix))
        batch_prefixes = _extract_batch_prefixes(blobs)

        if not batch_prefixes:
            return JSONResponse(
                {
                    "status": "success",
                    "message": "No batches found to merge",
                    "batches_merged": 0,
                }
            )

        logger.info("Found %d batches to merge", len(batch_prefixes))

        # Create main VectorStore
        main_store = VectorStore(
            persist_directory="/tmp/lancedb",  # nosec B108 - unused when GCS set
            collection_name=collection_name,
            gcs_bucket_name=gcs_bucket,
            gcs_project_id=gcs_project,
        )

        # Merge each batch sequentially
        total_documents = 0
        merged_batches = []

        for batch_prefix_name in sorted(batch_prefixes):
            try:
                doc_count = await _process_single_batch(batch_prefix_name, collection_name, gcs_bucket, main_store)
                total_documents += doc_count
                merged_batches.append(batch_prefix_name)
            except (ValueError, KeyError, RuntimeError, OSError):
                continue

        # Cleanup batches if requested
        deleted_batches = [b for b in merged_batches if _cleanup_batch_from_gcs(b, gcs_sync)] if cleanup else []

        return JSONResponse(
            {
                "status": "success",
                "collection_name": collection_name,
                "batches_merged": len(merged_batches),
                "total_documents": total_documents,
                "batches_cleaned": len(deleted_batches) if cleanup else 0,
                "final_uri": main_store.uri,
            }
        )

    except Exception as e:
        logger.exception("Failed to merge batches")
        return JSONResponse({"status": "error", "message": str(e)}, status_code=500)
