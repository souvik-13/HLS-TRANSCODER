"""
Integration tests using actual fixture MKV file.

These tests process the real video file in tests/fixtures/ and create actual outputs.
WARNING: These tests take longer to run as they perform real transcoding operations.
"""

import asyncio
import json
from pathlib import Path
from typing import List, Optional

import pytest

from hls_transcoder.inspector import MediaInspector
from hls_transcoder.hardware.detector import HardwareDetector
from hls_transcoder.transcoder.video import VideoTranscoder, QUALITY_PRESETS
from hls_transcoder.transcoder.audio import AudioExtractor, AUDIO_QUALITY_PRESETS
from hls_transcoder.transcoder.subtitle import SubtitleExtractor, extract_all_subtitles
from hls_transcoder.sprites.generator import SpriteGenerator, SpriteConfig
from hls_transcoder.playlist.generator import PlaylistGenerator
from hls_transcoder.validator.checker import OutputValidator
from hls_transcoder.models import AudioStream, SubtitleStream
from hls_transcoder.utils import MediaInspectionError, TranscodingError


# Path to the actual fixture file
FIXTURE_FILE = Path(__file__).parent / "fixtures" / "Hostel Daze S02 Complete (2021).mkv"


@pytest.fixture
def fixture_video():
    """Get path to fixture video file."""
    if not FIXTURE_FILE.exists():
        pytest.skip(f"Fixture file not found: {FIXTURE_FILE}")
    return FIXTURE_FILE


@pytest.fixture
def output_dir(tmp_path):
    """Create output directory for integration tests."""
    output = tmp_path / "integration_output"
    output.mkdir(exist_ok=True)
    return output


@pytest.fixture
async def media_info(fixture_video):
    """Inspect the fixture video file."""
    inspector = MediaInspector()
    info = await inspector.inspect(fixture_video)
    return info


@pytest.fixture
async def hardware_info():
    """Detect available hardware acceleration."""
    detector = HardwareDetector()
    return await detector.detect()


class TestMediaInspection:
    """Test media inspection with actual MKV file."""

    @pytest.mark.asyncio
    async def test_inspect_fixture_video(self, fixture_video):
        """Test inspecting the actual fixture video."""
        inspector = MediaInspector()
        media_info = await inspector.inspect(fixture_video)

        # Verify basic properties
        assert media_info is not None
        assert media_info.format is not None
        assert media_info.format.duration > 0
        assert media_info.format.size > 0

        # Should have at least one video stream
        assert len(media_info.video_streams) > 0
        video = media_info.video_streams[0]
        assert video.width > 0
        assert video.height > 0
        assert video.fps > 0

        print(f"\n=== Media Info ===")
        print(f"Duration: {media_info.format.duration:.2f}s")
        print(f"Size: {media_info.format.size / (1024*1024):.2f} MB")
        print(f"Video: {video.codec} {video.width}x{video.height} @ {video.fps}fps")
        print(f"Audio tracks: {len(media_info.audio_streams)}")
        print(f"Subtitle tracks: {len(media_info.subtitle_streams)}")

    @pytest.mark.asyncio
    async def test_inspect_video_streams(self, fixture_video):
        """Test video stream details."""
        inspector = MediaInspector()
        media_info = await inspector.inspect(fixture_video)

        for video in media_info.video_streams:
            assert video.codec is not None
            assert video.width > 0
            assert video.height > 0
            assert video.fps > 0
            assert video.duration > 0

            print(f"\nVideo Stream {video.index}:")
            print(f"  Codec: {video.codec_long}")
            print(f"  Resolution: {video.width}x{video.height}")
            print(f"  FPS: {video.fps}")
            print(f"  Bitrate: {video.bitrate / 1000 if video.bitrate else 'N/A'} kbps")

    @pytest.mark.asyncio
    async def test_inspect_audio_streams(self, fixture_video):
        """Test audio stream details."""
        inspector = MediaInspector()
        media_info = await inspector.inspect(fixture_video)

        if media_info.audio_streams:
            for audio in media_info.audio_streams:
                assert audio.codec is not None
                assert audio.sample_rate > 0
                assert audio.channels > 0

                print(f"\nAudio Stream {audio.index}:")
                print(f"  Language: {audio.language or 'Unknown'}")
                print(f"  Codec: {audio.codec_long}")
                print(f"  Channels: {audio.channels}")
                print(f"  Sample Rate: {audio.sample_rate} Hz")
                print(f"  Bitrate: {audio.bitrate / 1000 if audio.bitrate else 'N/A'} kbps")

    @pytest.mark.asyncio
    async def test_inspect_subtitle_streams(self, fixture_video):
        """Test subtitle stream details."""
        inspector = MediaInspector()
        media_info = await inspector.inspect(fixture_video)

        if media_info.subtitle_streams:
            for subtitle in media_info.subtitle_streams:
                assert subtitle.codec is not None

                print(f"\nSubtitle Stream {subtitle.index}:")
                print(f"  Language: {subtitle.language or 'Unknown'}")
                print(f"  Format: {subtitle.codec}")
                print(f"  Title: {subtitle.title or 'N/A'}")


