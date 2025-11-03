"""
Tests for parallel task execution.
"""

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from hls_transcoder.config import TranscoderConfig
from hls_transcoder.executor import (
    ExecutionResult,
    ExecutionSummary,
    ParallelExecutor,
    execute_parallel,
)
from hls_transcoder.hardware import HardwareInfo, HardwareType
from hls_transcoder.models import (
    AudioStream,
    AudioTask,
    FormatInfo,
    MediaInfo,
    SubtitleStream,
    SubtitleTask,
    SpriteTask,
    TaskStatus,
    TaskType,
    VideoStream,
    VideoTask,
)
from hls_transcoder.planner import ExecutionStrategy
from hls_transcoder.utils import TranscodingError


# === Fixtures ===


@pytest.fixture
def test_input_file(tmp_path):
    """Create test input file."""
    input_file = tmp_path / "input.mp4"
    input_file.touch()
    return input_file


@pytest.fixture
def test_output_dir(tmp_path):
    """Create test output directory."""
    return tmp_path / "output"


@pytest.fixture
def media_info():
    """Create sample media info."""
    return MediaInfo(
        format=FormatInfo(
            format_name="mp4",
            format_long_name="QuickTime / MOV",
            duration=600.0,
            size=1024 * 1024 * 100,  # 100 MB
            bitrate=1000000,
        ),
        video_streams=[
            VideoStream(
                index=0,
                codec="h264",
                codec_long="H.264 / AVC",
                profile="high",
                width=1920,
                height=1080,
                fps=30.0,
                bitrate=5000000,
                duration=600.0,
                pix_fmt="yuv420p",
            )
        ],
        audio_streams=[
            AudioStream(
                index=1,
                codec="aac",
                codec_long="AAC (Advanced Audio Coding)",
                profile="lc",
                language="eng",
                channels=2,
                sample_rate=48000,
                bitrate=128000,
                duration=600.0,
            )
        ],
        subtitle_streams=[
            SubtitleStream(
                index=2,
                codec="subrip",
                language="eng",
                title="English",
            )
        ],
        duration=600.0,
        size=1024 * 1024 * 100,
        bitrate=1000000,
    )


@pytest.fixture
def hardware_info():
    """Create sample hardware info."""
    from hls_transcoder.hardware.detector import EncoderInfo

    return HardwareInfo(
        detected_type=HardwareType.SOFTWARE,
        available_encoders=[
            EncoderInfo(
                name="libx264",
                hardware_type=HardwareType.SOFTWARE,
                display_name="Software H.264",
                available=True,
                tested=True,
            ),
            EncoderInfo(
                name="libx265",
                hardware_type=HardwareType.SOFTWARE,
                display_name="Software H.265",
                available=True,
                tested=True,
            ),
        ],
    )


@pytest.fixture
def config():
    """Create sample config."""
    return TranscoderConfig.create_default()


@pytest.fixture
def execution_strategy():
    """Create sample execution strategy."""
    return ExecutionStrategy(
        video_concurrency=2,
        audio_concurrency=2,
        subtitle_concurrency=2,
        sprite_separate=False,
        max_total_concurrent=4,
    )


@pytest.fixture
def video_task(test_output_dir):
    """Create sample video task."""
    return VideoTask(
        task_id="video_720p",
        task_type=TaskType.VIDEO,
        input_file=Path("input.mp4"),
        output_dir=test_output_dir / "video",
        quality="720p",
        width=1280,
        height=720,
        bitrate="3000k",
        encoder="libx264",
        stream_index=0,
    )


@pytest.fixture
def audio_task(test_output_dir):
    """Create sample audio task."""
    return AudioTask(
        task_id="audio_eng",
        task_type=TaskType.AUDIO,
        input_file=Path("input.mp4"),
        output_dir=test_output_dir / "audio",
        stream_index=1,
        language="eng",
        bitrate="128k",
    )


@pytest.fixture
def subtitle_task(test_output_dir):
    """Create sample subtitle task."""
    return SubtitleTask(
        task_id="subtitle_eng",
        task_type=TaskType.SUBTITLE,
        input_file=Path("input.mp4"),
        output_dir=test_output_dir / "subtitles",
        stream_index=2,
        language="eng",
        format="webvtt",
    )


