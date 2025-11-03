"""
Tests for media inspector module.
"""

import asyncio
import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from hls_transcoder.inspector import MediaInspector
from hls_transcoder.models import (
    AudioStream,
    FormatInfo,
    MediaInfo,
    SubtitleStream,
    VideoStream,
)
from hls_transcoder.utils import MediaInspectionError


@pytest.fixture
def sample_ffprobe_output():
    """Sample ffprobe JSON output for testing."""
    return {
        "format": {
            "filename": "/path/to/video.mp4",
            "format_name": "mov,mp4,m4a,3gp,3g2,mj2",
            "format_long_name": "QuickTime / MOV",
            "duration": "120.5",
            "size": "10485760",
            "bit_rate": "696320",
            "probe_score": 100,
        },
        "streams": [
            {
                "index": 0,
                "codec_type": "video",
                "codec_name": "h264",
                "codec_long_name": "H.264 / AVC / MPEG-4 AVC / MPEG-4 part 10",
                "profile": "High",
                "width": 1920,
                "height": 1080,
                "r_frame_rate": "30000/1001",
                "bit_rate": "600000",
                "pix_fmt": "yuv420p",
                "color_space": "bt709",
                "color_range": "tv",
                "duration": "120.5",
            },
            {
                "index": 1,
                "codec_type": "audio",
                "codec_name": "aac",
                "codec_long_name": "AAC (Advanced Audio Coding)",
                "profile": "LC",
                "sample_rate": "48000",
                "channels": 2,
                "channel_layout": "stereo",
                "bit_rate": "128000",
                "duration": "120.5",
                "tags": {
                    "language": "eng",
                    "title": "English Audio",
                },
            },
            {
                "index": 2,
                "codec_type": "subtitle",
                "codec_name": "subrip",
                "codec_long_name": "SubRip subtitle",
                "duration": "120.5",
                "tags": {
                    "language": "eng",
                    "title": "English Subtitles",
                },
            },
        ],
    }


@pytest.fixture
def inspector():
    """Create media inspector instance."""
    return MediaInspector()


