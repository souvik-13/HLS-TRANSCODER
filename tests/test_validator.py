"""
Tests for output validator.
"""

from pathlib import Path

import pytest

from hls_transcoder.models import (
    AudioTrackResult,
    SpriteResult,
    SubtitleResult,
    TranscodingResults,
    ValidationResult,
    VideoVariantResult,
)
from hls_transcoder.validator import OutputValidator, quick_validate, validate_output


# === Fixtures ===


@pytest.fixture
def output_dir(tmp_path):
    """Create test output directory."""
    return tmp_path / "output"


@pytest.fixture
def master_playlist(output_dir):
    """Create master playlist."""
    output_dir.mkdir(parents=True, exist_ok=True)
    master = output_dir / "master.m3u8"
    master.write_text(
        """#EXTM3U
#EXT-X-VERSION:7

#EXT-X-MEDIA:TYPE=AUDIO,GROUP-ID="audio",NAME="ENG Audio",LANGUAGE="eng",URI="audio_eng.m3u8",DEFAULT=YES
#EXT-X-STREAM-INF:BANDWIDTH=5000000,RESOLUTION=1920x1080,FRAME-RATE=30.0,CODECS="avc1.640028,mp4a.40.2",AUDIO="audio"
video_1080p.m3u8
"""
    )
    return master


@pytest.fixture
def video_playlist(output_dir):
    """Create video variant playlist with segments."""
    output_dir.mkdir(parents=True, exist_ok=True)
    playlist = output_dir / "video_1080p.m3u8"
    playlist.write_text(
        """#EXTM3U
#EXT-X-VERSION:3
#EXT-X-TARGETDURATION:6
#EXTINF:6.0,
segment_000.ts
#EXTINF:6.0,
segment_001.ts
#EXT-X-ENDLIST
"""
    )

    # Create segment files
    (output_dir / "segment_000.ts").write_bytes(b"fake video data")
    (output_dir / "segment_001.ts").write_bytes(b"fake video data")

    return playlist


@pytest.fixture
def audio_playlist(output_dir):
    """Create audio playlist with segments."""
    output_dir.mkdir(parents=True, exist_ok=True)
    playlist = output_dir / "audio_eng.m3u8"
    playlist.write_text(
        """#EXTM3U
#EXT-X-VERSION:3
#EXT-X-TARGETDURATION:6
#EXTINF:6.0,
audio_000.aac
#EXTINF:6.0,
audio_001.aac
#EXT-X-ENDLIST
"""
    )

    # Create segment files
    (output_dir / "audio_000.aac").write_bytes(b"fake audio data")
    (output_dir / "audio_001.aac").write_bytes(b"fake audio data")

    return playlist


@pytest.fixture
def subtitle_file(output_dir):
    """Create subtitle file."""
    output_dir.mkdir(parents=True, exist_ok=True)
    subtitle = output_dir / "subtitle_eng.vtt"
    subtitle.write_text(
        """WEBVTT

00:00:00.000 --> 00:00:05.000
First subtitle

00:00:05.000 --> 00:00:10.000
Second subtitle
"""
    )
    return subtitle


@pytest.fixture
def sprite_files(output_dir):
    """Create sprite files."""
    output_dir.mkdir(parents=True, exist_ok=True)
    sprite_img = output_dir / "sprites.jpg"
    sprite_vtt = output_dir / "sprites.vtt"

    sprite_img.write_bytes(b"fake sprite image data")
    sprite_vtt.write_text(
        """WEBVTT

00:00:00.000 --> 00:00:10.000
sprites.jpg#xywh=0,0,160,90

00:00:10.000 --> 00:00:20.000
sprites.jpg#xywh=160,0,160,90
"""
    )

    return sprite_img, sprite_vtt