class TestVideoTranscoding:
    """Test video transcoding with actual MKV file."""

    @pytest.mark.asyncio
    async def test_transcode_single_quality(self, fixture_video, output_dir, hardware_info):
        """Test transcoding to a single quality."""
        inspector = MediaInspector()
        media_info = await inspector.inspect(fixture_video)
        video_stream = media_info.video_streams[0]

        transcoder = VideoTranscoder(
            input_file=fixture_video,
            output_dir=output_dir,
            hardware_info=hardware_info,
            video_stream=video_stream,
        )

        # Transcode to 720p (faster than 1080p for testing)
        quality = QUALITY_PRESETS["720p"]
        result_path = await transcoder.transcode(
            quality=quality,
        )

        # Get the result by checking the output
        result = type(
            "obj",
            (object,),
            {
                "quality": quality.name,
                "height": quality.height,
                "width": quality.width,
                "playlist_path": result_path,
                "segment_count": len(list(output_dir.glob(f"{quality.name}_*.ts"))),
                "duration": video_stream.duration,
                "size": sum(f.stat().st_size for f in output_dir.glob(f"{quality.name}_*.ts")),
            },
        )()

        # Verify output
        assert result is not None
        assert result.quality == "720p"
        assert result.height == 720
        assert result.playlist_path.exists()
        assert result.segment_count > 0

        # Check that segments were created
        segments = list(output_dir.glob("*.ts"))
        assert len(segments) > 0
        assert len(segments) == result.segment_count

        print(f"\n=== Video Transcoding Result ===")
        print(f"Quality: {result.quality}")
        print(f"Resolution: {result.width}x{result.height}")
        print(f"Duration: {result.duration:.2f}s")
        print(f"Segments: {result.segment_count}")
        print(f"Size: {result.size / (1024*1024):.2f} MB")
        print(f"Playlist: {result.playlist_path}")

    @pytest.mark.asyncio
    async def test_transcode_multiple_qualities(self, fixture_video, output_dir, hardware_info):
        """Test transcoding to multiple quality variants."""
        inspector = MediaInspector()
        media_info = await inspector.inspect(fixture_video)
        video_stream = media_info.video_streams[0]

        transcoder = VideoTranscoder(
            input_file=fixture_video,
            output_dir=output_dir,
            hardware_info=hardware_info,
            video_stream=video_stream,
        )

        # Transcode to 480p and 360p (faster variants)
        quality_names = ["480p", "360p"]

        results = []
        for quality_name in quality_names:
            quality = QUALITY_PRESETS[quality_name]
            result_path = await transcoder.transcode(
                quality=quality,
            )

            # Create result object
            result = type(
                "obj",
                (object,),
                {
                    "quality": quality.name,
                    "height": quality.height,
                    "width": quality.width,
                    "playlist_path": result_path,
                    "segment_count": len(list(output_dir.glob(f"{quality.name}_*.ts"))),
                    "size": sum(f.stat().st_size for f in output_dir.glob(f"{quality.name}_*.ts")),
                },
            )()
            results.append(result)

        # Verify all outputs
        assert len(results) == 2

        for result in results:
            assert result.playlist_path.exists()
            assert result.segment_count > 0

        print(f"\n=== Multiple Quality Results ===")
        for result in results:
            print(
                f"{result.quality}: {result.width}x{result.height}, "
                f"{result.segment_count} segments, "
                f"{result.size / (1024*1024):.2f} MB"
            )

    @pytest.mark.asyncio
    async def test_transcode_with_progress(self, fixture_video, output_dir, hardware_info):
        """Test transcoding with progress callback."""
        inspector = MediaInspector()
        media_info = await inspector.inspect(fixture_video)
        video_stream = media_info.video_streams[0]

        transcoder = VideoTranscoder(
            input_file=fixture_video,
            output_dir=output_dir,
            hardware_info=hardware_info,
            video_stream=video_stream,
        )

        progress_updates = []

        def progress_callback(current: float, total: Optional[float] = None):
            progress_updates.append(current)
            print(f"\rProgress: {current:.1f}%", end="", flush=True)

        quality = QUALITY_PRESETS["360p"]
        result_path = await transcoder.transcode(
            quality=quality,
            progress_callback=progress_callback,
        )

        result = type(
            "obj",
            (object,),
            {
                "quality": quality.name,
                "playlist_path": result_path,
            },
        )()

        print()  # New line after progress

        # Should have received progress updates
        assert len(progress_updates) > 0
        assert progress_updates[-1] >= 99.0  # Should reach near 100%

        print(f"\n=== Progress Tracking ===")
        print(f"Total progress updates: {len(progress_updates)}")
        print(f"Final progress: {progress_updates[-1]:.1f}%")


