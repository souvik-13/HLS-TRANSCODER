"""
Tests for progress tracking system.
"""

import time
from unittest.mock import MagicMock, patch

import pytest
from rich.console import Console

from hls_transcoder.ui import ProgressTracker, TaskProgress, TranscodingMonitor
from hls_transcoder.ui.progress import (
    TaskStatus,
    create_simple_progress_bar,
    display_summary_table,
)


class TestTaskStatus:
    """Test TaskStatus enum."""

    def test_status_values(self):
        """Test status enum values."""
        assert TaskStatus.PENDING.value == "pending"
        assert TaskStatus.RUNNING.value == "running"
        assert TaskStatus.COMPLETED.value == "completed"
        assert TaskStatus.FAILED.value == "failed"
        assert TaskStatus.CANCELLED.value == "cancelled"


class TestTaskProgress:
    """Test TaskProgress class."""

    def test_initialization(self):
        """Test task progress initialization."""
        task = TaskProgress(task_id="task1", name="Test Task")

        assert task.task_id == "task1"
        assert task.name == "Test Task"
        assert task.status == TaskStatus.PENDING
        assert task.progress == 0.0
        assert task.current == 0.0
        assert task.total == 0.0
        assert task.speed == 0.0
        assert task.start_time is None
        assert task.end_time is None
        assert task.error_message is None

    def test_initialization_with_values(self):
        """Test initialization with custom values."""
        task = TaskProgress(
            task_id="task1",
            name="Test Task",
            status=TaskStatus.RUNNING,
            progress=0.5,
            total=100.0,
        )

        assert task.status == TaskStatus.RUNNING
        assert task.progress == 0.5
        assert task.total == 100.0

    def test_start(self):
        """Test starting a task."""
        task = TaskProgress(task_id="task1", name="Test Task")
        task.start()

        assert task.status == TaskStatus.RUNNING
        assert task.start_time is not None
        assert task.start_time <= time.time()

    def test_complete(self):
        """Test completing a task."""
        task = TaskProgress(task_id="task1", name="Test Task")
        task.start()
        time.sleep(0.01)  # Small delay
        task.complete()

        assert task.status == TaskStatus.COMPLETED
        assert task.progress == 1.0
        assert task.end_time is not None
        assert task.start_time is not None
        assert task.end_time > task.start_time

    def test_fail(self):
        """Test failing a task."""
        task = TaskProgress(task_id="task1", name="Test Task")
        task.start()
        task.fail("Something went wrong")

        assert task.status == TaskStatus.FAILED
        assert task.error_message == "Something went wrong"
        assert task.end_time is not None

    def test_update(self):
        """Test updating task progress."""
        task = TaskProgress(task_id="task1", name="Test Task", total=100.0)
        task.update(0.5, speed=30.0)

        assert task.progress == 0.5
        assert task.speed == 30.0
        assert task.current == 50.0  # 50% of 100

    def test_update_clamps_progress(self):
        """Test that progress is clamped to [0, 1]."""
        task = TaskProgress(task_id="task1", name="Test Task")

        task.update(-0.5)
        assert task.progress == 0.0

        task.update(1.5)
        assert task.progress == 1.0

    def test_elapsed_time(self):
        """Test elapsed time calculation."""
        task = TaskProgress(task_id="task1", name="Test Task")

        # Before start
        assert task.elapsed_time == 0.0

        # After start
        task.start()
        time.sleep(0.05)
        assert task.elapsed_time > 0.04

        # After complete
        task.complete()
        elapsed = task.elapsed_time
        time.sleep(0.01)
        assert task.elapsed_time == elapsed  # Should not change

    def test_eta(self):
        """Test ETA calculation."""
        task = TaskProgress(task_id="task1", name="Test Task")

        # Before start
        assert task.eta is None

        # At 0% progress
        task.start()
        assert task.eta is None

        # At 50% progress
        time.sleep(0.1)
        task.update(0.5)
        eta = task.eta
        assert eta is not None
        assert eta > 0

        # At 100% progress
        task.update(1.0)
        assert task.eta == 0.0

    def test_is_complete(self):
        """Test is_complete property."""
        task = TaskProgress(task_id="task1", name="Test Task")

        assert not task.is_complete

        task.status = TaskStatus.RUNNING
        assert not task.is_complete

        task.complete()
        assert task.is_complete

        task.status = TaskStatus.FAILED
        assert task.is_complete

        task.status = TaskStatus.CANCELLED
        assert task.is_complete


