"""
Tests for sprite generation module.
"""

import asyncio
from pathlib import Path
from typing import Optional
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from hls_transcoder.sprites import (
    SpriteConfig,
    SpriteGenerator,
    SpriteInfo,
    generate_sprite,
)
from hls_transcoder.utils import FFmpegError, TranscodingError


# === Fixtures ===


@pytest.fixture
def test_input_file(tmp_path):
    """Create test input video file."""
    input_file = tmp_path / "input.mp4"
    input_file.touch()
    return input_file


@pytest.fixture
def test_output_dir(tmp_path):
    """Create test output directory."""
    return tmp_path / "sprites"


@pytest.fixture
def sprite_config():
    """Create default sprite configuration."""
    return SpriteConfig(
        interval=10,
        width=160,
        height=90,
        columns=10,
        rows=10,
        quality=2,
    )


@pytest.fixture
def custom_sprite_config():
    """Create custom sprite configuration."""
    return SpriteConfig(
        interval=5,
        width=120,
        height=68,
        columns=8,
        rows=8,
        quality=3,
    )


# === SpriteConfig Tests ===


def test_sprite_config_creation():
    """Test creating sprite configuration."""
    config = SpriteConfig(
        interval=10,
        width=160,
        height=90,
        columns=10,
        rows=10,
        quality=2,
    )

    assert config.interval == 10
    assert config.width == 160
    assert config.height == 90
    assert config.columns == 10
    assert config.rows == 10
    assert config.quality == 2


def test_sprite_config_defaults():
    """Test default sprite configuration values."""
    config = SpriteConfig()

    assert config.interval == 10
    assert config.width == 160
    assert config.height == 90
    assert config.columns == 10
    assert config.rows == 10
    assert config.quality == 2


# === SpriteInfo Tests ===


def test_sprite_info_creation(tmp_path):
    """Test creating sprite info."""
    sprite_path = tmp_path / "sprite.jpg"
    vtt_path = tmp_path / "sprite.vtt"
    sprite_path.touch()
    vtt_path.touch()

    info = SpriteInfo(
        sprite_path=sprite_path,
        vtt_path=vtt_path,
        thumbnail_count=50,
        columns=10,
        rows=5,
        tile_width=160,
        tile_height=90,
        total_size=1024 * 1024,  # 1 MB
    )

    assert info.sprite_path == sprite_path
    assert info.vtt_path == vtt_path
    assert info.thumbnail_count == 50
    assert info.columns == 10
    assert info.rows == 5
    assert info.tile_width == 160
    assert info.tile_height == 90
    assert info.total_size == 1024 * 1024


def test_sprite_info_size_mb(tmp_path):
    """Test size_mb property."""
    sprite_path = tmp_path / "sprite.jpg"
    vtt_path = tmp_path / "sprite.vtt"
    sprite_path.touch()
    vtt_path.touch()

    info = SpriteInfo(
        sprite_path=sprite_path,
        vtt_path=vtt_path,
        thumbnail_count=50,
        columns=10,
        rows=5,
        tile_width=160,
        tile_height=90,
        total_size=2 * 1024 * 1024,  # 2 MB
    )

    assert info.size_mb == 2.0


# === SpriteGenerator Tests ===


def test_sprite_generator_initialization(test_input_file, test_output_dir):
    """Test sprite generator initialization."""
    generator = SpriteGenerator(
        input_file=test_input_file,
        output_dir=test_output_dir,
        duration=600.0,  # 10 minutes
    )

    assert generator.input_file == test_input_file
    assert generator.output_dir == test_output_dir
    assert generator.duration == 600.0
    assert test_output_dir.exists()


def test_sprite_generator_creates_output_directory(test_input_file, test_output_dir):
    """Test that output directory is created."""
    assert not test_output_dir.exists()

    SpriteGenerator(
        input_file=test_input_file,
        output_dir=test_output_dir,
        duration=300.0,
    )

    assert test_output_dir.exists()


def test_calculate_thumbnail_count_full_duration(test_input_file, test_output_dir):
    """Test thumbnail count calculation for full duration."""
    generator = SpriteGenerator(test_input_file, test_output_dir, duration=600.0)
    config = SpriteConfig(interval=10, columns=10, rows=10)

    count = generator._calculate_thumbnail_count(config)

    # 600 seconds / 10 second interval = 60 thumbnails
    assert count == 60


def test_calculate_thumbnail_count_exceeds_max(test_input_file, test_output_dir):
    """Test thumbnail count capped at max tiles."""
    generator = SpriteGenerator(test_input_file, test_output_dir, duration=2000.0)
    config = SpriteConfig(interval=10, columns=10, rows=10)

    count = generator._calculate_thumbnail_count(config)

    # 2000 / 10 = 200, but max is 10x10 = 100
    assert count == 100


