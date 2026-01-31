# MCP Server Architecture

This document describes the Model Context Protocol (MCP) server that provides semantic search capabilities to AI assistants across multiple document collections.

## Overview

The MCP server enables AI assistants like Claude to:
1. Search across multiple document collections (handbook, D&D, personal)
2. Filter searches by specific sources
3. Retrieve documents with relevance-based ranking
4. Access cached results for improved performance

## System Architecture

```mermaid
flowchart TB
    subgraph Clients["AI Assistants"]
        C1[Claude Desktop]
        C2[Claude Code]
        C3[Other MCP Clients]
    end

    subgraph CloudRun["Cloud Run - MCP Server"]
        HW[HTTP Wrapper]
        SSE[SSE Transport]
        MCP[MCP Protocol Handler]
        TH[Tool Handlers]
        CA[Query Cache]
    end

    subgraph Collections["LanceDB Tables"]
        HB[(handbook_documents)]
        DND[(dnd_documents)]
        PER[(personal_documents)]
    end

    subgraph Storage["Data Layer"]
        GCS[(GCS Backup)]
    end

    C1 & C2 & C3 -->|SSE/HTTP| HW
    HW --> SSE
    SSE --> MCP
    MCP --> TH
    TH --> CA
    CA -->|cache miss| HB & DND & PER
    HB & DND & PER <-->|sync| GCS
```

## MCP Protocol Flow

```mermaid
sequenceDiagram
    participant Client as AI Assistant
    participant SSE as SSE Transport
    participant MCP as MCP Server
    participant Tools as Tool Handlers
    participant Cache as Query Cache
    participant DB as LanceDB Tables

    Client->>SSE: GET /sse (establish connection)
    SSE-->>Client: SSE stream opened

    Client->>SSE: list_tools request
    SSE->>MCP: Parse request
    MCP-->>SSE: Tool definitions
    SSE-->>Client: Available tools

    Client->>SSE: call_tool (search_documents)
    SSE->>MCP: Parse request
    MCP->>Tools: Execute search
    Tools->>Cache: Check cache
    alt Cache Hit
        Cache-->>Tools: Cached results
    else Cache Miss
        Tools->>DB: Search across collections
        DB-->>Tools: Results (merged by relevance)
        Tools->>Cache: Store in cache
    end
    Tools-->>MCP: Search results
    MCP-->>SSE: Format response
    SSE-->>Client: Tool result
```

## Components

### HTTP Wrapper (`thoth/mcp/http_wrapper.py`)

Provides HTTP/SSE transport for Cloud Run deployment:

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/` | GET | Root health check |
| `/health` | GET | Detailed health status |
| `/sse` | GET | SSE connection for MCP protocol |
| `/messages` | POST | MCP message handling |

### MCP Server (`thoth/mcp/server/server.py`)

Core MCP protocol implementation with multi-collection support:

```mermaid
classDiagram
    class ThothMCPServer {
        -vector_stores: dict[str, VectorStore]
        -embedder: Embedder
        -cache: dict
        -source_registry: SourceRegistry
        +list_tools() List~Tool~
        +call_tool(name, args) Result
        +list_resources() List~Resource~
        +read_resource(uri) Content
    }

    class VectorStore {
        +collection_name: str
        +search(query, n_results) List~Document~
        +get(ids) List~Document~
        +add(documents) void
        +sync_from_gcs(prefix) void
    }

    class SourceRegistry {
        +list_sources() List~str~
        +get(name) SourceConfig
        +list_configs() List~SourceConfig~
    }

    ThothMCPServer --> VectorStore : manages multiple
    ThothMCPServer --> SourceRegistry
```

## Available Tools

### `ping`
Simple connectivity test.

**Arguments**: None

**Returns**: `{"status": "ok", "message": "pong"}`

### `search_documents`
Search across multiple document collections with optional source filtering.

**Arguments**:
| Name | Type | Required | Description |
|------|------|----------|-------------|
| `query` | string | Yes | Natural language search query |
| `sources` | array | No | Filter by sources (default: all). Options: `handbook`, `dnd`, `personal` |
| `n_results` | integer | No | Max results per source (default: 10, max: 20) |

**Returns**: List of matching documents sorted by relevance with:
- `content`: Matched text content
- `metadata`: File path, source, relevance score
- `source`: Which collection the result came from

**Example**:
```json
{
  "name": "search_documents",
  "arguments": {
    "query": "code review best practices",
    "sources": ["handbook", "personal"],
    "n_results": 5
  }
}
```

### `search_handbook` (Legacy)
Search handbook documentation only. Maintained for backward compatibility.

**Arguments**:
| Name | Type | Required | Description |
|------|------|----------|-------------|
| `query` | string | Yes | Natural language search query |
| `section` | string | No | Filter by section (e.g., "engineering") |
| `n_results` | integer | No | Max results (default: 10, max: 20) |

**Returns**: List of matching documents with:
- `content`: Matched text content
- `metadata`: File path, section, relevance score

## Multi-Collection Search

The server initializes vector stores for all configured sources at startup:

```mermaid
flowchart TB
    subgraph Init["Server Initialization"]
        SR[Source Registry]
        SR -->|handbook| VS1[VectorStore: handbook_documents]
        SR -->|dnd| VS2[VectorStore: dnd_documents]
        SR -->|personal| VS3[VectorStore: personal_documents]
    end

    subgraph Search["search_documents(query, sources)"]
        Q[Query]
        Q -->|sources=all| VS1 & VS2 & VS3
        Q -->|sources=handbook,dnd| VS1 & VS2
        VS1 & VS2 & VS3 --> M[Merge Results]
        M --> S[Sort by Relevance]
        S --> R[Return Top N]
    end
