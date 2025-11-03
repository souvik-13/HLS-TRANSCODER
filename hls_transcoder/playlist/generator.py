"""
HLS playlist generation module.

This module handles the generation of HLS master playlists, variant playlists,
and metadata files for transcoded video content.
"""

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Optional

from ..models import AudioStream, SubtitleStream, VideoStream
from ..utils import get_logger

logger = get_logger(__name__)


@dataclass
class PlaylistConfig:
    """Configuration for playlist generation."""

    output_dir: Path
    segment_duration: int = 6  # seconds
    version: int = 7  # HLS version
    allow_cache: bool = True
    target_duration: int = 6


@dataclass
class VideoVariantInfo:
    """Information about a video variant for playlist generation."""

    quality: str
    width: int
    height: int
    bitrate: int  # in kbps
    framerate: float
    codecs: str
    playlist_path: Path
    segment_count: int
    has_embedded_audio: bool = False  # True if variant contains muxed audio

    @property
    def bandwidth(self) -> int:
        """Calculate bandwidth in bits per second."""
        return self.bitrate * 1000

    @property
    def average_bandwidth(self) -> int:
        """Calculate average bandwidth (typically 90% of peak)."""
        return int(self.bitrate * 900)  # 90% of kbps * 1000 = bps * 0.9

    @property
    def resolution(self) -> str:
        """Get resolution string."""
        return f"{self.width}x{self.height}"


@dataclass
class AudioTrackInfo:
    """Information about an audio track for playlist generation."""

    name: str
    language: str
    channels: int
    sample_rate: int
    bitrate: int  # in kbps
    codecs: str
    playlist_path: Path
    is_default: bool = False

    @property
    def bandwidth(self) -> int:
        """Calculate bandwidth in bits per second."""
        return self.bitrate * 1000

    @property
    def group_id(self) -> str:
        """
        Get audio group ID.

        All audio tracks must be in the same group for proper player switching.
        Different languages and bitrates are differentiated by NAME and LANGUAGE attributes.
        """
        return "audio"

    @property
    def channel_layout(self) -> str:
        """Get channel layout description."""
        layouts = {
            1: "MONO",
            2: "STEREO",
            6: "5.1",
            8: "7.1",
        }
        return layouts.get(self.channels, f"{self.channels}CH")


@dataclass
class SubtitleTrackInfo:
    """Information about a subtitle track for playlist generation."""

    name: str
    language: str
    file_path: Path
    is_default: bool = False
    forced: bool = False

    @property
    def group_id(self) -> str:
        """Get subtitle group ID."""
        return "subtitles"


