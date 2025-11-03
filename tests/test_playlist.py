"""
Tests for HLS playlist generation.
"""

import json
from pathlib import Path

import pytest

from hls_transcoder.playlist import (
    AudioTrackInfo,
    PlaylistConfig,
    PlaylistGenerator,
    SubtitleTrackInfo,
    VideoVariantInfo,
    create_audio_track_info,
    create_subtitle_track_info,
    create_video_variant_info,
    generate_playlists,
)


# === Fixtures ===


@pytest.fixture
def output_dir(tmp_path):
    """Create test output directory."""
    return tmp_path / "output"


@pytest.fixture
def video_variants(output_dir):
    """Create sample video variants."""
    variants = []
    qualities = [
        ("1080p", 1920, 1080, 5000),
        ("720p", 1280, 720, 3000),
        ("480p", 854, 480, 1500),
    ]

    for quality, width, height, bitrate in qualities:
        playlist_path = output_dir / f"video_{quality}.m3u8"
        playlist_path.parent.mkdir(parents=True, exist_ok=True)
        playlist_path.write_text("#EXTM3U\n#EXT-X-ENDLIST\n")

        variants.append(
            VideoVariantInfo(
                quality=quality,
                width=width,
                height=height,
                bitrate=bitrate,
                framerate=30.0,
                codecs="avc1.640028,mp4a.40.2",
                playlist_path=playlist_path,
                segment_count=100,
            )
        )

    return variants


@pytest.fixture
def audio_tracks(output_dir):
    """Create sample audio tracks."""
    tracks = []
    languages = [("eng", True), ("spa", False), ("fre", False)]

    for lang, is_default in languages:
        playlist_path = output_dir / f"audio_{lang}.m3u8"
        playlist_path.parent.mkdir(parents=True, exist_ok=True)
        playlist_path.write_text("#EXTM3U\n#EXT-X-ENDLIST\n")

        tracks.append(
            AudioTrackInfo(
                name=f"{lang.upper()} Audio",
                language=lang,
                channels=2,
                sample_rate=48000,
                bitrate=128,
                codecs="mp4a.40.2",
                playlist_path=playlist_path,
                is_default=is_default,
            )
        )

    return tracks


@pytest.fixture
def subtitle_tracks(output_dir):
    """Create sample subtitle tracks."""
    tracks = []
    languages = [("eng", True, False), ("spa", False, False), ("eng", False, True)]

    for i, (lang, is_default, forced) in enumerate(languages):
        file_path = output_dir / f"subtitle_{lang}_{i}.vtt"
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text("WEBVTT\n")

        name = f"{lang.upper()} Subtitles"
        if forced:
            name += " (Forced)"

        tracks.append(
            SubtitleTrackInfo(
                name=name,
                language=lang,
                file_path=file_path,
                is_default=is_default,
                forced=forced,
            )
        )

    return tracks


# === VideoVariantInfo Tests ===


def test_video_variant_info_creation():
    """Test creating video variant info."""
    variant = VideoVariantInfo(
        quality="1080p",
        width=1920,
        height=1080,
        bitrate=5000,
        framerate=30.0,
        codecs="avc1.640028,mp4a.40.2",
        playlist_path=Path("video_1080p.m3u8"),
        segment_count=100,
    )

    assert variant.quality == "1080p"
    assert variant.width == 1920
    assert variant.height == 1080
    assert variant.bitrate == 5000
    assert variant.bandwidth == 5000000
    assert variant.resolution == "1920x1080"


def test_create_video_variant_info_h264():
    """Test creating video variant info with h264 codec."""
    variant = create_video_variant_info(
        quality="720p",
        width=1280,
        height=720,
        bitrate=3000,
        framerate=24.0,
        playlist_path=Path("video.m3u8"),
        segment_count=50,
        codec="h264",
    )

    assert variant.quality == "720p"
    assert variant.codecs == "avc1.640028,mp4a.40.2"


def test_create_video_variant_info_hevc():
    """Test creating video variant info with hevc codec."""
    variant = create_video_variant_info(
        quality="1080p",
        width=1920,
        height=1080,
        bitrate=4000,
        framerate=30.0,
        playlist_path=Path("video.m3u8"),
        segment_count=100,
        codec="hevc",
    )

    assert variant.codecs == "hvc1.1.6.L120.90,mp4a.40.2"


# === AudioTrackInfo Tests ===


