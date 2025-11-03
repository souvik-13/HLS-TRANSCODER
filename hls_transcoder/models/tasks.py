"""
Data models for transcoding tasks.

This module contains dataclasses and enums for representing different types
of transcoding tasks and their execution plans.
"""

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Optional


class TaskType(Enum):
    """Type of transcoding task."""

    VIDEO = "video"
    AUDIO = "audio"
    SUBTITLE = "subtitle"
    SPRITE = "sprite"


class TaskStatus(Enum):
    """Status of a transcoding task."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class TranscodingTask:
    """Base class for transcoding tasks."""

    task_id: str
    task_type: TaskType
    input_file: Path
    output_dir: Path
    status: TaskStatus = TaskStatus.PENDING
    progress: float = 0.0
    speed: Optional[float] = None  # Processing speed (fps or Mbps)
    error: Optional[str] = None
    retry_count: int = 0
    started_at: Optional[float] = None
    completed_at: Optional[float] = None

    @property
    def is_complete(self) -> bool:
        """Check if task is completed."""
        return self.status == TaskStatus.COMPLETED

    @property
    def is_running(self) -> bool:
        """Check if task is running."""
        return self.status == TaskStatus.RUNNING

    @property
    def has_failed(self) -> bool:
        """Check if task has failed."""
        return self.status == TaskStatus.FAILED

    @property
    def duration(self) -> Optional[float]:
        """Calculate task duration if completed."""
        if self.started_at and self.completed_at:
            return self.completed_at - self.started_at
        return None


@dataclass
class VideoTask(TranscodingTask):
    """Video transcoding task."""

    quality: str = ""
    width: int = 0
    height: int = 0
    bitrate: str = ""
    crf: int = 23
    encoder: str = "libx264"
    stream_index: int = 0

    def __post_init__(self) -> None:
        """Set task type after initialization."""
        self.task_type = TaskType.VIDEO

    @property
    def resolution(self) -> str:
        """Get resolution as string."""
        return f"{self.width}x{self.height}"


@dataclass
class AudioTask(TranscodingTask):
    """Audio extraction task."""

    stream_index: int = 0
    language: str = "und"
    codec: str = "aac"
    bitrate: str = "128k"

    def __post_init__(self) -> None:
        """Set task type after initialization."""
        self.task_type = TaskType.AUDIO


@dataclass
class SubtitleTask(TranscodingTask):
    """Subtitle extraction task."""

    stream_index: int = 0
    language: str = "und"
    format: str = "webvtt"

    def __post_init__(self) -> None:
        """Set task type after initialization."""
        self.task_type = TaskType.SUBTITLE


@dataclass
class SpriteTask(TranscodingTask):
    """Sprite generation task."""

    interval: int = 10
    width: int = 160
    height: int = 90
    columns: int = 10
    rows: int = 10

    def __post_init__(self) -> None:
        """Set task type after initialization."""
        self.task_type = TaskType.SPRITE

    @property
    def grid_size(self) -> tuple[int, int]:
        """Get sprite grid size as tuple."""
        return (self.columns, self.rows)

    @property
    def thumbnails_per_sheet(self) -> int:
        """Calculate number of thumbnails per sprite sheet."""
        return self.columns * self.rows


@dataclass
class TaskPlan:
    """Complete execution plan for transcoding."""

    video_tasks: list[VideoTask] = field(default_factory=list)
    audio_tasks: list[AudioTask] = field(default_factory=list)
    subtitle_tasks: list[SubtitleTask] = field(default_factory=list)
    sprite_task: Optional[SpriteTask] = None
    estimated_duration: float = 0.0
    estimated_size: int = 0

    @property
    def total_tasks(self) -> int:
        """Get total number of tasks."""
        count = len(self.video_tasks) + len(self.audio_tasks) + len(self.subtitle_tasks)
        if self.sprite_task:
            count += 1
        return count

    @property
    def all_tasks(self) -> list[TranscodingTask]:
        """Get list of all tasks."""
        tasks: list[TranscodingTask] = []
        tasks.extend(self.video_tasks)
        tasks.extend(self.audio_tasks)
        tasks.extend(self.subtitle_tasks)
        if self.sprite_task:
            tasks.append(self.sprite_task)
        return tasks

    def get_pending_tasks(self) -> list[TranscodingTask]:
        """Get all pending tasks."""
        return [task for task in self.all_tasks if task.status == TaskStatus.PENDING]

    def get_failed_tasks(self) -> list[TranscodingTask]:
        """Get all failed tasks."""
        return [task for task in self.all_tasks if task.has_failed]

    @property
    def is_complete(self) -> bool:
        """Check if all tasks are completed."""
        return all(task.is_complete for task in self.all_tasks)


@dataclass
class ExecutionPlan:
    """Plan for parallel execution of tasks."""

    video_pool_size: int
    audio_pool_size: int
    subtitle_pool_size: int
    max_concurrent_tasks: int = 4

    def __post_init__(self) -> None:
        """Validate pool sizes."""
        if self.video_pool_size < 1:
            self.video_pool_size = 1
        if self.audio_pool_size < 1:
            self.audio_pool_size = 1
        if self.subtitle_pool_size < 1:
            self.subtitle_pool_size = 1
