"""Thoth MCP Server - Simplified plugin-based MCP server implementation.

This module provides a simplified, plugin-based Model Context Protocol (MCP) server
that supports multiple RAG setups and tools through a plugin system.

Key Features:
    - Plugin-based architecture for tools and RAG setups
    - Support for multiple vector stores and data sources
    - MCP-compliant tool and resource interfaces
    - No dependencies on ingestion/refresh code

The server exposes tools via the MCP protocol, allowing AI assistants
like Claude to search and retrieve relevant information using natural language queries.

Example:
    To run the server:
        $ python -m thoth.mcp_server.server

    Or programmatically:
        >>> from thoth.mcp_server.server import ThothMCPServer
        >>> server = ThothMCPServer()
        >>> await server.run()
"""

import asyncio
from typing import Any

from mcp.server import Server
from mcp.server.sse import SseServerTransport
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool
from starlette.applications import Starlette
from starlette.routing import Route
from starlette.types import Receive, Scope, Send

from thoth.mcp_server.config import get_config
from thoth.mcp_server.plugins.rag.handbook import HandbookRAGPlugin
from thoth.mcp_server.plugins.rag.manager import RAGManager
from thoth.mcp_server.plugins.registry import get_registry
from thoth.mcp_server.plugins.tools.file_operations import FileOperationsPlugin
from thoth.mcp_server.plugins.tools.handbook_tools import HandbookToolsPlugin
from thoth.utils.logger import setup_logger

logger = setup_logger(__name__)


