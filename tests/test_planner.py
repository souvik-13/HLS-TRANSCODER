"""
Tests for transcoding execution planning.

This module tests the ExecutionPlanner class and related functionality
for creating transcoding plans and strategies.
"""

import pytest
from pathlib import Path
from unittest.mock import Mock, patch

from hls_transcoder.config import TranscoderConfig
from hls_transcoder.hardware import HardwareInfo
from hls_transcoder.hardware.detector import HardwareType, EncoderInfo
from hls_transcoder.models import (
    AudioStream,
    FormatInfo,
    MediaInfo,
    SubtitleStream,
    TaskType,
    VideoStream,
)
from hls_transcoder.planner import (
    ExecutionPlanner,
    ExecutionStrategy,
    ResourceEstimate,
    get_planner,
)


@pytest.fixture
def sample_video_stream():
    """Create a sample video stream for testing."""
    return VideoStream(
        index=0,
        codec="h264",
        codec_long="H.264 / AVC / MPEG-4 AVC / MPEG-4 part 10",
        profile="High",
        width=1920,
        height=1080,
        fps=24.0,
        bitrate=5000000,
        duration=600.0,
        pix_fmt="yuv420p",
    )


@pytest.fixture
def sample_audio_stream():
    """Create a sample audio stream for testing."""
    return AudioStream(
        index=1,
        codec="aac",
        codec_long="AAC (Advanced Audio Coding)",
        profile="LC",
        channels=2,
        sample_rate=48000,
        bitrate=128000,
        duration=600.0,
        language="eng",
    )


@pytest.fixture
def sample_subtitle_stream():
    """Create a sample subtitle stream for testing."""
    return SubtitleStream(
        index=2,
        codec="subrip",
        language="eng",
    )


@pytest.fixture
def sample_format_info():
    """Create a sample format info for testing."""
    return FormatInfo(
        format_name="matroska,webm",
        format_long_name="Matroska / WebM",
        duration=600.0,
        size=100000000,  # 100 MB
        bitrate=1333333,
    )


@pytest.fixture
def sample_media_info(
    sample_format_info, sample_video_stream, sample_audio_stream, sample_subtitle_stream
):
    """Create a sample media info for testing."""
    return MediaInfo(
        format=sample_format_info,
        video_streams=[sample_video_stream],
        audio_streams=[sample_audio_stream, sample_audio_stream],  # 2 audio tracks
        subtitle_streams=[sample_subtitle_stream],
        duration=600.0,
        size=100000000,
        bitrate=1333333,
    )


@pytest.fixture
def sample_hardware_info():
    """Create a sample hardware info for testing."""
    encoder = EncoderInfo(
        name="h264_nvenc",
        hardware_type=HardwareType.NVIDIA,
        display_name="NVIDIA NVENC H.264",
        available=True,
        tested=True,
    )
    return HardwareInfo(
        detected_type=HardwareType.NVIDIA,
        available_encoders=[encoder],
        selected_encoder=encoder,
    )


@pytest.fixture
def sample_config():
    """Create a sample configuration for testing."""
    return TranscoderConfig.create_default()


@pytest.fixture
def planner(sample_media_info, sample_hardware_info, sample_config, tmp_path):
    """Create an execution planner for testing."""
    input_file = tmp_path / "input.mkv"
    input_file.touch()
    output_dir = tmp_path / "output"

    return ExecutionPlanner(
        input_file=input_file,
        media_info=sample_media_info,
        hardware_info=sample_hardware_info,
        config=sample_config,
        output_dir=output_dir,
        profile_name="medium",
    )


# Test ExecutionStrategy


