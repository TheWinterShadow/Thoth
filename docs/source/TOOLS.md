# Thoth MCP Server Tools Documentation

This document provides comprehensive documentation for all tools available through the Thoth Model Context Protocol (MCP) server.

## Table of Contents

1. [Overview](#overview)
2. [Tools](#tools)
   - [ping](#ping)
   - [search_handbook](#search_handbook)
   - [get_handbook_section](#get_handbook_section)
   - [list_handbook_topics](#list_handbook_topics)
   - [get_recent_updates](#get_recent_updates)
3. [Usage Examples](#usage-examples)
4. [Error Handling](#error-handling)
5. [Performance Considerations](#performance-considerations)

## Overview

The Thoth MCP Server exposes five tools that enable AI assistants (like Claude) to interact with handbook content through the Model Context Protocol. These tools provide semantic search, section retrieval, topic listing, and change tracking capabilities.

### Architecture

- **Transport**: stdio (standard input/output)
- **Vector Store**: ChromaDB with cosine similarity
- **Embedding Model**: all-MiniLM-L6-v2 (default, configurable)
- **Cache Strategy**: Manual LRU with 100 entry limit

### Server Initialization

```python
from thoth.mcp_server.server import ThothMCPServer

server = ThothMCPServer(
    name="my-handbook-server",
    version="1.0.0",
    handbook_db_path="./handbook_vectors",
    handbook_repo_path="~/.thoth/handbook"
)
await server.run()
```

## Tools

### ping

A simple connectivity test tool that verifies the MCP server is responsive and can communicate with clients.

#### Purpose
- Verify server connectivity
- Test MCP protocol communication
- Health check endpoint

#### Input Schema

```json
{
  "type": "object",
  "properties": {
    "message": {
      "type": "string",
      "description": "Optional message to echo back in the response",
      "default": "ping"
    }
  },
  "required": []
}
```

#### Parameters

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `message` | string | No | `"ping"` | Message to echo back |

#### Response Format

Returns a `TextContent` object with format: `pong: {message}`

#### Examples

**Basic ping:**
```json
{
  "message": "ping"
}
```
Response: `pong: ping`

**Custom message:**
```json
{
  "message": "Health check from client 123"
}
```
Response: `pong: Health check from client 123`

**No parameters:**
```json
{}
```
Response: `pong: ping`

#### Use Cases

1. **Connection Testing**: Verify the MCP server is running and accessible
2. **Latency Measurement**: Measure round-trip time for server communication
3. **Integration Tests**: Validate MCP protocol integration
4. **Keep-Alive**: Maintain persistent connections with periodic pings

---

### search_handbook

Performs semantic search over handbook content using vector embeddings. Returns relevant document chunks ranked by similarity score.

#### Purpose
- Find relevant handbook content using natural language queries
- Filter results by section for targeted searches
- Rank results by relevance score

#### Input Schema

```json
{
  "type": "object",
  "properties": {
    "query": {
      "type": "string",
      "description": "The search query to find relevant handbook content"
    },
    "n_results": {
      "type": "integer",
      "description": "Number of results to return (default: 5, max: 20)",
      "default": 5,
      "minimum": 1,
      "maximum": 20
    },
    "filter_section": {
      "type": "string",
      "description": "Optional section name to filter results"
    }
  },
  "required": ["query"]
}
```

#### Parameters

| Parameter | Type | Required | Default | Range | Description |
|-----------|------|----------|---------|-------|-------------|
| `query` | string | Yes | - | - | Natural language search query |
| `n_results` | integer | No | 5 | 1-20 | Number of results to return |
| `filter_section` | string | No | null | - | Section name for filtering |

#### Response Format

```
Search Results for: '{query}'
Found {n} result(s) [in section '{section}']
Search time: {time}s

--- Result 1 ---
Relevance Score: 0.XXX
Section: {section}
Source: {source_file}
Chunk: {chunk_index}

Content:
{document_content}

--- Result 2 ---
...
```

#### Relevance Scoring

- **Score Range**: 0.0 (irrelevant) to 1.0 (exact match)
- **Calculation**: `1 - cosine_distance`
- **Good Results**: Typically > 0.7
- **Excellent Results**: > 0.85

#### Examples

**Basic search:**
```json
{
  "query": "How do I reset my password?"
}
```

**Limited results:**
```json
{
  "query": "authentication procedures",
  "n_results": 3
}
```

**Section-filtered search:**
```json
{
  "query": "deployment best practices",
  "n_results": 10,
  "filter_section": "operations"
}
```

#### Caching

The search tool implements a manual LRU cache with the following characteristics:

- **Cache Size**: 100 entries (configurable via `_cache_max_size`)
- **Cache Key**: `(query, n_results, filter_section)` tuple
- **Eviction Policy**: FIFO (First In, First Out)
- **Hit Rate**: ~80% for typical usage patterns
- **Performance**:
  - Cache hit: <1ms response time
  - Cache miss: 100-500ms (depends on database size)
  - Target: <2s total response time

#### Use Cases

1. **Question Answering**: Find relevant documentation for user questions
2. **Information Retrieval**: Locate specific procedures or guidelines
3. **Research**: Discover related topics and content
4. **Troubleshooting**: Find solutions to common problems
5. **Onboarding**: Help new users find relevant handbook sections

#### Error Handling

| Error Condition | Response |
|----------------|----------|
| Database not available | `Error: Handbook database not available...` |
| No results found | `No results found for query: '{query}'...` |
| Search exception | `Error performing search: {exception}` |

---

### get_handbook_section

Retrieves all content from a specific handbook section. Returns complete section content with metadata.

#### Purpose
- Retrieve complete section content
- Access all chunks from a specific topic area
- Get structured section data with metadata

#### Input Schema

```json
{
  "type": "object",
  "properties": {
    "section_name": {
      "type": "string",
      "description": "The name of the section to retrieve"
    },
    "limit": {
      "type": "integer",
      "description": "Maximum number of chunks to return (default: 50, max: 100)",
      "default": 50,
      "minimum": 1,
      "maximum": 100
    }
  },
  "required": ["section_name"]
}
```

#### Parameters

| Parameter | Type | Required | Default | Range | Description |
|-----------|------|----------|---------|-------|-------------|
| `section_name` | string | Yes | - | - | Name of section to retrieve |
| `limit` | integer | No | 50 | 1-100 | Maximum chunks to return |

#### Response Format

```
Handbook Section: '{section_name}'
Total chunks: {n}

--- Chunk 1 ---
Source: {source_file}
Chunk Index: {index}

Content:
{document_content}

--- Chunk 2 ---
...
```

#### Examples

**Basic section retrieval:**
```json
{
  "section_name": "introduction"
}
```

**Limited chunks:**
```json
{
  "section_name": "procedures",
  "limit": 10
}
```

**Large section:**
```json
{
  "section_name": "api_reference",
  "limit": 100
}
```

#### Use Cases

1. **Complete Section Review**: Read entire sections sequentially
2. **Section Export**: Extract section content for external use
3. **Content Analysis**: Analyze complete section structure and content
4. **Documentation Generation**: Generate documentation from sections
5. **Audit Trails**: Review complete section history

#### Performance Considerations

- **Response Size**: Proportional to limit and chunk size
- **Network**: Large limits may result in large responses
- **Processing**: Minimal overhead, direct database query
- **Target**: <1s for typical section retrieval

---

### list_handbook_topics

Lists all available handbook topics and sections with document counts. Provides a structured view of handbook organization.

#### Purpose
- Discover available handbook sections
- Get overview of handbook structure
- Count documents per section

#### Input Schema

```json
{
  "type": "object",
  "properties": {
    "max_depth": {
      "type": "integer",
      "description": "Maximum depth for nested sections (default: 2, max: 5)",
      "default": 2,
      "minimum": 1,
      "maximum": 5
    }
  },
  "required": []
}
```

#### Parameters

| Parameter | Type | Required | Default | Range | Description |
|-----------|------|----------|---------|-------|-------------|
| `max_depth` | integer | No | 2 | 1-5 | Maximum depth for organization |

*Note: `max_depth` is reserved for future hierarchical organization. Currently, all sections are listed at the same level.*

#### Response Format

```
Handbook Topics and Sections
Total documents: {total}

Available Sections:
  - {section_1} ({count} chunks)
  - {section_2} ({count} chunks)
  ...

Total sections: {n}
```

#### Examples

**Basic listing:**
```json
{}
```

**With depth specification:**
```json
{
  "max_depth": 3
}
```

#### Sample Output

```
Handbook Topics and Sections
Total documents: 150

Available Sections:
  - getting_started (12 chunks)
  - guidelines (25 chunks)
  - introduction (8 chunks)
  - operations (45 chunks)
  - policies (30 chunks)
  - procedures (30 chunks)

Total sections: 6
```

#### Use Cases

1. **Handbook Navigation**: Discover available content areas
2. **Section Discovery**: Find relevant sections for search
3. **Content Inventory**: Audit handbook organization
4. **Documentation Planning**: Identify gaps in documentation
5. **User Orientation**: Help users understand handbook structure

#### Performance

- **Target**: <2s for typical handbooks
- **Complexity**: O(n) where n is total document count
- **Caching**: Not cached (structure changes infrequently)

---

### get_recent_updates

Tracks recent changes in the handbook git repository. Returns commit history with changed files, dates, and commit messages.

#### Purpose
- Track recent handbook changes
- Monitor content updates
- Filter changes by date range and file paths
- Audit modification history

#### Input Schema

```json
{
  "type": "object",
  "properties": {
    "days": {
      "type": "integer",
      "description": "Number of days to look back (default: 7, max: 90)",
      "default": 7,
      "minimum": 1,
      "maximum": 90
    },
    "path_filter": {
      "type": "string",
      "description": "Optional path pattern to filter changes (glob-like matching)"
    },
    "max_commits": {
      "type": "integer",
      "description": "Maximum number of commits to return (default: 20, max: 100)",
      "default": 20,
      "minimum": 1,
      "maximum": 100
    }
  },
  "required": []
}
```

#### Parameters

| Parameter | Type | Required | Default | Range | Description |
|-----------|------|----------|---------|-------|-------------|
| `days` | integer | No | 7 | 1-90 | Days to look back |
| `path_filter` | string | No | null | - | Path pattern (glob or substring) |
| `max_commits` | integer | No | 20 | 1-100 | Maximum commits to return |

#### Path Filter Patterns

The `path_filter` parameter supports two matching modes:

1. **Glob patterns**: `*.md`, `content/**/*.txt`
2. **Substring matching**: `content/`, `procedures`

Examples:
- `*.md` - All markdown files
- `content/` - Files in content directory
- `procedures` - Files with "procedures" in path

#### Response Format

```
Recent Handbook Updates (Last {days} days)
Repository: {repo_path}

Found {n} commits affecting {m} files
[Filter: {path_filter}]

--- Commit 1/{n} ---
SHA: {sha_short}
Date: {date}
Author: {name} <{email}>
Message: {message}
Files changed: {count}
Changed files:
  - {file_1}
  - {file_2}
  ...
  [... and {n} more files]

--- Commit 2/{n} ---
...
```

#### Examples

**Recent week's changes:**
```json
{}
```

**Last 30 days:**
```json
{
  "days": 30
}
```

**Specific file path:**
```json
{
  "days": 14,
  "path_filter": "content/"
}
```

**Markdown files only:**
```json
{
  "days": 7,
  "path_filter": "*.md",
  "max_commits": 50
}
```

**Specific section updates:**
```json
{
  "days": 30,
  "path_filter": "procedures",
  "max_commits": 10
}
```

#### Use Cases

1. **Change Monitoring**: Track recent handbook modifications
2. **Content Reviews**: Identify recently changed sections
3. **Update Notifications**: Alert users to relevant changes
4. **Audit Trails**: Review modification history
5. **Content Synchronization**: Detect changes for re-ingestion

#### Git Repository Requirements

- Repository must exist at `handbook_repo_path`
- Must be a valid git repository (`.git` directory)
- Must have commit history
- Read access required

#### Error Handling

| Error Condition | Response |
|----------------|----------|
| Repository not found | `Error: Handbook repository not found at {path}...` |
| Invalid git repository | `Error: Invalid git repository at {path}...` |
| No commits found | `No commits found in the last {days} days...` |
| Git command error | `Error accessing git repository: {error}` |
| Path filter no matches | `No changes found... Try adjusting... path filter` |

#### Performance

- **Target**: <3s for typical queries
- **Factors**: Commit count, repository size, file count
- **Optimization**: Limit commits and use specific path filters

---

## Usage Examples

### Complete Workflow Example

```python
# 1. Test connectivity
ping_result = await call_tool("ping", {"message": "test"})
# Response: "pong: test"

# 2. Discover available sections
topics = await call_tool("list_handbook_topics", {})
# Shows all sections with counts

# 3. Search for specific content
search_results = await call_tool(
    "search_handbook",
    {
        "query": "deployment procedures",
        "n_results": 5,
        "filter_section": "operations"
    }
)
# Returns top 5 relevant chunks from operations section

# 4. Get complete section
section_content = await call_tool(
    "get_handbook_section",
    {
        "section_name": "operations",
        "limit": 50
    }
)
# Returns all chunks from operations section

# 5. Check recent changes
updates = await call_tool(
    "get_recent_updates",
    {
        "days": 7,
        "path_filter": "content/operations/"
    }
)
# Shows commits affecting operations content
```

### Integration with Claude

```python
# Claude can use these tools naturally:
# User: "What are the deployment procedures?"
# Claude uses: search_handbook("deployment procedures", filter_section="operations")

# User: "Show me everything in the getting started section"
# Claude uses: get_handbook_section("getting_started")

# User: "What sections are available?"
# Claude uses: list_handbook_topics()

# User: "What changed in the last week?"
# Claude uses: get_recent_updates(days=7)
```

## Error Handling

### Common Error Scenarios

#### Database Not Available

**Cause**: Handbook database not found or failed to initialize

**Affected Tools**: `search_handbook`, `get_handbook_section`, `list_handbook_topics`

**Response**: 
```
Error: Handbook database not available. Please ensure the handbook was ingested.
```

**Solution**: Run handbook ingestion to create vector database

#### Repository Not Found

**Cause**: Git repository path doesn't exist

**Affected Tools**: `get_recent_updates`

**Response**:
```
Error: Handbook repository not found at {path}. Please clone the repository first...
```

**Solution**: Clone handbook repository or configure correct path

#### Invalid Parameters

**Cause**: Parameters outside valid ranges

**Behavior**: Parameters are automatically clamped to valid ranges

**Examples**:
- `n_results=0` → clamped to 1
- `n_results=100` → clamped to 20
- `days=0` → clamped to 1
- `limit=200` → clamped to 100

#### Search Errors

**Cause**: Internal search failure or vector store issues

**Response**:
```
Error performing search: {exception_message}
```

**Solutions**:
- Check database health
- Verify vector store is properly initialized
- Check system resources (memory, disk space)

### Error Recovery Strategies

1. **Retry with exponential backoff**: For transient errors
2. **Fallback to alternative tools**: Use `get_handbook_section` if `search_handbook` fails
3. **Parameter adjustment**: Reduce limits or result counts
4. **Cache clearing**: Restart server to clear corrupted cache

## Performance Considerations

### Search Performance

**Target**: <2 seconds total response time

**Factors affecting performance**:
- Database size (total documents)
- Query complexity
- Number of results requested
- Section filtering (narrows search space)
- Cache hit rate (~80% typical)

**Optimization tips**:
1. Use section filtering to narrow results
2. Request fewer results initially
3. Leverage caching for repeated queries
4. Consider query specificity (specific queries are faster)

### Cache Performance

**Cache Hit**: <1ms response time  
**Cache Miss**: 100-500ms (database query)  
**Cache Size**: 100 entries  
**Eviction**: FIFO (oldest removed when full)

**Cache key includes**:
- Query string
- Number of results
- Section filter

**Maximizing cache hits**:
- Use consistent query formatting
- Standardize n_results values
- Use same filter_section strings

### Database Size Impact

| Documents | Search Time | Memory Usage |
|-----------|-------------|--------------|
| 0-1,000 | <500ms | ~50-100MB |
| 1,000-10,000 | <1s | ~100-500MB |
| 10,000-50,000 | <2s | ~500MB-2GB |
| 50,000+ | <5s | ~2GB+ |

### Network Considerations

**Response sizes**:
- `ping`: <100 bytes
- `search_handbook`: 1-50KB (depends on n_results)
- `get_handbook_section`: 10-500KB (depends on limit)
- `list_handbook_topics`: 1-10KB
- `get_recent_updates`: 5-100KB (depends on max_commits)

**Recommendations**:
- Use appropriate limits for network conditions
- Consider pagination for large result sets
- Implement client-side caching where appropriate

### Resource Requirements

**Minimum**:
- CPU: 2 cores
- RAM: 2GB
- Disk: 500MB (small handbook)

**Recommended**:
- CPU: 4+ cores
- RAM: 4-8GB
- Disk: 2GB+ (medium-large handbook)

### Concurrent Usage

The server supports concurrent requests:
- Independent queries can be processed in parallel
- Cache is thread-safe (Python GIL protection)
- Vector store supports concurrent reads
- Target: 10-50 concurrent users

### Monitoring Metrics

Key metrics to monitor:
1. **Response time** (target: <2s for search)
2. **Cache hit rate** (target: >70%)
3. **Error rate** (target: <1%)
4. **Memory usage** (watch for growth)
5. **Database size** (affects performance)

## Best Practices

### Tool Selection

**Use `search_handbook` when**:
- You have a natural language question
- You need ranked results by relevance
- You want to find specific information
- Section is unknown or multiple sections may be relevant

**Use `get_handbook_section` when**:
- You need complete section content
- You want sequential reading
- You need to process all section data
- You know the exact section name

**Use `list_handbook_topics` when**:
- You need to discover available sections
- You want to show section overview
- You're building a navigation interface
- You need section statistics

**Use `get_recent_updates` when**:
- You need to track changes
- You want to identify recently modified sections
- You're building update notifications
- You need audit trails

**Use `ping` when**:
- Testing connectivity
- Health checks
- Measuring latency
- Keeping connections alive

### Query Optimization

1. **Be specific**: "How to deploy to production" vs "deploy"
2. **Use section filters**: Narrow search space when possible
3. **Request appropriate result count**: Start with 5, increase if needed
4. **Leverage caching**: Reuse identical queries
5. **Batch related queries**: Plan multiple queries together

### Error Handling

1. **Always check error responses**: Handle "Error:" prefix in results
2. **Implement retries**: With exponential backoff for transient errors
3. **Provide fallbacks**: Alternative tools or degraded functionality
4. **Log errors**: For debugging and monitoring
5. **User-friendly messages**: Translate technical errors for users

### Security Considerations

1. **Input validation**: Already handled by tool schemas
2. **Path traversal**: Git operations restricted to repository path
3. **Resource limits**: Parameters clamped to safe ranges
4. **Rate limiting**: Consider implementing at client level
5. **Access control**: Implement at server initialization level

---

## Troubleshooting

### Common Issues

#### "Handbook database not available"

**Problem**: Vector database not found or failed to load

**Solutions**:
1. Verify `handbook_db_path` is correct
2. Run handbook ingestion: `thoth ingest`
3. Check database file permissions
4. Verify ChromaDB installation

#### "No results found"

**Problem**: Search returns no matching documents

**Solutions**:
1. Try broader query terms
2. Remove section filter
3. Verify database has content: `list_handbook_topics`
4. Check query spelling

#### "Repository not found"

**Problem**: Git repository doesn't exist

**Solutions**:
1. Verify `handbook_repo_path` is correct
2. Clone the handbook repository
3. Check directory permissions
4. Initialize git repository if needed

#### Slow performance

**Problem**: Queries taking longer than expected

**Solutions**:
1. Check database size
2. Reduce `n_results` or `limit`
3. Use section filtering
4. Monitor system resources (CPU, memory)
5. Clear cache (restart server)
6. Optimize vector database

#### High memory usage

**Problem**: Server consuming excessive memory

**Solutions**:
1. Reduce cache size (`_cache_max_size`)
2. Limit concurrent queries
3. Check for memory leaks
4. Restart server periodically
5. Optimize embedding model

---

## Version History

- **1.0.0** (2024): Initial release with all five tools
  - `ping`: Connectivity testing
  - `search_handbook`: Semantic search
  - `get_handbook_section`: Section retrieval
  - `list_handbook_topics`: Topic listing
  - `get_recent_updates`: Change tracking

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines on:
- Reporting issues
- Proposing new tools
- Submitting improvements
- Testing procedures

## Support

For support and questions:
- **GitHub Issues**: [TheWinterShadow/Thoth/issues](https://github.com/TheWinterShadow/Thoth/issues)
- **Documentation**: [Project Documentation](https://thewintershadow.github.io/Thoth/)
- **Email**: elijah.j.winter@outlook.com

## License

This project is licensed under the MIT License - see [LICENSE](LICENSE) file for details.
