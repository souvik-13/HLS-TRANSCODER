"""
Configuration management for HLS transcoder.

This module handles loading, validating, and managing configuration from YAML files.
"""

import os
from pathlib import Path
from typing import Optional

import yaml

from hls_transcoder.config.models import TranscoderConfig
from hls_transcoder.utils import ConfigurationError, get_logger

logger = get_logger(__name__)


class ConfigManager:
    """Manages transcoder configuration."""

    DEFAULT_CONFIG_LOCATIONS = [
        Path.home() / ".hls-transcoder.yaml",
        Path.home() / ".config" / "hls-transcoder" / "config.yaml",
        Path.cwd() / ".hls-transcoder.yaml",
    ]

    def __init__(self, config_path: Optional[Path] = None):
        """
        Initialize configuration manager.

        Args:
            config_path: Optional path to configuration file
        """
        self.config_path = config_path
        self._config: Optional[TranscoderConfig] = None

    @property
    def config(self) -> TranscoderConfig:
        """
        Get current configuration, loading it if necessary.

        Returns:
            TranscoderConfig instance

        Raises:
            ConfigurationError: If configuration cannot be loaded
        """
        if self._config is None:
            self._config = self.load()
        return self._config

    def load(self, config_path: Optional[Path] = None) -> TranscoderConfig:
        """
        Load configuration from file or create default.

        Args:
            config_path: Optional path to configuration file

        Returns:
            Loaded TranscoderConfig

        Raises:
            ConfigurationError: If configuration file is invalid
        """
        # Use provided path or instance path
        path = config_path or self.config_path

        # If specific path provided, use it
        if path:
            if not path.exists():
                raise ConfigurationError(f"Configuration file not found: {path}")
            return self._load_from_file(path)

        # Try default locations
        for default_path in self.DEFAULT_CONFIG_LOCATIONS:
            if default_path.exists():
                logger.info(f"Loading configuration from {default_path}")
                return self._load_from_file(default_path)

        # No config file found, use defaults
        logger.info("No configuration file found, using defaults")
        return TranscoderConfig.create_default()

    def _load_from_file(self, path: Path) -> TranscoderConfig:
        """
        Load configuration from YAML file.

        Args:
            path: Path to configuration file

        Returns:
            Loaded TranscoderConfig

        Raises:
            ConfigurationError: If file cannot be loaded or parsed
        """
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f)

            if data is None:
                raise ConfigurationError(f"Configuration file is empty: {path}")

            # Parse with Pydantic
            config = TranscoderConfig(**data)
            logger.debug(f"Successfully loaded configuration from {path}")
            return config

        except yaml.YAMLError as e:
            raise ConfigurationError(f"Invalid YAML in configuration file: {e}")
        except Exception as e:
            raise ConfigurationError(f"Failed to load configuration: {e}")

    def save(self, path: Optional[Path] = None, config: Optional[TranscoderConfig] = None) -> None:
        """
        Save configuration to file.

        Args:
            path: Path to save configuration (uses default if None)
            config: Configuration to save (uses current if None)

        Raises:
            ConfigurationError: If configuration cannot be saved
        """
        # Use provided config or current config
        cfg = config or self.config

        # Use provided path or first default location
        save_path = path or self.config_path or self.DEFAULT_CONFIG_LOCATIONS[0]

        try:
            # Ensure parent directory exists
            save_path.parent.mkdir(parents=True, exist_ok=True)

            # Convert to dict and save as YAML
            data = cfg.model_dump(mode="json")

            with open(save_path, "w", encoding="utf-8") as f:
                yaml.safe_dump(data, f, default_flow_style=False, sort_keys=False, indent=2)

            logger.info(f"Configuration saved to {save_path}")

        except Exception as e:
            raise ConfigurationError(f"Failed to save configuration: {e}")

    def init_default_config(self, path: Optional[Path] = None, force: bool = False) -> Path:
        """
        Initialize default configuration file.

        Args:
            path: Path to create configuration file (uses default if None)
            force: Overwrite existing file

        Returns:
            Path to created configuration file

        Raises:
            ConfigurationError: If file already exists and force=False
        """
        target_path = path or self.DEFAULT_CONFIG_LOCATIONS[0]

        if target_path.exists() and not force:
            raise ConfigurationError(
                f"Configuration file already exists: {target_path}. Use force=True to overwrite."
            )

        # Create default configuration
        default_config = TranscoderConfig.create_default()

        # Save to file
        self.save(target_path, default_config)

        logger.info(f"Default configuration created at {target_path}")
        return target_path

    def reload(self) -> TranscoderConfig:
        """
        Reload configuration from file.

        Returns:
            Reloaded TranscoderConfig
        """
        self._config = None
        return self.load()

    def get_profile_variants(self, profile_name: str) -> list:
        """
        Get quality variants for a profile.

        Args:
            profile_name: Name of the quality profile

        Returns:
            List of quality variants

        Raises:
            ConfigurationError: If profile doesn't exist
        """
        variants = self.config.get_profile(profile_name)
        if variants is None:
            available = ", ".join(self.config.profiles.keys())
            raise ConfigurationError(
                f"Profile '{profile_name}' not found. Available profiles: {available}"
            )
        return variants

    @property
    def available_profiles(self) -> list[str]:
        """Get list of available profile names."""
        return list(self.config.profiles.keys())

    def validate(self) -> bool:
        """
        Validate current configuration.

        Returns:
            True if configuration is valid

        Raises:
            ConfigurationError: If configuration is invalid
        """
        try:
            # Pydantic will validate on access
            _ = self.config
            return True
        except Exception as e:
            raise ConfigurationError(f"Configuration validation failed: {e}")


# Global configuration manager instance
_config_manager: Optional[ConfigManager] = None


def get_config_manager(config_path: Optional[Path] = None) -> ConfigManager:
    """
    Get global configuration manager instance.

    Args:
        config_path: Optional path to configuration file

    Returns:
        ConfigManager instance
    """
    global _config_manager

    if _config_manager is None:
        _config_manager = ConfigManager(config_path)

    return _config_manager


def get_config(config_path: Optional[Path] = None) -> TranscoderConfig:
    """
    Get transcoder configuration.

    Args:
        config_path: Optional path to configuration file

    Returns:
        TranscoderConfig instance
    """
    manager = get_config_manager(config_path)
    return manager.config
