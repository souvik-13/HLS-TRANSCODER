"""
Tests for subtitle extraction module.
"""

import asyncio
from pathlib import Path
from typing import Optional
from unittest.mock import AsyncMock, MagicMock, call, patch

import pytest

from hls_transcoder.models import SubtitleStream
from hls_transcoder.transcoder import (
    SubtitleExtractor,
    SubtitleExtractionOptions,
    extract_all_subtitles,
)
from hls_transcoder.utils import FFmpegError, TranscodingError


# === Fixtures ===


@pytest.fixture
def test_input_file(tmp_path):
    """Create test input file."""
    input_file = tmp_path / "input.mkv"
    input_file.touch()
    return input_file


@pytest.fixture
def test_output_dir(tmp_path):
    """Create test output directory."""
    return tmp_path / "output"


@pytest.fixture
def subtitle_stream():
    """Create sample subtitle stream."""
    return SubtitleStream(
        index=2,
        codec="subrip",
        language="eng",
        title="English",
        forced=False,
    )


@pytest.fixture
def forced_subtitle_stream():
    """Create forced subtitle stream."""
    return SubtitleStream(
        index=3,
        codec="ass",
        language="eng",
        title="English Forced",
        forced=True,
    )


@pytest.fixture
def multi_subtitle_streams():
    """Create multiple subtitle streams."""
    return [
        SubtitleStream(index=2, codec="subrip", language="eng", title="English", forced=False),
        SubtitleStream(index=3, codec="ass", language="fra", title="French", forced=False),
        SubtitleStream(index=4, codec="webvtt", language="spa", title="Spanish", forced=False),
    ]


# === SubtitleExtractionOptions Tests ===


def test_subtitle_extraction_options_creation(subtitle_stream, tmp_path):
    """Test creating subtitle extraction options."""
    output_path = tmp_path / "subtitle.vtt"

    options = SubtitleExtractionOptions(
        subtitle_stream=subtitle_stream,
        output_path=output_path,
        format="webvtt",
    )

    assert options.subtitle_stream == subtitle_stream
    assert options.output_path == output_path
    assert options.format == "webvtt"


def test_subtitle_extraction_options_defaults(subtitle_stream, tmp_path):
    """Test default values for extraction options."""
    output_path = tmp_path / "subtitle.vtt"

    options = SubtitleExtractionOptions(
        subtitle_stream=subtitle_stream,
        output_path=output_path,
    )

    assert options.format == "webvtt"  # Default format


# === SubtitleExtractor Tests ===


def test_subtitle_extractor_initialization(test_input_file, test_output_dir):
    """Test subtitle extractor initialization."""
    extractor = SubtitleExtractor(
        input_file=test_input_file,
        output_dir=test_output_dir,
    )

    assert extractor.input_file == test_input_file
    assert extractor.output_dir == test_output_dir
    assert test_output_dir.exists()


def test_subtitle_extractor_creates_output_directory(test_input_file, test_output_dir):
    """Test that output directory is created if it doesn't exist."""
    assert not test_output_dir.exists()

    SubtitleExtractor(
        input_file=test_input_file,
        output_dir=test_output_dir,
    )

    assert test_output_dir.exists()


def test_get_codec_webvtt(test_input_file, test_output_dir):
    """Test codec selection for WebVTT."""
    extractor = SubtitleExtractor(test_input_file, test_output_dir)

    assert extractor._get_codec("webvtt", "subrip") == "webvtt"
    assert extractor._get_codec("vtt", "subrip") == "webvtt"

    # Test copy when input matches output
    assert extractor._get_codec("webvtt", "webvtt") == "copy"


def test_get_codec_srt(test_input_file, test_output_dir):
    """Test codec selection for SRT."""
    extractor = SubtitleExtractor(test_input_file, test_output_dir)

    assert extractor._get_codec("srt", "webvtt") == "srt"
    assert extractor._get_codec("srt", "srt") == "copy"


def test_get_codec_ass(test_input_file, test_output_dir):
    """Test codec selection for ASS."""
    extractor = SubtitleExtractor(test_input_file, test_output_dir)

    assert extractor._get_codec("ass", "webvtt") == "ass"
    assert extractor._get_codec("ssa", "webvtt") == "ass"
    assert extractor._get_codec("ass", "ass") == "copy"