class PlaylistGenerator:
    """
    Generates HLS playlists for video streaming.

    This class creates the master playlist (master.m3u8) that references
    all video variants, audio tracks, and subtitles. It also generates
    metadata files for the transcoded content.
    """

    def __init__(
        self,
        output_dir: Path,
        config: Optional[PlaylistConfig] = None,
    ):
        """
        Initialize the playlist generator.

        Args:
            output_dir: Directory where playlists will be generated
            config: Optional playlist configuration
        """
        self.output_dir = Path(output_dir)
        self.config = config or PlaylistConfig(output_dir=self.output_dir)

        # Ensure output directory exists
        self.output_dir.mkdir(parents=True, exist_ok=True)

        logger.info(f"Initialized PlaylistGenerator for {self.output_dir}")

    def generate_master_playlist(
        self,
        video_variants: list[VideoVariantInfo],
        audio_tracks: Optional[list[AudioTrackInfo]] = None,
        subtitle_tracks: Optional[list[SubtitleTrackInfo]] = None,
    ) -> Path:
        """
        Generate the master HLS playlist.

        This method creates an HLS master playlist that properly handles:
        - Multiple video quality variants (720p, 1080p, etc.)
        - Multiple audio tracks (different languages and/or bitrates)
        - Multiple subtitle tracks (different languages)

        All audio tracks are grouped in a single "audio" group, allowing players
        to switch between different languages and bitrates dynamically. The first
        audio track is marked as default.

        All subtitle tracks are grouped in a single "subtitles" group, allowing
        players to select between different languages.

        Args:
            video_variants: List of video variant information (required, min 1)
            audio_tracks: Optional list of audio track information
                         (can include multiple languages/bitrates)
            subtitle_tracks: Optional list of subtitle track information
                            (can include multiple languages)

        Returns:
            Path to the generated master playlist

        Raises:
            ValueError: If no video variants are provided

        Example:
            Multiple audio tracks (different languages):
            - English 128k (default)
            - Spanish 128k
            - French 128k

            Multiple audio tracks (same language, different qualities):
            - English 96k
            - English 128k (default)
            - English 192k

            Multiple subtitle tracks:
            - English (default)
            - Spanish
            - French (forced)
        """
        if not video_variants:
            raise ValueError("At least one video variant is required")

        logger.info("Generating master playlist...")

        lines = [
            "#EXTM3U",
            f"#EXT-X-VERSION:{self.config.version}",
            "",
        ]

        # Add audio tracks
        if audio_tracks:
            lines.append("# Audio tracks")
            # Sort audio tracks: default first, then by language, then by bitrate (descending)
            sorted_audio = sorted(
                audio_tracks, key=lambda t: (not t.is_default, t.language, -t.bitrate)
            )
            for track in sorted_audio:
                lines.extend(self._generate_audio_entry(track))
            lines.append("")

            logger.debug(f"Added {len(audio_tracks)} audio tracks to master playlist")
            for track in sorted_audio:
                logger.debug(
                    f"  - {track.name} ({track.language}) @ {track.bitrate}kbps, default={track.is_default}"
                )

        # Add subtitle tracks
        if subtitle_tracks:
            lines.append("# Subtitle tracks")
            # Sort subtitle tracks: default first, then forced, then by language
            sorted_subs = sorted(
                subtitle_tracks, key=lambda t: (not t.is_default, not t.forced, t.language)
            )
            for track in sorted_subs:
                lines.extend(self._generate_subtitle_entry(track))
            lines.append("")

            logger.debug(f"Added {len(subtitle_tracks)} subtitle tracks to master playlist")
            for track in sorted_subs:
                logger.debug(
                    f"  - {track.name} ({track.language}), default={track.is_default}, forced={track.forced}"
                )

        # Add video variants
        lines.append("# Video variants")
        # Sort variants by bitrate (highest first)
        sorted_variants = sorted(video_variants, key=lambda v: v.bitrate, reverse=True)

        # All audio tracks use the same group ID
        audio_group_id = "audio" if audio_tracks else None

        for variant in sorted_variants:
            lines.extend(
                self._generate_variant_entry(
                    variant,
                    has_audio=bool(audio_tracks),
                    has_subtitles=bool(subtitle_tracks),
                    audio_group_id=audio_group_id,
                )
            )

        # Write master playlist
        master_path = self.output_dir / "master.m3u8"
        content = "\n".join(lines) + "\n"
        master_path.write_text(content, encoding="utf-8")

        logger.info(f"Generated master playlist: {master_path}")
        logger.info(f"  - {len(video_variants)} video variants")
        logger.info(f"  - {len(audio_tracks or [])} audio tracks")
        logger.info(f"  - {len(subtitle_tracks or [])} subtitle tracks")

        return master_path

    def _generate_audio_entry(self, track: AudioTrackInfo) -> list[str]:
        """Generate master playlist entry for an audio track."""
        # Make playlist path relative to master playlist
        playlist_rel = self._get_relative_path(track.playlist_path)

        # Build attributes
        attrs = [
            "TYPE=AUDIO",
            f'GROUP-ID="{track.group_id}"',
            f'NAME="{track.name}"',
            f'LANGUAGE="{track.language}"',
            f'URI="{playlist_rel}"',
        ]

        if track.is_default:
            attrs.append("DEFAULT=YES")
            attrs.append("AUTOSELECT=YES")
        else:
            attrs.append("DEFAULT=NO")
            attrs.append("AUTOSELECT=NO")

        return [f"#EXT-X-MEDIA:{','.join(attrs)}"]

    def _generate_subtitle_entry(self, track: SubtitleTrackInfo) -> list[str]:
        """Generate master playlist entry for a subtitle track."""
        # Make file path relative to master playlist
        file_rel = self._get_relative_path(track.file_path)

        # Build attributes
        attrs = [
            "TYPE=SUBTITLES",
            f'GROUP-ID="{track.group_id}"',
            f'NAME="{track.name}"',
            f'LANGUAGE="{track.language}"',
            f'URI="{file_rel}"',
        ]

        if track.is_default:
            attrs.append("DEFAULT=YES")
            attrs.append("AUTOSELECT=YES")
        else:
            attrs.append("DEFAULT=NO")

        if track.forced:
            attrs.append("FORCED=YES")

        return [f"#EXT-X-MEDIA:{','.join(attrs)}"]

    def _generate_variant_entry(
        self,
        variant: VideoVariantInfo,
        has_audio: bool = False,
        has_subtitles: bool = False,
        audio_group_id: Optional[str] = None,
    ) -> list[str]:
        """Generate master playlist entry for a video variant."""
        # Make playlist path relative to master playlist
        playlist_rel = self._get_relative_path(variant.playlist_path)

        # Calculate total bandwidth (video + typical audio)
        # Add ~128kbps for audio if audio tracks exist
        total_bandwidth = variant.bandwidth
        average_bandwidth = variant.average_bandwidth
        if has_audio and not variant.has_embedded_audio:
            total_bandwidth += 128000  # Add typical audio bitrate
            average_bandwidth += 115200  # Add typical average audio bitrate

        # Build codecs string - only include audio codec if variant has embedded audio
        codecs = variant.codecs
        if has_audio and not variant.has_embedded_audio:
            # Video-only variant, remove audio codec if present
            if "," in codecs:
                codecs = codecs.split(",")[0]  # Keep only video codec

        # Build stream info attributes
        attrs = [
            f"BANDWIDTH={total_bandwidth}",
            f"AVERAGE-BANDWIDTH={average_bandwidth}",
            f"RESOLUTION={variant.resolution}",
            f"FRAME-RATE={variant.framerate:.3f}",
            f'CODECS="{codecs}"',
        ]

        if has_audio and not variant.has_embedded_audio:
            # Reference separate audio group
            attrs.append(f'AUDIO="{audio_group_id or "audio"}"')

        if has_subtitles:
            attrs.append('SUBTITLES="subtitles"')

        lines = [
            f"#EXT-X-STREAM-INF:{','.join(attrs)}",
            playlist_rel,
        ]

        return lines

    def _get_relative_path(self, path: Path) -> str:
        """Get path relative to output directory."""
        try:
            return str(path.relative_to(self.output_dir))
        except ValueError:
            # If path is not relative to output_dir, use absolute path
            return str(path)

    def generate_metadata(
        self,
        video_variants: list[VideoVariantInfo],
        audio_tracks: Optional[list[AudioTrackInfo]] = None,
        subtitle_tracks: Optional[list[SubtitleTrackInfo]] = None,
        source_info: Optional[dict] = None,
        transcoding_info: Optional[dict] = None,
    ) -> Path:
        """
        Generate metadata JSON file for the transcoded content.

        Args:
            video_variants: List of video variant information
            audio_tracks: Optional list of audio track information
            subtitle_tracks: Optional list of subtitle track information
            source_info: Optional source file information
            transcoding_info: Optional transcoding process information

        Returns:
            Path to the generated metadata file
        """
        logger.info("Generating metadata file...")

        metadata = {
            "version": "1.0",
            "generated_by": "HLS Transcoder",
            "master_playlist": "master.m3u8",
            "video": {
                "variants": [
                    {
                        "quality": v.quality,
                        "resolution": v.resolution,
                        "width": v.width,
                        "height": v.height,
                        "bitrate": v.bitrate,
                        "framerate": v.framerate,
                        "codecs": v.codecs,
                        "playlist": str(self._get_relative_path(v.playlist_path)),
                        "segments": v.segment_count,
                    }
                    for v in video_variants
                ],
                "count": len(video_variants),
            },
        }

        # Add audio information
        if audio_tracks:
            metadata["audio"] = {
                "tracks": [
                    {
                        "name": a.name,
                        "language": a.language,
                        "channels": a.channels,
                        "channel_layout": a.channel_layout,
                        "sample_rate": a.sample_rate,
                        "bitrate": a.bitrate,
                        "codecs": a.codecs,
                        "playlist": str(self._get_relative_path(a.playlist_path)),
                        "default": a.is_default,
                    }
                    for a in audio_tracks
                ],
                "count": len(audio_tracks),
            }

        # Add subtitle information
        if subtitle_tracks:
            metadata["subtitles"] = {
                "tracks": [
                    {
                        "name": s.name,
                        "language": s.language,
                        "file": str(self._get_relative_path(s.file_path)),
                        "default": s.is_default,
                        "forced": s.forced,
                    }
                    for s in subtitle_tracks
                ],
                "count": len(subtitle_tracks),
            }

        # Add source information if provided
        if source_info:
            metadata["source"] = source_info

        # Add transcoding information if provided
        if transcoding_info:
            metadata["transcoding"] = transcoding_info

        # Write metadata file
        metadata_path = self.output_dir / "metadata.json"
        with metadata_path.open("w", encoding="utf-8") as f:
            json.dump(metadata, f, indent=2, ensure_ascii=False)

        logger.info(f"Generated metadata file: {metadata_path}")

        return metadata_path

    def validate_playlists(self) -> tuple[bool, list[str]]:
        """
        Validate generated playlists.

        Checks for:
        - Master playlist existence and format
        - Required headers and variants
        - Referenced playlist files existence
        - Multiple audio/subtitle tracks are properly configured

        Returns:
            Tuple of (is_valid, errors) where errors is a list of error messages
        """
        errors = []

        # Check master playlist exists
        master_path = self.output_dir / "master.m3u8"
        if not master_path.exists():
            errors.append("Master playlist (master.m3u8) not found")
            return False, errors

        # Parse master playlist
        try:
            content = master_path.read_text(encoding="utf-8")
            lines = [line.strip() for line in content.split("\n") if line.strip()]

            # Check for required header
            if not lines or lines[0] != "#EXTM3U":
                errors.append("Master playlist missing #EXTM3U header")

            # Check for at least one variant
            has_variant = any(line.startswith("#EXT-X-STREAM-INF:") for line in lines)
            if not has_variant:
                errors.append("Master playlist has no video variants")

            # Validate referenced playlists exist
            for i, line in enumerate(lines):
                if line.startswith("#EXT-X-STREAM-INF:"):
                    # Next line should be the playlist path
                    if i + 1 < len(lines):
                        playlist_path = self.output_dir / lines[i + 1]
                        if not playlist_path.exists():
                            errors.append(f"Referenced playlist not found: {lines[i + 1]}")

                elif line.startswith("#EXT-X-MEDIA:") and "URI=" in line:
                    # Extract URI from media tag
                    uri_start = line.find('URI="') + 5
                    uri_end = line.find('"', uri_start)
                    if uri_start > 4 and uri_end > uri_start:
                        uri = line[uri_start:uri_end]
                        media_path = self.output_dir / uri
                        if not media_path.exists():
                            errors.append(f"Referenced media file not found: {uri}")

        except Exception as e:
            errors.append(f"Error parsing master playlist: {e}")

        return len(errors) == 0, errors

    @staticmethod
    def validate_audio_tracks(audio_tracks: list[AudioTrackInfo]) -> tuple[bool, list[str]]:
        """
        Validate audio track configuration.

        Checks for:
        - At least one track marked as default
        - No duplicate language+bitrate combinations
        - Valid language codes

        Args:
            audio_tracks: List of audio tracks to validate

        Returns:
            Tuple of (is_valid, warnings) where warnings is a list of potential issues
        """
        if not audio_tracks:
            return True, []

        warnings = []

        # Check for default track
        default_tracks = [t for t in audio_tracks if t.is_default]
        if not default_tracks:
            warnings.append("No audio track marked as default, players may not auto-select")
        elif len(default_tracks) > 1:
            warnings.append(
                f"Multiple audio tracks marked as default ({len(default_tracks)}), only first will be used"
            )

        # Check for duplicate language+bitrate combinations
        seen = set()
        for track in audio_tracks:
            key = (track.language, track.bitrate, track.channels)
            if key in seen:
                warnings.append(
                    f"Duplicate audio track: {track.language} @ {track.bitrate}kbps with {track.channels} channels"
                )
            seen.add(key)

        # Check for valid language codes (basic check)
        for track in audio_tracks:
            if track.language == "und":
                warnings.append(f"Audio track '{track.name}' has undefined language code (und)")

        return len(warnings) == 0, warnings

    @staticmethod
    def validate_subtitle_tracks(
        subtitle_tracks: list[SubtitleTrackInfo],
    ) -> tuple[bool, list[str]]:
        """
        Validate subtitle track configuration.

        Checks for:
        - No duplicate languages
        - Valid language codes
        - File existence

        Args:
            subtitle_tracks: List of subtitle tracks to validate

        Returns:
            Tuple of (is_valid, warnings) where warnings is a list of potential issues
        """
        if not subtitle_tracks:
            return True, []

        warnings = []

        # Check for duplicate languages
        seen_languages = set()
        for track in subtitle_tracks:
            if track.language in seen_languages:
                warnings.append(f"Duplicate subtitle language: {track.language}")
            seen_languages.add(track.language)

        # Check for valid language codes
        for track in subtitle_tracks:
            if track.language == "und":
                warnings.append(f"Subtitle track '{track.name}' has undefined language code (und)")

        # Check file existence
        for track in subtitle_tracks:
            if not track.file_path.exists():
                warnings.append(f"Subtitle file not found: {track.file_path}")

        return len(warnings) == 0, warnings