class TestAudioExtraction:
    """Test audio extraction with actual MKV file."""

    @pytest.mark.asyncio
    async def test_extract_single_audio_track(self, fixture_video, output_dir):
        """Test extracting a single audio track."""
        inspector = MediaInspector()
        media_info = await inspector.inspect(fixture_video)

        if not media_info.audio_streams:
            pytest.skip("No audio streams in fixture file")

        audio_stream = media_info.audio_streams[0]
        extractor = AudioExtractor(
            input_file=fixture_video,
            output_dir=output_dir,
        )

        result = await extractor.extract(
            audio_stream=audio_stream,
            quality="high",
        )

        # Verify output
        assert result is not None
        assert result.index == audio_stream.index
        assert result.playlist_path.exists()
        assert result.size > 0

        # Check segments
        segments = list(output_dir.glob("audio*.ts"))
        assert len(segments) > 0

        print(f"\n=== Audio Extraction Result ===")
        print(f"Track: {result.index}")
        print(f"Language: {result.language}")
        print(f"Codec: {result.codec}")
        print(f"Size: {result.size / (1024*1024):.2f} MB")
        print(f"Playlist: {result.playlist_path}")

    @pytest.mark.asyncio
    async def test_extract_all_audio_tracks(self, fixture_video, output_dir):
        """Test extracting all audio tracks."""
        inspector = MediaInspector()
        media_info = await inspector.inspect(fixture_video)

        if not media_info.audio_streams:
            pytest.skip("No audio streams in fixture file")

        results = await extract_all_audio_tracks(
            input_file=fixture_video,
            audio_streams=media_info.audio_streams,
            output_dir=output_dir,
            quality="medium",
            max_concurrent=2,
        )

        # Verify outputs
        assert len(results) == len(media_info.audio_streams)

        for result in results:
            assert result.playlist_path.exists()
            assert result.size > 0

        print(f"\n=== All Audio Tracks ===")
        for result in results:
            print(
                f"Track {result.index} ({result.language}): " f"{result.size / (1024*1024):.2f} MB"
            )


class TestSubtitleExtraction:
    """Test subtitle extraction with actual MKV file."""

    @pytest.mark.asyncio
    async def test_extract_single_subtitle(self, fixture_video, output_dir):
        """Test extracting a single subtitle track."""
        inspector = MediaInspector()
        media_info = await inspector.inspect(fixture_video)

        if not media_info.subtitle_streams:
            pytest.skip("No subtitle streams in fixture file")

        subtitle_stream = media_info.subtitle_streams[0]
        extractor = SubtitleExtractor(
            input_file=fixture_video,
            output_dir=output_dir,
        )

        result = await extractor.extract_track(
            subtitle_stream=subtitle_stream,
            output_format="webvtt",
        )

        # Verify output
        assert result is not None
        assert result.index == subtitle_stream.index
        assert result.file_path.exists()

        print(f"\n=== Subtitle Extraction Result ===")
        print(f"Track: {result.index}")
        print(f"Language: {result.language}")
        print(f"Format: {result.format}")
        print(f"File: {result.file_path}")

    @pytest.mark.asyncio
    async def test_extract_all_subtitles(self, fixture_video, output_dir):
        """Test extracting all subtitle tracks."""
        inspector = MediaInspector()
        media_info = await inspector.inspect(fixture_video)

        if not media_info.subtitle_streams:
            pytest.skip("No subtitle streams in fixture file")

        results = await extract_all_subtitles(
            input_file=fixture_video,
            subtitle_streams=media_info.subtitle_streams,
            output_dir=output_dir,
            output_format="webvtt",
            max_concurrent=3,
        )

        # Verify outputs
        assert len(results) == len(media_info.subtitle_streams)

        for result in results:
            assert result.file_path.exists()

        print(f"\n=== All Subtitle Tracks ===")
        for result in results:
            print(f"Track {result.index} ({result.language}): {result.format}")


