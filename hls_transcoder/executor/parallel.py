"""
Parallel task execution for transcoding operations.

This module provides parallel execution of video, audio, subtitle, and sprite
tasks with resource management, error recovery, and progress tracking.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Callable, Optional

from ..config import TranscoderConfig
from ..hardware import HardwareInfo
from ..models import (
    AudioStream,
    AudioTask,
    MediaInfo,
    SubtitleStream,
    SubtitleTask,
    SpriteTask,
    TaskStatus,
    TranscodingTask,
    VideoStream,
    VideoTask,
)
from ..sprites import SpriteConfig, SpriteGenerator
from ..transcoder import AudioExtractor, AudioQuality, SubtitleExtractor, VideoTranscoder
from ..utils import TranscodingError, get_logger

if TYPE_CHECKING:
    from ..planner import ExecutionStrategy

logger = get_logger(__name__)


@dataclass
class ExecutionResult:
    """Result of task execution."""

    task: TranscodingTask
    success: bool
    output_path: Optional[Path] = None
    error: Optional[str] = None
    duration: float = 0.0


@dataclass
class ExecutionSummary:
    """Summary of parallel execution."""

    total_tasks: int
    completed_tasks: int
    failed_tasks: int
    cancelled_tasks: int
    total_duration: float
    results: list[ExecutionResult]

    @property
    def success_rate(self) -> float:
        """Calculate success rate."""
        if self.total_tasks == 0:
            return 0.0
        return (self.completed_tasks / self.total_tasks) * 100

    @property
    def has_failures(self) -> bool:
        """Check if any tasks failed."""
        return self.failed_tasks > 0


class ParallelExecutor:
    """
    Executes transcoding tasks in parallel with resource management.

    Manages concurrent execution of video, audio, subtitle, and sprite tasks
    with proper resource allocation, error handling, and progress tracking.
    """

    def __init__(
        self,
        input_file: Path,
        output_dir: Path,
        media_info: MediaInfo,
        hardware_info: HardwareInfo,
        config: TranscoderConfig,
        strategy: ExecutionStrategy,
    ):
        """
        Initialize parallel executor.

        Args:
            input_file: Source media file
            output_dir: Output directory for all results
            media_info: Media information
            hardware_info: Hardware capabilities
            config: Transcoder configuration
            strategy: Execution strategy with concurrency settings
        """
        self.input_file = input_file
        self.output_dir = output_dir
        self.media_info = media_info
        self.hardware_info = hardware_info
        self.config = config
        self.strategy = strategy

        # Create output directory
        self.output_dir.mkdir(parents=True, exist_ok=True)

        # Semaphores for concurrency control
        self._video_semaphore = asyncio.Semaphore(strategy.video_concurrency)
        self._audio_semaphore = asyncio.Semaphore(strategy.audio_concurrency)
        self._subtitle_semaphore = asyncio.Semaphore(strategy.subtitle_concurrency)

        # Track active tasks
        self._active_tasks: set[asyncio.Task] = set()
        self._results: list[ExecutionResult] = []
        self._cancelled = False

        logger.info(
            f"Initialized ParallelExecutor with strategy: "
            f"video={strategy.video_concurrency}, "
            f"audio={strategy.audio_concurrency}, "
            f"subtitle={strategy.subtitle_concurrency}"
        )

    async def execute_tasks(
        self,
        video_tasks: list[VideoTask],
        audio_tasks: list[AudioTask],
        subtitle_tasks: list[SubtitleTask],
        sprite_task: Optional[SpriteTask] = None,
        progress_callback: Optional[Callable[[int, int], None]] = None,
    ) -> ExecutionSummary:
        """
        Execute all transcoding tasks in parallel.

        Args:
            video_tasks: List of video transcoding tasks
            audio_tasks: List of audio extraction tasks
            subtitle_tasks: List of subtitle extraction tasks
            sprite_task: Optional sprite generation task
            progress_callback: Callback with (completed, total) counts

        Returns:
            ExecutionSummary with results

        Raises:
            TranscodingError: If execution fails critically
        """
        start_time = time.time()
        total_tasks = len(video_tasks) + len(audio_tasks) + len(subtitle_tasks)
        if sprite_task:
            total_tasks += 1

        logger.info(f"Starting parallel execution of {total_tasks} tasks")

        try:
            # Create all task coroutines
            task_coroutines = []

            # Video tasks
            for video_task in video_tasks:
                task_coroutines.append(
                    self._execute_video_task(video_task, progress_callback, total_tasks)
                )

            # Audio tasks
            for audio_task in audio_tasks:
                task_coroutines.append(
                    self._execute_audio_task(audio_task, progress_callback, total_tasks)
                )

            # Subtitle tasks
            for subtitle_task in subtitle_tasks:
                task_coroutines.append(
                    self._execute_subtitle_task(subtitle_task, progress_callback, total_tasks)
                )

            # Sprite task (if sprite_separate, run after others)
            if sprite_task and not self.strategy.sprite_separate:
                task_coroutines.append(
                    self._execute_sprite_task(sprite_task, progress_callback, total_tasks)
                )

            # Execute all tasks concurrently
            await asyncio.gather(*task_coroutines, return_exceptions=True)

            # Execute sprite separately if needed
            if sprite_task and self.strategy.sprite_separate:
                logger.info("Executing sprite task separately")
                await self._execute_sprite_task(sprite_task, progress_callback, total_tasks)

            # Calculate summary
            duration = time.time() - start_time
            completed = sum(1 for r in self._results if r.success)
            failed = sum(1 for r in self._results if not r.success)
            cancelled = total_tasks - len(self._results)

            summary = ExecutionSummary(
                total_tasks=total_tasks,
                completed_tasks=completed,
                failed_tasks=failed,
                cancelled_tasks=cancelled,
                total_duration=duration,
                results=self._results.copy(),
            )

            logger.info(
                f"Execution complete: {completed}/{total_tasks} tasks succeeded "
                f"in {duration:.2f}s (success rate: {summary.success_rate:.1f}%)"
            )

            return summary

        except Exception as e:
            error_msg = f"Parallel execution failed: {e}"
            logger.error(error_msg)
            raise TranscodingError(error_msg) from e

    async def _execute_video_task(
        self,
        task: VideoTask,
        progress_callback: Optional[Callable[[int, int], None]],
        total_tasks: int,
    ) -> ExecutionResult:
        """
        Execute video transcoding task.

        Args:
            task: Video task to execute
            progress_callback: Progress callback
            total_tasks: Total number of tasks

        Returns:
            ExecutionResult
        """
        async with self._video_semaphore:
            return await self._run_task(
                task,
                self._do_video_transcode,
                progress_callback,
                total_tasks,
            )

    async def _execute_audio_task(
        self,
        task: AudioTask,
        progress_callback: Optional[Callable[[int, int], None]],
        total_tasks: int,
    ) -> ExecutionResult:
        """
        Execute audio extraction task.

        Args:
            task: Audio task to execute
            progress_callback: Progress callback
            total_tasks: Total number of tasks

        Returns:
            ExecutionResult
        """
        async with self._audio_semaphore:
            return await self._run_task(
                task,
                self._do_audio_extract,
                progress_callback,
                total_tasks,
            )

    async def _execute_subtitle_task(
        self,
        task: SubtitleTask,
        progress_callback: Optional[Callable[[int, int], None]],
        total_tasks: int,
    ) -> ExecutionResult:
        """
        Execute subtitle extraction task.

        Args:
            task: Subtitle task to execute
            progress_callback: Progress callback
            total_tasks: Total number of tasks

        Returns:
            ExecutionResult
        """
        async with self._subtitle_semaphore:
            return await self._run_task(
                task,
                self._do_subtitle_extract,
                progress_callback,
                total_tasks,
            )

    async def _execute_sprite_task(
        self,
        task: SpriteTask,
        progress_callback: Optional[Callable[[int, int], None]],
        total_tasks: int,
    ) -> ExecutionResult:
        """
        Execute sprite generation task.

        Args:
            task: Sprite task to execute
            progress_callback: Progress callback
            total_tasks: Total number of tasks

        Returns:
            ExecutionResult
        """
        # Sprites don't use semaphore (controlled by sprite_separate flag)
        return await self._run_task(
            task,
            self._do_sprite_generate,
            progress_callback,
            total_tasks,
        )

    async def _run_task(
        self,
        task: TranscodingTask,
        executor_func: Callable,
        progress_callback: Optional[Callable[[int, int], None]],
        total_tasks: int,
    ) -> ExecutionResult:
        """
        Run a task with error handling and status tracking.

        Args:
            task: Task to execute
            executor_func: Function to execute the task
            progress_callback: Progress callback
            total_tasks: Total number of tasks

        Returns:
            ExecutionResult
        """
        if self._cancelled:
            task.status = TaskStatus.CANCELLED
            return ExecutionResult(
                task=task,
                success=False,
                error="Execution cancelled",
            )

        start_time = time.time()
        task.status = TaskStatus.RUNNING
        task.started_at = start_time

        logger.info(f"Starting task {task.task_id} ({task.task_type.value})")

        try:
            # Execute the task
            output_path = await executor_func(task)

            # Mark as completed
            task.status = TaskStatus.COMPLETED
            task.completed_at = time.time()
            task.progress = 1.0

            result = ExecutionResult(
                task=task,
                success=True,
                output_path=output_path,
                duration=task.completed_at - start_time,
            )

            self._results.append(result)

            # Update progress
            if progress_callback:
                completed = len(self._results)
                progress_callback(completed, total_tasks)

            logger.info(f"Completed task {task.task_id} in {result.duration:.2f}s")

            return result

        except Exception as e:
            # Mark as failed
            task.status = TaskStatus.FAILED
            task.completed_at = time.time()
            error_msg = str(e)
            task.error = error_msg

            result = ExecutionResult(
                task=task,
                success=False,
                error=error_msg,
                duration=time.time() - start_time,
            )

            self._results.append(result)

            # Update progress
            if progress_callback:
                completed = len(self._results)
                progress_callback(completed, total_tasks)

            logger.error(f"Task {task.task_id} failed: {error_msg}")

            return result

    async def _do_video_transcode(self, task: VideoTask) -> Path:
        """
        Execute video transcoding.

        Args:
            task: Video task

        Returns:
            Output playlist path
        """
        # Get video stream
        video_stream = next(
            (s for s in self.media_info.video_streams if s.index == task.stream_index),
            None,
        )
        if not video_stream:
            raise TranscodingError(f"Video stream {task.stream_index} not found")

        # Create transcoder
        transcoder = VideoTranscoder(
            input_file=self.input_file,
            output_dir=task.output_dir,
            hardware_info=self.hardware_info,
            video_stream=video_stream,
        )

        # Create quality configuration from task
        from ..transcoder.video import VideoQuality

        # Parse bitrate string to integer (e.g., "5000k" -> 5000)
        bitrate_str = task.bitrate.replace("M", "000").replace("k", "").replace("K", "")
        bitrate_kbps = int(bitrate_str)

        quality = VideoQuality(
            name=task.quality,
            height=task.height,
            bitrate=bitrate_kbps,
            maxrate=int(bitrate_kbps * 1.5),  # 1.5x bitrate
            bufsize=bitrate_kbps * 2,  # 2x bitrate
        )

        # Transcode
        def on_progress(current: float, total: Optional[float] = None):
            task.progress = current
            # Store speed for monitoring (total is used for speed calculation internally)
            if total is not None:
                task.speed = total

        output_path = await transcoder.transcode(
            quality=quality,
            progress_callback=on_progress,
        )

        return output_path

    async def _do_audio_extract(self, task: AudioTask) -> Path:
        """
        Execute audio extraction.

        Args:
            task: Audio task

        Returns:
            Output playlist path
        """
        # Get audio stream
        audio_stream = next(
            (s for s in self.media_info.audio_streams if s.index == task.stream_index),
            None,
        )
        if not audio_stream:
            raise TranscodingError(f"Audio stream {task.stream_index} not found")

        # Create extractor
        extractor = AudioExtractor(
            input_file=self.input_file,
            output_dir=task.output_dir,
        )

        # Create quality from task bitrate and config
        bitrate_value = int(task.bitrate.replace("k", "").replace("K", ""))

        # Get channels and sample_rate from config, handle "auto"
        # "auto" means use source stream values (represented as 0)
        if (
            isinstance(self.config.audio.channels, str)
            and self.config.audio.channels.lower() == "auto"
        ):
            channels = 0  # 0 means "use source channels"
        else:
            channels = int(self.config.audio.channels)

        if (
            isinstance(self.config.audio.sample_rate, str)
            and self.config.audio.sample_rate.lower() == "auto"
        ):
            sample_rate = 0  # 0 means "use source sample rate"
        else:
            sample_rate = int(self.config.audio.sample_rate)

        quality = AudioQuality(
            name=f"audio_{bitrate_value}k",
            bitrate=bitrate_value,
            sample_rate=sample_rate,
            channels=channels,
        )

        # Extract
        def on_progress(current: float, total: Optional[float] = None):
            task.progress = current
            if total is not None:
                task.speed = total

        output_path = await extractor.extract(
            audio_stream=audio_stream,
            quality=quality,
            progress_callback=on_progress,
            segment_duration=self.config.audio.segment_duration,
            copy_if_possible=self.config.audio.copy_if_possible,
        )

        return output_path

    async def _do_subtitle_extract(self, task: SubtitleTask) -> Path:
        """
        Execute subtitle extraction.

        Args:
            task: Subtitle task

        Returns:
            Output subtitle path
        """
        # Get subtitle stream
        subtitle_stream = next(
            (s for s in self.media_info.subtitle_streams if s.index == task.stream_index),
            None,
        )
        if not subtitle_stream:
            raise TranscodingError(f"Subtitle stream {task.stream_index} not found")

        # Create extractor
        extractor = SubtitleExtractor(
            input_file=self.input_file,
            output_dir=task.output_dir,
        )

        # Extract
        def on_progress(current: float, total: Optional[float] = None):
            task.progress = current

        output_path = await extractor.extract(
            subtitle_stream=subtitle_stream,
            output_format=task.format,
            progress_callback=on_progress,
        )

        return output_path

    async def _do_sprite_generate(self, task: SpriteTask) -> Path:
        """
        Execute sprite generation.

        Args:
            task: Sprite task

        Returns:
            Output sprite VTT path
        """
        # Create generator
        generator = SpriteGenerator(
            input_file=self.input_file,
            output_dir=task.output_dir,
            duration=self.media_info.duration,
        )

        # Create config from task
        config = SpriteConfig(
            interval=task.interval,
            width=task.width,
            height=task.height,
            columns=task.columns,
            rows=task.rows,
        )

        # Generate
        def on_progress(current: float, total: Optional[float] = None):
            task.progress = current

        sprite_info = await generator.generate(
            config=config,
            progress_callback=on_progress,
        )

        return sprite_info.vtt_path

    async def cancel(self) -> None:
        """Cancel all running tasks."""
        logger.warning("Cancelling all tasks")
        self._cancelled = True

        # Cancel all active asyncio tasks
        for task in self._active_tasks:
            if not task.done():
                task.cancel()

        # Wait for tasks to finish cancelling
        if self._active_tasks:
            await asyncio.gather(*self._active_tasks, return_exceptions=True)

        logger.info("All tasks cancelled")

    @property
    def is_cancelled(self) -> bool:
        """Check if execution is cancelled."""
        return self._cancelled

    @property
    def completed_count(self) -> int:
        """Get number of completed tasks."""
        return sum(1 for r in self._results if r.success)

    @property
    def failed_count(self) -> int:
        """Get number of failed tasks."""
        return sum(1 for r in self._results if not r.success)


async def execute_parallel(
    input_file: Path,
    output_dir: Path,
    media_info: MediaInfo,
    hardware_info: HardwareInfo,
    config: TranscoderConfig,
    strategy: ExecutionStrategy,
    video_tasks: list[VideoTask],
    audio_tasks: list[AudioTask],
    subtitle_tasks: list[SubtitleTask],
    sprite_task: Optional[SpriteTask] = None,
    progress_callback: Optional[Callable[[int, int], None]] = None,
) -> ExecutionSummary:
    """
    Convenience function for parallel execution.

    Args:
        input_file: Source media file
        output_dir: Output directory
        media_info: Media information
        hardware_info: Hardware capabilities
        config: Transcoder configuration
        strategy: Execution strategy
        video_tasks: Video tasks
        audio_tasks: Audio tasks
        subtitle_tasks: Subtitle tasks
        sprite_task: Optional sprite task
        progress_callback: Progress callback

    Returns:
        ExecutionSummary
    """
    executor = ParallelExecutor(
        input_file=input_file,
        output_dir=output_dir,
        media_info=media_info,
        hardware_info=hardware_info,
        config=config,
        strategy=strategy,
    )

    return await executor.execute_tasks(
        video_tasks=video_tasks,
        audio_tasks=audio_tasks,
        subtitle_tasks=subtitle_tasks,
        sprite_task=sprite_task,
        progress_callback=progress_callback,
    )
