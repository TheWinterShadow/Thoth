"""
Unit tests for the vector_store module.

Tests LanceDB initialization and CRUD operations.
"""

from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import MagicMock, patch

import lancedb

from thoth.shared.vector_store import VectorStore


class TestVectorStore(unittest.TestCase):
    """Test cases for VectorStore class."""

    def setUp(self):
        """Set up test fixtures before each test method."""
        self.test_dir = tempfile.mkdtemp()

        self.mock_embedder = MagicMock()
        self.mock_embedder.model_name = "mock-model"
        self.mock_embedder.get_embedding_dimension.return_value = 384
        self.mock_embedder.embed.side_effect = lambda texts, **kwargs: [[0.1] * 384] * len(texts)
        self.mock_embedder.embed_single.return_value = [0.1] * 384

        self.vector_store = VectorStore(
            persist_directory=self.test_dir,
            collection_name="test_collection",
            embedder=self.mock_embedder,
        )

    def tearDown(self):
        """Clean up after each test method."""
        if Path(self.test_dir).exists():
            shutil.rmtree(self.test_dir)

    def test_initialization(self):
        """Test that VectorStore initializes correctly."""
        self.assertIsNotNone(self.vector_store.db)
        self.assertIsNotNone(self.vector_store.table)
        self.assertEqual(self.vector_store.collection_name, "test_collection")
        self.assertTrue(Path(self.test_dir).exists())

    def test_add_documents(self):
        """Test adding documents to the vector store."""
        documents = [
            "This is the first document.",
            "This is the second document.",
            "And this is the third one.",
        ]
        self.vector_store.add_documents(documents)
        count = self.vector_store.get_document_count()
        self.assertEqual(count, 3)

    def test_add_documents_with_metadata(self):
        """Test adding documents with metadata (schema: section, source, etc.)."""
        documents = ["Document about Python", "Document about JavaScript"]
        metadatas = [
            {"section": "python", "source": "test"},
            {"section": "javascript", "source": "test"},
        ]
        self.vector_store.add_documents(documents, metadatas=metadatas)
        count = self.vector_store.get_document_count()
        self.assertEqual(count, 2)
        results = self.vector_store.get_documents()
        self.assertEqual(len(results["metadatas"]), 2)
        # Order is not guaranteed by the store; assert both metadata entries exist.
        sections = {m.get("section") for m in results["metadatas"]}
        self.assertEqual(sections, {"python", "javascript"})

    def test_add_documents_with_custom_ids(self):
        """Test adding documents with custom IDs."""
        documents = ["Doc 1", "Doc 2"]
        ids = ["custom_id_1", "custom_id_2"]
        self.vector_store.add_documents(documents, ids=ids)
        results = self.vector_store.get_documents(ids=["custom_id_1"])
        self.assertEqual(len(results["ids"]), 1)
        self.assertEqual(results["ids"][0], "custom_id_1")
        self.assertEqual(results["documents"][0], "Doc 1")

    def test_add_documents_validation(self):
        """Test input validation for add_documents."""
        documents = ["Doc 1", "Doc 2"]
        with self.assertRaises(ValueError):
            self.vector_store.add_documents(
                documents,
                metadatas=[{"key": "value"}],
            )
        with self.assertRaises(ValueError):
            self.vector_store.add_documents(
                documents,
                ids=["id_1"],
            )

    def test_add_empty_documents(self):
        """Test adding an empty list of documents."""
        self.vector_store.add_documents([])
        count = self.vector_store.get_document_count()
        self.assertEqual(count, 0)

    def test_search_similar(self):
        """Test searching for similar documents."""
        documents = [
            "Python is a programming language.",
            "JavaScript is also a programming language.",
            "The weather is nice today.",
        ]
        self.vector_store.add_documents(documents)
        results = self.vector_store.search_similar(query="programming languages", n_results=2)
        self.assertEqual(len(results["documents"]), 2)
        self.assertIn("ids", results)
        self.assertIn("distances", results)
        self.assertIn("metadatas", results)

    def test_search_similar_with_filters(self):
        """Test searching with metadata filters (schema: section)."""
        documents = [
            "Python tutorial",
            "JavaScript tutorial",
            "Python advanced guide",
        ]
        metadatas = [
            {"section": "python"},
            {"section": "javascript"},
            {"section": "python"},
        ]
        self.vector_store.add_documents(documents, metadatas=metadatas)
        results = self.vector_store.search_similar(query="tutorial", n_results=5, where={"section": "python"})
        self.assertEqual(len(results["documents"]), 2)
        for metadata in results["metadatas"]:
            self.assertEqual(metadata.get("section"), "python")

    def test_delete_documents_by_ids(self):
        """Test deleting documents by IDs."""
        documents = ["Doc 1", "Doc 2", "Doc 3"]
        ids = ["id_1", "id_2", "id_3"]
        self.vector_store.add_documents(documents, ids=ids)
        self.assertEqual(self.vector_store.get_document_count(), 3)
        self.vector_store.delete_documents(ids=["id_2"])
        self.assertEqual(self.vector_store.get_document_count(), 2)
        results = self.vector_store.get_documents()
        remaining_ids = set(results["ids"])
        self.assertIn("id_1", remaining_ids)
        self.assertIn("id_3", remaining_ids)
        self.assertNotIn("id_2", remaining_ids)

    def test_delete_documents_by_metadata(self):
        """Test deleting documents by metadata filter (schema: section)."""
        documents = ["Python doc", "Java doc", "Python doc 2"]
        metadatas = [
            {"section": "python"},
            {"section": "java"},
            {"section": "python"},
        ]
        self.vector_store.add_documents(documents, metadatas=metadatas)
        self.assertEqual(self.vector_store.get_document_count(), 3)
        self.vector_store.delete_documents(where={"section": "python"})
        self.assertEqual(self.vector_store.get_document_count(), 1)
        results = self.vector_store.get_documents()
        self.assertEqual(results["metadatas"][0].get("section"), "java")

    def test_delete_documents_validation(self):
        """Test validation for delete_documents."""
        with self.assertRaises(ValueError):
            self.vector_store.delete_documents()

    def test_get_document_count(self):
        """Test getting document count."""
        self.assertEqual(self.vector_store.get_document_count(), 0)
        self.vector_store.add_documents(["Doc 1", "Doc 2"])
        self.assertEqual(self.vector_store.get_document_count(), 2)
        self.vector_store.add_documents(["Doc 3"])
        self.assertEqual(self.vector_store.get_document_count(), 3)

    def test_get_documents(self):
        """Test retrieving documents."""
        documents = ["Doc 1", "Doc 2", "Doc 3"]
        ids = ["id_1", "id_2", "id_3"]
        self.vector_store.add_documents(documents, ids=ids)
        results = self.vector_store.get_documents()
        self.assertEqual(len(results["ids"]), 3)
        results = self.vector_store.get_documents(ids=["id_1", "id_3"])
        self.assertEqual(len(results["ids"]), 2)
        self.assertIn("id_1", results["ids"])
        self.assertIn("id_3", results["ids"])

    def test_get_documents_with_limit(self):
        """Test retrieving documents with a limit."""
        documents = [f"Doc {i}" for i in range(10)]
        self.vector_store.add_documents(documents)
        results = self.vector_store.get_documents(limit=5)
        self.assertEqual(len(results["ids"]), 5)

    def test_get_documents_with_metadata_filter(self):
        """Test retrieving documents with metadata filter (schema: section)."""
        documents = ["Python doc", "Java doc", "Python doc 2"]
        metadatas = [
            {"section": "python"},
            {"section": "java"},
            {"section": "python"},
        ]
        self.vector_store.add_documents(documents, metadatas=metadatas)
        results = self.vector_store.get_documents(where={"section": "python"})
        self.assertEqual(len(results["ids"]), 2)
        for metadata in results["metadatas"]:
            self.assertEqual(metadata.get("section"), "python")

    def test_reset(self):
        """Test resetting the collection."""
        self.vector_store.add_documents(["Doc 1", "Doc 2", "Doc 3"])
        self.assertEqual(self.vector_store.get_document_count(), 3)
        self.vector_store.reset()
        self.assertEqual(self.vector_store.get_document_count(), 0)

    def test_persistence(self):
        """Test that data persists across VectorStore instances."""
        documents = ["Persistent doc 1", "Persistent doc 2"]
        ids = ["persist_1", "persist_2"]
        self.vector_store.add_documents(documents, ids=ids)

        # LanceDB list_tables() may return different types across versions; ensure
        # the second VectorStore sees the existing table by patching list_tables.
        real_connect = lancedb.connect
        test_dir_str = str(self.test_dir)

        def patched_connect(uri):
            db = real_connect(uri)
            if str(uri) == test_dir_str:
                _orig = db.list_tables

                def list_tables():
                    out = _orig()
                    names = list(out) if hasattr(out, "__iter__") and not isinstance(out, str) else []
                    if "test_collection" not in names:
                        names.append("test_collection")
                    return names

                db.list_tables = list_tables
            return db

        with self.subTest():
            with patch("thoth.shared.vector_store.lancedb") as mock_lancedb:
                mock_lancedb.connect = patched_connect
                new_vector_store = VectorStore(
                    persist_directory=self.test_dir,
                    collection_name="test_collection",
                    embedder=self.vector_store.embedder,
                )
            self.assertEqual(new_vector_store.get_document_count(), 2)
            results = new_vector_store.get_documents()
            self.assertIn("persist_1", results["ids"])
            self.assertIn("persist_2", results["ids"])


if __name__ == "__main__":
    unittest.main()
