# Thoth Development Guide for AI Agents

## Project Overview

Thoth is a **semantic search system** for documentation with parallel batch ingestion and an MCP server for AI assistant integration. It uses **LanceDB** (vector database) with **sentence-transformers** embeddings, deployed on **Google Cloud Platform**.

### Core Architecture

**3-Component System:**
1. **Ingestion Worker** (`thoth/ingestion/`) - Parallel batch processing with Firestore job tracking
2. **MCP Server** (`thoth/mcp/`) - Model Context Protocol semantic search API
3. **Shared Utilities** (`thoth/shared/`) - Vector store, embedders, GCS sync, logging

**Data Flow (Parallel Ingestion):**
```
POST /ingest → List GCS files → Create sub-jobs → Enqueue to Cloud Tasks
  ↓ (parallel batches)
Cloud Tasks → /ingest-batch → Download → Parse → Chunk → Embed → Write to gs://bucket/lancedb_batch_X/
  ↓ (after all batches)
POST /merge-batches → Merge all batch tables → gs://bucket/lancedb/ → Cleanup
```

**Query Flow:** MCP Request → LRU Cache → Embedding → LanceDB Search → Results

## Essential Development Commands

```bash
# Development environment
pip install -e ".[dev]"

# Quality checks (run before committing)
hatch run format              # Auto-format with ruff
hatch run check               # Full check (format + typecheck + security)
hatch run test                # Run all tests
hatch run test-cov            # With coverage report

# Pre-commit (installed in CI, run locally for faster feedback)
hatch run precommit-install   # Install hooks
hatch run precommit           # Run all hooks manually

# Documentation
hatch run docs:build          # Build Sphinx docs
hatch run docs:serve          # Serve at localhost:8000
```

## Code Standards & Patterns

### Import Structure
```python
# Standard library (alphabetical groups)
from dataclasses import dataclass
import os
from typing import Any

# Third-party (alphabetical)
from google.cloud import firestore

# Local (relative imports for same package, absolute for cross-package)
from thoth.shared.utils.logger import setup_logger, get_job_logger
```

### Logging Pattern (Always Use)
```python
# Module-level logger
from thoth.shared.utils.logger import setup_logger
logger = setup_logger(__name__)

# Job-scoped logging (auto-adds job_id to all logs)
job_logger = get_job_logger(logger, job_id=job.job_id, source="handbook")
job_logger.info("Processing started", extra={"total_files": 100})

# Never: f-strings in log messages
# Always: extra dict for structured fields
```

### Async Testing Pattern
```python
# pytest-asyncio is configured with asyncio_mode = "auto"
async def test_async_function():  # No decorator needed
    result = await some_async_function()
    assert result == expected
```

### Error Handling Convention
```python
# Always log with context, never swallow exceptions
try:
    process_batch(files)
except Exception as e:
    job_logger.exception("Batch processing failed", extra={"batch_id": batch_id})
    raise  # Or convert to domain-specific error
```

## Critical Files & Patterns

### Singleton Management Pattern
**`thoth/ingestion/worker.py`** (116 lines) uses module-level globals for singleton instances:
```python
_job_manager: JobManager | None = None
_source_registry: SourceRegistry | None = None

def get_job_manager() -> JobManager:
    global _job_manager
    if _job_manager is None:
        _job_manager = JobManager()
    return _job_manager
```
**Why:** Cloud Run processes are long-lived; initialize expensive resources (Firestore client, LanceDB) once per worker instance.

### Modular Workflow Endpoints
**`thoth/ingestion/flows/`** - Each endpoint is a separate module:
- `health.py` - Health checks
- `clone.py` - Git clone operations
- `ingest.py` - Start parallel ingestion (creates batches)
- `batch.py` - Process one batch (called by Cloud Tasks)
- `merge.py` - Merge batch tables into main collection
- `job_status.py` - Query Firestore job state

**Pattern:** Each flow is a Starlette route handler returning `JSONResponse`.

