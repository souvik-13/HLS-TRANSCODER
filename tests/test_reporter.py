"""Tests for summary reporter."""

import pytest
from io import StringIO
from pathlib import Path

from rich.console import Console

from hls_transcoder.ui.reporter import (
    SummaryReporter,
    display_transcoding_summary,
    create_summary_table,
)
from hls_transcoder.models.results import (
    TranscodingResults,
    VideoVariantResult,
    AudioTrackResult,
    SubtitleResult,
    SpriteResult,
    ValidationResult,
)


@pytest.fixture
def mock_console():
    """Create mock console with string IO."""
    string_io = StringIO()
    console = Console(file=string_io, force_terminal=True, width=120)
    return console, string_io


@pytest.fixture
def sample_results(tmp_path):
    """Create sample transcoding results."""
    output_dir = tmp_path / "output"
    output_dir.mkdir()

    # Create video variants
    video_variants = [
        VideoVariantResult(
            quality="1080p",
            width=1920,
            height=1080,
            duration=600.0,
            bitrate="5000k",
            segment_count=100,
            size=500 * 1024 * 1024,  # 500 MB
            playlist_path=output_dir / "video_1080p.m3u8",
        ),
        VideoVariantResult(
            quality="720p",
            width=1280,
            height=720,
            duration=600.0,
            bitrate="2500k",
            segment_count=100,
            size=250 * 1024 * 1024,  # 250 MB
            playlist_path=output_dir / "video_720p.m3u8",
        ),
    ]

    # Create audio tracks
    audio_tracks = [
        AudioTrackResult(
            index=0,
            language="eng",
            codec="aac",
            size=50 * 1024 * 1024,  # 50 MB
            playlist_path=output_dir / "audio_eng.m3u8",
        ),
    ]

    # Create subtitle tracks
    subtitle_tracks = [
        SubtitleResult(
            index=0,
            language="eng",
            format="webvtt",
            file_path=output_dir / "subtitle_eng.vtt",
        ),
    ]

    # Create sprite result
    sprite = SpriteResult(
        thumbnail_count=50,
        sprite_path=output_dir / "sprite.jpg",
        vtt_path=output_dir / "sprite.vtt",
        size=5 * 1024 * 1024,  # 5 MB
    )

    # Create results
    results = TranscodingResults(
        video_variants=video_variants,
        audio_tracks=audio_tracks,
        subtitle_tracks=subtitle_tracks,
        sprite=sprite,
        master_playlist=output_dir / "master.m3u8",
        metadata_file=output_dir / "metadata.json",
        total_duration=3600.0,  # 1 hour
        hardware_used="nvidia",
        parallel_jobs=4,
        total_frames=90000,
    )

    return results


@pytest.fixture
def sample_validation():
    """Create sample validation result."""
    return ValidationResult(
        success=True,
        master_playlist_valid=True,
        all_segments_present=True,
        audio_sync_valid=True,
        subtitle_files_valid=True,
        errors=[],
        warnings=["Minor timing drift in segment 50"],
    )


@pytest.fixture
def failed_validation():
    """Create failed validation result."""
    return ValidationResult(
        success=False,
        master_playlist_valid=True,
        all_segments_present=False,
        audio_sync_valid=False,
        subtitle_files_valid=True,
        errors=[
            "Missing segments: segment_099.ts, segment_100.ts",
            "Audio sync issues detected in segments 50-60",
        ],
        warnings=["Low bitrate in segment 10"],
    )


