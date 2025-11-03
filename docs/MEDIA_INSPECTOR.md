# Media Inspector Module

## Overview

The Media Inspector module provides functionality to analyze media files and extract detailed information about their streams and metadata using FFprobe.

## Features

### Core Functionality

- **Async FFprobe Integration**: Non-blocking media file inspection
- **Video Stream Analysis**: Extract codec, resolution, fps, bitrate, pixel format, color space
- **Audio Stream Analysis**: Extract codec, channels, sample rate, bitrate, language
- **Subtitle Stream Analysis**: Extract codec, language, title
- **Format Metadata**: Extract container format, duration, file size, overall bitrate
- **Validation**: Check media compatibility for transcoding

### Key Components

#### MediaInspector Class

Main class for media file inspection:

```python
from hls_transcoder.inspector import MediaInspector, get_media_inspector
from pathlib import Path

# Create inspector
inspector = MediaInspector()  # Uses default 'ffprobe' command
# or
inspector = MediaInspector(ffprobe_path="/usr/bin/ffprobe")

# Inspect media file
media_info = await inspector.inspect(Path("video.mp4"))

# Access stream information
print(f"Resolution: {media_info.primary_video.resolution}")
print(f"Duration: {media_info.duration}s")
print(f"Audio tracks: {len(media_info.audio_streams)}")

# Validate for transcoding
warnings = inspector.validate_for_transcoding(media_info)
if warnings:
    print("Validation warnings:", warnings)
```

#### Global Instance Pattern

For convenience, use the global inspector instance:

```python
from hls_transcoder.inspector import get_media_inspector

inspector = get_media_inspector()
media_info = await inspector.inspect(Path("video.mp4"))
```

## Data Models

### MediaInfo

Complete media file information:

```python
@dataclass
class MediaInfo:
    format: FormatInfo
    video_streams: list[VideoStream]
    audio_streams: list[AudioStream]
    subtitle_streams: list[SubtitleStream]
    duration: float
    size: int
    bitrate: int
```

### VideoStream

Video stream properties:

```python
@dataclass
class VideoStream:
    index: int
    codec: str
    codec_long: str
    width: int
    height: int
    fps: float
    bitrate: int
    duration: float
    pix_fmt: str
    color_space: Optional[str] = None
```

### AudioStream

Audio stream properties:

```python
@dataclass
class AudioStream:
    index: int
    codec: str
    codec_long: str
    language: str
    channels: int
    sample_rate: int
    bitrate: int
    duration: float
```

### SubtitleStream

Subtitle stream properties:

```python
@dataclass
class SubtitleStream:
    index: int
    codec: str
    language: str
    title: Optional[str] = None
    forced: bool = False
```

## Usage Examples

### Basic Inspection

```python
from pathlib import Path
from hls_transcoder.inspector import get_media_inspector

async def inspect_video(video_path: Path):
    inspector = get_media_inspector()

    try:
        media_info = await inspector.inspect(video_path)

        # Access video information
        video = media_info.primary_video
        if video:
            print(f"Video: {video.codec} {video.width}x{video.height} @ {video.fps}fps")

        # Access audio information
        for audio in media_info.audio_streams:
            print(f"Audio: {audio.codec} {audio.channels}ch @ {audio.sample_rate}Hz ({audio.language})")

        # Access subtitle information
        for subtitle in media_info.subtitle_streams:
            print(f"Subtitle: {subtitle.codec} ({subtitle.language})")

    except MediaInspectionError as e:
        print(f"Inspection failed: {e}")
```

### Validation

```python
async def validate_video(video_path: Path):
    inspector = get_media_inspector()
    media_info = await inspector.inspect(video_path)

    # Validate for transcoding
    warnings = inspector.validate_for_transcoding(media_info)

    if warnings:
        print("Validation warnings:")
        for warning in warnings:
            print(f"  - {warning}")
    else:
        print("Media file is valid for transcoding")
```

### Stream Selection

