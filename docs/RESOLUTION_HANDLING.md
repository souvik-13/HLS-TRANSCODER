# Resolution Handling Guide

## Overview

The HLS Transcoder now supports advanced resolution handling including:

- **4K (2160p) support** - Full Ultra HD transcoding
- **Non-standard resolution preservation** - Always keeps original resolution
- **Smart quality ladder** - Automatically selects appropriate qualities based on source

## Supported Resolutions

### Standard Quality Labels

| Quality         | Resolution        | Typical Use Case                  |
| --------------- | ----------------- | --------------------------------- |
| 2160p (4K)      | 3840x2160         | Ultra HD content                  |
| 1440p (2K)      | 2560x1440         | High-end gaming, premium content  |
| 1080p (Full HD) | 1920x1080         | Standard HD video                 |
| 720p (HD)       | 1280x720          | HD streaming                      |
| 480p (SD)       | 854x480           | Standard definition               |
| 360p            | 640x360           | Low bandwidth                     |
| 240p            | 426x240           | Minimum quality                   |
| **original**    | Source dimensions | Preserves exact source resolution |

## Configuration Profiles

### Ultra Profile (4K Content)

```yaml
ultra:
  - quality: 2160p
    bitrate: 20000k
    crf: 18
  - quality: 1440p
    bitrate: 16000k
    crf: 20
  - quality: 1080p
    bitrate: 10000k
    crf: 20
  - quality: 720p
    bitrate: 6000k
    crf: 23
  - quality: 480p
    bitrate: 3000k
    crf: 26
  - quality: 360p
    bitrate: 1000k
    crf: 28
```

### High Profile (1440p/1080p Content)

```yaml
high:
  - quality: 1440p
    bitrate: 12000k
    crf: 22
  - quality: 1080p
    bitrate: 8000k
    crf: 20
  - quality: 720p
    bitrate: 5000k
    crf: 23
  - quality: 480p
    bitrate: 2500k
    crf: 26
  - quality: 360p
    bitrate: 1000k
    crf: 28
```

## Non-Standard Resolution Handling

### What are non-standard resolutions?

Any resolution that doesn't match the standard labels above, such as:

- **1366x768** - Common laptop screen recording
- **1600x900** - 16:9 variant
- **2560x1080** - Ultra-wide (21:9)
- **1080x1920** - Vertical video (TikTok/Instagram Reels)
- **1536x864** - Between 720p and 1080p
- **720x720** - Square video (Instagram)

### How are they handled?

1. **Original Resolution Always Preserved**

   - A variant with `quality: original` keeps the exact source dimensions
   - No upscaling or downscaling applied
   - Maintains source aspect ratio perfectly

2. **Smart Downscaling**
   - Target resolutions are calculated to maintain aspect ratio
   - Output dimensions are always even (required for most codecs)
   - No upscaling by default (prevents quality loss)

### Examples

#### Example 1: Laptop Screen Recording (1366x768)

**Source:** 1366x768 (weird 16:9 variant)

**Generated Variants:**

- `original`: 1366x768 (exact source)
- `720p`: 1280x720 (standard, slightly smaller)
- `480p`: 854x480
- `360p`: 640x360

**Excluded:** 1080p, 1440p, 2160p (would require upscaling)

#### Example 2: Ultra-Wide Video (2560x1080)

**Source:** 2560x1080 (21:9 aspect ratio)

**Generated Variants:**

- `original`: 2560x1080 (exact source)
- `720p`: 1706x720 (maintains 21:9 ratio)
- `480p`: 1138x480 (maintains 21:9 ratio)
- `360p`: 854x360 (maintains 21:9 ratio)

**Excluded:** 1080p and higher (source is only 1080 height)

#### Example 3: Vertical Video (1080x1920)

**Source:** 1080x1920 (9:16 aspect ratio - TikTok/Reels)

**Generated Variants:**

- `original`: 1080x1920 (exact source)
- `1440p`: 810x1440 (maintains 9:16 ratio)
- `1080p`: 608x1080 (maintains 9:16 ratio)
- `720p`: 405x720 (maintains 9:16 ratio)
- `480p`: 270x480 (maintains 9:16 ratio)

**Note:** Height of 1920 allows variants up to 1440p

#### Example 4: 4K Video (3840x2160)

**Source:** 3840x2160 (standard 4K)

**Generated Variants:**

- `original`: 3840x2160 (exact source)
- `2160p`: 3840x2160 (same as original)
- `1440p`: 2560x1440
- `1080p`: 1920x1080
- `720p`: 1280x720
- `480p`: 854x480
- `360p`: 640x360

**All qualities included** - source is highest resolution

## API Usage

### Helper Functions

```python
from hls_transcoder.utils import (
    calculate_target_resolution,
    should_include_quality,
    get_quality_from_height,
    get_standard_resolutions,
)

# Detect quality from height
quality = get_quality_from_height(1366)  # Returns "1080p"
quality = get_quality_from_height(1366, exact_match=True)  # Returns None

# Calculate target resolution maintaining aspect ratio
width, height = calculate_target_resolution(1366, 768, "720p")
# Returns: (1280, 720) - maintains aspect ratio

# Check if quality should be included
should_include = should_include_quality(720, "1080p")  # False (no upscaling)
should_include = should_include_quality(2160, "1080p")  # True

# Get standard resolutions
resolutions = get_standard_resolutions()
# Returns: {"2160p": (3840, 2160), "1440p": (2560, 1440), ...}
```