def test_audio_track_info_creation():
    """Test creating audio track info."""
    track = AudioTrackInfo(
        name="English Audio",
        language="eng",
        channels=2,
        sample_rate=48000,
        bitrate=128,
        codecs="mp4a.40.2",
        playlist_path=Path("audio_eng.m3u8"),
        is_default=True,
    )

    assert track.name == "English Audio"
    assert track.language == "eng"
    assert track.channels == 2
    assert track.bandwidth == 128000
    assert track.group_id == "audio"
    assert track.channel_layout == "STEREO"
    assert track.is_default is True


def test_audio_channel_layouts():
    """Test audio channel layout descriptions."""
    layouts = [
        (1, "MONO"),
        (2, "STEREO"),
        (6, "5.1"),
        (8, "7.1"),
        (4, "4CH"),
    ]

    for channels, expected_layout in layouts:
        track = AudioTrackInfo(
            name="Test",
            language="eng",
            channels=channels,
            sample_rate=48000,
            bitrate=128,
            codecs="mp4a.40.2",
            playlist_path=Path("audio.m3u8"),
        )
        assert track.channel_layout == expected_layout


def test_create_audio_track_info():
    """Test creating audio track info helper."""
    track = create_audio_track_info(
        name="Spanish Audio",
        language="spa",
        channels=2,
        sample_rate=48000,
        bitrate=128,
        playlist_path=Path("audio_spa.m3u8"),
        is_default=False,
        codec="aac",
    )

    assert track.name == "Spanish Audio"
    assert track.codecs == "mp4a.40.2"


# === SubtitleTrackInfo Tests ===


def test_subtitle_track_info_creation():
    """Test creating subtitle track info."""
    track = SubtitleTrackInfo(
        name="English Subtitles",
        language="eng",
        file_path=Path("subtitle_eng.vtt"),
        is_default=True,
        forced=False,
    )

    assert track.name == "English Subtitles"
    assert track.language == "eng"
    assert track.group_id == "subtitles"
    assert track.is_default is True
    assert track.forced is False


def test_create_subtitle_track_info():
    """Test creating subtitle track info helper."""
    track = create_subtitle_track_info(
        name="Spanish Subtitles",
        language="spa",
        file_path=Path("subtitle_spa.vtt"),
        is_default=False,
        forced=True,
    )

    assert track.name == "Spanish Subtitles"
    assert track.forced is True


# === PlaylistGenerator Tests ===


def test_playlist_generator_initialization(output_dir):
    """Test playlist generator initialization."""
    generator = PlaylistGenerator(output_dir)

    assert generator.output_dir == output_dir
    assert output_dir.exists()
    assert generator.config.output_dir == output_dir


def test_playlist_generator_with_config(output_dir):
    """Test playlist generator with custom config."""
    config = PlaylistConfig(
        output_dir=output_dir,
        segment_duration=10,
        version=6,
    )
    generator = PlaylistGenerator(output_dir, config)

    assert generator.config.segment_duration == 10
    assert generator.config.version == 6


def test_generate_master_playlist_video_only(output_dir, video_variants):
    """Test generating master playlist with video only."""
    generator = PlaylistGenerator(output_dir)
    master_path = generator.generate_master_playlist(video_variants)

    assert master_path.exists()
    assert master_path.name == "master.m3u8"

    content = master_path.read_text()
    assert "#EXTM3U" in content
    assert "#EXT-X-VERSION:" in content
    assert "#EXT-X-STREAM-INF:" in content
    assert "video_1080p.m3u8" in content
    assert "video_720p.m3u8" in content
    assert "video_480p.m3u8" in content


def test_generate_master_playlist_with_audio(output_dir, video_variants, audio_tracks):
    """Test generating master playlist with audio tracks."""
    generator = PlaylistGenerator(output_dir)
    master_path = generator.generate_master_playlist(
        video_variants=video_variants,
        audio_tracks=audio_tracks,
    )

    content = master_path.read_text()
    assert "#EXT-X-MEDIA:TYPE=AUDIO" in content
    assert 'LANGUAGE="eng"' in content
    assert "DEFAULT=YES" in content
    assert "DEFAULT=NO" in content
    assert "audio_eng.m3u8" in content


def test_generate_master_playlist_with_subtitles(output_dir, video_variants, subtitle_tracks):
    """Test generating master playlist with subtitles."""
    generator = PlaylistGenerator(output_dir)
    master_path = generator.generate_master_playlist(
        video_variants=video_variants,
        subtitle_tracks=subtitle_tracks,
    )

    content = master_path.read_text()
    assert "#EXT-X-MEDIA:TYPE=SUBTITLES" in content
    assert 'LANGUAGE="eng"' in content
    assert "subtitle_eng" in content


