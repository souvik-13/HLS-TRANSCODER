"""
Data models for media file information.

This module contains dataclasses for representing video, audio, and subtitle streams,
as well as complete media file information.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Optional


@dataclass
class FormatInfo:
    """Information about media container format."""

    format_name: str
    format_long_name: str
    duration: float
    size: int
    bitrate: int
    # Additional metadata
    encoder: Optional[str] = None
    creation_time: Optional[str] = None


@dataclass
class VideoStream:
    """Information about a video stream."""

    index: int
    codec: str
    codec_long: str
    profile: str
    width: int
    height: int
    fps: float
    bitrate: int
    duration: float
    pix_fmt: str
    color_space: Optional[str] = None
    color_range: Optional[str] = None
    # Additional metadata from tags
    title: Optional[str] = None
    frame_count: Optional[int] = None
    encoder: Optional[str] = None
    is_default: bool = True

    @property
    def resolution(self) -> str:
        """Get resolution as string (e.g., '1920x1080')."""
        return f"{self.width}x{self.height}"

    @property
    def aspect_ratio(self) -> float:
        """Calculate aspect ratio."""
        return self.width / self.height if self.height > 0 else 0.0


@dataclass
class AudioStream:
    """Information about an audio stream."""

    index: int
    codec: str
    codec_long: str
    profile: str
    language: str
    channels: int
    sample_rate: int
    bitrate: int
    duration: float
    # Additional metadata from tags
    title: Optional[str] = None
    channel_layout: Optional[str] = None
    frame_count: Optional[int] = None
    encoder: Optional[str] = None
    is_default: bool = True

    @property
    def channel_layout_name(self) -> str:
        """Get common channel layout name."""
        # Return actual channel_layout if available
        if self.channel_layout:
            return self.channel_layout

        # Otherwise, generate from channel count
        layouts = {
            1: "mono",
            2: "stereo",
            6: "5.1",
            8: "7.1",
        }
        return layouts.get(self.channels, f"{self.channels}ch")


@dataclass
class SubtitleStream:
    """Information about a subtitle stream."""

    index: int
    codec: str
    language: str
    title: Optional[str] = None
    forced: bool = False
    # Additional metadata
    frame_count: Optional[int] = None
    encoder: Optional[str] = None
    is_default: bool = True

    @property
    def display_name(self) -> str:
        """Get display name for subtitle track."""
        parts = [self.language.upper()]
        if self.title:
            parts.append(self.title)
        if self.forced:
            parts.append("(Forced)")
        return " - ".join(parts)


@dataclass
class MediaInfo:
    """Complete media file information."""

    format: FormatInfo
    video_streams: list[VideoStream]
    audio_streams: list[AudioStream]
    subtitle_streams: list[SubtitleStream]
    duration: float
    size: int
    bitrate: int

    @property
    def primary_video(self) -> Optional[VideoStream]:
        """Get the primary (first) video stream."""
        return self.video_streams[0] if self.video_streams else None

    @property
    def has_video(self) -> bool:
        """Check if media has video streams."""
        return len(self.video_streams) > 0

    @property
    def has_audio(self) -> bool:
        """Check if media has audio streams."""
        return len(self.audio_streams) > 0

    @property
    def has_subtitles(self) -> bool:
        """Check if media has subtitle streams."""
        return len(self.subtitle_streams) > 0

    def get_audio_by_language(self, language: str) -> Optional[AudioStream]:
        """Get audio stream by language code."""
        for stream in self.audio_streams:
            if stream.language.lower() == language.lower():
                return stream
        return None

    def get_subtitle_by_language(self, language: str) -> Optional[SubtitleStream]:
        """Get subtitle stream by language code."""
        for stream in self.subtitle_streams:
            if stream.language.lower() == language.lower():
                return stream
        return None
