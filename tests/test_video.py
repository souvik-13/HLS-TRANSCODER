"""
Tests for video transcoding functionality.
"""

import asyncio
from pathlib import Path
from typing import Optional
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from hls_transcoder.hardware import HardwareInfo
from hls_transcoder.hardware.detector import EncoderInfo, HardwareType
from hls_transcoder.models import VideoStream
from hls_transcoder.transcoder import (
    QUALITY_PRESETS,
    TranscodingOptions,
    VideoQuality,
    VideoTranscoder,
    transcode_all_qualities,
)
from hls_transcoder.utils import FFmpegError, TranscodingError


@pytest.fixture
def video_stream():
    """Create test video stream."""
    return VideoStream(
        index=0,
        codec="h264",
        codec_long="H.264 / AVC",
        profile="High",
        width=1920,
        height=1080,
        fps=30.0,
        bitrate=5000000,
        duration=120.0,
        pix_fmt="yuv420p",
    )


@pytest.fixture
def hardware_info_nvidia():
    """Create NVIDIA hardware info."""
    encoder = EncoderInfo(
        name="h264_nvenc",
        hardware_type=HardwareType.NVIDIA,
        display_name="NVIDIA NVENC",
        available=True,
        tested=True,
    )
    return HardwareInfo(
        detected_type=HardwareType.NVIDIA,
        available_encoders=[encoder],
        selected_encoder=encoder,
    )


@pytest.fixture
def hardware_info_software():
    """Create software-only hardware info."""
    encoder = EncoderInfo(
        name="libx264",
        hardware_type=HardwareType.SOFTWARE,
        display_name="Software x264",
        available=True,
        tested=True,
    )
    return HardwareInfo(
        detected_type=HardwareType.SOFTWARE,
        available_encoders=[encoder],
        selected_encoder=encoder,
    )


@pytest.fixture
def transcoder(tmp_path, video_stream, hardware_info_nvidia):
    """Create video transcoder instance."""
    input_file = tmp_path / "input.mp4"
    input_file.touch()
    output_dir = tmp_path / "output"

    return VideoTranscoder(
        input_file=input_file,
        output_dir=output_dir,
        hardware_info=hardware_info_nvidia,
        video_stream=video_stream,
    )


class TestVideoQuality:
    """Tests for VideoQuality dataclass."""

    def test_quality_initialization(self):
        """Test quality preset initialization."""
        quality = VideoQuality("1080p", 1080, 5000, 7500, 10000)

        assert quality.name == "1080p"
        assert quality.height == 1080
        assert quality.bitrate == 5000
        assert quality.maxrate == 7500
        assert quality.bufsize == 10000

    def test_width_calculation(self):
        """Test width calculation maintains 16:9 aspect ratio."""
        quality = VideoQuality("1080p", 1080, 5000, 7500, 10000)
        assert quality.width == 1920

        quality = VideoQuality("720p", 720, 3000, 4500, 6000)
        assert quality.width == 1280

    def test_resolution_string(self):
        """Test resolution string formatting."""
        quality = VideoQuality("1080p", 1080, 5000, 7500, 10000)
        assert quality.resolution == "1920x1080"


class TestQualityPresets:
    """Tests for quality presets."""

    def test_all_presets_exist(self):
        """Test all expected presets are defined."""
        expected = ["2160p", "1440p", "1080p", "720p", "480p", "360p"]

        for name in expected:
            assert name in QUALITY_PRESETS
            preset = QUALITY_PRESETS[name]
            assert preset.name == name

    def test_preset_ordering(self):
        """Test presets are ordered by descending height."""
        presets = list(QUALITY_PRESETS.values())
        heights = [p.height for p in presets]

        assert heights == sorted(heights, reverse=True)

    def test_preset_bitrates(self):
        """Test preset bitrates are reasonable."""
        for preset in QUALITY_PRESETS.values():
            assert preset.bitrate > 0
            assert preset.maxrate > preset.bitrate
            assert preset.bufsize > preset.maxrate