@pytest.fixture
def metadata_file(output_dir):
    """Create metadata file."""
    output_dir.mkdir(parents=True, exist_ok=True)
    metadata = output_dir / "metadata.json"
    metadata.write_text(
        """{
    "version": "1.0",
    "master_playlist": "master.m3u8",
    "video": {
        "count": 1,
        "variants": []
    }
}"""
    )
    return metadata


@pytest.fixture
def complete_results(
    output_dir,
    master_playlist,
    video_playlist,
    audio_playlist,
    subtitle_file,
    sprite_files,
    metadata_file,
):
    """Create complete transcoding results."""
    sprite_img, sprite_vtt = sprite_files

    return TranscodingResults(
        video_variants=[
            VideoVariantResult(
                quality="1080p",
                width=1920,
                height=1080,
                bitrate="5000k",
                size=1024 * 1024 * 10,
                segment_count=2,
                duration=12.0,
                playlist_path=video_playlist,
            )
        ],
        audio_tracks=[
            AudioTrackResult(
                index=0,
                language="eng",
                codec="aac",
                size=1024 * 1024 * 2,
                playlist_path=audio_playlist,
            )
        ],
        subtitle_tracks=[
            SubtitleResult(
                index=0,
                language="eng",
                format="webvtt",
                file_path=subtitle_file,
            )
        ],
        sprite=SpriteResult(
            sprite_path=sprite_img,
            vtt_path=sprite_vtt,
            thumbnail_count=2,
            size=1024 * 100,
        ),
        master_playlist=master_playlist,
        metadata_file=metadata_file,
        total_size=1024 * 1024 * 12,
        total_duration=12.0,
    )


# === OutputValidator Tests ===


def test_output_validator_initialization(output_dir):
    """Test validator initialization."""
    validator = OutputValidator(output_dir)

    assert validator.output_dir == output_dir
    assert validator.logger is not None


def test_validate_complete_output(output_dir, complete_results):
    """Test validating complete output."""
    validator = OutputValidator(output_dir)
    result = validator.validate(complete_results)

    assert result.success is True
    assert result.has_errors is False
    assert result.master_playlist_valid is True
    assert result.all_segments_present is True
    assert result.audio_sync_valid is True
    assert result.subtitle_files_valid is True


def test_validate_missing_master_playlist(output_dir):
    """Test validation fails when master playlist missing."""
    results = TranscodingResults(master_playlist=output_dir / "nonexistent.m3u8")

    validator = OutputValidator(output_dir)
    result = validator.validate(results)

    assert result.success is False
    assert result.has_errors is True
    assert result.master_playlist_valid is False
    assert "Master playlist not found" in result.errors[0]


def test_validate_no_master_playlist_set(output_dir):
    """Test validation fails when master playlist not set."""
    results = TranscodingResults(master_playlist=None)

    validator = OutputValidator(output_dir)
    result = validator.validate(results)

    assert result.success is False
    assert result.master_playlist_valid is False
    assert "Master playlist path not set" in result.errors[0]


def test_validate_empty_master_playlist(output_dir):
    """Test validation fails when master playlist empty."""
    output_dir.mkdir(parents=True, exist_ok=True)
    master = output_dir / "master.m3u8"
    master.write_text("")  # Empty file

    results = TranscodingResults(master_playlist=master)

    validator = OutputValidator(output_dir)
    result = validator.validate(results)

    assert result.success is False
    assert "Master playlist is empty" in result.errors[0]


def test_validate_invalid_master_playlist(output_dir):
    """Test validation fails when master playlist invalid."""
    output_dir.mkdir(parents=True, exist_ok=True)
    master = output_dir / "master.m3u8"
    master.write_text("Invalid content without #EXTM3U")

    results = TranscodingResults(
        master_playlist=master,
        video_variants=[
            VideoVariantResult(
                quality="1080p",
                width=1920,
                height=1080,
                bitrate="5000k",
                size=1024,
                segment_count=1,
                duration=6.0,
                playlist_path=output_dir / "video.m3u8",
            )
        ],
    )

    validator = OutputValidator(output_dir)
    result = validator.validate(results)

    assert result.success is False
    assert any("#EXTM3U header" in err for err in result.errors)