class TestSummaryReporter:
    """Tests for SummaryReporter class."""

    def test_initialization(self, mock_console):
        """Test reporter initialization."""
        console, _ = mock_console
        reporter = SummaryReporter(console)

        assert reporter.console is console
        assert reporter.logger is not None

    def test_initialization_default_console(self):
        """Test reporter with default console."""
        reporter = SummaryReporter()
        assert reporter.console is not None

    def test_display_summary_complete(self, mock_console, sample_results, sample_validation):
        """Test complete summary display."""
        console, string_io = mock_console
        reporter = SummaryReporter(console)

        reporter.display_summary(sample_results, sample_validation)

        output = string_io.getvalue()

        # Check for major sections
        assert "Transcoding Complete" in output
        assert "Overview" in output
        assert "Video Variants" in output
        assert "Audio Tracks" in output
        assert "Subtitle Tracks" in output
        assert "Sprite Generation" in output
        assert "Performance Metrics" in output
        assert "Validation Status" in output
        assert "Output Files" in output

    def test_display_summary_without_validation(self, mock_console, sample_results):
        """Test summary display without validation."""
        console, string_io = mock_console
        reporter = SummaryReporter(console)

        reporter.display_summary(sample_results, None)

        output = string_io.getvalue()

        # Should not have validation section
        assert "Validation Status" not in output
        # Should have other sections
        assert "Overview" in output
        assert "Video Variants" in output

    def test_display_overview(self, mock_console, sample_results):
        """Test overview display."""
        console, string_io = mock_console
        reporter = SummaryReporter(console)

        reporter._display_overview(sample_results)

        output = string_io.getvalue()

        assert "Overview" in output
        assert "Video Variants" in output
        assert "2" in output  # 2 video variants
        assert "Audio Tracks" in output
        assert "1" in output  # 1 audio track
        assert "Subtitle Tracks" in output
        assert "Sprites Generated" in output
        assert "Yes" in output
        assert "Total Output Size" in output
        assert "Duration" in output

    def test_display_video_variants(self, mock_console, sample_results):
        """Test video variants display."""
        console, string_io = mock_console
        reporter = SummaryReporter(console)

        reporter._display_video_variants(sample_results)

        output = string_io.getvalue()

        assert "Video Variants" in output
        assert "1080p" in output
        assert "1920x1080" in output
        assert "5000k" in output
        assert "100" in output  # segments
        assert "720p" in output
        assert "1280x720" in output
        assert "2500k" in output

    def test_display_audio_tracks(self, mock_console, sample_results):
        """Test audio tracks display."""
        console, string_io = mock_console
        reporter = SummaryReporter(console)

        reporter._display_audio_tracks(sample_results)

        output = string_io.getvalue()

        assert "Audio Tracks" in output
        assert "eng" in output
        assert "aac" in output
        assert "0" in output  # index

    def test_display_subtitle_tracks(self, mock_console, sample_results):
        """Test subtitle tracks display."""
        console, string_io = mock_console
        reporter = SummaryReporter(console)

        reporter._display_subtitle_tracks(sample_results)

        output = string_io.getvalue()

        assert "Subtitle Tracks" in output
        assert "eng" in output
        assert "webvtt" in output
        assert "0" in output  # index

    def test_display_sprites(self, mock_console, sample_results):
        """Test sprite display."""
        console, string_io = mock_console
        reporter = SummaryReporter(console)

        reporter._display_sprites(sample_results)

        output = string_io.getvalue()

        assert "Sprite Generation" in output
        assert "50" in output  # thumbnail count
        assert "sprite.jpg" in output
        assert "sprite.vtt" in output

    def test_display_sprites_none(self, mock_console, sample_results):
        """Test sprite display when no sprites."""
        console, string_io = mock_console
        reporter = SummaryReporter(console)

        # Remove sprite
        sample_results.sprite = None

        reporter._display_sprites(sample_results)

        output = string_io.getvalue()

        # Should produce no output
        assert output == ""

    def test_display_performance_metrics(self, mock_console, sample_results):
        """Test performance metrics display."""
        console, string_io = mock_console
        reporter = SummaryReporter(console)

        reporter._display_performance_metrics(sample_results)

        output = string_io.getvalue()

        assert "Performance Metrics" in output
        assert "nvidia" in output  # hardware
        assert "4" in output  # parallel jobs
        assert "90,000" in output or "90000" in output  # frames

    def test_display_validation_passed(self, mock_console, sample_validation):
        """Test validation display for passed validation."""
        console, string_io = mock_console
        reporter = SummaryReporter(console)

        reporter._display_validation_results(sample_validation)

        output = string_io.getvalue()

        assert "Validation Status" in output
        assert "PASSED" in output
        assert "Master Playlist" in output
        assert "Segments" in output
        assert "Audio Sync" in output
        assert "Subtitle Files" in output
        assert "Warnings (1)" in output
        assert "Minor timing drift" in output

    def test_display_validation_failed(self, mock_console, failed_validation):
        """Test validation display for failed validation."""
        console, string_io = mock_console
        reporter = SummaryReporter(console)

        reporter._display_validation_results(failed_validation)

        output = string_io.getvalue()

        assert "Validation Status" in output
        assert "FAILED" in output
        assert "Errors (2)" in output
        assert "Missing segments" in output
        assert "Audio sync issues" in output
        assert "Warnings (1)" in output
        assert "Low bitrate" in output

    def test_display_output_location(self, mock_console, sample_results):
        """Test output location display."""
        console, string_io = mock_console
        reporter = SummaryReporter(console)

        reporter._display_output_location(sample_results)

        output = string_io.getvalue()

        assert "Output Files" in output
        assert "master.m3u8" in output
        assert "Video Variants" in output
        assert "Audio Tracks" in output
        assert "Subtitles" in output
        assert "Sprites" in output
        assert "metadata.json" in output

    def test_display_error_without_exception(self, mock_console):
        """Test error display without exception."""
        console, string_io = mock_console
        reporter = SummaryReporter(console)

        reporter.display_error("Something went wrong")

        output = string_io.getvalue()

        assert "Error" in output
        assert "Something went wrong" in output

    def test_display_error_with_exception(self, mock_console):
        """Test error display with exception."""
        console, string_io = mock_console
        reporter = SummaryReporter(console)

        error = ValueError("Invalid parameter")
        reporter.display_error("Configuration error", error)

        output = string_io.getvalue()

        assert "Error" in output
        assert "Configuration error" in output
        assert "Invalid parameter" in output

    def test_display_success(self, mock_console):
        """Test success display."""
        console, string_io = mock_console
        reporter = SummaryReporter(console)

        reporter.display_success("Operation completed successfully")

        output = string_io.getvalue()

        assert "Success" in output
        assert "Operation completed successfully" in output

    def test_display_info(self, mock_console):
        """Test info display."""
        console, string_io = mock_console
        reporter = SummaryReporter(console)

        reporter.display_info("Processing file...")

        output = string_io.getvalue()

        assert "Processing file..." in output


