# Video Transcoder Implementation

## Overview

The Video Transcoder provides hardware-accelerated video transcoding with HLS output support. It automatically detects and uses available hardware encoders (NVENC, QSV, AMF, VideoToolbox, VAAPI) with fallback to software encoding.

## Features

### Core Capabilities

- ✅ **Hardware-Aware Encoding**: Automatically selects best available encoder
- ✅ **Multi-Hardware Support**: NVIDIA, Intel, AMD, Apple, VAAPI, Software
- ✅ **HLS Output**: Industry-standard adaptive streaming format
- ✅ **Quality Ladder**: Automatic quality variant generation
- ✅ **Progress Tracking**: Real-time progress callbacks
- ✅ **Async/Await**: Non-blocking transcoding operations
- ✅ **Parallel Processing**: Transcode multiple qualities concurrently

### Supported Hardware Encoders

| Hardware      | Encoder           | Platform      | Decoder      |
| ------------- | ----------------- | ------------- | ------------ |
| NVIDIA GPU    | h264_nvenc        | All           | CUDA         |
| Intel CPU/GPU | h264_qsv          | All           | QSV          |
| AMD GPU       | h264_amf          | Windows/Linux | D3D11VA      |
| Apple         | h264_videotoolbox | macOS         | VideoToolbox |
| Linux VA-API  | h264_vaapi        | Linux         | VAAPI        |
| Software      | libx264           | All           | Software     |

### Quality Presets

Standard quality ladder (16:9 aspect ratio):

| Preset | Resolution | Target Bitrate | Max Bitrate | Buffer Size |
| ------ | ---------- | -------------- | ----------- | ----------- |
| 2160p  | 3840x2160  | 12 Mbps        | 18 Mbps     | 24 Mbps     |
| 1440p  | 2560x1440  | 8 Mbps         | 12 Mbps     | 16 Mbps     |
| 1080p  | 1920x1080  | 5 Mbps         | 7.5 Mbps    | 10 Mbps     |
| 720p   | 1280x720   | 3 Mbps         | 4.5 Mbps    | 6 Mbps      |
| 480p   | 854x480    | 1.5 Mbps       | 2.25 Mbps   | 3 Mbps      |
| 360p   | 640x360    | 800 Kbps       | 1.2 Mbps    | 1.6 Mbps    |

## Usage

### Basic Transcoding

```python
from pathlib import Path
from hls_transcoder.transcoder import VideoTranscoder, QUALITY_PRESETS
from hls_transcoder.hardware import HardwareDetector
from hls_transcoder.inspector import MediaInspector

async def transcode_video():
    # Setup
    input_file = Path("input.mp4")
    output_dir = Path("output")

    # Detect hardware
    detector = HardwareDetector()
    hardware_info = detector.detect()

    # Inspect media
    inspector = MediaInspector()
    media_info = await inspector.inspect(input_file)
    video_stream = media_info.video_streams[0]

    # Create transcoder
    transcoder = VideoTranscoder(
        input_file=input_file,
        output_dir=output_dir,
        hardware_info=hardware_info,
        video_stream=video_stream,
    )

    # Transcode to 720p
    quality = QUALITY_PRESETS["720p"]
    output_path = await transcoder.transcode(quality)

    print(f"Output: {output_path}")
```

### With Progress Tracking

```python
from hls_transcoder.ui import TranscodingMonitor

async def transcode_with_progress():
    # ... setup code ...

    monitor = TranscodingMonitor()
    monitor.start()

    # Create progress task
    task = monitor.create_task("720p", "Transcoding 720p")
    monitor.start_task("720p")

    # Progress callback
    def update_progress(progress: float):
        monitor.update_task("720p", progress=progress, speed=30.0)

    # Transcode
    output_path = await transcoder.transcode(
        quality=QUALITY_PRESETS["720p"],
        progress_callback=update_progress,
    )

    monitor.complete_task("720p")
    monitor.stop()
```

### Quality Ladder Generation

```python
# Automatic quality ladder based on source
ladder = transcoder.calculate_quality_ladder()
# Returns all presets up to source resolution, sorted descending

# Filter specific qualities
ladder = transcoder.calculate_quality_ladder(
    max_qualities=["1080p", "720p", "480p"]
)
```

### Parallel Transcoding

```python
from hls_transcoder.transcoder import transcode_all_qualities

async def transcode_all():
    # ... setup code ...

    # Generate quality ladder
    qualities = transcoder.calculate_quality_ladder()

    # Progress callback
    def on_progress(quality_name: str, progress: float):
        print(f"{quality_name}: {progress*100:.1f}%")

    # Transcode all qualities (2 concurrent)
    results = await transcode_all_qualities(
        transcoder=transcoder,
        qualities=qualities,
        progress_callback=on_progress,
        max_concurrent=2,
    )

    # results = {"1080p": Path("output/1080p.m3u8"), ...}
```

