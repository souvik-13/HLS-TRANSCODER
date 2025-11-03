"""
Tests for resolution detection and handling.
"""

import pytest

from hls_transcoder.utils.helpers import (
    calculate_target_resolution,
    get_quality_from_height,
    get_standard_resolutions,
    should_include_quality,
)


class TestQualityDetection:
    """Test quality detection from height."""

    def test_exact_standard_resolutions(self):
        """Test exact matches for standard resolutions."""
        assert get_quality_from_height(2160) == "2160p"
        assert get_quality_from_height(1440) == "1440p"
        assert get_quality_from_height(1080) == "1080p"
        assert get_quality_from_height(720) == "720p"
        assert get_quality_from_height(480) == "480p"
        assert get_quality_from_height(360) == "360p"
        assert get_quality_from_height(240) == "240p"

    def test_non_standard_resolutions_rounded_down(self):
        """Test non-standard resolutions are rounded down."""
        # Between 4K and 1440p -> should get 1440p
        assert get_quality_from_height(1800) == "1440p"

        # Between 1440p and 1080p -> should get 1080p
        assert get_quality_from_height(1200) == "1080p"

        # Between 1080p and 720p -> should get 720p
        assert get_quality_from_height(900) == "720p"

        # Between 720p and 480p -> should get 480p
        assert get_quality_from_height(600) == "480p"

        # Between 480p and 360p -> should get 360p
        assert get_quality_from_height(400) == "360p"

    def test_below_minimum_resolution(self):
        """Test resolution below 240p."""
        assert get_quality_from_height(144) == "240p"
        assert get_quality_from_height(100) == "240p"

    def test_exact_match_mode(self):
        """Test exact match mode."""
        assert get_quality_from_height(1080, exact_match=True) == "1080p"
        assert get_quality_from_height(900, exact_match=True) is None
        assert get_quality_from_height(1200, exact_match=True) is None


class TestStandardResolutions:
    """Test standard resolution mapping."""

    def test_standard_resolutions(self):
        """Test that all standard resolutions are defined."""
        resolutions = get_standard_resolutions()

        assert resolutions["2160p"] == (3840, 2160)
        assert resolutions["1440p"] == (2560, 1440)
        assert resolutions["1080p"] == (1920, 1080)
        assert resolutions["720p"] == (1280, 720)
        assert resolutions["480p"] == (854, 480)
        assert resolutions["360p"] == (640, 360)
        assert resolutions["240p"] == (426, 240)


class TestTargetResolutionCalculation:
    """Test target resolution calculation."""

    def test_original_quality(self):
        """Test that 'original' returns source dimensions."""
        width, height = calculate_target_resolution(1920, 1080, "original")
        assert width == 1920
        assert height == 1080

        # Weird resolution
        width, height = calculate_target_resolution(1366, 768, "original")
        assert width == 1366
        assert height == 768

    def test_16_9_aspect_ratio(self):
        """Test standard 16:9 videos."""
        # 4K source to 1080p
        width, height = calculate_target_resolution(3840, 2160, "1080p")
        assert height == 1080
        assert width == 1920

        # 1080p source to 720p
        width, height = calculate_target_resolution(1920, 1080, "720p")
        assert height == 720
        assert width == 1280

    def test_non_standard_aspect_ratio(self):
        """Test non-standard aspect ratios maintain ratio."""
        # Vertical video (9:16)
        width, height = calculate_target_resolution(1080, 1920, "720p")
        assert height == 720
        # Should maintain aspect ratio (9:16)
        expected_width = int(720 * (1080 / 1920))
        assert width == expected_width or width == expected_width - 1  # Allow for rounding

    def test_ultra_wide_aspect_ratio(self):
        """Test ultra-wide aspect ratios (21:9)."""
        # 21:9 aspect ratio
        width, height = calculate_target_resolution(2560, 1080, "720p")
        assert height == 720
        # Should maintain 21:9 aspect ratio
        expected_width = int(720 * (2560 / 1080))
        # Ensure even width
        expected_width = expected_width if expected_width % 2 == 0 else expected_width - 1
        assert width == expected_width

    def test_even_dimensions(self):
        """Test that output dimensions are always even."""
        # Odd source dimensions
        width, height = calculate_target_resolution(1921, 1081, "720p")
        assert width % 2 == 0
        assert height % 2 == 0

    def test_square_aspect_ratio(self):
        """Test square videos (1:1)."""
        # Instagram style 1:1
        width, height = calculate_target_resolution(1080, 1080, "720p")
        assert height == 720
        assert width == 720

    def test_weird_resolutions(self):
        """Test various weird resolutions."""
        # 1366x768 (common laptop resolution)
        width, height = calculate_target_resolution(1366, 768, "720p")
        assert height == 720
        assert width % 2 == 0  # Must be even

        # 1600x900 (16:9 variant)
        width, height = calculate_target_resolution(1600, 900, "720p")
        assert height == 720
        assert width % 2 == 0