class TestProgressTracker:
    """Test ProgressTracker class."""

    def test_initialization(self):
        """Test tracker initialization."""
        tracker = ProgressTracker()
        assert len(tracker.get_all_tasks()) == 0

    def test_create_task(self):
        """Test creating a task."""
        tracker = ProgressTracker()
        task = tracker.create_task("task1", "Test Task", total=100.0)

        assert task.task_id == "task1"
        assert task.name == "Test Task"
        assert task.total == 100.0
        assert len(tracker.get_all_tasks()) == 1

    def test_get_task(self):
        """Test getting a task."""
        tracker = ProgressTracker()
        tracker.create_task("task1", "Test Task")

        task = tracker.get_task("task1")
        assert task is not None
        assert task.task_id == "task1"

        # Non-existent task
        assert tracker.get_task("task2") is None

    def test_update_task(self):
        """Test updating a task."""
        tracker = ProgressTracker()
        tracker.create_task("task1", "Test Task")

        tracker.update_task("task1", progress=0.5, speed=30.0)

        task = tracker.get_task("task1")
        assert task is not None
        assert task.progress == 0.5
        assert task.speed == 30.0

    def test_update_task_status(self):
        """Test updating task status."""
        tracker = ProgressTracker()
        tracker.create_task("task1", "Test Task")

        tracker.update_task("task1", status=TaskStatus.RUNNING)

        task = tracker.get_task("task1")
        assert task is not None
        assert task.status == TaskStatus.RUNNING

        tracker.update_task("task1", status=TaskStatus.COMPLETED)
        task = tracker.get_task("task1")
        assert task is not None
        assert task.status == TaskStatus.COMPLETED
        assert task.progress == 1.0

    def test_start_task(self):
        """Test starting a task."""
        tracker = ProgressTracker()
        tracker.create_task("task1", "Test Task")
        tracker.start_task("task1")

        task = tracker.get_task("task1")
        assert task is not None
        assert task.status == TaskStatus.RUNNING
        assert task.start_time is not None

    def test_complete_task(self):
        """Test completing a task."""
        tracker = ProgressTracker()
        tracker.create_task("task1", "Test Task")
        tracker.complete_task("task1")

        task = tracker.get_task("task1")
        assert task is not None
        assert task.status == TaskStatus.COMPLETED
        assert task.progress == 1.0

    def test_fail_task(self):
        """Test failing a task."""
        tracker = ProgressTracker()
        tracker.create_task("task1", "Test Task")
        tracker.fail_task("task1", "Error occurred")

        task = tracker.get_task("task1")
        assert task is not None
        assert task.status == TaskStatus.FAILED
        assert task.error_message == "Error occurred"

    def test_get_all_tasks(self):
        """Test getting all tasks."""
        tracker = ProgressTracker()
        tracker.create_task("task1", "Task 1")
        tracker.create_task("task2", "Task 2")
        tracker.create_task("task3", "Task 3")

        tasks = tracker.get_all_tasks()
        assert len(tasks) == 3
        assert [t.task_id for t in tasks] == ["task1", "task2", "task3"]

    def test_get_active_tasks(self):
        """Test getting active tasks."""
        tracker = ProgressTracker()
        tracker.create_task("task1", "Task 1")
        tracker.create_task("task2", "Task 2")
        tracker.create_task("task3", "Task 3")

        tracker.start_task("task1")
        tracker.start_task("task2")

        active = tracker.get_active_tasks()
        assert len(active) == 2
        assert all(t.status == TaskStatus.RUNNING for t in active)

    def test_get_pending_tasks(self):
        """Test getting pending tasks."""
        tracker = ProgressTracker()
        tracker.create_task("task1", "Task 1")
        tracker.create_task("task2", "Task 2")
        tracker.start_task("task1")

        pending = tracker.get_pending_tasks()
        assert len(pending) == 1
        assert pending[0].task_id == "task2"

    def test_get_completed_tasks(self):
        """Test getting completed tasks."""
        tracker = ProgressTracker()
        tracker.create_task("task1", "Task 1")
        tracker.create_task("task2", "Task 2")
        tracker.complete_task("task1")

        completed = tracker.get_completed_tasks()
        assert len(completed) == 1
        assert completed[0].task_id == "task1"

    def test_get_failed_tasks(self):
        """Test getting failed tasks."""
        tracker = ProgressTracker()
        tracker.create_task("task1", "Task 1")
        tracker.create_task("task2", "Task 2")
        tracker.fail_task("task1", "Error")

        failed = tracker.get_failed_tasks()
        assert len(failed) == 1
        assert failed[0].task_id == "task1"

    def test_total_progress(self):
        """Test total progress calculation."""
        tracker = ProgressTracker()

        # No tasks
        assert tracker.total_progress == 0.0

        # Multiple tasks
        tracker.create_task("task1", "Task 1")
        tracker.create_task("task2", "Task 2")
        tracker.create_task("task3", "Task 3")

        tracker.update_task("task1", progress=1.0)
        tracker.update_task("task2", progress=0.5)
        tracker.update_task("task3", progress=0.0)

        # Average: (1.0 + 0.5 + 0.0) / 3 = 0.5
        assert tracker.total_progress == pytest.approx(0.5)

    def test_is_complete(self):
        """Test is_complete property."""
        tracker = ProgressTracker()
        tracker.create_task("task1", "Task 1")
        tracker.create_task("task2", "Task 2")

        assert not tracker.is_complete

        tracker.complete_task("task1")
        assert not tracker.is_complete

        tracker.complete_task("task2")
        assert tracker.is_complete


