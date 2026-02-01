---
description: 
alwaysApply: true
---

# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Thoth is a semantic search system for handbook documentation with an MCP (Model Context Protocol) server for AI assistant integration. It provides vector-based semantic search over documents using LanceDB and sentence-transformers, deployed on Google Cloud Platform.

## Build & Development Commands

```bash
# Install dependencies (development)
pip install -e ".[dev]"

# Code formatting and linting
hatch run format              # Format with ruff and black
hatch run format-check        # Check formatting without changes
hatch run typecheck          # Run mypy type checking
hatch run security           # Run bandit security scanning
hatch run check              # Full quality check (format + typecheck + security)

# Testing
hatch run test               # Run all tests
hatch run test tests/path/to/test.py  # Run single test file
hatch run test-cov           # Run tests with coverage
hatch run cov-html           # Generate HTML coverage report

# Pre-commit hooks
hatch run precommit-install  # Install pre-commit hooks
hatch run precommit          # Run all pre-commit hooks

# Documentation
hatch run docs:build         # Build Sphinx documentation
hatch run docs:serve         # Serve docs at http://localhost:8000

# Build
hatch run build              # Build wheel and sdist packages
```

## Architecture

### Core Components

**Ingestion Pipeline** (`thoth/ingestion/`):
- `pipeline.py` - Orchestrates end-to-end ingestion flow
- `repo_manager.py` - Git repository management (clone/pull)
- `gcs_repo_sync.py` - GCS file listing and parallel batch downloads
- `chunker.py` - Document chunking (500-1000 tokens with overlap)
- `parsers/` - Multi-format support (markdown, PDF, DOCX, text)
- `worker.py` - HTTP server with singleton management (116 lines)
- `flows/` - Modular workflow endpoints (health, clone, ingest, batch, merge, job_status)
- `job_manager.py` - Firestore job tracking with sub-job aggregation
- `task_queue.py` - Cloud Tasks client for parallel batch distribution

**MCP Server** (`thoth/mcp/`):
- `server/server.py` - ThothMCPServer with semantic search tools
- `http_wrapper.py` - SSE transport wrapper for Cloud Run (Uvicorn/Starlette)

**Shared Utilities** (`thoth/shared/`):
- `vector_store.py` - LanceDB wrapper with native GCS support (gs:// URIs)
- `embedder.py` - sentence-transformers embedding generation (all-MiniLM-L6-v2)
- `cli.py` - Click-based CLI (`thoth` command)
- `sources/config.py` - Multi-source registry (handbook, dnd, personal collections)
- `gcs_sync.py` - GCS bucket sync utilities
- `health.py` - Health check endpoints
- `monitoring.py` - Metrics and observability

### Data Flow

1. **Ingestion (Parallel)**:
   - `/ingest` → List files from GCS → Create sub-jobs → Enqueue batches to Cloud Tasks
   - Cloud Tasks → `/ingest-batch` (parallel) → Download batch files → Parse → Chunk → Embed → Write to isolated LanceDB table (gs://bucket/lancedb_batch_X/)
   - `/merge-batches` → Read all batch tables → Merge into main LanceDB (gs://bucket/lancedb/) → Cleanup batches
2. **Ingestion (Local)**: GitLab repo → Parser → Chunker (500-1000 tokens) → Embedder → LanceDB (local or gs://)
3. **Query**: MCP request → LRU cache check → Query embedding → LanceDB similarity search → Results

### Entry Points

- **CLI**: `thoth [command]` (defined in `thoth/shared/cli.py`)
- **MCP Server**: `python -m thoth.mcp.http_wrapper` (port 8080)
- **Ingestion Worker**: `python -m thoth.ingestion.worker`

## Code Standards

- **Formatting**: Black (88 chars), Ruff (120 chars)
- **Type hints**: Full annotations required, mypy strict mode
- **Docstrings**: Google-style format
- **Test coverage**: >90% required
- **Async testing**: pytest-asyncio with `asyncio_mode = "auto"`

## Infrastructure

- **Cloud**: Google Cloud Run, Cloud Tasks, Cloud Storage, Secret Manager
- **IaC**: Terraform (remote state in Terraform Cloud: TheWinterShadow/thoth-mcp-gcp)
- **CI/CD**: GitHub Actions (`.github/workflows/`)
  - `ci.yml` - Lint, type-check, tests on PRs
  - `infra-deploy.yml` - Deploy to Cloud Run on main branch

## Key Environment Variables

- `GITLAB_TOKEN` / `GITLAB_URL` - GitLab API access
- `HF_TOKEN` - HuggingFace model downloads
- `GOOGLE_CLOUD_PROJECT` / `GCP_REGION` / `GCS_BUCKET_NAME` - GCP configuration
- `LOG_LEVEL` - Logging level (default: INFO)