def test_validate_video_variant_missing_playlist(output_dir, master_playlist):
    """Test validation fails when video playlist missing."""
    results = TranscodingResults(
        master_playlist=master_playlist,
        video_variants=[
            VideoVariantResult(
                quality="1080p",
                width=1920,
                height=1080,
                bitrate="5000k",
                size=1024,
                segment_count=1,
                duration=6.0,
                playlist_path=output_dir / "nonexistent.m3u8",
            )
        ],
    )

    validator = OutputValidator(output_dir)
    result = validator.validate(results)

    assert result.success is False
    assert result.all_segments_present is False
    assert any("Video variant playlist not found" in err for err in result.errors)


def test_validate_video_variant_missing_segments(output_dir, master_playlist):
    """Test validation fails when video segments missing."""
    output_dir.mkdir(parents=True, exist_ok=True)
    playlist = output_dir / "video_1080p.m3u8"
    playlist.write_text(
        """#EXTM3U
#EXTINF:6.0,
missing_segment.ts
"""
    )

    results = TranscodingResults(
        master_playlist=master_playlist,
        video_variants=[
            VideoVariantResult(
                quality="1080p",
                width=1920,
                height=1080,
                bitrate="5000k",
                size=1024,
                segment_count=1,
                duration=6.0,
                playlist_path=playlist,
            )
        ],
    )

    validator = OutputValidator(output_dir)
    result = validator.validate(results)

    assert result.success is False
    assert any("missing" in err.lower() and "segment" in err.lower() for err in result.errors)


def test_validate_audio_track_missing_playlist(output_dir, master_playlist):
    """Test validation fails when audio playlist missing."""
    results = TranscodingResults(
        master_playlist=master_playlist,
        audio_tracks=[
            AudioTrackResult(
                index=0,
                language="eng",
                codec="aac",
                size=1024,
                playlist_path=output_dir / "nonexistent.m3u8",
            )
        ],
    )

    validator = OutputValidator(output_dir)
    result = validator.validate(results)

    assert result.success is False
    assert result.audio_sync_valid is False
    assert any("Audio track playlist not found" in err for err in result.errors)


def test_validate_subtitle_missing_file(output_dir, master_playlist):
    """Test validation fails when subtitle file missing."""
    results = TranscodingResults(
        master_playlist=master_playlist,
        subtitle_tracks=[
            SubtitleResult(
                index=0,
                language="eng",
                format="webvtt",
                file_path=output_dir / "nonexistent.vtt",
            )
        ],
    )

    validator = OutputValidator(output_dir)
    result = validator.validate(results)

    assert result.success is False
    assert result.subtitle_files_valid is False
    assert any("Subtitle file not found" in err for err in result.errors)


def test_validate_subtitle_invalid_webvtt(output_dir, master_playlist):
    """Test validation fails when WebVTT subtitle invalid."""
    output_dir.mkdir(parents=True, exist_ok=True)
    subtitle = output_dir / "subtitle.vtt"
    subtitle.write_text("Invalid WebVTT without header")

    results = TranscodingResults(
        master_playlist=master_playlist,
        subtitle_tracks=[
            SubtitleResult(
                index=0,
                language="eng",
                format="webvtt",
                file_path=subtitle,
            )
        ],
    )

    validator = OutputValidator(output_dir)
    result = validator.validate(results)

    assert result.success is False
    assert any("WEBVTT header" in err for err in result.errors)


def test_validate_sprite_missing_image(output_dir, master_playlist):
    """Test validation fails when sprite image missing."""
    output_dir.mkdir(parents=True, exist_ok=True)
    vtt = output_dir / "sprites.vtt"
    vtt.write_text("WEBVTT\n")

    results = TranscodingResults(
        master_playlist=master_playlist,
        sprite=SpriteResult(
            sprite_path=output_dir / "nonexistent.jpg",
            vtt_path=vtt,
            thumbnail_count=1,
            size=1024,
        ),
    )

    validator = OutputValidator(output_dir)
    result = validator.validate(results)

    assert result.success is False
    assert any("Sprite image not found" in err for err in result.errors)