class TestExecutionStrategy:
    """Tests for ExecutionStrategy class."""

    def test_creation(self):
        """Test strategy creation."""
        strategy = ExecutionStrategy(
            video_concurrency=2,
            audio_concurrency=2,
            subtitle_concurrency=1,
            sprite_separate=False,
            max_total_concurrent=4,
        )

        assert strategy.video_concurrency == 2
        assert strategy.audio_concurrency == 2
        assert strategy.subtitle_concurrency == 1
        assert not strategy.sprite_separate
        assert strategy.max_total_concurrent == 4

    def test_validation(self):
        """Test that invalid concurrency values are corrected."""
        strategy = ExecutionStrategy(
            video_concurrency=0,
            audio_concurrency=-1,
            subtitle_concurrency=0,
            sprite_separate=False,
            max_total_concurrent=0,
        )

        assert strategy.video_concurrency == 1
        assert strategy.audio_concurrency == 1
        assert strategy.subtitle_concurrency == 1
        assert strategy.max_total_concurrent == 1

    def test_total_workers(self):
        """Test total workers calculation."""
        strategy = ExecutionStrategy(
            video_concurrency=2,
            audio_concurrency=2,
            subtitle_concurrency=1,
            sprite_separate=True,
            max_total_concurrent=6,
        )

        # 2 + 2 + 1 + 1 (sprite) = 6
        assert strategy.total_workers == 6

    def test_total_workers_no_sprite(self):
        """Test total workers without separate sprite task."""
        strategy = ExecutionStrategy(
            video_concurrency=2,
            audio_concurrency=2,
            subtitle_concurrency=1,
            sprite_separate=False,
            max_total_concurrent=5,
        )

        # 2 + 2 + 1 = 5
        assert strategy.total_workers == 5


# Test ResourceEstimate


class TestResourceEstimate:
    """Tests for ResourceEstimate class."""

    def test_creation(self):
        """Test resource estimate creation."""
        estimate = ResourceEstimate(
            estimated_duration=300.0,
            estimated_output_size=50000000,
            peak_memory_mb=2000,
            disk_space_needed=60000000,
            cpu_cores_needed=4,
            gpu_memory_mb=1000,
        )

        assert estimate.estimated_duration == 300.0
        assert estimate.estimated_output_size == 50000000
        assert estimate.peak_memory_mb == 2000
        assert estimate.disk_space_needed == 60000000
        assert estimate.cpu_cores_needed == 4
        assert estimate.gpu_memory_mb == 1000

    def test_duration_per_task(self):
        """Test duration per task property."""
        estimate = ResourceEstimate(
            estimated_duration=300.0,
            estimated_output_size=50000000,
            peak_memory_mb=2000,
            disk_space_needed=60000000,
            cpu_cores_needed=4,
            gpu_memory_mb=1000,
        )

        assert estimate.duration_per_task == 300.0

    def test_space_with_buffer(self):
        """Test space with buffer calculation."""
        estimate = ResourceEstimate(
            estimated_duration=300.0,
            estimated_output_size=50000000,
            peak_memory_mb=2000,
            disk_space_needed=60000000,
            cpu_cores_needed=4,
            gpu_memory_mb=1000,
        )

        # 60MB * 1.2 = 72MB
        assert estimate.space_with_buffer == 72000000


# Test ExecutionPlanner