def test_calculate_thumbnail_count_minimum(test_input_file, test_output_dir):
    """Test minimum thumbnail count is 1."""
    generator = SpriteGenerator(test_input_file, test_output_dir, duration=5.0)
    config = SpriteConfig(interval=10, columns=10, rows=10)

    count = generator._calculate_thumbnail_count(config)

    # Duration < interval, but should still be 1
    assert count == 1


def test_build_thumbnail_command(test_input_file, test_output_dir):
    """Test building thumbnail extraction command."""
    generator = SpriteGenerator(test_input_file, test_output_dir, duration=300.0)
    config = SpriteConfig(interval=10, width=160, height=90, quality=2)
    temp_dir = test_output_dir / "temp"

    command = generator._build_thumbnail_command(config, temp_dir, 30)

    assert "ffmpeg" in command
    assert "-hide_banner" in command
    assert "-y" in command
    assert "-i" in command
    assert str(test_input_file) in command
    assert "-vf" in command
    # Check that fps and scale are in the filter string
    filter_str = " ".join(command)
    assert "fps=1/10" in filter_str
    assert "scale=160:90" in filter_str
    assert "-frames:v" in command
    assert "30" in command
    assert "-q:v" in command
    assert "2" in command


def test_build_sprite_command(test_input_file, test_output_dir):
    """Test building sprite sheet command."""
    generator = SpriteGenerator(test_input_file, test_output_dir, duration=300.0)
    config = SpriteConfig(columns=10, rows=10, quality=2)
    temp_dir = test_output_dir / "temp"
    sprite_path = test_output_dir / "sprite.jpg"

    command = generator._build_sprite_command(config, temp_dir, sprite_path, 30)

    assert "ffmpeg" in command
    assert "-hide_banner" in command
    assert "-y" in command
    assert "-start_number" in command
    assert "1" in command
    assert "-i" in command
    assert "-frames:v" in command
    assert "30" in command
    assert "-filter_complex" in command
    assert "tile=10x3" in command  # 30 thumbnails = 10 cols x 3 rows
    assert "-q:v" in command
    assert "2" in command
    assert str(sprite_path) in command


def test_format_vtt_timestamp(test_input_file, test_output_dir):
    """Test VTT timestamp formatting."""
    generator = SpriteGenerator(test_input_file, test_output_dir, duration=300.0)

    # Test various timestamps
    assert generator._format_vtt_timestamp(0) == "00:00:00.000"
    assert generator._format_vtt_timestamp(10.5) == "00:00:10.500"
    assert generator._format_vtt_timestamp(65.123) == "00:01:05.123"
    assert generator._format_vtt_timestamp(3661.456) == "01:01:01.456"


def test_generate_vtt(test_input_file, test_output_dir):
    """Test WebVTT generation."""
    generator = SpriteGenerator(test_input_file, test_output_dir, duration=100.0)
    config = SpriteConfig(interval=10, width=160, height=90, columns=5, rows=2)
    sprite_path = test_output_dir / "sprite.jpg"
    sprite_path.touch()

    vtt_path = generator._generate_vtt(config, sprite_path, 10)

    assert vtt_path.exists()
    content = vtt_path.read_text()

    # Check header
    assert content.startswith("WEBVTT\n")

    # Check for cues
    assert "00:00:00.000 --> 00:00:10.000" in content
    assert "sprite.jpg#xywh=0,0,160,90" in content

    # Check second thumbnail (second column)
    assert "00:00:10.000 --> 00:00:20.000" in content
    assert "sprite.jpg#xywh=160,0,160,90" in content

    # Check sixth thumbnail (second row, first column)
    assert "00:00:50.000 --> 00:01:00.000" in content
    assert "sprite.jpg#xywh=0,90,160,90" in content


def test_cleanup_temp_files(test_input_file, test_output_dir):
    """Test temporary file cleanup."""
    generator = SpriteGenerator(test_input_file, test_output_dir, duration=300.0)

    # Create temp directory with files
    temp_dir = test_output_dir / "temp"
    temp_dir.mkdir()
    (temp_dir / "thumb_0001.jpg").touch()
    (temp_dir / "thumb_0002.jpg").touch()
    (temp_dir / "thumb_0003.jpg").touch()

    generator._cleanup_temp_files(temp_dir)

    # All files and directory should be removed
    assert not (temp_dir / "thumb_0001.jpg").exists()
    assert not (temp_dir / "thumb_0002.jpg").exists()
    assert not (temp_dir / "thumb_0003.jpg").exists()
    assert not temp_dir.exists()


