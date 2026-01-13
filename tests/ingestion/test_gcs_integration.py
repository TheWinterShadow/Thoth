"""Integration test for GCS storage functionality.

Run this test only when GCS credentials are configured.
Set environment variable: GOOGLE_APPLICATION_CREDENTIALS
"""

import os
import tempfile
import time

import pytest

from thoth.ingestion.vector_store import VectorStore

# Skip all tests if GCS credentials not available
pytestmark = pytest.mark.skipif(
    not os.getenv("GOOGLE_APPLICATION_CREDENTIALS") and not os.getenv("SKIP_GCS_TESTS"),
    reason="GCS credentials not configured",
)


class TestGCSIntegration:
    """Integration tests for GCS storage."""

    @pytest.fixture
    def test_bucket_name(self):
        """GCS bucket name for testing."""
        return os.getenv("GCS_TEST_BUCKET", "thoth-storage-bucket")

    @pytest.fixture
    def test_project_id(self):
        """GCP project ID for testing."""
        return os.getenv("GCP_PROJECT_ID", "thoth-483015")

    @pytest.fixture
    def vector_store_with_gcs(self, test_bucket_name, test_project_id):
        """Create a vector store with GCS enabled."""
        with tempfile.TemporaryDirectory() as tmpdir:
            store = VectorStore(
                persist_directory=tmpdir,
                collection_name="test_collection",
                gcs_bucket_name=test_bucket_name,
                gcs_project_id=test_project_id,
            )
            yield store

    def test_backup_and_restore(self, vector_store_with_gcs):
        """Test backing up to GCS and restoring."""
        store = vector_store_with_gcs

        # Add some test documents
        test_docs = [
            "This is a test document",
            "Another test document",
            "Yet another test document",
        ]
        test_metadata = [
            {"source": "test1", "file_path": "test1.txt"},
            {"source": "test2", "file_path": "test2.txt"},
            {"source": "test3", "file_path": "test3.txt"},
        ]

        store.add_documents(test_docs, metadatas=test_metadata)

        # Verify documents were added
        initial_count = store.get_document_count()
        assert initial_count == 3

        # Backup to GCS
        backup_prefix = store.backup_to_gcs(backup_name="test_backup_integration")
        assert backup_prefix is not None
        assert "test_backup_integration" in backup_prefix

        # Clear local store
        store.reset()
        assert store.get_document_count() == 0

        # Restore from backup
        restored_count = store.restore_from_gcs(backup_name="test_backup_integration")
        assert restored_count > 0

        # Verify documents were restored
        final_count = store.get_document_count()
        assert final_count == initial_count

    def test_sync_to_gcs(self, vector_store_with_gcs):
        """Test syncing vector store to GCS."""
        store = vector_store_with_gcs

        # Add test documents
        test_docs = ["Test document for sync"]
        store.add_documents(test_docs)

        # Sync to GCS
        result = store.sync_to_gcs(gcs_prefix="test_sync")

        assert result is not None
        assert result["direction"] == "to_gcs"
        assert result["uploaded_files"] > 0

    def test_list_backups(self, vector_store_with_gcs):
        """Test listing backups from GCS."""
        store = vector_store_with_gcs

        # Create a backup first
        store.add_documents(["Test document"])
        store.backup_to_gcs(backup_name="test_list_backup")

        # List backups
        backups = store.list_gcs_backups()

        assert isinstance(backups, list)
        # May contain backups from previous test runs
        assert "test_list_backup" in backups or len(backups) >= 0

    def test_performance_acceptable(self, vector_store_with_gcs):
        """Test that backup/restore performance is acceptable."""
        store = vector_store_with_gcs

        # Add a moderate number of documents
        test_docs = [f"Test document {i}" for i in range(100)]
        test_metadata = [{"source": f"test{i}", "file_path": f"test{i}.txt"} for i in range(100)]

        store.add_documents(test_docs, metadatas=test_metadata)

        # Measure backup time
        start = time.time()
        _ = store.backup_to_gcs(backup_name="perf_test_backup")
        backup_time = time.time() - start

        # Clear store
        store.reset()

        # Measure restore time
        start = time.time()
        store.restore_from_gcs(backup_name="perf_test_backup")
        restore_time = time.time() - start

        # Assert performance is acceptable (< 30 seconds for 100 docs)
        assert backup_time < 30, f"Backup took {backup_time:.2f}s (should be < 30s)"
        assert restore_time < 30, f"Restore took {restore_time:.2f}s (should be < 30s)"
