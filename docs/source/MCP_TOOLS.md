# Thoth MCP Tools Documentation

This document describes the available tools in the Thoth MCP Server.

## Overview

The Thoth MCP Server provides semantic search capabilities over handbook content through the Model Context Protocol (MCP). The server exposes tools that AI assistants like Claude can use to search and retrieve relevant information using natural language queries.

## Architecture

- **Vector Store**: ChromaDB with cosine similarity
- **Embedding Model**: all-MiniLM-L6-v2 (configurable)
- **Cache Strategy**: Manual LRU with 100 entry limit
- **Performance Target**: <2 seconds response time
- **Transport**: stdio (standard input/output)

## Available Tools

### ping

A simple connectivity test tool that verifies MCP server responsiveness.

**Purpose**: Verify that the MCP server is running and responding to tool calls correctly.

**Parameters**:
- `message` (string, optional): Custom message to echo back in the response
  - Default: `"ping"`
  - Description: Optional message to echo back in the response

**Returns**: Text content with format `"pong: {message}"`

**Examples**:

1. Basic ping without arguments:
   ```json
   {
     "name": "ping",
     "arguments": {}
   }
   ```
   Response: `"pong: ping"`

2. Ping with custom message:
   ```json
   {
     "name": "ping",
     "arguments": {
       "message": "Hello, Thoth!"
     }
   }
   ```
   Response: `"pong: Hello, Thoth!"`

**Use Cases**:
- Verify server connectivity
- Test MCP protocol communication
- Health check for the server
- Debugging and troubleshooting

**Error Handling**:
- No errors expected under normal operation
- Invalid tool names will raise `ValueError`

---

### search_handbook

Performs semantic search over handbook content using vector embeddings and returns formatted results with relevance scores and metadata.

**Purpose**: Search the handbook using natural language queries to find relevant sections, procedures, guidelines, and other content.

**Parameters**:
- `query` (string, **required**): Natural language search query
  - Example: "How do I reset my password?"
  - Description: The search query to find relevant handbook content
  
- `n_results` (integer, optional): Number of results to return
  - Default: `5`
  - Range: `1-20`
  - Description: Number of results to return (will be clamped to valid range)
  
- `filter_section` (string, optional): Section name to filter results
  - Examples: `"introduction"`, `"procedures"`, `"guidelines"`, `"security"`
  - Description: Optional section name to filter results. Must match section names in document metadata.

**Returns**: Formatted text containing:
- Search header with query and parameters
- Search execution time
- List of results with:
  - Relevance score (0.0-1.0 scale)
  - Section name (if available)
  - Source file (if available)
  - Chunk index (position in document)
  - Full document content

**Relevance Scoring**:
- Score = 1 - distance (where distance is from vector similarity)
- Score range: 0.0 (irrelevant) to 1.0 (exact match)
- Typical good results: >0.7 score

**Examples**:

1. Basic search:
   ```json
   {
     "name": "search_handbook",
     "arguments": {
       "query": "authentication process"
     }
   }
   ```

2. Search with custom result count:
   ```json
   {
     "name": "search_handbook",
     "arguments": {
       "query": "password reset procedure",
       "n_results": 10
     }
   }
   ```

3. Search with section filter:
   ```json
   {
     "name": "search_handbook",
     "arguments": {
       "query": "security best practices",
       "n_results": 5,
       "filter_section": "security"
     }
   }
   ```

**Response Format**:
```
Search Results for: 'authentication process'
Found 3 result(s) in section 'security'
Search time: 0.234s

--- Result 1 ---
Relevance Score: 0.892
Section: security
Source: handbook/security.md
Chunk: 5

Content:
[Document content here...]

--- Result 2 ---
...
```

**Performance**:
- Target: <2s total response time
- Cache hit: <100ms
- Cache miss: 100-500ms (depends on database size)
- Cache hit rate: ~80% for typical usage patterns

**Use Cases**:
- Finding relevant procedures and guidelines
- Answering questions about handbook content
- Discovering related sections and topics
- Quick reference lookup
- Contextual information retrieval