def test_generate_master_playlist_complete(
    output_dir, video_variants, audio_tracks, subtitle_tracks
):
    """Test generating complete master playlist."""
    generator = PlaylistGenerator(output_dir)
    master_path = generator.generate_master_playlist(
        video_variants=video_variants,
        audio_tracks=audio_tracks,
        subtitle_tracks=subtitle_tracks,
    )

    content = master_path.read_text()

    # Check structure
    lines = [line.strip() for line in content.split("\n") if line.strip()]
    assert lines[0] == "#EXTM3U"

    # Check audio present
    assert any("TYPE=AUDIO" in line for line in lines)

    # Check subtitles present
    assert any("TYPE=SUBTITLES" in line for line in lines)

    # Check video variants present
    assert any("EXT-X-STREAM-INF:" in line for line in lines)

    # Check audio and subtitle groups referenced in video variants
    assert any('AUDIO="audio"' in line for line in lines)
    assert any('SUBTITLES="subtitles"' in line for line in lines)


def test_generate_master_playlist_no_variants_raises_error(output_dir):
    """Test that generating playlist without variants raises error."""
    generator = PlaylistGenerator(output_dir)

    with pytest.raises(ValueError, match="At least one video variant is required"):
        generator.generate_master_playlist([])


def test_generate_master_playlist_variants_sorted_by_bitrate(output_dir):
    """Test that variants are sorted by bitrate (highest first)."""
    # Create variants in random order
    variants = [
        VideoVariantInfo(
            quality="480p",
            width=854,
            height=480,
            bitrate=1500,
            framerate=30.0,
            codecs="avc1.640028,mp4a.40.2",
            playlist_path=output_dir / "video_480p.m3u8",
            segment_count=50,
        ),
        VideoVariantInfo(
            quality="1080p",
            width=1920,
            height=1080,
            bitrate=5000,
            framerate=30.0,
            codecs="avc1.640028,mp4a.40.2",
            playlist_path=output_dir / "video_1080p.m3u8",
            segment_count=100,
        ),
        VideoVariantInfo(
            quality="720p",
            width=1280,
            height=720,
            bitrate=3000,
            framerate=30.0,
            codecs="avc1.640028,mp4a.40.2",
            playlist_path=output_dir / "video_720p.m3u8",
            segment_count=75,
        ),
    ]

    # Create playlist files
    for variant in variants:
        variant.playlist_path.parent.mkdir(parents=True, exist_ok=True)
        variant.playlist_path.write_text("#EXTM3U\n")

    generator = PlaylistGenerator(output_dir)
    master_path = generator.generate_master_playlist(variants)

    content = master_path.read_text()
    lines = content.split("\n")

    # Find variant lines
    variant_lines = []
    for i, line in enumerate(lines):
        if line.startswith("#EXT-X-STREAM-INF:"):
            if i + 1 < len(lines):
                variant_lines.append(lines[i + 1])

    # Should be ordered: 1080p, 720p, 480p
    assert variant_lines[0].endswith("video_1080p.m3u8")
    assert variant_lines[1].endswith("video_720p.m3u8")
    assert variant_lines[2].endswith("video_480p.m3u8")


def test_generate_metadata(output_dir, video_variants, audio_tracks, subtitle_tracks):
    """Test generating metadata file."""
    generator = PlaylistGenerator(output_dir)

    source_info = {
        "filename": "input.mp4",
        "duration": 600.0,
        "size": 1024 * 1024 * 100,
    }

    transcoding_info = {
        "hardware": "NVIDIA NVENC",
        "duration": 120.5,
        "parallel_jobs": 4,
    }

    metadata_path = generator.generate_metadata(
        video_variants=video_variants,
        audio_tracks=audio_tracks,
        subtitle_tracks=subtitle_tracks,
        source_info=source_info,
        transcoding_info=transcoding_info,
    )

    assert metadata_path.exists()
    assert metadata_path.name == "metadata.json"

    # Parse and validate metadata
    with metadata_path.open() as f:
        metadata = json.load(f)

    assert metadata["version"] == "1.0"
    assert metadata["master_playlist"] == "master.m3u8"

    # Check video section
    assert "video" in metadata
    assert metadata["video"]["count"] == 3
    assert len(metadata["video"]["variants"]) == 3

    # Check audio section
    assert "audio" in metadata
    assert metadata["audio"]["count"] == 3
    assert len(metadata["audio"]["tracks"]) == 3

    # Check subtitles section
    assert "subtitles" in metadata
    assert metadata["subtitles"]["count"] == 3
    assert len(metadata["subtitles"]["tracks"]) == 3

    # Check source info
    assert "source" in metadata
    assert metadata["source"]["filename"] == "input.mp4"

    # Check transcoding info
    assert "transcoding" in metadata
    assert metadata["transcoding"]["hardware"] == "NVIDIA NVENC"