@pytest.fixture
def sprite_task(test_output_dir):
    """Create sample sprite task."""
    return SpriteTask(
        task_id="sprite",
        task_type=TaskType.SPRITE,
        input_file=Path("input.mp4"),
        output_dir=test_output_dir / "sprites",
        interval=10,
        width=160,
        height=90,
        columns=10,
        rows=10,
    )


# === ExecutionResult Tests ===


def test_execution_result_creation(video_task, test_output_dir):
    """Test creating execution result."""
    output_path = test_output_dir / "output.m3u8"

    result = ExecutionResult(
        task=video_task,
        success=True,
        output_path=output_path,
        duration=10.5,
    )

    assert result.task == video_task
    assert result.success is True
    assert result.output_path == output_path
    assert result.error is None
    assert result.duration == 10.5


def test_execution_result_failure(video_task):
    """Test execution result for failed task."""
    result = ExecutionResult(
        task=video_task,
        success=False,
        error="Transcoding failed",
        duration=5.0,
    )

    assert result.task == video_task
    assert result.success is False
    assert result.output_path is None
    assert result.error == "Transcoding failed"


# === ExecutionSummary Tests ===


def test_execution_summary_creation(video_task):
    """Test creating execution summary."""
    results = [
        ExecutionResult(video_task, success=True, duration=10.0),
        ExecutionResult(video_task, success=False, error="Failed", duration=5.0),
    ]

    summary = ExecutionSummary(
        total_tasks=2,
        completed_tasks=1,
        failed_tasks=1,
        cancelled_tasks=0,
        total_duration=15.0,
        results=results,
    )

    assert summary.total_tasks == 2
    assert summary.completed_tasks == 1
    assert summary.failed_tasks == 1
    assert summary.cancelled_tasks == 0
    assert summary.total_duration == 15.0
    assert len(summary.results) == 2


def test_execution_summary_success_rate():
    """Test success rate calculation."""
    summary = ExecutionSummary(
        total_tasks=10,
        completed_tasks=8,
        failed_tasks=2,
        cancelled_tasks=0,
        total_duration=100.0,
        results=[],
    )

    assert summary.success_rate == 80.0


def test_execution_summary_success_rate_zero_tasks():
    """Test success rate with zero tasks."""
    summary = ExecutionSummary(
        total_tasks=0,
        completed_tasks=0,
        failed_tasks=0,
        cancelled_tasks=0,
        total_duration=0.0,
        results=[],
    )

    assert summary.success_rate == 0.0


def test_execution_summary_has_failures():
    """Test has_failures property."""
    summary_with_failures = ExecutionSummary(
        total_tasks=2,
        completed_tasks=1,
        failed_tasks=1,
        cancelled_tasks=0,
        total_duration=10.0,
        results=[],
    )

    summary_no_failures = ExecutionSummary(
        total_tasks=2,
        completed_tasks=2,
        failed_tasks=0,
        cancelled_tasks=0,
        total_duration=10.0,
        results=[],
    )

    assert summary_with_failures.has_failures is True
    assert summary_no_failures.has_failures is False


# === ParallelExecutor Tests ===


def test_parallel_executor_initialization(
    test_input_file,
    test_output_dir,
    media_info,
    hardware_info,
    config,
    execution_strategy,
):
    """Test parallel executor initialization."""
    executor = ParallelExecutor(
        input_file=test_input_file,
        output_dir=test_output_dir,
        media_info=media_info,
        hardware_info=hardware_info,
        config=config,
        strategy=execution_strategy,
    )

    assert executor.input_file == test_input_file
    assert executor.output_dir == test_output_dir
    assert executor.media_info == media_info
    assert executor.hardware_info == hardware_info
    assert executor.config == config
    assert executor.strategy == execution_strategy
    assert test_output_dir.exists()


def test_parallel_executor_creates_output_directory(
    test_input_file,
    test_output_dir,
    media_info,
    hardware_info,
    config,
    execution_strategy,
):
    """Test that output directory is created."""
    assert not test_output_dir.exists()

    ParallelExecutor(
        input_file=test_input_file,
        output_dir=test_output_dir,
        media_info=media_info,
        hardware_info=hardware_info,
        config=config,
        strategy=execution_strategy,
    )

    assert test_output_dir.exists()


