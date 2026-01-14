"""Plugin system for MCP server.

This module provides the plugin architecture for extending the MCP server
with custom tools, RAG setups, and data sources.
"""

from thoth.mcp_server.plugins.base import BasePlugin, BaseRAGPlugin, BaseToolPlugin
from thoth.mcp_server.plugins.registry import PluginRegistry

__all__ = [
    "BasePlugin",
    "BaseRAGPlugin",
    "BaseToolPlugin",
    "PluginRegistry",
]