class TestConvenienceFunctions:
    """Tests for convenience functions."""

    def test_display_transcoding_summary(self, mock_console, sample_results, sample_validation):
        """Test display_transcoding_summary function."""
        console, string_io = mock_console

        display_transcoding_summary(sample_results, sample_validation, console)

        output = string_io.getvalue()

        assert "Transcoding Complete" in output
        assert "Overview" in output
        assert "Validation Status" in output

    def test_display_transcoding_summary_default_console(self, sample_results):
        """Test display_transcoding_summary with default console."""
        # Should not raise
        display_transcoding_summary(sample_results)

    def test_create_summary_table(self, sample_results):
        """Test create_summary_table function."""
        table = create_summary_table(sample_results)

        assert table is not None
        assert table.title == "Transcoding Summary"

    def test_create_summary_table_with_sprites(self, sample_results):
        """Test summary table includes sprite info."""
        table = create_summary_table(sample_results)

        # Table should be created without errors
        assert table is not None

    def test_create_summary_table_without_sprites(self, sample_results):
        """Test summary table without sprites."""
        sample_results.sprite = None

        table = create_summary_table(sample_results)

        # Table should be created without errors
        assert table is not None


class TestEdgeCases:
    """Tests for edge cases."""

    def test_empty_results(self, mock_console, tmp_path):
        """Test display with empty results."""
        console, string_io = mock_console
        reporter = SummaryReporter(console)

        # Create minimal results
        results = TranscodingResults(
            video_variants=[],
            audio_tracks=[],
            subtitle_tracks=[],
            sprite=None,
            master_playlist=None,
            metadata_file=None,
            total_duration=0.0,
            hardware_used="cpu",
            parallel_jobs=1,
        )

        reporter.display_summary(results)

        output = string_io.getvalue()

        # Should still display overview
        assert "Overview" in output
        assert "0" in output  # 0 variants

    def test_validation_no_issues(self, mock_console):
        """Test validation display with no errors or warnings."""
        console, string_io = mock_console
        reporter = SummaryReporter(console)

        validation = ValidationResult(
            success=True,
            master_playlist_valid=True,
            all_segments_present=True,
            audio_sync_valid=True,
            subtitle_files_valid=True,
            errors=[],
            warnings=[],
        )

        reporter._display_validation_results(validation)

        output = string_io.getvalue()

        assert "PASSED" in output
        assert "No validation issues detected" in output

    def test_large_file_sizes(self, mock_console, tmp_path):
        """Test display with very large file sizes."""
        console, string_io = mock_console
        reporter = SummaryReporter(console)

        # Create result with large size
        video_variants = [
            VideoVariantResult(
                quality="4K",
                width=3840,
                height=2160,
                duration=7200.0,
                bitrate="20000k",
                segment_count=1000,
                size=50 * 1024 * 1024 * 1024,  # 50 GB
                playlist_path=Path("video_4k.m3u8"),
            ),
        ]

        results = TranscodingResults(
            video_variants=video_variants,
            audio_tracks=[],
            subtitle_tracks=[],
            sprite=None,
            master_playlist=None,
            metadata_file=None,
            total_duration=7200.0,  # 2 hours
            hardware_used="nvidia",
            parallel_jobs=8,
        )

        reporter.display_summary(results)

        output = string_io.getvalue()

        # Should display large sizes correctly
        assert "GB" in output or "50" in output

    def test_special_characters_in_paths(self, mock_console, tmp_path):
        """Test display with special characters in paths."""
        console, string_io = mock_console
        reporter = SummaryReporter(console)

        # Create result with special characters
        special_path = tmp_path / "output (2024) [HD]"
        special_path.mkdir()

        video_variants = [
            VideoVariantResult(
                quality="1080p",
                width=1920,
                height=1080,
                duration=600.0,
                bitrate="5000k",
                segment_count=100,
                size=500 * 1024 * 1024,
                playlist_path=special_path / "video.m3u8",
            ),
        ]

        results = TranscodingResults(
            video_variants=video_variants,
            audio_tracks=[],
            subtitle_tracks=[],
            sprite=None,
            master_playlist=special_path / "master.m3u8",
            metadata_file=None,
            total_duration=3600.0,
            hardware_used="cpu",
            parallel_jobs=1,
        )

        reporter.display_summary(results)

        output = string_io.getvalue()

        # Should handle special characters
        assert "video.m3u8" in output