class TestVideoTranscoder:
    """Tests for VideoTranscoder class."""

    def test_initialization(self, tmp_path, video_stream, hardware_info_nvidia):
        """Test transcoder initialization."""
        input_file = tmp_path / "input.mp4"
        input_file.touch()
        output_dir = tmp_path / "output"

        transcoder = VideoTranscoder(
            input_file=input_file,
            output_dir=output_dir,
            hardware_info=hardware_info_nvidia,
            video_stream=video_stream,
        )

        assert transcoder.input_file == input_file
        assert transcoder.output_dir == output_dir
        assert transcoder.hardware_info == hardware_info_nvidia
        assert transcoder.video_stream == video_stream
        assert output_dir.exists()

    @pytest.mark.asyncio
    async def test_transcode_success(self, transcoder):
        """Test successful transcoding."""
        quality = QUALITY_PRESETS["720p"]

        with patch("hls_transcoder.transcoder.video.AsyncFFmpegProcess") as mock_process_class:
            # Mock process
            mock_process = AsyncMock()
            mock_process.run.return_value = ("", "")
            mock_process_class.return_value = mock_process

            # Create output file
            output_path = transcoder.output_dir / "720p.m3u8"
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.touch()

            # Transcode
            result = await transcoder.transcode(quality)

            assert result == output_path
            mock_process.run.assert_called_once()

    @pytest.mark.asyncio
    async def test_transcode_with_progress_callback(self, transcoder):
        """Test transcoding with progress callback."""
        quality = QUALITY_PRESETS["720p"]
        progress_values = []

        def progress_callback(current: float, total: Optional[float] = None):
            progress_values.append(current)

        with patch("hls_transcoder.transcoder.video.AsyncFFmpegProcess") as mock_process_class:
            mock_process = AsyncMock()
            mock_process.run.return_value = ("", "")
            mock_process_class.return_value = mock_process

            output_path = transcoder.output_dir / "720p.m3u8"
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.touch()

            await transcoder.transcode(quality, progress_callback=progress_callback)

            # Verify progress callback was passed to process
            call_kwargs = mock_process_class.call_args[1]
            assert "progress_callback" in call_kwargs

    @pytest.mark.asyncio
    async def test_transcode_failure(self, transcoder):
        """Test transcoding failure handling."""
        quality = QUALITY_PRESETS["720p"]

        with patch("hls_transcoder.transcoder.video.AsyncFFmpegProcess") as mock_process_class:
            mock_process = AsyncMock()
            mock_process.run.side_effect = FFmpegError(
                "FFmpeg failed", command=["ffmpeg"], stderr="error"
            )
            mock_process_class.return_value = mock_process

            with pytest.raises(TranscodingError) as exc_info:
                await transcoder.transcode(quality)

            assert "Failed to transcode" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_transcode_output_not_created(self, transcoder):
        """Test error when output file not created."""
        quality = QUALITY_PRESETS["720p"]

        with patch("hls_transcoder.transcoder.video.AsyncFFmpegProcess") as mock_process_class:
            mock_process = AsyncMock()
            mock_process.run.return_value = ("", "")
            mock_process_class.return_value = mock_process

            # Don't create output file

            with pytest.raises(TranscodingError) as exc_info:
                await transcoder.transcode(quality)

            assert "output not found" in str(exc_info.value)

    def test_calculate_quality_ladder_1080p_source(self, transcoder):
        """Test quality ladder for 1080p source."""
        ladder = transcoder.calculate_quality_ladder()

        # Should include 1080p and below
        heights = [q.height for q in ladder]
        assert 1080 in heights
        assert 720 in heights
        assert 480 in heights
        assert 360 in heights
        assert 1440 not in heights  # Above source
        assert 2160 not in heights  # Above source

    def test_calculate_quality_ladder_720p_source(
        self, video_stream, tmp_path, hardware_info_nvidia
    ):
        """Test quality ladder for 720p source."""
        video_stream.height = 720
        video_stream.width = 1280

        input_file = tmp_path / "input.mp4"
        input_file.touch()

        transcoder = VideoTranscoder(
            input_file=input_file,
            output_dir=tmp_path / "output",
            hardware_info=hardware_info_nvidia,
            video_stream=video_stream,
        )

        ladder = transcoder.calculate_quality_ladder()
        heights = [q.height for q in ladder]

        assert 720 in heights
        assert 480 in heights
        assert 360 in heights
        assert 1080 not in heights  # Above source

    def test_calculate_quality_ladder_with_filter(self, transcoder):
        """Test quality ladder with specific qualities."""
        ladder = transcoder.calculate_quality_ladder(max_qualities=["1080p", "720p"])

        assert len(ladder) == 2
        assert ladder[0].name == "1080p"
        assert ladder[1].name == "720p"

    def test_calculate_quality_ladder_ordering(self, transcoder):
        """Test quality ladder is sorted by descending height."""
        ladder = transcoder.calculate_quality_ladder()

        # Check ordering
        for i in range(len(ladder) - 1):
            assert ladder[i].height > ladder[i + 1].height

    def test_calculate_quality_ladder_original_only(self, transcoder):
        """Test quality ladder with original_only flag."""
        ladder = transcoder.calculate_quality_ladder(original_only=True)

        # Should return single quality matching source
        assert len(ladder) == 1
        quality = ladder[0]
        assert quality.name == "original"
        assert quality.height == transcoder.video_stream.height
        assert quality.width == transcoder.video_stream.width
        assert quality.custom_width == transcoder.video_stream.width

    def test_calculate_quality_ladder_original_only_non_standard_aspect(
        self, video_stream, tmp_path, hardware_info_nvidia
    ):
        """Test original_only with non-standard aspect ratio."""
        # Ultra-wide source: 2560x1080
        video_stream.width = 2560
        video_stream.height = 1080

        input_file = tmp_path / "input.mp4"
        input_file.touch()

        transcoder = VideoTranscoder(
            input_file=input_file,
            output_dir=tmp_path / "output",
            hardware_info=hardware_info_nvidia,
            video_stream=video_stream,
        )

        ladder = transcoder.calculate_quality_ladder(original_only=True)

        assert len(ladder) == 1
        quality = ladder[0]
        assert quality.name == "original"
        assert quality.height == 1080
        assert quality.width == 2560  # Maintains exact source resolution
        assert quality.custom_width == 2560

    def test_video_quality_custom_width(self):
        """Test VideoQuality with custom width."""
        # Standard 16:9
        quality_169 = VideoQuality("720p", 720, 3000, 4500, 6000)
        assert quality_169.width == 1280  # Calculated from 16:9

        # Custom width (e.g., ultra-wide)
        quality_custom = VideoQuality("720p", 720, 3000, 4500, 6000, custom_width=2560)
        assert quality_custom.width == 2560  # Uses custom width
        assert quality_custom.resolution == "2560x720"


