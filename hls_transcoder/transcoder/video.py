"""
Video transcoding with hardware-aware encoding and HLS output.

This module provides video transcoding with support for multiple hardware
encoders (NVENC, QSV, AMF, VideoToolbox, VAAPI) and software encoding,
with automatic quality ladder generation and HLS segmentation.
"""

import asyncio
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Dict, List, Optional

from ..executor import AsyncFFmpegProcess
from ..hardware import HardwareInfo
from ..hardware.detector import HardwareType
from ..models import VideoStream
from ..utils import FFmpegError, TranscodingError, get_logger

logger = get_logger(__name__)


@dataclass
class VideoQuality:
    """Video quality preset configuration."""

    name: str  # e.g., "1080p", "720p", "original"
    height: int  # Target height
    bitrate: int  # Target bitrate in kbps
    maxrate: int  # Maximum bitrate in kbps
    bufsize: int  # Buffer size in kbps
    custom_width: Optional[int] = None  # Custom width (overrides 16:9 calculation)

    @property
    def width(self) -> int:
        """Calculate width maintaining 16:9 aspect ratio, or use custom width."""
        if self.custom_width is not None:
            return self.custom_width
        return int((self.height * 16) / 9)

    @property
    def resolution(self) -> str:
        """Get resolution as string."""
        return f"{self.width}x{self.height}"


# Standard quality presets
QUALITY_PRESETS: Dict[str, VideoQuality] = {
    "2160p": VideoQuality("2160p", 2160, 12000, 18000, 24000),
    "1440p": VideoQuality("1440p", 1440, 8000, 12000, 16000),
    "1080p": VideoQuality("1080p", 1080, 5000, 7500, 10000),
    "720p": VideoQuality("720p", 720, 3000, 4500, 6000),
    "480p": VideoQuality("480p", 480, 1500, 2250, 3000),
    "360p": VideoQuality("360p", 360, 800, 1200, 1600),
}


@dataclass
class TranscodingOptions:
    """Options for video transcoding."""

    quality: VideoQuality
    hardware_info: HardwareInfo
    video_stream: VideoStream
    output_path: Path
    segment_duration: int = 6  # HLS segment duration in seconds
    keyframe_interval: int = 2  # GOP size in seconds
    preset: str = "medium"  # Encoding preset (fast, medium, slow)
    crf: Optional[int] = None  # CRF for quality-based encoding
    two_pass: bool = False  # Enable two-pass encoding


