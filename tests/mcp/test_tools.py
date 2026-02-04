"""Unit tests for Thoth MCP Tools."""

import unittest
from unittest.mock import MagicMock, patch

import thoth.mcp.tools as tools_module
from thoth.mcp.tools import list_tools, list_topics, mcp, search_handbook


class TestListTools(unittest.TestCase):
    """Test suite for list_tools function."""

    def test_list_tools_returns_string(self):
        """Test that list_tools returns a string."""
        result = list_tools()
        self.assertIsInstance(result, str)

    def test_list_tools_contains_all_tools(self):
        """Test that list_tools includes all available tools."""
        result = list_tools()
        self.assertIn("search_handbook", result)
        self.assertIn("list_tools", result)
        self.assertIn("list_topics", result)

    def test_list_tools_has_header(self):
        """Test that list_tools has proper header."""
        result = list_tools()
        self.assertIn("Available MCP Tools", result)


class TestListTopics(unittest.TestCase):
    """Test suite for list_topics function."""

    @patch("thoth.mcp.tools.get_vector_store")
    def test_list_topics_empty_collection(self, mock_get_store):
        """Test list_topics when collection is empty."""
        mock_store = MagicMock()
        mock_store.get_document_count.return_value = 0
        mock_get_store.return_value = mock_store

        result = list_topics()
        self.assertIn("empty", result.lower())

    @patch("thoth.mcp.tools.get_vector_store")
    def test_list_topics_with_documents(self, mock_get_store):
        """Test list_topics with documents."""
        mock_store = MagicMock()
        mock_store.get_document_count.return_value = 5
        mock_store.get_documents.return_value = {
            "metadatas": [
                {"section": "intro", "file_path": "doc1.md"},
                {"section": "intro", "file_path": "doc1.md"},
                {"section": "setup", "file_path": "doc2.md"},
                {"section": "setup", "file_path": "doc2.md"},
                {"section": "faq", "file_path": "doc3.md"},
            ]
        }
        mock_get_store.return_value = mock_store

        result = list_topics()

        self.assertIn("Total documents: 5", result)
        self.assertIn("intro", result)
        self.assertIn("setup", result)
        self.assertIn("faq", result)

    @patch("thoth.mcp.tools.get_vector_store")
    def test_list_topics_counts_correctly(self, mock_get_store):
        """Test that list_topics counts sections correctly."""
        mock_store = MagicMock()
        mock_store.get_document_count.return_value = 4
        mock_store.get_documents.return_value = {
            "metadatas": [
                {"section": "intro", "file_path": "a.md"},
                {"section": "intro", "file_path": "a.md"},
                {"section": "intro", "file_path": "a.md"},
                {"section": "other", "file_path": "b.md"},
            ]
        }
        mock_get_store.return_value = mock_store

        result = list_topics()

        self.assertIn("intro (3 chunks)", result)
        self.assertIn("other (1 chunk)", result)


class TestSearchHandbook(unittest.TestCase):
    """Test suite for search_handbook function."""

    @patch("thoth.mcp.tools.get_vector_store")
    def test_search_handbook_no_results(self, mock_get_store):
        """Test search_handbook when no results found."""
        mock_store = MagicMock()
        mock_store.search_similar.return_value = {
            "documents": [],
            "metadatas": [],
            "distances": [],
        }
        mock_get_store.return_value = mock_store

        result = search_handbook("nonexistent query")
        self.assertIn("No results found", result)

    @patch("thoth.mcp.tools.get_vector_store")
    def test_search_handbook_with_results(self, mock_get_store):
        """Test search_handbook with results."""
        mock_store = MagicMock()
        mock_store.search_similar.return_value = {
            "documents": ["Document content here"],
            "metadatas": [{"file_path": "test.md", "section": "intro"}],
            "distances": [0.1],
        }
        mock_get_store.return_value = mock_store

        result = search_handbook("test query")

        self.assertIn("Found 1 results", result)
        self.assertIn("Document content here", result)
        self.assertIn("test.md", result)

    @patch("thoth.mcp.tools.get_vector_store")
    def test_search_handbook_clamps_num_results(self, mock_get_store):
        """Test that num_results is clamped to valid range."""
        mock_store = MagicMock()
        mock_store.search_similar.return_value = {
            "documents": [],
            "metadatas": [],
            "distances": [],
        }
        mock_get_store.return_value = mock_store

        # Test with value below minimum
        search_handbook("test", num_results=0)
        call_args = mock_store.search_similar.call_args
        self.assertEqual(call_args.kwargs["n_results"], 1)

        # Test with value above maximum
        mock_store.search_similar.reset_mock()
        search_handbook("test", num_results=100)
        call_args = mock_store.search_similar.call_args
        self.assertEqual(call_args.kwargs["n_results"], 20)

    @patch("thoth.mcp.tools.get_vector_store")
    def test_search_handbook_calculates_similarity(self, mock_get_store):
        """Test that similarity score is calculated correctly."""
        mock_store = MagicMock()
        mock_store.search_similar.return_value = {
            "documents": ["Content"],
            "metadatas": [{"file_path": "test.md"}],
            "distances": [0.2],  # Distance of 0.2 = similarity of 0.8
        }
        mock_get_store.return_value = mock_store

        result = search_handbook("test")
        self.assertIn("similarity: 0.80", result)


class TestGetVectorStore(unittest.TestCase):
    """Test suite for get_vector_store function."""

    @patch("thoth.mcp.tools.VectorStore")
    @patch("thoth.mcp.tools.os.getenv")
    def test_get_vector_store_initializes_once(self, mock_getenv, mock_vs_class):
        """Test that vector store is initialized lazily and cached."""
        # Reset global state
        tools_module._vector_store = None

        mock_getenv.side_effect = {
            "GCS_BUCKET_NAME": "test-bucket",
            "GCP_PROJECT_ID": "test-project",
        }.get

        mock_store = MagicMock()
        mock_store.get_document_count.return_value = 10
        mock_vs_class.return_value = mock_store

        # First call should initialize
        store1 = tools_module.get_vector_store()
        self.assertEqual(mock_vs_class.call_count, 1)

        # Second call should return cached instance
        store2 = tools_module.get_vector_store()
        self.assertEqual(mock_vs_class.call_count, 1)
        self.assertIs(store1, store2)

        # Reset for other tests
        tools_module._vector_store = None


class TestMCPInstance(unittest.TestCase):
    """Test suite for MCP FastMCP instance."""

    def test_mcp_instance_exists(self):
        """Test that mcp instance is created."""
        self.assertIsNotNone(mcp)

    def test_mcp_has_correct_name(self):
        """Test that mcp has correct server name."""
        self.assertEqual(mcp.name, "ThothHandbookServer")


if __name__ == "__main__":
    unittest.main()