class TestCommandBuilding:
    """Tests for FFmpeg command building."""

    def test_build_command_nvenc(self, transcoder):
        """Test NVENC command building."""
        quality = QUALITY_PRESETS["720p"]
        options = TranscodingOptions(
            quality=quality,
            hardware_info=transcoder.hardware_info,
            video_stream=transcoder.video_stream,
            output_path=transcoder.output_dir / "720p.m3u8",
        )

        command = transcoder._build_command(
            options,
            transcoder.output_dir / "720p_%03d.ts",
        )

        assert "ffmpeg" in command
        assert "-i" in command
        assert str(transcoder.input_file) in command
        assert "h264_nvenc" in command
        assert "-hwaccel" in command
        assert "cuda" in command

    def test_build_command_software(self, tmp_path, video_stream, hardware_info_software):
        """Test software encoding command building."""
        input_file = tmp_path / "input.mp4"
        input_file.touch()

        transcoder = VideoTranscoder(
            input_file=input_file,
            output_dir=tmp_path / "output",
            hardware_info=hardware_info_software,
            video_stream=video_stream,
        )

        quality = QUALITY_PRESETS["720p"]
        options = TranscodingOptions(
            quality=quality,
            hardware_info=hardware_info_software,
            video_stream=video_stream,
            output_path=tmp_path / "output" / "720p.m3u8",
        )

        command = transcoder._build_command(
            options,
            tmp_path / "output" / "720p_%03d.ts",
        )

        assert "libx264" in command
        assert "-preset" in command

    def test_hls_options_in_command(self, transcoder):
        """Test HLS options are included in command."""
        quality = QUALITY_PRESETS["720p"]
        options = TranscodingOptions(
            quality=quality,
            hardware_info=transcoder.hardware_info,
            video_stream=transcoder.video_stream,
            output_path=transcoder.output_dir / "720p.m3u8",
        )

        command = transcoder._build_command(
            options,
            transcoder.output_dir / "720p_%03d.ts",
        )

        assert "-f" in command
        assert "hls" in command
        assert "-hls_time" in command
        assert "-hls_segment_filename" in command

    def test_video_options_include_bitrate(self, transcoder):
        """Test video options include bitrate settings."""
        quality = QUALITY_PRESETS["720p"]
        options = TranscodingOptions(
            quality=quality,
            hardware_info=transcoder.hardware_info,
            video_stream=transcoder.video_stream,
            output_path=transcoder.output_dir / "720p.m3u8",
        )

        command = transcoder._build_command(
            options,
            transcoder.output_dir / "720p_%03d.ts",
        )

        # Check bitrate options
        assert "-b:v" in command
        assert f"{quality.bitrate}k" in command
        assert "-maxrate:v" in command
        assert f"{quality.maxrate}k" in command