class TestMediaInspector:
    """Test MediaInspector class."""

    def test_initialization(self):
        """Test inspector initialization."""
        inspector = MediaInspector()
        assert inspector._ffprobe_path == "ffprobe"

        inspector = MediaInspector(ffprobe_path="/usr/bin/ffprobe")
        assert inspector._ffprobe_path == "/usr/bin/ffprobe"

    @pytest.mark.asyncio
    async def test_inspect_nonexistent_file(self, inspector):
        """Test inspection with nonexistent file."""
        with pytest.raises(MediaInspectionError, match="File not found"):
            await inspector.inspect(Path("/nonexistent/file.mp4"))

    @pytest.mark.asyncio
    async def test_inspect_directory(self, inspector, tmp_path):
        """Test inspection with directory instead of file."""
        with pytest.raises(MediaInspectionError, match="Not a file"):
            await inspector.inspect(tmp_path)

    @pytest.mark.asyncio
    async def test_inspect_success(self, inspector, sample_ffprobe_output, tmp_path):
        """Test successful media inspection."""
        # Create a dummy file
        test_file = tmp_path / "test.mp4"
        test_file.write_text("dummy")

        # Mock ffprobe execution
        async def mock_run_ffprobe(input_file):
            return sample_ffprobe_output

        with patch.object(inspector, "_run_ffprobe", side_effect=mock_run_ffprobe):
            media_info = await inspector.inspect(test_file)

            # Check format info
            assert media_info.format.format_name == "mov,mp4,m4a,3gp,3g2,mj2"
            assert media_info.format.duration == 120.5
            assert media_info.format.size == 10485760
            assert media_info.format.bitrate == 696320

            # Check video stream
            assert len(media_info.video_streams) == 1
            video = media_info.video_streams[0]
            assert video.index == 0
            assert video.codec == "h264"
            assert video.width == 1920
            assert video.height == 1080
            assert video.fps == pytest.approx(29.97, rel=0.01)
            assert video.bitrate == 600000

            # Check audio stream
            assert len(media_info.audio_streams) == 1
            audio = media_info.audio_streams[0]
            assert audio.index == 1
            assert audio.codec == "aac"
            assert audio.channels == 2
            assert audio.sample_rate == 48000
            assert audio.language == "eng"

            # Check subtitle stream
            assert len(media_info.subtitle_streams) == 1
            subtitle = media_info.subtitle_streams[0]
            assert subtitle.index == 2
            assert subtitle.codec == "subrip"
            assert subtitle.language == "eng"
            assert subtitle.title == "English Subtitles"

    @pytest.mark.asyncio
    async def test_run_ffprobe_success(self, inspector, sample_ffprobe_output):
        """Test _run_ffprobe with successful execution."""
        test_file = Path("/test.mp4")

        # Mock subprocess
        mock_process = AsyncMock()
        mock_process.returncode = 0
        mock_process.communicate = AsyncMock(
            return_value=(json.dumps(sample_ffprobe_output).encode(), b"")
        )

        with patch("asyncio.create_subprocess_exec", return_value=mock_process):
            result = await inspector._run_ffprobe(test_file)
            assert result == sample_ffprobe_output

    @pytest.mark.asyncio
    async def test_run_ffprobe_failure(self, inspector):
        """Test _run_ffprobe with process failure."""
        test_file = Path("/test.mp4")

        # Mock subprocess with failure
        mock_process = AsyncMock()
        mock_process.returncode = 1
        mock_process.communicate = AsyncMock(return_value=(b"", b"Error: Invalid file"))

        with patch("asyncio.create_subprocess_exec", return_value=mock_process):
            with pytest.raises(MediaInspectionError, match="FFprobe failed"):
                await inspector._run_ffprobe(test_file)

    @pytest.mark.asyncio
    async def test_run_ffprobe_json_error(self, inspector):
        """Test _run_ffprobe with invalid JSON output."""
        test_file = Path("/test.mp4")

        # Mock subprocess with invalid JSON
        mock_process = AsyncMock()
        mock_process.returncode = 0
        mock_process.communicate = AsyncMock(return_value=(b"not json", b""))

        with patch("asyncio.create_subprocess_exec", return_value=mock_process):
            with pytest.raises(MediaInspectionError, match="Failed to parse"):
                await inspector._run_ffprobe(test_file)

    def test_parse_format(self, inspector, sample_ffprobe_output):
        """Test format information parsing."""
        format_info = inspector._parse_format(sample_ffprobe_output)

        assert format_info.format_name == "mov,mp4,m4a,3gp,3g2,mj2"
        assert format_info.format_long_name == "QuickTime / MOV"
        assert format_info.duration == 120.5
        assert format_info.size == 10485760
        assert format_info.bitrate == 696320

    def test_parse_video_stream(self, inspector, sample_ffprobe_output):
        """Test video stream parsing."""
        stream_data = sample_ffprobe_output["streams"][0]
        video = inspector._parse_video_stream(stream_data)

        assert video is not None
        assert video.index == 0
        assert video.codec == "h264"
        assert video.codec_long == "H.264 / AVC / MPEG-4 AVC / MPEG-4 part 10"
        assert video.width == 1920
        assert video.height == 1080
        assert video.fps == pytest.approx(29.97, rel=0.01)
        assert video.bitrate == 600000
        assert video.pix_fmt == "yuv420p"
        assert video.color_space == "bt709"
        assert video.duration == 120.5

    def test_parse_video_stream_invalid_fps(self, inspector):
        """Test video stream parsing with invalid frame rate."""
        stream_data = {
            "index": 0,
            "codec_name": "h264",
            "codec_long_name": "H.264",
            "width": 1920,
            "height": 1080,
            "r_frame_rate": "0/0",  # Invalid
            "pix_fmt": "yuv420p",
            "duration": "120.5",
        }
        video = inspector._parse_video_stream(stream_data)

        assert video is not None
        assert video.fps == 0.0

    def test_parse_audio_stream(self, inspector, sample_ffprobe_output):
        """Test audio stream parsing."""
        stream_data = sample_ffprobe_output["streams"][1]
        audio = inspector._parse_audio_stream(stream_data)

        assert audio is not None
        assert audio.index == 1
        assert audio.codec == "aac"
        assert audio.codec_long == "AAC (Advanced Audio Coding)"
        assert audio.sample_rate == 48000
        assert audio.channels == 2
        assert audio.bitrate == 128000
        assert audio.language == "eng"
        assert audio.duration == 120.5

    def test_parse_audio_stream_no_language(self, inspector):
        """Test audio stream parsing without language tag."""
        stream_data = {
            "index": 1,
            "codec_name": "aac",
            "codec_long_name": "AAC",
            "sample_rate": "48000",
            "channels": 2,
            "bit_rate": "128000",
            "duration": "120.5",
            "tags": {},
        }
        audio = inspector._parse_audio_stream(stream_data)

        assert audio is not None
        assert audio.language == "und"  # undefined

    def test_parse_subtitle_stream(self, inspector, sample_ffprobe_output):
        """Test subtitle stream parsing."""
        stream_data = sample_ffprobe_output["streams"][2]
        subtitle = inspector._parse_subtitle_stream(stream_data)

        assert subtitle is not None
        assert subtitle.index == 2
        assert subtitle.codec == "subrip"
        assert subtitle.language == "eng"
        assert subtitle.title == "English Subtitles"

    def test_parse_subtitle_stream_minimal(self, inspector):
        """Test subtitle stream parsing with minimal data."""
        stream_data = {
            "index": 2,
            "codec_name": "subrip",
            "tags": {"language": "eng"},
        }
        subtitle = inspector._parse_subtitle_stream(stream_data)

        assert subtitle is not None
        assert subtitle.index == 2
        assert subtitle.codec == "subrip"
        assert subtitle.language == "eng"
        assert subtitle.title is None  # None when no title tag


