"""
Configuration models using Pydantic.

This module defines the configuration structure for the HLS transcoder.
"""

from pathlib import Path
from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator


class HardwareConfig(BaseModel):
    """Hardware acceleration configuration."""

    prefer: str = Field(
        default="auto",
        description="Preferred hardware encoder: auto, nvenc, qsv, vaapi, amf, videotoolbox, none",
    )
    fallback: str = Field(
        default="software", description="Fallback to software encoding if HW fails"
    )
    max_instances: int = Field(
        default=4, ge=1, le=16, description="Max concurrent HW encoder instances"
    )

    @field_validator("prefer")
    @classmethod
    def validate_prefer(cls, v: str) -> str:
        """Validate preferred hardware encoder."""
        valid_options = ["auto", "nvenc", "qsv", "vaapi", "amf", "videotoolbox", "none"]
        if v.lower() not in valid_options:
            raise ValueError(f"prefer must be one of {valid_options}")
        return v.lower()

    @field_validator("fallback")
    @classmethod
    def validate_fallback(cls, v: str) -> str:
        """Validate fallback option."""
        valid_options = ["software", "none"]
        if v.lower() not in valid_options:
            raise ValueError(f"fallback must be one of {valid_options}")
        return v.lower()


class QualityVariant(BaseModel):
    """Quality variant configuration."""

    quality: str = Field(description="Quality label (e.g., 1080p, 720p, or 'original')")
    bitrate: str = Field(description="Target bitrate (e.g., 5000k)")
    crf: int = Field(ge=0, le=51, description="Constant Rate Factor (0-51, lower is better)")
    width: Optional[int] = Field(
        default=None, description="Custom width (for non-standard resolutions)"
    )
    height: Optional[int] = Field(
        default=None, description="Custom height (for non-standard resolutions)"
    )

    @field_validator("quality")
    @classmethod
    def validate_quality(cls, v: str) -> str:
        """Validate quality label."""
        valid_qualities = ["2160p", "1440p", "1080p", "720p", "480p", "360p", "240p", "original"]
        if v not in valid_qualities:
            raise ValueError(f"quality must be one of {valid_qualities}")
        return v


class HLSConfig(BaseModel):
    """HLS output configuration."""

    segment_duration: int = Field(default=6, ge=2, le=10, description="Segment duration in seconds")
    playlist_type: Literal["vod", "event"] = Field(
        default="vod", description="Playlist type: vod or event"
    )
    delete_threshold: int = Field(
        default=0, ge=0, description="Delete threshold (0 = keep all segments)"
    )


class AudioConfig(BaseModel):
    """Audio encoding configuration."""

    codec: str = Field(default="aac", description="Audio codec")
    bitrate: str = Field(default="128k", description="Audio bitrate")
    channels: int | str = Field(
        default="auto", description="Audio channels (auto, 1-8, or specific number)"
    )
    sample_rate: int | str = Field(
        default="auto", description="Sample rate in Hz (auto or specific value)"
    )
    segment_duration: int = Field(
        default=10, ge=2, le=20, description="Audio segment duration in seconds"
    )
    copy_if_possible: bool = Field(
        default=True, description="Use stream copy if source audio is compatible (no re-encoding)"
    )

    @field_validator("codec")
    @classmethod
    def validate_codec(cls, v: str) -> str:
        """Validate audio codec."""
        valid_codecs = ["aac", "mp3", "opus"]
        if v.lower() not in valid_codecs:
            raise ValueError(f"codec must be one of {valid_codecs}")
        return v.lower()

    @field_validator("channels")
    @classmethod
    def validate_channels(cls, v: int | str) -> int | str:
        """Validate audio channels."""
        if isinstance(v, str):
            if v.lower() == "auto":
                return "auto"
            raise ValueError("channels must be 'auto' or an integer between 1 and 8")
        if not (1 <= v <= 8):
            raise ValueError("channels must be between 1 and 8")
        return v

    @field_validator("sample_rate")
    @classmethod
    def validate_sample_rate(cls, v: int | str) -> int | str:
        """Validate sample rate."""
        if isinstance(v, str):
            if v.lower() == "auto":
                return "auto"
            raise ValueError("sample_rate must be 'auto' or a valid integer")
        if v not in [8000, 11025, 16000, 22050, 44100, 48000, 88200, 96000]:
            raise ValueError("sample_rate must be a standard audio sample rate")
        return v


