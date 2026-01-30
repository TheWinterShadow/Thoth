# MCP Server Architecture

This document describes the Model Context Protocol (MCP) server that provides semantic search capabilities to AI assistants.

## Overview

The MCP server enables AI assistants like Claude to:
1. Search handbook documentation using natural language
2. Retrieve specific sections by topic
3. List available handbook topics
4. Get recent documentation updates

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

    subgraph Storage["Data Layer"]
        VS[(ChromaDB)]
        GCS[(GCS Backup)]
    end

    C1 & C2 & C3 -->|SSE/HTTP| HW
    HW --> SSE
    SSE --> MCP
    MCP --> TH
    TH --> CA
    CA -->|cache miss| VS
    VS <-->|sync| GCS
```

## MCP Protocol Flow

```mermaid
sequenceDiagram
    participant Client as AI Assistant
    participant SSE as SSE Transport
    participant MCP as MCP Server
    participant Tools as Tool Handlers
    participant Cache as Query Cache
    participant DB as ChromaDB

    Client->>SSE: GET /sse (establish connection)
    SSE-->>Client: SSE stream opened

    Client->>SSE: list_tools request
    SSE->>MCP: Parse request
    MCP-->>SSE: Tool definitions
    SSE-->>Client: Available tools

    Client->>SSE: call_tool (search_handbook)
    SSE->>MCP: Parse request
    MCP->>Tools: Execute search
    Tools->>Cache: Check cache
    alt Cache Hit
        Cache-->>Tools: Cached results
    else Cache Miss
        Tools->>DB: Semantic search
        DB-->>Tools: Results
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

Core MCP protocol implementation:

```mermaid
classDiagram
    class ThothMCPServer {
        -vector_store: VectorStore
        -embedder: Embedder
        -cache: dict
        +list_tools() List~Tool~
        +call_tool(name, args) Result
        +list_resources() List~Resource~
        +read_resource(uri) Content
    }

    class VectorStore {
        +search(query, n_results) List~Document~
        +get(ids) List~Document~
        +add(documents) void
    }

    class Embedder {
        +embed(text) List~float~
        +embed_batch(texts) List~List~float~~
    }

    ThothMCPServer --> VectorStore
    ThothMCPServer --> Embedder
```

## Available Tools

### `ping`
Simple connectivity test.

**Arguments**: None

**Returns**: `{"status": "ok", "message": "pong"}`

### `search_handbook`
Semantic search across handbook documentation.

**Arguments**:
| Name | Type | Required | Description |
|------|------|----------|-------------|
| `query` | string | Yes | Natural language search query |
| `section` | string | No | Filter by section (e.g., "engineering") |
| `n_results` | integer | No | Max results (default: 10, max: 20) |

**Returns**: List of matching documents with:
- `content`: Matched text content
- `metadata`: File path, section, relevance score

### `get_handbook_section`
Retrieve a specific section by path.

**Arguments**:
| Name | Type | Required | Description |
|------|------|----------|-------------|
| `path` | string | Yes | Section path (e.g., "engineering/onboarding") |

**Returns**: Full section content with metadata

### `list_handbook_topics`
List all available handbook topics.

**Arguments**: None

**Returns**: Hierarchical list of topics and subtopics

### `get_recent_updates`
Get recently updated documentation.

**Arguments**:
| Name | Type | Required | Description |
|------|------|----------|-------------|
| `days` | integer | No | Lookback period (default: 7) |

**Returns**: List of recently modified documents

## Caching Strategy

```mermaid
flowchart TB
    Q[Query] --> H{Hash Query}
    H --> C{In Cache?}
    C -->|Yes| R[Return Cached]
    C -->|No| S[Search DB]
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
- TTL: Session-based (cleared on restart)
- Hit rate target: ~80% for repeated queries

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
| `CHROMA_PATH` | `/tmp/chroma` | ChromaDB storage path |
| `GCS_BUCKET` | - | GCS bucket for DB sync |
| `CACHE_SIZE` | `100` | Max cache entries |
| `PORT` | `8080` | HTTP server port |
