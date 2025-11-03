"""
Transcoding execution planning and strategy.

This module provides planning functionality for transcoding operations,
including quality ladder calculation, resource allocation, and estimation
of output size and duration.
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

from ..config import TranscoderConfig, QualityVariant
from ..hardware import HardwareInfo
from ..hardware.detector import HardwareType
from ..models import (
    AudioStream,
    AudioTask,
    MediaInfo,
    SpriteTask,
    SubtitleStream,
    SubtitleTask,
    TaskPlan,
    TaskType,
    VideoStream,
    VideoTask,
)
from ..transcoder import AUDIO_QUALITY_PRESETS, QUALITY_PRESETS, AudioQuality, VideoQuality
from ..utils import (
    calculate_segment_count,
    calculate_target_resolution,
    get_logger,
    get_quality_from_height,
    should_include_quality,
)

logger = get_logger(__name__)


@dataclass
class ResourceEstimate:
    """Estimation of resources needed for transcoding."""

    estimated_duration: float  # Estimated total time in seconds
    estimated_output_size: int  # Estimated output size in bytes
    peak_memory_mb: int  # Estimated peak memory usage in MB
    disk_space_needed: int  # Required disk space in bytes
    cpu_cores_needed: int  # Recommended CPU cores
    gpu_memory_mb: int  # Estimated GPU memory usage in MB (0 for CPU)

    @property
    def duration_per_task(self) -> float:
        """Get average duration per task."""
        return self.estimated_duration

    @property
    def space_with_buffer(self) -> int:
        """Get required disk space with 20% buffer."""
        return int(self.disk_space_needed * 1.2)


@dataclass
class ExecutionStrategy:
    """Strategy for parallel execution."""

    video_concurrency: int  # Concurrent video tasks
    audio_concurrency: int  # Concurrent audio tasks
    subtitle_concurrency: int  # Concurrent subtitle tasks
    sprite_separate: bool  # Run sprites separately
    max_total_concurrent: int  # Maximum total concurrent tasks

    def __post_init__(self) -> None:
        """Validate concurrency values."""
        if self.video_concurrency < 1:
            self.video_concurrency = 1
        if self.audio_concurrency < 1:
            self.audio_concurrency = 1
        if self.subtitle_concurrency < 1:
            self.subtitle_concurrency = 1
        if self.max_total_concurrent < 1:
            self.max_total_concurrent = 1

    @property
    def total_workers(self) -> int:
        """Get total number of workers."""
        return (
            self.video_concurrency
            + self.audio_concurrency
            + self.subtitle_concurrency
            + (1 if self.sprite_separate else 0)
        )


class ExecutionPlanner:
    """
    Plans transcoding execution with resource allocation and estimation.

    This class analyzes source media, hardware capabilities, and configuration
    to create an optimal execution plan with quality ladder, task allocation,
    and resource estimates.
    """

    def __init__(
        self,
        input_file: Path,
        media_info: MediaInfo,
        hardware_info: HardwareInfo,
        config: TranscoderConfig,
        output_dir: Path,
        profile_name: str = "medium",
    ):
        """
        Initialize execution planner.

        Args:
            input_file: Source media file path
            media_info: Source media information
            hardware_info: Hardware acceleration information
            config: Transcoder configuration
            output_dir: Output directory for transcoded files
            profile_name: Quality profile name to use
        """
        self.input_file = input_file
        self.media_info = media_info
        self.hardware_info = hardware_info
        self.config = config
        self.output_dir = output_dir
        self.profile_name = profile_name

        # Get profile configuration
        self.profile = config.get_profile(profile_name)
        if not self.profile:
            raise ValueError(f"Profile '{profile_name}' not found in configuration")

        logger.info(
            f"Initialized ExecutionPlanner for {input_file.name} " f"with profile '{profile_name}'"
        )

    def create_plan(
        self,
        include_audio: bool = True,
        include_subtitles: bool = True,
        include_sprites: bool = True,
        original_only: bool = False,
    ) -> TaskPlan:
        """
        Create complete execution plan.

        Args:
            include_audio: Include audio extraction tasks
            include_subtitles: Include subtitle extraction tasks
            include_sprites: Include sprite generation task
            original_only: Only transcode at original resolution (no downscaling)

        Returns:
            Complete task plan with all tasks
        """
        logger.info("Creating execution plan...")

        # Create task plan
        plan = TaskPlan()

        # Calculate quality ladder and create video tasks
        video_qualities = self._calculate_quality_ladder(original_only)
        plan.video_tasks = self._create_video_tasks(video_qualities)
        logger.info(f"Created {len(plan.video_tasks)} video tasks")

        # Create audio tasks
        if include_audio and self.media_info.audio_streams:
            plan.audio_tasks = self._create_audio_tasks()
            logger.info(f"Created {len(plan.audio_tasks)} audio tasks")

        # Create subtitle tasks
        if include_subtitles and self.media_info.subtitle_streams:
            plan.subtitle_tasks = self._create_subtitle_tasks()
            logger.info(f"Created {len(plan.subtitle_tasks)} subtitle tasks")

        # Create sprite task
        if include_sprites and self.config.sprites.enabled:
            plan.sprite_task = self._create_sprite_task()
            logger.info("Created sprite generation task")

        # Estimate resources
        estimate = self.estimate_resources(plan)
        plan.estimated_duration = estimate.estimated_duration
        plan.estimated_size = estimate.estimated_output_size

        logger.info(
            f"Plan complete: {plan.total_tasks} tasks, "
            f"~{estimate.estimated_duration:.1f}s, "
            f"~{estimate.estimated_output_size / (1024**3):.2f} GB"
        )

        return plan

    def _calculate_quality_ladder(self, original_only: bool = False) -> List[VideoQuality]:
        """
        Calculate quality ladder based on source resolution and profile.

        Args:
            original_only: If True, only include original resolution

        Returns:
            List of video quality presets to transcode
        """
        if not self.media_info.video_streams:
            return []

        source_video = self.media_info.video_streams[0]
        source_height = source_video.height
        source_width = source_video.width

        logger.debug(f"Calculating quality ladder from source: {source_width}x{source_height}")

        # If original_only, create a single quality variant at source resolution
        if original_only:
            source_quality_name = get_quality_from_height(source_height) or f"{source_height}p"

            # Find matching preset or create custom
            if source_quality_name in QUALITY_PRESETS:
                base_quality = QUALITY_PRESETS[source_quality_name]
                # Use source dimensions for non-standard aspect ratios
                original_quality = VideoQuality(
                    name="original",
                    height=source_height,
                    bitrate=base_quality.bitrate,
                    maxrate=base_quality.maxrate,
                    bufsize=base_quality.bufsize,
                    custom_width=source_width,
                )
            else:
                # Create custom quality for non-standard resolutions
                # Estimate bitrate based on pixel count (rule of thumb: ~0.1 bits per pixel)
                pixel_count = source_width * source_height
                estimated_bitrate = int(pixel_count * 0.1 / 1000)  # Convert to kbps

                original_quality = VideoQuality(
                    name="original",
                    height=source_height,
                    bitrate=estimated_bitrate,
                    maxrate=int(estimated_bitrate * 1.5),
                    bufsize=int(estimated_bitrate * 2),
                    custom_width=source_width,
                )

            logger.info(f"Original-only mode: using {original_quality.resolution}")
            return [original_quality]

        # Build quality ladder from profile variants
        qualities: List[VideoQuality] = []

        if not self.profile:
            logger.warning("No profile variants found")
            return []

        # self.profile is a list of QualityVariant
        for variant in self.profile:
            # Skip "original" placeholder in config
            if variant.quality == "original":
                continue

            # Get standard quality preset
            if variant.quality not in QUALITY_PRESETS:
                logger.warning(f"Unknown quality preset: {variant.quality}")
                continue

            quality_preset = QUALITY_PRESETS[variant.quality]

            # Check if we should include this quality
            if not should_include_quality(source_height, variant.quality, allow_upscaling=False):
                logger.debug(f"Skipping {variant.quality} (would require upscaling)")
                continue

            # Calculate target resolution maintaining aspect ratio
            target_width, target_height = calculate_target_resolution(
                source_width, source_height, variant.quality
            )

            # Create quality variant with custom dimensions
            custom_quality = VideoQuality(
                name=variant.quality,
                height=target_height,
                bitrate=quality_preset.bitrate,
                maxrate=quality_preset.maxrate,
                bufsize=quality_preset.bufsize,
                custom_width=target_width,
            )

            qualities.append(custom_quality)

        # Sort by height descending (highest quality first)
        qualities.sort(key=lambda q: q.height, reverse=True)

        logger.info(
            f"Quality ladder: {', '.join(q.name for q in qualities)} "
            f"({len(qualities)} variants)"
        )

        return qualities

    def _create_video_tasks(self, qualities: List[VideoQuality]) -> List[VideoTask]:
        """
        Create video transcoding tasks for each quality variant.

        Args:
            qualities: List of quality presets

        Returns:
            List of video tasks
        """
        tasks: List[VideoTask] = []

        if not self.media_info.video_streams:
            return tasks

        source_video = self.media_info.video_streams[0]

        # Get encoder name from selected encoder or detected type
        encoder_name = "libx264"  # Default software encoder
        if self.hardware_info.selected_encoder:
            encoder_name = self.hardware_info.selected_encoder.name
        elif self.hardware_info.detected_type != HardwareType.SOFTWARE:
            # Try to get first available encoder for detected type
            encoder = self.hardware_info.get_encoder(self.hardware_info.detected_type)
            if encoder:
                encoder_name = encoder.name

        for quality in qualities:
            task_id = f"video_{quality.name}"
            output_path = self.output_dir / f"video_{quality.name}"

            task = VideoTask(
                task_id=task_id,
                task_type=TaskType.VIDEO,
                input_file=self.input_file,
                output_dir=output_path,
                quality=quality.name,
                width=quality.width,
                height=quality.height,
                bitrate=f"{quality.bitrate}k",
                encoder=encoder_name,
                stream_index=source_video.index,
            )

            tasks.append(task)

        return tasks

    def _create_audio_tasks(self) -> List[AudioTask]:
        """
        Create audio extraction tasks for each audio stream.

        Returns:
            List of audio tasks
        """
        tasks: List[AudioTask] = []

        for audio_stream in self.media_info.audio_streams:
            language = audio_stream.language or "und"
            task_id = f"audio_{audio_stream.index}_{language}"
            output_path = self.output_dir / f"audio_{language}"

            task = AudioTask(
                task_id=task_id,
                task_type=TaskType.AUDIO,
                input_file=self.input_file,
                output_dir=output_path,
                stream_index=audio_stream.index,
                language=language,
                codec=self.config.audio.codec,
                bitrate=self.config.audio.bitrate,
            )

            tasks.append(task)

        return tasks

    def _create_subtitle_tasks(self) -> List[SubtitleTask]:
        """
        Create subtitle extraction tasks for each subtitle stream.

        Returns:
            List of subtitle tasks
        """
        tasks: List[SubtitleTask] = []

        for subtitle_stream in self.media_info.subtitle_streams:
            language = subtitle_stream.language or "und"
            task_id = f"subtitle_{subtitle_stream.index}_{language}"
            output_path = self.output_dir / f"subtitles"

            task = SubtitleTask(
                task_id=task_id,
                task_type=TaskType.SUBTITLE,
                input_file=self.input_file,
                output_dir=output_path,
                stream_index=subtitle_stream.index,
                language=language,
                format="webvtt",
            )

            tasks.append(task)

        return tasks

    def _create_sprite_task(self) -> SpriteTask:
        """
        Create sprite generation task.

        Returns:
            Sprite task
        """
        task_id = "sprites"
        output_path = self.output_dir / "sprites"

        task = SpriteTask(
            task_id=task_id,
            task_type=TaskType.SPRITE,
            input_file=self.input_file,
            output_dir=output_path,
            interval=self.config.sprites.interval,
            width=self.config.sprites.width,
            height=self.config.sprites.height,
            columns=self.config.sprites.columns,
            rows=self.config.sprites.rows,
        )

        return task

    def estimate_resources(self, plan: TaskPlan) -> ResourceEstimate:
        """
        Estimate resources needed for execution plan.

        Args:
            plan: Task plan to estimate

        Returns:
            Resource estimates
        """
        # Get source video info
        if not self.media_info.video_streams:
            return ResourceEstimate(0, 0, 0, 0, 0, 0)

        source_video = self.media_info.video_streams[0]
        duration = source_video.duration or self.media_info.format.duration

        # Estimate transcoding speed based on hardware
        speed_multiplier = self._get_speed_multiplier()

        # Estimate video duration (all variants in parallel)
        video_duration = (duration / speed_multiplier) if plan.video_tasks else 0

        # Estimate audio duration (parallel extraction)
        audio_duration = (duration / 4.0) if plan.audio_tasks else 0  # Audio is fast

        # Estimate subtitle duration (very fast)
        subtitle_duration = (duration / 10.0) if plan.subtitle_tasks else 0

        # Estimate sprite duration
        sprite_duration = (duration / 5.0) if plan.sprite_task else 0

        # Total duration (assuming parallel execution)
        total_duration = max(video_duration, audio_duration, subtitle_duration, sprite_duration)

        # Estimate output size
        total_size = self._estimate_output_size(plan, duration)

        # Estimate memory usage
        peak_memory = self._estimate_memory_usage(plan)

        # Estimate disk space (including temp files)
        disk_space = int(total_size * 1.3)  # 30% overhead for temp files

        # CPU cores recommendation
        cpu_cores = min(plan.total_tasks, 8)  # Max 8 cores

        # GPU memory (only for hardware encoding)
        gpu_memory = 0
        if self.hardware_info.detected_type != HardwareType.SOFTWARE:
            # Rough estimate: 500MB per concurrent video task
            gpu_memory = len(plan.video_tasks) * 500

        estimate = ResourceEstimate(
            estimated_duration=total_duration,
            estimated_output_size=total_size,
            peak_memory_mb=peak_memory,
            disk_space_needed=disk_space,
            cpu_cores_needed=cpu_cores,
            gpu_memory_mb=gpu_memory,
        )

        logger.debug(
            f"Resource estimate: {total_duration:.1f}s, "
            f"{total_size / (1024**3):.2f}GB, "
            f"{peak_memory}MB RAM"
        )

        return estimate

    def _get_speed_multiplier(self) -> float:
        """
        Get encoding speed multiplier based on hardware.

        Returns:
            Speed multiplier (higher = faster)
        """
        # Speed estimates relative to real-time
        speed_map = {
            HardwareType.NVIDIA: 3.0,  # NVENC is very fast
            HardwareType.INTEL: 2.5,  # QSV is fast
            HardwareType.AMD: 2.5,  # AMF is fast
            HardwareType.APPLE: 2.5,  # VideoToolbox is fast
            HardwareType.VAAPI: 2.0,  # VAAPI varies
            HardwareType.SOFTWARE: 0.5,  # CPU is slow
        }
        return speed_map.get(self.hardware_info.detected_type, 1.0)

    def _estimate_output_size(self, plan: TaskPlan, duration: float) -> int:
        """
        Estimate total output size.

        Args:
            plan: Task plan
            duration: Video duration in seconds

        Returns:
            Estimated size in bytes
        """
        total_size = 0

        # Video size estimation
        for task in plan.video_tasks:
            # Parse bitrate (e.g., "5000k" -> 5000000 bits/sec)
            bitrate_kbps = int(task.bitrate.rstrip("k"))
            bitrate_bps = bitrate_kbps * 1000

            # Size = bitrate * duration (in bytes)
            video_size = int((bitrate_bps * duration) / 8)
            total_size += video_size

        # Audio size estimation
        for task in plan.audio_tasks:
            # Parse bitrate (e.g., "128k" -> 128000 bits/sec)
            bitrate_kbps = int(task.bitrate.rstrip("k"))
            bitrate_bps = bitrate_kbps * 1000

            # Size = bitrate * duration (in bytes)
            audio_size = int((bitrate_bps * duration) / 8)
            total_size += audio_size

        # Subtitle size (very small, ~50KB per track)
        total_size += len(plan.subtitle_tasks) * 50 * 1024

        # Sprite size (estimate ~100KB per sprite sheet)
        if plan.sprite_task:
            segment_count = calculate_segment_count(duration, plan.sprite_task.interval)
            sheets = (
                segment_count + plan.sprite_task.thumbnails_per_sheet - 1
            ) // plan.sprite_task.thumbnails_per_sheet
            total_size += sheets * 100 * 1024

        return total_size

    def _estimate_memory_usage(self, plan: TaskPlan) -> int:
        """
        Estimate peak memory usage in MB.

        Args:
            plan: Task plan

        Returns:
            Estimated memory in MB
        """
        # Base memory for FFmpeg process
        base_memory = 100  # MB

        # Memory per video task (varies by resolution)
        video_memory = 0
        for task in plan.video_tasks:
            # Rough estimate based on resolution
            pixels = task.width * task.height
            task_memory = int((pixels / 1_000_000) * 50)  # ~50MB per megapixel
            video_memory += task_memory

        # Memory per audio task (small)
        audio_memory = len(plan.audio_tasks) * 50  # MB

        # Memory for sprites (image processing)
        sprite_memory = 200 if plan.sprite_task else 0  # MB

        # Total peak memory (concurrent tasks)
        peak_memory = base_memory + video_memory + audio_memory + sprite_memory

        return peak_memory

    def create_execution_strategy(
        self,
        plan: TaskPlan,
        max_concurrent: Optional[int] = None,
    ) -> ExecutionStrategy:
        """
        Create optimal execution strategy based on plan and resources.

        Args:
            plan: Task plan
            max_concurrent: Maximum concurrent tasks (default: from config)

        Returns:
            Execution strategy
        """
        if max_concurrent is None:
            max_concurrent = self.config.performance.max_parallel_tasks

        # Calculate optimal concurrency for each task type
        video_count = len(plan.video_tasks)
        audio_count = len(plan.audio_tasks)
        subtitle_count = len(plan.subtitle_tasks)

        # Hardware limitations
        hw_limit = self.config.hardware.max_instances
        if self.hardware_info.detected_type == HardwareType.SOFTWARE:
            # CPU encoding: limit based on CPU cores
            import os

            cpu_count = os.cpu_count() or 4
            hw_limit = max(1, cpu_count // 2)  # Use half the cores

        # Video concurrency (limited by hardware)
        video_concurrency = min(video_count, hw_limit, max_concurrent)

        # Audio concurrency (less resource intensive)
        remaining = max_concurrent - video_concurrency
        audio_concurrency = min(audio_count, max(1, remaining // 2))

        # Subtitle concurrency (very light)
        remaining = max_concurrent - video_concurrency - audio_concurrency
        subtitle_concurrency = min(subtitle_count, max(1, remaining))

        # Run sprites separately if many other tasks
        sprite_separate = plan.sprite_task is not None and (video_count + audio_count) > 2

        strategy = ExecutionStrategy(
            video_concurrency=video_concurrency,
            audio_concurrency=audio_concurrency,
            subtitle_concurrency=subtitle_concurrency,
            sprite_separate=sprite_separate,
            max_total_concurrent=max_concurrent,
        )

        logger.info(
            f"Execution strategy: video={video_concurrency}, "
            f"audio={audio_concurrency}, subtitle={subtitle_concurrency}, "
            f"sprites={'separate' if sprite_separate else 'parallel'}"
        )

        return strategy


# Global planner instance (optional convenience)
_planner_instance: Optional[ExecutionPlanner] = None


def get_planner(
    input_file: Path,
    media_info: MediaInfo,
    hardware_info: HardwareInfo,
    config: TranscoderConfig,
    output_dir: Path,
    profile_name: str = "medium",
) -> ExecutionPlanner:
    """
    Get or create execution planner instance.

    Args:
        input_file: Source media file path
        media_info: Source media information
        hardware_info: Hardware acceleration information
        config: Transcoder configuration
        output_dir: Output directory
        profile_name: Quality profile name

    Returns:
        ExecutionPlanner instance
    """
    global _planner_instance

    # Always create new instance (planner is stateful per media file)
    _planner_instance = ExecutionPlanner(
        input_file, media_info, hardware_info, config, output_dir, profile_name
    )
    return _planner_instance
