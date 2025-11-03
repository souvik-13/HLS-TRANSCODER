"""
Async subprocess wrapper for FFmpeg execution.

This module provides asynchronous process management for FFmpeg commands,
including progress tracking, timeout handling, and error recovery.
"""

import asyncio
import re
from pathlib import Path
from typing import AsyncIterator, Callable, Optional

from ..utils import FFmpegError, ProcessTimeoutError, get_logger

logger = get_logger(__name__)


class AsyncFFmpegProcess:
    """
    Async wrapper for FFmpeg subprocess execution.

    Provides non-blocking process execution with:
    - Real-time stderr streaming
    - Progress parsing and callbacks
    - Timeout handling
    - Proper cleanup on errors
    """

    # Regex patterns for parsing FFmpeg output
    DURATION_PATTERN = re.compile(r"Duration: (\d{2}):(\d{2}):(\d{2}\.\d{2})")
    PROGRESS_PATTERN = re.compile(r"time=(\d{2}):(\d{2}):(\d{2}\.\d{2})")
    FPS_PATTERN = re.compile(r"fps=\s*(\d+\.?\d*)")
    SPEED_PATTERN = re.compile(r"speed=\s*(\d+\.?\d*)x")

    def __init__(
        self,
        command: list[str],
        timeout: Optional[float] = None,
        progress_callback: Optional[Callable[[float, Optional[float]], None]] = None,
    ):
        """
        Initialize async FFmpeg process.

        Args:
            command: FFmpeg command as list of arguments
            timeout: Maximum execution time in seconds (None = no timeout)
            progress_callback: Callback function for progress updates (progress, speed)
                              - progress: float (0.0 to 1.0)
                              - speed: Optional[float] (fps or speed multiplier)
        """
        self.command = command
        self.timeout = timeout
        self.progress_callback = progress_callback
        self._process: Optional[asyncio.subprocess.Process] = None
        self._duration: Optional[float] = None
        self._stderr_lines: list[str] = []

    async def run(self) -> tuple[str, str]:
        """
        Run FFmpeg command and wait for completion.

        Returns:
            Tuple of (stdout, stderr) as strings

        Raises:
            FFmpegError: If process fails
            ProcessTimeoutError: If process exceeds timeout
        """
        logger.info(f"Running FFmpeg command: {' '.join(self.command[:3])}...")
        logger.debug(f"Full command: {' '.join(self.command)}")

        try:
            # Start process
            self._process = await asyncio.create_subprocess_exec(
                *self.command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            # Run with timeout if specified
            if self.timeout:
                stdout, stderr = await asyncio.wait_for(
                    self._communicate_with_progress(),
                    timeout=self.timeout,
                )
            else:
                stdout, stderr = await self._communicate_with_progress()

            # Check return code
            if self._process.returncode != 0:
                error_msg = self._extract_error_message(stderr)
                raise FFmpegError(
                    f"FFmpeg failed with code {self._process.returncode}: {error_msg}",
                    command=self.command,
                    stderr=stderr,
                )

            logger.info("FFmpeg command completed successfully")
            return stdout, stderr

        except asyncio.TimeoutError:
            logger.error(f"FFmpeg process exceeded timeout of {self.timeout}s")
            await self.terminate()
            raise ProcessTimeoutError(
                f"Process exceeded timeout of {self.timeout}s",
                timeout=self.timeout or 0.0,
            )

        except Exception as e:
            logger.error(f"FFmpeg process failed: {e}")
            await self.terminate()
            raise

    async def _communicate_with_progress(self) -> tuple[str, str]:
        """
        Communicate with process and track progress.

        Returns:
            Tuple of (stdout, stderr) as strings
        """
        if not self._process:
            raise RuntimeError("Process not started")

        # Read both stdout and stderr concurrently
        # We need to read them separately to avoid conflicts
        stdout_task = asyncio.create_task(self._read_stdout())
        stderr_task = asyncio.create_task(self._read_stderr())

        # Wait for both to complete
        stdout, stderr = await asyncio.gather(stdout_task, stderr_task)

        # Wait for process to finish
        await self._process.wait()

        return stdout, stderr

    async def _read_stdout(self) -> str:
        """
        Read stdout from process.

        Returns:
            Complete stdout output as string
        """
        if not self._process or not self._process.stdout:
            return ""

        stdout = await self._process.stdout.read()
        return stdout.decode() if stdout else ""

    async def _read_stderr(self) -> str:
        """
        Read and parse stderr for progress information.

        Returns:
            Complete stderr output as string
        """
        if not self._process or not self._process.stderr:
            return ""

        stderr_lines: list[str] = []

        async for line in self._stream_stderr():
            stderr_lines.append(line)

            # Parse duration on first encounter
            if self._duration is None:
                duration_match = self.DURATION_PATTERN.search(line)
                if duration_match:
                    h, m, s = map(float, duration_match.groups())
                    self._duration = h * 3600 + m * 60 + s
                    logger.debug(f"Detected duration: {self._duration}s")

            # Parse progress
            if self._duration and self.progress_callback:
                progress_match = self.PROGRESS_PATTERN.search(line)
                if progress_match:
                    h, m, s = map(float, progress_match.groups())
                    current_time = h * 3600 + m * 60 + s
                    progress = min(current_time / self._duration, 1.0)

                    # Parse speed (fps or speed multiplier)
                    speed: Optional[float] = None
                    fps_match = self.FPS_PATTERN.search(line)
                    speed_match = self.SPEED_PATTERN.search(line)

                    if fps_match:
                        speed = float(fps_match.group(1))
                    elif speed_match:
                        # Convert speed multiplier to approximate fps (assuming 30 fps base)
                        speed = float(speed_match.group(1)) * 30.0

                    try:
                        self.progress_callback(progress, speed)
                    except Exception as e:
                        logger.warning(f"Progress callback failed: {e}")

        self._stderr_lines = stderr_lines
        return "\n".join(stderr_lines)

    async def _stream_stderr(self) -> AsyncIterator[str]:
        """
        Stream stderr line by line.

        Yields:
            Individual lines from stderr
        """
        if not self._process or not self._process.stderr:
            return

        while True:
            line_bytes = await self._process.stderr.readline()
            if not line_bytes:
                break

            line = line_bytes.decode().strip()
            if line:
                yield line

    def _extract_error_message(self, stderr: str) -> str:
        """
        Extract meaningful error message from stderr.

        Args:
            stderr: Complete stderr output

        Returns:
            Extracted error message or truncated stderr
        """
        # Look for common error patterns
        error_patterns = [
            r"Error while (opening|decoding|encoding)",
            r"Invalid data found",
            r"No such file or directory",
            r"Permission denied",
            r"Unknown encoder",
            r"Codec .* is not supported",
            r"Invalid argument",
        ]

        for pattern in error_patterns:
            match = re.search(pattern, stderr, re.IGNORECASE)
            if match:
                # Get surrounding context
                lines = stderr.split("\n")
                for i, line in enumerate(lines):
                    if match.group() in line:
                        # Return this line and next 2 lines
                        context = lines[i : i + 3]
                        return " | ".join(context)

        # Return last 3 non-empty lines as fallback
        lines = [line for line in stderr.split("\n") if line.strip()]
        return " | ".join(lines[-3:]) if lines else "Unknown error"

    async def terminate(self) -> None:
        """
        Terminate the process gracefully.

        Sends SIGTERM, waits briefly, then sends SIGKILL if needed.
        """
        if not self._process:
            return

        try:
            if self._process.returncode is None:
                logger.info("Terminating FFmpeg process...")
                self._process.terminate()

                # Wait up to 5 seconds for graceful shutdown
                try:
                    await asyncio.wait_for(self._process.wait(), timeout=5.0)
                    logger.info("Process terminated gracefully")
                except asyncio.TimeoutError:
                    # Force kill if not terminated
                    logger.warning("Forcing process termination...")
                    self._process.kill()
                    await self._process.wait()
                    logger.info("Process killed")

        except Exception as e:
            logger.error(f"Error during process termination: {e}")

    @property
    def is_running(self) -> bool:
        """Check if process is currently running."""
        return self._process is not None and self._process.returncode is None

    @property
    def returncode(self) -> Optional[int]:
        """Get process return code."""
        return self._process.returncode if self._process else None

    @property
    def stderr_output(self) -> list[str]:
        """Get captured stderr lines."""
        return self._stderr_lines.copy()


async def run_ffmpeg_async(
    command: list[str],
    timeout: Optional[float] = None,
    progress_callback: Optional[Callable[[float, Optional[float]], None]] = None,
) -> tuple[str, str]:
    """
    Convenience function to run FFmpeg command asynchronously.

    Args:
        command: FFmpeg command as list of arguments
        timeout: Maximum execution time in seconds
        progress_callback: Callback for progress updates (progress, speed)
                          - progress: float (0.0 to 1.0)
                          - speed: Optional[float] (fps or speed multiplier)

    Returns:
        Tuple of (stdout, stderr)

    Raises:
        FFmpegError: If command fails
        ProcessTimeoutError: If command exceeds timeout
    """
    process = AsyncFFmpegProcess(command, timeout, progress_callback)
    return await process.run()


async def run_ffprobe_async(
    input_file: Path,
    additional_args: Optional[list[str]] = None,
) -> str:
    """
    Run FFprobe command asynchronously.

    Args:
        input_file: Path to media file
        additional_args: Additional FFprobe arguments

    Returns:
        FFprobe output as string

    Raises:
        FFmpegError: If FFprobe fails
    """
    command = ["ffprobe", "-v", "quiet"]

    if additional_args:
        command.extend(additional_args)

    command.append(str(input_file))

    process = AsyncFFmpegProcess(command)
    stdout, _ = await process.run()
    return stdout


class FFmpegCommandBuilder:
    """
    Builder for constructing FFmpeg commands.

    Provides a fluent interface for building complex FFmpeg commands.
    """

    def __init__(self):
        """Initialize command builder."""
        self._command = ["ffmpeg", "-hide_banner"]
        self._input_options: list[str] = []
        self._output_options: list[str] = []
        self._inputs: list[str] = []
        self._outputs: list[str] = []

    def global_option(self, option: str, value: Optional[str] = None) -> "FFmpegCommandBuilder":
        """
        Add global FFmpeg option.

        Args:
            option: Option name (e.g., "-y", "-loglevel")
            value: Option value (if applicable)

        Returns:
            Self for chaining
        """
        self._command.append(option)
        if value is not None:
            self._command.append(value)
        return self

    def input(
        self,
        file: Path,
        options: Optional[dict[str, str]] = None,
    ) -> "FFmpegCommandBuilder":
        """
        Add input file with options.

        Args:
            file: Input file path
            options: Input options as dict (e.g., {"hwaccel": "cuda"})

        Returns:
            Self for chaining
        """
        if options:
            for key, value in options.items():
                self._input_options.append(f"-{key}")
                self._input_options.append(value)

        self._inputs.append(str(file))
        return self

    def output(
        self,
        file: Path,
        options: Optional[dict[str, str]] = None,
    ) -> "FFmpegCommandBuilder":
        """
        Add output file with options.

        Args:
            file: Output file path
            options: Output options as dict

        Returns:
            Self for chaining
        """
        if options:
            for key, value in options.items():
                self._output_options.append(f"-{key}")
                if value:  # Skip empty values (for flags)
                    self._output_options.append(value)

        self._outputs.append(str(file))
        return self

    def build(self) -> list[str]:
        """
        Build final command list.

        Returns:
            Complete FFmpeg command as list
        """
        command = self._command.copy()

        # Add input options and files
        for i, input_file in enumerate(self._inputs):
            # Add options before each input
            if self._input_options:
                command.extend(self._input_options)
            command.extend(["-i", input_file])

        # Add output options and files
        if self._output_options:
            command.extend(self._output_options)

        for output_file in self._outputs:
            command.append(output_file)

        return command


def build_simple_transcode_command(
    input_file: Path,
    output_file: Path,
    video_codec: str,
    audio_codec: str,
    video_bitrate: Optional[str] = None,
    audio_bitrate: Optional[str] = None,
) -> list[str]:
    """
    Build simple transcode command.

    Args:
        input_file: Input file path
        output_file: Output file path
        video_codec: Video codec (e.g., "libx264", "h264_nvenc")
        audio_codec: Audio codec (e.g., "aac", "copy")
        video_bitrate: Video bitrate (e.g., "5M")
        audio_bitrate: Audio bitrate (e.g., "128k")

    Returns:
        FFmpeg command as list
    """
    builder = FFmpegCommandBuilder()
    builder.global_option("-y")  # Overwrite output
    builder.input(input_file)

    output_options = {
        "c:v": video_codec,
        "c:a": audio_codec,
    }

    if video_bitrate:
        output_options["b:v"] = video_bitrate

    if audio_bitrate:
        output_options["b:a"] = audio_bitrate

    builder.output(output_file, output_options)

    return builder.build()
