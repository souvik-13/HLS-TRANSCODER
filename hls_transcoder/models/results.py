"""
Data models for transcoding results.

This module contains dataclasses for representing the results of transcoding operations.
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


@dataclass
class VideoVariantResult:
    """Result of a single video variant transcoding."""

    quality: str
    width: int
    height: int
    bitrate: str
    size: int
    segment_count: int
    duration: float
    playlist_path: Path

    @property
    def resolution(self) -> str:
        """Get resolution as string."""
        return f"{self.width}x{self.height}"

    @property
    def size_mb(self) -> float:
        """Get size in megabytes."""
        return self.size / (1024 * 1024)


@dataclass
class AudioTrackResult:
    """Result of audio extraction."""

    index: int
    language: str
    codec: str
    size: int
    playlist_path: Path

    @property
    def size_mb(self) -> float:
        """Get size in megabytes."""
        return self.size / (1024 * 1024)


@dataclass
class SubtitleResult:
    """Result of subtitle extraction."""

    index: int
    language: str
    format: str
    file_path: Path

    @property
    def exists(self) -> bool:
        """Check if subtitle file exists."""
        return self.file_path.exists()


@dataclass
class SpriteResult:
    """Result of sprite generation."""

    sprite_path: Path
    vtt_path: Path
    thumbnail_count: int
    size: int

    @property
    def size_mb(self) -> float:
        """Get size in megabytes."""
        return self.size / (1024 * 1024)

    @property
    def exists(self) -> bool:
        """Check if sprite files exist."""
        return self.sprite_path.exists() and self.vtt_path.exists()


@dataclass
class TranscodingResults:
    """Complete transcoding results."""

    video_variants: list[VideoVariantResult] = field(default_factory=list)
    audio_tracks: list[AudioTrackResult] = field(default_factory=list)
    subtitle_tracks: list[SubtitleResult] = field(default_factory=list)
    sprite: Optional[SpriteResult] = None
    master_playlist: Optional[Path] = None
    metadata_file: Optional[Path] = None
    total_size: int = 0
    total_duration: float = 0.0
    hardware_used: str = "software"
    parallel_jobs: int = 1
    total_frames: int = 0
    compression_ratio: float = 1.0

    @property
    def total_size_mb(self) -> float:
        """Get total size in megabytes."""
        return self.total_size / (1024 * 1024)

    @property
    def total_size_gb(self) -> float:
        """Get total size in gigabytes."""
        return self.total_size / (1024 * 1024 * 1024)

    @property
    def video_count(self) -> int:
        """Get number of video variants."""
        return len(self.video_variants)

    @property
    def audio_count(self) -> int:
        """Get number of audio tracks."""
        return len(self.audio_tracks)

    @property
    def subtitle_count(self) -> int:
        """Get number of subtitle tracks."""
        return len(self.subtitle_tracks)

    @property
    def has_sprites(self) -> bool:
        """Check if sprites were generated."""
        return self.sprite is not None and self.sprite.exists

    def get_variant_by_quality(self, quality: str) -> Optional[VideoVariantResult]:
        """Get video variant by quality name."""
        for variant in self.video_variants:
            if variant.quality == quality:
                return variant
        return None


@dataclass
class ValidationResult:
    """Output validation result."""

    success: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    master_playlist_valid: bool = True
    all_segments_present: bool = True
    audio_sync_valid: bool = True
    subtitle_files_valid: bool = True

    @property
    def has_errors(self) -> bool:
        """Check if there are any errors."""
        return len(self.errors) > 0

    @property
    def has_warnings(self) -> bool:
        """Check if there are any warnings."""
        return len(self.warnings) > 0

    @property
    def is_valid(self) -> bool:
        """Check if validation passed without errors."""
        return self.success and not self.has_errors

    def add_error(self, error: str) -> None:
        """Add an error message."""
        self.errors.append(error)
        self.success = False

    def add_warning(self, warning: str) -> None:
        """Add a warning message."""
        self.warnings.append(warning)