def test_get_extension(test_input_file, test_output_dir):
    """Test extension selection for formats."""
    extractor = SubtitleExtractor(test_input_file, test_output_dir)

    assert extractor._get_extension("webvtt") == "vtt"
    assert extractor._get_extension("vtt") == "vtt"
    assert extractor._get_extension("srt") == "srt"
    assert extractor._get_extension("ass") == "ass"
    assert extractor._get_extension("ssa") == "ass"


def test_get_extension_unknown_format(test_input_file, test_output_dir):
    """Test extension defaults to vtt for unknown formats."""
    extractor = SubtitleExtractor(test_input_file, test_output_dir)

    assert extractor._get_extension("unknown") == "vtt"


def test_build_command_basic(test_input_file, test_output_dir, subtitle_stream):
    """Test building basic extraction command."""
    extractor = SubtitleExtractor(test_input_file, test_output_dir)
    output_file = test_output_dir / "subtitle.vtt"

    command = extractor._build_command(
        subtitle_stream=subtitle_stream,
        output_file=output_file,
        output_format="webvtt",
    )

    assert "ffmpeg" in command
    assert "-hide_banner" in command
    assert "-y" in command
    assert "-i" in command
    assert str(test_input_file) in command
    assert "-map" in command
    assert f"0:{subtitle_stream.index}" in command
    assert "-c:s" in command
    assert "webvtt" in command
    assert str(output_file) in command


def test_build_command_srt_format(test_input_file, test_output_dir, subtitle_stream):
    """Test building command for SRT format."""
    extractor = SubtitleExtractor(test_input_file, test_output_dir)
    output_file = test_output_dir / "subtitle.srt"

    command = extractor._build_command(
        subtitle_stream=subtitle_stream,
        output_file=output_file,
        output_format="srt",
    )

    assert "-c:s" in command
    assert "srt" in command


def test_build_command_with_copy(test_input_file, test_output_dir):
    """Test building command with copy codec."""
    extractor = SubtitleExtractor(test_input_file, test_output_dir)
    output_file = test_output_dir / "subtitle.vtt"

    # Stream that's already WebVTT
    webvtt_stream = SubtitleStream(
        index=2,
        codec="webvtt",
        language="eng",
        title="English",
        forced=False,
    )

    command = extractor._build_command(
        subtitle_stream=webvtt_stream,
        output_file=output_file,
        output_format="webvtt",
    )

    assert "-c:s" in command
    assert "copy" in command


@pytest.mark.asyncio
async def test_extract_subtitle_success(test_input_file, test_output_dir, subtitle_stream):
    """Test successful subtitle extraction."""
    extractor = SubtitleExtractor(test_input_file, test_output_dir)

    # Mock AsyncFFmpegProcess
    with patch("hls_transcoder.transcoder.subtitle.AsyncFFmpegProcess") as mock_process_class:
        mock_process = AsyncMock()
        mock_process.run.return_value = ("", "")
        mock_process_class.return_value = mock_process

        # Create expected output file
        expected_output = test_output_dir / "subtitle_eng.vtt"
        expected_output.touch()

        result = await extractor.extract(
            subtitle_stream=subtitle_stream,
            output_format="webvtt",
        )

        assert result == expected_output
        assert result.exists()
        mock_process.run.assert_awaited_once()


@pytest.mark.asyncio
async def test_extract_forced_subtitle(test_input_file, test_output_dir, forced_subtitle_stream):
    """Test extracting forced subtitle."""
    extractor = SubtitleExtractor(test_input_file, test_output_dir)

    with patch("hls_transcoder.transcoder.subtitle.AsyncFFmpegProcess") as mock_process_class:
        mock_process = AsyncMock()
        mock_process.run.return_value = ("", "")
        mock_process_class.return_value = mock_process

        # Create expected output file with forced suffix
        expected_output = test_output_dir / "subtitle_eng_forced.vtt"
        expected_output.touch()

        result = await extractor.extract(
            subtitle_stream=forced_subtitle_stream,
            output_format="webvtt",
        )

        assert result == expected_output
        assert "forced" in result.name


