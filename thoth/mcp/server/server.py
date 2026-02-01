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
        >>> server = ThothMCPServer(handbook_db_path="./handbook_vectors")
        >>> await server.run()
"""

import asyncio
from datetime import UTC, datetime, timedelta
from fnmatch import fnmatch
import os
from pathlib import Path
import time
from typing import Any

from git import GitCommandError, InvalidGitRepositoryError, Repo
from mcp.server import Server
from mcp.server.sse import SseServerTransport
from mcp.server.stdio import stdio_server
from mcp.types import (
    TextContent,
    Tool,
)
from starlette.applications import Starlette
from starlette.routing import Route
from starlette.types import Receive, Scope, Send

from thoth.shared.sources.config import SourceRegistry
from thoth.shared.utils.logger import configure_root_logger, setup_logger
from thoth.shared.vector_store import VectorStore

# Configure root logger for structured JSON output in Cloud Run
configure_root_logger()
logger = setup_logger(__name__)


class ThothMCPServer:
    """Main Thoth MCP Server implementation.

    This server provides semantic search capabilities over multiple document
    collections through the Model Context Protocol (MCP). It uses LanceDB
    vector stores for efficient similarity search and implements a manual
    LRU cache for query performance optimization.

    Architecture:
        - Vector Stores: Multiple LanceDB tables (handbook, dnd, personal)
        - Embedding Model: Configurable (default: all-MiniLM-L6-v2)
        - Cache Strategy: Manual LRU with 100 entry limit
        - Transport: stdio (standard input/output)

    Attributes:
        name (str): Server identifier name
        version (str): Server version string
        base_db_path (str): Base path for LanceDB (local) or GCS bucket (Cloud Run)
        server (Server): MCP Server instance
        source_registry (SourceRegistry): Registry of available data sources
        vector_stores (dict[str, VectorStore]): Vector stores by source name
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
        ...     base_db_path="./vector_dbs",
        ... )
        >>> await server.run()
    """

    def __init__(
        self,
        name: str = "thoth-server",
        version: str = "1.0.0",
        base_db_path: str = "./vector_dbs",
        handbook_repo_path: str | None = None,
    ):
        """Initialize the Thoth MCP Server.

        Args:
            name: Server name identifier
            version: Server version
            base_db_path: Base path for vector databases (one per collection)
            handbook_repo_path: Path to the handbook git repository. If not
                provided, defaults to ``~/.thoth/handbook``. When using the
                default, the directory (and any missing parents) will be
                created automatically if it does not already exist.
        """
        self.name = name
        self.version = version

        # Use /tmp paths in Cloud Run (GCS environment)
        if os.getenv("GCS_BUCKET_NAME") and os.getenv("GCP_PROJECT_ID"):
            self.base_db_path = "/tmp/vector_dbs"  # nosec B108 - Cloud Run requires /tmp
            self.handbook_repo_path = (
                handbook_repo_path or "/tmp/handbook"  # nosec B108
            )
        else:
            self.base_db_path = base_db_path
            self.handbook_repo_path = handbook_repo_path or str(Path.home() / ".thoth" / "handbook")

        # Create directories if possible, but don't fail if we lack permissions
        try:
            Path(self.handbook_repo_path).mkdir(parents=True, exist_ok=True)
        except (PermissionError, OSError) as e:
            logger.warning("Cannot create handbook repo path %s: %s", self.handbook_repo_path, e)

        try:
            Path(self.base_db_path).mkdir(parents=True, exist_ok=True)
        except (PermissionError, OSError) as e:
            logger.warning("Cannot create base db path %s: %s", self.base_db_path, e)

        self.server = Server(name)

        # Initialize source registry
        self.source_registry = SourceRegistry()

        # Initialize search cache (max 100 entries)
        # Cache key includes sources tuple for multi-collection support
        self._search_cache: dict[tuple[str, int, str | None, tuple[str, ...] | None], tuple] = {}
        self._cache_max_size = 100

        # Dictionary of vector stores by source name
        self.vector_stores: dict[str, VectorStore] = {}

        # Legacy: maintain backward compatibility with single vector_store attribute
        self.vector_store: VectorStore | None = None

        # Lazy loading flag to avoid blocking startup
        self._vector_stores_loaded = False

        # Setup MCP handlers first
        self._setup_handlers()

        logger.info(
            "Initialized %s v%s (vector stores will be loaded on first use)",
            name,
            version,
        )

    def _ensure_vector_stores_loaded(self) -> None:
        """Ensure vector stores are loaded (lazy loading on first access).

        Defers LanceDB connection and embedder loading until the first
        search/query operation so startup stays fast. Subsequent calls are
        no-ops. Uses a simple flag check; multiple simultaneous calls may
        trigger redundant loading once, which is acceptable.
        """
        if self._vector_stores_loaded:
            return

        logger.info("Lazy loading vector stores on first access...")
        # Load LanceDB tables and embedder; sets vector_stores and vector_store.
        self._init_vector_stores()
        self._vector_stores_loaded = True
        logger.info("Vector stores loaded: %d collections ready", len(self.vector_stores))

    def _init_vector_stores(self) -> None:
        """Initialize vector stores for all configured data sources.

        Loads LanceDB tables for each source (handbook, dnd, personal).
        In Cloud Run, uses GCS URI directly; no restore step needed.

        Each source has its own table with metadata including:
            - section: The document section name
            - source: Original source file path
            - chunk_index: Position of chunk in original document
            - format: Document format (md, pdf, txt, docx)

        Error Handling:
            - OSError: File system issues (permissions, disk space)
            - ValueError: Invalid database format or configuration
            - RuntimeError: Database corruption or version mismatch

        Note:
            Failure to initialize a source is non-fatal. The server will start
            with only the successfully loaded collections.
        """
        gcs_bucket = os.getenv("GCS_BUCKET_NAME")
        gcs_project = os.getenv("GCP_PROJECT_ID")

        logger.info(
            "Starting vector store initialization (GCS: %s)",
            bool(gcs_bucket and gcs_project),
        )

        start_time = time.time()

        for source_config in self.source_registry.list_configs():
            try:
                source_name = source_config.name
                collection_name = source_config.collection_name
                db_path = Path(self.base_db_path)

                logger.info(
                    "Initializing source '%s' (table: %s)",
                    source_name,
                    collection_name,
                )
                source_start = time.time()

                if gcs_bucket and gcs_project:
                    # Cloud Run: LanceDB uses GCS URI directly; no restore needed
                    logger.info(
                        "Initializing '%s' from GCS",
                        source_name,
                    )
                    vector_store = VectorStore(
                        persist_directory=str(db_path),
                        collection_name=collection_name,
                        gcs_bucket_name=gcs_bucket,
                        gcs_project_id=gcs_project,
                    )
                    doc_count = vector_store.get_document_count()
                    logger.info(
                        "Loaded '%s' table: %d documents (%.2fs)",
                        source_name,
                        doc_count,
                        time.time() - source_start,
                    )
                    self.vector_stores[source_name] = vector_store
                elif db_path.exists():
                    # Local: one LanceDB directory, multiple tables
                    vector_store = VectorStore(
                        persist_directory=str(db_path),
                        collection_name=collection_name,
                    )
                    doc_count = vector_store.get_document_count()
                    logger.info(
                        "Loaded '%s' table from %s: %d documents (%.2fs)",
                        source_name,
                        db_path,
                        doc_count,
                        time.time() - source_start,
                    )
                    self.vector_stores[source_name] = vector_store
                else:
                    logger.info(
                        "Database path '%s' not found; '%s' unavailable",
                        db_path,
                        source_name,
                    )

            except (OSError, ValueError, RuntimeError):
                logger.exception("Failed to initialize vector store for '%s'", source_name)

        logger.info(
            "Vector store initialization complete: %d collections loaded in %.2fs",
            len(self.vector_stores),
            time.time() - start_time,
        )

        # Set legacy vector_store attribute to handbook for backward compatibility
        if "handbook" in self.vector_stores:
            self.vector_store = self.vector_stores["handbook"]
        elif self.vector_stores:
            # Use first available if handbook not present
            self.vector_store = next(iter(self.vector_stores.values()))
        else:
            self.vector_store = None
            logger.warning("No vector stores initialized - search tools will be unavailable")

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

            # Only add search tools if at least one vector store is available
            if self.vector_stores:
                # Build sources description dynamically
                available_sources = list(self.vector_stores.keys())
                sources_desc = ", ".join(f"'{s}'" for s in available_sources)

                tools.append(
                    Tool(
                        name="search_documents",
                        description=(
                            "Search across document collections using semantic similarity. "
                            "Returns relevant content from multiple sources (handbook, dnd, personal). "
                            "Supports filtering by section and by source collection."
                        ),
                        inputSchema={
                            "type": "object",
                            "properties": {
                                "query": {
                                    "type": "string",
                                    "description": "The search query to find relevant content",
                                },
                                "n_results": {
                                    "type": "integer",
                                    "description": "Number of results to return (default: 5, max: 20)",
                                    "default": 5,
                                    "minimum": 1,
                                    "maximum": 20,
                                },
                                "sources": {
                                    "type": "array",
                                    "items": {"type": "string"},
                                    "description": (
                                        f"Optional list of sources to search. "
                                        f"Available: {sources_desc}. "
                                        "If not specified, searches all sources."
                                    ),
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

                # Keep legacy search_handbook for backward compatibility
                tools.append(
                    Tool(
                        name="search_handbook",
                        description=(
                            "Search the handbook using semantic similarity. "
                            "Returns relevant sections from the handbook based on the query. "
                            "(Legacy - prefer search_documents for multi-source search)"
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
                >>> await call_tool("ping", {"message": "test"})
                [TextContent(type='text', text='pong: test')]
            """
            logger.info("Calling tool: %s with arguments: %s", name, arguments)

            # Handle ping tool - simple echo for connectivity testing
            if name == "ping":
                message = arguments.get("message", "ping")
                result = f"pong: {message}"
                return [TextContent(type="text", text=result)]

            # Handle search_documents tool - multi-collection semantic search
            if name == "search_documents":
                if not self.vector_stores:
                    return [
                        TextContent(
                            type="text",
                            text="Error: No document collections available. Please ensure documents were ingested.",
                        )
                    ]

                # Perform multi-collection search
                result = await self._search_documents(
                    query=arguments["query"],
                    n_results=arguments.get("n_results", 5),
                    sources=arguments.get("sources"),
                    filter_section=arguments.get("filter_section"),
                )
                return [TextContent(type="text", text=result)]

            # Handle legacy search_handbook tool - backward compatible
            if name == "search_handbook":
                if not self.vector_stores:
                    return [
                        TextContent(
                            type="text",
                            text="Error: No document collections available. Please ensure the handbook was ingested.",
                        )
                    ]

                # Search only handbook collection for backward compatibility
                result = await self._search_documents(
                    query=arguments["query"],
                    n_results=arguments.get("n_results", 5),
                    sources=["handbook"] if "handbook" in self.vector_stores else None,
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

    def _cached_search(
        self,
        query: str,
        n_results: int,
        filter_section: str | None,
        sources: tuple[str, ...] | None = None,
    ) -> tuple:
        """Cached multi-collection search for performance optimization.

        Implements a manual LRU (Least Recently Used) cache to improve search
        performance for repeated queries. The cache stores complete search results
        including document content, metadata, and relevance scores.

        Cache Strategy:
            - Cache key: (query, n_results, filter_section, sources) tuple
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
            sources: Optional tuple of source names to search (e.g., ('handbook', 'dnd'))

        Returns:
            Tuple containing:
                - ids: Tuple of document IDs
                - documents: Tuple of document text content
                - metadatas: Tuple of metadata dictionaries (includes 'source_name')
                - distances: Tuple of similarity distances (0=identical, 1=opposite)
                - search_time: Time taken for the search in seconds

        Note:
            Uses manual caching instead of functools.lru_cache to avoid
            memory leaks with instance methods. Results are converted to
            tuples for hashability and immutability.
        """
        # Check cache for existing results
        cache_key = (query, n_results, filter_section, sources)
        if cache_key in self._search_cache:
            # Cache hit - return immediately
            return self._search_cache[cache_key]

        # Cache miss - perform actual search
        start_time = time.time()

        # Build metadata filter for section-specific searches
        where_filter = None
        if filter_section:
            where_filter = {"section": filter_section}

        # Determine which sources to search
        sources_to_search = list(sources) if sources else list(self.vector_stores.keys())

        # Collect results from all sources
        all_results: list[tuple[str, str, dict, float]] = []

        for source_name in sources_to_search:
            if source_name not in self.vector_stores:
                continue

            vector_store = self.vector_stores[source_name]

            # Perform vector similarity search
            results = vector_store.search_similar(
                query=query,
                n_results=n_results,
                where=where_filter,
            )

            # Add source name to metadata and collect results
            for doc_id, doc, metadata, distance in zip(
                results["ids"],
                results["documents"],
                results["metadatas"],
                results["distances"],
                strict=True,
            ):
                # Add source_name to metadata
                enriched_metadata = {**metadata, "source_name": source_name}
                all_results.append((doc_id, doc, enriched_metadata, distance))

        # Sort by distance (lower is better) and take top n_results
        all_results.sort(key=lambda x: x[3])
        top_results = all_results[:n_results]

        search_time = time.time() - start_time

        # Convert results to immutable tuples for caching
        if top_results:
            ids, documents, metadatas, distances = zip(*top_results, strict=True)
            result = (
                tuple(ids),
                tuple(documents),
                tuple(metadatas),
                tuple(distances),
                search_time,
            )
        else:
            result = ((), (), (), (), search_time)

        # Update cache with simple FIFO eviction
        if len(self._search_cache) >= self._cache_max_size:
            self._search_cache.pop(next(iter(self._search_cache)))
        self._search_cache[cache_key] = result

        return result

    def _validate_sources(self, sources: list[str] | None) -> tuple[list[str], tuple[str, ...] | None]:
        """Validate and filter sources. Returns (valid_sources, sources_tuple)."""
        available_sources = list(self.vector_stores.keys())

        if not sources:
            return available_sources, None

        valid_sources = [s for s in sources if s in available_sources]
        invalid_sources = [s for s in sources if s not in available_sources]

        if invalid_sources:
            logger.warning("Ignoring unknown sources: %s", invalid_sources)

        if not valid_sources:
            msg = f"No valid sources specified. Available sources: {available_sources}"
            raise ValueError(msg)

        return valid_sources, tuple(valid_sources)

    def _format_metadata_fields(self, metadata: dict) -> list[str]:
        """Format metadata fields for display. Returns list of formatted strings."""
        lines = []
        field_mapping = {
            "source_name": "Collection",
            "section": "Section",
            "source": "Source",
            "format": "Format",
            "chunk_index": "Chunk",
        }

        for field, label in field_mapping.items():
            if field in metadata:
                lines.append(f"{label}: {metadata[field]}")

        return lines

    async def _search_documents(
        self,
        query: str,
        n_results: int = 5,
        sources: list[str] | None = None,
        filter_section: str | None = None,
    ) -> str:
        """Search across document collections using semantic similarity.

        Performs semantic search over multiple document collections using vector
        embeddings and returns formatted results with relevance scores and metadata.

        Search Process:
            0. Lazy load vector stores if not already loaded (first call only)
            1. Validates n_results parameter (clamps to 1-20 range)
            2. Validates and filters requested sources
            3. Checks cache for existing results
            4. Performs vector similarity search across all requested collections
            5. Merges and sorts results by relevance score
            6. Formats results with metadata and content

        Relevance Scoring:
            - Score = 1 - distance (where distance is from vector similarity)
            - Score range: 0.0 (irrelevant) to 1.0 (exact match)
            - Typical good results: >0.7 score

        Result Formatting:
            Each result includes:
                - Relevance score (0-1 scale)
                - Source collection name
                - Section name (if available in metadata)
                - Source file path (if available in metadata)
                - Chunk index (position in original document)
                - Full document content

        Args:
            query: Natural language search query
                  Example: "How do I reset my password?"
            n_results: Number of results to return
                      Default: 5, Range: 1-20
                      Will be clamped to valid range
            sources: Optional list of source names to search
                    Example: ['handbook', 'dnd']
                    If None, searches all available sources
            filter_section: Optional section name for filtering
                          Example: 'introduction', 'procedures', 'guidelines'
                          Must match section names in document metadata

        Returns:
            Formatted string containing:
                - Search header with query and parameters
                - List of sources searched
                - Search execution time
                - List of results with scores and content
                OR error message if search fails
                OR "No results found" if no matches

        Example:
            >>> result = await server._search_documents(
            ...     query="dragon stats", n_results=5, sources=["dnd"]
            ... )
            >>> print(result)
            Search Results for: 'dragon stats'
            Searching: dnd
            Found 5 result(s)
            Search time: 0.234s
            ...
        """
        try:
            # Lazy load vector stores on first access
            self._ensure_vector_stores_loaded()

            # Validate and clamp n_results to acceptable range (1-20)
            n_results = max(1, min(n_results, 20))

            # Validate and filter requested sources
            try:
                valid_sources, sources_tuple = self._validate_sources(sources)
            except ValueError as e:
                return f"Error: {e}"

            # Use cached search for performance
            _ids, documents, metadatas, distances, search_time = self._cached_search(
                query, n_results, filter_section, sources_tuple
            )

            # Handle case where no results are found
            if not documents:
                sources_str = ", ".join(valid_sources)
                section_part = f" (section: '{filter_section}')" if filter_section else ""
                return f"No results found for query: '{query}' in sources: {sources_str}{section_part}"

            # Build result header
            sources_str = ", ".join(valid_sources)
            section_part = f" in section '{filter_section}'" if filter_section else ""
            result_lines = [
                f"Search Results for: '{query}'",
                f"Searching: {sources_str}",
                f"Found {len(documents)} result(s){section_part}",
                f"Search time: {search_time:.3f}s",
                "",
            ]

            # Format each result with metadata and content
            for i, (doc, metadata, distance) in enumerate(zip(documents, metadatas, distances, strict=True), 1):
                result_lines.append(f"--- Result {i} ---")
                result_lines.append(f"Relevance Score: {1 - distance:.3f}")

                # Add metadata fields
                result_lines.extend(self._format_metadata_fields(metadata))
                result_lines.append(f"\nContent:\n{doc}\n")

            # Log search completion for monitoring/debugging
            logger.info(
                "Search completed in %.3fs, returned %d results from %s",
                search_time,
                len(documents),
                sources_str,
            )

            return "\n".join(result_lines)

        except (ValueError, RuntimeError, KeyError) as e:
            logger.exception("Search error")
            return f"Error performing search: {e!s}"

    async def _get_handbook_section(
        self,
        section_name: str,
        limit: int = 50,
        sources: list[str] | None = None,
    ) -> str:
        """Retrieve all content from a specific section across collections.

        Fetches all documents that belong to the specified section from the
        vector stores. This is useful for retrieving complete section content
        rather than semantic search results.

        Args:
            section_name: Name of the section to retrieve
                         Example: 'introduction', 'guidelines', 'procedures'
            limit: Maximum number of chunks to return (default: 50, max: 100)
                  Clamped to range [1, 100]
            sources: Optional list of source names to search
                    If None, searches all available sources

        Returns:
            Formatted string containing:
                - Section header with name
                - Total number of chunks found
                - Each chunk with metadata (source, chunk index)
                OR error message if section not found or retrieval fails

        Example:
            >>> result = await server._get_handbook_section(
            ...     section_name="introduction", limit=10
            ... )
            >>> print(result)
            Section: 'introduction'
            Total chunks: 10
            ...
        """
        try:
            # Lazy load vector stores on first access
            self._ensure_vector_stores_loaded()

            # Validate and clamp limit to acceptable range
            limit = max(1, min(limit, 100))

            if not self.vector_stores:
                msg = "No vector stores are initialized"
                raise RuntimeError(msg)

            # Determine which sources to search
            available_sources = list(self.vector_stores.keys())
            sources_to_search = [s for s in sources if s in available_sources] if sources else available_sources

            # Collect results from all sources
            all_docs: list[tuple[str, dict, str]] = []

            for source_name in sources_to_search:
                vector_store = self.vector_stores[source_name]
                results = vector_store.get_documents(where={"section": section_name}, limit=limit)

                for doc, metadata in zip(results["documents"], results["metadatas"], strict=True):
                    enriched_metadata = {**metadata, "source_name": source_name}
                    all_docs.append((doc, enriched_metadata, source_name))

            # Check if any documents were found
            if not all_docs:
                sources_str = ", ".join(sources_to_search)
                return f"ERROR: No content found for section: '{section_name}' in sources: {sources_str}"

            # Limit total results
            all_docs = all_docs[:limit]

            # Format results
            sources_str = ", ".join(sources_to_search)
            result_lines = [
                f"Section: '{section_name}'",
                f"Sources: {sources_str}",
                f"Total chunks: {len(all_docs)}",
                "",
            ]

            # Add each document with metadata
            for i, (doc, metadata, source_name) in enumerate(all_docs, 1):
                result_lines.append(f"--- Chunk {i} ---")
                result_lines.append(f"Collection: {source_name}")

                # Add metadata if available
                if metadata:
                    if "source" in metadata:
                        result_lines.append(f"Source: {metadata['source']}")
                    if "chunk_index" in metadata:
                        result_lines.append(f"Chunk Index: {metadata['chunk_index']}")

                result_lines.append(f"\nContent:\n{doc}\n")

            logger.info(
                "Retrieved %d chunks from section '%s' across %d sources",
                len(all_docs),
                section_name,
                len(sources_to_search),
            )

            return "\n".join(result_lines)

        except (ValueError, RuntimeError, KeyError) as e:
            logger.exception("Error retrieving section")
            return f"Error retrieving section '{section_name}': {e!s}"

    async def _list_handbook_topics(self, max_depth: int = 2) -> str:
        """List all available topics and sections across all collections.

        Retrieves unique section names from all vector store metadata and
        organizes them into a structured view of the content organization.

        Args:
            max_depth: Maximum depth for nested sections (default: 2, max: 5)
                      Currently used for future hierarchical organization
                      Clamped to range [1, 5]

        Returns:
            Formatted string containing:
                - List of available collections with document counts
                - Sections per collection
                - Total document counts
                OR error message if retrieval fails

        Example:
            >>> result = await server._list_handbook_topics(max_depth=2)
            >>> print(result)
            Document Collections Overview
            ==============================

            Collection: handbook (1500 documents)
            Available Sections:
              - introduction (10 chunks)
              - guidelines (25 chunks)
            ...
        """
        try:
            if self.vector_store is None:
                return "Error: Handbook database not available. Please ensure the handbook was ingested."
            # Lazy load vector stores on first access
            self._ensure_vector_stores_loaded()

            # Validate and clamp max_depth
            max_depth = max(1, min(max_depth, 5))

            if not self.vector_stores:
                return "Error: No document collections available."

            result_lines = [
                "Document Collections Overview",
                "==============================",
                "",
            ]

            total_all_docs = 0
            total_all_sections = 0

            for source_name, vector_store in sorted(self.vector_stores.items()):
                # Get total document count for this collection
                doc_count = vector_store.get_document_count()
                total_all_docs += doc_count

                # Get source description if available
                source_config = self.source_registry.get(source_name)
                description = source_config.description if source_config else ""

                result_lines.append(f"Collection: {source_name} ({doc_count} documents)")
                if description:
                    result_lines.append(f"  Description: {description}")

                if doc_count == 0:
                    result_lines.append("  (empty)")
                    result_lines.append("")
                    continue

                # Get all documents to extract unique sections
                all_docs = vector_store.get_documents(limit=doc_count)

                # Count documents per section
                section_counts: dict[str, int] = {}
                for metadata in all_docs["metadatas"]:
                    if metadata and "section" in metadata:
                        section = metadata["section"]
                        section_counts[section] = section_counts.get(section, 0) + 1

                total_all_sections += len(section_counts)

                if section_counts:
                    result_lines.append("  Sections:")
                    # Sort sections alphabetically for consistent output
                    for section in sorted(section_counts.keys()):
                        count = section_counts[section]
                        chunk_label = "chunk" if count == 1 else "chunks"
                        result_lines.append(f"    - {section} ({count} {chunk_label})")
                else:
                    result_lines.append("  (no sections defined)")

                result_lines.append("")

            # Add summary
            result_lines.extend(
                [
                    "Summary",
                    "-------",
                    f"Total collections: {len(self.vector_stores)}",
                    f"Total documents: {total_all_docs}",
                    f"Total sections: {total_all_sections}",
                ]
            )

            logger.info(
                "Listed %d collections with %d total documents",
                len(self.vector_stores),
                total_all_docs,
            )

            return "\n".join(result_lines)

        except (ValueError, RuntimeError, KeyError) as e:
            logger.exception("Error listing topics")
            return f"Error listing topics: {e!s}"

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
        commit_date = datetime.fromtimestamp(commit.committed_date, tz=UTC)
        lines.append(f"Date: {commit_date.strftime('%Y-%m-%d %H:%M:%S UTC')}")
        lines.append(f"Author: {commit.author.name} <{commit.author.email}>")

        # Add commit message (first line only for brevity)
        message = (commit.message or "").split("\n", 1)[0].strip() or "(no message)"
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

    async def _get_recent_updates(  # noqa: PLR0911, PLR0912
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
            ...     days=7, path_filter="content/", max_commits=10
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
            since_date = datetime.now(UTC) - timedelta(days=days)

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

    def get_sse_app(self) -> Starlette:
        """Create Starlette app with SSE transport for remote MCP connections.

        Returns:
            Starlette: ASGI application with SSE endpoints for MCP protocol
        """
        sse = SseServerTransport("/messages")

        async def handle_sse(scope: Scope, receive: Receive, send: Send) -> None:
            """Handle GET /sse: establish SSE and run MCP server over read/write streams."""
            async with sse.connect_sse(scope, receive, send) as streams:
                # Run MCP protocol over the bidirectional streams until client disconnects.
                await self.server.run(streams[0], streams[1], self.server.create_initialization_options())

        async def handle_messages(scope: Scope, receive: Receive, send: Send) -> None:
            """Handle POST /messages: process incoming MCP JSON-RPC messages."""
            await sse.handle_post_message(scope, receive, send)

        return Starlette(
            debug=True,
            routes=[
                Route("/sse", handle_sse),
                Route("/messages", handle_messages, methods=["POST"]),
            ],
        )


async def invoker() -> None:
    """Create ThothMCPServer and run the MCP protocol (stdio or SSE).

    Used as the async entry point; run_server() wraps this with asyncio.run().
    """
    server = ThothMCPServer()
    await server.run()


def run_server() -> None:
    """Synchronous entry point: run the MCP server until interrupted.

    Runs the async invoker in the default event loop. Exits on KeyboardInterrupt
    or propagates other exceptions.
    """
    try:
        # Run the async MCP server in the default event loop.
        asyncio.run(invoker())
    except KeyboardInterrupt:
        logger.info("Server shutdown requested")
    except Exception:
        logger.exception("Server error")
        raise