**Error Handling**:
- **Database not available**: Returns error message if vector store failed to initialize
- **No results found**: Returns "No results found for query: '...'" message
- **Search errors**: Catches and logs exceptions, returns error message to user

**Limitations**:
- Requires handbook database to be ingested first
- Results limited to 20 maximum per query
- Search quality depends on embedding model and chunking strategy
- Section filtering requires documents to have section metadata

**Performance Optimization**:
- Uses manual LRU cache with 100 entry limit
- Caches complete search results including metadata
- Cache key: (query, n_results, filter_section) tuple
- FIFO eviction when cache is full

## Testing Tools Locally

To test the tools locally:

1. **Start the MCP server**:
   ```bash
   python -m thoth.mcp_server.server
   ```

2. **Use an MCP client** to connect and call tools via stdio

3. **Run the unit tests**:
   ```bash
   hatch run dev:test tests/mcp_server/
   ```

4. **Test search functionality**:
   ```bash
   # Ensure handbook is ingested first
   python -m thoth.cli ingest --source /path/to/handbook
   
   # Then start the server
   python -m thoth.mcp_server.server
   ```

## Adding New Tools

To add a new tool to the server:

1. **Update the `list_tools()` handler** in `thoth/mcp_server/server.py` to include your tool definition

2. **Add handling logic** in the `call_tool()` handler

3. **Create unit tests** in `tests/mcp_server/test_mcp_server.py`

4. **Document the tool** in this file

Example tool definition structure:
```python
Tool(
    name="your_tool_name",
    description="Description of what your tool does",
    inputSchema={
        "type": "object",
        "properties": {
            "param1": {
                "type": "string",
                "description": "Description of param1"
            }
        },
        "required": ["param1"]  # List required parameters
    }
)
```

## Implementation Details

### Caching Strategy

The server implements a manual LRU (Least Recently Used) cache for search results:

- **Cache Size**: 100 entries maximum
- **Cache Key**: (query, n_results, filter_section) tuple
- **Eviction**: FIFO (First In, First Out) when cache is full
- **Storage**: In-memory dictionary
- **Thread Safety**: Single-threaded (stdio transport)

Benefits:
- Dramatically improves response time for repeated queries
- Reduces vector database load
- Simple implementation without external dependencies
- No memory leak issues (unlike functools.lru_cache on methods)

### Search Process

1. **Query Validation**: Validates and clamps n_results to 1-20 range
2. **Cache Check**: Looks for cached results
3. **Vector Search**: If cache miss, performs similarity search in ChromaDB
4. **Metadata Filtering**: Applies section filter if specified
5. **Result Formatting**: Formats results with scores and metadata
6. **Cache Update**: Stores results in cache for future use

### Vector Database

The handbook content is stored in ChromaDB with:
- **Distance Metric**: Cosine similarity
- **Embedding Model**: all-MiniLM-L6-v2 (384 dimensions)
- **Metadata Fields**:
  - `section`: Handbook section name
  - `source`: Original source file path
  - `chunk_index`: Position of chunk in document
- **Chunking Strategy**: Configurable (see `thoth/ingestion/chunker.py`)

## Troubleshooting

### Search tool not available
- **Cause**: Vector database not found or failed to initialize
- **Solution**: Run `thoth ingest --source /path/to/handbook` to create the database

### Poor search results
- **Cause**: Query too vague or content not in database
- **Solution**: Try more specific queries or verify handbook content was ingested

### Slow response times
- **Cause**: Large database or cache miss
- **Solution**: 
  - Check database size and consider optimizing chunks
  - Monitor cache hit rate
  - Reduce n_results parameter

### Server not responding
- **Cause**: Server not running or stdio connection issues
- **Solution**: Check server logs and restart if needed

## Related Documentation

- [MCP Protocol Specification](https://modelcontextprotocol.io/)
- [Vector Store Documentation](VECTOR_STORE.md)
- [Embedding Model Documentation](EMBEDDING_MODEL.md)
- [Development Guide](DEVELOPMENT.md)
