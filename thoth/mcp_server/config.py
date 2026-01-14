"""Configuration management for MCP server.

Supports YAML/JSON configuration files for RAG setups and plugins.
"""

import json
import logging
import os
from pathlib import Path
from typing import Any

import yaml  # type: ignore[import-untyped]

logger = logging.getLogger(__name__)


class MCPConfig:
    """Configuration manager for MCP server."""

    def __init__(self, config_path: str | None = None):
        """Initialize configuration manager.

        Args:
            config_path: Path to configuration file (YAML or JSON)
                If not provided, looks for config.yaml or config.json in current directory
        """
        self.config_path = config_path
        self._config: dict[str, Any] = {}

        if config_path:
            self.load_from_file(config_path)
        else:
            # Try to load from default locations
            for default_path in ["config.yaml", "config.json", "mcp_config.yaml"]:
                if Path(default_path).exists():
                    self.load_from_file(default_path)
                    break

        # Load from environment variables
        self.load_from_env()

    def load_from_file(self, path: str) -> None:
        """Load configuration from file.

        Args:
            path: Path to configuration file
        """
        config_path = Path(path)
        if not config_path.exists():
            logger.warning(f"Configuration file not found: {path}")
            return

        try:
            # Open and parse configuration file based on extension
            with config_path.open() as f:
                # Support both YAML and JSON configuration formats
                if path.endswith((".yaml", ".yml")):
                    # Parse YAML configuration
                    self._config = yaml.safe_load(f) or {}
                else:
                    # Parse JSON configuration
                    self._config = json.load(f)

            logger.info(f"Loaded configuration from {path}")
        except (OSError, yaml.YAMLError, json.JSONDecodeError):
            # Log error but continue with empty config to allow fallback to env vars
            logger.exception(f"Failed to load configuration from {path}")
            self._config = {}

    def load_from_env(self) -> None:
        """Load configuration from environment variables."""
        # Override with environment variables
        env_config = {
            "s3_bucket_name": os.getenv("S3_BUCKET_NAME"),
            "dynamodb_table_name": os.getenv("DYNAMODB_TABLE_NAME"),
            "log_level": os.getenv("LOG_LEVEL", "INFO"),
        }

        # Merge environment config
        for key, value in env_config.items():
            if value is not None:
                self._set_nested(self._config, key, value)

    def _set_nested(self, d: dict, key: str, value: Any) -> None:
        """Set nested dictionary value using dot notation.

        Args:
            d: Dictionary to update
            key: Key in dot notation (e.g., 'rag.setups.handbook')
            value: Value to set
        """
        # Split dot-notation key into parts
        keys = key.split(".")
        # Navigate/create nested dictionaries for all but the last key
        for k in keys[:-1]:
            d = d.setdefault(k, {})
        # Set the final value at the last key
        d[keys[-1]] = value

    def get(self, key: str, default: Any = None) -> Any:
        """Get configuration value using dot notation.

        Args:
            key: Configuration key in dot notation
            default: Default value if key not found

        Returns:
            Configuration value or default
        """
        # Split dot-notation key into parts
        keys = key.split(".")
        value: Any = self._config
        # Navigate through nested dictionaries
        for k in keys:
            if isinstance(value, dict):
                value = value.get(k)
                # Return default if any intermediate key is missing
                if value is None:
                    return default
            else:
                # Return default if we hit a non-dict value before reaching the end
                return default
        # Return the final value or default if None
        return value if value is not None else default

    def get_rag_setups(self) -> list[dict[str, Any]]:
        """Get RAG setup configurations.

        Returns:
            List of RAG setup configurations
        """
        result = self.get("rag.setups", [])
        if isinstance(result, list):
            return result
        return []

    def get_plugin_config(self, plugin_name: str) -> dict[str, Any]:
        """Get configuration for a specific plugin.

        Args:
            plugin_name: Name of the plugin

        Returns:
            Plugin configuration dictionary
        """
        result = self.get(f"plugins.{plugin_name}", {})
        if isinstance(result, dict):
            return result
        return {}


# Global config instance
_config: MCPConfig | None = None


def get_config() -> MCPConfig:
    """Get or create the global configuration instance.

    Returns:
        MCPConfig instance
    """
    global _config  # noqa: PLW0603
    if _config is None:
        _config = MCPConfig()
    return _config
