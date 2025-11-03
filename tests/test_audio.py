"""
Tests for audio extraction and transcoding.
"""

from pathlib import Path
from typing import Optional
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from hls_transcoder.models import AudioStream
from hls_transcoder.transcoder.audio import (
    AUDIO_QUALITY_PRESETS,
    AudioExtractor,
    AudioExtractionOptions,
    AudioQuality,
)
from hls_transcoder.utils import TranscodingError


@pytest.fixture
def audio_stream():
    """Create test audio stream."""
    return AudioStream(
        index=1,
        codec="aac",
        codec_long="AAC (Advanced Audio Coding)",
        profile="LC",
        language="eng",
        channels=2,
        sample_rate=48000,
        bitrate=128000,
        duration=120.0,
    )


@pytest.fixture
def audio_extractor(tmp_path):
    """Create audio extractor instance."""
    input_file = tmp_path / "input.mp4"
    input_file.touch()

    output_dir = tmp_path / "audio_output"

    return AudioExtractor(
        input_file=input_file,
        output_dir=output_dir,
    )


class TestAudioQuality:
    """Tests for AudioQuality dataclass."""

    def test_quality_initialization(self):
        """Test audio quality preset initialization."""
        quality = AudioQuality("high", 192, 48000, 2)

        assert quality.name == "high"
        assert quality.bitrate == 192
        assert quality.sample_rate == 48000
        assert quality.channels == 2

    def test_channel_layout(self):
        """Test channel layout property."""
        mono = AudioQuality("mono", 96, 44100, 1)
        assert mono.channel_layout == "mono"

        stereo = AudioQuality("stereo", 128, 48000, 2)
        assert stereo.channel_layout == "stereo"

        surround = AudioQuality("5.1", 320, 48000, 6)
        assert surround.channel_layout == "5.1"

        custom = AudioQuality("custom", 256, 48000, 4)
        assert custom.channel_layout == "4ch"


class TestAudioQualityPresets:
    """Tests for standard audio quality presets."""

    def test_all_presets_exist(self):
        """Test all expected presets are defined."""
        assert "high" in AUDIO_QUALITY_PRESETS
        assert "medium" in AUDIO_QUALITY_PRESETS
        assert "low" in AUDIO_QUALITY_PRESETS

    def test_preset_bitrates(self):
        """Test preset bitrate values."""
        assert AUDIO_QUALITY_PRESETS["high"].bitrate == 192
        assert AUDIO_QUALITY_PRESETS["medium"].bitrate == 128
        assert AUDIO_QUALITY_PRESETS["low"].bitrate == 96

    def test_preset_sample_rates(self):
        """Test preset sample rate values."""
        assert AUDIO_QUALITY_PRESETS["high"].sample_rate == 48000
        assert AUDIO_QUALITY_PRESETS["medium"].sample_rate == 48000
        assert AUDIO_QUALITY_PRESETS["low"].sample_rate == 44100


