"""Tests for plugin system."""

import pytest

from thoth.mcp_server.plugins.rag.handbook import HandbookRAGPlugin
from thoth.mcp_server.plugins.registry import PluginRegistry
from thoth.mcp_server.plugins.tools.file_operations import FileOperationsPlugin


def test_plugin_registry():
    """Test plugin registry."""
    registry = PluginRegistry()

    # Register RAG plugin
    rag_plugin = HandbookRAGPlugin()
    registry.register_rag_plugin(rag_plugin)
    assert "handbook" in registry.list_rag_plugins()

    # Register tool plugin
    tool_plugin = FileOperationsPlugin()
    registry.register_tool_plugin(tool_plugin)
    assert "file_operations" in registry.list_tool_plugins()


def test_rag_plugin_search(tmp_path):
    """Test RAG plugin search."""
    plugin = HandbookRAGPlugin()
    plugin.initialize(
        {
            "persist_directory": str(tmp_path / "chroma_db"),
            "collection_name": "test",
        }
    )

    # Add test documents
    vector_store = plugin.get_vector_store()
    vector_store.add_documents(["Test document"], ids=["doc1"])

    # Search
    results = plugin.search("Test", n_results=1)
    assert len(results) > 0
    assert results[0]["text"] == "Test document"

    plugin.cleanup()


def test_tool_plugin_get_tools():
    """Test tool plugin get_tools."""
    plugin = FileOperationsPlugin()
    tools = plugin.get_tools()

    assert len(tools) > 0
    tool_names = [t["name"] for t in tools]
    assert "read_file" in tool_names
    assert "write_file" in tool_names


@pytest.mark.asyncio
async def test_tool_plugin_execute_tool(tmp_path):
    """Test tool plugin execute_tool."""
    plugin = FileOperationsPlugin()
    plugin.initialize({"base_path": str(tmp_path)})

    # Write file
    result = await plugin.execute_tool(
        "write_file",
        {
            "path": "test.txt",
            "content": "test content",
        },
    )
    assert result["status"] == "written"

    # Read file
    result = await plugin.execute_tool("read_file", {"path": "test.txt"})
    assert result["content"] == "test content"

    plugin.cleanup()