class SpriteConfig(BaseModel):
    """Sprite generation configuration."""

    enabled: bool = Field(default=True, description="Enable sprite generation")
    interval: int = Field(
        default=10, ge=1, le=60, description="Interval between thumbnails in seconds"
    )
    width: int = Field(default=160, ge=80, le=320, description="Thumbnail width")
    height: int = Field(default=90, ge=45, le=180, description="Thumbnail height")
    columns: int = Field(default=10, ge=5, le=20, description="Columns in sprite sheet")
    rows: int = Field(default=10, ge=5, le=20, description="Rows in sprite sheet")


class PerformanceConfig(BaseModel):
    """Performance tuning configuration."""

    max_parallel_tasks: int = Field(default=4, ge=1, le=32, description="Maximum parallel tasks")
    thread_queue_size: int = Field(
        default=512, ge=128, le=2048, description="FFmpeg thread queue size"
    )
    preset: str = Field(
        default="medium",
        description="Encoding preset: ultrafast, superfast, veryfast, faster, fast, medium, slow, slower, veryslow",
    )

    @field_validator("preset")
    @classmethod
    def validate_preset(cls, v: str) -> str:
        """Validate encoding preset."""
        valid_presets = [
            "ultrafast",
            "superfast",
            "veryfast",
            "faster",
            "fast",
            "medium",
            "slow",
            "slower",
            "veryslow",
        ]
        if v.lower() not in valid_presets:
            raise ValueError(f"preset must be one of {valid_presets}")
        return v.lower()


class OutputConfig(BaseModel):
    """Output configuration."""

    create_metadata: bool = Field(default=True, description="Create metadata.json file")
    organize_by_type: bool = Field(
        default=True, description="Organize output by type (video/audio/subtitles)"
    )
    cleanup_temp: bool = Field(default=True, description="Cleanup temporary files after completion")


class TranscoderConfig(BaseModel):
    """Main transcoder configuration."""

    hardware: HardwareConfig = Field(default_factory=HardwareConfig)
    profiles: dict[str, list[QualityVariant]] = Field(default_factory=dict)
    hls: HLSConfig = Field(default_factory=HLSConfig)
    audio: AudioConfig = Field(default_factory=AudioConfig)
    sprites: SpriteConfig = Field(default_factory=SpriteConfig)
    performance: PerformanceConfig = Field(default_factory=PerformanceConfig)
    output: OutputConfig = Field(default_factory=OutputConfig)

    @classmethod
    def create_default(cls) -> "TranscoderConfig":
        """Create default configuration with predefined profiles."""
        config = cls()

        # Ultra quality profile (4K)
        config.profiles["ultra"] = [
            QualityVariant(quality="2160p", bitrate="20000k", crf=18),
            QualityVariant(quality="1440p", bitrate="16000k", crf=20),
            QualityVariant(quality="1080p", bitrate="10000k", crf=20),
            QualityVariant(quality="720p", bitrate="6000k", crf=23),
            QualityVariant(quality="480p", bitrate="3000k", crf=26),
            QualityVariant(quality="360p", bitrate="1000k", crf=28),
        ]

        # High quality profile
        config.profiles["high"] = [
            QualityVariant(quality="1440p", bitrate="12000k", crf=22),
            QualityVariant(quality="1080p", bitrate="8000k", crf=20),
            QualityVariant(quality="720p", bitrate="5000k", crf=23),
            QualityVariant(quality="480p", bitrate="2500k", crf=26),
            QualityVariant(quality="360p", bitrate="1000k", crf=28),
        ]

        # Medium quality profile
        config.profiles["medium"] = [
            QualityVariant(quality="1080p", bitrate="5000k", crf=23),
            QualityVariant(quality="720p", bitrate="3000k", crf=25),
            QualityVariant(quality="480p", bitrate="1500k", crf=28),
        ]

        # Low quality profile
        config.profiles["low"] = [
            QualityVariant(quality="720p", bitrate="2000k", crf=28),
            QualityVariant(quality="480p", bitrate="1000k", crf=30),
        ]

        return config

    def get_profile(self, name: str) -> Optional[list[QualityVariant]]:
        """Get quality profile by name."""
        return self.profiles.get(name)

    def add_profile(self, name: str, variants: list[QualityVariant]) -> None:
        """Add or update a quality profile."""
        self.profiles[name] = variants

    def remove_profile(self, name: str) -> bool:
        """Remove a quality profile."""
        if name in self.profiles:
            del self.profiles[name]
            return True
        return False