# Convenience functions


def create_video_variant_info(
    quality: str,
    width: int,
    height: int,
    bitrate: int,
    framerate: float,
    playlist_path: Path,
    segment_count: int,
    codec: str = "h264",
    has_embedded_audio: bool = False,
) -> VideoVariantInfo:
    """
    Create a VideoVariantInfo instance.

    Args:
        quality: Quality label (e.g., "1080p", "720p")
        width: Video width in pixels
        height: Video height in pixels
        bitrate: Video bitrate in kbps
        framerate: Video frame rate
        playlist_path: Path to the variant playlist file
        segment_count: Number of segments in the playlist
        codec: Video codec (default: "h264")
        has_embedded_audio: Whether variant has embedded audio (default: False for video-only)

    Returns:
        VideoVariantInfo instance
    """
    # Generate codecs string
    # For video-only variants (typical HLS setup), only include video codec
    # For muxed variants, include both video and audio codecs
    if codec == "h264":
        video_codec = "avc1.640028"  # H.264 High Profile
        codecs = f"{video_codec},mp4a.40.2" if has_embedded_audio else video_codec
    elif codec == "h265" or codec == "hevc":
        video_codec = "hvc1.1.6.L120.90"  # HEVC Main Profile
        codecs = f"{video_codec},mp4a.40.2" if has_embedded_audio else video_codec
    else:
        codecs = f"{codec},mp4a.40.2" if has_embedded_audio else codec

    return VideoVariantInfo(
        quality=quality,
        width=width,
        height=height,
        bitrate=bitrate,
        framerate=framerate,
        codecs=codecs,
        playlist_path=playlist_path,
        segment_count=segment_count,
        has_embedded_audio=has_embedded_audio,
    )


