"""
Audio extraction and transcoding for HLS output.

This module provides audio extraction with AAC encoding, multi-track support,
and HLS audio playlist generation for adaptive streaming.
"""

import asyncio
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, List, Optional

from ..executor import AsyncFFmpegProcess
from ..models import AudioStream
from ..utils import FFmpegError, TranscodingError, get_logger

logger = get_logger(__name__)


@dataclass
class AudioQuality:
    """Audio quality preset configuration."""

    name: str  # e.g., "high", "medium", "low"
    bitrate: int  # Target bitrate in kbps
    sample_rate: int  # Sample rate in Hz
    channels: int  # Number of channels (1=mono, 2=stereo, 6=5.1)

    @property
    def channel_layout(self) -> str:
        """Get channel layout name."""
        layouts = {
            1: "mono",
            2: "stereo",
            6: "5.1",
            8: "7.1",
        }
        return layouts.get(self.channels, f"{self.channels}ch")


# Standard audio quality presets
# Note: channels and sample_rate can be overridden by config
AUDIO_QUALITY_PRESETS = {
    "high": AudioQuality("high", 192, 48000, 2),
    "medium": AudioQuality("medium", 128, 48000, 2),
    "low": AudioQuality("low", 96, 44100, 2),
}


@dataclass
class AudioExtractionOptions:
    """Options for audio extraction."""

    audio_stream: AudioStream
    output_path: Path
    quality: AudioQuality
    segment_duration: int = 10  # HLS segment duration in seconds (default 10 for audio)
    copy_if_possible: bool = True  # Use stream copy if source is compatible (no re-encoding)