class TestAudioExtractor:
    """Tests for AudioExtractor class."""

    def test_initialization(self, audio_extractor, tmp_path):
        """Test audio extractor initialization."""
        assert audio_extractor.input_file == tmp_path / "input.mp4"
        assert audio_extractor.output_dir == tmp_path / "audio_output"
        assert audio_extractor.output_dir.exists()

    @pytest.mark.asyncio
    async def test_extract_success(self, audio_extractor, audio_stream):
        """Test successful audio extraction."""
        quality = AUDIO_QUALITY_PRESETS["medium"]

        # Mock AsyncFFmpegProcess
        with patch("hls_transcoder.transcoder.audio.AsyncFFmpegProcess") as mock_process:
            mock_instance = AsyncMock()
            mock_process.return_value = mock_instance

            # Create expected output file
            output_path = audio_extractor.output_dir / "audio_eng_medium.m3u8"
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.touch()

            result = await audio_extractor.extract(
                audio_stream=audio_stream,
                quality=quality,
            )

            assert result == output_path
            mock_instance.run.assert_called_once()

    @pytest.mark.asyncio
    async def test_extract_with_progress_callback(self, audio_extractor, audio_stream):
        """Test extraction with progress callback."""
        quality = AUDIO_QUALITY_PRESETS["high"]
        progress_values = []

        def progress_callback(current: float, total: Optional[float] = None):
            progress_values.append(current)

        with patch("hls_transcoder.transcoder.audio.AsyncFFmpegProcess") as mock_process:
            mock_instance = AsyncMock()
            mock_process.return_value = mock_instance

            output_path = audio_extractor.output_dir / "audio_eng_high.m3u8"
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.touch()

            await audio_extractor.extract(
                audio_stream=audio_stream,
                quality=quality,
                progress_callback=progress_callback,
            )

            # Verify progress callback was passed
            assert mock_process.call_args.kwargs["progress_callback"] is not None

    @pytest.mark.asyncio
    async def test_extract_failure(self, audio_extractor, audio_stream):
        """Test extraction failure handling."""
        quality = AUDIO_QUALITY_PRESETS["medium"]

        with patch("hls_transcoder.transcoder.audio.AsyncFFmpegProcess") as mock_process:
            mock_instance = AsyncMock()
            mock_instance.run.side_effect = Exception("FFmpeg failed")
            mock_process.return_value = mock_instance

            with pytest.raises(TranscodingError) as exc_info:
                await audio_extractor.extract(audio_stream, quality)

            assert "Failed to extract audio" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_extract_output_not_created(self, audio_extractor, audio_stream):
        """Test error when output file is not created."""
        quality = AUDIO_QUALITY_PRESETS["medium"]

        with patch("hls_transcoder.transcoder.audio.AsyncFFmpegProcess") as mock_process:
            mock_instance = AsyncMock()
            mock_process.return_value = mock_instance

            # Don't create output file

            with pytest.raises(TranscodingError) as exc_info:
                await audio_extractor.extract(audio_stream, quality)

            assert "output not found" in str(exc_info.value)

    def test_get_track_name(self, audio_extractor, audio_stream):
        """Test track name generation."""
        quality = AUDIO_QUALITY_PRESETS["high"]

        name = audio_extractor._get_track_name(audio_stream, quality)
        assert name == "audio_eng_high"

        # Test with different language
        audio_stream.language = "hin"
        name = audio_extractor._get_track_name(audio_stream, quality)
        assert name == "audio_hin_high"

        # Test with undefined language
        audio_stream.language = None
        name = audio_extractor._get_track_name(audio_stream, quality)
        assert name == "audio_und_high"


class TestCommandBuilding:
    """Tests for FFmpeg command building."""

    def test_build_command_basic(self, audio_extractor, audio_stream):
        """Test basic command building."""
        quality = AUDIO_QUALITY_PRESETS["medium"]
        options = AudioExtractionOptions(
            audio_stream=audio_stream,
            output_path=audio_extractor.output_dir / "audio_eng_medium.m3u8",
            quality=quality,
        )
        segment_pattern = audio_extractor.output_dir / "audio_eng_medium_%03d.ts"

        command = audio_extractor._build_command(options, segment_pattern)

        assert "ffmpeg" in command
        assert "-y" in command
        assert "-i" in command
        assert str(audio_extractor.input_file) in command
        assert "-map" in command
        assert f"0:{audio_stream.index}" in command

    def test_audio_options(self, audio_extractor, audio_stream):
        """Test audio encoding options."""
        quality = AUDIO_QUALITY_PRESETS["high"]
        options = AudioExtractionOptions(
            audio_stream=audio_stream,
            output_path=audio_extractor.output_dir / "test.m3u8",
            quality=quality,
        )

        audio_opts = audio_extractor._get_audio_options(options)

        assert "-c:a" in audio_opts
        assert "aac" in audio_opts
        assert "-b:a" in audio_opts
        assert f"{quality.bitrate}k" in audio_opts
        assert "-ar" in audio_opts
        assert str(quality.sample_rate) in audio_opts

    def test_audio_options_channel_conversion(self, audio_extractor, audio_stream):
        """Test audio options with channel conversion."""
        # Source has 6 channels, target has 2
        audio_stream.channels = 6
        quality = AUDIO_QUALITY_PRESETS["medium"]  # 2 channels

        options = AudioExtractionOptions(
            audio_stream=audio_stream,
            output_path=audio_extractor.output_dir / "test.m3u8",
            quality=quality,
        )

        audio_opts = audio_extractor._get_audio_options(options)

        assert "-ac" in audio_opts
        assert "2" in audio_opts

    def test_hls_options(self, audio_extractor, audio_stream):
        """Test HLS output options."""
        quality = AUDIO_QUALITY_PRESETS["medium"]
        options = AudioExtractionOptions(
            audio_stream=audio_stream,
            output_path=audio_extractor.output_dir / "test.m3u8",
            quality=quality,
        )
        segment_pattern = audio_extractor.output_dir / "test_%03d.ts"

        hls_opts = audio_extractor._get_hls_options(options, segment_pattern)

        assert "-f" in hls_opts
        assert "hls" in hls_opts
        assert "-hls_time" in hls_opts
        assert str(options.segment_duration) in hls_opts
        assert "-hls_segment_filename" in hls_opts


