# Audio Auto Channels & Sample Rate Implementation

## Summary

Implemented support for `auto` values in audio configuration to preserve original channel count and sample rate from source media, instead of always downmixing to stereo.

## Changes Made

### 1. Configuration Model (`hls_transcoder/config/models.py`)

**Updated `AudioConfig` class:**

- Changed `channels` field type from `int` to `int | str` to support "auto"
- Changed `sample_rate` field type from `int` to `int | str` to support "auto"
- Added validators for both fields to accept "auto" or valid numeric values
- Default values set to "auto" for both fields

```python
channels: int | str = Field(default="auto", ...)
sample_rate: int | str = Field(default="auto", ...)
```

### 2. Audio Transcoder (`hls_transcoder/transcoder/audio.py`)

**Updated `_get_audio_options()` method:**

- Modified to handle "auto" values (represented internally as 0)
- When `quality.sample_rate == 0`: use source stream's sample rate
- When `quality.channels == 0`: use source stream's channel count
- Added debug logging to indicate preservation vs conversion

```python
# Handle sample rate - use source if quality.sample_rate is 0 (auto)
target_sample_rate = quality.sample_rate if quality.sample_rate > 0 else source.sample_rate

# Handle channel conversion - use source if quality.channels is 0 (auto)
target_channels = quality.channels if quality.channels > 0 else source.channels
```

### 3. Executor (`hls_transcoder/executor/parallel.py`)

**Updated `_do_audio_extract()` method:**

- Parse config values for channels and sample_rate
- Convert "auto" string to 0 (sentinel value meaning "use source")
- Create AudioQuality object with these values

```python
if isinstance(self.config.audio.channels, str) and self.config.audio.channels.lower() == "auto":
    channels = 0  # 0 means "use source channels"
else:
    channels = int(self.config.audio.channels)
```

### 4. Configuration Files

**Updated `.hls-transcoder.yaml`:**

- Changed default `channels` from `2` to `auto`
- Changed default `sample_rate` from `48000` to `auto`
- Added comprehensive documentation explaining options and trade-offs

**Updated `hls_transcoder/config/defaults.yaml`:**

- Changed defaults to `auto` with explanatory comments

### 5. CLI Output Validation (`hls_transcoder/cli/main.py`)

**Fixed audio track validation warning:**

- Added import for `AudioTrackResult`
- Fixed results object creation to include populated `audio_track_results` list
- Added conversion from `AudioTrackInfo` to `AudioTrackResult` with proper fields
- Calculated segment sizes for audio tracks

## Behavior

### Before Changes

- **Always** downmixed audio to stereo (2 channels)
- **Always** resampled to 48000 Hz
- Example: 6-channel 5.1 surround → 2-channel stereo

### After Changes

- **Default (auto)**: Preserves source channel count and sample rate
- **Configurable**: Can still explicitly set to 2 channels or 48000 Hz if desired
- Example with auto: 6-channel 5.1 surround → 6-channel 5.1 surround

## Configuration Options

### Channels

- `auto` (default): Preserve original channel count from source
- `1`: Downmix to mono
- `2`: Downmix to stereo (smaller files, wider compatibility)
- `6`: 5.1 surround sound (requires compatible source)
- `8`: 7.1 surround sound (requires compatible source)

### Sample Rate

- `auto` (default): Preserve original sample rate from source
- `44100`: CD quality
- `48000`: Standard (DVD/Blu-ray)
- `96000`: High-resolution audio

## Trade-offs

### Preserving Channels (auto)

**Pros:**

- Best audio quality (no downmixing loss)
- Preserves surround sound for compatible systems
- Respects original content creator's intent

**Cons:**

- Larger file sizes (5.1 = ~3x bandwidth of stereo)
- Not all HLS clients support >2 channels
- Mobile devices typically only have stereo output

### Downmixing to Stereo (explicit 2)

**Pros:**

- Smaller file sizes
- Universal compatibility
- Better for mobile/web streaming

**Cons:**

- Loss of surround sound information
- May affect audio quality for audiophiles

## Testing

Created test script `test_auto_channels.py` to verify:

- ✓ Auto channels remain as "auto" string
- ✓ Numeric channels remain as int
- ✓ Auto sample_rate remains as "auto" string
- ✓ Numeric sample_rate remains as int
- ✓ Default values are "auto"

## Validation Fix

Fixed warning "No audio tracks to validate" that appeared even when audio was successfully transcoded:

- Root cause: Results object created with empty `audio_tracks=[]` list
- Solution: Convert `AudioTrackInfo` objects to `AudioTrackResult` objects with proper validation fields
- Now correctly reports number of audio tracks and validates them

## Recommendation

**For general HLS streaming**: Keep `channels: auto` and `sample_rate: auto` (new defaults)

- Respects source quality
- Modern devices increasingly support multi-channel audio
- Users can override if needed for specific use cases

**For maximum compatibility**: Override to `channels: 2` and `sample_rate: 48000`

- Ensures playback on all devices
- Smaller file sizes
- Better for low-bandwidth scenarios