class ThothMCPServer:
    """Simplified plugin-based Thoth MCP Server.

    This server uses a plugin architecture to provide tools and RAG capabilities.
    It is completely independent of ingestion/refresh code, ensuring that failures
    in data refresh don't affect the MCP server functionality.

    Architecture:
        - Plugin System: Dynamic tool and RAG plugin loading
        - RAG Manager: Manages multiple RAG setups
        - Tool Registry: Manages tool plugins
        - Configuration: YAML/JSON-based configuration

    Attributes:
        name (str): Server identifier name
        version (str): Server version string
        server (Server): MCP Server instance
        registry (PluginRegistry): Plugin registry
        rag_manager (RAGManager): RAG plugin manager
        config (MCPConfig): Configuration manager
    """

    def __init__(
        self,
        name: str = "thoth-server",
        version: str = "1.0.0",
        config_path: str | None = None,
    ):
        """Initialize the Thoth MCP Server.

        Args:
            name: Server name identifier
            version: Server version
            config_path: Optional path to configuration file
        """
        self.name = name
        self.version = version
        self.server = Server(name)

        # Initialize configuration
        self.config = get_config()
        if config_path:
            self.config.load_from_file(config_path)

        # Initialize plugin registry and managers
        self.registry = get_registry()
        self.rag_manager = RAGManager(registry=self.registry)

        # Setup plugins
        self._setup_plugins()

        # Setup MCP handlers
        self._setup_handlers()

        logger.info("Initialized %s v%s", name, version)

    def _setup_plugins(self) -> None:
        """Set up plugins from configuration."""
        try:
            # Load RAG setups from config
            rag_setups = self.config.get_rag_setups()
            for setup_config in rag_setups:
                setup_name = setup_config.get("name", "default")
                plugin_type = setup_config.get("plugin_type", "handbook")
                plugin_config = setup_config.get("config", {})

                # Create and register RAG plugin
                if plugin_type == "handbook":
                    plugin = HandbookRAGPlugin(name=setup_name)
                    self.rag_manager.register_rag_setup(setup_name, plugin, plugin_config)

            # Register default handbook RAG if no setups configured
            if not rag_setups:
                plugin = HandbookRAGPlugin(name="handbook")
                self.rag_manager.register_rag_setup("handbook", plugin, {})

            # Register tool plugins
            file_ops_plugin = FileOperationsPlugin()
            file_ops_config = self.config.get_plugin_config("file_operations")
            file_ops_plugin.initialize(file_ops_config)
            self.registry.register_tool_plugin(file_ops_plugin)

            handbook_tools_plugin = HandbookToolsPlugin()
            handbook_tools_config = self.config.get_plugin_config("handbook_tools")
            handbook_tools_config["rag_manager"] = self.rag_manager
            handbook_tools_plugin.initialize(handbook_tools_config)
            self.registry.register_tool_plugin(handbook_tools_plugin)

            logger.info("Plugins initialized successfully")
        except Exception:
            logger.exception("Failed to setup plugins")
            # Continue without plugins - server will still work but without tools

    def _setup_handlers(self) -> None:
        """Set up MCP protocol handlers."""

        # List tools handler - MCP protocol handler for listing available tools
        @self.server.list_tools()
        async def list_tools() -> list[Tool]:
            """List all available tools from registered plugins."""
            tools: list[Tool] = []
            # Iterate through all registered tool plugins
            for plugin_name in self.registry.list_tool_plugins():
                plugin = self.registry.get_tool_plugin(plugin_name)
                if plugin:
                    try:
                        # Get tool definitions from plugin
                        plugin_tools = plugin.get_tools()
                        # Convert plugin tool format to MCP Tool format
                        tools.extend(
                            Tool(
                                name=tool_def["name"],
                                description=tool_def.get("description", ""),
                                inputSchema=tool_def.get("inputSchema", {}),
                            )
                            for tool_def in plugin_tools
                        )
                    except Exception:
                        # Log error but continue with other plugins
                        logger.exception(f"Error getting tools from plugin {plugin_name}")

            logger.debug(f"Listed {len(tools)} tools")
            return tools

        # Call tool handler - MCP protocol handler for executing tools
        @self.server.call_tool()
        async def call_tool(name: str, arguments: dict[str, Any] | None) -> list[TextContent]:
            """Execute a tool by name."""
            # Ensure arguments is a dict (MCP may pass None)
            if arguments is None:
                arguments = {}

            # Search for tool in all registered plugins
            for plugin_name in self.registry.list_tool_plugins():
                plugin = self.registry.get_tool_plugin(plugin_name)
                if plugin:
                    try:
                        # Get list of tools from this plugin
                        plugin_tools = plugin.get_tools()
                        tool_names = [t["name"] for t in plugin_tools]
                        # Check if requested tool is in this plugin
                        if name in tool_names:
                            # Execute the tool and return result as MCP TextContent
                            result = await plugin.execute_tool(name, arguments)
                            return [
                                TextContent(
                                    type="text",
                                    text=str(result),
                                )
                            ]
                    except Exception as e:
                        # Log error and return error message to client
                        logger.exception(f"Error executing tool {name} from plugin {plugin_name}")
                        return [
                            TextContent(
                                type="text",
                                text=f"Error executing tool: {e}",
                            )
                        ]

            # Tool not found in any plugin
            error_msg = f"Tool '{name}' not found"
            logger.warning(error_msg)
            return [
                TextContent(
                    type="text",
                    text=error_msg,
                )
            ]

        # List resources handler (optional)
        @self.server.list_resources()
        async def list_resources() -> list[Any]:
            """List available resources."""
            # Resources can be added later if needed
            return []

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
            """Handle SSE connection using raw ASGI interface."""
            async with sse.connect_sse(scope, receive, send) as streams:
                await self.server.run(streams[0], streams[1], self.server.create_initialization_options())

        async def handle_messages(scope: Scope, receive: Receive, send: Send) -> None:
            """Handle POST messages using raw ASGI interface."""
            await sse.handle_post_message(scope, receive, send)

        return Starlette(
            debug=True,
            routes=[
                Route("/sse", endpoint=handle_sse),
                Route("/messages", endpoint=handle_messages, methods=["POST"]),
            ],
        )

    def cleanup(self) -> None:
        """Clean up server resources."""
        self.rag_manager.cleanup()
        self.registry.cleanup_all()
        logger.info("Cleaned up server resources")


async def invoker() -> None:
    """Main entry point for the MCP server."""
    server = ThothMCPServer()
    try:
        await server.run()
    except KeyboardInterrupt:
        logger.info("Server stopped by user")
    finally:
        server.cleanup()


def run_server() -> None:
    """Run the MCP server (blocking)."""
    try:
        asyncio.run(invoker())
    except Exception:
        logger.exception("Server error")
        raise


if __name__ == "__main__":
    import asyncio

    asyncio.run(invoker())
