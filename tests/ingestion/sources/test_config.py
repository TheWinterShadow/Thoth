"""Tests for source configuration module."""

import os
from unittest.mock import patch

import pytest

from thoth.ingestion.sources.config import (
    DEFAULT_SOURCES,
    SourceConfig,
    SourceRegistry,
)


class TestSourceConfig:
    """Tests for SourceConfig dataclass."""

    def test_source_config_creation(self):
        """Test creating a SourceConfig."""
        config = SourceConfig(
            name="test_source",
            collection_name="test_collection",
            gcs_prefix="test_prefix",
            supported_formats=[".md", ".pdf"],
            description="Test description",
        )

        assert config.name == "test_source"
        assert config.collection_name == "test_collection"
        assert config.gcs_prefix == "test_prefix"
        assert config.supported_formats == [".md", ".pdf"]
        assert config.description == "Test description"

    def test_source_config_defaults(self):
        """Test SourceConfig default values."""
        config = SourceConfig(
            name="minimal",
            collection_name="minimal_collection",
            gcs_prefix="minimal_prefix",
        )

        assert config.supported_formats == []
        assert config.description == ""

    def test_supports_format(self):
        """Test the supports_format method."""
        config = SourceConfig(
            name="test",
            collection_name="test_collection",
            gcs_prefix="test_prefix",
            supported_formats=[".md", ".PDF", ".txt"],
        )

        # Case-insensitive matching
        assert config.supports_format(".md")
        assert config.supports_format(".MD")
        assert config.supports_format(".pdf")
        assert config.supports_format(".PDF")
        assert config.supports_format(".txt")

        # Unsupported format
        assert not config.supports_format(".docx")
        assert not config.supports_format(".jpg")

    def test_supports_format_empty(self):
        """Test supports_format with empty formats list."""
        config = SourceConfig(
            name="test",
            collection_name="test_collection",
            gcs_prefix="test_prefix",
        )

        assert not config.supports_format(".md")
        assert not config.supports_format(".pdf")


class TestDefaultSources:
    """Tests for default source configurations."""

    def test_default_sources_exist(self):
        """Test that default sources are defined."""
        assert "handbook" in DEFAULT_SOURCES
        assert "dnd" in DEFAULT_SOURCES
        assert "personal" in DEFAULT_SOURCES

    def test_handbook_config(self):
        """Test handbook source configuration."""
        config = DEFAULT_SOURCES["handbook"]

        assert config.name == "handbook"
        assert config.collection_name == "handbook_documents"
        assert config.gcs_prefix == "handbook"
        assert ".md" in config.supported_formats
        assert config.description

    def test_dnd_config(self):
        """Test D&D source configuration."""
        config = DEFAULT_SOURCES["dnd"]

        assert config.name == "dnd"
        assert config.collection_name == "dnd_documents"
        assert config.gcs_prefix == "dnd"
        assert ".md" in config.supported_formats
        assert ".pdf" in config.supported_formats
        assert ".txt" in config.supported_formats

    def test_personal_config(self):
        """Test personal source configuration."""
        config = DEFAULT_SOURCES["personal"]

        assert config.name == "personal"
        assert config.collection_name == "personal_documents"
        assert config.gcs_prefix == "personal"
        assert ".md" in config.supported_formats
        assert ".pdf" in config.supported_formats
        assert ".txt" in config.supported_formats
        assert ".docx" in config.supported_formats


class TestSourceRegistry:
    """Tests for SourceRegistry class."""

    def test_registry_initialization(self):
        """Test registry initializes with default sources."""
        registry = SourceRegistry()

        assert registry.get("handbook") is not None
        assert registry.get("dnd") is not None
        assert registry.get("personal") is not None

    def test_get_source(self):
        """Test getting a source by name."""
        registry = SourceRegistry()
        config = registry.get("handbook")

        assert config is not None
        assert config.name == "handbook"
        assert config.collection_name == "handbook_documents"

    def test_get_nonexistent_source(self):
        """Test getting a non-existent source."""
        registry = SourceRegistry()
        config = registry.get("nonexistent")

        assert config is None

    def test_list_sources(self):
        """Test listing source names."""
        registry = SourceRegistry()
        sources = registry.list_sources()

        assert isinstance(sources, list)
        assert "handbook" in sources
        assert "dnd" in sources
        assert "personal" in sources
        assert len(sources) >= 3

    def test_list_configs(self):
        """Test listing source configurations."""
        registry = SourceRegistry()
        configs = registry.list_configs()

        assert isinstance(configs, list)
        assert all(isinstance(c, SourceConfig) for c in configs)
        assert len(configs) >= 3

    def test_register_new_source(self):
        """Test registering a new source."""
        registry = SourceRegistry()
        new_config = SourceConfig(
            name="custom",
            collection_name="custom_collection",
            gcs_prefix="custom_prefix",
            supported_formats=[".json"],
            description="Custom source",
        )

        registry.register(new_config)

        assert registry.get("custom") is not None
        assert registry.get("custom").collection_name == "custom_collection"
        assert "custom" in registry.list_sources()

    def test_register_duplicate_source(self):
        """Test registering a duplicate source raises error."""
        registry = SourceRegistry()
        duplicate_config = SourceConfig(
            name="handbook",  # Already exists
            collection_name="different_collection",
            gcs_prefix="different_prefix",
        )

        with pytest.raises(ValueError, match="already registered"):
            registry.register(duplicate_config)

    def test_update_source(self):
        """Test updating an existing source."""
        registry = SourceRegistry()
        updated_config = SourceConfig(
            name="handbook",
            collection_name="updated_handbook_collection",
            gcs_prefix="updated_handbook_prefix",
            supported_formats=[".md", ".rst"],
        )

        registry.update(updated_config)

        config = registry.get("handbook")
        assert config.collection_name == "updated_handbook_collection"
        assert config.gcs_prefix == "updated_handbook_prefix"
        assert ".rst" in config.supported_formats

    def test_get_all_collections(self):
        """Test getting all collection names."""
        registry = SourceRegistry()
        collections = registry.get_all_collections()

        assert isinstance(collections, list)
        assert "handbook_documents" in collections
        assert "dnd_documents" in collections
        assert "personal_documents" in collections

    def test_env_override_gcs_prefix(self):
        """Test environment variable override for GCS prefix."""
        with patch.dict(os.environ, {"THOTH_SOURCE_HANDBOOK_GCS_PREFIX": "custom_handbook_prefix"}):
            registry = SourceRegistry()
            config = registry.get("handbook")

            assert config.gcs_prefix == "custom_handbook_prefix"

    def test_env_override_collection(self):
        """Test environment variable override for collection name."""
        with patch.dict(os.environ, {"THOTH_SOURCE_DND_COLLECTION": "my_dnd_collection"}):
            registry = SourceRegistry()
            config = registry.get("dnd")

            assert config.collection_name == "my_dnd_collection"

    def test_registry_does_not_modify_defaults(self):
        """Test that registry doesn't modify DEFAULT_SOURCES."""
        original_gcs_prefix = DEFAULT_SOURCES["handbook"].gcs_prefix

        registry = SourceRegistry()
        registry.get("handbook").gcs_prefix = "modified_prefix"

        # DEFAULT_SOURCES should remain unchanged
        assert DEFAULT_SOURCES["handbook"].gcs_prefix == original_gcs_prefix