@pytest.mark.asyncio
async def test_extract_with_progress_callback(test_input_file, test_output_dir, subtitle_stream):
    """Test extraction with progress callback."""
    extractor = SubtitleExtractor(test_input_file, test_output_dir)
    progress_values = []

    def progress_callback(current: float, total: Optional[float] = None):
        progress_values.append(current)

    with patch("hls_transcoder.transcoder.subtitle.AsyncFFmpegProcess") as mock_process_class:
        mock_process = AsyncMock()
        mock_process.run.return_value = ("", "")
        mock_process_class.return_value = mock_process

        # Create output file
        expected_output = test_output_dir / "subtitle_eng.vtt"
        expected_output.touch()

        await extractor.extract(
            subtitle_stream=subtitle_stream,
            progress_callback=progress_callback,
        )

        # Verify progress callback was passed to AsyncFFmpegProcess
        call_args = mock_process_class.call_args
        assert call_args is not None
        assert "progress_callback" in call_args.kwargs


@pytest.mark.asyncio
async def test_extract_with_timeout(test_input_file, test_output_dir, subtitle_stream):
    """Test extraction with custom timeout."""
    extractor = SubtitleExtractor(test_input_file, test_output_dir)

    with patch("hls_transcoder.transcoder.subtitle.AsyncFFmpegProcess") as mock_process_class:
        mock_process = AsyncMock()
        mock_process.run.return_value = ("", "")
        mock_process_class.return_value = mock_process

        # Create output file
        expected_output = test_output_dir / "subtitle_eng.vtt"
        expected_output.touch()

        await extractor.extract(
            subtitle_stream=subtitle_stream,
            timeout=120.0,
        )

        # Verify timeout was passed to AsyncFFmpegProcess
        call_args = mock_process_class.call_args
        assert call_args is not None
        assert call_args.kwargs["timeout"] == 120.0


@pytest.mark.asyncio
async def test_extract_ffmpeg_error(test_input_file, test_output_dir, subtitle_stream):
    """Test handling FFmpeg errors during extraction."""
    extractor = SubtitleExtractor(test_input_file, test_output_dir)

    with patch("hls_transcoder.transcoder.subtitle.AsyncFFmpegProcess") as mock_process_class:
        mock_process = AsyncMock()
        mock_process.run.side_effect = FFmpegError("FFmpeg failed", command=[], stderr="Error")
        mock_process_class.return_value = mock_process

        with pytest.raises(TranscodingError, match="FFmpeg subtitle extraction failed"):
            await extractor.extract(
                subtitle_stream=subtitle_stream,
            )


@pytest.mark.asyncio
async def test_extract_timeout_error(test_input_file, test_output_dir, subtitle_stream):
    """Test handling timeout during extraction."""
    extractor = SubtitleExtractor(test_input_file, test_output_dir)

    with patch("hls_transcoder.transcoder.subtitle.AsyncFFmpegProcess") as mock_process_class:
        mock_process = AsyncMock()
        mock_process.run.side_effect = asyncio.TimeoutError()
        mock_process_class.return_value = mock_process

        with pytest.raises(TranscodingError, match="Subtitle extraction timed out"):
            await extractor.extract(
                subtitle_stream=subtitle_stream,
                timeout=60.0,
            )


@pytest.mark.asyncio
async def test_extract_output_not_created(test_input_file, test_output_dir, subtitle_stream):
    """Test error when output file is not created."""
    extractor = SubtitleExtractor(test_input_file, test_output_dir)

    with patch("hls_transcoder.transcoder.subtitle.AsyncFFmpegProcess") as mock_process_class:
        mock_process = AsyncMock()
        mock_process.run.return_value = ("", "")
        mock_process_class.return_value = mock_process

        # Don't create output file - simulating failure

        with pytest.raises(TranscodingError, match="output file not created"):
            await extractor.extract(
                subtitle_stream=subtitle_stream,
            )