def test_generate_metadata_video_only(output_dir, video_variants):
    """Test generating metadata with video only."""
    generator = PlaylistGenerator(output_dir)
    metadata_path = generator.generate_metadata(video_variants=video_variants)

    with metadata_path.open() as f:
        metadata = json.load(f)

    assert "video" in metadata
    assert "audio" not in metadata
    assert "subtitles" not in metadata


def test_validate_playlists_success(output_dir, video_variants):
    """Test validating playlists successfully."""
    generator = PlaylistGenerator(output_dir)
    generator.generate_master_playlist(video_variants)

    is_valid, errors = generator.validate_playlists()

    assert is_valid is True
    assert len(errors) == 0


def test_validate_playlists_missing_master(output_dir):
    """Test validation fails when master playlist missing."""
    generator = PlaylistGenerator(output_dir)

    is_valid, errors = generator.validate_playlists()

    assert is_valid is False
    assert "Master playlist (master.m3u8) not found" in errors


def test_validate_playlists_missing_variant_playlist(output_dir):
    """Test validation fails when variant playlist missing."""
    # Create variant with non-existent playlist
    variant = VideoVariantInfo(
        quality="1080p",
        width=1920,
        height=1080,
        bitrate=5000,
        framerate=30.0,
        codecs="avc1.640028,mp4a.40.2",
        playlist_path=output_dir / "nonexistent.m3u8",
        segment_count=100,
    )

    generator = PlaylistGenerator(output_dir)
    generator.generate_master_playlist([variant])

    is_valid, errors = generator.validate_playlists()

    assert is_valid is False
    assert any("Referenced playlist not found" in error for error in errors)


# === Convenience Function Tests ===


def test_generate_playlists_convenience(output_dir, video_variants, audio_tracks, subtitle_tracks):
    """Test convenience function for generating playlists."""
    master_path, metadata_path = generate_playlists(
        output_dir=output_dir,
        video_variants=video_variants,
        audio_tracks=audio_tracks,
        subtitle_tracks=subtitle_tracks,
    )

    assert master_path.exists()
    assert metadata_path.exists()
    assert master_path.name == "master.m3u8"
    assert metadata_path.name == "metadata.json"


def test_generate_playlists_with_info(output_dir, video_variants):
    """Test convenience function with source and transcoding info."""
    source_info = {"filename": "test.mp4"}
    transcoding_info = {"hardware": "software"}

    master_path, metadata_path = generate_playlists(
        output_dir=output_dir,
        video_variants=video_variants,
        source_info=source_info,
        transcoding_info=transcoding_info,
    )

    with metadata_path.open() as f:
        metadata = json.load(f)

    assert "source" in metadata
    assert "transcoding" in metadata


# === Multiple Audio/Subtitle Tracks Tests ===