@pytest.mark.asyncio
async def test_execute_single_video_task(
    test_input_file,
    test_output_dir,
    media_info,
    hardware_info,
    config,
    execution_strategy,
    video_task,
):
    """Test executing single video task."""
    executor = ParallelExecutor(
        input_file=test_input_file,
        output_dir=test_output_dir,
        media_info=media_info,
        hardware_info=hardware_info,
        config=config,
        strategy=execution_strategy,
    )

    # Mock video transcoder
    with patch("hls_transcoder.executor.parallel.VideoTranscoder") as mock_transcoder_class:
        mock_transcoder = AsyncMock()
        mock_output = test_output_dir / "video_720p.m3u8"
        mock_output.parent.mkdir(parents=True, exist_ok=True)
        mock_output.touch()
        mock_transcoder.transcode.return_value = mock_output
        mock_transcoder_class.return_value = mock_transcoder

        summary = await executor.execute_tasks(
            video_tasks=[video_task],
            audio_tasks=[],
            subtitle_tasks=[],
        )

        assert summary.total_tasks == 1
        assert summary.completed_tasks == 1
        assert summary.failed_tasks == 0
        assert summary.success_rate == 100.0


@pytest.mark.asyncio
async def test_execute_single_audio_task(
    test_input_file,
    test_output_dir,
    media_info,
    hardware_info,
    config,
    execution_strategy,
    audio_task,
):
    """Test executing single audio task."""
    executor = ParallelExecutor(
        input_file=test_input_file,
        output_dir=test_output_dir,
        media_info=media_info,
        hardware_info=hardware_info,
        config=config,
        strategy=execution_strategy,
    )

    # Mock audio extractor
    with patch("hls_transcoder.executor.parallel.AudioExtractor") as mock_extractor_class:
        mock_extractor = AsyncMock()
        mock_output = test_output_dir / "audio_eng.m3u8"
        mock_output.parent.mkdir(parents=True, exist_ok=True)
        mock_output.touch()
        mock_extractor.extract.return_value = mock_output
        mock_extractor_class.return_value = mock_extractor

        summary = await executor.execute_tasks(
            video_tasks=[],
            audio_tasks=[audio_task],
            subtitle_tasks=[],
        )

        assert summary.total_tasks == 1
        assert summary.completed_tasks == 1
        assert summary.failed_tasks == 0


@pytest.mark.asyncio
async def test_execute_single_subtitle_task(
    test_input_file,
    test_output_dir,
    media_info,
    hardware_info,
    config,
    execution_strategy,
    subtitle_task,
):
    """Test executing single subtitle task."""
    executor = ParallelExecutor(
        input_file=test_input_file,
        output_dir=test_output_dir,
        media_info=media_info,
        hardware_info=hardware_info,
        config=config,
        strategy=execution_strategy,
    )

    # Mock subtitle extractor
    with patch("hls_transcoder.executor.parallel.SubtitleExtractor") as mock_extractor_class:
        mock_extractor = AsyncMock()
        mock_output = test_output_dir / "subtitle_eng.vtt"
        mock_output.parent.mkdir(parents=True, exist_ok=True)
        mock_output.touch()
        mock_extractor.extract.return_value = mock_output
        mock_extractor_class.return_value = mock_extractor

        summary = await executor.execute_tasks(
            video_tasks=[],
            audio_tasks=[],
            subtitle_tasks=[subtitle_task],
        )

        assert summary.total_tasks == 1
        assert summary.completed_tasks == 1
        assert summary.failed_tasks == 0


@pytest.mark.asyncio
async def test_execute_single_sprite_task(
    test_input_file,
    test_output_dir,
    media_info,
    hardware_info,
    config,
    execution_strategy,
    sprite_task,
):
    """Test executing single sprite task."""
    executor = ParallelExecutor(
        input_file=test_input_file,
        output_dir=test_output_dir,
        media_info=media_info,
        hardware_info=hardware_info,
        config=config,
        strategy=execution_strategy,
    )

    # Mock sprite generator
    with patch("hls_transcoder.executor.parallel.SpriteGenerator") as mock_generator_class:
        mock_generator = AsyncMock()
        mock_output = test_output_dir / "sprite.vtt"
        mock_output.parent.mkdir(parents=True, exist_ok=True)
        mock_output.touch()

        from hls_transcoder.sprites import SpriteInfo

        mock_sprite_info = SpriteInfo(
            sprite_path=test_output_dir / "sprite.jpg",
            vtt_path=mock_output,
            thumbnail_count=60,
            columns=10,
            rows=6,
            tile_width=160,
            tile_height=90,
            total_size=1024 * 100,
        )
        mock_generator.generate.return_value = mock_sprite_info
        mock_generator_class.return_value = mock_generator

        summary = await executor.execute_tasks(
            video_tasks=[],
            audio_tasks=[],
            subtitle_tasks=[],
            sprite_task=sprite_task,
        )

        assert summary.total_tasks == 1
        assert summary.completed_tasks == 1
        assert summary.failed_tasks == 0


