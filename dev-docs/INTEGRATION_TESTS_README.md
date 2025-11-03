# Integration Tests - Real Fixture File

## Overview

Created comprehensive integration tests that use the actual MKV file located at:
`tests/fixtures/Hostel Daze S02 Complete (2021).mkv`

These tests perform **real transcoding operations** and create **actual output files** to verify the entire pipeline works correctly.

## Test File

**Location**: `tests/test_integration_real.py`

## Test Classes

### 1. TestMediaInspection

Tests media inspection with the real MKV file.

**Test**: `test_inspect_fixture_video`

- Inspects the fixture video file
- Verifies all stream information (video, audio, subtitles)
- Prints detailed media information

### 2. TestVideoTranscoding

Tests video transcoding with hardware acceleration.

**Test**: `test_transcode_360p`

- Transcodes video to 360p quality
- Uses detected hardware acceleration (NVENC/QSV/etc or software fallback)
- Creates actual HLS segments (.ts files)
- Creates M3U8 playlist
- Verifies all outputs exist
- Prints transcoding results

### 3. TestAudioExtraction

Tests audio track extraction.

**Test**: `test_extract_first_audio_track`

- Extracts first audio track to AAC
- Creates HLS audio segments
- Creates audio playlist
- Verifies outputs
- Prints extraction results

### 4. TestSubtitleExtraction

Tests subtitle extraction.

**Test**: `test_extract_first_subtitle`

- Extracts first subtitle track
- Converts to WebVTT format
- Verifies output file exists
- Prints extraction results

### 5. TestSpriteGeneration

Tests thumbnail sprite generation.

**Test**: `test_generate_basic_sprites`

- Generates thumbnail sprites at 10-second intervals
- Creates sprite sheet image
- Creates WebVTT file with coordinates
- Verifies all outputs
- Prints generation results

### 6. TestFullPipeline

Complete end-to-end pipeline test.

**Test**: `test_minimal_transcoding_pipeline`

- **Step 1**: Inspect media
- **Step 2**: Transcode video to 360p
- **Step 3**: Extract audio track
- **Step 4**: Verify playlists
- **Step 5**: Simple validation
- Creates real output files in temp directory
- Prints detailed progress and results

## Running the Tests

### Run all integration tests:

```bash
pytest tests/test_integration_real.py -v -s
```

### Run specific test class:

```bash
# Media inspection only
pytest tests/test_integration_real.py::TestMediaInspection -v -s

# Video transcoding only
pytest tests/test_integration_real.py::TestVideoTranscoding -v -s

# Full pipeline test
pytest tests/test_integration_real.py::TestFullPipeline -v -s
```

### Run specific test:

```bash
pytest tests/test_integration_real.py::TestMediaInspection::test_inspect_fixture_video -v -s
```

## Output Files Created

Tests create real output files in temporary directories:

### Video Transcoding:

- `360p.m3u8` - Video playlist
- `360p_000.ts`, `360p_001.ts`, ... - Video segments
- Additional qualities if tested (480p, 720p, etc.)

### Audio Extraction:

- `audio_{lang}.m3u8` - Audio playlist
- `audio_{lang}_000.ts`, `audio_{lang}_001.ts`, ... - Audio segments

### Subtitle Extraction:

- `subtitle_{lang}.vtt` - WebVTT subtitle file

### Sprite Generation:

- `sprite.jpg` - Sprite sheet image with thumbnails
- `sprite.vtt` - WebVTT file with thumbnail coordinates

## Test Characteristics

✅ **Uses Real MKV File**: Tests process the actual fixture video
✅ **Creates Real Outputs**: All output files are actually generated  
✅ **Hardware Aware**: Auto-detects and uses available hardware acceleration
✅ **Comprehensive**: Tests all major components of the transcoder
✅ **Verbose Output**: Prints detailed progress and results with `-s` flag
⚠️ **Time**: Tests take several minutes to run (real transcoding)
⚠️ **Resources**: Uses CPU/GPU for actual video processing

## Example Output

When running the full pipeline test, you'll see output like:

```
======================================================================
FULL TRANSCODING PIPELINE TEST
======================================================================

[1/5] Inspecting media...
  ✓ Duration: 1234.56s
  ✓ Video: 1920x1080 @ 30.0fps
  ✓ Audio tracks: 1
  ✓ Subtitle tracks: 0

[2/5] Transcoding video to 360p...
  Using: NVIDIA NVENC
  ✓ Created 206 video segments

[3/5] Extracting audio...
  ✓ Extracted 1 audio track

[4/5] Generating master playlist...
  ✓ Video playlist: 360p.m3u8
  ✓ Audio playlist: audio_und.m3u8

[5/5] Validating output...
  ✓ Validation: PASSED

======================================================================
PIPELINE COMPLETE
======================================================================

Output directory: /tmp/pytest-of-user/pytest-current/test_minimal_transcoding_pipeline0/integration_output
Total files created: 415
Total size: 125.34 MB

Key files:
  - Video playlist: 360p.m3u8
  - Audio playlist: audio_und.m3u8
  - Video segments: 206

======================================================================
```

## Notes

1. **Temp Directories**: Output files are created in pytest temp directories which are automatically cleaned up
2. **Skip if Missing**: Tests automatically skip if the fixture MKV file is not found
3. **Hardware Detection**: Tests adapt to available hardware (NVENC, QSV, software, etc.)
4. **Minimal Quality**: Tests use 360p for speed - full quality tests would take much longer
5. **Error Handling**: Tests include proper assertions and error messages

## Benefits

- **Real-World Testing**: Validates the system works with actual video files
- **Output Verification**: Confirms all expected files are created
- **Performance Testing**: Can be used to benchmark transcoding speed
- **Hardware Testing**: Verifies hardware acceleration works correctly
- **Integration Testing**: Tests the complete pipeline end-to-end

## Future Enhancements

Potential additions:

- Test multiple quality variants simultaneously
- Test error recovery and fallback mechanisms
- Benchmark performance with different hardware
- Test with various video formats and codecs
- Add file size and quality verification
- Test playlist parsing and validation