@pytest.mark.asyncio
async def test_extract_unknown_language(test_input_file, test_output_dir):
    """Test extraction with unknown language."""
    extractor = SubtitleExtractor(test_input_file, test_output_dir)

    # Subtitle stream with "und" (undefined) language
    stream_no_lang = SubtitleStream(
        index=2,
        codec="subrip",
        language="und",
        title="Unknown",
        forced=False,
    )

    with patch("hls_transcoder.transcoder.subtitle.AsyncFFmpegProcess") as mock_process_class:
        mock_process = AsyncMock()
        mock_process.run.return_value = ("", "")
        mock_process_class.return_value = mock_process

        # Create output file with "und" for undefined language
        expected_output = test_output_dir / "subtitle_und.vtt"
        expected_output.touch()

        result = await extractor.extract(
            subtitle_stream=stream_no_lang,
        )

        assert result == expected_output
        assert "und" in result.name


# === Multi-track Extraction Tests ===


@pytest.mark.asyncio
async def test_extract_all_tracks_success(test_input_file, test_output_dir, multi_subtitle_streams):
    """Test extracting multiple subtitle tracks."""
    extractor = SubtitleExtractor(test_input_file, test_output_dir)

    with patch("hls_transcoder.transcoder.subtitle.AsyncFFmpegProcess") as mock_process_class:
        mock_process = AsyncMock()
        mock_process.run.return_value = ("", "")
        mock_process_class.return_value = mock_process

        # Create expected output files
        expected_files = [
            test_output_dir / "subtitle_eng.vtt",
            test_output_dir / "subtitle_fra.vtt",
            test_output_dir / "subtitle_spa.vtt",
        ]
        for file in expected_files:
            file.touch()

        results = await extractor.extract_all_tracks(
            subtitle_streams=multi_subtitle_streams,
        )

        assert len(results) == 3
        assert all(isinstance(path, Path) for path in results)
        assert all(path.exists() for path in results)


@pytest.mark.asyncio
async def test_extract_all_tracks_with_progress(
    test_input_file, test_output_dir, multi_subtitle_streams
):
    """Test multi-track extraction with progress callback."""
    extractor = SubtitleExtractor(test_input_file, test_output_dir)
    progress_updates = []

    def progress_callback(completed: int, total: int):
        progress_updates.append((completed, total))

    with patch("hls_transcoder.transcoder.subtitle.AsyncFFmpegProcess") as mock_process_class:
        mock_process = AsyncMock()
        mock_process.run.return_value = ("", "")
        mock_process_class.return_value = mock_process

        # Create output files
        for stream in multi_subtitle_streams:
            output_file = test_output_dir / f"subtitle_{stream.language}.vtt"
            output_file.touch()

        await extractor.extract_all_tracks(
            subtitle_streams=multi_subtitle_streams,
            progress_callback=progress_callback,
        )

        assert len(progress_updates) == 3
        assert progress_updates[-1] == (3, 3)  # Final update


@pytest.mark.asyncio
async def test_extract_all_tracks_empty_list(test_input_file, test_output_dir):
    """Test extract_all_tracks with empty list."""
    extractor = SubtitleExtractor(test_input_file, test_output_dir)

    results = await extractor.extract_all_tracks(
        subtitle_streams=[],
    )

    assert results == []


@pytest.mark.asyncio
async def test_extract_all_tracks_concurrent_limit(
    test_input_file, test_output_dir, multi_subtitle_streams
):
    """Test concurrent extraction limit."""
    extractor = SubtitleExtractor(test_input_file, test_output_dir)

    with patch("hls_transcoder.transcoder.subtitle.AsyncFFmpegProcess") as mock_process_class:
        mock_process = AsyncMock()
        mock_process.run.return_value = ("", "")
        mock_process_class.return_value = mock_process

        # Create output files
        for stream in multi_subtitle_streams:
            output_file = test_output_dir / f"subtitle_{stream.language}.vtt"
            output_file.touch()

        await extractor.extract_all_tracks(
            subtitle_streams=multi_subtitle_streams,
            max_concurrent=2,
        )

        # All should complete
        assert mock_process.run.call_count == 3


