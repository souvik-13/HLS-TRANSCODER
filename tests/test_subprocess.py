"""
Tests for async subprocess wrapper.
"""

import asyncio
from pathlib import Path
from typing import Optional
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from hls_transcoder.executor import AsyncFFmpegProcess
from hls_transcoder.executor.subprocess import (
    FFmpegCommandBuilder,
    build_simple_transcode_command,
    run_ffmpeg_async,
    run_ffprobe_async,
)
from hls_transcoder.utils import FFmpegError, ProcessTimeoutError


@pytest.fixture
def sample_command():
    """Sample FFmpeg command for testing."""
    return [
        "ffmpeg",
        "-i",
        "input.mp4",
        "-c:v",
        "libx264",
        "-c:a",
        "aac",
        "output.mp4",
    ]


@pytest.fixture
def sample_stderr():
    """Sample FFmpeg stderr output."""
    return """
ffmpeg version 6.0 Copyright (c) 2000-2023 the FFmpeg developers
  Duration: 00:02:30.50, start: 0.000000, bitrate: 5000 kb/s
    Stream #0:0(und): Video: h264, yuv420p, 1920x1080, 24 fps
    Stream #0:1(und): Audio: aac, 48000 Hz, stereo, fltp, 128 kb/s
frame=  150 fps= 30 q=-1.0 Lsize=    1024kB time=00:00:05.00 bitrate=1677.7kbits/s speed=1.0x
frame=  300 fps= 30 q=-1.0 Lsize=    2048kB time=00:00:10.00 bitrate=1677.7kbits/s speed=1.0x
frame=  450 fps= 30 q=-1.0 Lsize=    3072kB time=00:00:15.00 bitrate=1677.7kbits/s speed=1.0x
video:3000kB audio:200kB subtitle:0kB other streams:0kB global headers:0kB muxing overhead: 0.5%
""".strip()