class TestQualityInclusion:
    """Test quality variant inclusion logic."""

    def test_no_upscaling_by_default(self):
        """Test that higher qualities are excluded by default."""
        # 720p source should not include 1080p
        assert should_include_quality(720, "1080p", allow_upscaling=False) is False
        assert should_include_quality(720, "1440p", allow_upscaling=False) is False
        assert should_include_quality(720, "2160p", allow_upscaling=False) is False

        # But should include same or lower
        assert should_include_quality(720, "720p", allow_upscaling=False) is True
        assert should_include_quality(720, "480p", allow_upscaling=False) is True
        assert should_include_quality(720, "360p", allow_upscaling=False) is True

    def test_upscaling_allowed(self):
        """Test that higher qualities are included when upscaling allowed."""
        # 720p source with upscaling
        assert should_include_quality(720, "1080p", allow_upscaling=True) is True
        assert should_include_quality(720, "1440p", allow_upscaling=True) is True
        assert should_include_quality(720, "2160p", allow_upscaling=True) is True

    def test_original_always_included(self):
        """Test that 'original' is always included."""
        assert should_include_quality(480, "original", allow_upscaling=False) is True
        assert should_include_quality(1080, "original", allow_upscaling=False) is True
        assert should_include_quality(2160, "original", allow_upscaling=False) is True

    def test_4k_source(self):
        """Test quality inclusion for 4K source."""
        # 4K should include all qualities
        assert should_include_quality(2160, "2160p", allow_upscaling=False) is True
        assert should_include_quality(2160, "1440p", allow_upscaling=False) is True
        assert should_include_quality(2160, "1080p", allow_upscaling=False) is True
        assert should_include_quality(2160, "720p", allow_upscaling=False) is True
        assert should_include_quality(2160, "480p", allow_upscaling=False) is True

    def test_low_quality_source(self):
        """Test quality inclusion for low quality source."""
        # 360p source should only include 360p and lower
        assert should_include_quality(360, "480p", allow_upscaling=False) is False
        assert should_include_quality(360, "720p", allow_upscaling=False) is False
        assert should_include_quality(360, "360p", allow_upscaling=False) is True
        assert should_include_quality(360, "240p", allow_upscaling=False) is True

    def test_non_standard_source_resolutions(self):
        """Test with non-standard source resolutions."""
        # 1366x768 (between 720p and 1080p)
        assert should_include_quality(768, "1080p", allow_upscaling=False) is False
        assert should_include_quality(768, "720p", allow_upscaling=False) is True
        assert should_include_quality(768, "480p", allow_upscaling=False) is True

        # 900p (between 720p and 1080p)
        assert should_include_quality(900, "1080p", allow_upscaling=False) is False
        assert should_include_quality(900, "720p", allow_upscaling=False) is True


class TestIntegrationScenarios:
    """Integration tests for real-world scenarios."""

    def test_4k_video_transcoding(self):
        """Test transcoding a 4K video."""
        source_width, source_height = 3840, 2160

        # Should create all qualities
        qualities = ["2160p", "1440p", "1080p", "720p", "480p", "360p"]

        for quality in qualities:
            assert should_include_quality(source_height, quality) is True
            width, height = calculate_target_resolution(source_width, source_height, quality)
            assert height <= source_height
            assert width <= source_width
            assert width % 2 == 0
            assert height % 2 == 0

    def test_weird_resolution_video(self):
        """Test transcoding a video with weird resolution."""
        # Example: 1366x768 (common laptop screen recording)
        source_width, source_height = 1366, 768

        # Should include qualities up to 720p
        assert should_include_quality(source_height, "720p") is True
        assert should_include_quality(source_height, "480p") is True
        assert should_include_quality(source_height, "1080p") is False

        # Calculate 720p - should maintain aspect ratio
        width, height = calculate_target_resolution(source_width, source_height, "720p")
        assert height == 720
        assert width % 2 == 0
        # Aspect ratio should be approximately 16:9
        assert abs((width / height) - (source_width / source_height)) < 0.01

    def test_vertical_video(self):
        """Test transcoding a vertical (portrait) video."""
        # TikTok/Instagram Reels style: 1080x1920
        source_width, source_height = 1080, 1920

        # Height is 1920, so should include up to 1440p (1440) but not 2160p
        assert should_include_quality(source_height, "1080p") is True
        assert should_include_quality(source_height, "1440p") is True
        assert should_include_quality(source_height, "2160p") is False

        # Calculate 720p - should maintain vertical aspect ratio
        width, height = calculate_target_resolution(source_width, source_height, "720p")
        assert height == 720
        # Width should be about 405 (720 * 9/16)
        expected_width = int(720 * (source_width / source_height))
        expected_width = expected_width if expected_width % 2 == 0 else expected_width - 1
        assert width == expected_width

    def test_original_resolution_preserved(self):
        """Test that original resolution is always preserved."""
        weird_resolutions = [
            (1366, 768),
            (1600, 900),
            (2560, 1080),  # Ultra-wide
            (1080, 1920),  # Vertical
            (720, 720),  # Square
        ]

        for source_width, source_height in weird_resolutions:
            width, height = calculate_target_resolution(source_width, source_height, "original")
            assert width == source_width
            assert height == source_height
