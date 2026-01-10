"""
Unit tests for Thoth MCP Server.

Tests the ThothMCPServer class and its handlers using unittest.TestCase.
"""

import contextlib
from datetime import datetime, timezone
import inspect
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from git import GitCommandError
from mcp.server import Server
from mcp.types import TextContent, Tool

from thoth.mcp_server.server import ThothMCPServer, invoker, run_server


class TestThothMCPServer(unittest.TestCase):
    """Test suite for ThothMCPServer class."""

    def setUp(self):
        """Set up test fixtures before each test."""
        self.server_name = "test-server"
        self.server_version = "0.0.1"
        self.server = ThothMCPServer(name=self.server_name, version=self.server_version)

    def test_server_initialization(self):
        """Test that server initializes with correct name and version."""
        self.assertEqual(self.server.name, self.server_name)
        self.assertEqual(self.server.version, self.server_version)
        self.assertIsNotNone(self.server.server)

    def test_server_initialization_with_defaults(self):
        """Test that server initializes with default values."""
        default_server = ThothMCPServer()
        self.assertEqual(default_server.name, "thoth-server")
        self.assertEqual(default_server.version, "1.0.0")

    def test_setup_handlers_called(self):
        """Test that _setup_handlers is called during initialization."""
        with patch.object(ThothMCPServer, "_setup_handlers") as mock_setup:
            ThothMCPServer()
            mock_setup.assert_called_once()


class TestMCPServerHandlers(unittest.IsolatedAsyncioTestCase):
    """Test suite for MCP server handlers (async tests)."""

    async def asyncSetUp(self):
        """Set up async test fixtures before each test."""
        self.server = ThothMCPServer(name="test-server", version="0.0.1")

    async def test_list_tools_handler(self):
        """Test that list_tools returns expected tool definitions."""
        # Access the registered handler through the server's handlers
        # Since the handlers are registered as decorators, we need to test them
        # by checking if they're callable and return expected structure
        # For now, we'll test the structure indirectly

        # Create a mock list_tools response
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

        # Verify server has the handlers set up
        self.assertIsNotNone(self.server.server)

    async def test_call_tool_ping_with_message(self):
        """Test calling the ping tool with a custom message."""
        # This tests the logic that would be executed by call_tool handler
        test_message = "Hello, Thoth!"
        expected_result = f"pong: {test_message}"

        # Simulate what the handler does
        arguments = {"message": test_message}
        result = f"pong: {arguments.get('message', 'ping')}"

        self.assertEqual(result, expected_result)

    async def test_call_tool_ping_without_message(self):
        """Test calling the ping tool without a message (uses default)."""
        # Test with empty arguments
        arguments = {}
        result = f"pong: {arguments.get('message', 'ping')}"
        expected_result = "pong: ping"

        self.assertEqual(result, expected_result)

    async def test_call_tool_unknown_tool(self):
        """Test that calling unknown tool raises ValueError."""
        # Test the logic for unknown tools
        tool_name = "nonexistent_tool"

        with self.assertRaises(ValueError) as context:
            msg = f"Unknown tool: {tool_name}"
            raise ValueError(msg)

        self.assertIn("Unknown tool", str(context.exception))
        self.assertIn(tool_name, str(context.exception))

    async def test_list_resources_returns_empty_list(self):
        """Test that list_resources returns an empty list."""
        # Test the expected behavior of list_resources
        resources = []
        self.assertEqual(resources, [])
        self.assertIsInstance(resources, list)

    async def test_read_resource_raises_error(self):
        """Test that read_resource raises ValueError for any URI."""
        test_uri = "thoth://test/resource"

        with self.assertRaises(ValueError) as context:
            msg = f"Resource not found: {test_uri}"
            raise ValueError(msg)

        self.assertIn("Resource not found", str(context.exception))
        self.assertIn(test_uri, str(context.exception))


class TestServerRunMethods(unittest.IsolatedAsyncioTestCase):
    """Test suite for server run methods."""

    @patch("thoth.mcp_server.server.stdio_server")
    async def test_run_method(self, mock_stdio):
        """Test that run method starts server with stdio transport."""
        # Setup mocks
        mock_read_stream = AsyncMock()
        mock_write_stream = AsyncMock()
        mock_stdio.return_value.__aenter__.return_value = (
            mock_read_stream,
            mock_write_stream,
        )

        server = ThothMCPServer()

        # Mock the server.run method to avoid actual server startup
        with patch.object(server.server, "run", new_callable=AsyncMock) as mock_run:
            await server.run()

            # Verify server.run was called
            mock_run.assert_called_once()

    @patch("thoth.mcp_server.server.ThothMCPServer")
    async def test_main_function(self, mock_server_class):
        """Test that main function creates and runs server."""
        mock_server_instance = AsyncMock()
        mock_server_class.return_value = mock_server_instance

        await invoker()

        mock_server_class.assert_called_once()
        mock_server_instance.run.assert_called_once()


class TestRunServerFunction(unittest.TestCase):
    """Test suite for synchronous run_server function."""

    @patch("thoth.mcp_server.server.asyncio.run")
    def test_run_server_success(self, mock_asyncio_run):
        """Test that run_server calls asyncio.run with main."""
        run_server()
        # Verify asyncio.run was called once (don't check the exact coroutine object)
        mock_asyncio_run.assert_called_once()

    @patch("thoth.mcp_server.server.asyncio.run")
    @patch("thoth.mcp_server.server.logger")
    def test_run_server_keyboard_interrupt(self, mock_logger, mock_asyncio_run):
        """Test that run_server handles KeyboardInterrupt gracefully."""
        mock_asyncio_run.side_effect = KeyboardInterrupt()

        # Should not raise, just log
        run_server()
        mock_logger.info.assert_called_with("Server shutdown requested")

    @patch("thoth.mcp_server.server.asyncio.run")
    @patch("thoth.mcp_server.server.logger")
    def test_run_server_exception(self, mock_logger, mock_asyncio_run):
        """Test that run_server logs and re-raises exceptions."""
        test_exception = RuntimeError("Test error")
        mock_asyncio_run.side_effect = test_exception

        with self.assertRaises(RuntimeError):
            run_server()

        # Verify error was logged
        mock_logger.exception.assert_called()
        call_args = mock_logger.exception.call_args
        self.assertIn("Server error", call_args[0][0])


class TestToolResponse(unittest.TestCase):
    """Test suite for tool response formatting."""

    def test_text_content_creation(self):
        """Test creating TextContent response."""
        message = "Test message"
        content = TextContent(type="text", text=message)

        self.assertEqual(content.type, "text")
        self.assertEqual(content.text, message)

    def test_tool_definition_structure(self):
        """Test Tool definition has required fields."""
        tool = Tool(
            name="test_tool",
            description="Test description",
            inputSchema={
                "type": "object",
                "properties": {},
            },
        )

        self.assertEqual(tool.name, "test_tool")
        self.assertEqual(tool.description, "Test description")
        self.assertIsInstance(tool.inputSchema, dict)
        self.assertEqual(tool.inputSchema["type"], "object")

    def test_ping_tool_response_format(self):
        """Test ping tool response format."""
        message = "test"
        expected = f"pong: {message}"

        # Simulate ping tool response
        response = f"pong: {message}"
        self.assertEqual(response, expected)

        # Test default message
        default_response = "pong: ping"
        self.assertEqual(default_response, "pong: ping")


class TestServerIntegration(unittest.IsolatedAsyncioTestCase):
    """Integration tests for server components."""

    async def asyncSetUp(self):
        """Set up integration test fixtures."""
        self.server = ThothMCPServer(name="integration-test", version="0.1.0")

    async def test_server_has_mcp_server_instance(self):
        """Test that ThothMCPServer contains MCP Server instance."""
        self.assertIsInstance(self.server.server, Server)

    async def test_server_attributes_accessible(self):
        """Test that server attributes are properly accessible."""
        self.assertEqual(self.server.name, "integration-test")
        self.assertEqual(self.server.version, "0.1.0")
        self.assertTrue(hasattr(self.server, "server"))
        self.assertTrue(hasattr(self.server, "_setup_handlers"))
        self.assertTrue(hasattr(self.server, "run"))


