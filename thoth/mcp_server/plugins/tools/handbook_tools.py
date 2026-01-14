"""Handbook tools plugin for MCP server."""

import logging
from typing import Any

from thoth.mcp_server.plugins.base import BaseToolPlugin
from thoth.mcp_server.plugins.rag.manager import RAGManager

logger = logging.getLogger(__name__)


class HandbookToolsPlugin(BaseToolPlugin):
    """Plugin providing handbook search tools."""

    def __init__(self, name: str = "handbook_tools", version: str = "1.0.0"):
        """Initialize handbook tools plugin.

        Args:
            name: Plugin name
            version: Plugin version
        """
        super().__init__(name, version)
        self.rag_manager: RAGManager | None = None
        self.default_rag_setup: str = "handbook"

    def initialize(self, config: dict[str, Any] | None = None) -> None:
        """Initialize the handbook tools plugin.

        Args:
            config: Configuration dictionary with:
                - rag_manager: RAGManager instance (optional, creates new one if not provided)
                - default_rag_setup: Default RAG setup name (default: "handbook")
        """
        if config:
            self.rag_manager = config.get("rag_manager")
            self.default_rag_setup = config.get("default_rag_setup", "handbook")

        if not self.rag_manager:
            self.rag_manager = RAGManager()

    def cleanup(self) -> None:
        """Clean up plugin resources."""
        self.rag_manager = None

    def get_tools(self) -> list[dict[str, Any]]:
        """Get list of handbook tools.

        Returns:
            List of tool definitions compatible with MCP Tool type
        """
        return [
            {
                "name": "search_handbook",
                "description": "Search the handbook using semantic similarity",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "Search query text",
                        },
                        "n_results": {
                            "type": "integer",
                            "description": "Number of results to return",
                            "default": 5,
                        },
                        "rag_setup": {
                            "type": "string",
                            "description": "RAG setup name to use (optional)",
                        },
                    },
                    "required": ["query"],
                },
            },
            {
                "name": "get_handbook_section",
                "description": "Get a specific section from the handbook",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "section_path": {
                            "type": "string",
                            "description": "Path to the handbook section",
                        },
                        "rag_setup": {
                            "type": "string",
                            "description": "RAG setup name to use (optional)",
                        },
                    },
                    "required": ["section_path"],
                },
            },
        ]

    async def execute_tool(self, tool_name: str, arguments: dict[str, Any]) -> Any:
        """Execute a handbook tool.

        Args:
            tool_name: Name of the tool to execute
            arguments: Tool arguments

        Returns:
            Tool execution result

        Raises:
            ValueError: If tool name is invalid or RAG manager not initialized
        """
        if not self.rag_manager:
            msg = "RAG manager not initialized"
            raise ValueError(msg)

        if tool_name == "search_handbook":
            return await self._search_handbook(
                query=arguments["query"],
                n_results=arguments.get("n_results", 5),
                rag_setup=arguments.get("rag_setup", self.default_rag_setup),
            )

        if tool_name == "get_handbook_section":
            return await self._get_handbook_section(
                section_path=arguments["section_path"],
                rag_setup=arguments.get("rag_setup", self.default_rag_setup),
            )

        msg = f"Unknown tool: {tool_name}"
        raise ValueError(msg)

    async def _search_handbook(
        self,
        query: str,
        n_results: int = 5,
        rag_setup: str = "handbook",
    ) -> dict[str, Any]:
        """Search the handbook.

        Args:
            query: Search query
            n_results: Number of results
            rag_setup: RAG setup name

        Returns:
            Search results
        """
        if not self.rag_manager:
            msg = "RAG manager not initialized"
            raise ValueError(msg)
        try:
            results = self.rag_manager.search(
                rag_setup_name=rag_setup,
                query=query,
                n_results=n_results,
            )

            return {
                "query": query,
                "results": results,
                "count": len(results),
                "rag_setup": rag_setup,
            }
        except Exception:
            logger.exception("Handbook search failed")
            raise

    async def _get_handbook_section(
        self,
        section_path: str,
        rag_setup: str = "handbook",
    ) -> dict[str, Any]:
        """Get a specific handbook section.

        Args:
            section_path: Path to the section
            rag_setup: RAG setup name

        Returns:
            Section content
        """
        if not self.rag_manager:
            msg = "RAG manager not initialized"
            raise ValueError(msg)
        try:
            # Search for the section by path
            results = self.rag_manager.search(
                rag_setup_name=rag_setup,
                query=section_path,
                n_results=1,
                filters={"file_path": section_path},
            )

            if results:
                return {
                    "section_path": section_path,
                    "content": results[0]["text"],
                    "metadata": results[0]["metadata"],
                    "rag_setup": rag_setup,
                }
            return {
                "section_path": section_path,
                "content": None,
                "error": "Section not found",
                "rag_setup": rag_setup,
            }
        except Exception:
            logger.exception("Failed to get handbook section")
            raise