def test_multiple_audio_tracks_different_languages(output_dir, video_variants):
    """Test playlist with multiple audio tracks in different languages."""
    # Create audio tracks for different languages
    audio_tracks = [
        create_audio_track_info(
            name="English",
            language="eng",
            channels=2,
            sample_rate=48000,
            bitrate=128,
            playlist_path=output_dir / "audio_eng/eng_128k.m3u8",
            is_default=True,
        ),
        create_audio_track_info(
            name="Spanish",
            language="spa",
            channels=2,
            sample_rate=48000,
            bitrate=128,
            playlist_path=output_dir / "audio_spa/spa_128k.m3u8",
            is_default=False,
        ),
        create_audio_track_info(
            name="French",
            language="fra",
            channels=2,
            sample_rate=48000,
            bitrate=128,
            playlist_path=output_dir / "audio_fra/fra_128k.m3u8",
            is_default=False,
        ),
        create_audio_track_info(
            name="Hindi 5.1",
            language="hin",
            channels=6,
            sample_rate=48000,
            bitrate=192,
            playlist_path=output_dir / "audio_hin/hin_192k.m3u8",
            is_default=False,
        ),
    ]

    # Create playlist files
    for track in audio_tracks:
        track.playlist_path.parent.mkdir(parents=True, exist_ok=True)
        track.playlist_path.write_text("#EXTM3U\n#EXT-X-ENDLIST\n")

    for variant in video_variants:
        variant.playlist_path.parent.mkdir(parents=True, exist_ok=True)
        variant.playlist_path.write_text("#EXTM3U\n#EXT-X-ENDLIST\n")

    generator = PlaylistGenerator(output_dir)
    master_path = generator.generate_master_playlist(
        video_variants=video_variants,
        audio_tracks=audio_tracks,
    )

    content = master_path.read_text()
    lines = content.split("\n")

    # Count audio entries
    audio_entries = [l for l in lines if "TYPE=AUDIO" in l]
    assert len(audio_entries) == 4, "Should have 4 audio tracks"

    # Verify all audio tracks use the same GROUP-ID="audio"
    for entry in audio_entries:
        assert 'GROUP-ID="audio"' in entry, "All audio tracks must use group 'audio'"

    # Verify languages are present
    assert 'LANGUAGE="eng"' in content
    assert 'LANGUAGE="spa"' in content
    assert 'LANGUAGE="fra"' in content
    assert 'LANGUAGE="hin"' in content

    # Verify only first track is default
    default_count = sum(1 for entry in audio_entries if "DEFAULT=YES" in entry)
    assert default_count == 1, "Only one audio track should be default"

    # Verify video variants reference the audio group
    stream_inf_lines = [l for l in lines if l.startswith("#EXT-X-STREAM-INF:")]
    for stream_inf in stream_inf_lines:
        assert 'AUDIO="audio"' in stream_inf, "Video variants must reference audio group"


def test_multiple_audio_tracks_same_language_different_bitrates(output_dir, video_variants):
    """Test playlist with multiple bitrates for the same language."""
    # Create multiple bitrates for English
    audio_tracks = [
        create_audio_track_info(
            name="English 96k",
            language="eng",
            channels=2,
            sample_rate=48000,
            bitrate=96,
            playlist_path=output_dir / "audio_eng/eng_96k.m3u8",
            is_default=False,
        ),
        create_audio_track_info(
            name="English 128k",
            language="eng",
            channels=2,
            sample_rate=48000,
            bitrate=128,
            playlist_path=output_dir / "audio_eng/eng_128k.m3u8",
            is_default=True,
        ),
        create_audio_track_info(
            name="English 192k",
            language="eng",
            channels=2,
            sample_rate=48000,
            bitrate=192,
            playlist_path=output_dir / "audio_eng/eng_192k.m3u8",
            is_default=False,
        ),
    ]

    # Create playlist files
    for track in audio_tracks:
        track.playlist_path.parent.mkdir(parents=True, exist_ok=True)
        track.playlist_path.write_text("#EXTM3U\n#EXT-X-ENDLIST\n")

    for variant in video_variants:
        variant.playlist_path.parent.mkdir(parents=True, exist_ok=True)
        variant.playlist_path.write_text("#EXTM3U\n#EXT-X-ENDLIST\n")

    generator = PlaylistGenerator(output_dir)
    master_path = generator.generate_master_playlist(
        video_variants=video_variants,
        audio_tracks=audio_tracks,
    )

    content = master_path.read_text()
    lines = content.split("\n")

    # Count audio entries with same language
    audio_entries = [l for l in lines if "TYPE=AUDIO" in l]
    eng_entries = [l for l in audio_entries if 'LANGUAGE="eng"' in l]

    assert len(eng_entries) == 3, "Should have 3 English audio tracks at different bitrates"

    # Verify all use the same group ID
    for entry in eng_entries:
        assert 'GROUP-ID="audio"' in entry

    # Verify names are different (to distinguish bitrates)
    names = []
    for entry in eng_entries:
        if 'NAME="' in entry:
            start = entry.find('NAME="') + 6
            end = entry.find('"', start)
            names.append(entry[start:end])

    assert len(names) == len(set(names)), "Track names should be unique"
    assert "English 128k" in names, "Track names should include bitrate"


