"""
Subtitle extraction and conversion for HLS output.

This module provides subtitle extraction with WebVTT conversion, multi-track support,
and proper handling of both embedded and external subtitle formats.
"""

import asyncio
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, List, Optional

from ..executor import AsyncFFmpegProcess
from ..models import SubtitleStream
from ..utils import FFmpegError, TranscodingError, get_logger

logger = get_logger(__name__)


@dataclass
class SubtitleExtractionOptions:
    """Options for subtitle extraction."""

    subtitle_stream: SubtitleStream
    output_path: Path
    format: str = "webvtt"  # Output format (webvtt, srt, ass)


class SubtitleExtractor:
    """
    Handles subtitle extraction and conversion to WebVTT format.

    Supports multi-track subtitle extraction, format conversion, and proper
    handling of embedded and external subtitle files for HLS compatibility.
    """

    def __init__(
        self,
        input_file: Path,
        output_dir: Path,
    ):
        """
        Initialize subtitle extractor.

        Args:
            input_file: Source media file
            output_dir: Output directory for subtitle files
        """
        self.input_file = input_file
        self.output_dir = output_dir

        # Create output directory
        self.output_dir.mkdir(parents=True, exist_ok=True)

        logger.info(f"Initialized SubtitleExtractor for {input_file.name}")

    async def extract(
        self,
        subtitle_stream: SubtitleStream,
        output_format: str = "webvtt",
        progress_callback: Optional[Callable[[float, Optional[float]], None]] = None,
        timeout: Optional[float] = None,
    ) -> Path:
        """
        Extract and convert subtitle stream to WebVTT format.

        Args:
            subtitle_stream: Source subtitle stream to extract
            output_format: Target format (default: webvtt)
            progress_callback: Callback for progress updates (0.0 to 1.0)
            timeout: Maximum extraction time in seconds

        Returns:
            Path to extracted subtitle file

        Raises:
            TranscodingError: If extraction fails
            FFmpegError: If FFmpeg command fails
        """
        language = subtitle_stream.language if subtitle_stream.language else "und"
        forced_suffix = "_forced" if subtitle_stream.forced else ""

        # Determine output extension based on format
        extension = self._get_extension(output_format)
        output_file = self.output_dir / f"subtitle_{language}{forced_suffix}.{extension}"

        logger.info(
            f"Extracting subtitle stream {subtitle_stream.index} "
            f"({language}) to {output_file.name}"
        )

        # Build FFmpeg command
        command = self._build_command(
            subtitle_stream=subtitle_stream,
            output_file=output_file,
            output_format=output_format,
        )

        # Execute extraction
        try:
            process = AsyncFFmpegProcess(
                command=command,
                timeout=timeout or 300.0,  # Default 5 minutes timeout
                progress_callback=progress_callback,
            )

            await process.run()

            if not output_file.exists():
                raise TranscodingError(f"Subtitle extraction failed: output file not created")

            logger.info(f"Successfully extracted subtitle: {output_file.name}")
            return output_file

        except FFmpegError as e:
            error_msg = f"FFmpeg subtitle extraction failed: {e}"
            logger.error(error_msg)
            raise TranscodingError(error_msg) from e
        except asyncio.TimeoutError:
            error_msg = f"Subtitle extraction timed out after {timeout}s"
            logger.error(error_msg)
            raise TranscodingError(error_msg)
        except Exception as e:
            error_msg = f"Unexpected error during subtitle extraction: {e}"
            logger.error(error_msg)
            raise TranscodingError(error_msg) from e

    def _build_command(
        self,
        subtitle_stream: SubtitleStream,
        output_file: Path,
        output_format: str,
    ) -> List[str]:
        """
        Build FFmpeg command for subtitle extraction.

        Args:
            subtitle_stream: Source subtitle stream
            output_file: Output file path
            output_format: Target subtitle format

        Returns:
            FFmpeg command as list of arguments
        """
        command = ["ffmpeg", "-hide_banner", "-y"]

        # Input file
        command.extend(["-i", str(self.input_file)])

        # Select subtitle stream
        command.extend(["-map", f"0:{subtitle_stream.index}"])

        # Set output codec based on format
        codec = self._get_codec(output_format, subtitle_stream.codec)
        command.extend(["-c:s", codec])

        # Output file
        command.append(str(output_file))

        logger.debug(f"Subtitle extraction command: {' '.join(command)}")
        return command

    def _get_codec(self, output_format: str, input_codec: str) -> str:
        """
        Get appropriate subtitle codec for output format.

        Args:
            output_format: Target format
            input_codec: Input subtitle codec

        Returns:
            FFmpeg codec name
        """
        format_codec_map = {
            "webvtt": "webvtt",
            "vtt": "webvtt",
            "srt": "srt",
            "ass": "ass",
            "ssa": "ass",
        }

        codec = format_codec_map.get(output_format.lower(), "webvtt")

        # If input is already in target format, we can copy
        if input_codec.lower() == codec.lower():
            return "copy"

        return codec

    def _get_extension(self, output_format: str) -> str:
        """
        Get file extension for output format.

        Args:
            output_format: Target format

        Returns:
            File extension (without dot)
        """
        extension_map = {
            "webvtt": "vtt",
            "vtt": "vtt",
            "srt": "srt",
            "ass": "ass",
            "ssa": "ass",
        }
        return extension_map.get(output_format.lower(), "vtt")

    async def extract_all_tracks(
        self,
        subtitle_streams: List[SubtitleStream],
        output_format: str = "webvtt",
        progress_callback: Optional[Callable[[int, int], None]] = None,
        max_concurrent: int = 4,
    ) -> List[Path]:
        """
        Extract multiple subtitle tracks concurrently.

        Args:
            subtitle_streams: List of subtitle streams to extract
            output_format: Target format for all tracks
            progress_callback: Callback with (completed, total) counts
            max_concurrent: Maximum concurrent extractions

        Returns:
            List of paths to extracted subtitle files

        Raises:
            TranscodingError: If any extraction fails
        """
        if not subtitle_streams:
            logger.warning("No subtitle streams to extract")
            return []

        logger.info(
            f"Extracting {len(subtitle_streams)} subtitle tracks "
            f"(max {max_concurrent} concurrent)"
        )

        # Create semaphore to limit concurrency
        semaphore = asyncio.Semaphore(max_concurrent)
        results: List[Path] = []
        errors: List[str] = []
        completed = 0

        async def extract_with_semaphore(stream: SubtitleStream) -> Optional[Path]:
            """Extract with semaphore control."""
            nonlocal completed

            async with semaphore:
                try:
                    output_path = await self.extract(
                        subtitle_stream=stream,
                        output_format=output_format,
                    )
                    completed += 1
                    if progress_callback:
                        progress_callback(completed, len(subtitle_streams))
                    return output_path
                except Exception as e:
                    error_msg = (
                        f"Failed to extract subtitle {stream.index} " f"({stream.language}): {e}"
                    )
                    logger.error(error_msg)
                    errors.append(error_msg)
                    completed += 1
                    if progress_callback:
                        progress_callback(completed, len(subtitle_streams))
                    return None

        # Execute all extractions concurrently
        tasks = [extract_with_semaphore(stream) for stream in subtitle_streams]

        extracted_paths = await asyncio.gather(*tasks)

        # Filter out None values (failed extractions)
        results = [path for path in extracted_paths if path is not None]

        if errors:
            error_summary = "; ".join(errors)
            if len(results) == 0:
                # All extractions failed
                raise TranscodingError(f"All subtitle extractions failed: {error_summary}")
            else:
                # Some extractions succeeded
                logger.warning(f"Some subtitle extractions failed: {error_summary}")

        logger.info(
            f"Successfully extracted {len(results)}/{len(subtitle_streams)} " f"subtitle tracks"
        )
        return results


# Convenience function for extracting all subtitles
async def extract_all_subtitles(
    input_file: Path,
    subtitle_streams: List[SubtitleStream],
    output_dir: Path,
    output_format: str = "webvtt",
    progress_callback: Optional[Callable[[int, int], None]] = None,
    max_concurrent: int = 4,
) -> List[Path]:
    """
    Extract all subtitle tracks from a media file.

    Args:
        input_file: Source media file
        subtitle_streams: List of subtitle streams to extract
        output_dir: Output directory for subtitle files
        output_format: Target format (default: webvtt)
        progress_callback: Callback with (completed, total) counts
        max_concurrent: Maximum concurrent extractions

    Returns:
        List of paths to extracted subtitle files
    """
    extractor = SubtitleExtractor(input_file, output_dir)
    return await extractor.extract_all_tracks(
        subtitle_streams=subtitle_streams,
        output_format=output_format,
        progress_callback=progress_callback,
        max_concurrent=max_concurrent,
    )