class TestHardwareEncoders:
    """Tests for hardware-specific encoders."""

    def test_nvenc_options(self, transcoder):
        """Test NVIDIA NVENC options."""
        quality = QUALITY_PRESETS["720p"]
        options = TranscodingOptions(
            quality=quality,
            hardware_info=transcoder.hardware_info,
            video_stream=transcoder.video_stream,
            output_path=transcoder.output_dir / "720p.m3u8",
        )

        video_opts = transcoder._get_nvenc_options(options)

        assert "h264_nvenc" in video_opts
        assert "-preset" in video_opts
        assert "p4" in video_opts
        assert "-rc:v" in video_opts
        assert "vbr" in video_opts

    def test_qsv_options(self, tmp_path, video_stream):
        """Test Intel QSV options."""
        encoder = EncoderInfo(
            name="h264_qsv",
            hardware_type=HardwareType.INTEL,
            display_name="Intel QSV",
            available=True,
            tested=True,
        )
        hardware_info = HardwareInfo(
            detected_type=HardwareType.INTEL,
            available_encoders=[encoder],
            selected_encoder=encoder,
        )

        input_file = tmp_path / "input.mp4"
        input_file.touch()

        transcoder = VideoTranscoder(
            input_file=input_file,
            output_dir=tmp_path / "output",
            hardware_info=hardware_info,
            video_stream=video_stream,
        )

        quality = QUALITY_PRESETS["720p"]
        options = TranscodingOptions(
            quality=quality,
            hardware_info=hardware_info,
            video_stream=video_stream,
            output_path=tmp_path / "output" / "720p.m3u8",
        )

        video_opts = transcoder._get_qsv_options(options)

        assert "h264_qsv" in video_opts
        # Check for scale_qsv in the vf filter string
        assert any("scale_qsv" in opt for opt in video_opts)

    def test_software_fallback(self, tmp_path, video_stream):
        """Test software encoding fallback."""
        hardware_info = HardwareInfo(
            detected_type=HardwareType.SOFTWARE,
            available_encoders=[],
            selected_encoder=None,
        )

        input_file = tmp_path / "input.mp4"
        input_file.touch()

        transcoder = VideoTranscoder(
            input_file=input_file,
            output_dir=tmp_path / "output",
            hardware_info=hardware_info,
            video_stream=video_stream,
        )

        quality = QUALITY_PRESETS["720p"]
        options = TranscodingOptions(
            quality=quality,
            hardware_info=hardware_info,
            video_stream=video_stream,
            output_path=tmp_path / "output" / "720p.m3u8",
        )

        video_opts = transcoder._get_video_options(options)

        assert "libx264" in video_opts