class TestTranscodingMonitor:
    """Test TranscodingMonitor class."""

    def test_initialization(self):
        """Test monitor initialization."""
        monitor = TranscodingMonitor()
        assert monitor.console is not None
        assert isinstance(monitor.tracker, ProgressTracker)

    def test_initialization_with_console(self):
        """Test initialization with custom console."""
        console = Console()
        monitor = TranscodingMonitor(console=console)
        assert monitor.console is console

    def test_create_progress(self):
        """Test progress creation."""
        monitor = TranscodingMonitor()
        progress = monitor.create_progress()
        assert progress is not None

    def test_create_task(self):
        """Test creating a task."""
        monitor = TranscodingMonitor()
        monitor.start()

        task = monitor.create_task("task1", "Test Task", total=100.0)
        assert task.task_id == "task1"
        assert task.rich_task_id is not None

        monitor.stop()

    def test_update_task(self):
        """Test updating a task."""
        monitor = TranscodingMonitor()
        monitor.start()
        monitor.create_task("task1", "Test Task")

        monitor.update_task("task1", progress=0.5, speed=30.0)

        task = monitor.tracker.get_task("task1")
        assert task is not None
        assert task.progress == 0.5
        assert task.speed == 30.0

        monitor.stop()

    def test_start_task(self):
        """Test starting a task."""
        monitor = TranscodingMonitor()
        monitor.start()
        monitor.create_task("task1", "Test Task")

        monitor.start_task("task1")

        task = monitor.tracker.get_task("task1")
        assert task is not None
        assert task.status == TaskStatus.RUNNING

        monitor.stop()

    def test_complete_task(self):
        """Test completing a task."""
        monitor = TranscodingMonitor()
        monitor.start()
        monitor.create_task("task1", "Test Task")

        monitor.complete_task("task1")

        task = monitor.tracker.get_task("task1")
        assert task is not None
        assert task.status == TaskStatus.COMPLETED

        monitor.stop()

    def test_fail_task(self):
        """Test failing a task."""
        monitor = TranscodingMonitor()
        monitor.start()
        monitor.create_task("task1", "Test Task")

        monitor.fail_task("task1", "Error occurred")

        task = monitor.tracker.get_task("task1")
        assert task is not None
        assert task.status == TaskStatus.FAILED
        assert task.error_message == "Error occurred"

        monitor.stop()

    def test_format_speed(self):
        """Test speed formatting."""
        monitor = TranscodingMonitor()

        assert monitor._format_speed(0.0) == ""
        assert monitor._format_speed(0.5) == "0.50x"
        assert monitor._format_speed(25.5) == "25.5 fps"
        assert monitor._format_speed(150.0) == "150 fps"

    def test_context_manager(self):
        """Test context manager usage."""
        with TranscodingMonitor() as monitor:
            assert monitor._live is not None
            task = monitor.create_task("task1", "Test Task")
            monitor.update_task("task1", progress=0.5)

        # Should be stopped after exit
        assert monitor._live is None


class TestHelperFunctions:
    """Test helper functions."""

    def test_create_simple_progress_bar(self):
        """Test simple progress bar creation."""
        progress = create_simple_progress_bar("Test Task")
        assert progress is not None

    def test_display_summary_table(self):
        """Test summary table display."""
        data = [
            ("Input", "video.mp4"),
            ("Duration", "01:30:00"),
            ("Size", "1.5 GB"),
        ]

        # Should not raise
        with patch("rich.console.Console.print"):
            display_summary_table("Test Summary", data)
