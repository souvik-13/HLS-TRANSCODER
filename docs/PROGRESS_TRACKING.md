# Progress Tracking System

## Overview

The Progress Tracking System provides Rich-based progress monitoring for transcoding operations with support for multiple concurrent tasks, real-time updates, ETA calculation, and beautiful terminal output.

## Features

### Core Components

#### TaskProgress

Tracks progress information for a single task:

```python
from hls_transcoder.ui import TaskProgress, TaskStatus

# Create task
task = TaskProgress(
    task_id="video_1080p",
    name="Transcoding 1080p",
    total=150.5  # Total duration in seconds
)

# Start task
task.start()

# Update progress
task.update(progress=0.5, speed=30.0)  # 50% complete, 30 fps

# Check ETA
print(f"ETA: {task.eta}s")  # Estimated time remaining

# Complete task
task.complete()
```

#### ProgressTracker

Manages multiple concurrent tasks:

```python
from hls_transcoder.ui import ProgressTracker

tracker = ProgressTracker()

# Create multiple tasks
tracker.create_task("video_1080p", "1080p Variant", total=150.0)
tracker.create_task("video_720p", "720p Variant", total=150.0)
tracker.create_task("audio_eng", "English Audio", total=150.0)

# Start tasks
tracker.start_task("video_1080p")
tracker.start_task("video_720p")

# Update progress
tracker.update_task("video_1080p", progress=0.3, speed=28.5)
tracker.update_task("video_720p", progress=0.5, speed=45.2)

# Get task status
active_tasks = tracker.get_active_tasks()
print(f"Active tasks: {len(active_tasks)}")

# Calculate overall progress
print(f"Total progress: {tracker.total_progress * 100:.1f}%")
```

#### TranscodingMonitor

Rich-based visual progress monitor:

```python
from hls_transcoder.ui import TranscodingMonitor

# Create monitor
monitor = TranscodingMonitor()
monitor.start()

# Create tasks
task1 = monitor.create_task("video_1080p", "1080p Variant")
task2 = monitor.create_task("video_720p", "720p Variant")

# Start and update tasks
monitor.start_task("video_1080p")
monitor.update_task("video_1080p", progress=0.25, speed=30.0)

# Complete tasks
monitor.complete_task("video_1080p")

monitor.stop()
```

## Usage Examples

### Basic Usage

```python
from hls_transcoder.ui import TranscodingMonitor
import asyncio
import time

async def transcode_video():
    """Example transcoding with progress tracking."""

    with TranscodingMonitor() as monitor:
        # Create tasks
        video_task = monitor.create_task(
            "video_1080p",
            "Transcoding 1080p",
            total=120.0
        )
        audio_task = monitor.create_task(
            "audio_eng",
            "Extracting Audio",
            total=120.0
        )

        # Start video transcoding
        monitor.start_task("video_1080p")

        # Simulate progress updates
        for i in range(10):
            await asyncio.sleep(1)
            progress = (i + 1) / 10
            speed = 30.0 + (i * 2)  # Increasing speed
            monitor.update_task("video_1080p", progress=progress, speed=speed)

        monitor.complete_task("video_1080p")

        # Start audio extraction
        monitor.start_task("audio_eng")

        for i in range(5):
            await asyncio.sleep(0.5)
            progress = (i + 1) / 5
            monitor.update_task("audio_eng", progress=progress)

        monitor.complete_task("audio_eng")

# Run
asyncio.run(transcode_video())
```

### With FFmpeg Integration

```python
from hls_transcoder.ui import TranscodingMonitor
from hls_transcoder.executor import AsyncFFmpegProcess

async def transcode_with_progress(input_file, output_file):
    """Transcode with real-time progress."""

    monitor = TranscodingMonitor()
    monitor.start()

    # Create progress task
    task = monitor.create_task(
        "transcode",
        f"Transcoding {input_file.name}",
    )

    monitor.start_task("transcode")

    # Progress callback
    def update_progress(progress: float):
        # Calculate speed from FFmpeg output
        monitor.update_task("transcode", progress=progress, speed=30.0)

    # Build FFmpeg command
    command = [
        "ffmpeg", "-i", str(input_file),
        "-c:v", "libx264", "-c:a", "aac",
        str(output_file)
    ]

    try:
        # Run with progress tracking
        process = AsyncFFmpegProcess(
            command,
            progress_callback=update_progress
        )
        await process.run()

        monitor.complete_task("transcode")

    except Exception as e:
        monitor.fail_task("transcode", str(e))

    finally:
        monitor.stop()
```

### Multi-Task Parallel Processing

