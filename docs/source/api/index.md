# API Reference

This section contains API documentation for Thoth.

## HTTP API

**Quick Links:**
- <a href="http.html">Interactive API Docs (Swagger/ReDoc)</a> - Try out endpoints
- [OpenAPI Specification](openapi.yaml) (YAML)

### Endpoints Summary

**MCP Server** (`thoth-mcp-server`)

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/` | GET | Root health check |
| `/health` | GET | Detailed health status |
| `/sse` | GET | SSE connection for MCP protocol |
| `/messages` | POST | MCP message handling |

**Ingestion Worker** (`thoth-ingestion-worker`)

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/health` | GET/POST | Health check |
| `/clone-to-gcs` | POST | Clone repository to GCS |
| `/ingest` | POST | Trigger parallel ingestion |
| `/ingest-batch` | POST | Process file batch |

## Python API

Auto-generated documentation from source code docstrings.

```{toctree}
:maxdepth: 2

generated/thoth
```

### Module Overview

**Ingestion Pipeline** (`thoth.ingestion`)
- `pipeline` - Main orchestrator
- `chunker` - Document chunking
- `repo_manager` - Repository management
- `worker` - HTTP worker endpoints
- `gitlab_api` - GitLab API client

**MCP Server** (`thoth.mcp`)
- `server.server` - MCP protocol handler
- `http_wrapper` - HTTP/SSE transport

**Shared Utilities** (`thoth.shared`)
- `vector_store` - ChromaDB wrapper
- `embedder` - Embedding generation
- `cli` - Command-line interface
- `scheduler` - Scheduled tasks
- `health` - Health checks
- `gcs_sync` - GCS synchronization

## MCP Tools

The MCP server exposes these tools to AI assistants:

| Tool | Description |
|------|-------------|
| `ping` | Connectivity test |
| `search_handbook` | Semantic search with optional filtering |
| `get_handbook_section` | Retrieve full section content |
| `list_handbook_topics` | List available topics |
| `get_recent_updates` | Recent documentation changes |

See [MCP Server Architecture](../architecture/mcp-server.md) for detailed tool specifications.
