# Thoth Architecture

This document describes the architecture and design decisions behind the Thoth library.

## Overview

Thoth is a modular Python library that provides a Model Context Protocol (MCP) server for AI assistant integration, with semantic search capabilities over handbook documentation. The architecture emphasizes:

- **Modularity**: Each component is self-contained and can be used independently
- **Type Safety**: Full type annotations throughout the codebase
- **Cloud-Native**: Designed for deployment on Google Cloud Run
- **Extensibility**: Plugin-based architecture for MCP tools and resources
- **Maintainability**: Clear separation of concerns and well-defined interfaces

## Project Structure

```
thoth/
├── __init__.py              # Main package entry point
├── __about__.py             # Version and metadata information
├── ingestion/               # Data ingestion pipeline
│   ├── __init__.py          # Exports: Chunk, ChunkMetadata, MarkdownChunker,
│   │                        #          GitLabAPIClient, HandbookRepoManager, VectorStore
│   ├── chunker.py           # Markdown document chunker (500-1000 tokens)
│   ├── gitlab_api.py        # GitLab API client
│   ├── repo_manager.py      # Repository management (clone, pull, diff)
│   ├── pipeline.py          # Main ingestion orchestrator
│   ├── worker.py            # Task worker for parallel processing
│   └── gcs_repo_sync.py     # GCS sync for repository data
├── mcp/                     # Model Context Protocol server
│   ├── __init__.py
│   ├── http_wrapper.py      # HTTP/SSE wrapper for Cloud Run deployment
│   └── server/
│       ├── __init__.py      # Re-exports server components
│       ├── server.py        # ThothMCPServer implementation
│       └── plugins/
│           ├── rag/         # RAG (Retrieval Augmented Generation) plugins
│           └── tools/       # MCP tools plugins
└── shared/                  # Shared utilities and services
    ├── __init__.py
    ├── cli.py               # CLI commands (thoth command)
    ├── embedder.py          # Embedding generation (sentence-transformers)
    ├── gcs_sync.py          # GCS synchronization utilities
    ├── health.py            # Health check utilities for Cloud Run
    ├── monitoring.py        # Metrics and monitoring
    ├── scheduler.py         # APScheduler integration
    ├── vector_store.py      # ChromaDB vector database wrapper
    └── utils/
        ├── __init__.py
        ├── logger.py        # Logging utilities
        └── secrets.py       # Secret management (GCP Secret Manager)

terraform/                   # Infrastructure as Code
├── main.tf                  # Provider config, Terraform Cloud backend
├── cloud_run.tf             # Cloud Run service definition
├── cloud_tasks.tf           # Cloud Tasks queue for parallel ingestion
├── iam.tf                   # Service account, IAM roles
├── variables.tf             # Input variables
└── outputs.tf               # Output values

docs/                        # Documentation
├── README.md                # Documentation index
├── source/                  # Sphinx documentation source
│   ├── conf.py
│   ├── index.rst
│   └── api/                 # Auto-generated API docs
└── *.md                     # Additional documentation

tests/                       # Test suite
├── __init__.py
├── conftest.py              # Pytest configuration and fixtures
├── ingestion/               # Ingestion module tests
├── mcp/                     # MCP server tests
└── shared/                  # Shared utilities tests

pyproject.toml               # Project configuration (hatch)
CONTRIBUTING.md              # Contribution guidelines
LICENSE                      # MIT License
README.md                    # Project overview
```

## Design Principles

### 1. Cloud-Native Architecture

Thoth is designed for deployment on Google Cloud Platform:
- **Cloud Run**: Serverless container deployment with auto-scaling
- **Cloud Storage**: Vector database persistence and backup
- **Cloud Tasks**: Parallel ingestion processing
- **Secret Manager**: Secure credential storage

### 2. Type Safety

All public APIs include comprehensive type hints:
```python
from typing import Optional
from thoth.mcp.server import ThothMCPServer

server = ThothMCPServer(
    name: str = "thoth-mcp-server",
    version: str = "1.0.0",
    handbook_db_path: Optional[str] = None,
    handbook_repo_path: Optional[str] = None
)
```

### 3. Modular Design

Each module is independent and can be imported separately:
```python
# Import MCP server
from thoth.mcp.server import ThothMCPServer, run_server

# Import ingestion components
from thoth.ingestion import MarkdownChunker, HandbookRepoManager

# Import shared utilities
from thoth.shared.embedder import Embedder
from thoth.shared.vector_store import VectorStore
from thoth.shared.utils.logger import get_logger
```

