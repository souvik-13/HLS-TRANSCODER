# Speed/FPS Display Fix - Implementation Summary

## Issue

Video transcoding progress showed time-based progress but no speed/fps information in the TranscodingMonitor UI during actual transcoding (only visible in demo).

## Root Cause

The `AsyncFFmpegProcess` in `subprocess.py` was only parsing the time-based progress from FFmpeg's stderr output, but not extracting the fps (frames per second) or speed multiplier that FFmpeg also outputs.

## Solution Overview

Enhanced the entire callback chain to parse, propagate, and display speed/fps information from FFmpeg through all transcoding components.

## Files Modified

### 1. `hls_transcoder/executor/subprocess.py`

**Changes:**

- Added `FPS_PATTERN = re.compile(r"fps=\s*(\d+\.?\d*)")` (line 33)
- Added `SPEED_PATTERN = re.compile(r"speed=\s*(\d+\.?\d*)x")` (line 34)
- Changed progress callback signature from `Callable[[float], None]` to `Callable[[float, Optional[float]], None]` (line 39)
- Enhanced `_parse_progress()` method to extract both fps and speed from FFmpeg stderr (lines 178-197)
- Updated all callback invocations to pass `(progress, speed)` tuple

**FFmpeg Output Format:**

```
frame= 1234 fps= 30 q=28.0 size= 12345kB time=00:00:41.40 bitrate=2441.2kbits/s speed=1.23x
```

### 2. `hls_transcoder/models/tasks.py`

**Changes:**

- Added `speed: Optional[float] = None` field to `TranscodingTask` dataclass (line ~44)
- Field stores the processing speed (fps for video, speed multiplier for audio)
- All task types (VideoTask, AudioTask, SubtitleTask, SpriteTask) inherit this field

### 3. `hls_transcoder/transcoder/video.py`

**Changes:**

- Updated `transcode()` method callback signature to `Callable[[float, Optional[float]], None]` (line 114)
- Updated `transcode_all_qualities()` nested callback to accept speed parameter (line 582)
- Updated docstring to document speed parameter

### 4. `hls_transcoder/transcoder/audio.py`

**Changes:**

- Updated `extract()` method callback signature to `Callable[[float, Optional[float]], None]` (line 91)
- Updated `extract_all()` nested callback to accept and ignore speed parameter (line 313)
- Updated docstring to document speed parameter

### 5. `hls_transcoder/executor/parallel.py`

**Changes:**

- Updated `_do_video_transcode()` on_progress callback to accept and store speed (lines 453-455)
  ```python
  def on_progress(progress: float, speed: Optional[float] = None):
      task.progress = progress
      task.speed = speed
  ```
- Updated `_do_audio_extract()` on_progress callback similarly (lines 497-499)

### 6. `hls_transcoder/cli/main.py`

**Changes:**

- Updated monitor update call to pass speed to UI (lines 425-427)
  ```python
  monitor.update_task(
      monitor_id, progress=task.progress, speed=task.speed
  )
  ```

## How It Works

### Data Flow

```
FFmpeg stderr output
    ↓ (regex parsing)
AsyncFFmpegProcess._parse_progress()
    ↓ (callback with progress, speed)
VideoTranscoder.transcode() / AudioExtractor.extract()
    ↓ (nested callback)
ParallelExecutor._do_video_transcode() / _do_audio_extract()
    ↓ (stores in task)
TranscodingTask.speed field
    ↓ (polling loop)
CLI update_monitor()
    ↓ (UI update)
TranscodingMonitor.update_task()
    ↓ (display)
Progress bar with speed indicator
```

### Callback Signature Evolution

```python
# Before:
progress_callback: Optional[Callable[[float], None]] = None

# After:
progress_callback: Optional[Callable[[float, Optional[float]], None]] = None

# Usage:
def on_progress(progress: float, speed: Optional[float] = None):
    task.progress = progress
    task.speed = speed
```

## Testing

### Test Script

Created `test_speed_display.py` to verify the fix works with actual video files.

### Manual Testing

Run transcoding and verify UI shows speed information:

```bash
python -m hls_transcoder transcode video.mp4 --resolutions 480p
```

Expected output in UI:

- Video tasks: "30 fps" or similar
- Audio tasks: "1.2x" speed multiplier
- Progress bars update with real-time speed

### Demo Script

The existing `demo_progress_ui.py` already demonstrates speed display with simulated tasks.

## Key Points

1. **Optional Speed**: Speed is `Optional[float]` because:

   - Not all FFmpeg operations output fps/speed
   - Subtitle extraction doesn't use FFmpeg (no speed available)
   - Sprite generation may not report speed consistently

2. **Backward Compatibility**: All callbacks use default parameter `speed: Optional[float] = None` so existing code without speed still works.

3. **Regex Patterns**:

   - FPS pattern extracts frames per second: `fps= 30.5`
   - Speed pattern extracts multiplier: `speed= 1.23x`
   - Both patterns handle optional whitespace and decimals

4. **UI Display**: TranscodingMonitor already had the logic to display speed when provided, it was just missing the data.

## Verification Checklist

- [x] FFmpeg stderr parsing extracts fps and speed
- [x] Callback signatures updated throughout the chain
- [x] Task model has speed field to store the value
- [x] Parallel executor stores speed in tasks
- [x] CLI passes speed to monitor updates
- [x] No compilation errors
- [x] Test script created for manual verification

## Next Steps

1. Run the test script with an actual video file
2. Verify speed/fps appears in the UI during transcoding
3. Check that all task types (video, audio) show appropriate speed indicators
4. Confirm the speed updates in real-time during processing
