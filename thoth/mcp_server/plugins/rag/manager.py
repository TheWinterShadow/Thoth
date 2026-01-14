"""RAG plugin manager for managing multiple RAG setups."""

import logging
from typing import Any

from thoth.mcp_server.plugins.base import BaseRAGPlugin
from thoth.mcp_server.plugins.registry import PluginRegistry, get_registry

logger = logging.getLogger(__name__)


class RAGManager:
    """Manager for multiple RAG plugin instances."""

    def __init__(self, registry: PluginRegistry | None = None):
        """Initialize RAG manager.

        Args:
            registry: Optional plugin registry (creates new one if not provided)
        """
        self.registry = registry or get_registry()
        self._active_rag_plugins: dict[str, BaseRAGPlugin] = {}

    def register_rag_setup(
        self,
        name: str,
        plugin: BaseRAGPlugin,
        config: dict[str, Any] | None = None,
    ) -> None:
        """Register a RAG setup.

        Args:
            name: Name of the RAG setup
            plugin: RAG plugin instance
            config: Optional configuration for the plugin
        """
        # Initialize plugin with config
        plugin.initialize(config)

        # Register in registry
        self.registry.register_rag_plugin(plugin)

        # Store as active
        self._active_rag_plugins[name] = plugin

        logger.info(f"Registered RAG setup: {name}")

    def get_rag_setup(self, name: str) -> BaseRAGPlugin | None:
        """Get a RAG setup by name.

        Args:
            name: Name of the RAG setup

        Returns:
            RAG plugin instance or None if not found
        """
        return self._active_rag_plugins.get(name)

    def list_rag_setups(self) -> list[str]:
        """List all registered RAG setup names.

        Returns:
            List of RAG setup names
        """
        return list(self._active_rag_plugins.keys())

    def search(
        self,
        rag_setup_name: str,
        query: str,
        n_results: int = 5,
        filters: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        """Perform search using a specific RAG setup.

        Args:
            rag_setup_name: Name of the RAG setup to use
            query: Search query text
            n_results: Number of results to return
            filters: Optional metadata filters

        Returns:
            List of search results

        Raises:
            ValueError: If RAG setup not found
        """
        plugin = self.get_rag_setup(rag_setup_name)
        if not plugin:
            msg = f"RAG setup '{rag_setup_name}' not found"
            raise ValueError(msg)

        return plugin.search(query=query, n_results=n_results, filters=filters)

    def cleanup(self) -> None:
        """Clean up all RAG plugins."""
        for plugin in self._active_rag_plugins.values():
            try:
                plugin.cleanup()
            except Exception:
                logger.exception("Error cleaning up RAG plugin")

        self._active_rag_plugins.clear()
