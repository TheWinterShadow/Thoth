"""Thoth MCP Server - Main remote MCP server implementation.

This module provides the core Model Context Protocol (MCP) server
that enables remote tool and resource access.
"""

import asyncio
from typing import Any

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import (
    TextContent,
    Tool,
)

from thoth.utils.logger import setup_logger

logger = setup_logger(__name__)


class ThothMCPServer:
    """Main Thoth MCP Server implementation."""

    def __init__(self, name: str = "thoth-server", version: str = "1.0.0"):
        """Initialize the Thoth MCP Server.

        Args:
            name: Server name identifier
            version: Server version
        """
        self.name = name
        self.version = version
        self.server = Server(name)
        self._setup_handlers()
        logger.info("Initialized %s v%s", name, version)

    def _setup_handlers(self) -> None:
        """Set up MCP protocol handlers."""

        # Register list_tools handler
        @self.server.list_tools()
        async def list_tools() -> list[Tool]:
            """List available tools."""
            return [
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

        # Register call_tool handler
        @self.server.call_tool()
        async def call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
            """Execute a tool by name with given arguments.

            Args:
                name: Tool name to execute
                arguments: Tool arguments

            Returns:
                List of content results
            """
            logger.info("Calling tool: %s with arguments: %s", name, arguments)

            if name == "ping":
                message = arguments.get("message", "ping")
                result = f"pong: {message}"
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