### Custom Quality

```python
from hls_transcoder.transcoder import VideoQuality

# Define custom quality
custom_quality = VideoQuality(
    name="custom",
    height=900,
    bitrate=4000,    # kbps
    maxrate=6000,
    bufsize=8000,
)

output = await transcoder.transcode(custom_quality)
```

## Architecture

### VideoTranscoder Class

```python
class VideoTranscoder:
    """Main transcoder class."""

    def __init__(
        self,
        input_file: Path,
        output_dir: Path,
        hardware_info: HardwareInfo,
        video_stream: VideoStream,
    ):
        """Initialize transcoder."""

    async def transcode(
        self,
        quality: VideoQuality,
        progress_callback: Optional[Callable] = None,
        timeout: Optional[float] = None,
    ) -> Path:
        """Transcode to specific quality."""

    def calculate_quality_ladder(
        self,
        max_qualities: Optional[List[str]] = None,
    ) -> List[VideoQuality]:
        """Calculate appropriate quality ladder."""
```

### Command Building

The transcoder builds FFmpeg commands in multiple stages:

1. **Input Options**: Input file and hardware decoder
2. **Video Options**: Encoder-specific settings (bitrate, GOP, scaling)
3. **HLS Options**: Segment duration, playlist type, output pattern
4. **Output File**: Final playlist path

Example command (NVENC):

```bash
ffmpeg -y \
  -hwaccel cuda -hwaccel_output_format cuda \
  -i input.mp4 \
  -c:v h264_nvenc \
  -preset p4 \
  -rc:v vbr \
  -b:v 3000k \
  -maxrate:v 4500k \
  -bufsize:v 6000k \
  -g 60 \
  -keyint_min 60 \
  -sc_threshold 0 \
  -vf scale=1280:720:force_original_aspect_ratio=decrease,pad=1280:720:(ow-iw)/2:(oh-ih)/2 \
  -f hls \
  -hls_time 6 \
  -hls_segment_filename output/720p_%03d.ts \
  -hls_playlist_type vod \
  -hls_flags independent_segments \
  -hls_segment_type mpegts \
  output/720p.m3u8
```

### Hardware-Specific Options

#### NVIDIA NVENC

```python
[
    "-c:v", "h264_nvenc",
    "-preset", "p4",           # p1 (fastest) to p7 (slowest)
    "-rc:v", "vbr",            # Variable bitrate
    "-b:v", f"{bitrate}k",
    "-maxrate:v", f"{maxrate}k",
    "-bufsize:v", f"{bufsize}k",
    "-g", str(gop_size),
    "-vf", f"scale={width}:{height}:...",
]
```

#### Intel QSV

```python
[
    "-c:v", "h264_qsv",
    "-preset", "medium",        # fast, medium, slow, veryslow
    "-b:v", f"{bitrate}k",
    "-vf", f"scale_qsv={width}:{height}",
]
```

#### AMD AMF

```python
[
    "-c:v", "h264_amf",
    "-quality", "balanced",     # speed, balanced, quality
    "-rc", "vbr_peak",
    "-b:v", f"{bitrate}k",
]
```

#### Software (libx264)

```python
[
    "-c:v", "libx264",
    "-preset", "medium",        # ultrafast to veryslow
    "-b:v", f"{bitrate}k",
    "-crf", "23",              # Optional quality-based
]
```

## HLS Output Structure

```
output/
├── 1080p.m3u8              # Playlist
├── 1080p_000.ts            # Segment 1
├── 1080p_001.ts            # Segment 2
├── ...
├── 720p.m3u8
├── 720p_000.ts
├── ...
└── master.m3u8             # Master playlist (future)
```

### HLS Playlist Example

```m3u8
#EXTM3U
#EXT-X-VERSION:3
#EXT-X-TARGETDURATION:6
#EXT-X-MEDIA-SEQUENCE:0
#EXT-X-PLAYLIST-TYPE:VOD
#EXTINF:6.000000,
720p_000.ts
#EXTINF:6.000000,
720p_001.ts
...
#EXT-X-ENDLIST
```

## Integration with Other Modules

### With Progress Tracking

```python
from hls_transcoder.ui import TranscodingMonitor

monitor = TranscodingMonitor()
monitor.start()

# Create tasks
for quality in qualities:
    monitor.create_task(quality.name, f"{quality.name} Variant")

# Transcode with monitoring
for quality in qualities:
    monitor.start_task(quality.name)

    def progress(p: float):
        monitor.update_task(quality.name, progress=p)

    await transcoder.transcode(quality, progress_callback=progress)
    monitor.complete_task(quality.name)

monitor.stop()
```