### LanceDB with Native GCS
**`thoth/shared/vector_store.py`** uses LanceDB's native `gs://` support:
```python
# Cloud Run (native GCS)
VectorStore(
    collection_name="handbook_docs",
    gcs_bucket_name="bucket",
    gcs_project_id="project-id"
)
# → Writes to gs://bucket/lancedb/

# Batch isolation (parallel writes)
VectorStore(
    collection_name="handbook_docs",
    gcs_bucket_name="bucket",
    gcs_table_path=f"lancedb_batch_{batch_id}"  # → gs://bucket/lancedb_batch_123/
)
```

### Job Tracking with Firestore
**`thoth/ingestion/job_manager.py`** tracks parent jobs and sub-jobs:
- Parent job: `job_id = uuid4()`, `total_batches = 10`
- Sub-jobs: `job_id = "{parent_id}_{batch_index:04d}"`, `parent_job_id = parent_id`
- Aggregation: `get_job_with_sub_jobs()` merges stats from all sub-jobs

## Infrastructure

### Terraform Cloud Deployment
- **Remote State:** Terraform Cloud workspace `TheWinterShadow/thoth-mcp-gcp`
- **Apply:** `cd terraform && terraform apply -var-file=environments/dev.tfvars`
- **Services:** Cloud Run, Cloud Tasks, Secret Manager, Firestore, GCS
- **Logs:** Job responses include `logs_url` field → Cloud Logging filtered by `job_id`

### Local Docker Testing
```bash
# Build MCP server
docker build -f Dockerfile.mcp -t thoth-mcp:local .
docker run -p 8080:8080 -e GCS_BUCKET_NAME=test-bucket thoth-mcp:local

# Build ingestion worker
docker build -f Dockerfile.ingestion -t thoth-ingestion:local .
```

## Common Patterns to Know

### Multi-Source Configuration
**`thoth/shared/sources/config.py`** - Registry of data sources:
```python
# Each source has: name, collection_name, gcs_prefix, supported_formats
sources = SourceRegistry.get_default()
handbook_config = sources.get_source("handbook")
# → SourceConfig(name="handbook", gcs_prefix="handbook", formats=[".md"])
```

### Chunking Strategy
**`thoth/ingestion/chunker.py`** - 500-1000 tokens with 200-token overlap for context preservation

### Cloud Run Health Checks
Both services have `/health` endpoints. **Startup probes:** 195s timeout (15s initial + 15s period × 12 failures).

## Testing & Debugging

```bash
# Run specific test file
hatch run test tests/ingestion/test_pipeline.py

# Run with verbose output
hatch run test tests/mcp/ -v

# View Cloud Run logs (after deployment)
gcloud logging read 'resource.labels.service_name="thoth-ingestion-worker"' --limit=50

# View logs for specific job
gcloud logging read 'jsonPayload.job_id="job_abc123"' --limit=100

# Query job status via API
curl http://localhost:8080/jobs/{job_id}
```

## Key Environment Variables

**Required in Cloud Run:**
- `GCP_PROJECT_ID` - GCP project
- `GCS_BUCKET_NAME` - Storage bucket for LanceDB
- `HF_TOKEN` - HuggingFace for model downloads (from Secret Manager)

**Optional:**
- `LOG_LEVEL` - Default: INFO
- `SKIP_VECTOR_RESTORE` - Set to "1" to skip GCS restore on startup

## Anti-Patterns to Avoid

❌ **Don't** use f-strings in log messages → Use `extra` dict for structured logging
❌ **Don't** create multiple JobManager instances → Use `get_job_manager()` singleton
❌ **Don't** write to main LanceDB table during batch processing → Use isolated batch tables
❌ **Don't** forget to call `job_manager.mark_completed()` → Jobs stay in RUNNING forever
❌ **Don't** use synchronous I/O in async functions → Use aiofiles, httpx, etc.

## When Making Changes

1. **Update tests first** - Test-driven development is enforced (>90% coverage required)
2. **Run pre-commit** - Before pushing: `hatch run precommit`
3. **Update docstrings** - Google-style format with Args/Returns/Example
4. **Check logs** - Verify structured logging with `extra` fields, not f-strings
5. **Consider batching** - For operations on >100 files, use parallel batch pattern
