"""
HLS Video Transcoder

A tool for converting video files to HLS format with hardware acceleration
and parallel processing.
"""

__version__ = "0.1.0"
__author__ = "Souvik Karmakar"
__email__ = "souvikk431@gmail.com"

from hls_transcoder.models import (
    AudioStream,
    MediaInfo,
    TaskPlan,
    TranscodingResults,
    VideoStream,
)
from hls_transcoder.utils import (
    ConfigurationError,
    TranscoderError,
    TranscodingError,
    get_logger,
    setup_logger,
)

__all__ = [
    "__version__",
    # Models
    "AudioStream",
    "MediaInfo",
    "TaskPlan",
    "TranscodingResults",
    "VideoStream",
    # Utils
    "ConfigurationError",
    "TranscoderError",
    "TranscodingError",
    "get_logger",
    "setup_logger",
]