class TestExecutionPlanner:
    """Tests for ExecutionPlanner class."""

    def test_initialization(self, planner):
        """Test planner initialization."""
        assert planner.media_info is not None
        assert planner.hardware_info is not None
        assert planner.config is not None
        assert planner.profile is not None
        assert planner.profile_name == "medium"

    def test_invalid_profile(
        self, sample_media_info, sample_hardware_info, sample_config, tmp_path
    ):
        """Test initialization with invalid profile."""
        input_file = tmp_path / "input.mkv"
        input_file.touch()

        with pytest.raises(ValueError, match="Profile 'invalid' not found"):
            ExecutionPlanner(
                input_file=input_file,
                media_info=sample_media_info,
                hardware_info=sample_hardware_info,
                config=sample_config,
                output_dir=tmp_path / "output",
                profile_name="invalid",
            )

    def test_calculate_quality_ladder(self, planner):
        """Test quality ladder calculation."""
        qualities = planner._calculate_quality_ladder()

        # Medium profile should include 720p, 480p, 360p for 1080p source
        assert len(qualities) > 0
        assert all(q.height <= 1080 for q in qualities)
        # Should be sorted by height descending
        heights = [q.height for q in qualities]
        assert heights == sorted(heights, reverse=True)

    def test_calculate_quality_ladder_original_only(self, planner):
        """Test quality ladder with original_only mode."""
        qualities = planner._calculate_quality_ladder(original_only=True)

        assert len(qualities) == 1
        assert qualities[0].name == "original"
        assert qualities[0].height == 1080
        assert qualities[0].width == 1920

    def test_calculate_quality_ladder_4k_source(self, planner, sample_media_info):
        """Test quality ladder for 4K source."""
        # Update source to 4K
        sample_media_info.video_streams[0].width = 3840
        sample_media_info.video_streams[0].height = 2160

        qualities = planner._calculate_quality_ladder()

        # Should include multiple variants up to 2160p
        assert len(qualities) > 0
        assert max(q.height for q in qualities) <= 2160

    def test_create_video_tasks(self, planner):
        """Test video task creation."""
        qualities = planner._calculate_quality_ladder()
        tasks = planner._create_video_tasks(qualities)

        assert len(tasks) == len(qualities)
        for task in tasks:
            assert task.task_type == TaskType.VIDEO
            assert task.input_file.exists()
            assert task.encoder == "h264_nvenc"
            assert task.stream_index == 0

    def test_create_audio_tasks(self, planner):
        """Test audio task creation."""
        tasks = planner._create_audio_tasks()

        # Should have 2 tasks (2 audio streams)
        assert len(tasks) == 2
        for task in tasks:
            assert task.task_type == TaskType.AUDIO
            assert task.input_file.exists()
            assert task.codec == "aac"
            assert task.bitrate == "128k"

    def test_create_subtitle_tasks(self, planner):
        """Test subtitle task creation."""
        tasks = planner._create_subtitle_tasks()

        # Should have 1 task (1 subtitle stream)
        assert len(tasks) == 1
        task = tasks[0]
        assert task.task_type == TaskType.SUBTITLE
        assert task.input_file.exists()
        assert task.format == "webvtt"
        assert task.language == "eng"

    def test_create_sprite_task(self, planner):
        """Test sprite task creation."""
        task = planner._create_sprite_task()

        assert task.task_type == TaskType.SPRITE
        assert task.input_file.exists()
        assert task.interval == 10
        assert task.width == 160
        assert task.height == 90
        assert task.columns == 10
        assert task.rows == 10

    def test_create_plan(self, planner):
        """Test complete plan creation."""
        plan = planner.create_plan()

        assert len(plan.video_tasks) > 0
        assert len(plan.audio_tasks) == 2
        assert len(plan.subtitle_tasks) == 1
        assert plan.sprite_task is not None
        assert plan.total_tasks > 0
        assert plan.estimated_duration > 0
        assert plan.estimated_size > 0

    def test_create_plan_original_only(self, planner):
        """Test plan creation with original_only mode."""
        plan = planner.create_plan(original_only=True)

        # Should only have 1 video task
        assert len(plan.video_tasks) == 1
        assert plan.video_tasks[0].quality == "original"

    def test_create_plan_no_audio(self, planner):
        """Test plan creation without audio."""
        plan = planner.create_plan(include_audio=False)

        assert len(plan.audio_tasks) == 0

    def test_create_plan_no_subtitles(self, planner):
        """Test plan creation without subtitles."""
        plan = planner.create_plan(include_subtitles=False)

        assert len(plan.subtitle_tasks) == 0

    def test_create_plan_no_sprites(self, planner):
        """Test plan creation without sprites."""
        plan = planner.create_plan(include_sprites=False)

        assert plan.sprite_task is None

    def test_estimate_resources(self, planner):
        """Test resource estimation."""
        plan = planner.create_plan()
        estimate = planner.estimate_resources(plan)

        assert isinstance(estimate, ResourceEstimate)
        assert estimate.estimated_duration > 0
        assert estimate.estimated_output_size > 0
        assert estimate.peak_memory_mb > 0
        assert estimate.disk_space_needed > 0
        assert estimate.cpu_cores_needed > 0
        assert estimate.gpu_memory_mb > 0  # NVENC uses GPU memory

    def test_estimate_resources_software_encoding(self, sample_media_info, sample_config, tmp_path):
        """Test resource estimation with software encoding."""
        input_file = tmp_path / "input.mkv"
        input_file.touch()

        # Create hardware info for software encoding
        encoder = EncoderInfo(
            name="libx264",
            hardware_type=HardwareType.SOFTWARE,
            display_name="Software H.264",
            available=True,
        )
        hardware_info = HardwareInfo(
            detected_type=HardwareType.SOFTWARE,
            available_encoders=[encoder],
            selected_encoder=encoder,
        )

        planner = ExecutionPlanner(
            input_file=input_file,
            media_info=sample_media_info,
            hardware_info=hardware_info,
            config=sample_config,
            output_dir=tmp_path / "output",
        )

        plan = planner.create_plan()
        estimate = planner.estimate_resources(plan)

        # Software encoding should not use GPU memory
        assert estimate.gpu_memory_mb == 0
        # Should estimate longer duration (software is slower)
        assert estimate.estimated_duration > 0

    def test_create_execution_strategy(self, planner):
        """Test execution strategy creation."""
        plan = planner.create_plan()
        strategy = planner.create_execution_strategy(plan)

        assert isinstance(strategy, ExecutionStrategy)
        assert strategy.video_concurrency > 0
        assert strategy.audio_concurrency > 0
        assert strategy.subtitle_concurrency > 0
        assert strategy.max_total_concurrent == 4  # Default from config

    def test_create_execution_strategy_custom_max(self, planner):
        """Test execution strategy with custom max concurrent."""
        plan = planner.create_plan()
        strategy = planner.create_execution_strategy(plan, max_concurrent=8)

        assert strategy.max_total_concurrent == 8

    @patch("os.cpu_count", return_value=8)
    def test_create_execution_strategy_software_encoding(
        self, mock_cpu_count, sample_media_info, sample_config, tmp_path
    ):
        """Test execution strategy with software encoding."""
        input_file = tmp_path / "input.mkv"
        input_file.touch()

        # Create hardware info for software encoding
        encoder = EncoderInfo(
            name="libx264",
            hardware_type=HardwareType.SOFTWARE,
            display_name="Software H.264",
            available=True,
        )
        hardware_info = HardwareInfo(
            detected_type=HardwareType.SOFTWARE,
            available_encoders=[encoder],
            selected_encoder=encoder,
        )

        planner = ExecutionPlanner(
            input_file=input_file,
            media_info=sample_media_info,
            hardware_info=hardware_info,
            config=sample_config,
            output_dir=tmp_path / "output",
        )

        plan = planner.create_plan()
        strategy = planner.create_execution_strategy(plan)

        # With 8 CPU cores, should use 4 (half)
        assert strategy.video_concurrency <= 4