### Creating Custom Quality Variants

```python
from hls_transcoder.config import QualityVariant

# Standard quality
variant = QualityVariant(
    quality="1080p",
    bitrate="8000k",
    crf=20
)

# Custom resolution (non-standard)
variant = QualityVariant(
    quality="original",
    bitrate="10000k",
    crf=20,
    width=1366,
    height=768
)
```

## Best Practices

### 1. Always Include Original

```python
# Add original resolution to preserve source quality
variants = [
    QualityVariant(quality="original", bitrate="auto", crf=18),
    QualityVariant(quality="1080p", bitrate="8000k", crf=20),
    # ... other qualities
]
```

### 2. Don't Force Upscaling

```python
# Only include qualities at or below source resolution
if should_include_quality(source_height, target_quality, allow_upscaling=False):
    # Include this quality
    pass
```

### 3. Maintain Aspect Ratio

```python
# Always use calculate_target_resolution for custom sources
target_width, target_height = calculate_target_resolution(
    source_width, source_height, target_quality
)
```

### 4. Consider Bandwidth

For non-standard resolutions, adjust bitrate based on pixel count:

```python
# Calculate pixel ratio compared to 1080p
source_pixels = source_width * source_height
standard_1080p_pixels = 1920 * 1080
pixel_ratio = source_pixels / standard_1080p_pixels

# Adjust bitrate accordingly
adjusted_bitrate = int(8000 * pixel_ratio)  # 8000k base for 1080p
```

## Quality Selection Algorithm

### Automatic Quality Ladder

```python
def generate_quality_ladder(source_width: int, source_height: int) -> list:
    """
    Generate appropriate quality ladder for source video.
    """
    variants = []

    # Always include original
    variants.append({
        "quality": "original",
        "width": source_width,
        "height": source_height,
    })

    # Add standard qualities that don't exceed source
    for quality in ["2160p", "1440p", "1080p", "720p", "480p", "360p"]:
        if should_include_quality(source_height, quality):
            target_width, target_height = calculate_target_resolution(
                source_width, source_height, quality
            )
            variants.append({
                "quality": quality,
                "width": target_width,
                "height": target_height,
            })

    return variants
```

## Testing

Comprehensive tests cover:

- ✅ Standard resolutions (240p to 4K)
- ✅ Non-standard resolutions (1366x768, 1600x900, etc.)
- ✅ Ultra-wide videos (21:9)
- ✅ Vertical videos (9:16)
- ✅ Square videos (1:1)
- ✅ Aspect ratio preservation
- ✅ Even dimension requirements
- ✅ Upscaling prevention
- ✅ Original resolution preservation

Run tests:

```bash
poetry run pytest tests/test_resolution.py -v
```

## Migration Notes

### Upgrading from Previous Version

1. **New "ultra" profile** added for 4K content
2. **"original" quality** now supported in QualityVariant
3. **width/height fields** added to QualityVariant (optional)
4. **New helper functions** for resolution calculation

### Configuration Updates

Update your `config.yaml` to include ultra profile:

```yaml
profiles:
  ultra: # NEW
    - quality: 2160p
      bitrate: 20000k
      crf: 18
    # ... other variants

  high:
    - quality: 1440p # UPDATED - now includes 1440p
      bitrate: 12000k
      crf: 22
    # ... rest unchanged
```

## Performance Considerations

### 4K Transcoding

- Requires significant CPU/GPU resources
- Recommended hardware acceleration (NVENC/QSV/VideoToolbox)
- Consider reducing parallel tasks for 4K content
- Estimated time: 1.5-3x video duration (with HW acceleration)

### Non-Standard Resolutions

- No performance penalty compared to standard resolutions
- Aspect ratio calculation is fast (done once per source)
- Original variant is fastest (no scaling)

## Troubleshooting

### Issue: Upscaling Unwanted

**Problem:** 720p source generating 1080p variant

**Solution:** Use `should_include_quality()` before adding variants:

```python
if should_include_quality(source_height, "1080p", allow_upscaling=False):
    # Only adds if source >= 1080p
```

### Issue: Odd Dimensions Error

**Problem:** FFmpeg errors with odd-width videos

**Solution:** All functions ensure even dimensions automatically:

```python
# calculate_target_resolution() always returns even dimensions
width, height = calculate_target_resolution(1921, 1081, "720p")
assert width % 2 == 0  # Always true
assert height % 2 == 0  # Always true
```

### Issue: Aspect Ratio Not Preserved

**Problem:** Videos appear stretched

**Solution:** Always use `calculate_target_resolution()`:

```python
# DON'T do this:
target_width, target_height = 1280, 720  # Might stretch

# DO this:
target_width, target_height = calculate_target_resolution(
    source_width, source_height, "720p"
)  # Maintains aspect ratio
```

## Future Enhancements

- [ ] 8K (4320p) support
- [ ] Automatic bitrate calculation based on resolution
- [ ] Content-aware encoding (adjust settings based on content type)
- [ ] HDR/Dolby Vision support
- [ ] Variable frame rate handling