```python
async def select_streams(video_path: Path):
    inspector = get_media_inspector()
    media_info = await inspector.inspect(video_path)

    # Get primary video stream
    video = media_info.primary_video

    # Get audio by language
    english_audio = media_info.get_audio_by_language("eng")
    spanish_audio = media_info.get_audio_by_language("spa")

    # Get subtitles by language
    english_subs = media_info.get_subtitle_by_language("eng")

    # Check what's available
    print(f"Has video: {media_info.has_video}")
    print(f"Has audio: {media_info.has_audio}")
    print(f"Has subtitles: {media_info.has_subtitles}")
```

## Error Handling

The inspector raises `MediaInspectionError` for various failure conditions:

- File not found
- Not a regular file (e.g., directory)
- FFprobe execution failure
- Invalid FFprobe output
- JSON parsing errors

```python
from hls_transcoder.utils import MediaInspectionError

try:
    media_info = await inspector.inspect(video_path)
except MediaInspectionError as e:
    logger.error(f"Failed to inspect media: {e}")
    # Handle error appropriately
```

## Implementation Details

### FFprobe Integration

The inspector runs FFprobe as an async subprocess:

```bash
ffprobe -v quiet -print_format json -show_format -show_streams input.mp4
```

This returns JSON output containing:

- Format information (container, duration, size, bitrate)
- Stream information (video, audio, subtitle streams)
- Metadata tags (language, title, etc.)

### Async Design

All inspection is performed asynchronously to avoid blocking:

```python
async def _run_ffprobe(self, input_file: Path) -> dict:
    """Run ffprobe and return parsed JSON output."""
    process = await asyncio.create_subprocess_exec(
        self._ffprobe_path,
        "-v", "quiet",
        "-print_format", "json",
        "-show_format",
        "-show_streams",
        str(input_file),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )

    stdout, stderr = await process.communicate()
    # ... parse and return
```

### Validation Checks

The `validate_for_transcoding()` method performs these checks:

1. **Video streams present**: Warns if no video streams found
2. **Valid resolution**: Warns if width or height is 0
3. **Valid frame rate**: Warns if fps is 0
4. **Codec support**: Warns about potentially problematic codecs
5. **Audio streams present**: Warns if no audio streams found
6. **File size**: Warns if file size is 0 bytes
7. **Duration**: Warns if duration is 0 seconds

## Testing

The module includes comprehensive tests:

- **21 test cases** covering all functionality
- **Async test support** using pytest-asyncio
- **Mocked FFprobe** responses for unit testing
- **Edge case handling** (invalid FPS, missing languages, minimal data)
- **Validation testing** for all warning conditions

Run tests:

```bash
poetry run pytest tests/test_inspector.py -v
```

## Dependencies

- **FFprobe**: Must be installed on the system (part of FFmpeg)
- **asyncio**: For async subprocess execution
- **json**: For parsing FFprobe output
- **pathlib**: For file path handling

## Performance Considerations

- **Async execution**: Non-blocking, can inspect multiple files concurrently
- **Subprocess overhead**: FFprobe startup takes ~10-50ms per file
- **JSON parsing**: Negligible overhead for typical media files
- **Global instance**: Reuse inspector instance to avoid repeated initialization

## Future Enhancements

Potential improvements:

1. **Caching**: Cache inspection results for recently inspected files
2. **Batch inspection**: Inspect multiple files in parallel
3. **Partial inspection**: Option to skip certain stream types
4. **Custom FFprobe args**: Allow passing additional FFprobe arguments
5. **Stream filtering**: Filter streams by codec, language, or other criteria
6. **HDR detection**: Detect and parse HDR metadata (HDR10, Dolby Vision)
7. **Chapter information**: Extract chapter markers if present

## See Also

- [Hardware Detection](./docs/HARDWARE_DETECTION.md) - Hardware acceleration detection
- [Resolution Handling](./docs/RESOLUTION_HANDLING.md) - Resolution management
- [Data Models](../hls_transcoder/models/media.py) - Media data structures