def create_audio_track_info(
    name: str,
    language: str,
    channels: int,
    sample_rate: int,
    bitrate: int,
    playlist_path: Path,
    is_default: bool = False,
    codec: str = "aac",
) -> AudioTrackInfo:
    """
    Create an AudioTrackInfo instance.

    Args:
        name: Track name (human-readable, e.g., "Hindi", "English 192k", "Spanish 5.1")
        language: Language code (e.g., "eng", "spa", "hin")
        channels: Number of audio channels
        sample_rate: Sample rate in Hz
        bitrate: Audio bitrate in kbps
        playlist_path: Path to the audio playlist file
        is_default: Whether this is the default audio track
        codec: Audio codec (default: "aac")

    Returns:
        AudioTrackInfo instance

    Note:
        For multiple bitrates of the same language, include bitrate in name:
        - "English 128k", "English 192k"
        For multiple channel layouts, include that:
        - "Hindi Stereo", "Hindi 5.1"
    """
    # Generate codecs string
    if codec == "aac":
        codecs = "mp4a.40.2"  # AAC-LC
    else:
        codecs = codec

    return AudioTrackInfo(
        name=name,
        language=language,
        channels=channels,
        sample_rate=sample_rate,
        bitrate=bitrate,
        codecs=codecs,
        playlist_path=playlist_path,
        is_default=is_default,
    )


