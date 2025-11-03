"""
Tests for configuration system.
"""

import tempfile
from pathlib import Path

import pytest

from hls_transcoder.config import ConfigManager, TranscoderConfig, QualityVariant
from hls_transcoder.utils import ConfigurationError


class TestTranscoderConfig:
    """Test TranscoderConfig model."""

    def test_create_default(self):
        """Test creating default configuration."""
        config = TranscoderConfig.create_default()

        assert config.hardware.prefer == "auto"
        assert config.hardware.fallback == "software"
        assert len(config.profiles) == 4
        assert "ultra" in config.profiles
        assert "high" in config.profiles
        assert "medium" in config.profiles
        assert "low" in config.profiles

    def test_get_profile(self):
        """Test getting quality profile."""
        config = TranscoderConfig.create_default()

        high_profile = config.get_profile("high")
        assert high_profile is not None
        assert len(high_profile) == 5
        assert high_profile[0].quality == "1440p"

        ultra_profile = config.get_profile("ultra")
        assert ultra_profile is not None
        assert len(ultra_profile) == 6
        assert ultra_profile[0].quality == "2160p"

    def test_add_profile(self):
        """Test adding custom profile."""
        config = TranscoderConfig.create_default()

        custom_variants = [
            QualityVariant(quality="720p", bitrate="3000k", crf=23),
            QualityVariant(quality="480p", bitrate="1500k", crf=26),
        ]
        config.add_profile("custom", custom_variants)

        assert "custom" in config.profiles
        assert len(config.profiles["custom"]) == 2

    def test_remove_profile(self):
        """Test removing profile."""
        config = TranscoderConfig.create_default()

        assert config.remove_profile("low") is True
        assert "low" not in config.profiles
        assert config.remove_profile("nonexistent") is False


class TestConfigManager:
    """Test ConfigManager."""

    def test_load_default(self):
        """Test loading default configuration."""
        manager = ConfigManager()
        config = manager.load()

        assert isinstance(config, TranscoderConfig)
        assert config.hardware.prefer == "auto"

    def test_save_and_load(self):
        """Test saving and loading configuration."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "config.yaml"

            # Create and save config
            manager = ConfigManager(config_path)
            config = TranscoderConfig.create_default()
            manager.save(config_path, config)

            assert config_path.exists()

            # Load config
            manager2 = ConfigManager(config_path)
            loaded_config = manager2.load()

            assert loaded_config.hardware.prefer == config.hardware.prefer
            assert len(loaded_config.profiles) == len(config.profiles)

    def test_init_default_config(self):
        """Test initializing default config file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "config.yaml"

            manager = ConfigManager()
            created_path = manager.init_default_config(config_path)

            assert created_path.exists()
            assert created_path == config_path

    def test_init_existing_config_without_force(self):
        """Test initializing config when file exists without force."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "config.yaml"
            config_path.touch()

            manager = ConfigManager()

            with pytest.raises(ConfigurationError):
                manager.init_default_config(config_path, force=False)

    def test_get_profile_variants(self):
        """Test getting profile variants."""
        manager = ConfigManager()
        variants = manager.get_profile_variants("high")

        assert len(variants) == 5
        assert variants[0].quality == "1440p"

    def test_get_nonexistent_profile(self):
        """Test getting nonexistent profile."""
        manager = ConfigManager()

        with pytest.raises(ConfigurationError):
            manager.get_profile_variants("nonexistent")

    def test_available_profiles(self):
        """Test getting available profiles."""
        manager = ConfigManager()
        profiles = manager.available_profiles

        assert len(profiles) == 4
        assert "ultra" in profiles
        assert "high" in profiles
        assert "medium" in profiles
        assert "low" in profiles


class TestQualityVariant:
    """Test QualityVariant validation."""

    def test_valid_quality(self):
        """Test valid quality variant."""
        variant = QualityVariant(quality="1080p", bitrate="5000k", crf=23)

        assert variant.quality == "1080p"
        assert variant.bitrate == "5000k"
        assert variant.crf == 23
        assert variant.width is None
        assert variant.height is None

    def test_quality_with_custom_resolution(self):
        """Test quality variant with custom resolution."""
        variant = QualityVariant(
            quality="original", bitrate="10000k", crf=20, width=1366, height=768
        )

        assert variant.quality == "original"
        assert variant.width == 1366
        assert variant.height == 768

    def test_4k_quality(self):
        """Test 4K quality variant."""
        variant = QualityVariant(quality="2160p", bitrate="20000k", crf=18)

        assert variant.quality == "2160p"
        assert variant.bitrate == "20000k"
        assert variant.crf == 18

    def test_invalid_quality(self):
        """Test invalid quality label."""
        with pytest.raises(ValueError):
            QualityVariant(quality="900p", bitrate="5000k", crf=23)

    def test_invalid_crf(self):
        """Test invalid CRF value."""
        with pytest.raises(ValueError):
            QualityVariant(quality="1080p", bitrate="5000k", crf=60)
