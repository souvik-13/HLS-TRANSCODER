"""
Tests for hardware detection module.
"""

import pytest

from hls_transcoder.hardware import HardwareDetector, HardwareInfo
from hls_transcoder.hardware.detector import HardwareType, EncoderInfo
from hls_transcoder.utils import HardwareError


class TestEncoderInfo:
    """Test EncoderInfo dataclass."""

    def test_create_encoder_info(self):
        """Test creating encoder info."""
        encoder = EncoderInfo(
            name="h264_nvenc",
            hardware_type=HardwareType.NVIDIA,
            display_name="NVIDIA NVENC H.264",
            available=True,
        )

        assert encoder.name == "h264_nvenc"
        assert encoder.hardware_type == HardwareType.NVIDIA
        assert encoder.display_name == "NVIDIA NVENC H.264"
        assert encoder.available is True
        assert encoder.tested is False
        assert encoder.error is None


class TestHardwareInfo:
    """Test HardwareInfo dataclass."""

    def test_hardware_info_with_encoders(self):
        """Test hardware info with available encoders."""
        encoders = [
            EncoderInfo(
                name="h264_nvenc",
                hardware_type=HardwareType.NVIDIA,
                display_name="NVIDIA NVENC H.264",
                available=True,
            ),
            EncoderInfo(
                name="libx264",
                hardware_type=HardwareType.SOFTWARE,
                display_name="Software H.264",
                available=True,
            ),
        ]

        hardware_info = HardwareInfo(
            detected_type=HardwareType.NVIDIA,
            available_encoders=encoders,
        )

        assert hardware_info.detected_type == HardwareType.NVIDIA
        assert len(hardware_info.available_encoders) == 2
        assert hardware_info.has_hardware_encoding is True

    def test_available_hardware_types(self):
        """Test getting available hardware types."""
        encoders = [
            EncoderInfo(
                name="h264_nvenc",
                hardware_type=HardwareType.NVIDIA,
                display_name="NVIDIA NVENC H.264",
                available=True,
            ),
            EncoderInfo(
                name="h264_qsv",
                hardware_type=HardwareType.INTEL,
                display_name="Intel QSV H.264",
                available=True,
            ),
            EncoderInfo(
                name="libx264",
                hardware_type=HardwareType.SOFTWARE,
                display_name="Software H.264",
                available=True,
            ),
        ]

        hardware_info = HardwareInfo(
            detected_type=HardwareType.NVIDIA,
            available_encoders=encoders,
        )

        hw_types = hardware_info.available_hardware_types
        assert HardwareType.NVIDIA in hw_types
        assert HardwareType.INTEL in hw_types
        assert HardwareType.SOFTWARE not in hw_types

    def test_get_encoder(self):
        """Test getting encoder by type."""
        encoders = [
            EncoderInfo(
                name="h264_nvenc",
                hardware_type=HardwareType.NVIDIA,
                display_name="NVIDIA NVENC H.264",
                available=True,
            ),
        ]

        hardware_info = HardwareInfo(
            detected_type=HardwareType.NVIDIA,
            available_encoders=encoders,
        )

        nvidia_encoder = hardware_info.get_encoder(HardwareType.NVIDIA)
        assert nvidia_encoder is not None
        assert nvidia_encoder.name == "h264_nvenc"

        intel_encoder = hardware_info.get_encoder(HardwareType.INTEL)
        assert intel_encoder is None


@pytest.mark.asyncio
class TestHardwareDetector:
    """Test HardwareDetector class."""

    def test_create_detector(self):
        """Test creating detector instance."""
        detector = HardwareDetector()
        assert detector is not None

    @pytest.mark.asyncio
    async def test_detect_basic(self):
        """Test basic hardware detection."""
        detector = HardwareDetector()

        try:
            hardware_info = await detector.detect()

            print(hardware_info)

            # Should have some encoders
            assert len(hardware_info.available_encoders) > 0

            # Should detect a hardware type
            assert hardware_info.detected_type is not None

            # Software encoders should always be available
            software_encoders = [
                enc
                for enc in hardware_info.available_encoders
                if enc.hardware_type == HardwareType.SOFTWARE and enc.available
            ]
            assert len(software_encoders) > 0

        except HardwareError as e:
            # If FFmpeg is not installed, skip this test
            if "FFmpeg not found" in str(e):
                pytest.skip("FFmpeg not installed")
            raise

    @pytest.mark.asyncio
    async def test_detect_with_preference(self):
        """Test detection with hardware preference."""
        detector = HardwareDetector()

        try:
            # Try software preference (should always work)
            hardware_info = await detector.detect(prefer="software")

            assert hardware_info.detected_type == HardwareType.SOFTWARE

        except HardwareError as e:
            if "FFmpeg not found" in str(e):
                pytest.skip("FFmpeg not installed")
            raise

    @pytest.mark.asyncio
    async def test_detect_caching(self):
        """Test that detection results are cached."""
        detector = HardwareDetector()

        try:
            # First detection
            hardware_info1 = await detector.detect()

            # Second detection should use cache
            hardware_info2 = await detector.detect()

            assert hardware_info1 is hardware_info2

            # Clear cache and detect again
            detector.clear_cache()
            hardware_info3 = await detector.detect()

            assert hardware_info3 is not hardware_info1

        except HardwareError as e:
            if "FFmpeg not found" in str(e):
                pytest.skip("FFmpeg not installed")
            raise

    @pytest.mark.asyncio
    @pytest.mark.slow
    async def test_detect_with_testing(self):
        """Test detection with encoder testing (slow)."""
        detector = HardwareDetector()

        try:
            # This will actually test encoders
            hardware_info = await detector.detect(test_encoding=True)

            # Check if any encoders were tested
            tested_encoders = [enc for enc in hardware_info.available_encoders if enc.tested]

            # Note: May be 0 if no hardware encoders available
            # This is fine - just verifies the testing code path works

        except HardwareError as e:
            if "FFmpeg not found" in str(e):
                pytest.skip("FFmpeg not installed")
            raise


def test_hardware_type_enum():
    """Test HardwareType enum values."""
    assert HardwareType.NVIDIA.value == "nvidia"
    assert HardwareType.INTEL.value == "intel"
    assert HardwareType.AMD.value == "amd"
    assert HardwareType.APPLE.value == "apple"
    assert HardwareType.VAAPI.value == "vaapi"
    assert HardwareType.SOFTWARE.value == "software"