### With Hardware Detection

```python
from hls_transcoder.hardware import HardwareDetector

# Detect hardware
detector = HardwareDetector()
hardware_info = detector.detect()

# Check what's available
if hardware_info.has_hardware_encoding:
    encoder = hardware_info.selected_encoder
    print(f"Using: {encoder.display_name}")
else:
    print("Using software encoding")

# Create transcoder with hardware info
transcoder = VideoTranscoder(..., hardware_info=hardware_info)
```

### With Media Inspector

```python
from hls_transcoder.inspector import MediaInspector

inspector = MediaInspector()
media_info = await inspector.inspect(input_file)

# Use video stream info
video_stream = media_info.video_streams[0]
print(f"Source: {video_stream.resolution} @ {video_stream.fps}fps")

# Calculate appropriate quality ladder
transcoder = VideoTranscoder(..., video_stream=video_stream)
ladder = transcoder.calculate_quality_ladder()
```

## Performance Considerations

### Hardware vs Software

Typical transcoding speeds (1080p source):

- **NVIDIA NVENC**: 100-300 fps (3-10x realtime)
- **Intel QSV**: 80-200 fps (2.5-6x realtime)
- **AMD AMF**: 90-250 fps (3-8x realtime)
- **Apple VideoToolbox**: 70-150 fps (2-5x realtime)
- **Software (x264)**: 20-80 fps (0.6-2.5x realtime)

### Concurrent Transcoding

For optimal performance:

- **1-2 concurrent**: Best for hardware encoders (avoid saturation)
- **2-4 concurrent**: Good for software encoding (utilize CPU cores)
- **Memory**: ~500MB-1GB per concurrent task
- **Disk I/O**: Ensure fast storage for output segments

### GOP Size Recommendations

- **Live Streaming**: 1-2 seconds (30-60 frames @ 30fps)
- **VOD**: 2-4 seconds (60-120 frames @ 30fps)
- **Long-form**: 6-10 seconds (180-300 frames @ 30fps)

Current default: 2 seconds (configurable via `TranscodingOptions.keyframe_interval`)

## Testing

Run video transcoder tests:

```bash
poetry run pytest tests/test_video.py -v
```

Test coverage includes:

- Quality preset validation
- Command building for all encoders
- Hardware decoder selection
- HLS option generation
- Quality ladder calculation
- Async transcoding with mocked FFmpeg
- Progress callback integration
- Error handling and recovery
- Parallel transcoding
- Concurrent limit enforcement

## Error Handling

### Common Errors

```python
from hls_transcoder.utils import TranscodingError, FFmpegError

try:
    output = await transcoder.transcode(quality)
except FFmpegError as e:
    # FFmpeg command failed
    print(f"FFmpeg error: {e}")
    print(f"Command: {e.command}")
    print(f"Stderr: {e.stderr}")
except TranscodingError as e:
    # High-level transcoding error
    print(f"Transcoding failed: {e}")
```

### Automatic Hardware Fallback

If hardware encoding fails, the transcoder automatically falls back to software:

```python
# Transcoder automatically handles this internally
hardware_info = detector.detect()  # May have no HW encoder
transcoder = VideoTranscoder(..., hardware_info=hardware_info)

# If hardware_info.selected_encoder is None, uses libx264
output = await transcoder.transcode(quality)
```

## Best Practices

1. **Always Inspect Media First**: Use `MediaInspector` to get accurate source info
2. **Calculate Quality Ladder**: Don't hardcode qualities, use `calculate_quality_ladder()`
3. **Use Progress Callbacks**: Provide user feedback for long operations
4. **Limit Concurrency**: 1-2 concurrent for hardware, 2-4 for software
5. **Handle Errors**: Always catch `TranscodingError` and `FFmpegError`
6. **Clean Up**: Use async context managers or try/finally blocks
7. **Monitor Resources**: Watch GPU/CPU usage and adjust concurrency
8. **Test Output**: Validate HLS playlists and segments after transcoding

## Future Enhancements

- [ ] Two-pass encoding support
- [ ] VP9/AV1 encoder support
- [ ] HDR/10-bit encoding
- [ ] Variable segment duration
- [ ] Thumbnail preview generation
- [ ] Audio passthrough option
- [ ] Subtitle burn-in
- [ ] Dynamic bitrate adjustment
- [ ] Codec auto-detection
- [ ] Quality-based encoding (CRF mode)

## See Also

- [Hardware Detection](./HARDWARE_DETECTION.md) - Hardware encoder detection
- [Media Inspector](./MEDIA_INSPECTOR.md) - Media file analysis
- [Progress Tracking](./PROGRESS_TRACKING.md) - Progress monitoring
- [Async Subprocess](./ASYNC_SUBPROCESS.md) - FFmpeg execution
