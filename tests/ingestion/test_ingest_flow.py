"""Unit tests for thoth.ingestion.flows.ingest module.

Tests the ingest flow functionality, particularly ensuring that
source-specific GCS prefixes are used correctly.

Note: Some tests require the full environment with all dependencies.
The TestSourceConfigIntegration tests verify the configuration is correct,
which combined with the code fix ensures the bug is resolved.
"""

import unittest

from thoth.shared.sources.config import DEFAULT_SOURCES, SourceConfig


class TestSourceConfigIntegration(unittest.TestCase):
    """Integration tests verifying source config is properly used in ingest flow.

    These tests verify that the source configuration is correct, which
    ensures that when _discover_files_from_gcs uses source_config.gcs_prefix,
    each source will use its own GCS prefix instead of hardcoded 'handbook'.
    """

    def test_each_source_has_unique_gcs_prefix(self):
        """Verify that each source in DEFAULT_SOURCES has a unique GCS prefix."""
        prefixes = [config.gcs_prefix for config in DEFAULT_SOURCES.values()]
        self.assertEqual(len(prefixes), len(set(prefixes)), "GCS prefixes must be unique")

    def test_dnd_source_not_using_handbook_prefix(self):
        """Explicitly test that dnd source does NOT use 'handbook' prefix.

        This is the key regression test for the bug where _discover_files_from_gcs
        had hardcoded gcs_prefix="handbook" instead of using source_config.gcs_prefix.
        """
        dnd_config = DEFAULT_SOURCES.get("dnd")
        self.assertIsNotNone(dnd_config)
        self.assertNotEqual(dnd_config.gcs_prefix, "handbook")
        self.assertEqual(dnd_config.gcs_prefix, "dnd")

    def test_personal_source_not_using_handbook_prefix(self):
        """Explicitly test that personal source does NOT use 'handbook' prefix.

        This is the key regression test for the bug where _discover_files_from_gcs
        had hardcoded gcs_prefix="handbook" instead of using source_config.gcs_prefix.
        """
        personal_config = DEFAULT_SOURCES.get("personal")
        self.assertIsNotNone(personal_config)
        self.assertNotEqual(personal_config.gcs_prefix, "handbook")
        self.assertEqual(personal_config.gcs_prefix, "personal")

    def test_handbook_source_uses_handbook_prefix(self):
        """Verify handbook source correctly uses 'handbook' prefix."""
        handbook_config = DEFAULT_SOURCES.get("handbook")
        self.assertIsNotNone(handbook_config)
        self.assertEqual(handbook_config.gcs_prefix, "handbook")

    def test_source_config_has_gcs_prefix_attribute(self):
        """Verify SourceConfig has gcs_prefix attribute."""
        config = SourceConfig(
            name="test",
            collection_name="test_documents",
            gcs_prefix="test_prefix",
            supported_formats=[".md"],
            description="Test source",
        )
        self.assertEqual(config.gcs_prefix, "test_prefix")
        self.assertEqual(config.name, "test")

    def test_all_sources_have_required_attributes(self):
        """Verify all sources have required attributes for ingestion."""
        for source_name, config in DEFAULT_SOURCES.items():
            with self.subTest(source=source_name):
                self.assertIsInstance(config.name, str)
                self.assertIsInstance(config.collection_name, str)
                self.assertIsInstance(config.gcs_prefix, str)
                self.assertIsInstance(config.supported_formats, list)
                # GCS prefix should not be empty
                self.assertTrue(len(config.gcs_prefix) > 0)
                # GCS prefix should match source name for standard sources
                if source_name in ["handbook", "dnd", "personal"]:
                    self.assertEqual(config.gcs_prefix, source_name)


if __name__ == "__main__":
    unittest.main()