@pytest.mark.asyncio
async def test_extract_all_tracks_partial_failure(
    test_input_file, test_output_dir, multi_subtitle_streams
):
    """Test handling partial failures in multi-track extraction."""
    extractor = SubtitleExtractor(test_input_file, test_output_dir)

    call_count = 0

    def mock_run_side_effect():
        nonlocal call_count
        call_count += 1
        if call_count == 2:
            # Second extraction fails
            raise FFmpegError("Failed", command=[], stderr="Error")
        return ("", "")

    with patch("hls_transcoder.transcoder.subtitle.AsyncFFmpegProcess") as mock_process_class:
        mock_process = AsyncMock()
        mock_process.run.side_effect = mock_run_side_effect
        mock_process_class.return_value = mock_process

        # Create output files for successful extractions
        (test_output_dir / "subtitle_eng.vtt").touch()
        (test_output_dir / "subtitle_spa.vtt").touch()

        # Should succeed but with warning about partial failure
        results = await extractor.extract_all_tracks(
            subtitle_streams=multi_subtitle_streams,
        )

        assert len(results) == 2  # Only successful ones


@pytest.mark.asyncio
async def test_extract_all_tracks_all_failures(
    test_input_file, test_output_dir, multi_subtitle_streams
):
    """Test handling all failures in multi-track extraction."""
    extractor = SubtitleExtractor(test_input_file, test_output_dir)

    with patch("hls_transcoder.transcoder.subtitle.AsyncFFmpegProcess") as mock_process_class:
        mock_process = AsyncMock()
        mock_process.run.side_effect = FFmpegError("Failed", command=[], stderr="Error")
        mock_process_class.return_value = mock_process

        with pytest.raises(TranscodingError, match="All subtitle extractions failed"):
            await extractor.extract_all_tracks(
                subtitle_streams=multi_subtitle_streams,
            )


# === Convenience Function Tests ===


@pytest.mark.asyncio
async def test_extract_all_subtitles_function(
    test_input_file, test_output_dir, multi_subtitle_streams
):
    """Test convenience function for extracting all subtitles."""
    with patch("hls_transcoder.transcoder.subtitle.AsyncFFmpegProcess") as mock_process_class:
        mock_process = AsyncMock()
        mock_process.run.return_value = ("", "")
        mock_process_class.return_value = mock_process

        # Create output directory and files
        test_output_dir.mkdir(parents=True, exist_ok=True)
        for stream in multi_subtitle_streams:
            output_file = test_output_dir / f"subtitle_{stream.language}.vtt"
            output_file.touch()

        results = await extract_all_subtitles(
            input_file=test_input_file,
            subtitle_streams=multi_subtitle_streams,
            output_dir=test_output_dir,
        )

        assert len(results) == 3
        assert all(isinstance(path, Path) for path in results)


@pytest.mark.asyncio
async def test_extract_all_subtitles_with_srt_format(
    test_input_file, test_output_dir, multi_subtitle_streams
):
    """Test convenience function with SRT format."""
    with patch("hls_transcoder.transcoder.subtitle.AsyncFFmpegProcess") as mock_process_class:
        mock_process = AsyncMock()
        mock_process.run.return_value = ("", "")
        mock_process_class.return_value = mock_process

        # Create output directory and files with .srt extension
        test_output_dir.mkdir(parents=True, exist_ok=True)
        for stream in multi_subtitle_streams:
            output_file = test_output_dir / f"subtitle_{stream.language}.srt"
            output_file.touch()

        results = await extract_all_subtitles(
            input_file=test_input_file,
            subtitle_streams=multi_subtitle_streams,
            output_dir=test_output_dir,
            output_format="srt",
        )

        assert len(results) == 3
        assert all(path.suffix == ".srt" for path in results)


@pytest.mark.asyncio
async def test_extract_all_subtitles_with_progress(
    test_input_file, test_output_dir, multi_subtitle_streams
):
    """Test convenience function with progress callback."""
    progress_updates = []

    def progress_callback(completed: int, total: int):
        progress_updates.append((completed, total))

    with patch("hls_transcoder.transcoder.subtitle.AsyncFFmpegProcess") as mock_process_class:
        mock_process = AsyncMock()
        mock_process.run.return_value = ("", "")
        mock_process_class.return_value = mock_process

        # Create output directory and files
        test_output_dir.mkdir(parents=True, exist_ok=True)
        for stream in multi_subtitle_streams:
            output_file = test_output_dir / f"subtitle_{stream.language}.vtt"
            output_file.touch()

        await extract_all_subtitles(
            input_file=test_input_file,
            subtitle_streams=multi_subtitle_streams,
            output_dir=test_output_dir,
            progress_callback=progress_callback,
        )

        assert len(progress_updates) == 3