def test_validate_sprite_missing_vtt(output_dir, master_playlist):
    """Test validation fails when sprite VTT missing."""
    output_dir.mkdir(parents=True, exist_ok=True)
    sprite = output_dir / "sprites.jpg"
    sprite.write_bytes(b"fake image")

    results = TranscodingResults(
        master_playlist=master_playlist,
        sprite=SpriteResult(
            sprite_path=sprite,
            vtt_path=output_dir / "nonexistent.vtt",
            thumbnail_count=1,
            size=1024,
        ),
    )

    validator = OutputValidator(output_dir)
    result = validator.validate(results)

    assert result.success is False
    assert any("Sprite VTT file not found" in err for err in result.errors)


def test_validate_metadata_missing(output_dir, master_playlist):
    """Test warning when metadata file missing."""
    results = TranscodingResults(
        master_playlist=master_playlist,
        metadata_file=output_dir / "nonexistent.json",
    )

    validator = OutputValidator(output_dir)
    result = validator.validate(results)

    assert result.has_warnings is True
    assert any("Metadata file not found" in warn for warn in result.warnings)


def test_validate_metadata_invalid_json(output_dir, master_playlist):
    """Test warning when metadata JSON invalid."""
    output_dir.mkdir(parents=True, exist_ok=True)
    metadata = output_dir / "metadata.json"
    metadata.write_text("Invalid JSON {")

    results = TranscodingResults(
        master_playlist=master_playlist,
        metadata_file=metadata,
    )

    validator = OutputValidator(output_dir)
    result = validator.validate(results)

    assert result.has_warnings is True
    assert any("Invalid JSON" in warn for warn in result.warnings)


# === Playlist Syntax Validation Tests ===


def test_validate_playlist_syntax_success(output_dir):
    """Test playlist syntax validation success."""
    output_dir.mkdir(parents=True, exist_ok=True)
    playlist = output_dir / "test.m3u8"
    playlist.write_text(
        """#EXTM3U
#EXT-X-VERSION:3
#EXTINF:6.0,
segment.ts
#EXT-X-ENDLIST
"""
    )

    validator = OutputValidator(output_dir)
    result = validator.validate_playlist_syntax(playlist)

    assert result.success is True
    assert result.has_errors is False


def test_validate_playlist_syntax_missing_header(output_dir):
    """Test playlist syntax validation fails without header."""
    output_dir.mkdir(parents=True, exist_ok=True)
    playlist = output_dir / "test.m3u8"
    playlist.write_text("#EXTINF:6.0,\nsegment.ts")

    validator = OutputValidator(output_dir)
    result = validator.validate_playlist_syntax(playlist)

    assert result.success is False
    assert any("#EXTM3U header" in err for err in result.errors)


def test_validate_playlist_syntax_missing_endlist(output_dir):
    """Test playlist syntax validation warns without endlist."""
    output_dir.mkdir(parents=True, exist_ok=True)
    playlist = output_dir / "test.m3u8"
    playlist.write_text("#EXTM3U\n#EXTINF:6.0,\nsegment.ts")

    validator = OutputValidator(output_dir)
    result = validator.validate_playlist_syntax(playlist)

    assert result.success is True
    assert result.has_warnings is True
    assert any("EXT-X-ENDLIST" in warn for warn in result.warnings)


def test_validate_playlist_syntax_nonexistent(output_dir):
    """Test playlist syntax validation fails for nonexistent file."""
    validator = OutputValidator(output_dir)
    result = validator.validate_playlist_syntax(output_dir / "nonexistent.m3u8")

    assert result.success is False
    assert any("not found" in err for err in result.errors)


# === Segment Check Tests ===