def test_multiple_subtitle_tracks(output_dir, video_variants):
    """Test playlist with multiple subtitle tracks."""
    # Create subtitle tracks
    subtitle_tracks = [
        create_subtitle_track_info(
            name="English",
            language="eng",
            file_path=output_dir / "subtitles/eng.vtt",
            is_default=True,
            forced=False,
        ),
        create_subtitle_track_info(
            name="Spanish",
            language="spa",
            file_path=output_dir / "subtitles/spa.vtt",
            is_default=False,
            forced=False,
        ),
        create_subtitle_track_info(
            name="French (Forced)",
            language="fra",
            file_path=output_dir / "subtitles/fra_forced.vtt",
            is_default=False,
            forced=True,
        ),
        create_subtitle_track_info(
            name="German",
            language="deu",
            file_path=output_dir / "subtitles/deu.vtt",
            is_default=False,
            forced=False,
        ),
    ]

    # Create subtitle files
    for track in subtitle_tracks:
        track.file_path.parent.mkdir(parents=True, exist_ok=True)
        track.file_path.write_text("WEBVTT\n")

    for variant in video_variants:
        variant.playlist_path.parent.mkdir(parents=True, exist_ok=True)
        variant.playlist_path.write_text("#EXTM3U\n#EXT-X-ENDLIST\n")

    generator = PlaylistGenerator(output_dir)
    master_path = generator.generate_master_playlist(
        video_variants=video_variants,
        subtitle_tracks=subtitle_tracks,
    )

    content = master_path.read_text()
    lines = content.split("\n")

    # Count subtitle entries
    subtitle_entries = [l for l in lines if "TYPE=SUBTITLES" in l]
    assert len(subtitle_entries) == 4, "Should have 4 subtitle tracks"

    # Verify all subtitles use the same GROUP-ID="subtitles"
    for entry in subtitle_entries:
        assert 'GROUP-ID="subtitles"' in entry, "All subtitle tracks must use group 'subtitles'"

    # Verify languages
    assert 'LANGUAGE="eng"' in content
    assert 'LANGUAGE="spa"' in content
    assert 'LANGUAGE="fra"' in content
    assert 'LANGUAGE="deu"' in content

    # Verify forced flag
    forced_entries = [e for e in subtitle_entries if "FORCED=YES" in e]
    assert len(forced_entries) == 1, "Should have exactly one forced subtitle"

    # Verify video variants reference the subtitle group
    stream_inf_lines = [l for l in lines if l.startswith("#EXT-X-STREAM-INF:")]
    for stream_inf in stream_inf_lines:
        assert 'SUBTITLES="subtitles"' in stream_inf, "Video variants must reference subtitle group"


def test_audio_tracks_sorting(output_dir, video_variants):
    """Test that audio tracks are sorted correctly (default first, then by language, then bitrate)."""
    # Create audio tracks in random order
    audio_tracks = [
        create_audio_track_info(
            name="French 96k",
            language="fra",
            channels=2,
            sample_rate=48000,
            bitrate=96,
            playlist_path=output_dir / "audio_fra/fra_96k.m3u8",
            is_default=False,
        ),
        create_audio_track_info(
            name="English 128k",
            language="eng",
            channels=2,
            sample_rate=48000,
            bitrate=128,
            playlist_path=output_dir / "audio_eng/eng_128k.m3u8",
            is_default=True,  # Default track
        ),
        create_audio_track_info(
            name="English 192k",
            language="eng",
            channels=2,
            sample_rate=48000,
            bitrate=192,
            playlist_path=output_dir / "audio_eng/eng_192k.m3u8",
            is_default=False,
        ),
        create_audio_track_info(
            name="French 128k",
            language="fra",
            channels=2,
            sample_rate=48000,
            bitrate=128,
            playlist_path=output_dir / "audio_fra/fra_128k.m3u8",
            is_default=False,
        ),
    ]

    # Create files
    for track in audio_tracks:
        track.playlist_path.parent.mkdir(parents=True, exist_ok=True)
        track.playlist_path.write_text("#EXTM3U\n")

    for variant in video_variants:
        variant.playlist_path.parent.mkdir(parents=True, exist_ok=True)
        variant.playlist_path.write_text("#EXTM3U\n")

    generator = PlaylistGenerator(output_dir)
    master_path = generator.generate_master_playlist(
        video_variants=video_variants,
        audio_tracks=audio_tracks,
    )

    content = master_path.read_text()
    lines = content.split("\n")

    # Extract audio entry order
    audio_entries = [l for l in lines if "TYPE=AUDIO" in l]

    # First entry should be default
    assert "DEFAULT=YES" in audio_entries[0], "First audio track should be default"
    assert 'LANGUAGE="eng"' in audio_entries[0], "Default track should be English"