```python
from hls_transcoder.ui import TranscodingMonitor
import asyncio

async def parallel_transcoding():
    """Process multiple quality variants in parallel."""

    with TranscodingMonitor() as monitor:
        # Create tasks for all variants
        qualities = ["1080p", "720p", "480p", "360p"]
        tasks = []

        for quality in qualities:
            task_id = f"video_{quality}"
            monitor.create_task(task_id, f"{quality} Variant")
            tasks.append(transcode_quality(monitor, task_id))

        # Run all in parallel
        await asyncio.gather(*tasks)

async def transcode_quality(monitor, task_id):
    """Transcode a single quality variant."""
    monitor.start_task(task_id)

    # Simulate transcoding
    for i in range(20):
        await asyncio.sleep(0.1)
        progress = (i + 1) / 20
        speed = 25.0 + (i * 1.5)
        monitor.update_task(task_id, progress=progress, speed=speed)

    monitor.complete_task(task_id)

# Run
asyncio.run(parallel_transcoding())
```

### Custom Progress Display

```python
from hls_transcoder.ui.progress import create_simple_progress_bar
from rich.console import Console

# Create simple progress bar
console = Console()
progress = create_simple_progress_bar("Processing")

with progress:
    task_id = progress.add_task("Converting", total=100)

    for i in range(100):
        progress.update(task_id, advance=1)
        # Do work...
```

### Summary Tables

```python
from hls_transcoder.ui.progress import display_summary_table
from rich.console import Console

# Display results summary
console = Console()

data = [
    ("Input File", "movie.mkv"),
    ("Duration", "02:15:30"),
    ("Video Variants", "4 (1080p, 720p, 480p, 360p)"),
    ("Audio Tracks", "3 (ENG, SPA, FRE)"),
    ("Total Size", "2.8 GB"),
    ("Processing Time", "15m 23s"),
    ("Average Speed", "32.5 fps"),
]

display_summary_table("Transcoding Summary", data, console)
```

## Features

### Automatic ETA Calculation

The system automatically calculates estimated time remaining based on:

- Elapsed time
- Current progress
- Processing speed (if available)

```python
task = TaskProgress("task1", "Test")
task.start()
task.update(0.5)  # 50% complete

# ETA is automatically calculated
print(f"ETA: {task.eta:.1f}s")
```

### Speed Monitoring

Track processing speed (fps for video, Mbps for data):

```python
monitor.update_task("video", progress=0.3, speed=28.5)
# Displays as "28.5 fps" in the progress bar
```

### Task State Management

Tasks have multiple states:

- **PENDING**: Created but not started
- **RUNNING**: Currently processing
- **COMPLETED**: Successfully finished
- **FAILED**: Encountered an error
- **CANCELLED**: User cancelled

```python
# Filter tasks by state
active = tracker.get_active_tasks()
completed = tracker.get_completed_tasks()
failed = tracker.get_failed_tasks()

# Check if all complete
if tracker.is_complete:
    print("All tasks finished!")
```

### Context Manager Support

Automatic cleanup with context managers:

```python
with TranscodingMonitor() as monitor:
    # Create and update tasks
    pass
# Automatically stopped when exiting context
```

## Visual Output

The progress monitor provides beautiful terminal output:

```
╭──────────────────────────────────────────────────────────╮
│              HLS Transcoding Progress                    │
│                                                          │
│  ⠋ Transcoding 1080p ━━━━━━━━━━━━━━━━━━━━━━ 45% 00:15  │
│  ⠋ Transcoding 720p  ━━━━━━━━━━━━━━━━━━━━━━ 67% 00:08  │
│  ⠋ Extracting Audio  ━━━━━━━━━━━━━━━━━━━━━━ 78% 00:03  │
│                                                          │
├──────────────────────────────────────────────────────────┤
│ Active: 3 | Completed: 0 | Total: 3                     │
╰──────────────────────────────────────────────────────────╯
```

## Testing

Run the test suite:

```bash
poetry run pytest tests/test_progress.py -v
```

The test suite includes:

- TaskProgress lifecycle tests
- ETA calculation verification
- ProgressTracker task management
- TranscodingMonitor display tests
- Context manager tests
- 40+ comprehensive tests

## Performance Considerations

- **Refresh Rate**: Progress display refreshes 4 times per second by default
- **Overhead**: Minimal performance impact (<1% CPU)
- **Threading**: Rich Live display runs in background thread
- **Memory**: ~1KB per task for progress tracking

## Best Practices

1. **Use Context Managers**: Ensures proper cleanup
2. **Update Frequently**: Update progress at regular intervals (every 0.5-1s)
3. **Meaningful Names**: Use clear, descriptive task names
4. **Error Handling**: Always call `fail_task()` on errors
5. **Complete Tasks**: Always mark tasks as complete or failed

## See Also

- [Async Subprocess Wrapper](./ASYNC_SUBPROCESS.md) - FFmpeg process management
- [Hardware Detection](./HARDWARE_DETECTION.md) - Hardware acceleration
- [Media Inspector](./MEDIA_INSPECTOR.md) - Media file analysis