@pytest.mark.asyncio
async def test_execute_multiple_tasks_parallel(
    test_input_file,
    test_output_dir,
    media_info,
    hardware_info,
    config,
    execution_strategy,
    video_task,
    audio_task,
    subtitle_task,
):
    """Test executing multiple tasks in parallel."""
    executor = ParallelExecutor(
        input_file=test_input_file,
        output_dir=test_output_dir,
        media_info=media_info,
        hardware_info=hardware_info,
        config=config,
        strategy=execution_strategy,
    )

    # Mock all extractors/transcoders
    with (
        patch("hls_transcoder.executor.parallel.VideoTranscoder") as mock_video,
        patch("hls_transcoder.executor.parallel.AudioExtractor") as mock_audio,
        patch("hls_transcoder.executor.parallel.SubtitleExtractor") as mock_subtitle,
    ):

        # Setup mocks
        mock_video_instance = AsyncMock()
        mock_video_instance.transcode.return_value = test_output_dir / "video.m3u8"
        mock_video.return_value = mock_video_instance

        mock_audio_instance = AsyncMock()
        mock_audio_instance.extract.return_value = test_output_dir / "audio.m3u8"
        mock_audio.return_value = mock_audio_instance

        mock_subtitle_instance = AsyncMock()
        mock_subtitle_instance.extract.return_value = test_output_dir / "subtitle.vtt"
        mock_subtitle.return_value = mock_subtitle_instance

        # Create output files
        (test_output_dir / "video.m3u8").parent.mkdir(parents=True, exist_ok=True)
        (test_output_dir / "video.m3u8").touch()
        (test_output_dir / "audio.m3u8").touch()
        (test_output_dir / "subtitle.vtt").touch()

        summary = await executor.execute_tasks(
            video_tasks=[video_task],
            audio_tasks=[audio_task],
            subtitle_tasks=[subtitle_task],
        )

        assert summary.total_tasks == 3
        assert summary.completed_tasks == 3
        assert summary.failed_tasks == 0
        assert summary.success_rate == 100.0


@pytest.mark.asyncio
async def test_execute_with_progress_callback(
    test_input_file,
    test_output_dir,
    media_info,
    hardware_info,
    config,
    execution_strategy,
    video_task,
):
    """Test execution with progress callback."""
    executor = ParallelExecutor(
        input_file=test_input_file,
        output_dir=test_output_dir,
        media_info=media_info,
        hardware_info=hardware_info,
        config=config,
        strategy=execution_strategy,
    )

    progress_updates = []

    def progress_callback(completed: int, total: int):
        progress_updates.append((completed, total))

    with patch("hls_transcoder.executor.parallel.VideoTranscoder") as mock_transcoder_class:
        mock_transcoder = AsyncMock()
        mock_output = test_output_dir / "video.m3u8"
        mock_output.parent.mkdir(parents=True, exist_ok=True)
        mock_output.touch()
        mock_transcoder.transcode.return_value = mock_output
        mock_transcoder_class.return_value = mock_transcoder

        await executor.execute_tasks(
            video_tasks=[video_task],
            audio_tasks=[],
            subtitle_tasks=[],
            progress_callback=progress_callback,
        )

        assert len(progress_updates) > 0
        assert progress_updates[-1] == (1, 1)