def test_validate_audio_tracks_no_default(output_dir):
    """Test validation warns when no default audio track."""
    audio_tracks = [
        create_audio_track_info(
            name="English",
            language="eng",
            channels=2,
            sample_rate=48000,
            bitrate=128,
            playlist_path=output_dir / "audio.m3u8",
            is_default=False,  # No default
        ),
    ]

    generator = PlaylistGenerator(output_dir)
    is_valid, warnings = generator.validate_audio_tracks(audio_tracks)

    assert not is_valid
    assert any("No audio track marked as default" in w for w in warnings)


def test_validate_audio_tracks_multiple_defaults(output_dir):
    """Test validation warns when multiple default audio tracks."""
    audio_tracks = [
        create_audio_track_info(
            name="English",
            language="eng",
            channels=2,
            sample_rate=48000,
            bitrate=128,
            playlist_path=output_dir / "audio_eng.m3u8",
            is_default=True,
        ),
        create_audio_track_info(
            name="Spanish",
            language="spa",
            channels=2,
            sample_rate=48000,
            bitrate=128,
            playlist_path=output_dir / "audio_spa.m3u8",
            is_default=True,  # Also default
        ),
    ]

    generator = PlaylistGenerator(output_dir)
    is_valid, warnings = generator.validate_audio_tracks(audio_tracks)

    assert not is_valid
    assert any("Multiple audio tracks marked as default" in w for w in warnings)


def test_validate_audio_tracks_duplicates(output_dir):
    """Test validation warns about duplicate audio tracks."""
    audio_tracks = [
        create_audio_track_info(
            name="English",
            language="eng",
            channels=2,
            sample_rate=48000,
            bitrate=128,
            playlist_path=output_dir / "audio1.m3u8",
            is_default=True,
        ),
        create_audio_track_info(
            name="English Duplicate",
            language="eng",  # Same language
            channels=2,  # Same channels
            sample_rate=48000,
            bitrate=128,  # Same bitrate
            playlist_path=output_dir / "audio2.m3u8",
            is_default=False,
        ),
    ]

    generator = PlaylistGenerator(output_dir)
    is_valid, warnings = generator.validate_audio_tracks(audio_tracks)

    assert not is_valid
    assert any("Duplicate audio track" in w for w in warnings)


def test_validate_audio_tracks_undefined_language(output_dir):
    """Test validation warns about undefined language codes."""
    audio_tracks = [
        create_audio_track_info(
            name="Unknown Language",
            language="und",  # Undefined
            channels=2,
            sample_rate=48000,
            bitrate=128,
            playlist_path=output_dir / "audio.m3u8",
            is_default=True,
        ),
    ]

    generator = PlaylistGenerator(output_dir)
    is_valid, warnings = generator.validate_audio_tracks(audio_tracks)

    assert not is_valid
    assert any("undefined language code (und)" in w for w in warnings)


def test_validate_subtitle_tracks_duplicates(output_dir):
    """Test validation warns about duplicate subtitle languages."""
    subtitle_tracks = [
        create_subtitle_track_info(
            name="English",
            language="eng",
            file_path=output_dir / "sub1.vtt",
            is_default=True,
        ),
        create_subtitle_track_info(
            name="English SDH",
            language="eng",  # Same language
            file_path=output_dir / "sub2.vtt",
            is_default=False,
        ),
    ]

    # Create files
    for track in subtitle_tracks:
        track.file_path.parent.mkdir(parents=True, exist_ok=True)
        track.file_path.write_text("WEBVTT\n")

    generator = PlaylistGenerator(output_dir)
    is_valid, warnings = generator.validate_subtitle_tracks(subtitle_tracks)

    assert not is_valid
    assert any("Duplicate subtitle language" in w for w in warnings)


def test_validate_subtitle_tracks_missing_file(output_dir):
    """Test validation warns about missing subtitle files."""
    subtitle_tracks = [
        create_subtitle_track_info(
            name="English",
            language="eng",
            file_path=output_dir / "nonexistent.vtt",  # Does not exist
            is_default=True,
        ),
    ]

    generator = PlaylistGenerator(output_dir)
    is_valid, warnings = generator.validate_subtitle_tracks(subtitle_tracks)

    assert not is_valid
    assert any("Subtitle file not found" in w for w in warnings)