```

### Search Algorithm

1. **Parse sources**: If not specified, search all available collections
2. **Parallel search**: Query each source's vector store
3. **Merge results**: Combine results from all sources
4. **Sort by relevance**: Order by similarity score (descending)
5. **Deduplicate**: Remove duplicate documents
6. **Limit results**: Return top N results

## Caching Strategy

```mermaid
flowchart TB
    Q[Query + Sources] --> H{Hash Key}
    H --> C{In Cache?}
    C -->|Yes| R[Return Cached]
    C -->|No| S[Search Collections]
    S --> ST[Store in Cache]
    ST --> R2[Return Results]

    subgraph Cache["LRU Cache (100 entries)"]
        E1[Entry 1]
        E2[Entry 2]
        EN[...]
    end
```

**Cache Configuration**:
- Type: LRU (Least Recently Used)
- Max entries: 100
- Key: Hash of (query, sources, n_results)
- TTL: Session-based (cleared on restart)
- Hit rate target: ~80% for repeated queries

## Vector Store Initialization

Each collection is synced from GCS at startup:

```python
# GCS prefix pattern for collections
# LanceDB uses single GCS path: gs://bucket/lancedb with one table per collection

# Example prefixes:
# - Tables: thoth_documents, dnd_documents, personal_documents in gs://bucket/lancedb
```

The server handles missing collections gracefully - if a collection doesn't exist in GCS, it's skipped during initialization and searches return empty results for that source.

## Performance Targets

| Metric | Target | Description |
|--------|--------|-------------|
| Response time | < 2s | P95 latency for search queries |
| Cache hit rate | > 80% | For repeated/similar queries |
| Concurrent connections | 50 | Max SSE connections per instance |
| Cold start | < 10s | Time to first request readiness |

## Scaling Configuration

```mermaid
flowchart LR
    subgraph CloudRun["Cloud Run Auto-scaling"]
        I1[Instance 1]
        I2[Instance 2]
        I3[Instance 3]
    end

    LB[Load Balancer] --> I1 & I2 & I3

    subgraph Config["Scaling Config"]
        MIN[Min: 0 instances]
        MAX[Max: 3 instances]
        CPU[CPU target: 80%]
        CON[Concurrency: 80]
    end
```

## Error Handling

The server implements graceful error handling:

```mermaid
flowchart TB
    R[Request] --> V{Validate}
    V -->|Invalid| E1[400 Bad Request]
    V -->|Valid| T{Execute Tool}
    T -->|Not Found| E2[Tool Not Found Error]
    T -->|DB Error| E3[Internal Error + Retry]
    T -->|Success| S[Return Results]
    E3 --> RT{Retry?}
    RT -->|Yes| T
    RT -->|No| E4[503 Service Unavailable]
```

## Configuration

Environment variables:

| Variable | Default | Description |
|----------|---------|-------------|
| `LOG_LEVEL` | `INFO` | Logging verbosity |
| `base_db_path` | `./vector_dbs` | LanceDB local path or GCS bucket (Cloud Run) |
| `GCS_BUCKET_NAME` | - | GCS bucket for DB sync |
| `GCP_PROJECT_ID` | - | GCP project ID |
| `CACHE_SIZE` | `100` | Max cache entries |
| `PORT` | `8080` | HTTP server port |

## Usage Examples

### Search All Collections

```bash
# Via MCP protocol
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "tools/call",
  "params": {
    "name": "search_documents",
    "arguments": {
      "query": "how to set up development environment"
    }
  }
}
```

### Search Specific Sources

```bash
# Search only handbook and personal docs
{
  "jsonrpc": "2.0",
  "id": 2,
  "method": "tools/call",
  "params": {
    "name": "search_documents",
    "arguments": {
      "query": "authentication flow",
      "sources": ["handbook", "personal"],
      "n_results": 5
    }
  }
}
```

### Legacy Handbook Search

```bash
# Backward compatible with existing integrations
{
  "jsonrpc": "2.0",
  "id": 3,
  "method": "tools/call",
  "params": {
    "name": "search_handbook",
    "arguments": {
      "query": "onboarding checklist",
      "n_results": 10
    }
  }
}
```
