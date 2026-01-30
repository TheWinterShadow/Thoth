# Ingestion Pipeline Architecture

This document describes the data ingestion pipeline that processes GitLab handbook repositories into searchable vector embeddings.

## Overview

The ingestion pipeline is responsible for:
1. Cloning/syncing GitLab repositories to GCS
2. Chunking markdown documents into semantic segments
3. Generating embeddings using sentence-transformers
4. Storing vectors in ChromaDB for semantic search

## System Architecture

```mermaid
flowchart TB
    subgraph External["External Services"]
        GL[GitLab Repository]
        GCS[(Google Cloud Storage)]
        SM[Secret Manager]
    end

    subgraph CloudRun["Cloud Run - Ingestion Worker"]
        W[Worker HTTP Server]
        RM[Repo Manager]
        CH[Chunker]
        EM[Embedder]
    end

    subgraph Tasks["Cloud Tasks"]
        Q[Ingestion Queue]
    end

    subgraph Storage["Vector Storage"]
        VS[(ChromaDB)]
    end

    GL -->|clone/pull| RM
    SM -->|gitlab-token| RM
    RM -->|raw files| GCS
    GCS -->|markdown files| CH
    CH -->|chunks| EM
    EM -->|embeddings| VS
    VS -->|backup| GCS

    W -->|/clone-to-gcs| RM
    W -->|/ingest| Q
    Q -->|/ingest-batch| W
```

## Data Flow

```mermaid
sequenceDiagram
    participant Client
    participant Worker as Ingestion Worker
    participant Tasks as Cloud Tasks
    participant GitLab
    participant GCS
    participant ChromaDB

    Client->>Worker: POST /clone-to-gcs
    Worker->>GitLab: Clone repository
    Worker->>GCS: Upload repository files
    Worker-->>Client: 200 OK

    Client->>Worker: POST /ingest
    Worker->>Worker: List files, create batches
    loop For each batch
        Worker->>Tasks: Enqueue batch task
    end
    Worker-->>Client: 202 Accepted

    Tasks->>Worker: POST /ingest-batch {start, end, files}
    Worker->>GCS: Download batch files
    Worker->>Worker: Chunk documents
    Worker->>Worker: Generate embeddings
    Worker->>ChromaDB: Upsert vectors
    Worker-->>Tasks: 200 OK
```

## Components

### Repository Manager (`thoth/ingestion/repo_manager.py`)

Handles GitLab repository operations:

| Method | Description |
|--------|-------------|
| `clone_handbook()` | Initial clone of handbook repository |
| `update_repository()` | Pull latest changes |
| `get_changed_files()` | Detect files changed since last sync |
| `get_all_markdown_files()` | List all `.md` files in repository |

### Markdown Chunker (`thoth/ingestion/chunker.py`)

Splits documents into semantic chunks:

- **Chunk Size**: 500-1000 tokens (configurable)
- **Overlap**: 50 tokens between chunks
- **Strategy**: Respects markdown structure (headers, code blocks)
- **Metadata**: Preserves file path, section hierarchy, line numbers

```mermaid
flowchart LR
    MD[Markdown File] --> P[Parser]
    P --> S[Section Splitter]
    S --> T[Token Counter]
    T --> C[Chunk Generator]
    C --> M[Metadata Enricher]
    M --> O[Chunks + Metadata]
```

### Embedder (`thoth/shared/embedder.py`)

Generates vector embeddings:

- **Model**: `all-MiniLM-L6-v2` (384 dimensions)
- **Batch Processing**: Processes chunks in batches for efficiency
- **Caching**: Model loaded once, reused across requests

### Worker HTTP Server (`thoth/ingestion/worker.py`)

Cloud Run service endpoints:

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/health` | GET/POST | Health check |
| `/clone-to-gcs` | POST | One-time repository clone |
| `/ingest` | POST | Trigger parallel batch ingestion |
| `/ingest-batch` | POST | Process specific file batch |

## Parallel Processing

The pipeline uses Cloud Tasks for parallel processing:

```mermaid
flowchart TB
    subgraph Coordinator["Coordinator (POST /ingest)"]
        L[List 1000 files]
        B[Split into 10 batches]
    end

    subgraph Queue["Cloud Tasks Queue"]
        T1[Batch 1: files 0-99]
        T2[Batch 2: files 100-199]
        T3[Batch 3: files 200-299]
        TN[...]
    end

    subgraph Workers["Worker Instances"]
        W1[Worker 1]
        W2[Worker 2]
        W3[Worker 3]
    end

    L --> B
    B --> T1 & T2 & T3 & TN
    T1 --> W1
    T2 --> W2
    T3 --> W3
```

**Queue Configuration**:
- Max concurrent dispatches: 10
- Dispatch rate: 5 tasks/second
- Retry policy: 3 attempts with exponential backoff (10-60s)

## State Management

The pipeline tracks state for resumability:

```python
@dataclass
class PipelineState:
    last_commit: str          # Last processed commit SHA
    processed_files: set      # Files already processed
    failed_files: set         # Files that failed processing
    total_chunks: int         # Total chunks created
    last_run: datetime        # Timestamp of last run
```

State is persisted to GCS for recovery across restarts.

## Configuration

Environment variables:

| Variable | Default | Description |
|----------|---------|-------------|
| `GITLAB_BASE_URL` | `https://gitlab.com` | GitLab instance URL |
| `HANDBOOK_REPO` | - | Repository path (e.g., `group/handbook`) |
| `GCS_BUCKET` | - | GCS bucket for storage |
| `CHUNK_SIZE` | `800` | Target chunk size in tokens |
| `CHUNK_OVERLAP` | `50` | Overlap between chunks |
| `BATCH_SIZE` | `100` | Files per batch task |
