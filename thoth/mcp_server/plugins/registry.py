"""Plugin registry for managing and discovering plugins."""

import importlib
import logging
from typing import Any

from thoth.mcp_server.plugins.base import BasePlugin, BaseRAGPlugin, BaseToolPlugin

logger = logging.getLogger(__name__)


class PluginRegistry:
    """Registry for managing MCP server plugins."""

    def __init__(self) -> None:
        """Initialize plugin registry."""
        self._rag_plugins: dict[str, BaseRAGPlugin] = {}
        self._tool_plugins: dict[str, BaseToolPlugin] = {}
        self._all_plugins: dict[str, BasePlugin] = {}

    def register_rag_plugin(self, plugin: BaseRAGPlugin) -> None:
        """Register a RAG plugin.

        Args:
            plugin: RAG plugin instance
        """
        if plugin.name in self._rag_plugins:
            logger.warning(f"RAG plugin '{plugin.name}' already registered, overwriting")
        self._rag_plugins[plugin.name] = plugin
        self._all_plugins[plugin.name] = plugin
        logger.info(f"Registered RAG plugin: {plugin.name} v{plugin.version}")

    def register_tool_plugin(self, plugin: BaseToolPlugin) -> None:
        """Register a tool plugin.

        Args:
            plugin: Tool plugin instance
        """
        if plugin.name in self._tool_plugins:
            logger.warning(f"Tool plugin '{plugin.name}' already registered, overwriting")
        self._tool_plugins[plugin.name] = plugin
        self._all_plugins[plugin.name] = plugin
        logger.info(f"Registered tool plugin: {plugin.name} v{plugin.version}")

    def get_rag_plugin(self, name: str) -> BaseRAGPlugin | None:
        """Get a RAG plugin by name.

        Args:
            name: Plugin name

        Returns:
            RAG plugin instance or None if not found
        """
        return self._rag_plugins.get(name)

    def get_tool_plugin(self, name: str) -> BaseToolPlugin | None:
        """Get a tool plugin by name.

        Args:
            name: Plugin name

        Returns:
            Tool plugin instance or None if not found
        """
        return self._tool_plugins.get(name)

    def list_rag_plugins(self) -> list[str]:
        """List all registered RAG plugin names.

        Returns:
            List of plugin names
        """
        return list(self._rag_plugins.keys())

    def list_tool_plugins(self) -> list[str]:
        """List all registered tool plugin names.

        Returns:
            List of plugin names
        """
        return list(self._tool_plugins.keys())

    def load_plugin_from_module(
        self,
        module_path: str,
        plugin_class: str,
        config: dict[str, Any] | None = None,
    ) -> BasePlugin:
        """Load a plugin from a Python module.

        Args:
            module_path: Full module path (e.g., 'thoth.mcp_server.plugins.rag.handbook')
            plugin_class: Class name of the plugin
            config: Optional configuration for the plugin

        Returns:
            Plugin instance

        Raises:
            ImportError: If module or class cannot be loaded
        """
        try:
            module = importlib.import_module(module_path)
            plugin_cls = getattr(module, plugin_class)
            plugin: BasePlugin = plugin_cls()
            plugin.initialize(config or {})
            return plugin
        except (ImportError, AttributeError):
            logger.exception(f"Failed to load plugin from {module_path}.{plugin_class}")
            raise

    def cleanup_all(self) -> None:
        """Clean up all registered plugins."""
        for plugin in self._all_plugins.values():
            try:
                plugin.cleanup()
            except Exception:
                logger.exception(f"Error cleaning up plugin {plugin.name}")


# Global registry instance
_registry: PluginRegistry | None = None


def get_registry() -> PluginRegistry:
    """Get or create the global plugin registry.

    Returns:
        PluginRegistry instance
    """
    global _registry  # noqa: PLW0603
    if _registry is None:
        _registry = PluginRegistry()
    return _registry