def create_subtitle_track_info(
    name: str,
    language: str,
    file_path: Path,
    is_default: bool = False,
    forced: bool = False,
) -> SubtitleTrackInfo:
    """
    Create a SubtitleTrackInfo instance.

    Args:
        name: Track name
        language: Language code (e.g., "eng", "spa")
        file_path: Path to the subtitle file
        is_default: Whether this is the default subtitle track
        forced: Whether this is a forced subtitle track

    Returns:
        SubtitleTrackInfo instance
    """
    return SubtitleTrackInfo(
        name=name,
        language=language,
        file_path=file_path,
        is_default=is_default,
        forced=forced,
    )


def generate_playlists(
    output_dir: Path,
    video_variants: list[VideoVariantInfo],
    audio_tracks: Optional[list[AudioTrackInfo]] = None,
    subtitle_tracks: Optional[list[SubtitleTrackInfo]] = None,
    source_info: Optional[dict] = None,
    transcoding_info: Optional[dict] = None,
) -> tuple[Path, Path]:
    """
    Convenience function to generate both master playlist and metadata.

    Args:
        output_dir: Output directory
        video_variants: List of video variants
        audio_tracks: Optional list of audio tracks
        subtitle_tracks: Optional list of subtitle tracks
        source_info: Optional source file information
        transcoding_info: Optional transcoding information

    Returns:
        Tuple of (master_playlist_path, metadata_path)
    """
    generator = PlaylistGenerator(output_dir)

    master_path = generator.generate_master_playlist(
        video_variants=video_variants,
        audio_tracks=audio_tracks,
        subtitle_tracks=subtitle_tracks,
    )

    metadata_path = generator.generate_metadata(
        video_variants=video_variants,
        audio_tracks=audio_tracks,
        subtitle_tracks=subtitle_tracks,
        source_info=source_info,
        transcoding_info=transcoding_info,
    )

    return master_path, metadata_path
