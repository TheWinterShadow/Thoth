"""Base classes for plugin system."""

from abc import ABC, abstractmethod
from typing import Any


class BasePlugin(ABC):
    """Base class for all plugins.

    All plugins must inherit from this class and implement the required methods.
    """

    def __init__(self, name: str, version: str = "1.0.0"):
        """Initialize plugin.

        Args:
            name: Plugin name
            version: Plugin version
        """
        self.name = name
        self.version = version

    @abstractmethod
    def initialize(self, config: dict[str, Any] | None = None) -> None:
        """Initialize the plugin with configuration.

        Args:
            config: Optional configuration dictionary
        """

    @abstractmethod
    def cleanup(self) -> None:
        """Clean up plugin resources."""


class BaseRAGPlugin(BasePlugin):
    """Base class for RAG (Retrieval Augmented Generation) plugins.

    RAG plugins provide semantic search capabilities over specific data sources.
    """

    @abstractmethod
    def search(
        self,
        query: str,
        n_results: int = 5,
        filters: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        """Perform semantic search.

        Args:
            query: Search query text
            n_results: Number of results to return
            filters: Optional metadata filters

        Returns:
            List of search results with 'text', 'metadata', 'score' keys
        """

    @abstractmethod
    def get_vector_store(self) -> Any:
        """Get the underlying vector store instance.

        Returns:
            Vector store instance
        """


class BaseToolPlugin(BasePlugin):
    """Base class for tool plugins.

    Tool plugins provide executable tools that can be called via MCP.
    """

    @abstractmethod
    def get_tools(self) -> list[dict[str, Any]]:
        """Get list of tools provided by this plugin.

        Returns:
            List of tool definitions compatible with MCP Tool type
        """

    @abstractmethod
    async def execute_tool(self, tool_name: str, arguments: dict[str, Any]) -> Any:
        """Execute a tool by name.

        Args:
            tool_name: Name of the tool to execute
            arguments: Tool arguments

        Returns:
            Tool execution result
        """
