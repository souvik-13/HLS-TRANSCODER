"""
Hardware acceleration detection for video encoding.

This module detects available hardware encoders and provides
fallback mechanisms when hardware acceleration is unavailable.
"""

import asyncio
import platform
import shutil
import subprocess
from dataclasses import dataclass
from enum import Enum
from typing import Dict, List, Optional

from ..utils import HardwareError, get_logger

logger = get_logger(__name__)


class HardwareType(str, Enum):
    """Hardware acceleration types."""

    NVIDIA = "nvidia"  # NVENC
    INTEL = "intel"  # Quick Sync (QSV)
    AMD = "amd"  # AMF
    APPLE = "apple"  # VideoToolbox
    VAAPI = "vaapi"  # Linux VA-API
    SOFTWARE = "software"  # CPU encoding


@dataclass
class EncoderInfo:
    """Information about a specific encoder."""

    name: str  # FFmpeg encoder name (e.g., 'h264_nvenc')
    hardware_type: HardwareType
    display_name: str  # Human-readable name
    available: bool = False
    tested: bool = False
    error: Optional[str] = None


@dataclass
class HardwareInfo:
    """Complete hardware acceleration information."""

    detected_type: HardwareType
    available_encoders: List[EncoderInfo]
    selected_encoder: Optional[EncoderInfo] = None
    platform: str = platform.system()

    @property
    def has_hardware_encoding(self) -> bool:
        """Check if any hardware encoder is available."""
        return any(enc.available for enc in self.available_encoders)

    @property
    def available_hardware_types(self) -> List[HardwareType]:
        """Get list of available hardware types."""
        return list(
            {
                enc.hardware_type
                for enc in self.available_encoders
                if enc.available and enc.hardware_type != HardwareType.SOFTWARE
            }
        )

    def get_encoder(self, hardware_type: HardwareType) -> Optional[EncoderInfo]:
        """Get encoder for specific hardware type."""
        for enc in self.available_encoders:
            if enc.hardware_type == hardware_type and enc.available:
                return enc
        return None