def test_cleanup_temp_files_nonexistent(test_input_file, test_output_dir):
    """Test cleanup with nonexistent directory."""
    generator = SpriteGenerator(test_input_file, test_output_dir, duration=300.0)
    temp_dir = test_output_dir / "nonexistent"

    # Should not raise error
    generator._cleanup_temp_files(temp_dir)


@pytest.mark.asyncio
async def test_generate_sprite_success(test_input_file, test_output_dir, sprite_config):
    """Test successful sprite generation."""
    generator = SpriteGenerator(test_input_file, test_output_dir, duration=100.0)

    with patch("hls_transcoder.sprites.generator.AsyncFFmpegProcess") as mock_process_class:
        mock_process = AsyncMock()
        mock_process.run.return_value = ("", "")
        mock_process_class.return_value = mock_process

        # Create expected output files
        sprite_path = test_output_dir / "sprite.jpg"
        sprite_path.write_bytes(b"fake sprite data")

        # Create temp thumbnails
        temp_dir = test_output_dir / "temp_thumbnails"
        temp_dir.mkdir(exist_ok=True)
        for i in range(1, 11):
            (temp_dir / f"thumb_{i:04d}.jpg").touch()

        result = await generator.generate(config=sprite_config)

        assert isinstance(result, SpriteInfo)
        assert result.sprite_path.exists()
        assert result.vtt_path.exists()
        assert result.thumbnail_count == 10
        assert result.total_size > 0


@pytest.mark.asyncio
async def test_generate_sprite_with_progress(test_input_file, test_output_dir, sprite_config):
    """Test sprite generation with progress callback."""
    generator = SpriteGenerator(test_input_file, test_output_dir, duration=100.0)
    progress_values = []

    def progress_callback(current: float, total: Optional[float] = None):
        progress_values.append(current)

    with patch("hls_transcoder.sprites.generator.AsyncFFmpegProcess") as mock_process_class:
        mock_process = AsyncMock()
        mock_process.run.return_value = ("", "")
        mock_process_class.return_value = mock_process

        # Create output files
        sprite_path = test_output_dir / "sprite.jpg"
        sprite_path.write_bytes(b"fake sprite data")

        # Create temp thumbnails
        temp_dir = test_output_dir / "temp_thumbnails"
        temp_dir.mkdir(exist_ok=True)
        for i in range(1, 11):
            (temp_dir / f"thumb_{i:04d}.jpg").touch()

        await generator.generate(
            config=sprite_config,
            progress_callback=progress_callback,
        )

        # Should have progress updates
        assert len(progress_values) > 0
        assert progress_values[-1] == 1.0  # Final progress


@pytest.mark.asyncio
async def test_generate_sprite_default_config(test_input_file, test_output_dir):
    """Test sprite generation with default config."""
    generator = SpriteGenerator(test_input_file, test_output_dir, duration=100.0)

    with patch("hls_transcoder.sprites.generator.AsyncFFmpegProcess") as mock_process_class:
        mock_process = AsyncMock()
        mock_process.run.return_value = ("", "")
        mock_process_class.return_value = mock_process

        # Create output files
        sprite_path = test_output_dir / "sprite.jpg"
        sprite_path.write_bytes(b"fake sprite data")

        # Create temp thumbnails
        temp_dir = test_output_dir / "temp_thumbnails"
        temp_dir.mkdir(exist_ok=True)
        for i in range(1, 11):
            (temp_dir / f"thumb_{i:04d}.jpg").touch()

        result = await generator.generate()  # No config provided

        assert isinstance(result, SpriteInfo)
        assert result.sprite_path.exists()


@pytest.mark.asyncio
async def test_generate_sprite_thumbnail_extraction_failure(
    test_input_file, test_output_dir, sprite_config
):
    """Test handling thumbnail extraction failure."""
    generator = SpriteGenerator(test_input_file, test_output_dir, duration=100.0)

    with patch("hls_transcoder.sprites.generator.AsyncFFmpegProcess") as mock_process_class:
        mock_process = AsyncMock()
        mock_process.run.side_effect = FFmpegError("Extraction failed", command=[], stderr="Error")
        mock_process_class.return_value = mock_process

        with pytest.raises(TranscodingError, match="Thumbnail extraction failed"):
            await generator.generate(config=sprite_config)


@pytest.mark.asyncio
async def test_generate_sprite_no_thumbnails_created(
    test_input_file, test_output_dir, sprite_config
):
    """Test error when no thumbnails are created."""
    generator = SpriteGenerator(test_input_file, test_output_dir, duration=100.0)

    with patch("hls_transcoder.sprites.generator.AsyncFFmpegProcess") as mock_process_class:
        mock_process = AsyncMock()
        mock_process.run.return_value = ("", "")
        mock_process_class.return_value = mock_process

        # Don't create thumbnails - simulating failure

        with pytest.raises(TranscodingError, match="No thumbnails were generated"):
            await generator.generate(config=sprite_config)