class AudioExtractor:
    """
    Handles audio extraction and transcoding for HLS output.

    Supports multi-track audio extraction, AAC encoding, and HLS-compatible
    audio playlist generation with language tags.
    """

    def __init__(
        self,
        input_file: Path,
        output_dir: Path,
    ):
        """
        Initialize audio extractor.

        Args:
            input_file: Source media file
            output_dir: Output directory for audio files
        """
        self.input_file = input_file
        self.output_dir = output_dir

        # Create output directory
        self.output_dir.mkdir(parents=True, exist_ok=True)

        logger.info(f"Initialized AudioExtractor for {input_file.name}")

    async def extract(
        self,
        audio_stream: AudioStream,
        quality: Optional[AudioQuality] = None,
        progress_callback: Optional[Callable[[float, Optional[float]], None]] = None,
        timeout: Optional[float] = None,
        segment_duration: int = 10,
        copy_if_possible: bool = True,
    ) -> Path:
        """
        Extract and transcode audio stream to AAC with HLS output.

        Args:
            audio_stream: Source audio stream to extract
            quality: Target quality preset (default: medium)
            progress_callback: Callback for progress updates (0.0 to 1.0, speed multiplier)
            timeout: Maximum extraction time in seconds
            segment_duration: HLS segment duration in seconds (default: 10)
            copy_if_possible: Use stream copy if source is compatible (default: True)

        Returns:
            Path to output playlist file

        Raises:
            TranscodingError: If extraction fails
        """
        if quality is None:
            quality = AUDIO_QUALITY_PRESETS["medium"]

        logger.info(
            f"Extracting audio track {audio_stream.index} "
            f"({audio_stream.language}) at {quality.bitrate}kbps"
        )

        # Create output paths
        track_name = self._get_track_name(audio_stream, quality)
        output_path = self.output_dir / f"{track_name}.m3u8"
        segment_pattern = self.output_dir / f"{track_name}_%03d.ts"

        # Build extraction options
        options = AudioExtractionOptions(
            audio_stream=audio_stream,
            output_path=output_path,
            quality=quality,
            segment_duration=segment_duration,
            copy_if_possible=copy_if_possible,
        )

        try:
            # Build FFmpeg command
            command = self._build_command(options, segment_pattern)

            # Execute extraction
            process = AsyncFFmpegProcess(
                command=command,
                timeout=timeout,
                progress_callback=progress_callback,
            )

            await process.run()

            # Verify output was created
            if not output_path.exists():
                raise TranscodingError(
                    f"Audio extraction completed but output not found: {output_path}"
                )

            logger.info(f"Successfully extracted audio track {audio_stream.index}")
            return output_path

        except FFmpegError as e:
            logger.error(f"Audio extraction failed: {e}")
            raise TranscodingError(f"Failed to extract audio: {e}") from e
        except Exception as e:
            logger.error(f"Audio extraction failed: {e}")
            raise TranscodingError(f"Failed to extract audio: {e}") from e

    def _get_track_name(self, audio_stream: AudioStream, quality: AudioQuality) -> str:
        """
        Generate track name for audio output.

        Args:
            audio_stream: Source audio stream
            quality: Quality preset

        Returns:
            Track name (e.g., "audio_eng_high", "audio_hin_medium")
        """
        language = audio_stream.language or "und"
        return f"audio_{language}_{quality.name}"

    def _build_command(
        self,
        options: AudioExtractionOptions,
        segment_pattern: Path,
    ) -> List[str]:
        """
        Build FFmpeg command for audio extraction.

        Args:
            options: Extraction options
            segment_pattern: Output segment file pattern

        Returns:
            FFmpeg command as list of arguments
        """
        command = ["ffmpeg", "-y"]

        # Input file
        command.extend(["-i", str(self.input_file)])

        # Select audio stream
        command.extend(["-map", f"0:{options.audio_stream.index}"])

        # Audio encoding options
        command.extend(self._get_audio_options(options))

        # HLS output options
        command.extend(self._get_hls_options(options, segment_pattern))

        # Output file
        command.append(str(options.output_path))

        logger.debug(f"Built command: {' '.join(command)}")
        return command

    def _get_audio_options(self, options: AudioExtractionOptions) -> List[str]:
        """
        Get audio encoding options.

        Args:
            options: Extraction options

        Returns:
            List of FFmpeg arguments for audio encoding
        """
        quality = options.quality
        source = options.audio_stream

        # Determine target parameters
        target_sample_rate = quality.sample_rate if quality.sample_rate > 0 else source.sample_rate
        target_channels = quality.channels if quality.channels > 0 else source.channels

        # Check if we can use stream copy (no re-encoding) - MUCH faster!
        # Conditions: source is AAC, sample rate matches, channels match, and copy is enabled
        can_copy = (
            options.copy_if_possible
            and source.codec.lower() == "aac"
            and source.sample_rate == target_sample_rate
            and source.channels == target_channels
        )

        if can_copy:
            logger.info(
                f"Audio stream already compatible (AAC, {source.sample_rate}Hz, "
                f"{source.channels}ch), using stream copy (no re-encoding) - 50-100x faster!"
            )
            return ["-c:a", "copy"]

        # Otherwise, transcode the audio
        logger.info(
            f"Transcoding audio: {source.codec} → AAC, "
            f"{source.sample_rate}Hz → {target_sample_rate}Hz, "
            f"{source.channels}ch → {target_channels}ch"
        )

        args = [
            "-c:a",
            "aac",  # AAC encoder
            "-b:a",
            f"{quality.bitrate}k",  # Bitrate
        ]

        # Handle sample rate
        args.extend(["-ar", str(target_sample_rate)])

        # Always specify channel count explicitly to avoid FFmpeg defaults
        args.extend(["-ac", str(target_channels)])

        # Handle channel conversion
        if source.channels != target_channels:
            logger.debug(f"Converting channels: {source.channels} → {target_channels}")
        else:
            logger.debug(f"Preserving {source.channels} channels from source")

        logger.debug(
            f"Using AAC encoder with {quality.bitrate}kbps @ {target_sample_rate}Hz, {target_channels}ch"
        )
        return args

    def _get_hls_options(
        self,
        options: AudioExtractionOptions,
        segment_pattern: Path,
    ) -> List[str]:
        """
        Get HLS output format options for audio.

        Args:
            options: Extraction options
            segment_pattern: Output segment file pattern

        Returns:
            List of FFmpeg arguments for HLS output
        """
        args = [
            # Format
            "-f",
            "hls",
            # Segment duration
            "-hls_time",
            str(options.segment_duration),
            # Segment filename pattern
            "-hls_segment_filename",
            str(segment_pattern),
            # Playlist type
            "-hls_playlist_type",
            "vod",
            # Flags
            "-hls_flags",
            "independent_segments",
            # Segment type
            "-hls_segment_type",
            "mpegts",
        ]

        logger.debug(f"HLS segment duration: {options.segment_duration}s")
        return args

    async def extract_all_tracks(
        self,
        audio_streams: List[AudioStream],
        quality: Optional[AudioQuality] = None,
        progress_callback: Optional[Callable[[int, float], None]] = None,
        max_concurrent: int = 2,
    ) -> dict[str, Path]:
        """
        Extract multiple audio tracks concurrently.

        Args:
            audio_streams: List of audio streams to extract
            quality: Target quality preset for all tracks
            progress_callback: Callback(track_index, progress) for updates
            max_concurrent: Maximum concurrent extraction tasks

        Returns:
            Dictionary mapping track names to output playlist paths

        Raises:
            TranscodingError: If any extraction fails
        """
        logger.info(
            f"Extracting {len(audio_streams)} audio tracks " f"(max {max_concurrent} concurrent)"
        )

        results: dict[str, Path] = {}
        semaphore = asyncio.Semaphore(max_concurrent)

        async def extract_track(stream: AudioStream) -> tuple[str, Path]:
            """Extract a single audio track with semaphore."""
            async with semaphore:
                # Create progress callback for this track
                def track_progress(progress: float, speed: Optional[float] = None):
                    if progress_callback:
                        progress_callback(stream.index, progress)

                output_path = await self.extract(
                    audio_stream=stream,
                    quality=quality,
                    progress_callback=track_progress,
                )
                track_name = self._get_track_name(
                    stream, quality or AUDIO_QUALITY_PRESETS["medium"]
                )
                return track_name, output_path

        # Extract all tracks concurrently
        tasks = [extract_track(stream) for stream in audio_streams]
        completed = await asyncio.gather(*tasks, return_exceptions=True)

        # Process results
        for result in completed:
            if isinstance(result, Exception):
                logger.error(f"Audio extraction failed: {result}")
                raise result
            if isinstance(result, tuple):
                track_name, output_path = result
                results[track_name] = output_path

        logger.info(f"Successfully extracted all {len(audio_streams)} audio tracks")
        return results