class TestAsyncFFmpegProcess:
    """Test AsyncFFmpegProcess class."""

    def test_initialization(self, sample_command):
        """Test process initialization."""
        process = AsyncFFmpegProcess(sample_command)
        assert process.command == sample_command
        assert process.timeout is None
        assert process.progress_callback is None
        assert not process.is_running
        assert process.returncode is None

    def test_initialization_with_options(self, sample_command):
        """Test initialization with timeout and callback."""
        callback = MagicMock()
        process = AsyncFFmpegProcess(
            sample_command, timeout=30.0, progress_callback=callback
        )
        assert process.timeout == 30.0
        assert process.progress_callback == callback

    @pytest.mark.asyncio
    async def test_run_success(self, sample_command, sample_stderr):
        """Test successful command execution."""
        # Mock subprocess
        mock_process = AsyncMock()
        mock_process.returncode = 0
        mock_process.communicate = AsyncMock(
            return_value=(b"output", sample_stderr.encode())
        )
        mock_process.stderr = AsyncMock()
        mock_process.stderr.readline = AsyncMock(
            side_effect=[
                line.encode() + b"\n"
                for line in sample_stderr.split("\n")
            ]
            + [b""]
        )

        with patch(
            "asyncio.create_subprocess_exec", return_value=mock_process
        ):
            process = AsyncFFmpegProcess(sample_command)
            stdout, stderr = await process.run()

            assert stdout == "output"
            assert "Duration: 00:02:30.50" in stderr
            assert process.returncode == 0

    @pytest.mark.asyncio
    async def test_run_failure(self, sample_command):
        """Test command execution failure."""
        # Mock subprocess with failure
        mock_process = AsyncMock()
        mock_process.returncode = 1
        mock_process.communicate = AsyncMock(
            return_value=(b"", b"Error: Invalid data found")
        )
        mock_process.stderr = AsyncMock()
        mock_process.stderr.readline = AsyncMock(
            side_effect=[b"Error: Invalid data found\n", b""]
        )

        with patch(
            "asyncio.create_subprocess_exec", return_value=mock_process
        ):
            process = AsyncFFmpegProcess(sample_command)

            with pytest.raises(FFmpegError, match="FFmpeg failed"):
                await process.run()

    @pytest.mark.asyncio
    async def test_run_with_timeout(self, sample_command):
        """Test command execution with timeout."""
        # Mock subprocess that takes too long
        mock_process = AsyncMock()
        mock_process.returncode = None
        mock_process.communicate = AsyncMock(
            side_effect=asyncio.TimeoutError()
        )
        mock_process.stderr = AsyncMock()
        mock_process.stderr.readline = AsyncMock(return_value=b"")

        with patch(
            "asyncio.create_subprocess_exec", return_value=mock_process
        ):
            process = AsyncFFmpegProcess(sample_command, timeout=0.1)

            with pytest.raises(ProcessTimeoutError, match="exceeded timeout"):
                await process.run()

    @pytest.mark.asyncio
    async def test_progress_callback(self, sample_command, sample_stderr):
        """Test progress callback invocation."""
        progress_values = []

        def progress_callback(current: float, total: Optional[float] = None):
            progress_values.append(current)

        # Mock subprocess
        mock_process = AsyncMock()
        mock_process.returncode = 0
        mock_process.communicate = AsyncMock(
            return_value=(b"", sample_stderr.encode())
        )
        mock_process.stderr = AsyncMock()
        mock_process.stderr.readline = AsyncMock(
            side_effect=[
                line.encode() + b"\n"
                for line in sample_stderr.split("\n")
            ]
            + [b""]
        )

        with patch(
            "asyncio.create_subprocess_exec", return_value=mock_process
        ):
            process = AsyncFFmpegProcess(
                sample_command, progress_callback=progress_callback
            )
            await process.run()

            # Should have received progress updates
            assert len(progress_values) > 0
            # Progress should be between 0 and 1
            assert all(0.0 <= p <= 1.0 for p in progress_values)

    @pytest.mark.asyncio
    async def test_terminate(self, sample_command):
        """Test process termination."""
        # Mock subprocess
        mock_process = AsyncMock()
        mock_process.returncode = None
        mock_process.terminate = MagicMock()
        mock_process.wait = AsyncMock()

        process = AsyncFFmpegProcess(sample_command)
        process._process = mock_process

        await process.terminate()

        mock_process.terminate.assert_called_once()
        mock_process.wait.assert_called_once()

    @pytest.mark.asyncio
    async def test_terminate_force_kill(self, sample_command):
        """Test forced process termination."""
        # Mock subprocess that doesn't terminate gracefully
        mock_process = AsyncMock()
        mock_process.returncode = None
        mock_process.terminate = MagicMock()
        mock_process.wait = AsyncMock(side_effect=asyncio.TimeoutError())
        mock_process.kill = MagicMock()

        # Second wait() call should succeed
        async def wait_side_effect():
            if mock_process.wait.call_count == 1:
                raise asyncio.TimeoutError()
            return None

        mock_process.wait = AsyncMock(side_effect=wait_side_effect)

        process = AsyncFFmpegProcess(sample_command)
        process._process = mock_process

        await process.terminate()

        mock_process.terminate.assert_called_once()
        mock_process.kill.assert_called_once()

    def test_extract_error_message(self, sample_command):
        """Test error message extraction."""
        process = AsyncFFmpegProcess(sample_command)

        # Test with common error pattern
        stderr = "Some info\nError while opening file\nMore details\n"
        msg = process._extract_error_message(stderr)
        assert "Error while opening" in msg

        # Test with no pattern match
        stderr = "Line 1\nLine 2\nLine 3\nLine 4\n"
        msg = process._extract_error_message(stderr)
        assert "Line 2" in msg or "Line 3" in msg or "Line 4" in msg


class TestConvenienceFunctions:
    """Test convenience functions."""

    @pytest.mark.asyncio
    async def test_run_ffmpeg_async(self, sample_command):
        """Test run_ffmpeg_async function."""
        # Mock subprocess
        mock_process = AsyncMock()
        mock_process.returncode = 0
        mock_process.communicate = AsyncMock(return_value=(b"out", b"err"))
        mock_process.stderr = AsyncMock()
        mock_process.stderr.readline = AsyncMock(return_value=b"")

        with patch(
            "asyncio.create_subprocess_exec", return_value=mock_process
        ):
            stdout, stderr = await run_ffmpeg_async(sample_command)
            assert stdout == "out"
            assert stderr == ""

    @pytest.mark.asyncio
    async def test_run_ffprobe_async(self, tmp_path):
        """Test run_ffprobe_async function."""
        # Create test file
        test_file = tmp_path / "test.mp4"
        test_file.write_text("dummy")

        # Mock subprocess
        mock_process = AsyncMock()
        mock_process.returncode = 0
        mock_process.communicate = AsyncMock(
            return_value=(b'{"format": {}}', b"")
        )
        mock_process.stderr = AsyncMock()
        mock_process.stderr.readline = AsyncMock(return_value=b"")

        with patch(
            "asyncio.create_subprocess_exec", return_value=mock_process
        ):
            output = await run_ffprobe_async(test_file)
            assert '{"format": {}}' in output