class TestSpriteGeneration:
    """Test sprite generation with actual MKV file."""

    @pytest.mark.asyncio
    async def test_generate_sprite_basic(self, fixture_video, output_dir):
        """Test basic sprite generation."""
        inspector = MediaInspector()
        media_info = await inspector.inspect(fixture_video)

        result = await generate_sprite(
            input_file=fixture_video,
            output_dir=output_dir,
            duration=media_info.format_info.duration,
            interval=10,  # Every 10 seconds
            width=160,
            height=90,
            columns=5,
            rows=5,
        )

        # Verify output
        assert result is not None
        assert result.sprite_path.exists()
        assert result.vtt_path.exists()
        assert result.thumbnail_count > 0
        assert result.size > 0

        print(f"\n=== Sprite Generation Result ===")
        print(f"Thumbnails: {result.thumbnail_count}")
        print(f"Sprite: {result.sprite_path}")
        print(f"VTT: {result.vtt_path}")
        print(f"Size: {result.size / 1024:.2f} KB")

    @pytest.mark.asyncio
    async def test_generate_sprite_custom_settings(self, fixture_video, output_dir):
        """Test sprite generation with custom settings."""
        inspector = MediaInspector()
        media_info = await inspector.inspect(fixture_video)

        generator = SpriteGenerator(
            input_file=fixture_video,
            output_dir=output_dir,
            duration=media_info.format_info.duration,
        )

        result = await generator.generate(
            interval=5,  # Every 5 seconds
            width=120,
            height=68,
            columns=10,
            rows=10,
            quality=2,  # JPEG quality
        )

        # Verify output
        assert result is not None
        assert result.sprite_path.exists()
        assert result.vtt_path.exists()

        print(f"\n=== Custom Sprite Result ===")
        print(f"Thumbnails: {result.thumbnail_count}")
        print(f"Size: {result.size / 1024:.2f} KB")


class TestPlaylistGeneration:
    """Test playlist generation with actual outputs."""

    @pytest.mark.asyncio
    async def test_generate_master_playlist(self, fixture_video, output_dir, hardware_info):
        """Test generating master playlist with real variants."""
        # First, create some video variants
        inspector = MediaInspector()
        media_info = await inspector.inspect(fixture_video)
        video_stream = media_info.video_streams[0]

        transcoder = VideoTranscoder(
            input_file=fixture_video,
            output_dir=output_dir,
            hardware_info=hardware_info,
            video_stream=video_stream,
        )

        # Create 360p variant
        video_result = await transcoder.transcode(
            quality_name="360p",
            height=360,
            bitrate="600k",
            maxrate="800k",
            bufsize="1200k",
        )

        # Extract audio if available
        audio_results = []
        if media_info.audio_streams:
            extractor = AudioExtractor(
                input_file=fixture_video,
                output_dir=output_dir,
            )
            audio_result = await extractor.extract_track(
                audio_stream=media_info.audio_streams[0],
                quality="medium",
            )
            audio_results.append(audio_result)

        # Generate master playlist
        generator = PlaylistGenerator(output_dir)
        master_path = await generator.generate_master_playlist(
            video_variants=[video_result],
            audio_tracks=audio_results,
        )

        # Verify output
        assert master_path.exists()

        # Read and verify content
        content = master_path.read_text()
        assert "#EXTM3U" in content
        assert "#EXT-X-STREAM-INF" in content

        print(f"\n=== Master Playlist ===")
        print(f"Path: {master_path}")
        print(f"\nContent preview:")
        print(content[:500])


