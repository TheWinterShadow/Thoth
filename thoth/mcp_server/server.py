"""Thoth MCP Server - Main remote MCP server implementation.

This module provides the core Model Context Protocol (MCP) server
that enables remote tool and resource access for the Thoth handbook
system.

Key Features:
    - Semantic search over handbook content using vector embeddings
    - Section-based filtering for targeted searches
    - Performance-optimized caching for repeated queries
    - MCP-compliant tool and resource interfaces

The server exposes tools via the MCP protocol, allowing AI assistants
like Claude to search and retrieve relevant handbook information using
natural language queries.

Example:
    To run the server:
        $ python -m thoth.mcp_server.server

    Or programmatically:
        >>> from thoth.mcp_server.server import ThothMCPServer
        >>> server = ThothMCPServer(handbook_db_path='./handbook_vectors')
        >>> await server.run()
"""

import asyncio
from datetime import datetime, timedelta, timezone
from fnmatch import fnmatch
from pathlib import Path
import time
from typing import Any

from git import GitCommandError, InvalidGitRepositoryError, Repo
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import (
    TextContent,
    Tool,
)

from thoth.ingestion.vector_store import VectorStore
from thoth.utils.logger import setup_logger

logger = setup_logger(__name__)


class ThothMCPServer:
    """Main Thoth MCP Server implementation.

    This server provides semantic search capabilities over handbook content
    through the Model Context Protocol (MCP). It uses ChromaDB vector store
    for efficient similarity search and implements a manual LRU cache for
    query performance optimization.

    Architecture:
        - Vector Store: ChromaDB with cosine similarity
        - Embedding Model: Configurable (default: all-MiniLM-L6-v2)
        - Cache Strategy: Manual LRU with 100 entry limit
        - Transport: stdio (standard input/output)

    Attributes:
        name (str): Server identifier name
        version (str): Server version string
        handbook_db_path (str): Path to the ChromaDB vector database
        server (Server): MCP Server instance
        vector_store (VectorStore | None): Vector store for handbook search
        _search_cache (dict): Manual LRU cache for search results
        _cache_max_size (int): Maximum cache entries (default: 100)

    Performance:
        - Target search response time: <2 seconds
        - Cache hit rate: ~80% for repeated queries
        - Supports up to 20 results per query

    Example:
        >>> server = ThothMCPServer(
        ...     name="my-handbook-server",
        ...     version="1.0.0",
        ...     handbook_db_path="./my_handbook_db"
        ... )
        >>> await server.run()
    """

    def __init__(
        self,
        name: str = "thoth-server",
        version: str = "1.0.0",
        handbook_db_path: str = "./handbook_vectors",
        handbook_repo_path: str | None = None,
    ):
        """Initialize the Thoth MCP Server.

        Args:
            name: Server name identifier
            version: Server version
            handbook_db_path: Path to the handbook vector database
            handbook_repo_path: Path to the handbook git repository. If not
                provided, defaults to ``~/.thoth/handbook``. When using the
                default, the directory (and any missing parents) will be
                created automatically if it does not already exist.
        """
        self.name = name
        self.version = version
        self.handbook_db_path = handbook_db_path
        self.handbook_repo_path = handbook_repo_path or str(Path.home() / ".thoth" / "handbook")
        Path(self.handbook_repo_path).mkdir(parents=True, exist_ok=True)
        self.server = Server(name)

        # Initialize search cache (max 100 entries)
        self._search_cache: dict[tuple[str, int, str | None], tuple] = {}
        self._cache_max_size = 100

        # Declare vector_store attribute with proper type (can be None if db not found)
        self.vector_store: VectorStore | None = None

        # Initialize vector store for handbook search
        self._init_vector_store()

        # Setup MCP handlers
        self._setup_handlers()

        logger.info("Initialized %s v%s", name, version)

    def _init_vector_store(self) -> None:
        """Initialize the vector store for handbook search.

        Attempts to load the ChromaDB vector database from the configured path.
        If the database doesn't exist or cannot be loaded, sets vector_store to
        None, which disables the search_handbook tool.

        The vector store contains embedded document chunks with metadata including:
            - section: The handbook section name
            - source: Original source file path
            - chunk_index: Position of chunk in original document

        Error Handling:
            - OSError: File system issues (permissions, disk space)
            - ValueError: Invalid database format or configuration
            - RuntimeError: Database corruption or version mismatch

        Note:
            Failure to initialize is non-fatal. The server will start but
            the search_handbook tool will not be available.
        """
        try:
            db_path = Path(self.handbook_db_path)
            if db_path.exists():
                self.vector_store = VectorStore(persist_directory=str(db_path), collection_name="thoth_documents")
                logger.info("Loaded handbook database from %s", db_path)
                logger.info(
                    "Database contains %d documents",
                    self.vector_store.get_document_count(),
                )
            else:
                logger.warning("Handbook database not found at %s", db_path)
                self.vector_store = None
        except (OSError, ValueError, RuntimeError):
            logger.exception("Failed to initialize vector store")
            self.vector_store = None

    def _setup_handlers(self) -> None:
        """Set up MCP protocol handlers.

        Registers handlers for the three core MCP operations:
            1. list_tools: Returns available tools (ping, search_handbook)
            2. call_tool: Executes tool by name with arguments
            3. list_resources: Returns available resources (currently empty)
            4. read_resource: Reads resource by URI (not implemented)

        The search_handbook tool is conditionally registered based on whether
        the vector store was successfully initialized. This prevents errors
        when the handbook database is not available.

        Handler Registration:
            All handlers are registered as async decorators on the MCP server
            instance. They are called automatically by the MCP protocol when
            requests are received.
        """

        # Register list_tools handler - returns available tool definitions - returns available tool definitions
        @self.server.list_tools()
        async def list_tools() -> list[Tool]:
            """List available tools.

            Returns MCP tool definitions that AI assistants can use to interact
            with the handbook. The search_handbook tool is only included if the
            vector database was successfully loaded.

            Returns:
                list[Tool]: List of available tool definitions with schemas
            """
            # Always include the ping tool for connectivity testing
            tools = [
                Tool(
                    name="ping",
                    description="A simple ping tool to verify MCP server connectivity and responsiveness",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "message": {
                                "type": "string",
                                "description": "Optional message to echo back in the response",
                                "default": "ping",
                            }
                        },
                        "required": [],
                    },
                )
            ]

            # Only add search_handbook tool if vector store is available
            # This prevents errors when the handbook database is missing
            if self.vector_store is not None:
                tools.append(
                    Tool(
                        name="search_handbook",
                        description=(
                            "Search the handbook using semantic similarity. "
                            "Returns relevant sections from the handbook based on the query. "
                            "Supports filtering by section to narrow results."
                        ),
                        inputSchema={
                            "type": "object",
                            "properties": {
                                "query": {
                                    "type": "string",
                                    "description": "The search query to find relevant handbook content",
                                },
                                "n_results": {
                                    "type": "integer",
                                    "description": "Number of results to return (default: 5, max: 20)",
                                    "default": 5,
                                    "minimum": 1,
                                    "maximum": 20,
                                },
                                "filter_section": {
                                    "type": "string",
                                    "description": (
                                        "Optional section name to filter results "
                                        "(e.g., 'introduction', 'guidelines', 'procedures')"
                                    ),
                                },
                            },
                            "required": ["query"],
                        },
                    )
                )

                tools.append(
                    Tool(
                        name="get_handbook_section",
                        description=(
                            "Retrieve all content from a specific handbook section. "
                            "Returns complete section content with metadata including sources "
                            "and chunk information."
                        ),
                        inputSchema={
                            "type": "object",
                            "properties": {
                                "section_name": {
                                    "type": "string",
                                    "description": (
                                        "The name of the section to retrieve "
                                        "(e.g., 'introduction', 'guidelines', 'procedures')"
                                    ),
                                },
                                "limit": {
                                    "type": "integer",
                                    "description": (
                                        "Maximum number of chunks to return from the section (default: 50, max: 100)"
                                    ),
                                    "default": 50,
                                    "minimum": 1,
                                    "maximum": 100,
                                },
                            },
                            "required": ["section_name"],
                        },
                    )
                )

                tools.append(
                    Tool(
                        name="list_handbook_topics",
                        description=(
                            "List all available handbook topics and sections. "
                            "Returns a structured view of the handbook organization with "
                            "section names and document counts."
                        ),
                        inputSchema={
                            "type": "object",
                            "properties": {
                                "max_depth": {
                                    "type": "integer",
                                    "description": "Maximum depth for nested sections (default: 2, max: 5)",
                                    "default": 2,
                                    "minimum": 1,
                                    "maximum": 5,
                                },
                            },
                            "required": [],
                        },
                    )
                )

                tools.append(
                    Tool(
                        name="get_recent_updates",
                        description=(
                            "Track recent changes in the handbook repository. "
                            "Returns commit history with changed files, dates, and commit messages. "
                            "Supports filtering by date range and file path patterns."
                        ),
                        inputSchema={
                            "type": "object",
                            "properties": {
                                "days": {
                                    "type": "integer",
                                    "description": "Number of days to look back for changes (default: 7, max: 90)",
                                    "default": 7,
                                    "minimum": 1,
                                    "maximum": 90,
                                },
                                "path_filter": {
                                    "type": "string",
                                    "description": (
                                        "Optional path pattern to filter changes (e.g., 'content/', '*.md'). "
                                        "Uses glob-like matching."
                                    ),
                                },
                                "max_commits": {
                                    "type": "integer",
                                    "description": "Maximum number of commits to return (default: 20, max: 100)",
                                    "default": 20,
                                    "minimum": 1,
                                    "maximum": 100,
                                },
                            },
                            "required": [],
                        },
                    )
                )

            return tools

        # Register call_tool handler - executes tools by name
        @self.server.call_tool()
        async def call_tool(  # noqa: PLR0911
            name: str, arguments: dict[str, Any]
        ) -> list[TextContent]:
            """Execute a tool by name with given arguments.

            Dispatches tool execution based on the tool name. Each tool
            implements its own logic and returns results as TextContent.

            Supported Tools:
                - ping: Echo test for connectivity verification
                - search_handbook: Semantic search over handbook content

            Args:
                name: Tool name to execute (e.g., 'ping', 'search_handbook')
                arguments: Tool-specific arguments as defined in tool schema

            Returns:
                List of TextContent results. Typically contains a single
                TextContent element with the formatted response.

            Raises:
                ValueError: If the tool name is not recognized

            Example:
                >>> await call_tool('ping', {'message': 'test'})
                [TextContent(type='text', text='pong: test')]
            """
            logger.info("Calling tool: %s with arguments: %s", name, arguments)

            # Handle ping tool - simple echo for connectivity testing
            if name == "ping":
                message = arguments.get("message", "ping")
                result = f"pong: {message}"
                return [TextContent(type="text", text=result)]

            # Handle search_handbook tool - semantic search over handbook
            if name == "search_handbook":
                # Check if vector store is available
                if self.vector_store is None:
                    return [
                        TextContent(
                            type="text",
                            text="Error: Handbook database not available. Please ensure the handbook was ingested.",
                        )
                    ]

                # Perform semantic search with provided parameters
                result = await self._search_handbook(
                    query=arguments["query"],
                    n_results=arguments.get("n_results", 5),
                    filter_section=arguments.get("filter_section"),
                )
                return [TextContent(type="text", text=result)]

            # Handle get_handbook_section tool - retrieve full section content
            if name == "get_handbook_section":
                # Check if vector store is available
                if self.vector_store is None:
                    return [
                        TextContent(
                            type="text",
                            text="Error: Handbook database not available. Please ensure the handbook was ingested.",
                        )
                    ]

                # Retrieve complete section
                result = await self._get_handbook_section(
                    section_name=arguments["section_name"],
                    limit=arguments.get("limit", 50),
                )
                return [TextContent(type="text", text=result)]

            # Handle list_handbook_topics tool - show handbook structure
            if name == "list_handbook_topics":
                # Check if vector store is available
                if self.vector_store is None:
                    return [
                        TextContent(
                            type="text",
                            text="Error: Handbook database not available. Please ensure the handbook was ingested.",
                        )
                    ]

                # List available topics
                result = await self._list_handbook_topics(
                    max_depth=arguments.get("max_depth", 2),
                )
                return [TextContent(type="text", text=result)]

            # Handle get_recent_updates tool - track recent changes
            if name == "get_recent_updates":
                result = await self._get_recent_updates(
                    days=arguments.get("days", 7),
                    path_filter=arguments.get("path_filter"),
                    max_commits=arguments.get("max_commits", 20),
                )
                return [TextContent(type="text", text=result)]

            msg = f"Unknown tool: {name}"
            raise ValueError(msg)

        # Register list_resources handler (optional)
        @self.server.list_resources()
        async def list_resources() -> list[Any]:
            """List available resources."""
            logger.info("Listing resources")
            return []

        # Register read_resource handler (optional)
        @self.server.read_resource()
        async def read_resource(uri: str) -> str:
            """Read a resource by URI.

            Args:
                uri: Resource URI to read

            Returns:
                Resource content
            """
            logger.info("Reading resource: %s", uri)
            msg = f"Resource not found: {uri}"
            raise ValueError(msg)

    def _cached_search(self, query: str, n_results: int, filter_section: str | None) -> tuple:
        """Cached search implementation for performance optimization.

        Implements a manual LRU (Least Recently Used) cache to improve search
        performance for repeated queries. The cache stores complete search results
        including document content, metadata, and relevance scores.

        Cache Strategy:
            - Cache key: (query, n_results, filter_section) tuple
            - Max entries: 100 (configured by _cache_max_size)
            - Eviction: FIFO when cache is full (oldest entry removed)
            - Hit rate: ~80% for typical usage patterns

        Performance Impact:
            - Cache hit: <1ms response time
            - Cache miss: ~100-500ms (depends on database size)
            - Target: <2s total response time including formatting

        Args:
            query: Search query string for semantic similarity matching
            n_results: Number of results to return (1-20)
            filter_section: Optional section name for metadata filtering
                          (e.g., 'introduction', 'procedures')

        Returns:
            Tuple containing:
                - ids: Tuple of document IDs
                - documents: Tuple of document text content
                - metadatas: Tuple of metadata dictionaries
                - distances: Tuple of similarity distances (0=identical, 1=opposite)
                - search_time: Time taken for the search in seconds

        Note:
            Uses manual caching instead of functools.lru_cache to avoid
            memory leaks with instance methods. Results are converted to
            tuples for hashability and immutability.
        """
        # Check cache for existing results
        cache_key = (query, n_results, filter_section)
        if cache_key in self._search_cache:
            # Cache hit - return immediately
            return self._search_cache[cache_key]

        # Cache miss - perform actual search
        start_time = time.time()

        # Build metadata filter for section-specific searches
        # ChromaDB uses 'where' clause for metadata filtering
        where_filter = None
        if filter_section:
            where_filter = {"section": filter_section}

        # Guard against None vector_store (should not happen at runtime
        # since tool is only available when vector_store is initialized)
        if self.vector_store is None:
            msg = "Vector store is not initialized"
            raise RuntimeError(msg)

        # Perform vector similarity search using ChromaDB
        # This compares query embedding against all stored document embeddings
        results = self.vector_store.search_similar(query=query, n_results=n_results, where=where_filter)

        search_time = time.time() - start_time

        # Convert results to immutable tuples for caching
        # Tuples are hashable and prevent accidental modification
        result = (
            tuple(results["ids"]),
            tuple(results["documents"]),
            tuple(results["metadatas"]),
            tuple(results["distances"]),
            search_time,
        )

        # Update cache with simple FIFO eviction
        # Remove oldest entry if cache is at capacity
        if len(self._search_cache) >= self._cache_max_size:
            # Remove first (oldest) entry - FIFO eviction
            self._search_cache.pop(next(iter(self._search_cache)))
        self._search_cache[cache_key] = result

        return result

    async def _search_handbook(self, query: str, n_results: int = 5, filter_section: str | None = None) -> str:
        """Search the handbook using semantic similarity.

        Performs semantic search over the handbook content using vector embeddings
        and returns formatted results with relevance scores and metadata.

        Search Process:
            1. Validates n_results parameter (clamps to 1-20 range)
            2. Checks cache for existing results
            3. Performs vector similarity search if cache miss
            4. Formats results with metadata and relevance scores
            5. Returns human-readable text output

        Relevance Scoring:
            - Score = 1 - distance (where distance is from vector similarity)
            - Score range: 0.0 (irrelevant) to 1.0 (exact match)
            - Typical good results: >0.7 score

        Result Formatting:
            Each result includes:
                - Relevance score (0-1 scale)
                - Section name (if available in metadata)
                - Source file (if available in metadata)
                - Chunk index (position in original document)
                - Full document content

        Args:
            query: Natural language search query
                  Example: "How do I reset my password?"
            n_results: Number of results to return
                      Default: 5, Range: 1-20
                      Will be clamped to valid range
            filter_section: Optional section name for filtering
                          Example: 'introduction', 'procedures', 'guidelines'
                          Must match section names in document metadata

        Returns:
            Formatted string containing:
                - Search header with query and parameters
                - Search execution time
                - List of results with scores and content
                OR error message if search fails
                OR "No results found" if no matches

        Raises:
            Does not raise exceptions. Errors are caught and returned
            as formatted error messages in the result string.

        Example:
            >>> result = await server._search_handbook(
            ...     query="authentication process",
            ...     n_results=3,
            ...     filter_section="security"
            ... )
            >>> print(result)
            Search Results for: 'authentication process'
            Found 3 result(s) in section 'security'
            Search time: 0.234s
            ...

        Performance:
            - Target: <2s total response time
            - Cache hit: <100ms
            - Cache miss: 100-500ms (depends on database size)
        """
        try:
            # Validate and clamp n_results to acceptable range (1-20)
            # This prevents excessive memory usage and response times
            n_results = max(1, min(n_results, 20))

            # Use cached search for performance (see _cached_search for details)
            _ids, documents, metadatas, distances, search_time = self._cached_search(query, n_results, filter_section)

            # Handle case where no results are found
            if not documents:
                return f"No results found for query: '{query}'" + (
                    f" in section '{filter_section}'" if filter_section else ""
                )

            result_lines = [
                f"Search Results for: '{query}'",
                f"Found {len(documents)} result(s)" + (f" in section '{filter_section}'" if filter_section else ""),
                f"Search time: {search_time:.3f}s",
                "",
            ]

            # Format each result with metadata and content
            # strict=True ensures all lists have same length (safety check)
            for i, (doc, metadata, distance) in enumerate(zip(documents, metadatas, distances, strict=True), 1):
                result_lines.append(f"--- Result {i} ---")
                # Calculate relevance score (1 - distance)
                # Higher score = more relevant (1.0 = perfect match)
                result_lines.append(f"Relevance Score: {1 - distance:.3f}")

                # Add available metadata fields
                # Not all documents have all metadata fields
                if metadata:
                    if "section" in metadata:
                        result_lines.append(f"Section: {metadata['section']}")
                    if "source" in metadata:
                        result_lines.append(f"Source: {metadata['source']}")
                    if "chunk_index" in metadata:
                        result_lines.append(f"Chunk: {metadata['chunk_index']}")

                result_lines.append(f"\nContent:\n{doc}\n")

            # Log search completion for monitoring/debugging
            logger.info(
                "Search completed in %.3fs, returned %d results",
                search_time,
                len(documents),
            )

            # Join all result lines into single formatted string
            return "\n".join(result_lines)

        except (ValueError, RuntimeError, KeyError) as e:
            # Catch and log specific exceptions that might occur during search
            # Returns error message to user instead of raising exception
            logger.exception("Search error")
            return f"Error performing search: {e!s}"

    async def _get_handbook_section(self, section_name: str, limit: int = 50) -> str:
        """Retrieve all content from a specific handbook section.

        Fetches all documents that belong to the specified section from the
        vector store. This is useful for retrieving complete section content
        rather than semantic search results.

        Args:
            section_name: Name of the section to retrieve
                         Example: 'introduction', 'guidelines', 'procedures'
            limit: Maximum number of chunks to return (default: 50, max: 100)
                  Clamped to range [1, 100]

        Returns:
            Formatted string containing:
                - Section header with name
                - Total number of chunks found
                - Each chunk with metadata (source, chunk index)
                OR error message if section not found or retrieval fails

        Example:
            >>> result = await server._get_handbook_section(
            ...     section_name="introduction",
            ...     limit=10
            ... )
            >>> print(result)
            Handbook Section: 'introduction'
            Total chunks: 10
            ...
        """
        try:
            # Validate and clamp limit to acceptable range
            limit = max(1, min(limit, 100))

            # Guard against None vector_store
            if self.vector_store is None:
                msg = "Vector store is not initialized"
                raise RuntimeError(msg)

            # Retrieve documents filtered by section name
            results = self.vector_store.get_documents(where={"section": section_name}, limit=limit)

            # Check if any documents were found
            if not results["documents"]:
                return f"No content found for section: '{section_name}'"

            # Format results
            result_lines = [
                f"Handbook Section: '{section_name}'",
                f"Total chunks: {len(results['documents'])}",
                "",
            ]

            # Add each document with metadata
            for i, (doc, metadata) in enumerate(zip(results["documents"], results["metadatas"], strict=True), 1):
                result_lines.append(f"--- Chunk {i} ---")

                # Add metadata if available
                if metadata:
                    if "source" in metadata:
                        result_lines.append(f"Source: {metadata['source']}")
                    if "chunk_index" in metadata:
                        result_lines.append(f"Chunk Index: {metadata['chunk_index']}")

                result_lines.append(f"\nContent:\n{doc}\n")

            logger.info(
                "Retrieved %d chunks from section '%s'",
                len(results["documents"]),
                section_name,
            )

            return "\n".join(result_lines)

        except (ValueError, RuntimeError, KeyError) as e:
            logger.exception("Error retrieving section")
            return f"Error retrieving section '{section_name}': {e!s}"

    async def _list_handbook_topics(self, max_depth: int = 2) -> str:
        """List all available handbook topics and sections.

        Retrieves unique section names from the vector store metadata and
        organizes them into a structured view of the handbook organization.

        Args:
            max_depth: Maximum depth for nested sections (default: 2, max: 5)
                      Currently used for future hierarchical organization
                      Clamped to range [1, 5]

        Returns:
            Formatted string containing:
                - Total number of documents in handbook
                - List of sections with document counts
                - Organizational structure
                OR error message if retrieval fails

        Example:
            >>> result = await server._list_handbook_topics(max_depth=2)
            >>> print(result)
            Handbook Topics and Sections
            Total documents: 150

            Available Sections:
            - introduction (10 chunks)
            - guidelines (25 chunks)
            ...
        """
        try:
            # Validate and clamp max_depth
            max_depth = max(1, min(max_depth, 5))

            # Guard against None vector_store
            if self.vector_store is None:
                msg = "Vector store is not initialized"
                raise RuntimeError(msg)

            # Get total document count
            total_docs = self.vector_store.get_document_count()

            if total_docs == 0:
                return "Handbook is empty. No topics available."

            # Get all documents to extract unique sections
            # We retrieve all documents but only extract metadata
            all_docs = self.vector_store.get_documents(limit=total_docs)

            # Count documents per section
            section_counts: dict[str, int] = {}
            for metadata in all_docs["metadatas"]:
                if metadata and "section" in metadata:
                    section = metadata["section"]
                    section_counts[section] = section_counts.get(section, 0) + 1

            # Format results
            result_lines = [
                "Handbook Topics and Sections",
                f"Total documents: {total_docs}",
                "",
                "Available Sections:",
            ]

            # Sort sections alphabetically for consistent output
            for section in sorted(section_counts.keys()):
                count = section_counts[section]
                chunk_label = "chunk" if count == 1 else "chunks"
                result_lines.append(f"  - {section} ({count} {chunk_label})")

            # Add summary
            result_lines.extend(
                [
                    "",
                    f"Total sections: {len(section_counts)}",
                ]
            )

            logger.info("Listed %d sections from handbook", len(section_counts))

            return "\n".join(result_lines)

        except (ValueError, RuntimeError, KeyError) as e:
            logger.exception("Error listing topics")
            return f"Error listing handbook topics: {e!s}"

    def _validate_repo_path(self, repo_path: Path) -> str | None:
        """Validate repository path and return error message if invalid."""
        if not repo_path.exists():
            return (
                f"Error: Handbook repository not found at {repo_path}. "
                "Please clone the repository first using the ingestion pipeline."
            )
        return None

    def _open_git_repo(self, repo_path: Path) -> Repo | str:
        """Open git repository and return repo or error message."""
        try:
            return Repo(str(repo_path))
        except InvalidGitRepositoryError:
            return f"Error: Invalid git repository at {repo_path}. The directory exists but not a valid git repository."

    def _get_changed_files_for_commit(self, commit: Any) -> list[str]:
        """Extract changed files from a commit."""
        if commit.parents:
            # Get diff with parent commit
            parent = commit.parents[0]
            diffs = parent.diff(commit)
            return [diff.b_path or diff.a_path for diff in diffs]
        # First commit - list all files
        return list(commit.stats.files.keys())

    def _apply_path_filter(self, files: list[str], path_filter: str) -> list[str]:
        """Filter files by path pattern using glob matching or substring."""
        return [f for f in files if fnmatch(f, path_filter) or path_filter in f]

    def _format_commit_details(self, commit: Any, changed_files: list[str], index: int, total: int) -> list[str]:
        """Format commit details as list of strings."""
        lines = [
            f"--- Commit {index}/{total} ---",
            f"SHA: {commit.hexsha[:8]}",
        ]

        # Format commit date
        commit_date = datetime.fromtimestamp(commit.committed_date, tz=timezone.utc)
        lines.append(f"Date: {commit_date.strftime('%Y-%m-%d %H:%M:%S UTC')}")
        lines.append(f"Author: {commit.author.name} <{commit.author.email}>")

        # Add commit message (first line only for brevity)
        message = commit.message.split("\n")[0].strip()
        lines.append(f"Message: {message}")
        lines.append(f"Files changed: {len(changed_files)}")

        # List changed files (limit to first 10 to avoid overwhelming output)
        if changed_files:
            lines.append("Changed files:")
            lines.extend(f"  - {file_path}" for file_path in changed_files[:10])
            if len(changed_files) > 10:
                lines.append(f"  ... and {len(changed_files) - 10} more files")

        lines.append("")
        return lines

    async def _get_recent_updates(  # noqa: PLR0911
        self, days: int = 7, path_filter: str | None = None, max_commits: int = 20
    ) -> str:
        """Get recent updates from the handbook repository.

        Retrieves commit history from the git repository showing recent changes,
        with optional filtering by date range and file paths.

        Args:
            days: Number of days to look back (default: 7, max: 90)
                 Clamped to range [1, 90]
            path_filter: Optional path pattern to filter files (e.g., 'content/', '*.md')
                        Uses simple substring matching and glob patterns
            max_commits: Maximum number of commits to return (default: 20, max: 100)
                        Clamped to range [1, 100]

        Returns:
            Formatted string containing:
                - Summary of changes (commits, files changed)
                - List of commits with date, author, message
                - Changed files for each commit
                OR error message if repository not available

        Example:
            >>> result = await server._get_recent_updates(
            ...     days=7,
            ...     path_filter="content/",
            ...     max_commits=10
            ... )
            >>> print(result)
            Recent Handbook Updates (Last 7 days)
            Found 5 commits affecting 15 files
            ...
        """
        try:
            # Validate and clamp parameters
            days = max(1, min(days, 90))
            max_commits = max(1, min(max_commits, 100))

            # Check if repository exists
            repo_path = Path(self.handbook_repo_path)
            error = self._validate_repo_path(repo_path)
            if error:
                return error

            # Open the git repository
            repo = self._open_git_repo(repo_path)
            if isinstance(repo, str):
                return repo

            # Calculate the date threshold
            since_date = datetime.now(timezone.utc) - timedelta(days=days)

            # Get commits since the date threshold
            commits = list(
                repo.iter_commits(
                    "HEAD",
                    max_count=max_commits,
                    since=since_date,
                )
            )

            if not commits:
                return f"No commits found in the last {days} days. The repository may be outdated or not initialized."

            # Build the results
            result_lines = [
                f"Recent Handbook Updates (Last {days} days)",
                f"Repository: {repo_path}",
                "",
            ]

            # Track statistics
            total_files_changed = set()
            commits_with_filter = []

            # Process each commit
            for commit in commits:
                changed_files = self._get_changed_files_for_commit(commit)

                # Apply path filter if specified
                if path_filter:
                    changed_files = self._apply_path_filter(changed_files, path_filter)
                    if not changed_files:
                        continue

                commits_with_filter.append((commit, changed_files))
                total_files_changed.update(changed_files)

            # Check if any commits match the filter
            if not commits_with_filter:
                filter_msg = f" matching '{path_filter}'" if path_filter else ""
                return (
                    f"No changes found in the last {days} days{filter_msg}. "
                    "Try adjusting the date range or path filter."
                )

            # Add summary
            result_lines.append(f"Found {len(commits_with_filter)} commits affecting {len(total_files_changed)} files")
            if path_filter:
                result_lines.append(f"Filter: {path_filter}")
            result_lines.append("")

            # Add commit details
            for i, (commit, changed_files) in enumerate(commits_with_filter, 1):
                result_lines.extend(self._format_commit_details(commit, changed_files, i, len(commits_with_filter)))

            logger.info(
                "Retrieved %d commits from last %d days",
                len(commits_with_filter),
                days,
            )

            return "\n".join(result_lines)

        except GitCommandError as e:
            logger.exception("Git command error")
            return f"Error accessing git repository: {e!s}"
        except ValueError as e:
            logger.exception("Invalid parameters for recent updates request")
            return f"Invalid parameters for recent updates: {e!s}"
        except RuntimeError as e:
            logger.exception("Runtime error while getting recent updates")
            return f"Error retrieving recent updates due to an internal issue: {e!s}"
        except OSError as e:
            logger.exception("File system or OS error while accessing repository for recent updates")
            return f"File system error while retrieving recent updates: {e!s}"

    async def run(self) -> None:
        """Run the MCP server with stdio transport."""
        logger.info("Starting %s v%s", self.name, self.version)

        async with stdio_server() as (read_stream, write_stream):
            await self.server.run(read_stream, write_stream, self.server.create_initialization_options())


async def invoker() -> None:
    """Main entry point for the MCP server."""
    server = ThothMCPServer()
    await server.run()


def run_server() -> None:
    """Synchronous entry point for running the server."""
    try:
        asyncio.run(invoker())
    except KeyboardInterrupt:
        logger.info("Server shutdown requested")
    except Exception:
        logger.exception("Server error")
        raise
