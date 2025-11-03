"""
Sprite sheet generation for video seeking previews.

This module provides thumbnail extraction at regular intervals and combines them
into sprite sheets with accompanying WebVTT files for video player seeking previews.
"""

import asyncio
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

from ..executor import AsyncFFmpegProcess
from ..utils import FFmpegError, TranscodingError, get_logger

logger = get_logger(__name__)


@dataclass
class SpriteConfig:
    """Configuration for sprite generation."""

    interval: int = 10  # Seconds between thumbnails
    width: int = 160  # Thumbnail width in pixels
    height: int = 90  # Thumbnail height in pixels
    columns: int = 10  # Columns in sprite sheet
    rows: int = 10  # Rows in sprite sheet
    quality: int = 2  # JPEG quality (1-31, lower is better)


@dataclass
class SpriteInfo:
    """Information about generated sprite."""

    sprite_path: Path | list[Path]  # Single path or list of paths for multiple sheets
    vtt_path: Path
    thumbnail_count: int
    columns: int
    rows: int
    tile_width: int
    tile_height: int
    total_size: int
    sheet_count: int = 1  # Number of sprite sheets generated

    @property
    def size_mb(self) -> float:
        """Get total size in megabytes."""
        return self.total_size / (1024 * 1024)


class SpriteGenerator:
    """
    Generates sprite sheets and WebVTT files for video seeking previews.

    Creates thumbnail images at regular intervals, combines them into sprite sheets,
    and generates WebVTT files with coordinates for video player integration.
    """

    def __init__(
        self,
        input_file: Path,
        output_dir: Path,
        duration: float,
    ):
        """
        Initialize sprite generator.

        Args:
            input_file: Source video file
            output_dir: Output directory for sprites
            duration: Video duration in seconds
        """
        self.input_file = input_file
        self.output_dir = output_dir
        self.duration = duration

        # Create output directory
        self.output_dir.mkdir(parents=True, exist_ok=True)

        logger.info(
            f"Initialized SpriteGenerator for {input_file.name} " f"(duration: {duration:.2f}s)"
        )

    async def generate(
        self,
        config: Optional[SpriteConfig] = None,
        progress_callback: Optional[Callable[[float, Optional[float]], None]] = None,
        timeout: Optional[float] = None,
    ) -> SpriteInfo:
        """
        Generate sprite sheet and WebVTT file.

        Args:
            config: Sprite configuration (uses defaults if None)
            progress_callback: Callback for progress updates (current, total)
            timeout: Maximum generation time in seconds

        Returns:
            SpriteInfo with paths and metadata

        Raises:
            TranscodingError: If generation fails
        """
        if config is None:
            config = SpriteConfig()

        # Calculate thumbnail count and sheets needed
        thumbnail_count = self._calculate_thumbnail_count(config)
        sheet_count = self._calculate_sheet_count(thumbnail_count, config)

        logger.info(
            f"Generating {thumbnail_count} thumbnails "
            f"({config.width}x{config.height}) at {config.interval}s intervals "
            f"across {sheet_count} sprite sheet(s)"
        )

        # Create temporary directory for individual thumbnails
        temp_dir = self.output_dir / "temp_thumbnails"
        temp_dir.mkdir(exist_ok=True)

        try:
            # Step 1: Extract thumbnails (60% of progress)
            await self._extract_thumbnails(
                config=config,
                temp_dir=temp_dir,
                progress_callback=lambda p, t=None: (
                    progress_callback(p * 0.6, None) if progress_callback else None
                ),
                timeout=timeout,
            )

            # Step 2: Create sprite sheets (30% of progress)
            sprite_paths = await self._create_sprite_sheets(
                config=config,
                temp_dir=temp_dir,
                thumbnail_count=thumbnail_count,
                sheet_count=sheet_count,
                progress_callback=lambda p, t=None: (
                    progress_callback(0.6 + p * 0.3, None) if progress_callback else None
                ),
            )

            # Step 3: Generate WebVTT (10% of progress)
            vtt_path = self._generate_vtt(
                config=config,
                sprite_paths=sprite_paths,
                thumbnail_count=thumbnail_count,
                sheet_count=sheet_count,
            )

            if progress_callback:
                progress_callback(1.0, None)

            # Calculate total size
            total_size = sum(p.stat().st_size for p in sprite_paths) + vtt_path.stat().st_size

            sprite_info = SpriteInfo(
                sprite_path=sprite_paths[0] if sheet_count == 1 else sprite_paths,
                vtt_path=vtt_path,
                thumbnail_count=thumbnail_count,
                columns=config.columns,
                rows=config.rows,
                tile_width=config.width,
                tile_height=config.height,
                total_size=total_size,
                sheet_count=sheet_count,
            )

            logger.info(
                f"Successfully generated {sheet_count} sprite sheet(s): "
                f"{sprite_paths[0].name if sheet_count == 1 else f'sprite_*.jpg'} "
                f"({sprite_info.size_mb:.2f} MB, {thumbnail_count} thumbnails)"
            )

            return sprite_info

        except Exception as e:
            error_msg = f"Sprite generation failed: {e}"
            logger.error(error_msg)
            raise TranscodingError(error_msg) from e

        finally:
            # Cleanup temporary directory
            self._cleanup_temp_files(temp_dir)

    def _calculate_thumbnail_count(self, config: SpriteConfig) -> int:
        """
        Calculate number of thumbnails to extract.

        Args:
            config: Sprite configuration

        Returns:
            Number of thumbnails
        """
        # Calculate based on duration and interval
        count = math.ceil(self.duration / config.interval)

        # No cap - we'll generate multiple sprite sheets if needed
        return max(1, count)  # At least one thumbnail

    def _calculate_sheet_count(self, thumbnail_count: int, config: SpriteConfig) -> int:
        """
        Calculate number of sprite sheets needed.

        Args:
            thumbnail_count: Total number of thumbnails
            config: Sprite configuration

        Returns:
            Number of sprite sheets needed
        """
        tiles_per_sheet = config.columns * config.rows
        return math.ceil(thumbnail_count / tiles_per_sheet)

    async def _extract_thumbnails(
        self,
        config: SpriteConfig,
        temp_dir: Path,
        progress_callback: Optional[Callable[[float, Optional[float]], None]],
        timeout: Optional[float],
    ) -> None:
        """
        Extract thumbnails from video at regular intervals.

        Args:
            config: Sprite configuration
            temp_dir: Temporary directory for thumbnails
            progress_callback: Progress callback
            timeout: Maximum extraction time

        Raises:
            TranscodingError: If extraction fails
        """
        thumbnail_count = self._calculate_thumbnail_count(config)

        # Build FFmpeg command for thumbnail extraction
        command = self._build_thumbnail_command(config, temp_dir, thumbnail_count)

        logger.debug(f"Extracting {thumbnail_count} thumbnails to {temp_dir}")

        try:
            process = AsyncFFmpegProcess(
                command=command,
                timeout=timeout or 600.0,  # Default 10 minutes
                progress_callback=progress_callback,
            )

            await process.run()

            # Verify thumbnails were created
            thumbnails = list(temp_dir.glob("thumb_*.jpg"))
            if len(thumbnails) == 0:
                raise TranscodingError("No thumbnails were generated")

            logger.debug(f"Extracted {len(thumbnails)} thumbnails")

        except FFmpegError as e:
            error_msg = f"Thumbnail extraction failed: {e}"
            logger.error(error_msg)
            raise TranscodingError(error_msg) from e

    def _build_thumbnail_command(
        self,
        config: SpriteConfig,
        temp_dir: Path,
        thumbnail_count: int,
    ) -> list[str]:
        """
        Build FFmpeg command for thumbnail extraction.

        Args:
            config: Sprite configuration
            temp_dir: Output directory for thumbnails
            thumbnail_count: Number of thumbnails to extract

        Returns:
            FFmpeg command as list
        """
        output_pattern = str(temp_dir / "thumb_%04d.jpg")

        command = [
            "ffmpeg",
            "-hide_banner",
            "-y",
            "-i",
            str(self.input_file),
            "-vf",
            f"fps=1/{config.interval},scale={config.width}:{config.height}",
            "-frames:v",
            str(thumbnail_count),
            "-q:v",
            str(config.quality),
            output_pattern,
        ]

        logger.debug(f"Thumbnail command: {' '.join(command)}")
        return command

    async def _create_sprite_sheets(
        self,
        config: SpriteConfig,
        temp_dir: Path,
        thumbnail_count: int,
        sheet_count: int,
        progress_callback: Optional[Callable[[float, Optional[float]], None]],
    ) -> list[Path]:
        """
        Combine thumbnails into one or more sprite sheets using FFmpeg tile filter.

        Args:
            config: Sprite configuration
            temp_dir: Directory containing thumbnails
            thumbnail_count: Total number of thumbnails
            sheet_count: Number of sprite sheets to create
            progress_callback: Progress callback

        Returns:
            List of paths to sprite sheets

        Raises:
            TranscodingError: If sprite creation fails
        """
        sprite_paths: list[Path] = []
        tiles_per_sheet = config.columns * config.rows

        for sheet_idx in range(sheet_count):
            # Calculate thumbnails for this sheet
            start_thumb = sheet_idx * tiles_per_sheet
            end_thumb = min(start_thumb + tiles_per_sheet, thumbnail_count)
            sheet_thumb_count = end_thumb - start_thumb

            # Determine sprite filename
            if sheet_count == 1:
                sprite_path = self.output_dir / "sprite.jpg"
            else:
                sprite_path = self.output_dir / f"sprite_{sheet_idx}.jpg"

            # Build FFmpeg command for this sprite sheet
            command = self._build_sprite_command(
                config, temp_dir, sprite_path, sheet_thumb_count, start_thumb + 1
            )

            # Update sprite_path to match actual output format (PNG)
            sprite_path = sprite_path.with_suffix(".png")

            logger.debug(
                f"Creating sprite sheet {sheet_idx + 1}/{sheet_count}: {sprite_path.name} "
                f"(thumbnails {start_thumb + 1}-{end_thumb})"
            )

            try:
                sheet_progress = (sheet_idx / sheet_count, (sheet_idx + 1) / sheet_count)
                process = AsyncFFmpegProcess(
                    command=command,
                    timeout=300.0,  # 5 minutes for sprite creation
                    progress_callback=(
                        lambda p, t=None, sp=sheet_progress: (
                            progress_callback(sp[0] + (p * (sp[1] - sp[0])), None)
                            if progress_callback
                            else None
                        )
                    ),
                )

                await process.run()

                if not sprite_path.exists():
                    raise TranscodingError(f"Sprite sheet {sheet_idx} was not created")

                sprite_paths.append(sprite_path)
                logger.debug(f"Created sprite sheet: {sprite_path.name}")

            except FFmpegError as e:
                error_msg = f"Sprite sheet {sheet_idx} creation failed: {e}"
                logger.error(error_msg)
                raise TranscodingError(error_msg) from e

        return sprite_paths

    def _build_sprite_command(
        self,
        config: SpriteConfig,
        temp_dir: Path,
        sprite_path: Path,
        thumbnail_count: int,
        start_number: int = 1,
    ) -> list[str]:
        """
        Build FFmpeg command for sprite sheet creation.

        Args:
            config: Sprite configuration
            temp_dir: Directory containing thumbnails
            sprite_path: Output sprite path
            thumbnail_count: Number of thumbnails for this sheet
            start_number: Starting thumbnail number (for multiple sheets)

        Returns:
            FFmpeg command as list
        """
        # Calculate actual grid dimensions
        columns = min(config.columns, thumbnail_count)
        rows = math.ceil(thumbnail_count / columns)

        # Create input file list
        input_pattern = str(temp_dir / "thumb_%04d.jpg")

        command = [
            "ffmpeg",
            "-hide_banner",
            "-y",
            "-start_number",
            str(start_number),
            "-i",
            input_pattern,
            "-frames:v",
            "1",
            # str(thumbnail_count),
            "-filter_complex",
            f"tile={columns}x{rows}",
            "-c:v",
            "png",
            "-q:v",
            str(config.quality),
            "-f",
            "image2",
            str(sprite_path.with_suffix(".png")),
        ]

        logger.debug(f"Sprite command: {' '.join(command)}")
        return command

    def _generate_vtt(
        self,
        config: SpriteConfig,
        sprite_paths: list[Path],
        thumbnail_count: int,
        sheet_count: int,
    ) -> Path:
        """
        Generate WebVTT file with sprite coordinates for one or more sprite sheets.

        Args:
            config: Sprite configuration
            sprite_paths: List of paths to sprite sheets
            thumbnail_count: Total number of thumbnails
            sheet_count: Number of sprite sheets

        Returns:
            Path to WebVTT file
        """
        vtt_path = self.output_dir / "sprite.vtt"

        logger.debug(f"Generating WebVTT: {vtt_path.name}")

        tiles_per_sheet = config.columns * config.rows

        # Generate VTT content
        vtt_lines = ["WEBVTT", ""]

        for i in range(thumbnail_count):
            # Calculate time range
            start_time = i * config.interval
            end_time = min(start_time + config.interval, self.duration)

            # Determine which sprite sheet this thumbnail is in
            sheet_idx = i // tiles_per_sheet
            thumb_in_sheet = i % tiles_per_sheet

            # Calculate tile position within the sheet
            col = thumb_in_sheet % config.columns
            row = thumb_in_sheet // config.columns

            # Calculate coordinates (x, y, width, height)
            x = col * config.width
            y = row * config.height
            w = config.width
            h = config.height

            # Format timestamps
            start_str = self._format_vtt_timestamp(start_time)
            end_str = self._format_vtt_timestamp(end_time)

            # Get sprite filename
            sprite_name = sprite_paths[sheet_idx].name

            # Add cue
            vtt_lines.extend(
                [
                    f"{start_str} --> {end_str}",
                    f"{sprite_name}#xywh={x},{y},{w},{h}",
                    "",
                ]
            )

        # Write VTT file
        vtt_path.write_text("\n".join(vtt_lines), encoding="utf-8")

        logger.debug(
            f"Generated WebVTT with {thumbnail_count} cues across {sheet_count} sprite sheet(s)"
        )
        return vtt_path

    def _format_vtt_timestamp(self, seconds: float) -> str:
        """
        Format timestamp for WebVTT (HH:MM:SS.mmm).

        Args:
            seconds: Time in seconds

        Returns:
            Formatted timestamp
        """
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = seconds % 60

        return f"{hours:02d}:{minutes:02d}:{secs:06.3f}"

    def _cleanup_temp_files(self, temp_dir: Path) -> None:
        """
        Clean up temporary thumbnail files.

        Args:
            temp_dir: Temporary directory to clean
        """
        if not temp_dir.exists():
            return

        try:
            # Remove all thumbnail files
            for thumb_file in temp_dir.glob("thumb_*.jpg"):
                thumb_file.unlink()

            # Remove temp directory
            temp_dir.rmdir()

            logger.debug(f"Cleaned up temporary files in {temp_dir}")

        except Exception as e:
            logger.warning(f"Failed to cleanup temp files: {e}")


async def generate_sprite(
    input_file: Path,
    output_dir: Path,
    duration: float,
    config: Optional[SpriteConfig] = None,
    progress_callback: Optional[Callable[[float, Optional[float]], None]] = None,
    timeout: Optional[float] = None,
) -> SpriteInfo:
    """
    Convenience function to generate sprite sheet.

    Args:
        input_file: Source video file
        output_dir: Output directory
        duration: Video duration in seconds
        config: Sprite configuration
        progress_callback: Progress callback (current, total)
        timeout: Maximum generation time

    Returns:
        SpriteInfo with paths and metadata
    """
    generator = SpriteGenerator(input_file, output_dir, duration)
    return await generator.generate(config, progress_callback, timeout)
