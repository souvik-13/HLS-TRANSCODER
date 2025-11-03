"""
Transcoding modules for video, audio, and subtitles.
"""

from .audio import (
    AUDIO_QUALITY_PRESETS,
    AudioExtractor,
    AudioExtractionOptions,
    AudioQuality,
)
from .subtitle import (
    SubtitleExtractor,
    SubtitleExtractionOptions,
    extract_all_subtitles,
)
from .video import (
    QUALITY_PRESETS,
    TranscodingOptions,
    VideoQuality,
    VideoTranscoder,
    transcode_all_qualities,
)

__all__ = [
    # Video
    "VideoTranscoder",
    "VideoQuality",
    "QUALITY_PRESETS",
    "TranscodingOptions",
    "transcode_all_qualities",
    # Audio
    "AudioExtractor",
    "AudioQuality",
    "AUDIO_QUALITY_PRESETS",
    "AudioExtractionOptions",
    # Subtitle
    "SubtitleExtractor",
    "SubtitleExtractionOptions",
    "extract_all_subtitles",
]