class HardwareDetector:
    """
    Detects available hardware encoders and selects the best option.

    This class checks for various hardware acceleration technologies:
    - NVIDIA NVENC (h264_nvenc, hevc_nvenc)
    - Intel Quick Sync (h264_qsv, hevc_qsv)
    - AMD AMF (h264_amf, hevc_amf)
    - Apple VideoToolbox (h264_videotoolbox, hevc_videotoolbox)
    - VA-API (h264_vaapi, hevc_vaapi)
    - Software fallback (libx264, libx265)
    """

    # Encoder definitions: (ffmpeg_name, hardware_type, display_name)
    ENCODERS = [
        # NVIDIA NVENC
        ("h264_nvenc", HardwareType.NVIDIA, "NVIDIA NVENC H.264"),
        ("hevc_nvenc", HardwareType.NVIDIA, "NVIDIA NVENC H.265"),
        # Intel QSV
        ("h264_qsv", HardwareType.INTEL, "Intel Quick Sync H.264"),
        ("hevc_qsv", HardwareType.INTEL, "Intel Quick Sync H.265"),
        # AMD AMF
        ("h264_amf", HardwareType.AMD, "AMD AMF H.264"),
        ("hevc_amf", HardwareType.AMD, "AMD AMF H.265"),
        # Apple VideoToolbox
        ("h264_videotoolbox", HardwareType.APPLE, "Apple VideoToolbox H.264"),
        ("hevc_videotoolbox", HardwareType.APPLE, "Apple VideoToolbox H.265"),
        # VA-API (Linux)
        ("h264_vaapi", HardwareType.VAAPI, "VA-API H.264"),
        ("hevc_vaapi", HardwareType.VAAPI, "VA-API H.265"),
        # Software fallback
        ("libx264", HardwareType.SOFTWARE, "Software H.264 (x264)"),
        ("libx265", HardwareType.SOFTWARE, "Software H.265 (x265)"),
    ]

    def __init__(self):
        """Initialize hardware detector."""
        self._ffmpeg_path: Optional[str] = None
        self._cache: Optional[HardwareInfo] = None

    async def detect(self, prefer: str = "auto", test_encoding: bool = False) -> HardwareInfo:
        """
        Detect available hardware encoders.

        Args:
            prefer: Preferred hardware type ('auto', 'nvidia', 'intel', 'amd', 'apple', 'vaapi', 'software')
            test_encoding: Whether to test encoders with actual encoding

        Returns:
            HardwareInfo with detected encoders

        Raises:
            HardwareError: If FFmpeg is not found or detection fails
        """
        # Check cache
        if self._cache is not None:
            logger.debug("Using cached hardware detection results")
            return self._cache

        logger.info("Detecting hardware acceleration capabilities...")

        # Check FFmpeg availability
        self._ffmpeg_path = shutil.which("ffmpeg")
        if not self._ffmpeg_path:
            raise HardwareError("FFmpeg not found in PATH. Please install FFmpeg.")

        # Get available encoders from FFmpeg
        available_encoder_names = await self._get_ffmpeg_encoders()

        # Create encoder info objects
        encoders = []
        for name, hw_type, display_name in self.ENCODERS:
            encoder = EncoderInfo(
                name=name,
                hardware_type=hw_type,
                display_name=display_name,
                available=name in available_encoder_names,
            )
            encoders.append(encoder)

        # Determine detected hardware type
        detected_type = self._determine_hardware_type(encoders, prefer)

        # Test encoders if requested
        if test_encoding:
            await self._test_encoders(encoders)

        # Create hardware info
        hardware_info = HardwareInfo(
            detected_type=detected_type,
            available_encoders=encoders,
        )

        # Select best encoder
        hardware_info.selected_encoder = self._select_encoder(hardware_info, prefer)

        # Cache results
        self._cache = hardware_info

        # Log results
        self._log_detection_results(hardware_info)

        return hardware_info

    async def _get_ffmpeg_encoders(self) -> set:
        """
        Get list of available encoders from FFmpeg.

        Returns:
            Set of encoder names

        Raises:
            HardwareError: If FFmpeg command fails
        """
        if not self._ffmpeg_path:
            raise HardwareError("FFmpeg path not initialized")

        try:
            process = await asyncio.create_subprocess_exec(
                self._ffmpeg_path,
                "-hide_banner",
                "-encoders",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            stdout, stderr = await process.communicate()

            if process.returncode != 0:
                raise HardwareError(f"Failed to get FFmpeg encoders: {stderr.decode()}")

            # Parse encoder list
            encoders = set()
            for line in stdout.decode().split("\n"):
                # Encoder lines start with " V....." for video encoders
                if line.strip().startswith("V"):
                    # Extract encoder name (second column)
                    parts = line.split()
                    if len(parts) >= 2:
                        encoders.add(parts[1])

            logger.debug(f"Found {len(encoders)} video encoders in FFmpeg")
            return encoders

        except Exception as e:
            raise HardwareError(f"Failed to detect FFmpeg encoders: {e}")

    def _determine_hardware_type(self, encoders: List[EncoderInfo], prefer: str) -> HardwareType:
        """
        Determine the primary hardware type based on available encoders.

        Args:
            encoders: List of encoder info objects
            prefer: User preference ('auto' or specific type)

        Returns:
            Detected hardware type
        """
        # If user specified a preference and it's available, use it
        if prefer != "auto":
            try:
                preferred_type = HardwareType(prefer.lower())
                if any(enc.available for enc in encoders if enc.hardware_type == preferred_type):
                    logger.info(f"Using preferred hardware type: {preferred_type.value}")
                    return preferred_type
            except ValueError:
                logger.warning(f"Invalid hardware preference: {prefer}")

        # Auto-detect: priority order based on performance
        priority = [
            HardwareType.NVIDIA,  # Usually fastest
            HardwareType.APPLE,  # Good on Mac
            HardwareType.INTEL,  # Good quality/speed balance
            HardwareType.AMD,  # Decent performance
            HardwareType.VAAPI,  # Linux fallback
            HardwareType.SOFTWARE,  # Last resort
        ]

        for hw_type in priority:
            if any(enc.available for enc in encoders if enc.hardware_type == hw_type):
                logger.info(f"Detected hardware type: {hw_type.value}")
                return hw_type

        return HardwareType.SOFTWARE

    async def _test_encoders(self, encoders: List[EncoderInfo]) -> None:
        """
        Test encoders with actual encoding to verify they work.

        Args:
            encoders: List of encoder info objects to test
        """
        if not self._ffmpeg_path:
            logger.warning("FFmpeg path not set, skipping encoder tests")
            return

        logger.info("Testing encoders with actual encoding...")

        for encoder in encoders:
            if not encoder.available or encoder.hardware_type == HardwareType.SOFTWARE:
                continue

            logger.debug(f"Testing encoder: {encoder.name}")

            try:
                # Build FFmpeg command based on encoder type
                cmd = [self._ffmpeg_path, "-loglevel", "error"]

                # Hardware-specific initialization
                if encoder.hardware_type == HardwareType.VAAPI:
                    # VAAPI requires device initialization and format conversion
                    cmd.extend(
                        [
                            "-init_hw_device",
                            "vaapi=va:/dev/dri/renderD128",
                            "-filter_hw_device",
                            "va",
                        ]
                    )
                elif encoder.hardware_type == HardwareType.INTEL:
                    # QSV (Intel Quick Sync)
                    cmd.extend(
                        [
                            "-init_hw_device",
                            "qsv=hw",
                            "-filter_hw_device",
                            "hw",
                        ]
                    )
                elif encoder.hardware_type == HardwareType.NVIDIA:
                    # NVENC
                    cmd.extend(
                        [
                            "-init_hw_device",
                            "cuda=cu:0",
                            "-filter_hw_device",
                            "cu",
                        ]
                    )

                # Input test pattern
                cmd.extend(
                    [
                        "-f",
                        "lavfi",
                        "-i",
                        "color=black:s=1280x720:d=1",
                    ]
                )

                # Hardware upload filter if needed
                if encoder.hardware_type == HardwareType.VAAPI:
                    cmd.extend(["-vf", "format=nv12,hwupload"])
                elif encoder.hardware_type == HardwareType.INTEL:
                    cmd.extend(["-vf", "format=nv12,hwupload=extra_hw_frames=64"])
                elif encoder.hardware_type == HardwareType.NVIDIA:
                    cmd.extend(["-vf", "format=nv12,hwupload_cuda"])

                # Encoder and output
                cmd.extend(
                    [
                        "-c:v",
                        encoder.name,
                        "-frames:v",
                        "25",
                        "-f",
                        "null",
                        "-",
                    ]
                )

                # Test encoding
                process = await asyncio.create_subprocess_exec(
                    *cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )

                stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=10.0)

                if process.returncode == 0:
                    encoder.tested = True
                    logger.debug(f"✓ {encoder.name} test passed")
                else:
                    encoder.available = False
                    encoder.error = "Test encoding failed"
                    error_msg = stderr.decode().strip()
                    if error_msg:
                        logger.debug(f"Error output: {error_msg[:200]}")
                    logger.warning(f"✗ {encoder.name} test failed")

            except asyncio.TimeoutError:
                encoder.available = False
                encoder.error = "Test encoding timed out"
                logger.warning(f"✗ {encoder.name} test timed out")
            except Exception as e:
                encoder.available = False
                encoder.error = str(e)
                logger.warning(f"✗ {encoder.name} test error: {e}")

    def _select_encoder(self, hardware_info: HardwareInfo, prefer: str) -> Optional[EncoderInfo]:
        """
        Select the best encoder to use.

        Args:
            hardware_info: Hardware information
            prefer: User preference

        Returns:
            Selected encoder or None
        """
        # Try to get H.264 encoder for detected type
        for encoder in hardware_info.available_encoders:
            if (
                encoder.hardware_type == hardware_info.detected_type
                and encoder.available
                and "h264" in encoder.name
            ):
                logger.info(f"Selected encoder: {encoder.display_name}")
                return encoder

        # Fallback to any available encoder
        for encoder in hardware_info.available_encoders:
            if encoder.available and "h264" in encoder.name:
                logger.warning(f"Falling back to encoder: {encoder.display_name}")
                return encoder

        logger.error("No suitable encoder found!")
        return None

    def _log_detection_results(self, hardware_info: HardwareInfo) -> None:
        """
        Log hardware detection results.

        Args:
            hardware_info: Hardware information to log
        """
        logger.info("=" * 60)
        logger.info("Hardware Detection Results")
        logger.info("=" * 60)
        logger.info(f"Platform: {hardware_info.platform}")
        logger.info(f"Detected Type: {hardware_info.detected_type.value}")
        logger.info(f"Hardware Encoding: {'Yes' if hardware_info.has_hardware_encoding else 'No'}")
        logger.info("")
        logger.info("Available Encoders:")

        for encoder in hardware_info.available_encoders:
            if encoder.available:
                status = "✓ AVAILABLE"
                if encoder.tested:
                    status += " (tested)"
            else:
                status = "✗ NOT AVAILABLE"
                if encoder.error:
                    status += f" ({encoder.error})"

            logger.info(f"  {encoder.display_name:40s} {status}")

        if hardware_info.selected_encoder:
            logger.info("")
            logger.info(f"Selected: {hardware_info.selected_encoder.display_name}")

        logger.info("=" * 60)

    def clear_cache(self) -> None:
        """Clear cached detection results."""
        self._cache = None
        logger.debug("Hardware detection cache cleared")


# Global instance for easy access
_detector: Optional[HardwareDetector] = None


def get_hardware_detector() -> HardwareDetector:
    """
    Get global hardware detector instance.

    Returns:
        HardwareDetector instance
    """
    global _detector
    if _detector is None:
        _detector = HardwareDetector()
    return _detector
