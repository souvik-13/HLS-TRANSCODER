"""
Helper functions for HLS transcoder.

This module contains utility functions used throughout the application.
"""

import re
from pathlib import Path
from typing import Optional


def format_size(bytes: int) -> str:
    """
    Format file size in human-readable format.

    Args:
        bytes: Size in bytes

    Returns:
        Formatted size string (e.g., "1.5 GB")
    """
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if bytes < 1024.0:
            return f"{bytes:.1f} {unit}"
        bytes /= 1024.0  # type: ignore
    return f"{bytes:.1f} PB"


def format_duration(seconds: float) -> str:
    """
    Format duration as HH:MM:SS.

    Args:
        seconds: Duration in seconds

    Returns:
        Formatted duration string (e.g., "01:30:45")
    """
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"


def parse_time_to_seconds(time_str: str) -> float:
    """
    Parse time string to seconds.

    Supports formats:
    - HH:MM:SS.mmm
    - MM:SS.mmm
    - SS.mmm

    Args:
        time_str: Time string to parse

    Returns:
        Time in seconds
    """
    parts = time_str.split(":")
    if len(parts) == 3:
        hours, minutes, seconds = parts
        return float(hours) * 3600 + float(minutes) * 60 + float(seconds)
    elif len(parts) == 2:
        minutes, seconds = parts
        return float(minutes) * 60 + float(seconds)
    else:
        return float(parts[0])


def sanitize_filename(filename: str) -> str:
    """
    Sanitize filename by removing invalid characters.

    Args:
        filename: Original filename

    Returns:
        Sanitized filename
    """
    # Remove invalid characters
    filename = re.sub(r'[<>:"/\\|?*]', "", filename)
    # Replace spaces with underscores
    filename = filename.replace(" ", "_")
    # Limit length
    if len(filename) > 255:
        name, ext = filename.rsplit(".", 1) if "." in filename else (filename, "")
        filename = name[: 255 - len(ext) - 1] + "." + ext if ext else name[:255]
    return filename


def ensure_directory(path: Path) -> Path:
    """
    Ensure directory exists, create if it doesn't.

    Args:
        path: Directory path

    Returns:
        Resolved directory path
    """
    path.mkdir(parents=True, exist_ok=True)
    return path.resolve()


def get_file_size(path: Path) -> int:
    """
    Get file size in bytes.

    Args:
        path: File path

    Returns:
        File size in bytes, 0 if file doesn't exist
    """
    if path.exists() and path.is_file():
        return path.stat().st_size
    return 0


def parse_bitrate(bitrate_str: str) -> int:
    """
    Parse bitrate string to bits per second.

    Supports formats like: "128k", "5M", "1000"

    Args:
        bitrate_str: Bitrate string

    Returns:
        Bitrate in bits per second
    """
    bitrate_str = bitrate_str.strip().upper()

    # Extract number and unit
    match = re.match(r"(\d+\.?\d*)\s*([KMG])?", bitrate_str)
    if not match:
        return 0

    value = float(match.group(1))
    unit = match.group(2)

    # Convert to bits per second
    if unit == "K":
        return int(value * 1000)
    elif unit == "M":
        return int(value * 1000000)
    elif unit == "G":
        return int(value * 1000000000)
    else:
        return int(value)


def format_bitrate(bits_per_second: int) -> str:
    """
    Format bitrate in human-readable format.

    Args:
        bits_per_second: Bitrate in bits per second

    Returns:
        Formatted bitrate string (e.g., "5.0 Mbps")
    """
    if bits_per_second >= 1000000:
        return f"{bits_per_second / 1000000:.1f} Mbps"
    elif bits_per_second >= 1000:
        return f"{bits_per_second / 1000:.1f} Kbps"
    else:
        return f"{bits_per_second} bps"


def calculate_aspect_ratio(width: int, height: int) -> tuple[int, int]:
    """
    Calculate aspect ratio in simplest form.

    Args:
        width: Video width
        height: Video height

    Returns:
        Tuple of (width_ratio, height_ratio)
    """
    from math import gcd

    divisor = gcd(width, height)
    return (width // divisor, height // divisor)


def get_quality_from_height(height: int, exact_match: bool = False) -> Optional[str]:
    """
    Get quality label from video height.

    Args:
        height: Video height in pixels
        exact_match: If True, only return label for exact height matches

    Returns:
        Quality label (e.g., "1080p") or None
    """
    quality_map = {
        2160: "2160p",
        1440: "1440p",
        1080: "1080p",
        720: "720p",
        480: "480p",
        360: "360p",
        240: "240p",
    }

    # Check for exact match
    if height in quality_map:
        return quality_map[height]

    # If exact match required, return None
    if exact_match:
        return None

    # Find closest quality (prefer lower to avoid upscaling)
    for standard_height in sorted(quality_map.keys(), reverse=True):
        if height >= standard_height:
            return quality_map[standard_height]

    # If video is smaller than 240p, return the smallest quality
    return "240p"


def get_standard_resolutions() -> dict[str, tuple[int, int]]:
    """
    Get standard resolution mappings.

    Returns:
        Dictionary mapping quality labels to (width, height) tuples
    """
    return {
        "2160p": (3840, 2160),
        "1440p": (2560, 1440),
        "1080p": (1920, 1080),
        "720p": (1280, 720),
        "480p": (854, 480),
        "360p": (640, 360),
        "240p": (426, 240),
    }


def calculate_target_resolution(
    source_width: int, source_height: int, target_quality: str
) -> tuple[int, int]:
    """
    Calculate target resolution maintaining aspect ratio.

    Args:
        source_width: Source video width
        source_height: Source video height
        target_quality: Target quality label (e.g., "1080p") or "original"

    Returns:
        Tuple of (target_width, target_height)
    """
    # If original, return source dimensions
    if target_quality == "original":
        return (source_width, source_height)

    # Get standard resolution for target quality
    standard_resolutions = get_standard_resolutions()
    if target_quality not in standard_resolutions:
        return (source_width, source_height)

    std_width, std_height = standard_resolutions[target_quality]

    # Calculate aspect ratio
    source_aspect = source_width / source_height

    # Calculate target dimensions maintaining aspect ratio
    target_height = std_height
    target_width = int(target_height * source_aspect)

    # Ensure even dimensions (required for most codecs)
    target_width = target_width if target_width % 2 == 0 else target_width - 1
    target_height = target_height if target_height % 2 == 0 else target_height - 1

    return (target_width, target_height)


def should_include_quality(
    source_height: int, target_quality: str, allow_upscaling: bool = False
) -> bool:
    """
    Determine if a quality variant should be included based on source resolution.

    Args:
        source_height: Source video height
        target_quality: Target quality label (e.g., "1080p")
        allow_upscaling: Whether to allow upscaling to higher resolutions

    Returns:
        True if quality should be included, False otherwise
    """
    if target_quality == "original":
        return True

    standard_resolutions = get_standard_resolutions()
    if target_quality not in standard_resolutions:
        return False

    target_height = standard_resolutions[target_quality][1]

    # Don't include if target is higher than source (unless upscaling allowed)
    if target_height > source_height and not allow_upscaling:
        return False

    return True


def calculate_segment_count(duration: float, segment_duration: int) -> int:
    """
    Calculate number of HLS segments.

    Args:
        duration: Total duration in seconds
        segment_duration: Segment duration in seconds

    Returns:
        Number of segments
    """
    import math

    return math.ceil(duration / segment_duration)