@pytest.mark.asyncio
async def test_execute_with_task_failure(
    test_input_file,
    test_output_dir,
    media_info,
    hardware_info,
    config,
    execution_strategy,
    video_task,
):
    """Test handling task failure."""
    executor = ParallelExecutor(
        input_file=test_input_file,
        output_dir=test_output_dir,
        media_info=media_info,
        hardware_info=hardware_info,
        config=config,
        strategy=execution_strategy,
    )

    with patch("hls_transcoder.executor.parallel.VideoTranscoder") as mock_transcoder_class:
        mock_transcoder = AsyncMock()
        mock_transcoder.transcode.side_effect = TranscodingError("Transcode failed")
        mock_transcoder_class.return_value = mock_transcoder

        summary = await executor.execute_tasks(
            video_tasks=[video_task],
            audio_tasks=[],
            subtitle_tasks=[],
        )

        assert summary.total_tasks == 1
        assert summary.completed_tasks == 0
        assert summary.failed_tasks == 1
        assert summary.has_failures is True
        assert summary.success_rate == 0.0


@pytest.mark.asyncio
async def test_execute_with_partial_failures(
    test_input_file,
    test_output_dir,
    media_info,
    hardware_info,
    config,
    execution_strategy,
):
    """Test execution with some tasks failing."""
    # Create two video tasks
    video_task1 = VideoTask(
        task_id="video_1080p",
        task_type=TaskType.VIDEO,
        input_file=test_input_file,
        output_dir=test_output_dir / "video1",
        quality="1080p",
        width=1920,
        height=1080,
        bitrate="5000k",
        encoder="libx264",
        stream_index=0,
    )

    video_task2 = VideoTask(
        task_id="video_720p",
        task_type=TaskType.VIDEO,
        input_file=test_input_file,
        output_dir=test_output_dir / "video2",
        quality="720p",
        width=1280,
        height=720,
        bitrate="3000k",
        encoder="libx264",
        stream_index=0,
    )

    executor = ParallelExecutor(
        input_file=test_input_file,
        output_dir=test_output_dir,
        media_info=media_info,
        hardware_info=hardware_info,
        config=config,
        strategy=execution_strategy,
    )

    call_count = 0

    def mock_transcode_side_effect(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            # First call succeeds
            output = test_output_dir / "video1.m3u8"
            output.parent.mkdir(parents=True, exist_ok=True)
            output.touch()
            return output
        else:
            # Second call fails
            raise TranscodingError("Failed")

    with patch("hls_transcoder.executor.parallel.VideoTranscoder") as mock_transcoder_class:
        mock_transcoder = AsyncMock()
        mock_transcoder.transcode.side_effect = mock_transcode_side_effect
        mock_transcoder_class.return_value = mock_transcoder

        summary = await executor.execute_tasks(
            video_tasks=[video_task1, video_task2],
            audio_tasks=[],
            subtitle_tasks=[],
        )

        assert summary.total_tasks == 2
        assert summary.completed_tasks == 1
        assert summary.failed_tasks == 1
        assert summary.success_rate == 50.0


@pytest.mark.asyncio
async def test_executor_properties(
    test_input_file,
    test_output_dir,
    media_info,
    hardware_info,
    config,
    execution_strategy,
):
    """Test executor properties."""
    executor = ParallelExecutor(
        input_file=test_input_file,
        output_dir=test_output_dir,
        media_info=media_info,
        hardware_info=hardware_info,
        config=config,
        strategy=execution_strategy,
    )

    assert executor.is_cancelled is False
    assert executor.completed_count == 0
    assert executor.failed_count == 0


# === Convenience Function Tests ===


@pytest.mark.asyncio
async def test_execute_parallel_function(
    test_input_file,
    test_output_dir,
    media_info,
    hardware_info,
    config,
    execution_strategy,
    video_task,
):
    """Test convenience function for parallel execution."""
    with patch("hls_transcoder.executor.parallel.VideoTranscoder") as mock_transcoder_class:
        mock_transcoder = AsyncMock()
        mock_output = test_output_dir / "video.m3u8"
        mock_output.parent.mkdir(parents=True, exist_ok=True)
        mock_output.touch()
        mock_transcoder.transcode.return_value = mock_output
        mock_transcoder_class.return_value = mock_transcoder

        summary = await execute_parallel(
            input_file=test_input_file,
            output_dir=test_output_dir,
            media_info=media_info,
            hardware_info=hardware_info,
            config=config,
            strategy=execution_strategy,
            video_tasks=[video_task],
            audio_tasks=[],
            subtitle_tasks=[],
        )

        assert isinstance(summary, ExecutionSummary)
        assert summary.total_tasks == 1
        assert summary.completed_tasks == 1