def test_check_segments_complete_success(output_dir):
    """Test checking segments all present."""
    output_dir.mkdir(parents=True, exist_ok=True)
    playlist = output_dir / "test.m3u8"
    playlist.write_text(
        """#EXTM3U
#EXTINF:6.0,
segment_0.ts
#EXTINF:6.0,
segment_1.ts
"""
    )

    # Create segment files
    (output_dir / "segment_0.ts").write_bytes(b"data")
    (output_dir / "segment_1.ts").write_bytes(b"data")

    validator = OutputValidator(output_dir)
    all_present, found, missing = validator.check_segments_complete(playlist, expected_count=2)

    assert all_present is True
    assert found == 2
    assert missing == 0


def test_check_segments_missing(output_dir):
    """Test checking segments with missing files."""
    output_dir.mkdir(parents=True, exist_ok=True)
    playlist = output_dir / "test.m3u8"
    playlist.write_text(
        """#EXTM3U
#EXTINF:6.0,
segment_0.ts
#EXTINF:6.0,
missing_segment.ts
"""
    )

    # Create only one segment
    (output_dir / "segment_0.ts").write_bytes(b"data")

    validator = OutputValidator(output_dir)
    all_present, found, missing = validator.check_segments_complete(playlist)

    assert all_present is False
    assert found == 1
    assert missing == 1


def test_check_segments_nonexistent_playlist(output_dir):
    """Test checking segments for nonexistent playlist."""
    validator = OutputValidator(output_dir)
    all_present, found, missing = validator.check_segments_complete(output_dir / "nonexistent.m3u8")

    assert all_present is False
    assert found == 0
    assert missing == 0


# === Convenience Function Tests ===


def test_validate_output_convenience(output_dir, complete_results):
    """Test validate_output convenience function."""
    result = validate_output(output_dir, complete_results)

    assert result.success is True
    assert result.has_errors is False


def test_quick_validate_success(output_dir, master_playlist):
    """Test quick validation success."""
    is_valid = quick_validate(output_dir, master_playlist)

    assert is_valid is True


def test_quick_validate_missing_directory():
    """Test quick validation fails for missing directory."""
    is_valid = quick_validate(Path("/nonexistent"), Path("/nonexistent/master.m3u8"))

    assert is_valid is False


def test_quick_validate_missing_master_playlist(output_dir):
    """Test quick validation fails for missing master playlist."""
    output_dir.mkdir(parents=True, exist_ok=True)

    is_valid = quick_validate(output_dir, output_dir / "nonexistent.m3u8")

    assert is_valid is False


def test_quick_validate_empty_master_playlist(output_dir):
    """Test quick validation fails for empty master playlist."""
    output_dir.mkdir(parents=True, exist_ok=True)
    master = output_dir / "master.m3u8"
    master.write_text("")

    is_valid = quick_validate(output_dir, master)

    assert is_valid is False


def test_quick_validate_invalid_header(output_dir):
    """Test quick validation fails for invalid header."""
    output_dir.mkdir(parents=True, exist_ok=True)
    master = output_dir / "master.m3u8"
    master.write_text("Invalid content")

    is_valid = quick_validate(output_dir, master)

    assert is_valid is False


# === ValidationResult Tests ===


def test_validation_result_properties():
    """Test ValidationResult properties."""
    result = ValidationResult(success=True)

    assert result.has_errors is False
    assert result.has_warnings is False
    assert result.is_valid is True

    result.add_error("Test error")
    assert result.has_errors is True
    assert result.success is False
    assert result.is_valid is False

    result.add_warning("Test warning")
    assert result.has_warnings is True


def test_validation_result_add_methods():
    """Test ValidationResult add methods."""
    result = ValidationResult(success=True)

    result.add_error("Error 1")
    result.add_error("Error 2")
    assert len(result.errors) == 2

    result.add_warning("Warning 1")
    result.add_warning("Warning 2")
    assert len(result.warnings) == 2
