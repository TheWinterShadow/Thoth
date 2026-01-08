"""
Unit tests for the vector_store module.

Tests ChromaDB initialization and CRUD operations.
"""

from pathlib import Path
import shutil
import tempfile
import unittest

from thoth.ingestion.vector_store import VectorStore


class TestVectorStore(unittest.TestCase):
    """Test cases for VectorStore class."""

    def setUp(self):
        """Set up test fixtures before each test method."""
        # Create a temporary directory for test database
        self.test_dir = tempfile.mkdtemp()
        self.vector_store = VectorStore(persist_directory=self.test_dir, collection_name="test_collection")

    def tearDown(self):
        """Clean up after each test method."""
        # Remove temporary directory
        if Path(self.test_dir).exists():
            shutil.rmtree(self.test_dir)

    def test_initialization(self):
        """Test that VectorStore initializes correctly."""
        self.assertIsNotNone(self.vector_store.client)
        self.assertIsNotNone(self.vector_store.collection)
        self.assertEqual(self.vector_store.collection_name, "test_collection")
        self.assertTrue(Path(self.test_dir).exists())

    def test_add_documents(self):
        """Test adding documents to the vector store."""
        documents = [
            "This is the first document.",
            "This is the second document.",
            "And this is the third one.",
        ]

        # Add documents
        self.vector_store.add_documents(documents)

        # Verify documents were added
        count = self.vector_store.get_document_count()
        self.assertEqual(count, 3)

    def test_add_documents_with_metadata(self):
        """Test adding documents with metadata."""
        documents = ["Document about Python", "Document about JavaScript"]
        metadatas = [
            {"language": "python", "category": "programming"},
            {"language": "javascript", "category": "programming"},
        ]

        self.vector_store.add_documents(documents, metadatas=metadatas)

        # Verify documents were added
        count = self.vector_store.get_document_count()
        self.assertEqual(count, 2)

        # Retrieve and verify metadata
        results = self.vector_store.get_documents()
        self.assertEqual(len(results["metadatas"]), 2)
        self.assertEqual(results["metadatas"][0]["language"], "python")

    def test_add_documents_with_custom_ids(self):
        """Test adding documents with custom IDs."""
        documents = ["Doc 1", "Doc 2"]
        ids = ["custom_id_1", "custom_id_2"]

        self.vector_store.add_documents(documents, ids=ids)

        # Retrieve documents by ID
        results = self.vector_store.get_documents(ids=["custom_id_1"])
        self.assertEqual(len(results["ids"]), 1)
        self.assertEqual(results["ids"][0], "custom_id_1")
        self.assertEqual(results["documents"][0], "Doc 1")

    def test_add_documents_validation(self):
        """Test input validation for add_documents."""
        documents = ["Doc 1", "Doc 2"]

        # Test mismatched metadata length
        with self.assertRaises(ValueError):
            self.vector_store.add_documents(
                documents,
                metadatas=[{"key": "value"}],  # Only 1 metadata for 2 docs
            )

        # Test mismatched ids length
        with self.assertRaises(ValueError):
            self.vector_store.add_documents(
                documents,
                ids=["id_1"],  # Only 1 ID for 2 docs
            )

    def test_add_empty_documents(self):
        """Test adding an empty list of documents."""
        # Should not raise an error, just log a warning
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

        # Search for programming-related documents
        results = self.vector_store.search_similar(query="programming languages", n_results=2)

        self.assertEqual(len(results["documents"]), 2)
        self.assertIn("ids", results)
        self.assertIn("distances", results)
        self.assertIn("metadatas", results)

    def test_search_similar_with_filters(self):
        """Test searching with metadata filters."""
        documents = ["Python tutorial", "JavaScript tutorial", "Python advanced guide"]
        metadatas = [
            {"language": "python", "level": "beginner"},
            {"language": "javascript", "level": "beginner"},
            {"language": "python", "level": "advanced"},
        ]

        self.vector_store.add_documents(documents, metadatas=metadatas)

        # Search only for Python documents
        results = self.vector_store.search_similar(query="tutorial", n_results=5, where={"language": "python"})

        # Should only return Python documents
        self.assertEqual(len(results["documents"]), 2)
        for metadata in results["metadatas"]:
            self.assertEqual(metadata["language"], "python")

    def test_delete_documents_by_ids(self):
        """Test deleting documents by IDs."""
        documents = ["Doc 1", "Doc 2", "Doc 3"]
        ids = ["id_1", "id_2", "id_3"]

        self.vector_store.add_documents(documents, ids=ids)
        self.assertEqual(self.vector_store.get_document_count(), 3)

        # Delete one document
        self.vector_store.delete_documents(ids=["id_2"])
        self.assertEqual(self.vector_store.get_document_count(), 2)

        # Verify the correct document was deleted
        results = self.vector_store.get_documents()
        remaining_ids = set(results["ids"])
        self.assertIn("id_1", remaining_ids)
        self.assertIn("id_3", remaining_ids)
        self.assertNotIn("id_2", remaining_ids)

    def test_delete_documents_by_metadata(self):
        """Test deleting documents by metadata filter."""
        documents = ["Python doc", "Java doc", "Python doc 2"]
        metadatas = [
            {"language": "python"},
            {"language": "java"},
            {"language": "python"},
        ]

        self.vector_store.add_documents(documents, metadatas=metadatas)
        self.assertEqual(self.vector_store.get_document_count(), 3)

        # Delete all Python documents
        self.vector_store.delete_documents(where={"language": "python"})
        self.assertEqual(self.vector_store.get_document_count(), 1)

        # Verify only Java document remains
        results = self.vector_store.get_documents()
        self.assertEqual(results["metadatas"][0]["language"], "java")

    def test_delete_documents_validation(self):
        """Test validation for delete_documents."""
        # Should raise ValueError if neither ids nor where is provided
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

        # Get all documents
        results = self.vector_store.get_documents()
        self.assertEqual(len(results["ids"]), 3)

        # Get specific documents by ID
        results = self.vector_store.get_documents(ids=["id_1", "id_3"])
        self.assertEqual(len(results["ids"]), 2)
        self.assertIn("id_1", results["ids"])
        self.assertIn("id_3", results["ids"])

    def test_get_documents_with_limit(self):
        """Test retrieving documents with a limit."""
        documents = [f"Doc {i}" for i in range(10)]
        self.vector_store.add_documents(documents)

        # Get only 5 documents
        results = self.vector_store.get_documents(limit=5)
        self.assertEqual(len(results["ids"]), 5)

    def test_get_documents_with_metadata_filter(self):
        """Test retrieving documents with metadata filter."""
        documents = ["Python doc", "Java doc", "Python doc 2"]
        metadatas = [
            {"language": "python"},
            {"language": "java"},
            {"language": "python"},
        ]

        self.vector_store.add_documents(documents, metadatas=metadatas)

        # Get only Python documents
        results = self.vector_store.get_documents(where={"language": "python"})
        self.assertEqual(len(results["ids"]), 2)
        for metadata in results["metadatas"]:
            self.assertEqual(metadata["language"], "python")

    def test_reset(self):
        """Test resetting the collection."""
        # Add some documents
        self.vector_store.add_documents(["Doc 1", "Doc 2", "Doc 3"])
        self.assertEqual(self.vector_store.get_document_count(), 3)

        # Reset the collection
        self.vector_store.reset()
        self.assertEqual(self.vector_store.get_document_count(), 0)

    def test_persistence(self):
        """Test that data persists across VectorStore instances."""
        # Add documents in first instance
        documents = ["Persistent doc 1", "Persistent doc 2"]
        ids = ["persist_1", "persist_2"]
        self.vector_store.add_documents(documents, ids=ids)

        # Create new instance with same directory
        new_vector_store = VectorStore(persist_directory=self.test_dir, collection_name="test_collection")

        # Verify documents persist
        self.assertEqual(new_vector_store.get_document_count(), 2)
        results = new_vector_store.get_documents()
        self.assertIn("persist_1", results["ids"])
        self.assertIn("persist_2", results["ids"])


if __name__ == "__main__":
    unittest.main()