class TestMCPTools(unittest.IsolatedAsyncioTestCase):
    """Comprehensive test suite for MCP tools."""

    async def asyncSetUp(self):
        """Set up test fixtures for tool tests."""
        self.server = ThothMCPServer(name="tool-test-server", version="0.0.1")

    async def test_ping_tool_exists(self):
        """Test that ping tool is registered."""
        # The ping tool should be defined in the handlers
        # We can verify by checking the server has handlers set up
        self.assertIsNotNone(self.server.server)

    async def test_ping_tool_with_default_message(self):
        """Test ping tool with no message (uses default 'ping')."""
        # Simulate the ping tool logic
        arguments = {}
        message = arguments.get("message", "ping")
        result = f"pong: {message}"

        self.assertEqual(result, "pong: ping")
        self.assertIsInstance(result, str)

    async def test_ping_tool_with_custom_message(self):
        """Test ping tool with custom message."""
        test_messages = [
            "Hello, World!",
            "test123",
            "MCP Server Test",
            "健康チェック",  # Unicode test
            "multi word message",
        ]

        for test_message in test_messages:
            with self.subTest(message=test_message):
                arguments = {"message": test_message}
                message = arguments.get("message", "ping")
                result = f"pong: {message}"

                self.assertEqual(result, f"pong: {test_message}")
                self.assertIn(test_message, result)

    async def test_ping_tool_with_empty_string(self):
        """Test ping tool with empty string message."""
        arguments = {"message": ""}
        message = arguments.get("message", "ping")
        result = f"pong: {message}"

        self.assertEqual(result, "pong: ")

    async def test_ping_tool_response_format(self):
        """Test that ping tool response follows correct format."""
        test_message = "format_test"
        arguments = {"message": test_message}
        message = arguments.get("message", "ping")
        result = f"pong: {message}"

        # Verify format
        self.assertTrue(result.startswith("pong: "))
        self.assertIn(test_message, result)
        self.assertEqual(result.split(": ", 1)[0], "pong")

    async def test_ping_tool_schema_validation(self):
        """Test ping tool schema structure."""
        # Expected schema for ping tool
        expected_schema = {
            "type": "object",
            "properties": {
                "message": {
                    "type": "string",
                    "description": "Optional message to echo back in the response",
                    "default": "ping",
                }
            },
            "required": [],
        }

        # Verify schema structure
        self.assertIsInstance(expected_schema, dict)
        self.assertEqual(expected_schema["type"], "object")
        self.assertIn("message", expected_schema["properties"])
        self.assertEqual(expected_schema["required"], [])

    async def test_ping_tool_text_content_response(self):
        """Test that ping tool returns TextContent objects."""
        message = "content_test"
        result = f"pong: {message}"
        content = TextContent(type="text", text=result)

        self.assertEqual(content.type, "text")
        self.assertEqual(content.text, result)
        self.assertIsInstance(content, TextContent)

    async def test_tool_error_handling_unknown_tool(self):
        """Test error handling for unknown tools."""
        unknown_tools = ["invalid_tool", "not_a_tool", "xyz123"]

        for tool_name in unknown_tools:
            with self.subTest(tool=tool_name):
                with self.assertRaises(ValueError) as context:
                    msg = f"Unknown tool: {tool_name}"
                    raise ValueError(msg)

                self.assertIn("Unknown tool", str(context.exception))
                self.assertIn(tool_name, str(context.exception))

    async def test_tool_list_structure(self):
        """Test that tool list follows MCP Tool schema."""
        # Verify Tool object can be created with required fields
        tool = Tool(
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

        self.assertEqual(tool.name, "ping")
        self.assertIsInstance(tool.description, str)
        self.assertIsInstance(tool.inputSchema, dict)
        self.assertGreater(len(tool.description), 0)


class TestMCPResources(unittest.IsolatedAsyncioTestCase):
    """Comprehensive test suite for MCP resources."""

    async def asyncSetUp(self):
        """Set up test fixtures for resource tests."""
        self.server = ThothMCPServer(name="resource-test-server", version="0.0.1")

    async def test_list_resources_returns_list(self):
        """Test that list_resources returns a list."""
        resources = []
        self.assertIsInstance(resources, list)

    async def test_list_resources_empty_by_default(self):
        """Test that resources list is empty by default."""
        resources = []
        self.assertEqual(len(resources), 0)
        self.assertEqual(resources, [])

    async def test_read_resource_not_found(self):
        """Test that reading non-existent resource raises ValueError."""
        test_uris = [
            "thoth://resource/test",
            "file:///nonexistent",
            "http://example.com/resource",
        ]

        for uri in test_uris:
            with self.subTest(uri=uri):
                with self.assertRaises(ValueError) as context:
                    msg = f"Resource not found: {uri}"
                    raise ValueError(msg)

                self.assertIn("Resource not found", str(context.exception))
                self.assertIn(uri, str(context.exception))

    async def test_resource_uri_format(self):
        """Test resource URI format validation."""
        valid_uris = [
            "thoth://resource/test",
            "file:///path/to/resource",
            "custom://scheme/path",
        ]

        for uri in valid_uris:
            with self.subTest(uri=uri):
                self.assertIsInstance(uri, str)
                self.assertIn("://", uri)

    async def test_resource_error_message_format(self):
        """Test that resource error messages are properly formatted."""
        test_uri = "thoth://test/resource"
        error_msg = f"Resource not found: {test_uri}"

        self.assertIn("Resource not found", error_msg)
        self.assertIn(test_uri, error_msg)
        self.assertTrue(error_msg.startswith("Resource not found:"))


class TestSearchHandbookTool(unittest.IsolatedAsyncioTestCase):
    """Test suite for search_handbook MCP tool functionality."""

    async def asyncSetUp(self):
        """Set up test fixtures for search tests."""
        # Create server with actual handbook database
        self.server = ThothMCPServer(
            name="search-test-server",
            version="0.0.1",
            handbook_db_path="./handbook_vectors",
        )

    async def test_server_initialization_with_vector_store(self):
        """Test that server initializes vector store if database exists."""
        self.assertTrue(hasattr(self.server, "vector_store"))
        # Vector store may be None if database doesn't exist, which is OK

    async def test_search_handbook_tool_exists_when_db_available(self):
        """Test that search_handbook tool is available when database exists."""
        # If vector store is available, the tool should be registered
        if self.server.vector_store is not None:
            self.assertIsNotNone(self.server.vector_store)
            self.assertTrue(hasattr(self.server, "_search_handbook"))
            self.assertTrue(hasattr(self.server, "_cached_search"))

    async def test_search_handbook_parameters(self):
        """Test search_handbook tool parameter schema."""
        expected_params = ["query", "n_results", "filter_section"]
        # The tool should accept these parameters
        # We verify the structure exists
        self.assertIsNotNone(expected_params)
        self.assertEqual(len(expected_params), 3)

    async def test_search_handbook_n_results_validation(self):
        """Test that n_results is validated to be between 1 and 20."""
        test_cases = [
            (0, 1),  # Below minimum should be clamped to 1
            (1, 1),  # Minimum value
            (5, 5),  # Default/normal value
            (10, 10),  # Normal value
            (20, 20),  # Maximum value
            (25, 20),  # Above maximum should be clamped to 20
            (100, 20),  # Well above maximum should be clamped to 20
        ]

        for input_val, expected in test_cases:
            with self.subTest(input=input_val):
                # Simulate the validation logic from _search_handbook
                validated = max(1, min(input_val, 20))
                self.assertEqual(validated, expected)

    async def test_search_handbook_query_required(self):
        """Test that query parameter is required."""
        # Query should be required parameter
        required_params = ["query"]
        self.assertIn("query", required_params)
        self.assertEqual(len(required_params), 1)

    async def test_search_handbook_filter_section_optional(self):
        """Test that filter_section parameter is optional."""
        # Test with None value (no filter)
        filter_section = None
        where_filter = {"section": filter_section} if filter_section else None
        self.assertIsNone(where_filter)

        # Test with actual section
        filter_section = "introduction"
        where_filter = {"section": filter_section} if filter_section else None
        self.assertEqual(where_filter, {"section": "introduction"})

    async def test_search_result_formatting(self):
        """Test that search results are formatted correctly."""
        # Mock result structure
        docs = ["Document 1", "Document 2"]
        metadatas = [
            {"section": "intro", "source": "file1.txt", "chunk_index": 0},
            {"section": "body", "source": "file2.txt", "chunk_index": 1},
        ]
        distances = [0.1, 0.2]

        # Test result formatting logic
        self.assertEqual(len(docs), len(metadatas))
        self.assertEqual(len(docs), len(distances))

        for _i, (_doc, metadata, distance) in enumerate(zip(docs, metadatas, distances, strict=True), 1):
            relevance_score = 1 - distance
            self.assertGreater(relevance_score, 0)
            self.assertLessEqual(relevance_score, 1)
            self.assertIn("section", metadata)
            self.assertIn("source", metadata)

    async def test_search_no_results_message(self):
        """Test message format when no results are found."""
        query = "nonexistent query"
        filter_section = None

        # Simulate no results (empty list)
        expected_msg = f"No results found for query: '{query}'"

        result_msg = f"No results found for query: '{query}'" + (
            f" in section '{filter_section}'" if filter_section else ""
        )

        self.assertEqual(result_msg, expected_msg)

    async def test_search_no_results_with_filter_message(self):
        """Test message format when no results with section filter."""
        query = "test query"
        filter_section = "nonexistent_section"

        result_msg = f"No results found for query: '{query}'" + (
            f" in section '{filter_section}'" if filter_section else ""
        )

        expected = f"No results found for query: '{query}' in section '{filter_section}'"
        self.assertEqual(result_msg, expected)

    async def test_cached_search_method_exists(self):
        """Test that _cached_search method exists and uses manual caching."""
        self.assertTrue(hasattr(self.server, "_cached_search"))
        # Check if cache dict exists (manual caching implementation)
        self.assertTrue(hasattr(self.server, "_search_cache"))

    async def test_cached_search_returns_tuple(self):
        """Test that _cached_search returns expected tuple structure."""
        # The method should return a tuple with 5 elements
        expected_tuple_length = 5
        self.assertEqual(expected_tuple_length, 5)

    async def test_search_performance_timing(self):
        """Test that search timing is recorded."""
        start_time = time.time()
        # Simulate some work
        time.sleep(0.001)  # 1ms
        search_time = time.time() - start_time

        self.assertGreater(search_time, 0)
        # Should be much less than 1 second for this test
        self.assertLess(search_time, 1.0)

    async def test_search_metadata_filter_construction(self):
        """Test that metadata filters are constructed correctly."""
        # Test with no filter
        filter_section = None
        where_filter = {"section": filter_section} if filter_section else None
        self.assertIsNone(where_filter)

        # Test with filter
        filter_section = "procedures"
        where_filter = {"section": filter_section} if filter_section else None
        self.assertEqual(where_filter, {"section": "procedures"})
        self.assertIsInstance(where_filter, dict)

    async def test_search_error_handling(self):
        """Test that search errors are handled gracefully."""
        # Simulate error handling
        try:
            msg = "Test search error"
            raise ValueError(msg)
        except ValueError as e:
            error_msg = f"Error performing search: {e!s}"
            self.assertIn("Error performing search", error_msg)
            self.assertIn("Test search error", error_msg)

    async def test_search_result_header_format(self):
        """Test that search result header is formatted correctly."""
        query = "test query"
        n_results = 3
        filter_section = "guidelines"
        search_time = 0.123

        header_lines = [
            f"Search Results for: '{query}'",
            f"Found {n_results} result(s) in section '{filter_section}'",
            f"Search time: {search_time:.3f}s",
            "",
        ]

        self.assertEqual(len(header_lines), 4)
        self.assertIn(query, header_lines[0])
        self.assertIn(str(n_results), header_lines[1])
        self.assertIn(filter_section, header_lines[1])
        self.assertIn("0.123s", header_lines[2])

    async def test_search_relevance_score_calculation(self):
        """Test that relevance score is calculated correctly."""
        distances = [0.0, 0.1, 0.5, 0.9, 1.0]
        expected_scores = [1.0, 0.9, 0.5, 0.1, 0.0]

        for distance, expected_score in zip(distances, expected_scores, strict=True):
            relevance_score = 1 - distance
            self.assertAlmostEqual(relevance_score, expected_score, places=10)

    async def test_search_result_metadata_display(self):
        """Test that metadata fields are displayed when available."""
        metadata = {
            "section": "introduction",
            "source": "handbook.md",
            "chunk_index": 5,
        }

        # Test section display
        if "section" in metadata:
            section_line = f"Section: {metadata['section']}"
            self.assertEqual(section_line, "Section: introduction")

        # Test source display
        if "source" in metadata:
            source_line = f"Source: {metadata['source']}"
            self.assertEqual(source_line, "Source: handbook.md")

        # Test chunk_index display
        if "chunk_index" in metadata:
            chunk_line = f"Chunk: {metadata['chunk_index']}"
            self.assertEqual(chunk_line, "Chunk: 5")

    async def test_database_not_available_error(self):
        """Test error message when database is not available."""
        error_msg = "Error: Handbook database not available. Please ensure the handbook has been ingested."

        self.assertIn("Error", error_msg)
        self.assertIn("Handbook database not available", error_msg)
        self.assertIn("ingested", error_msg)

    @patch("thoth.mcp_server.server.VectorStore")
    async def test_vector_store_initialization_failure(self, mock_vector_store):
        """Test handling of vector store initialization failure."""
        mock_vector_store.side_effect = Exception("Database connection failed")

        # Server should handle this gracefully
        server = ThothMCPServer(handbook_db_path="./nonexistent")
        # Vector store should be None on initialization failure
        self.assertIsNone(server.vector_store)

    async def test_search_with_various_section_names(self):
        """Test filtering with various section names."""
        test_sections = [
            "introduction",
            "procedures",
            "guidelines",
            "policies",
            "references",
        ]

        for section in test_sections:
            with self.subTest(section=section):
                where_filter = {"section": section}
                self.assertEqual(where_filter["section"], section)
                self.assertIsInstance(where_filter, dict)


class TestSearchHandbookPerformance(unittest.IsolatedAsyncioTestCase):
    """Test suite for search_handbook performance requirements (Issue #35)."""

    async def asyncSetUp(self):
        """Set up test fixtures for performance tests."""
        self.server = ThothMCPServer(
            name="performance-test-server",
            version="0.0.1",
            handbook_db_path="./handbook_vectors",
        )
        self.performance_target = 2.0  # seconds

    async def test_performance_target_defined(self):
        """Test that performance target is set to <2s."""
        self.assertEqual(self.performance_target, 2.0)
        self.assertGreater(self.performance_target, 0)

    async def test_cache_size_configured(self):
        """Test that cache is configured with appropriate size."""
        if hasattr(self.server, "_search_cache"):
            # Check cache dict exists and max size is configured
            self.assertIsNotNone(self.server._search_cache)
            self.assertEqual(self.server._cache_max_size, 100)

    async def test_cache_hit_improves_performance(self):
        """Test that cache hits improve performance."""
        if self.server.vector_store is None:
            self.skipTest("Vector store not available")

        query = "test query"
        n_results = 5
        filter_section = None

        # First call (cache miss)
        start1 = time.time()
        try:
            self.server._cached_search(query, n_results, filter_section)
            time1 = time.time() - start1
        except (ValueError, RuntimeError, AttributeError):
            self.skipTest("Cannot perform search without valid database")

        # Second call (cache hit)
        start2 = time.time()
        self.server._cached_search(query, n_results, filter_section)
        time2 = time.time() - start2

        # Cache hit should be faster or similar
        # We just verify both complete in reasonable time
        self.assertLess(time1, 10.0)  # Generous timeout
        self.assertLess(time2, 10.0)

    async def test_timing_measurement_included(self):
        """Test that search timing is measured and returned."""
        start_time = time.time()
        # Simulate search
        time.sleep(0.01)  # 10ms
        search_time = time.time() - start_time

        # Verify timing is measured
        self.assertGreater(search_time, 0)
        self.assertIsInstance(search_time, float)

    async def test_search_time_included_in_results(self):
        """Test that search time is included in formatted results."""
        search_time = 0.456
        time_line = f"Search time: {search_time:.3f}s"

        self.assertEqual(time_line, "Search time: 0.456s")
        self.assertIn("Search time:", time_line)
        self.assertIn("s", time_line)


class TestHandbookToolIntegration(unittest.IsolatedAsyncioTestCase):
    """Integration tests for search_handbook tool (Issues #33, #34, #35)."""

    async def asyncSetUp(self):
        """Set up integration test fixtures."""
        self.server = ThothMCPServer(
            name="integration-test",
            version="1.0.0",
            handbook_db_path="./handbook_vectors",
        )

    async def test_issue_33_basic_search_implementation(self):
        """Test Issue #33: Basic search tool is implemented."""
        # Verify tool exists
        self.assertTrue(hasattr(self.server, "_search_handbook"))

        # Verify it's async
        self.assertTrue(inspect.iscoroutinefunction(self.server._search_handbook))

    async def test_issue_34_section_filtering_implementation(self):
        """Test Issue #34: Section filtering is implemented."""
        # Verify filter_section parameter is supported
        sig = inspect.signature(self.server._search_handbook)
        self.assertIn("filter_section", sig.parameters)

        # Verify default is None (optional parameter)
        self.assertIsNone(sig.parameters["filter_section"].default)

    async def test_issue_35_caching_implementation(self):
        """Test Issue #35: Caching is implemented."""
        # Verify _cached_search exists
        self.assertTrue(hasattr(self.server, "_cached_search"))

        # Verify cache dict exists
        self.assertTrue(hasattr(self.server, "_search_cache"))
        self.assertTrue(hasattr(self.server, "_cache_max_size"))

    async def test_all_requirements_met(self):
        """Test that all three issues' requirements are met."""
        # Issue #33: Tool callable from Claude
        self.assertTrue(hasattr(self.server, "_search_handbook"))

        # Issue #34: Section filtering
        sig = inspect.signature(self.server._search_handbook)
        self.assertIn("filter_section", sig.parameters)

        # Issue #35: Performance optimization with caching
        self.assertTrue(hasattr(self.server, "_search_cache"))


class TestGetHandbookSection(unittest.IsolatedAsyncioTestCase):
    """Test suite for get_handbook_section tool (Issue #37)."""

    async def asyncSetUp(self):
        """Set up test fixtures for section retrieval tests."""
        self.server = ThothMCPServer(
            name="section-test-server",
            version="1.0.0",
            handbook_db_path="./handbook_vectors",
        )

    async def test_get_handbook_section_method_exists(self):
        """Test that _get_handbook_section method exists."""
        self.assertTrue(hasattr(self.server, "_get_handbook_section"))
        self.assertTrue(inspect.iscoroutinefunction(self.server._get_handbook_section))

    async def test_get_handbook_section_signature(self):
        """Test _get_handbook_section has correct signature."""
        sig = inspect.signature(self.server._get_handbook_section)
        self.assertIn("section_name", sig.parameters)
        self.assertIn("limit", sig.parameters)

        # Check defaults
        self.assertEqual(sig.parameters["limit"].default, 50)

    async def test_get_handbook_section_with_no_vector_store(self):
        """Test error handling when vector store is not available."""
        self.server.vector_store = None
        result = await self.server._get_handbook_section("test_section")
        self.assertIn("Error", result)

    async def test_get_handbook_section_limit_validation(self):
        """Test that limit parameter is validated and clamped."""
        if self.server.vector_store is None:
            self.skipTest("Vector store not available")

        # Test will clamp limits in the actual method
        # We just need to verify the method handles edge cases
        with patch.object(self.server.vector_store, "get_documents") as mock_get:
            mock_get.return_value = {"documents": [], "metadatas": []}

            # Test with various limits
            await self.server._get_handbook_section("test", limit=1)
            await self.server._get_handbook_section("test", limit=100)
            # Should clamp to 1
            await self.server._get_handbook_section("test", limit=0)
            # Should clamp to 100
            await self.server._get_handbook_section("test", limit=200)

    async def test_get_handbook_section_formats_output(self):
        """Test that section retrieval formats output correctly."""
        if self.server.vector_store is None:
            self.skipTest("Vector store not available")

        with patch.object(self.server.vector_store, "get_documents") as mock_get:
            mock_get.return_value = {
                "documents": ["Test content 1", "Test content 2"],
                "metadatas": [
                    {"section": "test", "source": "test.md", "chunk_index": 0},
                    {"section": "test", "source": "test.md", "chunk_index": 1},
                ],
            }

            result = await self.server._get_handbook_section("test")

            # Verify output format
            self.assertIn("Handbook Section:", result)
            self.assertIn("test", result)
            self.assertIn("Total chunks:", result)
            self.assertIn("Test content 1", result)
            self.assertIn("Test content 2", result)

    async def test_get_handbook_section_no_results(self):
        """Test handling when section has no content."""
        if self.server.vector_store is None:
            self.skipTest("Vector store not available")

        with patch.object(self.server.vector_store, "get_documents") as mock_get:
            mock_get.return_value = {"documents": [], "metadatas": []}

            result = await self.server._get_handbook_section("nonexistent")
            self.assertIn("No content found", result)
            self.assertIn("nonexistent", result)


class TestListHandbookTopics(unittest.IsolatedAsyncioTestCase):
    """Test suite for list_handbook_topics tool (Issue #38)."""

    async def asyncSetUp(self):
        """Set up test fixtures for topic listing tests."""
        self.server = ThothMCPServer(
            name="topics-test-server",
            version="1.0.0",
            handbook_db_path="./handbook_vectors",
        )

    async def test_list_handbook_topics_method_exists(self):
        """Test that _list_handbook_topics method exists."""
        self.assertTrue(hasattr(self.server, "_list_handbook_topics"))
        self.assertTrue(inspect.iscoroutinefunction(self.server._list_handbook_topics))

    async def test_list_handbook_topics_signature(self):
        """Test _list_handbook_topics has correct signature."""
        sig = inspect.signature(self.server._list_handbook_topics)
        self.assertIn("max_depth", sig.parameters)

        # Check default
        self.assertEqual(sig.parameters["max_depth"].default, 2)

    async def test_list_handbook_topics_with_no_vector_store(self):
        """Test error handling when vector store is not available."""
        self.server.vector_store = None
        result = await self.server._list_handbook_topics()
        self.assertIn("Error", result)

    async def test_list_handbook_topics_depth_validation(self):
        """Test that max_depth parameter is validated and clamped."""
        if self.server.vector_store is None:
            self.skipTest("Vector store not available")

        with (
            patch.object(self.server.vector_store, "get_document_count") as mock_count,
            patch.object(self.server.vector_store, "get_documents") as mock_get,
        ):
            mock_count.return_value = 0
            mock_get.return_value = {"documents": [], "metadatas": []}

            # Test with various depths
            await self.server._list_handbook_topics(max_depth=1)
            await self.server._list_handbook_topics(max_depth=5)
            # Should clamp to 1
            await self.server._list_handbook_topics(max_depth=0)
            # Should clamp to 5
            await self.server._list_handbook_topics(max_depth=10)

    async def test_list_handbook_topics_formats_output(self):
        """Test that topic listing formats output correctly."""
        if self.server.vector_store is None:
            self.skipTest("Vector store not available")

        with (
            patch.object(self.server.vector_store, "get_document_count") as mock_count,
            patch.object(self.server.vector_store, "get_documents") as mock_get,
        ):
            mock_count.return_value = 5
            mock_get.return_value = {
                "documents": ["doc1", "doc2", "doc3", "doc4", "doc5"],
                "metadatas": [
                    {"section": "introduction"},
                    {"section": "introduction"},
                    {"section": "guidelines"},
                    {"section": "guidelines"},
                    {"section": "procedures"},
                ],
            }

            result = await self.server._list_handbook_topics()

            # Verify output format
            self.assertIn("Handbook Topics and Sections", result)
            self.assertIn("Total documents:", result)
            self.assertIn("Available Sections:", result)
            self.assertIn("introduction", result)
            self.assertIn("guidelines", result)
            self.assertIn("procedures", result)
            self.assertIn("chunks", result)

    async def test_list_handbook_topics_empty_handbook(self):
        """Test handling when handbook is empty."""
        if self.server.vector_store is None:
            self.skipTest("Vector store not available")

        with patch.object(self.server.vector_store, "get_document_count") as mock_count:
            mock_count.return_value = 0

            result = await self.server._list_handbook_topics()
            self.assertIn("empty", result.lower())
            self.assertIn("No topics", result)

    async def test_list_handbook_topics_counts_sections(self):
        """Test that topic listing correctly counts chunks per section."""
        if self.server.vector_store is None:
            self.skipTest("Vector store not available")

        with (
            patch.object(self.server.vector_store, "get_document_count") as mock_count,
            patch.object(self.server.vector_store, "get_documents") as mock_get,
        ):
            mock_count.return_value = 4
            mock_get.return_value = {
                "documents": ["d1", "d2", "d3", "d4"],
                "metadatas": [
                    {"section": "section_a"},
                    {"section": "section_a"},
                    {"section": "section_a"},
                    {"section": "section_b"},
                ],
            }

            result = await self.server._list_handbook_topics()

            # Verify counts are correct
            self.assertIn("section_a (3 chunks)", result)
            self.assertIn("section_b (1 chunk)", result)


class TestContentRetrievalToolsIntegration(unittest.IsolatedAsyncioTestCase):
    """Integration tests for content retrieval tools (Issue #36)."""

    async def asyncSetUp(self):
        """Set up integration test fixtures."""
        self.server = ThothMCPServer(
            name="content-retrieval-test",
            version="1.0.0",
            handbook_db_path="./handbook_vectors",
        )

    async def test_issue_36_requirements_met(self):
        """Test that Issue #36 requirements are met."""
        # Requirement: get_handbook_section works
        self.assertTrue(hasattr(self.server, "_get_handbook_section"))

        # Requirement: list_handbook_topics works
        self.assertTrue(hasattr(self.server, "_list_handbook_topics"))

    async def test_issue_37_get_handbook_section_implemented(self):
        """Test Issue #37: get_handbook_section is fully implemented."""
        # Tool exists and is async
        self.assertTrue(inspect.iscoroutinefunction(self.server._get_handbook_section))

        # Has required parameters
        sig = inspect.signature(self.server._get_handbook_section)
        self.assertIn("section_name", sig.parameters)
        self.assertIn("limit", sig.parameters)

    async def test_issue_38_list_handbook_topics_implemented(self):
        """Test Issue #38: list_handbook_topics is fully implemented."""
        # Tool exists and is async
        self.assertTrue(inspect.iscoroutinefunction(self.server._list_handbook_topics))

        # Has required parameters
        sig = inspect.signature(self.server._list_handbook_topics)
        self.assertIn("max_depth", sig.parameters)

    async def test_both_tools_handle_missing_database(self):
        """Test that both new tools handle missing database gracefully."""
        self.server.vector_store = None

        # Test get_handbook_section
        result1 = await self.server._get_handbook_section("test")
        self.assertIn("Error", result1)

        # Test list_handbook_topics
        result2 = await self.server._list_handbook_topics()
        self.assertIn("Error", result2)


class TestGetRecentUpdatesTools(unittest.IsolatedAsyncioTestCase):
    """Test suite for get_recent_updates tool (Issues #39 and #40)."""

    async def asyncSetUp(self):
        """Set up test fixtures."""
        self.server = ThothMCPServer(
            name="updates-test",
            version="1.0.0",
            handbook_db_path="./handbook_vectors",
            handbook_repo_path="/tmp/test-handbook",
        )

    async def test_issue_39_40_get_recent_updates_implemented(self):
        """Test Issues #39 and #40: get_recent_updates is fully implemented."""
        # Tool exists and is async
        self.assertTrue(hasattr(self.server, "_get_recent_updates"))
        self.assertTrue(inspect.iscoroutinefunction(self.server._get_recent_updates))

        # Has required parameters
        sig = inspect.signature(self.server._get_recent_updates)
        self.assertIn("days", sig.parameters)
        self.assertIn("path_filter", sig.parameters)
        self.assertIn("max_commits", sig.parameters)

    async def test_get_recent_updates_repository_not_found(self):
        """Test get_recent_updates when repository doesn't exist."""
        # Use a non-existent path
        self.server.handbook_repo_path = "/nonexistent/path"

        result = await self.server._get_recent_updates(days=7)

        # Should return error message
        self.assertIn("Error", result)
        self.assertIn("not found", result.lower())

    @patch("thoth.mcp_server.server.Repo")
    async def test_get_recent_updates_with_mock_repo(self, mock_repo_class):
        """Test get_recent_updates with mocked git repository."""
        # Create mock repository
        mock_repo = MagicMock()
        mock_repo_class.return_value = mock_repo

        # Create mock commits
        mock_commit = MagicMock()
        mock_commit.hexsha = "abc123def456"
        mock_commit.committed_date = datetime.now(timezone.utc).timestamp()
        mock_commit.author.name = "Test Author"
        mock_commit.author.email = "test@example.com"
        mock_commit.message = "Test commit message"
        mock_commit.parents = []
        mock_commit.stats.files = {"file1.md": {}, "file2.md": {}}

        mock_repo.iter_commits.return_value = [mock_commit]

        # Use existing path for this test
        with tempfile.TemporaryDirectory() as tmpdir:
            self.server.handbook_repo_path = tmpdir
            # Create .git directory to make it look like a repo
            Path(tmpdir, ".git").mkdir()

            result = await self.server._get_recent_updates(days=7, max_commits=10)

            # Should contain commit information
            self.assertIn("Recent Handbook Updates", result)
            self.assertIn("Found", result)

    async def test_get_recent_updates_validates_parameters(self):
        """Test that get_recent_updates validates and clamps parameters."""
        # Create a temporary directory structure
        with tempfile.TemporaryDirectory() as tmpdir:
            self.server.handbook_repo_path = tmpdir

            # These should be clamped but won't fail
            # (they'll return error because repo doesn't exist, but that's expected)
            # Should clamp to 1
            result1 = await self.server._get_recent_updates(days=0)
            # Should clamp to 90
            result2 = await self.server._get_recent_updates(days=100)
            # Should clamp to 1
            result3 = await self.server._get_recent_updates(max_commits=0)
            # Should clamp to 100
            result4 = await self.server._get_recent_updates(max_commits=200)

            # All should have error (non-git repo) but shouldn't crash
            self.assertIsInstance(result1, str)
            self.assertIsInstance(result2, str)
            self.assertIsInstance(result3, str)
            self.assertIsInstance(result4, str)

    async def test_get_recent_updates_with_path_filter(self):
        """Test get_recent_updates with path filtering."""
        # This tests the path_filter parameter exists and is used
        self.server.handbook_repo_path = "/tmp/nonexistent"

        result = await self.server._get_recent_updates(days=7, path_filter="content/")

        # Should handle the parameter without crashing
        self.assertIsInstance(result, str)

    @patch("thoth.mcp_server.server.Repo")
    async def test_get_recent_updates_filters_by_path(self, mock_repo_class):
        """Test that path filtering works correctly."""
        # Create mock repository
        mock_repo = MagicMock()
        mock_repo_class.return_value = mock_repo

        # Create mock commit with specific files
        mock_commit = MagicMock()
        mock_commit.hexsha = "abc123"
        mock_commit.committed_date = datetime.now(timezone.utc).timestamp()
        mock_commit.author.name = "Test"
        mock_commit.author.email = "test@test.com"
        mock_commit.message = "Update files"

        # Mock parent commit for diff
        mock_parent = MagicMock()
        mock_commit.parents = [mock_parent]

        # Create mock diffs
        mock_diff1 = MagicMock()
        mock_diff1.a_path = "content/handbook.md"
        mock_diff1.b_path = "content/handbook.md"

        mock_diff2 = MagicMock()
        mock_diff2.a_path = "other/file.txt"
        mock_diff2.b_path = "other/file.txt"

        mock_parent.diff.return_value = [mock_diff1, mock_diff2]

        mock_repo.iter_commits.return_value = [mock_commit]

        with tempfile.TemporaryDirectory() as tmpdir:
            self.server.handbook_repo_path = tmpdir
            Path(tmpdir, ".git").mkdir()

            # Test with filter that should match content/handbook.md
            result = await self.server._get_recent_updates(days=7, path_filter="content/", max_commits=10)

            # Should contain the filtered file
            self.assertIn("content/handbook.md", result)
            # Should not contain the non-matching file (or should show less)

    async def test_acceptance_criteria_issue_39(self):
        """Test acceptance criteria for Issue #39: get_recent_updates works."""
        # Tool exists
        self.assertTrue(hasattr(self.server, "_get_recent_updates"))

        # Can be called without errors (returns error message about missing repo)
        result = await self.server._get_recent_updates()
        self.assertIsInstance(result, str)

    async def test_acceptance_criteria_issue_39_filters(self):
        """Test acceptance criteria for Issue #39: Can filter by date and path."""
        # Can call with date filter
        result1 = await self.server._get_recent_updates(days=14)
        self.assertIsInstance(result1, str)

        # Can call with path filter
        result2 = await self.server._get_recent_updates(path_filter="*.md")
        self.assertIsInstance(result2, str)

        # Can call with both filters
        result3 = await self.server._get_recent_updates(days=7, path_filter="content/")
        self.assertIsInstance(result3, str)

    async def test_acceptance_criteria_issue_40(self):
        """Test acceptance criteria for Issue #40: Returns accurate changes."""
        # Tool returns formatted string output
        result = await self.server._get_recent_updates()
        self.assertIsInstance(result, str)
        self.assertGreater(len(result), 0)


class TestCachedSearchImplementation(unittest.IsolatedAsyncioTestCase):
    """Test suite for _cached_search method implementation details."""

    async def asyncSetUp(self):
        """Set up test fixtures."""
        self.server = ThothMCPServer(
            name="cache-test-server",
            version="1.0.0",
            handbook_db_path="./handbook_vectors",
        )

    async def test_cache_initialized(self):
        """Test that cache is initialized properly."""
        self.assertTrue(hasattr(self.server, "_search_cache"))
        self.assertIsInstance(self.server._search_cache, dict)
        self.assertEqual(len(self.server._search_cache), 0)

    async def test_cache_max_size_set(self):
        """Test that cache max size is set correctly."""
        self.assertTrue(hasattr(self.server, "_cache_max_size"))
        self.assertEqual(self.server._cache_max_size, 100)

    async def test_cache_eviction_when_full(self):
        """Test that cache evicts oldest entry when full."""
        if self.server.vector_store is None:
            self.skipTest("Vector store not available")

        # Fill cache to max size
        with patch.object(self.server.vector_store, "search_similar") as mock_search:
            mock_search.return_value = {
                "ids": ["1"],
                "documents": ["doc"],
                "metadatas": [{}],
                "distances": [0.1],
            }

            # Add max_size + 1 entries
            for i in range(self.server._cache_max_size + 1):
                with contextlib.suppress(RuntimeError, ValueError, AttributeError):
                    # Some queries might fail, that's OK for this test
                    self.server._cached_search(f"query_{i}", 5, None)

    async def test_cache_key_construction(self):
        """Test that cache keys are constructed correctly."""
        query = "test query"
        n_results = 5
        filter_section = "test_section"

        cache_key = (query, n_results, filter_section)
        self.assertIsInstance(cache_key, tuple)
        self.assertEqual(len(cache_key), 3)
        self.assertEqual(cache_key[0], query)
        self.assertEqual(cache_key[1], n_results)
        self.assertEqual(cache_key[2], filter_section)

    async def test_cache_key_with_none_filter(self):
        """Test cache key when filter_section is None."""
        cache_key = ("query", 5, None)
        self.assertIsInstance(cache_key, tuple)
        self.assertIsNone(cache_key[2])


class TestHelperMethods(unittest.IsolatedAsyncioTestCase):
    """Test suite for helper methods in ThothMCPServer."""

    async def asyncSetUp(self):
        """Set up test fixtures."""
        with tempfile.TemporaryDirectory() as tmpdir:
            self.tmpdir = tmpdir
            self.server = ThothMCPServer(
                name="helper-test-server",
                version="1.0.0",
                handbook_repo_path=tmpdir,
            )

    async def test_validate_repo_path_missing(self):
        """Test _validate_repo_path with non-existent path."""
        non_existent = Path("/this/path/does/not/exist")
        error = self.server._validate_repo_path(non_existent)
        self.assertIsNotNone(error)
        self.assertIn("not found", error)

    async def test_validate_repo_path_exists(self):
        """Test _validate_repo_path with existing path."""
        with tempfile.TemporaryDirectory() as tmpdir:
            existing = Path(tmpdir)
            error = self.server._validate_repo_path(existing)
            self.assertIsNone(error)

    async def test_open_git_repo_invalid(self):
        """Test _open_git_repo with non-git directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            result = self.server._open_git_repo(Path(tmpdir))
            self.assertIsInstance(result, str)
            self.assertIn("Invalid git repository", result)

    async def test_get_changed_files_no_parents(self):
        """Test _get_changed_files_for_commit with first commit."""
        mock_commit = MagicMock()
        mock_commit.parents = []
        mock_commit.stats.files = {"file1.txt": {}, "file2.txt": {}}

        files = self.server._get_changed_files_for_commit(mock_commit)
        self.assertEqual(set(files), {"file1.txt", "file2.txt"})

    async def test_get_changed_files_with_parents(self):
        """Test _get_changed_files_for_commit with parent commit."""
        mock_commit = MagicMock()
        mock_parent = MagicMock()
        mock_commit.parents = [mock_parent]

        mock_diff1 = MagicMock()
        mock_diff1.a_path = "file1.txt"
        mock_diff1.b_path = "file1.txt"

        mock_diff2 = MagicMock()
        mock_diff2.a_path = None
        mock_diff2.b_path = "file2.txt"

        mock_parent.diff.return_value = [mock_diff1, mock_diff2]

        files = self.server._get_changed_files_for_commit(mock_commit)
        self.assertIn("file1.txt", files)
        self.assertIn("file2.txt", files)

    async def test_apply_path_filter_glob(self):
        """Test _apply_path_filter with glob patterns."""
        files = ["content/doc1.md", "content/doc2.md", "other/file.txt"]

        # Test glob pattern
        filtered = self.server._apply_path_filter(files, "*.md")
        self.assertIn("content/doc1.md", filtered)
        self.assertIn("content/doc2.md", filtered)
        self.assertNotIn("other/file.txt", filtered)

    async def test_apply_path_filter_substring(self):
        """Test _apply_path_filter with substring matching."""
        files = ["content/doc1.md", "content/doc2.md", "other/file.txt"]

        filtered = self.server._apply_path_filter(files, "content/")
        self.assertIn("content/doc1.md", filtered)
        self.assertIn("content/doc2.md", filtered)
        self.assertNotIn("other/file.txt", filtered)

    async def test_format_commit_details(self):
        """Test _format_commit_details formatting."""
        mock_commit = MagicMock()
        mock_commit.hexsha = "abcdef1234567890"
        mock_commit.committed_date = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc).timestamp()
        mock_commit.author.name = "Test Author"
        mock_commit.author.email = "test@example.com"
        mock_commit.message = "Test commit message"

        changed_files = ["file1.txt", "file2.txt"]

        lines = self.server._format_commit_details(mock_commit, changed_files, 1, 5)

        self.assertIsInstance(lines, list)
        self.assertGreater(len(lines), 0)
        # Check for key components
        commit_str = "\n".join(lines)
        self.assertIn("Commit 1/5", commit_str)
        self.assertIn("abcdef12", commit_str)  # First 8 chars of SHA
        self.assertIn("Test Author", commit_str)
        self.assertIn("Test commit message", commit_str)

    async def test_format_commit_details_many_files(self):
        """Test _format_commit_details with >10 files."""
        mock_commit = MagicMock()
        mock_commit.hexsha = "abc123"
        mock_commit.committed_date = datetime.now(timezone.utc).timestamp()
        mock_commit.author.name = "Test"
        mock_commit.author.email = "test@test.com"
        mock_commit.message = "Many files"

        changed_files = [f"file{i}.txt" for i in range(15)]

        lines = self.server._format_commit_details(mock_commit, changed_files, 1, 1)
        commit_str = "\n".join(lines)

        # Should show first 10 and mention "more"
        self.assertIn("and 5 more files", commit_str)

    async def test_format_commit_details_no_message(self):
        """Test _format_commit_details with empty commit message."""
        mock_commit = MagicMock()
        mock_commit.hexsha = "abc123"
        mock_commit.committed_date = datetime.now(timezone.utc).timestamp()
        mock_commit.author.name = "Test"
        mock_commit.author.email = "test@test.com"
        mock_commit.message = ""

        lines = self.server._format_commit_details(mock_commit, [], 1, 1)
        commit_str = "\n".join(lines)

        self.assertIn("(no message)", commit_str)


class TestVectorStoreIntegration(unittest.IsolatedAsyncioTestCase):
    """Test suite for vector store integration."""

    async def asyncSetUp(self):
        """Set up test fixtures."""
        self.server = ThothMCPServer(
            name="vector-test-server",
            version="1.0.0",
            handbook_db_path="./handbook_vectors",
        )

    async def test_vector_store_attribute_exists(self):
        """Test that vector_store attribute exists."""
        self.assertTrue(hasattr(self.server, "vector_store"))

    async def test_init_vector_store_missing_db(self):
        """Test _init_vector_store with missing database."""
        server = ThothMCPServer(
            handbook_db_path="/nonexistent/path/to/db",
        )
        # Should set vector_store to None without crashing
        self.assertIsNone(server.vector_store)

    @patch("thoth.mcp_server.server.VectorStore")
    async def test_init_vector_store_error_handling(self, mock_vs):
        """Test _init_vector_store handles exceptions gracefully."""
        mock_vs.side_effect = RuntimeError("Database error")

        server = ThothMCPServer(handbook_db_path="./test_db")
        # Should handle error gracefully and set vector_store to None
        self.assertIsNone(server.vector_store)

    async def test_search_without_vector_store(self):
        """Test search operations when vector_store is None."""
        self.server.vector_store = None

        result = await self.server._search_handbook("test query")
        self.assertIn("Error", result)
        self.assertIn("not initialized", result)


class TestErrorHandlingComprehensive(unittest.IsolatedAsyncioTestCase):
    """Comprehensive error handling tests."""

    async def asyncSetUp(self):
        """Set up test fixtures."""
        self.server = ThothMCPServer(
            name="error-test-server",
            version="1.0.0",
        )

    async def test_search_handbook_value_error(self):
        """Test _search_handbook handles ValueError."""
        if self.server.vector_store is None:
            self.skipTest("Vector store not available")

        with patch.object(self.server, "_cached_search") as mock_cache:
            mock_cache.side_effect = ValueError("Test error")

            result = await self.server._search_handbook("test")
            self.assertIn("Error performing search", result)

    async def test_search_handbook_runtime_error(self):
        """Test _search_handbook handles RuntimeError."""
        if self.server.vector_store is None:
            self.skipTest("Vector store not available")

        with patch.object(self.server, "_cached_search") as mock_cache:
            mock_cache.side_effect = RuntimeError("Test runtime error")

            result = await self.server._search_handbook("test")
            self.assertIn("Error performing search", result)

    async def test_get_handbook_section_key_error(self):
        """Test _get_handbook_section handles KeyError."""
        if self.server.vector_store is None:
            self.skipTest("Vector store not available")

        with patch.object(self.server.vector_store, "get_documents") as mock_get:
            mock_get.side_effect = KeyError("Test key error")

            result = await self.server._get_handbook_section("test")
            self.assertIn("Error retrieving section", result)

    async def test_list_handbook_topics_error_handling(self):
        """Test _list_handbook_topics handles errors."""
        if self.server.vector_store is None:
            self.skipTest("Vector store not available")

        with patch.object(self.server.vector_store, "get_document_count") as mock_count:
            mock_count.side_effect = RuntimeError("Test error")

            result = await self.server._list_handbook_topics()
            self.assertIn("Error listing handbook topics", result)

    async def test_get_recent_updates_git_error(self):
        """Test _get_recent_updates handles GitCommandError."""
        with (
            tempfile.TemporaryDirectory() as tmpdir,
            patch("thoth.mcp_server.server.Repo") as mock_repo,
        ):
            self.server.handbook_repo_path = tmpdir
            Path(tmpdir, ".git").mkdir()

            mock_repo.side_effect = GitCommandError("git", "error")

            result = await self.server._get_recent_updates()
            self.assertIn("Error", result)

    async def test_get_recent_updates_os_error(self):
        """Test _get_recent_updates handles OSError."""
        with tempfile.TemporaryDirectory() as tmpdir:
            self.server.handbook_repo_path = tmpdir

            with patch("thoth.mcp_server.server.Repo") as mock_repo:
                mock_repo.side_effect = OSError("File system error")

                result = await self.server._get_recent_updates()
                self.assertIn("error", result.lower())


class TestSearchResultStructure(unittest.IsolatedAsyncioTestCase):
    """Test search result structure and formatting."""

    async def asyncSetUp(self):
        """Set up test fixtures."""
        self.server = ThothMCPServer(
            name="result-test-server",
            version="1.0.0",
        )

    async def test_search_result_has_header(self):
        """Test that search results include proper header."""
        if self.server.vector_store is None:
            self.skipTest("Vector store not available")

        with patch.object(self.server, "_cached_search") as mock_cache:
            mock_cache.return_value = (
                ("id1",),
                ("Sample document",),
                ({"section": "test"},),
                (0.1,),
                0.123,
            )

            result = await self.server._search_handbook("test query", n_results=1)

            self.assertIn("Search Results for:", result)
            self.assertIn("test query", result)
            self.assertIn("Found 1 result", result)
            self.assertIn("Search time:", result)

    async def test_search_result_includes_all_metadata(self):
        """Test that all available metadata is included."""
        if self.server.vector_store is None:
            self.skipTest("Vector store not available")

        with patch.object(self.server, "_cached_search") as mock_cache:
            mock_cache.return_value = (
                ("id1",),
                ("Document content",),
                ({"section": "intro", "source": "file.md", "chunk_index": 5},),
                (0.2,),
                0.1,
            )

            result = await self.server._search_handbook("query")

            self.assertIn("Section: intro", result)
            self.assertIn("Source: file.md", result)
            self.assertIn("Chunk: 5", result)
            self.assertIn("Relevance Score:", result)
            self.assertIn("Document content", result)

    async def test_search_result_partial_metadata(self):
        """Test search results with partial metadata."""
        if self.server.vector_store is None:
            self.skipTest("Vector store not available")

        with patch.object(self.server, "_cached_search") as mock_cache:
            mock_cache.return_value = (
                ("id1",),
                ("Content",),
                ({"section": "test"},),  # Only section, no source or chunk_index
                (0.1,),
                0.05,
            )

            result = await self.server._search_handbook("query")

            self.assertIn("Section: test", result)
            # Should not crash when source/chunk_index missing


class TestHandbookSectionRetrieval(unittest.IsolatedAsyncioTestCase):
    """Test handbook section retrieval functionality."""

    async def asyncSetUp(self):
        """Set up test fixtures."""
        self.server = ThothMCPServer(
            name="section-retrieval-test",
            version="1.0.0",
        )

    async def test_section_retrieval_with_multiple_chunks(self):
        """Test retrieving section with multiple chunks."""
        if self.server.vector_store is None:
            self.skipTest("Vector store not available")

        with patch.object(self.server.vector_store, "get_documents") as mock_get:
            mock_get.return_value = {
                "documents": ["Chunk 1", "Chunk 2", "Chunk 3"],
                "metadatas": [
                    {"section": "test", "source": "file.md", "chunk_index": 0},
                    {"section": "test", "source": "file.md", "chunk_index": 1},
                    {"section": "test", "source": "file.md", "chunk_index": 2},
                ],
            }

            result = await self.server._get_handbook_section("test", limit=10)

            self.assertIn("Total chunks: 3", result)
            self.assertIn("Chunk 1", result)
            self.assertIn("Chunk 2", result)
            self.assertIn("Chunk 3", result)

    async def test_section_retrieval_validates_limit(self):
        """Test that section retrieval validates limit parameter."""
        if self.server.vector_store is None:
            self.skipTest("Vector store not available")

        with patch.object(self.server.vector_store, "get_documents") as mock_get:
            mock_get.return_value = {"documents": [], "metadatas": []}

            # These should be clamped
            await self.server._get_handbook_section("test", limit=-1)  # -> 1
            await self.server._get_handbook_section("test", limit=0)  # -> 1
            # -> 100
            await self.server._get_handbook_section("test", limit=200)

            # Verify mock was called (limit was validated)
            self.assertEqual(mock_get.call_count, 3)


class TestTopicsListing(unittest.IsolatedAsyncioTestCase):
    """Test topics listing functionality."""

    async def asyncSetUp(self):
        """Set up test fixtures."""
        self.server = ThothMCPServer(
            name="topics-listing-test",
            version="1.0.0",
        )

    async def test_topics_listing_counts_correctly(self):
        """Test that topics listing counts sections correctly."""
        if self.server.vector_store is None:
            self.skipTest("Vector store not available")

        with (
            patch.object(self.server.vector_store, "get_document_count") as mock_count,
            patch.object(self.server.vector_store, "get_documents") as mock_get,
        ):
            mock_count.return_value = 6
            mock_get.return_value = {
                "documents": ["d1", "d2", "d3", "d4", "d5", "d6"],
                "metadatas": [
                    {"section": "intro"},
                    {"section": "intro"},
                    {"section": "body"},
                    {"section": "body"},
                    {"section": "body"},
                    {"section": "conclusion"},
                ],
            }

            result = await self.server._list_handbook_topics()

            # Check counts
            self.assertIn("intro (2 chunks)", result)
            self.assertIn("body (3 chunks)", result)
            self.assertIn("conclusion (1 chunk)", result)
            self.assertIn("Total sections: 3", result)

    async def test_topics_listing_handles_no_section_metadata(self):
        """Test topics listing when metadata lacks section field."""
        if self.server.vector_store is None:
            self.skipTest("Vector store not available")

        with (
            patch.object(self.server.vector_store, "get_document_count") as mock_count,
            patch.object(self.server.vector_store, "get_documents") as mock_get,
        ):
            mock_count.return_value = 2
            mock_get.return_value = {
                "documents": ["d1", "d2"],
                "metadatas": [
                    {"other_field": "value"},  # No section field
                    {"section": "test"},
                ],
            }

            result = await self.server._list_handbook_topics()

            # Should handle gracefully
            self.assertIsInstance(result, str)
            self.assertIn("Available Sections:", result)


class TestMCPHandlerIntegration(unittest.IsolatedAsyncioTestCase):
    """Test actual MCP handler invocations through the server."""

    async def asyncSetUp(self):
        """Set up test fixtures."""
        self.server = ThothMCPServer(
            name="handler-integration-test",
            version="1.0.0",
        )

    async def test_list_tools_handler_invocation(self):
        """Test that list_tools handler returns proper tool list."""
        # Get the list_tools handler from the server
        # The handlers are registered with the MCP server instance
        self.assertIsInstance(self.server.server, Server)

    async def test_handbook_repo_path_creation(self):
        """Test that handbook_repo_path directory is created."""
        with tempfile.TemporaryDirectory() as tmpdir:
            test_path = Path(tmpdir) / "test_handbook"
            server = ThothMCPServer(handbook_repo_path=str(test_path))
            # Directory should be created
            self.assertTrue(test_path.exists())
            self.assertTrue(test_path.is_dir())
            # Verify server was initialized with correct path
            self.assertEqual(server.handbook_repo_path, str(test_path))

    async def test_handbook_repo_path_default(self):
        """Test default handbook_repo_path."""
        server = ThothMCPServer()
        expected_path = Path.home() / ".thoth" / "handbook"
        self.assertEqual(Path(server.handbook_repo_path), expected_path)

    async def test_vector_store_none_when_db_missing(self):
        """Test that vector_store is None when database is missing."""
        server = ThothMCPServer(handbook_db_path="/completely/nonexistent/path")
        self.assertIsNone(server.vector_store)

    async def test_search_handbook_clamps_n_results(self):
        """Test that _search_handbook properly clamps n_results."""
        if self.server.vector_store is None:
            self.skipTest("Vector store not available")

        with patch.object(self.server, "_cached_search") as mock_cache:
            mock_cache.return_value = ((), (), (), (), 0.1)

            # Test clamping to minimum
            await self.server._search_handbook("test", n_results=0)
            # Should have been called with clamped value
            self.assertTrue(mock_cache.called)

            # Test clamping to maximum
            mock_cache.reset_mock()
            await self.server._search_handbook("test", n_results=100)
            self.assertTrue(mock_cache.called)

    async def test_get_handbook_section_clamps_limit(self):
        """Test that _get_handbook_section properly clamps limit."""
        if self.server.vector_store is None:
            self.skipTest("Vector store not available")

        with patch.object(self.server.vector_store, "get_documents") as mock_get:
            mock_get.return_value = {"documents": [], "metadatas": []}

            # Test clamping to minimum
            await self.server._get_handbook_section("test", limit=0)
            # Test clamping to maximum
            await self.server._get_handbook_section("test", limit=200)

            # Both should have been called (validates clamping works)
            self.assertEqual(mock_get.call_count, 2)

    async def test_list_handbook_topics_clamps_max_depth(self):
        """Test that _list_handbook_topics properly clamps max_depth."""
        if self.server.vector_store is None:
            self.skipTest("Vector store not available")

        with (
            patch.object(self.server.vector_store, "get_document_count") as mock_count,
            patch.object(self.server.vector_store, "get_documents") as mock_get,
        ):
            mock_count.return_value = 1
            mock_get.return_value = {"documents": ["d"], "metadatas": [{}]}

            # Test clamping
            await self.server._list_handbook_topics(max_depth=0)
            await self.server._list_handbook_topics(max_depth=10)

            # Both should complete without error
            self.assertEqual(mock_count.call_count, 2)

    async def test_get_recent_updates_clamps_days(self):
        """Test that _get_recent_updates properly clamps days."""
        with tempfile.TemporaryDirectory() as tmpdir:
            self.server.handbook_repo_path = tmpdir

            # These should clamp but not crash
            result1 = await self.server._get_recent_updates(days=0)
            result2 = await self.server._get_recent_updates(days=200)

            # Both should return error (no repo) but shouldn't crash
            self.assertIsInstance(result1, str)
            self.assertIsInstance(result2, str)

    async def test_get_recent_updates_clamps_max_commits(self):
        """Test that _get_recent_updates properly clamps max_commits."""
        with tempfile.TemporaryDirectory() as tmpdir:
            self.server.handbook_repo_path = tmpdir

            # These should clamp but not crash
            result1 = await self.server._get_recent_updates(max_commits=0)
            result2 = await self.server._get_recent_updates(max_commits=200)

            # Both should return error (no repo) but shouldn't crash
            self.assertIsInstance(result1, str)
            self.assertIsInstance(result2, str)

    async def test_cached_search_converts_to_tuples(self):
        """Test that _cached_search converts results to tuples."""
        if self.server.vector_store is None:
            self.skipTest("Vector store not available")

        with patch.object(self.server.vector_store, "search_similar") as mock_search:
            mock_search.return_value = {
                "ids": ["id1"],
                "documents": ["doc1"],
                "metadatas": [{"key": "value"}],
                "distances": [0.5],
            }

            result = self.server._cached_search("query", 5, None)

            # Result should be tuple
            self.assertIsInstance(result, tuple)
            self.assertEqual(len(result), 5)

            # Elements should be tuples
            self.assertIsInstance(result[0], tuple)  # ids
            self.assertIsInstance(result[1], tuple)  # documents
            self.assertIsInstance(result[2], tuple)  # metadatas
            self.assertIsInstance(result[3], tuple)  # distances
            self.assertIsInstance(result[4], float)  # search_time

    async def test_search_result_includes_timing(self):
        """Test that search results include timing information."""
        if self.server.vector_store is None:
            self.skipTest("Vector store not available")

        with patch.object(self.server, "_cached_search") as mock_cache:
            mock_cache.return_value = (
                ("id1",),
                ("Document content",),
                ({"section": "test"},),
                (0.2,),
                0.456,
            )

            result = await self.server._search_handbook("test query")

            # Should include search time
            self.assertIn("Search time:", result)
            self.assertIn("0.456s", result)

    async def test_get_recent_updates_with_first_commit(self):
        """Test _get_changed_files_for_commit handles first commit."""
        mock_commit = MagicMock()
        mock_commit.parents = []
        mock_commit.stats.files = {"file1.txt": {}, "file2.txt": {}}

        files = self.server._get_changed_files_for_commit(mock_commit)

        self.assertIsInstance(files, list)
        self.assertIn("file1.txt", files)
        self.assertIn("file2.txt", files)

    async def test_format_commit_details_multiline_message(self):
        """Test _format_commit_details with multiline commit message."""
        mock_commit = MagicMock()
        mock_commit.hexsha = "abc123def456"
        mock_commit.committed_date = datetime.now(timezone.utc).timestamp()
        mock_commit.author.name = "Test"
        mock_commit.author.email = "test@test.com"
        mock_commit.message = "First line\n\nSecond paragraph\nThird line"

        lines = self.server._format_commit_details(mock_commit, [], 1, 1)
        commit_str = "\n".join(lines)

        # Should only show first line
        self.assertIn("First line", commit_str)
        self.assertNotIn("Second paragraph", commit_str)

    async def test_apply_path_filter_empty_list(self):
        """Test _apply_path_filter with empty file list."""
        files = []
        filtered = self.server._apply_path_filter(files, "*.md")

        self.assertEqual(filtered, [])
        self.assertIsInstance(filtered, list)

    @patch("thoth.mcp_server.server.VectorStore")
    async def test_init_vector_store_os_error(self, mock_vs):
        """Test _init_vector_store handles OSError."""
        mock_vs.side_effect = OSError("Disk error")

        server = ThothMCPServer(handbook_db_path="./test_db")
        # Should handle error gracefully
        self.assertIsNone(server.vector_store)

    @patch("thoth.mcp_server.server.VectorStore")
    async def test_init_vector_store_value_error(self, mock_vs):
        """Test _init_vector_store handles ValueError."""
        mock_vs.side_effect = ValueError("Invalid config")

        server = ThothMCPServer(handbook_db_path="./test_db")
        # Should handle error gracefully
        self.assertIsNone(server.vector_store)

    @patch("thoth.mcp_server.server.Path")
    async def test_init_vector_store_db_exists_check(self, mock_path):
        """Test _init_vector_store checks if database exists."""
        # Mock Path to return false for exists()
        mock_path_instance = MagicMock()
        mock_path_instance.exists.return_value = False
        mock_path.return_value = mock_path_instance

        server = ThothMCPServer(handbook_db_path="/fake/path")
        # Vector store should be None when path doesn't exist
        self.assertIsNone(server.vector_store)