class TestValidation:
    """Test media validation functionality."""

    def test_validate_complete_media(self):
        """Test validation with complete, valid media."""
        media_info = MediaInfo(
            format=FormatInfo(
                format_name="mp4",
                format_long_name="MPEG-4",
                duration=120.5,
                size=10485760,
                bitrate=696320,
            ),
            video_streams=[
                VideoStream(
                    index=0,
                    codec="h264",
                    codec_long="H.264",
                    profile="Main",
                    width=1920,
                    height=1080,
                    fps=30.0,
                    bitrate=600000,
                    pix_fmt="yuv420p",
                    color_space="bt709",
                    duration=120.5,
                )
            ],
            audio_streams=[
                AudioStream(
                    index=1,
                    codec="aac",
                    codec_long="AAC",
                    profile="LC",
                    language="eng",
                    channels=2,
                    sample_rate=48000,
                    bitrate=128000,
                    duration=120.5,
                )
            ],
            subtitle_streams=[],
            duration=120.5,
            size=10485760,
            bitrate=696320,
        )

        inspector = MediaInspector()
        warnings = inspector.validate_for_transcoding(media_info)
        assert len(warnings) == 0

    def test_validate_no_video(self):
        """Test validation with no video streams."""
        media_info = MediaInfo(
            format=FormatInfo(
                format_name="mp3",
                format_long_name="MP3",
                duration=120.5,
                size=1048576,
                bitrate=128000,
            ),
            video_streams=[],
            audio_streams=[
                AudioStream(
                    index=0,
                    codec="mp3",
                    codec_long="MP3",
                    profile="",
                    language="eng",
                    channels=2,
                    sample_rate=44100,
                    bitrate=128000,
                    duration=120.5,
                )
            ],
            subtitle_streams=[],
            duration=120.5,
            size=1048576,
            bitrate=128000,
        )

        inspector = MediaInspector()
        warnings = inspector.validate_for_transcoding(media_info)
        assert "No video streams found" in warnings

    def test_validate_invalid_resolution(self):
        """Test validation with invalid resolution."""
        media_info = MediaInfo(
            format=FormatInfo(
                format_name="mp4",
                format_long_name="MPEG-4",
                duration=120.5,
                size=10485760,
                bitrate=696320,
            ),
            video_streams=[
                VideoStream(
                    index=0,
                    codec="h264",
                    codec_long="H.264",
                    profile="Main",
                    width=0,
                    height=0,
                    fps=30.0,
                    bitrate=600000,
                    pix_fmt="yuv420p",
                    duration=120.5,
                )
            ],
            audio_streams=[],
            subtitle_streams=[],
            duration=120.5,
            size=10485760,
            bitrate=696320,
        )

        inspector = MediaInspector()
        warnings = inspector.validate_for_transcoding(media_info)
        assert "Invalid video resolution" in warnings
        assert "No audio streams found" in warnings

    def test_validate_zero_fps(self):
        """Test validation with zero frame rate."""
        media_info = MediaInfo(
            format=FormatInfo(
                format_name="mp4",
                format_long_name="MPEG-4",
                duration=120.5,
                size=10485760,
                bitrate=696320,
            ),
            video_streams=[
                VideoStream(
                    index=0,
                    codec="h264",
                    codec_long="H.264",
                    profile="Main",
                    width=1920,
                    height=1080,
                    fps=0.0,
                    bitrate=600000,
                    pix_fmt="yuv420p",
                    duration=120.5,
                )
            ],
            audio_streams=[
                AudioStream(
                    index=1,
                    codec="aac",
                    codec_long="AAC",
                    profile="LC",
                    language="eng",
                    channels=2,
                    sample_rate=48000,
                    bitrate=128000,
                    duration=120.5,
                )
            ],
            subtitle_streams=[],
            duration=120.5,
            size=10485760,
            bitrate=696320,
        )

        inspector = MediaInspector()
        warnings = inspector.validate_for_transcoding(media_info)
        assert "Invalid or missing frame rate" in warnings

    def test_validate_zero_size(self):
        """Test validation with zero file size."""
        media_info = MediaInfo(
            format=FormatInfo(
                format_name="mp4",
                format_long_name="MPEG-4",
                duration=120.5,
                size=0,
                bitrate=696320,
            ),
            video_streams=[
                VideoStream(
                    index=0,
                    codec="h264",
                    codec_long="H.264",
                    profile="Main",
                    width=1920,
                    height=1080,
                    fps=30.0,
                    bitrate=600000,
                    pix_fmt="yuv420p",
                    duration=120.5,
                )
            ],
            audio_streams=[
                AudioStream(
                    index=1,
                    codec="aac",
                    codec_long="AAC",
                    profile="LC",
                    language="eng",
                    channels=2,
                    sample_rate=48000,
                    bitrate=128000,
                    duration=120.5,
                )
            ],
            subtitle_streams=[],
            duration=120.5,
            size=0,
            bitrate=696320,
        )

        inspector = MediaInspector()
        warnings = inspector.validate_for_transcoding(media_info)
        assert "File size is 0 bytes" in warnings

    def test_validate_zero_duration(self):
        """Test validation with zero duration."""
        media_info = MediaInfo(
            format=FormatInfo(
                format_name="mp4",
                format_long_name="MPEG-4",
                duration=0.0,
                size=10485760,
                bitrate=696320,
            ),
            video_streams=[
                VideoStream(
                    index=0,
                    codec="h264",
                    codec_long="H.264",
                    profile="Main",
                    width=1920,
                    height=1080,
                    fps=30.0,
                    bitrate=600000,
                    pix_fmt="yuv420p",
                    duration=0.0,
                )
            ],
            audio_streams=[
                AudioStream(
                    index=1,
                    codec="aac",
                    codec_long="AAC",
                    profile="LC",
                    language="eng",
                    channels=2,
                    sample_rate=48000,
                    bitrate=128000,
                    duration=0.0,
                )
            ],
            subtitle_streams=[],
            duration=0.0,
            size=10485760,
            bitrate=696320,
        )

        inspector = MediaInspector()
        warnings = inspector.validate_for_transcoding(media_info)
        assert "Duration is 0 seconds" in warnings