class VideoTranscoder:
    """
    Handles video transcoding with hardware acceleration and HLS output.

    Supports multiple hardware encoders with automatic fallback to software
    encoding. Generates HLS-compatible output with configurable segmentation.
    """

    def __init__(
        self,
        input_file: Path,
        output_dir: Path,
        hardware_info: HardwareInfo,
        video_stream: VideoStream,
    ):
        """
        Initialize video transcoder.

        Args:
            input_file: Source video file
            output_dir: Output directory for transcoded files
            hardware_info: Hardware acceleration information
            video_stream: Source video stream metadata
        """
        self.input_file = input_file
        self.output_dir = output_dir
        self.hardware_info = hardware_info
        self.video_stream = video_stream

        # Create output directory
        self.output_dir.mkdir(parents=True, exist_ok=True)

        logger.info(f"Initialized VideoTranscoder for {input_file.name}")
        logger.debug(
            f"Source: {video_stream.resolution} @ {video_stream.fps}fps, "
            f"Codec: {video_stream.codec}"
        )

    async def transcode(
        self,
        quality: VideoQuality,
        progress_callback: Optional[Callable[[float, Optional[float]], None]] = None,
        timeout: Optional[float] = None,
    ) -> Path:
        """
        Transcode video to specified quality.

        Args:
            quality: Target quality preset
            progress_callback: Callback for progress updates (progress, speed)
                              - progress: float (0.0 to 1.0)
                              - speed: Optional[float] (fps or speed multiplier)
            timeout: Maximum transcoding time in seconds

        Returns:
            Path to output playlist file

        Raises:
            TranscodingError: If transcoding fails
        """
        logger.info(f"Starting transcoding to {quality.name}")

        # Create output paths
        output_path = self.output_dir / f"{quality.name}.m3u8"
        segment_pattern = self.output_dir / f"{quality.name}_%03d.ts"

        # Build transcoding options
        options = TranscodingOptions(
            quality=quality,
            hardware_info=self.hardware_info,
            video_stream=self.video_stream,
            output_path=output_path,
        )

        try:
            # Build FFmpeg command
            command = self._build_command(options, segment_pattern)

            # Execute transcoding
            process = AsyncFFmpegProcess(
                command=command,
                timeout=timeout,
                progress_callback=progress_callback,
            )

            await process.run()

            # Verify output was created
            if not output_path.exists():
                raise TranscodingError(f"Transcoding completed but output not found: {output_path}")

            logger.info(f"Successfully transcoded to {quality.name}")
            return output_path

        except FFmpegError as e:
            logger.error(f"Transcoding failed for {quality.name}: {e}")
            raise TranscodingError(f"Failed to transcode {quality.name}: {e}") from e

    def _build_command(
        self,
        options: TranscodingOptions,
        segment_pattern: Path,
    ) -> List[str]:
        """
        Build FFmpeg command for transcoding.

        Note: Audio (-an) and subtitles (-sn) are disabled as they're handled
        separately by AudioExtractor and SubtitleExtractor respectively.
        This prevents:
        - Audio encoding errors during video transcoding
        - Auto-extraction of embedded subtitles as thousands of VTT files
        - Maintains separation of concerns between video, audio, and subtitle processing

        Args:
            options: Transcoding options
            segment_pattern: Output segment file pattern

        Returns:
            FFmpeg command as list of arguments
        """
        command = ["ffmpeg", "-y"]

        # Hardware decoder (if available) - must come BEFORE input
        if self.hardware_info.has_hardware_encoding:
            hw_decode = self._get_hardware_decoder()
            if hw_decode:
                command.extend(hw_decode)

        # Input options
        command.extend(["-i", str(self.input_file)])

        # Video encoding options
        command.extend(self._get_video_options(options))

        # Disable audio (handled separately by AudioExtractor)
        command.extend(["-an"])

        # Disable subtitles (handled separately by SubtitleExtractor)
        # This prevents FFmpeg from auto-extracting embedded subtitles as VTT files
        command.extend(["-sn"])

        # HLS output options
        command.extend(self._get_hls_options(options, segment_pattern))

        # Output file
        command.append(str(options.output_path))

        logger.debug(f"Built command: {' '.join(command)}")
        return command

    def _get_hardware_decoder(self) -> Optional[List[str]]:
        """
        Get hardware decoder options.

        Returns:
            List of FFmpeg arguments for hardware decoding, or None
        """
        if not self.hardware_info.selected_encoder:
            return None

        hw_type = self.hardware_info.selected_encoder.hardware_type

        decoder_map = {
            HardwareType.NVIDIA: ["-hwaccel", "cuda", "-hwaccel_output_format", "cuda"],
            HardwareType.INTEL: ["-hwaccel", "qsv", "-hwaccel_output_format", "qsv"],
            HardwareType.AMD: ["-hwaccel", "d3d11va"],  # Windows
            HardwareType.APPLE: ["-hwaccel", "videotoolbox"],
            HardwareType.VAAPI: [
                "-init_hw_device",
                "vaapi=va:/dev/dri/renderD128",
                "-hwaccel",
                "vaapi",
                "-hwaccel_output_format",
                "vaapi",
                "-hwaccel_device",
                "va",
            ],
        }

        options = decoder_map.get(hw_type)
        if options:
            logger.debug(f"Using hardware decoder: {hw_type.value}")
        return options

    def _get_video_options(self, options: TranscodingOptions) -> List[str]:
        """
        Get video encoding options based on hardware type.

        Args:
            options: Transcoding options

        Returns:
            List of FFmpeg arguments for video encoding
        """
        encoder = self.hardware_info.selected_encoder
        if not encoder:
            # Fallback to software encoding
            logger.warning("No hardware encoder available, using software encoding")
            return self._get_software_video_options(options)

        hw_type = encoder.hardware_type

        # Dispatch to hardware-specific method
        encoder_methods = {
            HardwareType.NVIDIA: self._get_nvenc_options,
            HardwareType.INTEL: self._get_qsv_options,
            HardwareType.AMD: self._get_amf_options,
            HardwareType.APPLE: self._get_videotoolbox_options,
            HardwareType.VAAPI: self._get_vaapi_options,
            HardwareType.SOFTWARE: self._get_software_video_options,
        }

        method = encoder_methods.get(hw_type, self._get_software_video_options)
        return method(options)

    def _get_nvenc_options(self, options: TranscodingOptions) -> List[str]:
        """Get NVIDIA NVENC encoding options."""
        quality = options.quality
        gop_size = int(options.video_stream.fps * options.keyframe_interval)

        args = [
            "-c:v",
            "h264_nvenc",
            "-preset",
            "p4",  # NVENC preset (p1=fastest, p7=slowest)
            "-rc:v",
            "vbr",  # Variable bitrate
            "-b:v",
            f"{quality.bitrate}k",
            "-maxrate:v",
            f"{quality.maxrate}k",
            "-bufsize:v",
            f"{quality.bufsize}k",
            "-g",
            str(gop_size),  # GOP size
            "-keyint_min",
            str(gop_size),
            "-sc_threshold",
            "0",  # Disable scene change detection
            "-vf",
            f"scale={quality.width}:{quality.height}:force_original_aspect_ratio=decrease,pad={quality.width}:{quality.height}:(ow-iw)/2:(oh-ih)/2",
        ]

        logger.debug(f"Using NVENC encoder with {quality.name} preset")
        return args

    def _get_qsv_options(self, options: TranscodingOptions) -> List[str]:
        """Get Intel QSV encoding options."""
        quality = options.quality
        gop_size = int(options.video_stream.fps * options.keyframe_interval)

        args = [
            "-c:v",
            "h264_qsv",
            "-preset",
            options.preset,
            "-b:v",
            f"{quality.bitrate}k",
            "-maxrate:v",
            f"{quality.maxrate}k",
            "-bufsize:v",
            f"{quality.bufsize}k",
            "-g",
            str(gop_size),
            "-keyint_min",
            str(gop_size),
            "-sc_threshold",
            "0",
            "-vf",
            f"scale_qsv={quality.width}:{quality.height}",
        ]

        logger.debug(f"Using QSV encoder with {quality.name} preset")
        return args

    def _get_amf_options(self, options: TranscodingOptions) -> List[str]:
        """Get AMD AMF encoding options."""
        quality = options.quality
        gop_size = int(options.video_stream.fps * options.keyframe_interval)

        args = [
            "-c:v",
            "h264_amf",
            "-quality",
            "balanced",  # speed, balanced, or quality
            "-rc",
            "vbr_peak",  # Variable bitrate
            "-b:v",
            f"{quality.bitrate}k",
            "-maxrate:v",
            f"{quality.maxrate}k",
            "-bufsize:v",
            f"{quality.bufsize}k",
            "-g",
            str(gop_size),
            "-keyint_min",
            str(gop_size),
            "-sc_threshold",
            "0",
            "-vf",
            f"scale={quality.width}:{quality.height}:force_original_aspect_ratio=decrease,pad={quality.width}:{quality.height}:(ow-iw)/2:(oh-ih)/2",
        ]

        logger.debug(f"Using AMF encoder with {quality.name} preset")
        return args

    def _get_videotoolbox_options(self, options: TranscodingOptions) -> List[str]:
        """Get Apple VideoToolbox encoding options."""
        quality = options.quality
        gop_size = int(options.video_stream.fps * options.keyframe_interval)

        args = [
            "-c:v",
            "h264_videotoolbox",
            "-b:v",
            f"{quality.bitrate}k",
            "-maxrate:v",
            f"{quality.maxrate}k",
            "-bufsize:v",
            f"{quality.bufsize}k",
            "-g",
            str(gop_size),
            "-keyint_min",
            str(gop_size),
            "-sc_threshold",
            "0",
            "-vf",
            f"scale={quality.width}:{quality.height}:force_original_aspect_ratio=decrease,pad={quality.width}:{quality.height}:(ow-iw)/2:(oh-ih)/2",
        ]

        logger.debug(f"Using VideoToolbox encoder with {quality.name} preset")
        return args

    def _get_vaapi_options(self, options: TranscodingOptions) -> List[str]:
        """Get VAAPI encoding options."""
        quality = options.quality
        gop_size = int(options.video_stream.fps * options.keyframe_interval)

        args = [
            "-c:v",
            "h264_vaapi",
            "-b:v",
            f"{quality.bitrate}k",
            "-maxrate:v",
            f"{quality.maxrate}k",
            "-bufsize:v",
            f"{quality.bufsize}k",
            "-g",
            str(gop_size),
            "-keyint_min",
            str(gop_size),
            "-sc_threshold",
            "0",
            "-vf",
            f"scale_vaapi=w={quality.width}:h={quality.height}:format=nv12",
        ]

        logger.debug(f"Using VAAPI encoder with {quality.name} preset")
        return args

    def _get_software_video_options(self, options: TranscodingOptions) -> List[str]:
        """Get software (libx264) encoding options."""
        quality = options.quality
        gop_size = int(options.video_stream.fps * options.keyframe_interval)

        args = [
            "-c:v",
            "libx264",
            "-preset",
            options.preset,  # ultrafast, fast, medium, slow, veryslow
            "-b:v",
            f"{quality.bitrate}k",
            "-maxrate:v",
            f"{quality.maxrate}k",
            "-bufsize:v",
            f"{quality.bufsize}k",
            "-g",
            str(gop_size),
            "-keyint_min",
            str(gop_size),
            "-sc_threshold",
            "0",
            "-vf",
            f"scale={quality.width}:{quality.height}:force_original_aspect_ratio=decrease,pad={quality.width}:{quality.height}:(ow-iw)/2:(oh-ih)/2",
        ]

        # Add CRF if specified
        if options.crf:
            args.extend(["-crf", str(options.crf)])

        logger.debug(f"Using libx264 software encoder with {quality.name} preset")
        return args

    def _get_hls_options(
        self,
        options: TranscodingOptions,
        segment_pattern: Path,
    ) -> List[str]:
        """
        Get HLS output format options.

        Args:
            options: Transcoding options
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
            # Playlist type (VOD or EVENT)
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

    def calculate_quality_ladder(
        self,
        max_qualities: Optional[List[str]] = None,
        original_only: bool = False,
    ) -> List[VideoQuality]:
        """
        Calculate appropriate quality ladder based on source video.

        Args:
            max_qualities: Optional list of quality names to include
            original_only: If True, only transcode at original resolution (no downscaling)

        Returns:
            List of VideoQuality presets sorted by descending height
        """
        source_height = self.video_stream.height
        source_width = self.video_stream.width

        logger.info(f"Calculating quality ladder for {source_width}x{source_height}")

        # If original_only, create a single quality preset matching source
        if original_only:
            # Find the closest preset to use as bitrate reference
            closest_preset = None
            min_diff = float("inf")

            for preset in QUALITY_PRESETS.values():
                height_diff = abs(preset.height - source_height)
                if height_diff < min_diff:
                    min_diff = height_diff
                    closest_preset = preset

            # Create quality preset matching exact source resolution
            original_quality = VideoQuality(
                name="original",
                height=source_height,
                bitrate=closest_preset.bitrate if closest_preset else 5000,
                maxrate=closest_preset.maxrate if closest_preset else 7500,
                bufsize=closest_preset.bufsize if closest_preset else 10000,
                custom_width=source_width,  # Use actual source width
            )

            logger.info(f"Original only mode: {source_width}x{source_height}")
            return [original_quality]

        # Get all presets up to source height
        available_qualities = []
        for name, preset in QUALITY_PRESETS.items():
            # Only include qualities at or below source resolution
            if preset.height <= source_height:
                # Filter by max_qualities if specified
                if max_qualities is None or name in max_qualities:
                    available_qualities.append(preset)

        # Sort by descending height
        available_qualities.sort(key=lambda q: q.height, reverse=True)

        logger.info(f"Quality ladder: {', '.join(q.name for q in available_qualities)}")

        return available_qualities


async def transcode_all_qualities(
    transcoder: VideoTranscoder,
    qualities: List[VideoQuality],
    progress_callback: Optional[Callable[[str, float], None]] = None,
    max_concurrent: int = 2,
) -> Dict[str, Path]:
    """
    Transcode video to multiple qualities concurrently.

    Args:
        transcoder: VideoTranscoder instance
        qualities: List of quality presets to transcode
        progress_callback: Callback(quality_name, progress) for updates
        max_concurrent: Maximum concurrent transcoding tasks

    Returns:
        Dictionary mapping quality names to output playlist paths

    Raises:
        TranscodingError: If any transcoding fails
    """
    logger.info(f"Transcoding to {len(qualities)} qualities (max {max_concurrent} concurrent)")

    results: Dict[str, Path] = {}
    semaphore = asyncio.Semaphore(max_concurrent)

    async def transcode_quality(quality: VideoQuality) -> tuple[str, Path]:
        """Transcode a single quality with semaphore."""
        async with semaphore:
            # Create progress callback for this quality
            def quality_progress(progress: float, speed: Optional[float]):
                if progress_callback:
                    progress_callback(quality.name, progress)

            output_path = await transcoder.transcode(
                quality=quality,
                progress_callback=quality_progress,
            )
            return quality.name, output_path

    # Transcode all qualities concurrently
    tasks = [transcode_quality(q) for q in qualities]
    completed = await asyncio.gather(*tasks, return_exceptions=True)

    # Process results
    for result in completed:
        if isinstance(result, Exception):
            logger.error(f"Transcoding failed: {result}")
            raise result
        if isinstance(result, tuple):
            quality_name, output_path = result
            results[quality_name] = output_path

    logger.info(f"Successfully transcoded all {len(qualities)} qualities")
    return results
