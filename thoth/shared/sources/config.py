"""Source configuration for multi-source ingestion.

This module provides configuration management for different data sources
(handbook, D&D, personal documents) with configurable GCS locations and
supported file formats.
"""

from dataclasses import dataclass, field
import os

from thoth.shared.utils.logger import setup_logger

logger = setup_logger(__name__)


@dataclass
class SourceConfig:
    """Configuration for a data source.

    Attributes:
        name: Unique identifier for the source (e.g., 'handbook', 'dnd')
        collection_name: ChromaDB collection name for this source
        gcs_prefix: GCS prefix where source files are stored
        supported_formats: List of supported file extensions (e.g., ['.md', '.pdf'])
        description: Human-readable description of the source
    """

    name: str
    collection_name: str
    gcs_prefix: str
    supported_formats: list[str] = field(default_factory=list)
    description: str = ""

    def supports_format(self, extension: str) -> bool:
        """Check if this source supports a file format.

        Args:
            extension: File extension including dot (e.g., '.md')

        Returns:
            True if format is supported
        """
        return extension.lower() in [fmt.lower() for fmt in self.supported_formats]


# Default source configurations
DEFAULT_SOURCES: dict[str, SourceConfig] = {
    "handbook": SourceConfig(
        name="handbook",
        collection_name="handbook_documents",
        gcs_prefix="handbook",
        supported_formats=[".md"],
        description="GitLab Handbook documentation",
    ),
    "dnd": SourceConfig(
        name="dnd",
        collection_name="dnd_documents",
        gcs_prefix="dnd",
        supported_formats=[".md", ".pdf", ".txt"],
        description="D&D game materials and rulebooks",
    ),
    "personal": SourceConfig(
        name="personal",
        collection_name="personal_documents",
        gcs_prefix="personal",
        supported_formats=[".md", ".pdf", ".txt", ".docx"],
        description="Personal documents and notes",
    ),
}


class SourceRegistry:
    """Registry for managing data source configurations.

    The registry loads default configurations and supports environment
    variable overrides for GCS prefixes.

    Environment variables:
        THOTH_SOURCE_{NAME}_GCS_PREFIX: Override GCS prefix for a source
        THOTH_SOURCE_{NAME}_COLLECTION: Override collection name for a source

    Example:
        THOTH_SOURCE_HANDBOOK_GCS_PREFIX=custom_handbook
        THOTH_SOURCE_DND_COLLECTION=my_dnd_collection
    """

    def __init__(self) -> None:
        """Initialize the source registry with defaults and overrides."""
        self._sources: dict[str, SourceConfig] = {}
        self._load_defaults()
        self._load_overrides()

    def _load_defaults(self) -> None:
        """Load default source configurations."""
        for name, config in DEFAULT_SOURCES.items():
            # Create a copy to avoid modifying the defaults
            self._sources[name] = SourceConfig(
                name=config.name,
                collection_name=config.collection_name,
                gcs_prefix=config.gcs_prefix,
                supported_formats=config.supported_formats.copy(),
                description=config.description,
            )

    def _load_overrides(self) -> None:
        """Load environment variable overrides for source configurations."""
        for name, config in self._sources.items():
            # Check for GCS prefix override
            gcs_env = f"THOTH_SOURCE_{name.upper()}_GCS_PREFIX"
            if os.getenv(gcs_env):
                config.gcs_prefix = os.getenv(gcs_env, config.gcs_prefix)
                logger.info("Override %s GCS prefix: %s", name, config.gcs_prefix)

            # Check for collection name override
            collection_env = f"THOTH_SOURCE_{name.upper()}_COLLECTION"
            if os.getenv(collection_env):
                config.collection_name = os.getenv(collection_env, config.collection_name)
                logger.info("Override %s collection: %s", name, config.collection_name)

    def get(self, name: str) -> SourceConfig | None:
        """Get source configuration by name.

        Args:
            name: Source identifier (e.g., 'handbook', 'dnd', 'personal')

        Returns:
            SourceConfig if found, None otherwise
        """
        return self._sources.get(name)

    def list_sources(self) -> list[str]:
        """List all registered source names.

        Returns:
            List of source names
        """
        return list(self._sources.keys())

    def list_configs(self) -> list[SourceConfig]:
        """List all source configurations.

        Returns:
            List of SourceConfig instances
        """
        return list(self._sources.values())

    def register(self, config: SourceConfig) -> None:
        """Register a new source configuration.

        Args:
            config: SourceConfig to register

        Raises:
            ValueError: If source with same name already exists
        """
        if config.name in self._sources:
            msg = f"Source '{config.name}' already registered"
            raise ValueError(msg)
        self._sources[config.name] = config
        logger.info("Registered new source: %s", config.name)

    def update(self, config: SourceConfig) -> None:
        """Update an existing source configuration.

        Args:
            config: SourceConfig with updated values
        """
        self._sources[config.name] = config
        logger.info("Updated source: %s", config.name)

    def get_all_collections(self) -> list[str]:
        """Get all collection names.

        Returns:
            List of collection names from all sources
        """
        return [config.collection_name for config in self._sources.values()]