class TestMultiTrackExtraction:
    """Tests for multi-track audio extraction."""

    @pytest.mark.asyncio
    async def test_extract_all_tracks_success(self, audio_extractor):
        """Test successful multi-track extraction."""
        audio_streams = [
            AudioStream(
                index=1,
                codec="aac",
                codec_long="AAC",
                profile="LC",
                language="eng",
                channels=2,
                sample_rate=48000,
                bitrate=128000,
                duration=120.0,
            ),
            AudioStream(
                index=2,
                codec="aac",
                codec_long="AAC",
                profile="LC",
                language="hin",
                channels=2,
                sample_rate=48000,
                bitrate=128000,
                duration=120.0,
            ),
        ]

        with patch("hls_transcoder.transcoder.audio.AsyncFFmpegProcess") as mock_process:
            mock_instance = AsyncMock()
            mock_process.return_value = mock_instance

            # Create output files
            for stream in audio_streams:
                output_path = audio_extractor.output_dir / f"audio_{stream.language}_medium.m3u8"
                output_path.parent.mkdir(parents=True, exist_ok=True)
                output_path.touch()

            results = await audio_extractor.extract_all_tracks(audio_streams)

            assert len(results) == 2
            assert "audio_eng_medium" in results
            assert "audio_hin_medium" in results

    @pytest.mark.asyncio
    async def test_extract_all_tracks_with_progress(self, audio_extractor):
        """Test multi-track extraction with progress tracking."""
        audio_streams = [
            AudioStream(
                index=1,
                codec="aac",
                codec_long="AAC",
                profile="LC",
                language="eng",
                channels=2,
                sample_rate=48000,
                bitrate=128000,
                duration=120.0,
            ),
        ]

        progress_updates = []

        def progress_callback(track_index: int, progress: float):
            progress_updates.append((track_index, progress))

        with patch("hls_transcoder.transcoder.audio.AsyncFFmpegProcess") as mock_process:
            mock_instance = AsyncMock()
            mock_process.return_value = mock_instance

            output_path = audio_extractor.output_dir / "audio_eng_medium.m3u8"
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.touch()

            await audio_extractor.extract_all_tracks(
                audio_streams,
                progress_callback=progress_callback,
            )

            # Verify progress callback was set up
            assert mock_process.call_count == 1

    @pytest.mark.asyncio
    async def test_extract_all_tracks_with_failure(self, audio_extractor):
        """Test multi-track extraction with failure."""
        audio_streams = [
            AudioStream(
                index=1,
                codec="aac",
                codec_long="AAC",
                profile="LC",
                language="eng",
                channels=2,
                sample_rate=48000,
                bitrate=128000,
                duration=120.0,
            ),
        ]

        with patch("hls_transcoder.transcoder.audio.AsyncFFmpegProcess") as mock_process:
            mock_instance = AsyncMock()
            mock_instance.run.side_effect = Exception("Extraction failed")
            mock_process.return_value = mock_instance

            with pytest.raises(Exception) as exc_info:
                await audio_extractor.extract_all_tracks(audio_streams)

            assert "Extraction failed" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_concurrent_limit(self, audio_extractor):
        """Test concurrent extraction limit."""
        audio_streams = [
            AudioStream(
                index=i,
                codec="aac",
                codec_long="AAC",
                profile="LC",
                language=f"lang{i}",
                channels=2,
                sample_rate=48000,
                bitrate=128000,
                duration=120.0,
            )
            for i in range(5)
        ]

        with patch("hls_transcoder.transcoder.audio.AsyncFFmpegProcess") as mock_process:
            mock_instance = AsyncMock()
            mock_process.return_value = mock_instance

            # Create output files
            for stream in audio_streams:
                output_path = audio_extractor.output_dir / f"audio_{stream.language}_medium.m3u8"
                output_path.parent.mkdir(parents=True, exist_ok=True)
                output_path.touch()

            # Extract with max_concurrent=2
            results = await audio_extractor.extract_all_tracks(
                audio_streams,
                max_concurrent=2,
            )

            assert len(results) == 5