class TestGlobalInstance:
    """Test global inspector instance."""

    def test_get_global_inspector(self):
        """Test global inspector getter."""
        from hls_transcoder.inspector.analyzer import get_media_inspector

        inspector1 = get_media_inspector()
        inspector2 = get_media_inspector()

        assert inspector1 is inspector2  # Same instance


class TestFallbackParsing:
    """Tests for fallback parsing from tags."""

    @pytest.mark.asyncio
    async def test_parse_mkv_with_tags_bitrate(self):
        """Test parsing MKV file where bitrate is in tags.BPS."""
        inspector = MediaInspector()

        # Load real MKV metadata
        fixtures_dir = Path(__file__).parent / "fixtures"
        json_file = fixtures_dir / "metadata" / "Hostel Daze S02 Complete (2021).json"

        if not json_file.exists():
            pytest.skip("Test fixture not found")

        with open(json_file) as f:
            ffprobe_data = json.load(f)

        with patch.object(inspector, "_run_ffprobe", return_value=ffprobe_data):
            media_info = await inspector.inspect(
                fixtures_dir / "Hostel Daze S02 Complete (2021).mkv"
            )

            # Check video stream parsed correctly with BPS fallback
            assert len(media_info.video_streams) == 1
            video = media_info.video_streams[0]
            assert video.codec == "hevc"
            assert video.width == 1280
            assert video.height == 720
            assert video.fps == 25.0
            # Bitrate should come from tags.BPS
            assert video.bitrate == 736522
            # Check additional metadata from tags
            assert video.frame_count == 50807
            assert video.encoder == "mkvmerge v59.0.0 ('Shining Star') 64-bit"
            assert video.is_default is True
            assert video.duration == pytest.approx(7701.648, rel=0.001)

            # Check audio stream
            assert len(media_info.audio_streams) == 1
            audio = media_info.audio_streams[0]
            assert audio.codec == "eac3"
            assert audio.channels == 6
            assert audio.channel_layout == "5.1(side)"
            assert audio.language == "hin"
            assert audio.title == "Hindi"
            assert audio.bitrate == 640000  # From bit_rate field
            # Check additional metadata from tags
            assert audio.frame_count == 63509
            assert audio.encoder == "mkvmerge v59.0.0 ('Shining Star') 64-bit"
            assert audio.is_default is True

            # Check subtitle stream
            assert len(media_info.subtitle_streams) == 1
            subtitle = media_info.subtitle_streams[0]
            assert subtitle.codec == "subrip"
            assert subtitle.language == "eng"
            assert subtitle.title == "English"
            # Check additional metadata from tags
            assert subtitle.frame_count == 586
            assert subtitle.encoder == "mkvmerge v59.0.0 ('Shining Star') 64-bit"
            assert subtitle.is_default is True
            assert subtitle.forced is False

            # Check format info metadata
            assert media_info.format.encoder == "Lavf59.3.100"
            # Note: This particular file doesn't have creation_time in format tags
            assert media_info.format.creation_time is None

    def test_parse_duration_string(self):
        """Test duration string parsing."""
        inspector = MediaInspector()

        # Test valid duration strings
        assert inspector._parse_duration_string("02:08:21.648000000") == pytest.approx(
            7701.648, rel=0.001
        )
        assert inspector._parse_duration_string("00:01:30.000000000") == 90.0
        assert inspector._parse_duration_string("01:00:00.000000000") == 3600.0

        # Test edge cases
        assert inspector._parse_duration_string("") == 0.0
        assert inspector._parse_duration_string("invalid") == 0.0
        assert inspector._parse_duration_string("12:34") == 0.0  # Wrong format

    @pytest.mark.asyncio
    async def test_bitrate_fallback_priority(self):
        """Test bitrate fallback priority (bit_rate > tags.BPS)."""
        inspector = MediaInspector()

        # Stream with both bit_rate and tags.BPS
        stream_with_both = {
            "index": 0,
            "codec_type": "video",
            "codec_name": "h264",
            "codec_long_name": "H.264",
            "width": 1920,
            "height": 1080,
            "r_frame_rate": "30/1",
            "bit_rate": "5000000",  # Should use this
            "pix_fmt": "yuv420p",
            "duration": "120.0",
            "tags": {"BPS": "4000000"},  # Not this
        }

        video = inspector._parse_video_stream(stream_with_both)
        assert video is not None
        assert video.bitrate == 5000000  # Uses bit_rate, not tags.BPS

        # Stream with only tags.BPS
        stream_tags_only = {
            "index": 0,
            "codec_type": "video",
            "codec_name": "hevc",
            "codec_long_name": "HEVC",
            "width": 1280,
            "height": 720,
            "r_frame_rate": "25/1",
            "pix_fmt": "yuv420p",
            "tags": {"BPS": "736522"},  # Should use this
        }

        video = inspector._parse_video_stream(stream_tags_only)
        assert video is not None
        assert video.bitrate == 736522  # Falls back to tags.BPS

    @pytest.mark.asyncio
    async def test_duration_fallback_priority(self):
        """Test duration fallback priority (duration > tags.DURATION)."""
        inspector = MediaInspector()

        # Stream with both duration and tags.DURATION
        stream_with_both = {
            "index": 1,
            "codec_type": "audio",
            "codec_name": "aac",
            "codec_long_name": "AAC",
            "sample_rate": "48000",
            "channels": 2,
            "bit_rate": "128000",
            "duration": "120.5",  # Should use this
            "tags": {"DURATION": "02:00:30.000000000"},  # Not this
        }

        audio = inspector._parse_audio_stream(stream_with_both)
        assert audio is not None
        assert audio.duration == 120.5  # Uses duration, not tags.DURATION

        # Stream with only tags.DURATION
        stream_tags_only = {
            "index": 1,
            "codec_type": "audio",
            "codec_name": "eac3",
            "codec_long_name": "E-AC-3",
            "sample_rate": "48000",
            "channels": 6,
            "bit_rate": "640000",
            "tags": {"DURATION": "02:08:21.664000000"},  # Should parse this
        }

        audio = inspector._parse_audio_stream(stream_tags_only)
        assert audio is not None
        assert audio.duration == pytest.approx(7701.664, rel=0.001)

    def test_subtitle_forced_flag(self):
        """Test subtitle forced flag parsing from disposition."""
        inspector = MediaInspector()

        # Subtitle with forced flag
        subtitle_forced = {
            "index": 2,
            "codec_type": "subtitle",
            "codec_name": "subrip",
            "codec_long_name": "SubRip",
            "disposition": {"forced": 1},
            "tags": {"language": "eng", "title": "English (Forced)"},
        }

        subtitle = inspector._parse_subtitle_stream(subtitle_forced)
        assert subtitle is not None
        assert subtitle.forced is True

        # Subtitle without forced flag
        subtitle_normal = {
            "index": 2,
            "codec_type": "subtitle",
            "codec_name": "subrip",
            "codec_long_name": "SubRip",
            "disposition": {"forced": 0},
            "tags": {"language": "eng", "title": "English"},
        }

        subtitle = inspector._parse_subtitle_stream(subtitle_normal)
        assert subtitle is not None
        assert subtitle.forced is False

    def test_tag_value_with_language_suffix(self):
        """Test _get_tag_value with language-suffixed tag names."""
        inspector = MediaInspector()

        # Test exact match
        tags_exact = {
            "_STATISTICS_TAGS": "BPS DURATION NUMBER_OF_FRAMES",
            "BPS": "5000000",
            "DURATION": "120.5",
            "NUMBER_OF_FRAMES": "3600",
        }
        assert inspector._get_tag_value(tags_exact, "BPS") == "5000000"
        assert inspector._get_tag_value(tags_exact, "DURATION") == "120.5"
        assert inspector._get_tag_value(tags_exact, "NUMBER_OF_FRAMES") == "3600"

        # Test pattern match with underscore suffix (BPS_HINDI)
        tags_underscore = {
            "_STATISTICS_TAGS": "BPS_HINDI DURATION_ENG NUMBER_OF_FRAMES_HINDI",
            "BPS_HINDI": "640000",
            "DURATION_ENG": "02:08:21.648000000",
            "NUMBER_OF_FRAMES_HINDI": "63509",
        }
        assert inspector._get_tag_value(tags_underscore, "BPS") == "640000"
        assert inspector._get_tag_value(tags_underscore, "DURATION") == "02:08:21.648000000"
        assert inspector._get_tag_value(tags_underscore, "NUMBER_OF_FRAMES") == "63509"

        # Test pattern match with hyphen suffix (BPS-eng)
        tags_hyphen = {
            "_STATISTICS_TAGS": "BPS-eng DURATION-eng NUMBER_OF_FRAMES-eng",
            "BPS-eng": "736522",
            "DURATION-eng": "02:08:21.648000000",
            "NUMBER_OF_FRAMES-eng": "50807",
        }
        assert inspector._get_tag_value(tags_hyphen, "BPS") == "736522"
        assert inspector._get_tag_value(tags_hyphen, "DURATION") == "02:08:21.648000000"
        assert inspector._get_tag_value(tags_hyphen, "NUMBER_OF_FRAMES") == "50807"

        # Test multiple languages - should return first match
        tags_multiple = {
            "_STATISTICS_TAGS": "BPS-eng BPS-hin DURATION-eng",
            "BPS-eng": "5000000",
            "BPS-hin": "640000",
            "DURATION-eng": "120.0",
        }
        # Should get first matching tag (BPS-eng)
        bps_value = inspector._get_tag_value(tags_multiple, "BPS")
        assert bps_value in ["5000000", "640000"]  # Either is valid

        # Test non-existent tag
        assert inspector._get_tag_value(tags_exact, "NONEXISTENT") == ""
        assert inspector._get_tag_value(tags_exact, "NONEXISTENT", "default") == "default"

        # Test fallback when no _STATISTICS_TAGS
        tags_no_stats = {
            "BPS": "1000000",
            "DURATION": "60.0",
        }
        assert inspector._get_tag_value(tags_no_stats, "BPS") == "1000000"
        assert inspector._get_tag_value(tags_no_stats, "DURATION") == "60.0"