class TestFFmpegCommandBuilder:
    """Test FFmpegCommandBuilder class."""

    def test_basic_command(self):
        """Test basic command building."""
        builder = FFmpegCommandBuilder()
        command = builder.build()

        assert command[0] == "ffmpeg"
        assert "-hide_banner" in command

    def test_global_option(self):
        """Test adding global options."""
        builder = FFmpegCommandBuilder()
        builder.global_option("-y")
        builder.global_option("-loglevel", "error")

        command = builder.build()
        assert "-y" in command
        assert "-loglevel" in command
        assert "error" in command

    def test_input_file(self):
        """Test adding input file."""
        builder = FFmpegCommandBuilder()
        builder.input(Path("input.mp4"))

        command = builder.build()
        assert "-i" in command
        assert "input.mp4" in command

    def test_input_with_options(self):
        """Test adding input with options."""
        builder = FFmpegCommandBuilder()
        builder.input(Path("input.mp4"), options={"hwaccel": "cuda"})

        command = builder.build()
        assert "-hwaccel" in command
        assert "cuda" in command
        assert "-i" in command
        assert "input.mp4" in command

    def test_output_file(self):
        """Test adding output file."""
        builder = FFmpegCommandBuilder()
        builder.input(Path("input.mp4"))
        builder.output(Path("output.mp4"))

        command = builder.build()
        assert "output.mp4" in command

    def test_output_with_options(self):
        """Test adding output with options."""
        builder = FFmpegCommandBuilder()
        builder.input(Path("input.mp4"))
        builder.output(
            Path("output.mp4"),
            options={"c:v": "libx264", "c:a": "aac", "b:v": "5M"},
        )

        command = builder.build()
        assert "-c:v" in command
        assert "libx264" in command
        assert "-c:a" in command
        assert "aac" in command
        assert "-b:v" in command
        assert "5M" in command

    def test_complete_command(self):
        """Test building complete command."""
        builder = FFmpegCommandBuilder()
        builder.global_option("-y")
        builder.input(Path("input.mp4"), options={"hwaccel": "cuda"})
        builder.output(
            Path("output.mp4"),
            options={"c:v": "h264_nvenc", "c:a": "copy"},
        )

        command = builder.build()
        assert command[0] == "ffmpeg"
        assert "-y" in command
        assert "-hwaccel" in command
        assert "-i" in command
        assert "input.mp4" in command
        assert "-c:v" in command
        assert "h264_nvenc" in command
        assert "output.mp4" in command

    def test_method_chaining(self):
        """Test method chaining."""
        command = (
            FFmpegCommandBuilder()
            .global_option("-y")
            .input(Path("input.mp4"))
            .output(Path("output.mp4"), options={"c:v": "copy"})
            .build()
        )

        assert "ffmpeg" in command
        assert "-y" in command
        assert "input.mp4" in command
        assert "output.mp4" in command


class TestSimpleTranscodeCommand:
    """Test build_simple_transcode_command function."""

    def test_basic_transcode(self):
        """Test basic transcode command."""
        command = build_simple_transcode_command(
            input_file=Path("input.mp4"),
            output_file=Path("output.mp4"),
            video_codec="libx264",
            audio_codec="aac",
        )

        assert "ffmpeg" in command
        assert "-y" in command
        assert "input.mp4" in command
        assert "output.mp4" in command
        assert "-c:v" in command
        assert "libx264" in command
        assert "-c:a" in command
        assert "aac" in command

    def test_transcode_with_bitrates(self):
        """Test transcode with bitrates."""
        command = build_simple_transcode_command(
            input_file=Path("input.mp4"),
            output_file=Path("output.mp4"),
            video_codec="h264_nvenc",
            audio_codec="aac",
            video_bitrate="5M",
            audio_bitrate="128k",
        )

        assert "-b:v" in command
        assert "5M" in command
        assert "-b:a" in command
        assert "128k" in command

    def test_transcode_copy_audio(self):
        """Test transcode with audio copy."""
        command = build_simple_transcode_command(
            input_file=Path("input.mp4"),
            output_file=Path("output.mp4"),
            video_codec="libx265",
            audio_codec="copy",
        )

        assert "-c:a" in command
        assert "copy" in command
