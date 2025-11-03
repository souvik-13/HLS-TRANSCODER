"""
Media inspection and analysis using FFprobe.

This module provides functionality to inspect media files and extract
detailed information about video, audio, and subtitle streams.
"""

import asyncio
import json
from pathlib import Path
from typing import Optional

from ..models import (
    AudioStream,
    FormatInfo,
    MediaInfo,
    SubtitleStream,
    VideoStream,
)
from ..utils import MediaInspectionError, get_logger

logger = get_logger(__name__)


class MediaInspector:
    """
    Inspects media files using FFprobe to extract stream information.

    This class provides methods to analyze video files and extract:
    - Video stream information (codec, resolution, fps, bitrate)
    - Audio stream information (codec, channels, sample rate, language)
    - Subtitle stream information (format, language)
    - Container format and metadata
    """

    def __init__(self, ffprobe_path: str = "ffprobe"):
        """
        Initialize media inspector.

        Args:
            ffprobe_path: Path to ffprobe executable (default: "ffprobe")
        """
        self._ffprobe_path = ffprobe_path

    async def inspect(self, input_file: Path) -> MediaInfo:
        """
        Inspect media file and extract all stream information.

        Args:
            input_file: Path to media file to inspect

        Returns:
            MediaInfo object containing all stream details

        Raises:
            MediaInspectionError: If file doesn't exist or inspection fails
        """
        if not input_file.exists():
            raise MediaInspectionError(f"File not found: {input_file}")

        if not input_file.is_file():
            raise MediaInspectionError(f"Not a file: {input_file}")

        logger.info(f"Inspecting media file: {input_file.name}")

        try:
            # Run ffprobe to get JSON output
            probe_data = await self._run_ffprobe(input_file)

            # Parse format information
            format_info = self._parse_format(probe_data)

            # Parse streams
            video_streams = []
            audio_streams = []
            subtitle_streams = []

            for stream in probe_data.get("streams", []):
                codec_type = stream.get("codec_type", "").lower()

                if codec_type == "video":
                    video_stream = self._parse_video_stream(stream)
                    if video_stream:
                        video_streams.append(video_stream)

                elif codec_type == "audio":
                    audio_stream = self._parse_audio_stream(stream)
                    if audio_stream:
                        audio_streams.append(audio_stream)

                elif codec_type == "subtitle":
                    subtitle_stream = self._parse_subtitle_stream(stream)
                    if subtitle_stream:
                        subtitle_streams.append(subtitle_stream)

            # Create MediaInfo
            media_info = MediaInfo(
                format=format_info,
                video_streams=video_streams,
                audio_streams=audio_streams,
                subtitle_streams=subtitle_streams,
                duration=format_info.duration,
                size=format_info.size,
                bitrate=format_info.bitrate,
            )

            logger.info(f"Successfully inspected: {input_file.name}")
            logger.debug(
                f"Found {len(video_streams)} video, "
                f"{len(audio_streams)} audio, "
                f"{len(subtitle_streams)} subtitle streams"
            )

            return media_info

        except MediaInspectionError:
            raise
        except Exception as e:
            raise MediaInspectionError(f"Failed to inspect media file: {e}")

    async def _run_ffprobe(self, input_file: Path) -> dict:
        """
        Run ffprobe and return parsed JSON output.

        Args:
            input_file: Path to media file

        Returns:
            Dictionary containing ffprobe output

        Raises:
            MediaInspectionError: If ffprobe fails
        """
        try:
            process = await asyncio.create_subprocess_exec(
                self._ffprobe_path,
                "-v",
                "quiet",
                "-print_format",
                "json",
                "-show_format",
                "-show_streams",
                str(input_file),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            stdout, stderr = await process.communicate()

            if process.returncode != 0:
                error_msg = stderr.decode() if stderr else "Unknown error"
                raise MediaInspectionError(
                    f"FFprobe failed with code {process.returncode}: {error_msg}"
                )

            # Parse JSON output
            probe_data = json.loads(stdout.decode())
            return probe_data

        except json.JSONDecodeError as e:
            raise MediaInspectionError(f"Failed to parse FFprobe output: {e}")
        except Exception as e:
            raise MediaInspectionError(f"FFprobe execution failed: {e}")

    def _parse_duration_string(self, duration_str: str) -> float:
        """
        Parse duration string in format HH:MM:SS.microseconds to seconds.

        Args:
            duration_str: Duration string (e.g., "02:08:21.648000000")

        Returns:
            Duration in seconds as float
        """
        if not duration_str:
            return 0.0

        try:
            # Format: HH:MM:SS.microseconds
            parts = duration_str.split(":")
            if len(parts) != 3:
                return 0.0

            hours = int(parts[0])
            minutes = int(parts[1])
            seconds = float(parts[2])

            return hours * 3600 + minutes * 60 + seconds

        except (ValueError, IndexError):
            logger.warning(f"Failed to parse duration string: {duration_str}")
            return 0.0

    def _get_tag_value(self, tags: dict, tag_name: str, default: str = "") -> str:
        """
        Get tag value, checking _STATISTICS_TAGS for valid tag names.

        Supports pattern matching for tags with language suffixes:
        - BPS matches BPS, BPS-eng, BPS_HINDI, etc.
        - NUMBER_OF_FRAMES matches NUMBER_OF_FRAMES, NUMBER_OF_FRAMES-eng, etc.

        Args:
            tags: Dictionary of tags from stream/format
            tag_name: Name of tag to retrieve (e.g., "BPS", "DURATION")
            default: Default value if tag not found

        Returns:
            Tag value as string, or default if not found
        """
        # Check if _STATISTICS_TAGS lists available tags
        stats_tags = tags.get("_STATISTICS_TAGS", "")
        if stats_tags:
            available_tags = stats_tags.split()

            # First try exact match
            if tag_name in available_tags:
                return tags.get(tag_name, default)

            # Try pattern match: find tags that start with tag_name
            # Handle cases like BPS-eng, BPS_HINDI, NUMBER_OF_FRAMES-eng
            matching_tags = [
                tag
                for tag in available_tags
                if tag.startswith(tag_name)
                and (len(tag) == len(tag_name) or tag[len(tag_name)] in ["-", "_", "."])
            ]

            if matching_tags:
                # Return the first matching tag value
                # In multi-language scenarios, this will get the first available
                return tags.get(matching_tags[0], default)

            return default

        # Fallback: try to get tag directly (for non-MKV files)
        return tags.get(tag_name, default)

    def _parse_format(self, probe_data: dict) -> FormatInfo:
        """
        Parse format information from ffprobe data.

        Args:
            probe_data: FFprobe JSON output

        Returns:
            FormatInfo object
        """
        format_data = probe_data.get("format", {})
        format_tags = format_data.get("tags", {})

        # Extract encoder information
        encoder = (
            format_tags.get("ENCODER")
            or format_tags.get("encoder")
            or format_tags.get("_STATISTICS_WRITING_APP")
            or ""
        )

        # Extract creation time
        creation_time = (
            format_tags.get("creation_time")
            or format_tags.get("_STATISTICS_WRITING_DATE_UTC")
            or ""
        )

        return FormatInfo(
            format_name=format_data.get("format_name", ""),
            format_long_name=format_data.get("format_long_name", ""),
            duration=float(format_data.get("duration", 0.0)),
            size=int(format_data.get("size", 0)),
            bitrate=int(format_data.get("bit_rate", 0)),
            encoder=encoder if encoder else None,
            creation_time=creation_time if creation_time else None,
        )

    def _parse_video_stream(self, stream: dict) -> Optional[VideoStream]:
        """
        Parse video stream information.

        Args:
            stream: Stream data from ffprobe

        Returns:
            VideoStream object or None if parsing fails
        """
        try:
            # Get basic properties
            index = stream.get("index", 0)
            codec_name = stream.get("codec_name", "unknown")
            codec_long_name = stream.get("codec_long_name", "")
            profile = stream.get("profile", "")
            width = stream.get("width", 0)
            height = stream.get("height", 0)

            # Parse frame rate (try r_frame_rate, then avg_frame_rate)
            fps_str = stream.get("r_frame_rate") or stream.get("avg_frame_rate", "0/1")
            try:
                num, denom = map(int, fps_str.split("/"))
                fps = num / denom if denom != 0 else 0.0
            except (ValueError, ZeroDivisionError):
                fps = 0.0

            # Get tags for fallback values
            tags = stream.get("tags", {})

            # Get bitrate with fallback to tags (using _STATISTICS_TAGS)
            bitrate = int(stream.get("bit_rate", 0))
            if bitrate == 0:
                # Try BPS from tags (MKV files often have this)
                bps_str = self._get_tag_value(tags, "BPS", "0")
                try:
                    bitrate = int(bps_str)
                except ValueError:
                    bitrate = 0

            # Get pixel format
            pix_fmt = stream.get("pix_fmt", "")

            # Get color space info
            color_space = stream.get("color_space", "")
            color_range = stream.get("color_range", "")

            # Get duration with fallback to tags (using _STATISTICS_TAGS)
            duration_str = stream.get("duration")
            if duration_str:
                duration = float(duration_str)
            else:
                # Try parsing from tags.DURATION (format: HH:MM:SS.microseconds)
                duration_tag = self._get_tag_value(tags, "DURATION", "")
                duration = self._parse_duration_string(duration_tag)

            # Extract additional metadata from tags
            title = tags.get("title", "")

            # Get frame count from tags (using _STATISTICS_TAGS)
            frame_count = None
            frame_count_str = self._get_tag_value(tags, "NUMBER_OF_FRAMES", "")
            if frame_count_str:
                try:
                    frame_count = int(frame_count_str)
                except ValueError:
                    pass

            # Get encoder info
            encoder = tags.get("_STATISTICS_WRITING_APP") or tags.get("encoder", "")

            # Check if this is the default stream
            disposition = stream.get("disposition", {})
            is_default = bool(disposition.get("default", 1))

            return VideoStream(
                index=index,
                codec=codec_name,
                codec_long=codec_long_name,
                profile=profile,
                width=width,
                height=height,
                fps=fps,
                bitrate=bitrate,
                pix_fmt=pix_fmt,
                color_space=color_space,
                color_range=color_range,
                duration=duration,
                title=title if title else None,
                frame_count=frame_count,
                encoder=encoder if encoder else None,
                is_default=is_default,
            )

        except Exception as e:
            logger.warning(f"Failed to parse video stream: {e}")
            return None

    def _parse_audio_stream(self, stream: dict) -> Optional[AudioStream]:
        """
        Parse audio stream information.

        Args:
            stream: Stream data from ffprobe

        Returns:
            AudioStream object or None if parsing fails
        """
        try:
            # Get basic properties
            index = stream.get("index", 0)
            codec_name = stream.get("codec_name", "unknown")
            codec_long_name = stream.get("codec_long_name", "")
            profile = stream.get("profile", "")

            # Get tags for fallback values
            tags = stream.get("tags", {})

            # Get audio properties
            sample_rate = int(stream.get("sample_rate", 0))
            channels = int(stream.get("channels", 0))
            channel_layout = stream.get("channel_layout", "")

            # Get bitrate with fallback to tags (using _STATISTICS_TAGS)
            bitrate = int(stream.get("bit_rate", 0))
            if bitrate == 0:
                # Try BPS from tags
                bps_str = self._get_tag_value(tags, "BPS", "0")
                try:
                    bitrate = int(bps_str)
                except ValueError:
                    bitrate = 0

            # Get language (und = undefined)
            language = tags.get("language", "und")

            # Get title
            title = tags.get("title", "")

            # Get duration with fallback to tags (using _STATISTICS_TAGS)
            duration_str = stream.get("duration")
            if duration_str:
                duration = float(duration_str)
            else:
                # Try parsing from tags.DURATION
                duration_tag = self._get_tag_value(tags, "DURATION", "")
                duration = self._parse_duration_string(duration_tag)

            # Extract additional metadata from tags
            title = tags.get("title", "")

            # Get frame count from tags (using _STATISTICS_TAGS)
            frame_count = None
            frame_count_str = self._get_tag_value(tags, "NUMBER_OF_FRAMES", "")
            if frame_count_str:
                try:
                    frame_count = int(frame_count_str)
                except ValueError:
                    pass

            # Get encoder info
            encoder = tags.get("_STATISTICS_WRITING_APP") or tags.get("encoder", "")

            # Check if this is the default stream
            disposition = stream.get("disposition", {})
            is_default = bool(disposition.get("default", 1))

            return AudioStream(
                index=index,
                codec=codec_name,
                codec_long=codec_long_name,
                profile=profile,
                language=language,
                channels=channels,
                channel_layout=channel_layout if channel_layout else None,
                sample_rate=sample_rate,
                bitrate=bitrate,
                duration=duration,
                title=title if title else None,
                frame_count=frame_count,
                encoder=encoder if encoder else None,
                is_default=is_default,
            )

        except Exception as e:
            logger.warning(f"Failed to parse audio stream: {e}")
            return None

    def _parse_subtitle_stream(self, stream: dict) -> Optional[SubtitleStream]:
        """
        Parse subtitle stream information.

        Args:
            stream: Stream data from ffprobe

        Returns:
            SubtitleStream object or None if parsing fails
        """
        try:
            # Get basic properties
            index = stream.get("index", 0)
            codec_name = stream.get("codec_name", "unknown")
            codec_long_name = stream.get("codec_long_name", "")

            # Get language and title from tags
            tags = stream.get("tags", {})
            language = tags.get("language", "und")
            title = tags.get("title", "")

            # Check disposition flags
            disposition = stream.get("disposition", {})
            forced = bool(disposition.get("forced", 0))
            is_default = bool(disposition.get("default", 1))

            # Get frame count from tags (using _STATISTICS_TAGS)
            frame_count = None
            frame_count_str = self._get_tag_value(tags, "NUMBER_OF_FRAMES", "")
            if frame_count_str:
                try:
                    frame_count = int(frame_count_str)
                except ValueError:
                    pass

            # Get encoder info
            encoder = tags.get("_STATISTICS_WRITING_APP") or tags.get("encoder", "")

            return SubtitleStream(
                index=index,
                codec=codec_name,
                language=language,
                title=title if title else None,
                forced=forced,
                frame_count=frame_count,
                encoder=encoder if encoder else None,
                is_default=is_default,
            )

        except Exception as e:
            logger.warning(f"Failed to parse subtitle stream: {e}")
            return None

    def validate_for_transcoding(self, media_info: MediaInfo) -> list[str]:
        """
        Validate media file for transcoding compatibility.

        Args:
            media_info: MediaInfo object to validate

        Returns:
            List of validation warnings (empty if all checks pass)
        """
        warnings = []

        # Check for video streams
        if not media_info.has_video:
            warnings.append("No video streams found")

        # Check video properties
        if media_info.primary_video:
            video = media_info.primary_video

            # Check resolution
            if video.width == 0 or video.height == 0:
                warnings.append("Invalid video resolution")

            # Check frame rate
            if video.fps == 0:
                warnings.append("Invalid or missing frame rate")

            # Check codec
            unsupported_codecs = ["av1", "vp9"]  # Example
            if video.codec in unsupported_codecs:
                warnings.append(f"Video codec '{video.codec}' may have limited hardware support")

        # Check for audio streams
        if not media_info.has_audio:
            warnings.append("No audio streams found")

        # Check file size
        if media_info.size == 0:
            warnings.append("File size is 0 bytes")

        # Check duration
        if media_info.duration == 0:
            warnings.append("Duration is 0 seconds")

        return warnings


# Global instance
_inspector: Optional[MediaInspector] = None


def get_media_inspector() -> MediaInspector:
    """
    Get global media inspector instance.

    Returns:
        MediaInspector instance
    """
    global _inspector
    if _inspector is None:
        _inspector = MediaInspector()
    return _inspector