### 4. Plugin Architecture

The MCP server supports plugins for extensibility:
```python
# Tools are registered in the server
@self.server.list_tools()
async def list_tools() -> list[Tool]:
    return [
        Tool(name="search_handbook", ...),
        Tool(name="get_handbook_section", ...),
    ]
```

### 5. Performance Considerations

- **Embedding caching**: LRU cache for search queries (100 entries)
- **Batch processing**: Efficient embedding generation for multiple documents
- **Vector similarity**: ChromaDB with cosine similarity for fast retrieval
- **Auto-scaling**: Cloud Run scales from 0 to handle load

## Module Organization

### Ingestion Package (`thoth/ingestion/`)

The ingestion pipeline processes handbook content:
- **Chunker**: Splits markdown documents into semantic chunks (500-1000 tokens)
- **GitLab API**: Fetches repository metadata and file lists
- **Repo Manager**: Clones and updates the handbook repository
- **Pipeline**: Orchestrates the ingestion process
- **Worker**: Handles parallel processing via Cloud Tasks

### MCP Package (`thoth/mcp/`)

Model Context Protocol server implementation:
- **Server**: Main ThothMCPServer class with tool handlers
- **HTTP Wrapper**: SSE transport for Cloud Run deployment
- **Plugins**: Extensible tools and RAG components

### Shared Package (`thoth/shared/`)

Common utilities used across modules:
- **Embedder**: Generates embeddings using sentence-transformers
- **Vector Store**: ChromaDB wrapper with GCS backup support
- **GCS Sync**: Google Cloud Storage synchronization
- **Health**: Health checks for Cloud Run
- **CLI**: Command-line interface
- **Utils**: Logging, secrets, and helper functions

## Data Flow

### Ingestion Flow

```
GitLab Handbook → Clone/Update → Markdown Files → Chunker → Embedder → ChromaDB → GCS Backup
```

1. **Repository Sync**: Clone or update handbook from GitLab
2. **File Discovery**: Find all markdown files
3. **Chunking**: Split documents into semantic chunks
4. **Embedding**: Generate vector embeddings
5. **Storage**: Store in ChromaDB with metadata
6. **Backup**: Sync to Google Cloud Storage

### Query Flow

```
User Query → MCP Server → Cache Check → Embed Query → Vector Search → Results
```

1. **Query Reception**: Receive search query via MCP protocol
2. **Cache Check**: Check LRU cache for repeated queries
3. **Query Embedding**: Generate embedding for query text
4. **Similarity Search**: Find similar documents in ChromaDB
5. **Result Formatting**: Return formatted results with metadata

## Configuration

### Environment Variables

Key configuration options:
- `GCP_PROJECT_ID` - Google Cloud project ID
- `GCS_BUCKET_NAME` - Storage bucket for vector DB backup
- `CHROMA_PERSIST_DIRECTORY` - Local ChromaDB path
- `LOG_LEVEL` - Logging verbosity (INFO, DEBUG, etc.)
- `EMBEDDING_MODEL` - Sentence-transformer model name

### Code Style Configuration

```toml
# pyproject.toml
[tool.ruff]
line-length = 88
target-version = "py39"

[tool.ruff.lint]
select = ["E", "F", "I", "B", "S"]

[tool.mypy]
python_version = "3.9"
strict = true
```

## Dependencies

### Core Dependencies
- Python 3.9+
- `mcp` - Model Context Protocol SDK
- `chromadb` - Vector database
- `sentence-transformers` - Embedding generation
- `google-cloud-storage` - GCS integration
- `starlette` - HTTP/SSE server

### Development Dependencies
- `ruff` - Linting and formatting
- `mypy` - Type checking
- `pytest` - Testing framework
- `pytest-asyncio` - Async test support
- `coverage` - Test coverage
- `sphinx` - Documentation generation

## Future Considerations

### Scaling
- Cloud Tasks for distributed ingestion
- Memorystore for Redis caching
- Batch embedding optimization

### Extensibility
- Additional MCP tools
- Custom embedding models
- Multiple handbook sources

### Monitoring
- Cloud Monitoring metrics
- Structured logging
- Performance tracing

This architecture provides a solid foundation for semantic search over handbook content while maintaining flexibility for future enhancements.