def test_complex_multi_track_scenario(output_dir):
    """Test complex scenario with multiple video variants, audio tracks, and subtitles."""
    # Create comprehensive set of variants
    video_variants = [
        create_video_variant_info(
            quality="1080p",
            width=1920,
            height=1080,
            bitrate=5000,
            framerate=30.0,
            playlist_path=output_dir / "video_1080p/1080p.m3u8",
            segment_count=100,
        ),
        create_video_variant_info(
            quality="720p",
            width=1280,
            height=720,
            bitrate=3000,
            framerate=30.0,
            playlist_path=output_dir / "video_720p/720p.m3u8",
            segment_count=100,
        ),
        create_video_variant_info(
            quality="480p",
            width=854,
            height=480,
            bitrate=1500,
            framerate=30.0,
            playlist_path=output_dir / "video_480p/480p.m3u8",
            segment_count=100,
        ),
    ]

    # Multiple languages with multiple bitrates
    audio_tracks = [
        create_audio_track_info(
            name="English 192k",
            language="eng",
            channels=2,
            sample_rate=48000,
            bitrate=192,
            playlist_path=output_dir / "audio_eng/eng_192k.m3u8",
            is_default=True,
        ),
        create_audio_track_info(
            name="English 128k",
            language="eng",
            channels=2,
            sample_rate=48000,
            bitrate=128,
            playlist_path=output_dir / "audio_eng/eng_128k.m3u8",
            is_default=False,
        ),
        create_audio_track_info(
            name="Spanish 128k",
            language="spa",
            channels=2,
            sample_rate=48000,
            bitrate=128,
            playlist_path=output_dir / "audio_spa/spa_128k.m3u8",
            is_default=False,
        ),
        create_audio_track_info(
            name="Hindi 5.1",
            language="hin",
            channels=6,
            sample_rate=48000,
            bitrate=192,
            playlist_path=output_dir / "audio_hin/hin_192k.m3u8",
            is_default=False,
        ),
    ]

    subtitle_tracks = [
        create_subtitle_track_info(
            name="English",
            language="eng",
            file_path=output_dir / "subtitles/eng.vtt",
            is_default=True,
        ),
        create_subtitle_track_info(
            name="Spanish",
            language="spa",
            file_path=output_dir / "subtitles/spa.vtt",
            is_default=False,
        ),
    ]

    # Create all files
    for variant in video_variants:
        variant.playlist_path.parent.mkdir(parents=True, exist_ok=True)
        variant.playlist_path.write_text("#EXTM3U\n#EXT-X-ENDLIST\n")

    for track in audio_tracks:
        track.playlist_path.parent.mkdir(parents=True, exist_ok=True)
        track.playlist_path.write_text("#EXTM3U\n#EXT-X-ENDLIST\n")

    for track in subtitle_tracks:
        track.file_path.parent.mkdir(parents=True, exist_ok=True)
        track.file_path.write_text("WEBVTT\n")

    # Validate tracks
    generator = PlaylistGenerator(output_dir)
    audio_valid, audio_warnings = generator.validate_audio_tracks(audio_tracks)
    sub_valid, sub_warnings = generator.validate_subtitle_tracks(subtitle_tracks)

    assert audio_valid, f"Audio validation failed: {audio_warnings}"
    assert sub_valid, f"Subtitle validation failed: {sub_warnings}"

    # Generate playlists
    master_path, metadata_path = generate_playlists(
        output_dir=output_dir,
        video_variants=video_variants,
        audio_tracks=audio_tracks,
        subtitle_tracks=subtitle_tracks,
        source_info={"filename": "test.mp4", "duration": 600.0},
    )

    # Validate structure
    is_valid, errors = generator.validate_playlists()
    assert is_valid, f"Playlist validation failed: {errors}"

    # Parse and verify content
    content = master_path.read_text()
    lines = content.split("\n")

    # Verify counts
    audio_entries = [l for l in lines if "TYPE=AUDIO" in l]
    subtitle_entries = [l for l in lines if "TYPE=SUBTITLES" in l]
    video_entries = [l for l in lines if l.startswith("#EXT-X-STREAM-INF:")]

    assert len(audio_entries) == 4, "Should have 4 audio tracks"
    assert len(subtitle_entries) == 2, "Should have 2 subtitle tracks"
    assert len(video_entries) == 3, "Should have 3 video variants"

    # Verify metadata
    with metadata_path.open() as f:
        metadata = json.load(f)

    assert metadata["video"]["count"] == 3
    assert metadata["audio"]["count"] == 4
    assert metadata["subtitles"]["count"] == 2