# Test get_planner function


def test_get_planner(sample_media_info, sample_hardware_info, sample_config, tmp_path):
    """Test get_planner convenience function."""
    input_file = tmp_path / "input.mkv"
    input_file.touch()

    planner = get_planner(
        input_file=input_file,
        media_info=sample_media_info,
        hardware_info=sample_hardware_info,
        config=sample_config,
        output_dir=tmp_path / "output",
        profile_name="medium",
    )

    assert isinstance(planner, ExecutionPlanner)
    assert planner.profile_name == "medium"


def test_get_planner_creates_new_instance(
    sample_media_info, sample_hardware_info, sample_config, tmp_path
):
    """Test that get_planner always creates a new instance."""
    input_file = tmp_path / "input.mkv"
    input_file.touch()

    planner1 = get_planner(
        input_file=input_file,
        media_info=sample_media_info,
        hardware_info=sample_hardware_info,
        config=sample_config,
        output_dir=tmp_path / "output1",
        profile_name="medium",
    )

    planner2 = get_planner(
        input_file=input_file,
        media_info=sample_media_info,
        hardware_info=sample_hardware_info,
        config=sample_config,
        output_dir=tmp_path / "output2",
        profile_name="high",
    )

    # Should be different instances
    assert planner1 is not planner2
    assert planner1.profile_name == "medium"
    assert planner2.profile_name == "high"