class TestParallelTranscoding:
    """Tests for parallel transcoding."""

    @pytest.mark.asyncio
    async def test_transcode_all_qualities(self, transcoder):
        """Test transcoding multiple qualities in parallel."""
        qualities = [QUALITY_PRESETS["1080p"], QUALITY_PRESETS["720p"]]

        with patch("hls_transcoder.transcoder.video.AsyncFFmpegProcess") as mock_process_class:
            mock_process = AsyncMock()
            mock_process.run.return_value = ("", "")
            mock_process_class.return_value = mock_process

            # Create output files
            for quality in qualities:
                output_path = transcoder.output_dir / f"{quality.name}.m3u8"
                output_path.parent.mkdir(parents=True, exist_ok=True)
                output_path.touch()

            results = await transcode_all_qualities(transcoder, qualities)

            assert len(results) == 2
            assert "1080p" in results
            assert "720p" in results

    @pytest.mark.asyncio
    async def test_transcode_all_qualities_with_progress(self, transcoder):
        """Test parallel transcoding with progress callback."""
        qualities = [QUALITY_PRESETS["720p"]]
        progress_updates = []

        def progress_callback(quality_name: str, progress: float):
            progress_updates.append((quality_name, progress))

        with patch("hls_transcoder.transcoder.video.AsyncFFmpegProcess") as mock_process_class:
            mock_process = AsyncMock()
            mock_process.run.return_value = ("", "")
            mock_process_class.return_value = mock_process

            output_path = transcoder.output_dir / "720p.m3u8"
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.touch()

            await transcode_all_qualities(
                transcoder,
                qualities,
                progress_callback=progress_callback,
            )

    @pytest.mark.asyncio
    async def test_transcode_all_qualities_with_failure(self, transcoder):
        """Test parallel transcoding with failure."""
        qualities = [QUALITY_PRESETS["1080p"], QUALITY_PRESETS["720p"]]

        with patch("hls_transcoder.transcoder.video.AsyncFFmpegProcess") as mock_process_class:
            mock_process = AsyncMock()
            mock_process.run.side_effect = FFmpegError("Failed", command=["ffmpeg"], stderr="error")
            mock_process_class.return_value = mock_process

            with pytest.raises(TranscodingError):
                await transcode_all_qualities(transcoder, qualities)

    @pytest.mark.asyncio
    async def test_concurrent_limit(self, transcoder):
        """Test concurrent transcoding limit."""
        qualities = [
            QUALITY_PRESETS["1080p"],
            QUALITY_PRESETS["720p"],
            QUALITY_PRESETS["480p"],
        ]

        with patch("hls_transcoder.transcoder.video.AsyncFFmpegProcess") as mock_process_class:
            mock_process = AsyncMock()
            mock_process.run.return_value = ("", "")
            mock_process_class.return_value = mock_process

            # Create output files
            for quality in qualities:
                output_path = transcoder.output_dir / f"{quality.name}.m3u8"
                output_path.parent.mkdir(parents=True, exist_ok=True)
                output_path.touch()

            results = await transcode_all_qualities(
                transcoder,
                qualities,
                max_concurrent=1,  # One at a time
            )

            assert len(results) == 3