@pytest.mark.asyncio
async def test_generate_sprite_sheet_creation_failure(
    test_input_file, test_output_dir, sprite_config
):
    """Test handling sprite sheet creation failure."""
    generator = SpriteGenerator(test_input_file, test_output_dir, duration=100.0)

    call_count = 0

    def mock_run_side_effect():
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            # First call (thumbnail extraction) succeeds
            return ("", "")
        else:
            # Second call (sprite creation) fails
            raise FFmpegError("Sprite creation failed", command=[], stderr="Error")

    with patch("hls_transcoder.sprites.generator.AsyncFFmpegProcess") as mock_process_class:
        mock_process = AsyncMock()
        mock_process.run.side_effect = mock_run_side_effect
        mock_process_class.return_value = mock_process

        # Create temp thumbnails for first step
        temp_dir = test_output_dir / "temp_thumbnails"
        temp_dir.mkdir(exist_ok=True)
        for i in range(1, 11):
            (temp_dir / f"thumb_{i:04d}.jpg").touch()

        with pytest.raises(TranscodingError, match="Sprite sheet creation failed"):
            await generator.generate(config=sprite_config)


@pytest.mark.asyncio
async def test_generate_sprite_cleanup_on_error(test_input_file, test_output_dir, sprite_config):
    """Test that temp files are cleaned up on error."""
    generator = SpriteGenerator(test_input_file, test_output_dir, duration=100.0)

    with patch("hls_transcoder.sprites.generator.AsyncFFmpegProcess") as mock_process_class:
        mock_process = AsyncMock()
        mock_process.run.side_effect = FFmpegError("Failed", command=[], stderr="Error")
        mock_process_class.return_value = mock_process

        # Create temp directory
        temp_dir = test_output_dir / "temp_thumbnails"
        temp_dir.mkdir(exist_ok=True)
        (temp_dir / "thumb_0001.jpg").touch()

        try:
            await generator.generate(config=sprite_config)
        except TranscodingError:
            pass

        # Temp files should be cleaned up even on error
        assert not (temp_dir / "thumb_0001.jpg").exists()
        assert not temp_dir.exists()


# === Convenience Function Tests ===


@pytest.mark.asyncio
async def test_generate_sprite_function(test_input_file, test_output_dir, sprite_config):
    """Test convenience function for sprite generation."""
    with patch("hls_transcoder.sprites.generator.AsyncFFmpegProcess") as mock_process_class:
        mock_process = AsyncMock()
        mock_process.run.return_value = ("", "")
        mock_process_class.return_value = mock_process

        # Create output directory and files
        test_output_dir.mkdir(parents=True, exist_ok=True)
        sprite_path = test_output_dir / "sprite.jpg"
        sprite_path.write_bytes(b"fake sprite data")

        # Create temp thumbnails
        temp_dir = test_output_dir / "temp_thumbnails"
        temp_dir.mkdir(exist_ok=True)
        for i in range(1, 11):
            (temp_dir / f"thumb_{i:04d}.jpg").touch()

        result = await generate_sprite(
            input_file=test_input_file,
            output_dir=test_output_dir,
            duration=100.0,
            config=sprite_config,
        )

        assert isinstance(result, SpriteInfo)
        assert result.sprite_path.exists()
        assert result.vtt_path.exists()


@pytest.mark.asyncio
async def test_generate_sprite_function_with_progress(test_input_file, test_output_dir):
    """Test convenience function with progress callback."""
    progress_values = []

    def progress_callback(current: float, total: Optional[float] = None):
        progress_values.append(current)

    with patch("hls_transcoder.sprites.generator.AsyncFFmpegProcess") as mock_process_class:
        mock_process = AsyncMock()
        mock_process.run.return_value = ("", "")
        mock_process_class.return_value = mock_process

        # Create output directory and files
        test_output_dir.mkdir(parents=True, exist_ok=True)
        sprite_path = test_output_dir / "sprite.jpg"
        sprite_path.write_bytes(b"fake sprite data")

        # Create temp thumbnails
        temp_dir = test_output_dir / "temp_thumbnails"
        temp_dir.mkdir(exist_ok=True)
        for i in range(1, 11):
            (temp_dir / f"thumb_{i:04d}.jpg").touch()

        await generate_sprite(
            input_file=test_input_file,
            output_dir=test_output_dir,
            duration=100.0,
            progress_callback=progress_callback,
        )

        assert len(progress_values) > 0
        assert progress_values[-1] == 1.0
