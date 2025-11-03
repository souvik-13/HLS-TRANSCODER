"""
Progress tracking and monitoring for transcoding tasks.

This module provides Rich-based progress tracking with support for:
- Multiple concurrent tasks
- Real-time progress updates
- ETA calculation
- Speed monitoring
- Beautiful terminal output
"""

import time
from collections import deque
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

from rich.console import Console, Group
from rich.live import Live
from rich.panel import Panel
from rich.progress import (
    BarColumn,
    Progress,
    SpinnerColumn,
    TaskID,
    TextColumn,
    TimeElapsedColumn,
    TimeRemainingColumn,
)
from rich.table import Table
from rich.text import Text

from ..utils import format_duration, format_size, get_logger

logger = get_logger(__name__)


class TaskStatus(Enum):
    """Status of a transcoding task."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class TaskProgress:
    """
    Progress information for a single task.

    Tracks progress, speed, and timing information for transcoding tasks.
    """

    task_id: str
    name: str
    status: TaskStatus = TaskStatus.PENDING
    progress: float = 0.0  # 0.0 to 1.0
    current: float = 0.0  # Current processed amount (seconds/bytes)
    total: float = 0.0  # Total amount to process
    speed: float = 0.0  # Processing speed (fps/Mbps)
    start_time: Optional[float] = None
    end_time: Optional[float] = None
    error_message: Optional[str] = None
    rich_task_id: Optional[TaskID] = None

    @property
    def elapsed_time(self) -> float:
        """Get elapsed time in seconds."""
        if self.start_time is None:
            return 0.0
        end = self.end_time if self.end_time else time.time()
        return end - self.start_time

    @property
    def eta(self) -> Optional[float]:
        """Calculate estimated time remaining in seconds."""
        if self.progress <= 0 or self.elapsed_time <= 0:
            return None

        if self.progress >= 1.0:
            return 0.0

        # Calculate ETA based on current progress
        time_per_percent = self.elapsed_time / self.progress
        remaining = time_per_percent * (1.0 - self.progress)
        return remaining

    @property
    def is_complete(self) -> bool:
        """Check if task is complete."""
        return self.status in (
            TaskStatus.COMPLETED,
            TaskStatus.FAILED,
            TaskStatus.CANCELLED,
        )

    def start(self) -> None:
        """Mark task as started."""
        self.status = TaskStatus.RUNNING
        self.start_time = time.time()

    def complete(self) -> None:
        """Mark task as completed."""
        self.status = TaskStatus.COMPLETED
        self.progress = 1.0
        self.end_time = time.time()

    def fail(self, error: str) -> None:
        """Mark task as failed."""
        self.status = TaskStatus.FAILED
        self.error_message = error
        self.end_time = time.time()

    def update(self, progress: float, speed: Optional[float] = None) -> None:
        """
        Update task progress.

        Args:
            progress: Progress value (0.0 to 1.0)
            speed: Processing speed (optional)
        """
        self.progress = min(max(progress, 0.0), 1.0)
        if speed is not None:
            self.speed = speed

        # Update current value based on progress
        if self.total > 0:
            self.current = self.total * self.progress


class ProgressTracker:
    """
    Progress tracker for multiple concurrent tasks.

    Manages progress for multiple tasks and provides methods to
    create, update, and query task progress.
    """

    def __init__(self):
        """Initialize progress tracker."""
        self._tasks: dict[str, TaskProgress] = {}
        self._task_order: list[str] = []  # Track insertion order

    def create_task(
        self,
        task_id: str,
        name: str,
        total: float = 100.0,
    ) -> TaskProgress:
        """
        Create a new task.

        Args:
            task_id: Unique task identifier
            name: Task display name
            total: Total amount to process

        Returns:
            TaskProgress object
        """
        task = TaskProgress(
            task_id=task_id,
            name=name,
            total=total,
        )
        self._tasks[task_id] = task
        self._task_order.append(task_id)
        logger.debug(f"Created task: {task_id} - {name}")
        return task

    def get_task(self, task_id: str) -> Optional[TaskProgress]:
        """
        Get task by ID.

        Args:
            task_id: Task identifier

        Returns:
            TaskProgress object or None
        """
        return self._tasks.get(task_id)

    def update_task(
        self,
        task_id: str,
        progress: Optional[float] = None,
        speed: Optional[float] = None,
        status: Optional[TaskStatus] = None,
    ) -> None:
        """
        Update task progress.

        Args:
            task_id: Task identifier
            progress: Progress value (0.0 to 1.0)
            speed: Processing speed
            status: New task status
        """
        task = self.get_task(task_id)
        if not task:
            logger.warning(f"Task not found: {task_id}")
            return

        if progress is not None:
            task.update(progress, speed)

        if status is not None:
            task.status = status
            if status == TaskStatus.COMPLETED:
                task.complete()

    def start_task(self, task_id: str) -> None:
        """Start a task."""
        task = self.get_task(task_id)
        if task:
            task.start()

    def complete_task(self, task_id: str) -> None:
        """Mark task as completed."""
        task = self.get_task(task_id)
        if task:
            task.complete()

    def fail_task(self, task_id: str, error: str) -> None:
        """Mark task as failed."""
        task = self.get_task(task_id)
        if task:
            task.fail(error)

    def get_all_tasks(self) -> list[TaskProgress]:
        """Get all tasks in creation order."""
        return [self._tasks[tid] for tid in self._task_order if tid in self._tasks]

    def get_active_tasks(self) -> list[TaskProgress]:
        """Get all active (running) tasks."""
        return [t for t in self.get_all_tasks() if t.status == TaskStatus.RUNNING]

    def get_pending_tasks(self) -> list[TaskProgress]:
        """Get all pending tasks."""
        return [t for t in self.get_all_tasks() if t.status == TaskStatus.PENDING]

    def get_completed_tasks(self) -> list[TaskProgress]:
        """Get all completed tasks."""
        return [t for t in self.get_all_tasks() if t.status == TaskStatus.COMPLETED]

    def get_failed_tasks(self) -> list[TaskProgress]:
        """Get all failed tasks."""
        return [t for t in self.get_all_tasks() if t.status == TaskStatus.FAILED]

    @property
    def total_progress(self) -> float:
        """Calculate overall progress across all tasks."""
        tasks = self.get_all_tasks()
        if not tasks:
            return 0.0

        total = sum(t.progress for t in tasks)
        return total / len(tasks)

    @property
    def is_complete(self) -> bool:
        """Check if all tasks are complete."""
        return all(t.is_complete for t in self.get_all_tasks())


class TranscodingMonitor:
    """
    Rich-based progress monitor for transcoding operations.

    Provides beautiful terminal UI with:
    - Multiple progress bars
    - Real-time updates
    - Status indicators
    - Statistics display
    - Log messages below progress bars
    """

    def __init__(self, console: Optional[Console] = None, max_log_lines: Optional[int] = None):
        """
        Initialize transcoding monitor.

        Args:
            console: Rich console (creates new if None)
            max_log_lines: Maximum number of log lines to display (auto-calculated if None)
        """
        self.console = console or Console()
        self.tracker = ProgressTracker()
        self._progress: Optional[Progress] = None
        self._live: Optional[Live] = None

        # Auto-calculate max log lines based on terminal height if not specified
        if max_log_lines is None:
            terminal_height = self.console.size.height
            # Reserve space for: header, progress bars, borders, and some padding
            # Estimate: 10 lines for header/progress, 8 lines for padding/borders
            max_log_lines = max(10, min(30, terminal_height - 18))

        self._log_lines: deque[str] = deque(maxlen=max_log_lines)
        self._max_log_lines = max_log_lines

    def create_progress(self) -> Progress:
        """
        Create Rich progress display.

        Returns:
            Progress object with custom columns
        """
        return Progress(
            SpinnerColumn(),
            TextColumn("[bold blue]{task.description}"),
            BarColumn(bar_width=None),
            TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
            TimeElapsedColumn(),
            TimeRemainingColumn(),
            TextColumn("[cyan]{task.fields[speed]}"),
            console=self.console,
            expand=True,
        )

    def start(self) -> None:
        """Start the progress monitor."""
        from ..utils import set_active_monitor

        self._progress = self.create_progress()
        self._live = Live(
            self._generate_layout(),
            console=self.console,
            refresh_per_second=4,
            transient=False,  # Keep display visible
        )
        self._live.start()

        # Register this monitor for log integration
        set_active_monitor(self)
        logger.debug("Progress monitor started")

    def add_log(self, message: str) -> None:
        """
        Add a log message to display below progress bars.

        Args:
            message: Log message to display
        """
        self._log_lines.append(message)
        if self._live:
            self._live.update(self._generate_layout())

    def stop(self) -> None:
        """Stop the progress monitor."""
        from ..utils import set_active_monitor

        if self._live:
            self._live.stop()
            self._live = None
        self._progress = None

        # Unregister this monitor
        set_active_monitor(None)
        logger.debug("Progress monitor stopped")

    def create_task(
        self,
        task_id: str,
        name: str,
        total: float = 100.0,
    ) -> TaskProgress:
        """
        Create a new task for monitoring.

        Args:
            task_id: Unique task identifier
            name: Task display name
            total: Total amount to process

        Returns:
            TaskProgress object
        """
        task = self.tracker.create_task(task_id, name, total)

        # Create Rich progress task
        if self._progress:
            rich_task_id = self._progress.add_task(
                name,
                total=100.0,
                speed="",
            )
            task.rich_task_id = rich_task_id

        return task

    def update_task(
        self,
        task_id: str,
        progress: Optional[float] = None,
        speed: Optional[float] = None,
    ) -> None:
        """
        Update task progress.

        Args:
            task_id: Task identifier
            progress: Progress value (0.0 to 1.0)
            speed: Processing speed
        """
        task = self.tracker.get_task(task_id)
        if not task:
            return

        # Update tracker
        self.tracker.update_task(task_id, progress, speed)

        # Update Rich progress
        if self._progress and task.rich_task_id is not None:
            completed = progress * 100 if progress else task.progress * 100
            speed_text = self._format_speed(speed or task.speed)

            self._progress.update(
                task.rich_task_id,
                completed=completed,
                speed=speed_text,
            )

    def start_task(self, task_id: str) -> None:
        """Start a task."""
        self.tracker.start_task(task_id)

    def complete_task(self, task_id: str) -> None:
        """Mark task as completed."""
        task = self.tracker.get_task(task_id)
        if task:
            self.tracker.complete_task(task_id)

            # Update Rich progress to 100%
            if self._progress and task.rich_task_id is not None:
                self._progress.update(
                    task.rich_task_id,
                    completed=100.0,
                    speed="✓ Complete",
                )

    def fail_task(self, task_id: str, error: str) -> None:
        """Mark task as failed."""
        task = self.tracker.get_task(task_id)
        if task:
            self.tracker.fail_task(task_id, error)

            # Update Rich progress
            if self._progress and task.rich_task_id is not None:
                self._progress.update(
                    task.rich_task_id,
                    speed="✗ Failed",
                )

    def _format_speed(self, speed: float) -> str:
        """
        Format speed for display.

        Args:
            speed: Speed value

        Returns:
            Formatted speed string
        """
        if speed <= 0:
            return ""

        # Assume speed is in fps for video tasks
        if speed < 1:
            return f"{speed:.2f}x"
        elif speed < 100:
            return f"{speed:.1f} fps"
        else:
            return f"{speed:.0f} fps"

    def _generate_layout(self) -> Group:
        """
        Generate layout for display with progress bars and logs.

        Returns:
            Rich Group with progress panel and log panel
        """
        # Create progress panel
        if self._progress:
            progress_layout = self._progress
        else:
            progress_layout = Table.grid()

        stats = self._generate_statistics()

        progress_panel = Panel(
            progress_layout,
            title="[bold cyan]HLS Transcoding Progress[/bold cyan]",
            subtitle=stats,
            border_style="cyan",
        )

        # Create logs panel if there are logs
        log_panel = None
        if self._log_lines:
            log_count = len(self._log_lines)
            log_text = "\n".join(self._log_lines)

            # Add subtitle showing this is a scrolling buffer
            if log_count >= self._max_log_lines:
                log_subtitle = (
                    f"[dim]Showing last {log_count} entries (buffer full, auto-scrolling)[/dim]"
                )
            else:
                log_subtitle = f"[dim]Showing {log_count} recent log entries (max: {self._max_log_lines})[/dim]"

            # Use Text.from_markup to properly render Rich markup
            log_panel = Panel(
                Text.from_markup(log_text, overflow="fold"),
                title="[bold yellow]📋 Logs[/bold yellow]",
                subtitle=log_subtitle,
                border_style="yellow",
                padding=(0, 1),
                height=min(self._max_log_lines + 3, self.console.size.height // 2),  # Limit height
            )

        # Combine panels
        if log_panel:
            return Group(progress_panel, log_panel)
        else:
            return Group(progress_panel)

    def _generate_statistics(self) -> str:
        """
        Generate statistics text.

        Returns:
            Formatted statistics string
        """
        all_tasks = self.tracker.get_all_tasks()
        if not all_tasks:
            return ""

        completed = len(self.tracker.get_completed_tasks())
        failed = len(self.tracker.get_failed_tasks())
        active = len(self.tracker.get_active_tasks())
        total = len(all_tasks)

        parts = []
        if active > 0:
            parts.append(f"[yellow]Active: {active}[/yellow]")
        if completed > 0:
            parts.append(f"[green]Completed: {completed}[/green]")
        if failed > 0:
            parts.append(f"[red]Failed: {failed}[/red]")

        parts.append(f"Total: {total}")

        return " | ".join(parts)

    def __enter__(self) -> "TranscodingMonitor":
        """Context manager entry."""
        self.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """Context manager exit."""
        self.stop()


def create_simple_progress_bar(description: str) -> Progress:
    """
    Create a simple progress bar for basic tasks.

    Args:
        description: Task description

    Returns:
        Progress object
    """
    return Progress(
        TextColumn("[bold blue]{task.description}"),
        BarColumn(bar_width=None),
        TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
        TimeRemainingColumn(),
    )


def display_summary_table(
    title: str,
    data: list[tuple[str, str]],
    console: Optional[Console] = None,
) -> None:
    """
    Display a summary table.

    Args:
        title: Table title
        data: List of (key, value) tuples
        console: Rich console (creates new if None)
    """
    console = console or Console()

    table = Table(title=title, show_header=False, box=None)
    table.add_column("Property", style="cyan", no_wrap=True)
    table.add_column("Value", style="white")

    for key, value in data:
        table.add_row(key, value)

    console.print(table)