class TestOutputValidation:
    """Test output validation with actual files."""

    @pytest.mark.asyncio
    async def test_validate_complete_output(self, fixture_video, output_dir, hardware_info):
        """Test validating a complete transcoding output."""
        # Create a minimal transcoding output
        inspector = MediaInspector()
        media_info = await inspector.inspect(fixture_video)
        video_stream = media_info.video_streams[0]

        transcoder = VideoTranscoder(
            input_file=fixture_video,
            output_dir=output_dir,
            hardware_info=hardware_info,
            video_stream=video_stream,
        )

        # Transcode
        video_result = await transcoder.transcode(
            quality_name="360p",
            height=360,
            bitrate="600k",
            maxrate="800k",
            bufsize="1200k",
        )

        # Generate master playlist
        generator = PlaylistGenerator(output_dir)
        master_path = await generator.generate_master_playlist(
            video_variants=[video_result],
            audio_tracks=[],
        )

        # Validate
        validator = OutputValidator(output_dir)
        result = await validator.validate_output(
            master_playlist=master_path,
            video_variants=[video_result],
            audio_tracks=[],
            subtitle_tracks=[],
        )

        # Should pass validation
        assert result.success
        assert result.master_playlist_valid
        assert result.all_segments_present
        assert len(result.errors) == 0

        print(f"\n=== Validation Result ===")
        print(f"Success: {result.success}")
        print(f"Master playlist: {'✓' if result.master_playlist_valid else '✗'}")
        print(f"All segments present: {'✓' if result.all_segments_present else '✗'}")
        if result.warnings:
            print(f"Warnings: {len(result.warnings)}")
            for warning in result.warnings:
                print(f"  - {warning}")


class TestFullPipeline:
    """Test complete transcoding pipeline end-to-end."""

    @pytest.mark.asyncio
    async def test_full_transcoding_pipeline(self, fixture_video, output_dir, hardware_info):
        """Test complete pipeline: inspect → transcode → extract → generate → validate."""
        print(f"\n{'='*60}")
        print("FULL PIPELINE TEST")
        print(f"{'='*60}")

        # Step 1: Inspect
        print("\n[1/5] Inspecting media...")
        inspector = MediaInspector()
        media_info = await inspector.inspect(fixture_video)
        print(f"  ✓ Duration: {media_info.format_info.duration:.2f}s")
        print(
            f"  ✓ Video: {media_info.video_streams[0].width}x{media_info.video_streams[0].height}"
        )
        print(f"  ✓ Audio tracks: {len(media_info.audio_streams)}")
        print(f"  ✓ Subtitle tracks: {len(media_info.subtitle_streams)}")

        # Step 2: Transcode video
        print("\n[2/5] Transcoding video...")
        video_stream = media_info.video_streams[0]
        transcoder = VideoTranscoder(
            input_file=fixture_video,
            output_dir=output_dir,
            hardware_info=hardware_info,
            video_stream=video_stream,
        )

        video_result = await transcoder.transcode(
            quality_name="360p",
            height=360,
            bitrate="600k",
            maxrate="800k",
            bufsize="1200k",
        )
        print(f"  ✓ Created {video_result.segment_count} segments")
        print(f"  ✓ Size: {video_result.size / (1024*1024):.2f} MB")

        # Step 3: Extract audio
        print("\n[3/5] Extracting audio...")
        audio_results = []
        if media_info.audio_streams:
            audio_results = await extract_all_audio_tracks(
                input_file=fixture_video,
                audio_streams=media_info.audio_streams[:1],  # Just first track
                output_dir=output_dir,
                quality="medium",
            )
            print(f"  ✓ Extracted {len(audio_results)} audio track(s)")
        else:
            print("  ⚠ No audio tracks found")

        # Step 4: Generate playlists
        print("\n[4/5] Generating playlists...")
        generator = PlaylistGenerator(output_dir)
        master_path = await generator.generate_master_playlist(
            video_variants=[video_result],
            audio_tracks=audio_results,
        )
        print(f"  ✓ Master playlist: {master_path.name}")

        # Step 5: Validate output
        print("\n[5/5] Validating output...")
        validator = OutputValidator(output_dir)
        validation = await validator.validate_output(
            master_playlist=master_path,
            video_variants=[video_result],
            audio_tracks=audio_results,
            subtitle_tracks=[],
        )

        print(
            f"  {'✓' if validation.success else '✗'} Validation: "
            f"{'PASSED' if validation.success else 'FAILED'}"
        )

        if validation.errors:
            for error in validation.errors:
                print(f"    ✗ {error}")

        if validation.warnings:
            for warning in validation.warnings:
                print(f"    ⚠ {warning}")

        # Final summary
        print(f"\n{'='*60}")
        print("PIPELINE COMPLETE")
        print(f"{'='*60}")
        print(f"Output directory: {output_dir}")
        print(f"Files created:")

        all_files = sorted(output_dir.rglob("*"))
        for file in all_files:
            if file.is_file():
                size = file.stat().st_size
                print(f"  - {file.relative_to(output_dir)} ({size / 1024:.1f} KB)")

        # Assert success
        assert validation.success
        assert master_path.exists()
        assert video_result.playlist_path.exists()


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
