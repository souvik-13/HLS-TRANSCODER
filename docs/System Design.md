# HLS Video Transcoder - Complete System Design & Technical Specification

## Project Overview

**Name**: HLS-Transcoder  
**Type**: Local CLI Tool  
**Purpose**: Convert video files to HLS format with separated streams, hardware acceleration, and parallel processing

---

## Tech Stack

### Core Language

**Python 3.10+**

- Modern async/await support
- Excellent library ecosystem
- Easy FFmpeg integration
- Cross-platform compatibility

### Primary Libraries

#### FFmpeg Integration

- **ffmpeg-python** (1.0.8+) - Pythonic FFmpeg wrapper
- Direct subprocess for custom commands when needed

#### CLI & UI

- **Typer** (0.9.0+) - Modern CLI framework (better than Click)
  - Automatic help generation
  - Type hints support
  - Rich integration out of the box
- **Rich** (13.0.0+) - Beautiful terminal output
  - Progress bars
  - Tables
  - Syntax highlighting
  - Live displays
  - Panels and layouts

#### Async & Parallel Processing

- **asyncio** (built-in) - Async operations
- **concurrent.futures** (built-in) - Thread/process pools
- **multiprocessing** (built-in) - CPU-bound parallel tasks

#### Data & Configuration

- **pydantic** (2.0+) - Data validation and settings
- **pyyaml** (6.0+) - Configuration files
- **tomli** (2.0+) - TOML config support

#### Utilities

- **pathlib** (built-in) - Path handling
- **dataclasses** (built-in) - Data structures
- **typing** (built-in) - Type hints

### External Dependencies

- **FFmpeg** (6.0+) with hardware acceleration support
- **FFprobe** (included with FFmpeg)

### Optional Enhancements

- **Pillow** (10.0+) - Sprite image processing
- **colorama** (0.4.6+) - Windows color support

---

## System Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                         CLI Interface                            │
│  ┌────────────────────────────────────────────────────────┐     │
│  │  Typer + Rich                                          │     │
│  │  - Argument parsing                                    │     │
│  │  - Beautiful help text                                 │     │
│  │  - Interactive prompts (optional)                      │     │
│  └────────────────────────────────────────────────────────┘     │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│                    Configuration Manager                         │
│  - Load user config (.yaml/.toml)                               │
│  - Hardware detection                                            │
│  - Profile management (quality presets)                         │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│                      Hardware Detector                           │
│  Detect available acceleration:                                  │
│  - NVIDIA (NVENC/NVDEC) - CUDA                                  │
│  - Intel (QSV) - Quick Sync Video                               │
│  - AMD (AMF) - Advanced Media Framework                         │
│  - Apple (VideoToolbox) - macOS                                 │
│  - VAAPI - Linux                                                │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│                      Media Inspector                             │
│  FFprobe Integration:                                            │
│  - Parse all streams (video/audio/subtitle)                     │
│  - Extract metadata                                              │
│  - Validate compatibility                                        │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│                    Transcoding Planner                           │
│  - Calculate quality ladder                                      │
│  - Select optimal encoder (HW/SW)                               │
│  - Plan parallel execution strategy                             │
│  - Estimate output size & time                                  │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│                  Parallel Task Executor                          │
│  ┌───────────────────────────────────────────────────────┐      │
│  │           Video Transcoding Pool                      │      │
│  │  Process each quality variant in parallel:            │      │
│  │  [1080p] [720p] [480p] [360p]                        │      │
│  │  Each uses separate HW encoder instance              │      │
│  └───────────────────────────────────────────────────────┘      │
│  ┌───────────────────────────────────────────────────────┐      │
│  │           Audio Extraction Pool                       │      │
│  │  Process each audio track in parallel:                │      │
│  │  [Track 0: ENG] [Track 1: SPA] [Track 2: FRE]        │      │
│  └───────────────────────────────────────────────────────┘      │
│  ┌───────────────────────────────────────────────────────┐      │
│  │          Subtitle Extraction Pool                     │      │
│  │  Process all subtitle tracks in parallel              │      │
│  └───────────────────────────────────────────────────────┘      │
│  ┌───────────────────────────────────────────────────────┐      │
│  │          Sprite Generation                            │      │
│  │  Generate preview thumbnails in parallel              │      │
│  └───────────────────────────────────────────────────────┘      │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│                  Progress Monitor (Rich)                         │
│  ╔══════════════════════════════════════════════════════╗       │
│  ║  📹 Video Transcoding                                ║       │
│  ║  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ 45% 1080p   ║       │
│  ║  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ 67% 720p ║       │
│  ║                                                      ║       │
│  ║  🎵 Audio Extraction                                 ║       │
│  ║  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ 78% ENG ║       │
│  ║                                                      ║       │
│  ║  💬 Subtitles: ✓ Complete                           ║       │
│  ║  🖼️  Sprites: Processing...                          ║       │
│  ╚══════════════════════════════════════════════════════╝       │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│                  Playlist Generator                              │
│  - Create master.m3u8                                            │
│  - Generate variant playlists                                    │
│  - Create metadata.json                                          │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│                    Output Validator                              │
│  - Verify all segments created                                   │
│  - Check playlist integrity                                      │
│  - Validate playback compatibility                              │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│                    Summary Reporter                              │
│  Display final report with Rich tables                           │
└─────────────────────────────────────────────────────────────────┘
```

---

## Module Breakdown

### 1. CLI Module (`cli/main.py`)

**Framework**: Typer with Rich

**Commands**:

```python
transcode <input>           # Main transcoding command
config init                 # Create config file
config show                 # Show current config
hardware detect             # Detect available hardware
profiles list               # List quality profiles
profiles create <name>      # Create custom profile
version                     # Show version info
```

**Main Command Arguments**:

```python
@app.command()
def transcode(
    input_file: Path,                    # Required
    output: Path = "./output",           # Output directory
    quality: str = "auto",               # auto, 1080,720,480 or profile name
    audio: str = "all",                  # all, 0, 1,2,3
    subtitle: str = "all",               # all, 0, 1,2,3
    hardware: str = "auto",              # auto, nvenc, qsv, vaapi, none
    parallel: int = 4,                   # Max parallel tasks
    sprite_interval: int = 10,           # Seconds between thumbnails
    no_sprites: bool = False,            # Skip sprite generation
    segment_duration: int = 6,           # HLS segment duration
    force: bool = False,                 # Overwrite existing output
    verbose: bool = False,               # Verbose output
    config: Optional[Path] = None,       # Custom config file
):
    """
    Transcode video to HLS format with hardware acceleration
    """
```

**Beautiful CLI Output Example**:

```
╭─────────────────────────────────────────────────────────────╮
│                    HLS Transcoder v1.0                      │
│              Fast • Parallel • Hardware Accelerated         │
╰─────────────────────────────────────────────────────────────╯

📁 Input: movie.mkv (4.2 GB)
📊 Duration: 02:15:30
🎬 Video: H.264, 1920x1080, 24 fps
🎵 Audio: 3 tracks (ENG, SPA, FRE)
💬 Subtitles: 2 tracks (ENG, SPA)

⚙️  Hardware: NVIDIA NVENC detected ✓
📐 Quality Ladder: 1080p, 720p, 480p, 360p
🔄 Parallel Jobs: 4

Starting transcoding...
```

### 2. Configuration Module (`config/manager.py`)

**Config File Format** (`.hls-transcoder.yaml`):

```yaml
# HLS Transcoder Configuration

# Hardware Acceleration
hardware:
  prefer: auto # auto, nvenc, qsv, vaapi, amf, videotoolbox, none
  fallback: software # Use software encoding if HW fails
  max_instances: 4 # Max concurrent HW encoder instances

# Quality Profiles
profiles:
  high:
    - { quality: 1080p, bitrate: 8000k, crf: 20 }
    - { quality: 720p, bitrate: 5000k, crf: 23 }
    - { quality: 480p, bitrate: 2500k, crf: 26 }
    - { quality: 360p, bitrate: 1000k, crf: 28 }

  medium:
    - { quality: 1080p, bitrate: 5000k, crf: 23 }
    - { quality: 720p, bitrate: 3000k, crf: 25 }
    - { quality: 480p, bitrate: 1500k, crf: 28 }

  low:
    - { quality: 720p, bitrate: 2000k, crf: 28 }
    - { quality: 480p, bitrate: 1000k, crf: 30 }

# HLS Settings
hls:
  segment_duration: 6 # seconds
  playlist_type: vod # vod or event
  delete_threshold: 0 # Keep all segments

# Audio Settings
audio:
  codec: aac
  bitrate: 128k
  channels: 2
  sample_rate: 48000

# Sprite Settings
sprites:
  enabled: true
  interval: 10 # seconds
  width: 160
  height: 90
  columns: 10
  rows: 10

# Performance
performance:
  max_parallel_tasks: 4
  thread_queue_size: 512
  preset: medium # ultrafast, superfast, veryfast, faster, fast, medium, slow, slower, veryslow

# Output
output:
  create_metadata: true
  organize_by_type: true
  cleanup_temp: true
```

**Pydantic Models**:

```python
from pydantic import BaseModel, Field

class HardwareConfig(BaseModel):
    prefer: str = "auto"
    fallback: str = "software"
    max_instances: int = 4

class QualityVariant(BaseModel):
    quality: str
    bitrate: str
    crf: int

class AudioConfig(BaseModel):
    codec: str = "aac"
    bitrate: str = "128k"
    channels: int = 2
    sample_rate: int = 48000

class Config(BaseModel):
    hardware: HardwareConfig
    profiles: dict[str, list[QualityVariant]]
    # ... more configs
```

### 3. Hardware Detection Module (`hardware/detector.py`)

**Responsibilities**:

- Detect available hardware encoders
- Test encoder functionality
- Select optimal encoder
- Provide fallback options

**Detection Logic**:

```python
class HardwareDetector:
    def detect_all(self) -> dict:
        """Detect all available hardware acceleration"""
        return {
            'nvidia': self._detect_nvidia(),
            'intel': self._detect_intel_qsv(),
            'amd': self._detect_amd(),
            'apple': self._detect_videotoolbox(),
            'vaapi': self._detect_vaapi(),
        }

    def _detect_nvidia(self) -> dict:
        """Detect NVIDIA NVENC"""
        # Check: nvidia-smi, ffmpeg encoders, test encode
        encoders = ['h264_nvenc', 'hevc_nvenc']
        return {
            'available': self._test_encoder(encoders[0]),
            'encoders': encoders,
            'decoders': ['h264_cuvid', 'hevc_cuvid'],
            'gpu_count': self._get_nvidia_gpu_count(),
        }
```

**Encoder Priority** (auto mode):

1. NVIDIA NVENC (best performance)
2. Intel QSV (good performance, lower quality)
3. AMD AMF (good performance)
4. Apple VideoToolbox (macOS only)
5. VAAPI (Linux, variable quality)
6. Software (libx264 - best quality, slowest)

**Hardware-Specific FFmpeg Commands**:

**NVIDIA NVENC**:

```bash
ffmpeg -hwaccel cuda -hwaccel_output_format cuda -i input.mkv \
  -c:v h264_nvenc -preset p4 -rc vbr -cq 23 -b:v 5M -maxrate 5.5M
```

**Intel QSV**:

```bash
ffmpeg -hwaccel qsv -hwaccel_output_format qsv -i input.mkv \
  -c:v h264_qsv -preset medium -global_quality 23 -b:v 5M
```

**AMD AMF**:

```bash
ffmpeg -hwaccel d3d11va -i input.mkv \
  -c:v h264_amf -quality balanced -rc vbr_latency -b:v 5M
```

**Apple VideoToolbox**:

```bash
ffmpeg -hwaccel videotoolbox -i input.mkv \
  -c:v h264_videotoolbox -b:v 5M -q:v 60
```

### 4. Media Inspector Module (`inspector/analyzer.py`)

**Uses**: ffmpeg-python for FFprobe

```python
import ffmpeg

class MediaInspector:
    def inspect(self, input_file: Path) -> MediaInfo:
        """Analyze media file and return structured info"""
        probe = ffmpeg.probe(str(input_file))

        return MediaInfo(
            format=self._parse_format(probe['format']),
            video_streams=self._parse_video_streams(probe['streams']),
            audio_streams=self._parse_audio_streams(probe['streams']),
            subtitle_streams=self._parse_subtitle_streams(probe['streams']),
        )
```

**Output Structure**:

```python
@dataclass
class VideoStream:
    index: int
    codec: str
    width: int
    height: int
    fps: float
    bitrate: int
    duration: float

@dataclass
class AudioStream:
    index: int
    codec: str
    language: str
    channels: int
    sample_rate: int
    bitrate: int

@dataclass
class SubtitleStream:
    index: int
    codec: str
    language: str
    title: str
```

### 5. Transcoding Planner Module (`planner/strategy.py`)

**Responsibilities**:

- Calculate optimal quality ladder based on source
- Plan parallel execution strategy
- Estimate output size and duration
- Allocate hardware resources

**Quality Ladder Logic**:

```python
def calculate_quality_ladder(source_height: int, profile: str) -> list:
    """Calculate quality variants based on source resolution"""

    available_qualities = {
        2160: ['2160p', '1080p', '720p', '480p'],
        1440: ['1440p', '1080p', '720p', '480p'],
        1080: ['1080p', '720p', '480p', '360p'],
        720: ['720p', '480p', '360p'],
        480: ['480p', '360p'],
    }

    # Never upscale
    qualities = [q for q in available_qualities[source_height]
                 if int(q[:-1]) <= source_height]

    return qualities
```

**Parallel Execution Strategy**:

```python
class ExecutionPlanner:
    def plan_parallel_execution(
        self,
        video_tasks: list,
        audio_tasks: list,
        hw_encoders_available: int
    ) -> ExecutionPlan:
        """
        Plan how to execute tasks in parallel

        Strategy:
        1. Video tasks use HW encoders (limited by GPU)
        2. Audio/subtitle tasks use CPU (can run many in parallel)
        3. Sprites run after video tasks complete
        """

        return ExecutionPlan(
            video_pool_size=min(len(video_tasks), hw_encoders_available),
            audio_pool_size=min(len(audio_tasks), 8),  # CPU threads
            subtitle_pool_size=len(subtitle_tasks),  # I/O bound, run all
        )
```

### 6. Parallel Task Executor Module (`executor/parallel.py`)

**Uses**: asyncio + concurrent.futures

```python
import asyncio
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor

class ParallelExecutor:
    def __init__(self, max_workers: int = 4):
        self.process_pool = ProcessPoolExecutor(max_workers=max_workers)
        self.thread_pool = ThreadPoolExecutor(max_workers=max_workers * 2)

    async def execute_all(self, tasks: TaskPlan):
        """Execute all tasks with optimal parallelism"""

        # Start all video tasks (HW limited)
        video_futures = [
            self._execute_video_task(task)
            for task in tasks.video_tasks
        ]

        # Start all audio tasks (CPU bound)
        audio_futures = [
            self._execute_audio_task(task)
            for task in tasks.audio_tasks
        ]

        # Start subtitle tasks (I/O bound)
        subtitle_futures = [
            self._execute_subtitle_task(task)
            for task in tasks.subtitle_tasks
        ]

        # Wait for all to complete
        await asyncio.gather(
            *video_futures,
            *audio_futures,
            *subtitle_futures,
        )

        # Generate sprites after video is done
        await self._execute_sprite_task(tasks.sprite_task)
```

**Progress Tracking with Rich**:

```python
from rich.progress import Progress, SpinnerColumn, BarColumn, TextColumn

class TranscodingProgress:
    def __init__(self):
        self.progress = Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
            TextColumn("•"),
            TextColumn("[cyan]{task.fields[speed]}"),
            TextColumn("•"),
            TextColumn("[yellow]{task.fields[eta]}"),
        )

    def track_ffmpeg_process(self, process, task_id, duration):
        """Parse FFmpeg stderr and update progress"""
        for line in process.stderr:
            if 'time=' in line:
                time_str = self._extract_time(line)
                progress_pct = self._calculate_progress(time_str, duration)
                speed = self._extract_speed(line)
                eta = self._calculate_eta(progress_pct, speed)

                self.progress.update(
                    task_id,
                    completed=progress_pct,
                    speed=speed,
                    eta=eta
                )
```

### 7. Video Transcoder Module (`transcoder/video.py`)

**Hardware-Aware Encoding**:

```python
class VideoTranscoder:
    def __init__(self, hardware_type: str):
        self.hardware = hardware_type
        self.encoder_settings = self._get_encoder_settings()

    def transcode(
        self,
        input_file: Path,
        output_dir: Path,
        quality: QualityVariant,
        stream_index: int = 0
    ):
        """Transcode video with hardware acceleration"""

        cmd = self._build_ffmpeg_command(
            input_file,
            output_dir,
            quality,
            stream_index
        )

        process = subprocess.Popen(
            cmd,
            stderr=subprocess.PIPE,
            universal_newlines=True
        )

        # Track progress
        # ...

    def _build_ffmpeg_command(self, ...):
        """Build FFmpeg command based on hardware"""

        if self.hardware == 'nvenc':
            return self._build_nvenc_command(...)
        elif self.hardware == 'qsv':
            return self._build_qsv_command(...)
        # ... more hardware types
        else:
            return self._build_software_command(...)
```

### 8. Audio Extractor Module (`transcoder/audio.py`)

**Multi-track Extraction**:

```python
class AudioExtractor:
    def extract_track(
        self,
        input_file: Path,
        output_dir: Path,
        stream_index: int,
        language: str
    ):
        """Extract and convert audio track to AAC/HLS"""

        output_playlist = output_dir / f"audio_{language}.m3u8"
        segment_pattern = output_dir / f"audio_{language}" / "segment_%03d.ts"

        cmd = [
            'ffmpeg', '-i', str(input_file),
            '-map', f'0:a:{stream_index}',
            '-c:a', 'aac',
            '-b:a', '128k',
            '-ac', '2',
            '-f', 'hls',
            '-hls_time', '6',
            '-hls_playlist_type', 'vod',
            '-hls_segment_filename', str(segment_pattern),
            str(output_playlist)
        ]

        # Execute...
```

### 9. Subtitle Extractor Module (`transcoder/subtitle.py`)

```python
class SubtitleExtractor:
    def extract_track(
        self,
        input_file: Path,
        output_dir: Path,
        stream_index: int,
        language: str
    ):
        """Extract subtitle and convert to WebVTT"""

        output_file = output_dir / f"subtitle_{language}.vtt"

        cmd = [
            'ffmpeg', '-i', str(input_file),
            '-map', f'0:s:{stream_index}',
            str(output_file)
        ]

        # Execute...
```

### 10. Sprite Generator Module (`sprites/generator.py`)

**Optimized Sprite Generation**:

```python
class SpriteGenerator:
    def generate(
        self,
        input_file: Path,
        output_dir: Path,
        interval: int = 10,
        width: int = 160,
        height: int = 90
    ):
        """Generate sprite sheet and VTT file"""

        # Step 1: Extract thumbnails
        thumb_dir = output_dir / "temp_thumbs"
        thumb_dir.mkdir(exist_ok=True)

        cmd = [
            'ffmpeg', '-i', str(input_file),
            '-vf', f'fps=1/{interval},scale={width}:{height}',
            str(thumb_dir / 'thumb_%04d.jpg')
        ]
        subprocess.run(cmd, check=True)

        # Step 2: Create sprite sheet (10x10 grid)
        sprite_file = output_dir / "sprite.jpg"
        cmd = [
            'ffmpeg',
            '-pattern_type', 'glob',
            '-i', str(thumb_dir / '*.jpg'),
            '-filter_complex', f'tile=10x10',
            str(sprite_file)
        ]
        subprocess.run(cmd, check=True)

        # Step 3: Generate WebVTT
        self._generate_vtt(
            output_dir / "sprite.vtt",
            interval,
            width,
            height,
            10, 10  # columns, rows
        )

        # Step 4: Cleanup temp files
        shutil.rmtree(thumb_dir)
```

### 11. Playlist Generator Module (`playlist/generator.py`)

**Master Playlist with All Variants**:

```python
class PlaylistGenerator:
    def generate_master_playlist(
        self,
        output_dir: Path,
        video_variants: list,
        audio_tracks: list,
        subtitle_tracks: list
    ):
        """Generate HLS master playlist"""

        lines = ['#EXTM3U', '#EXT-X-VERSION:6', '']

        # Add audio groups
        for audio in audio_tracks:
            lines.append(
                f'#EXT-X-MEDIA:TYPE=AUDIO,GROUP-ID="audio",'
                f'NAME="{audio.name}",LANGUAGE="{audio.language}",'
                f'URI="audio/{audio.language}.m3u8"'
            )

        lines.append('')

        # Add subtitle groups
        for sub in subtitle_tracks:
            lines.append(
                f'#EXT-X-MEDIA:TYPE=SUBTITLES,GROUP-ID="subs",'
                f'NAME="{sub.name}",LANGUAGE="{sub.language}",'
                f'URI="subtitles/{sub.language}.vtt"'
            )

        lines.append('')

        # Add video variants
        for variant in video_variants:
            lines.append(
                f'#EXT-X-STREAM-INF:BANDWIDTH={variant.bandwidth},'
                f'RESOLUTION={variant.resolution},'
                f'CODECS="avc1.640028,mp4a.40.2",'
                f'AUDIO="audio",SUBTITLES="subs"'
            )
            lines.append(f'video/{variant.quality}.m3u8')
            lines.append('')

        # Write master playlist
        master_file = output_dir / 'master.m3u8'
        master_file.write_text('\n'.join(lines))
```

### 12. Progress Monitor Module (`ui/progress.py`)

**Rich-based Multi-Task Progress Display**:

```python
from rich.live import Live
from rich.panel import Panel
from rich.table import Table
from rich.progress import Progress, TaskID

class TranscodingMonitor:
    def __init__(self):
        self.progress = Progress()
        self.task_ids: dict[str, TaskID] = {}

    def create_layout(self):
        """Create beautiful progress layout"""

        # Video progress table
        video_table = Table(show_header=False, box=None)
        video_table.add_column("Task", style="cyan")
        video_table.add_column("Progress", style="green")

        for task_name, task_id in self.task_ids.items():
            if task_name.startswith('video_'):
                task = self.progress.tasks[task_id]
                video_table.add_row(
                    task_name,
                    f"{task.percentage:.1f}%"
                )

        # Create panel
        panel = Panel(
            video_table,
            title="🎬 Transcoding Progress",
            border_style="blue"
        )

        return panel

    def start(self):
        """Start live display"""
        with Live(self.create_layout(), refresh_per_second=4):
            # Update in background
            pass
```

### 13. Output Validator Module (`validator/checker.py`)

```python
class OutputValidator:
    def validate_output(self, output_dir: Path) -> ValidationResult:
        """Validate all generated files"""

        checks = [
            self._check_master_playlist_exists(),
            self._check_all_segments_created(),
            self._check_playlist_integrity(),
            self._check_audio_sync(),
            self._check_subtitle_files(),
        ]

        return ValidationResult(
            success=all(checks),
            errors=self._collect_errors()
        )
```

---

## Directory Structure

```
hls-transcoder/
├── pyproject.toml              # Poetry config
├── README.md
├── .hls-transcoder.yaml        # Default config
├── hls_transcoder/
│   ├── __init__.py
│   ├── __main__.py             # Entry point
│   │
│   ├── cli/
│   │   ├── __init__.py
│   │   └── main.py             # Typer CLI
│   │
│   ├── config/
│   │   ├── __init__.py
│   │   ├── manager.py          # Config loader
│   │   ├── models.py           # Pydantic models
│   │   └── defaults.yaml       # Default config
│   │
│   ├── hardware/
│   │   ├── __init__.py
│   │   └── detector.py         # Hardware detection
│   │
│   ├── inspector/
│   │   ├── __init__.py
│   │   └── analyzer.py         # Media analysis
│   │
│   ├── planner/
│   │   ├── __init__.py
│   │   └── strategy.py         # Execution planning
│   │
│   ├── executor/
│   │   ├── __init__.py
│   │   ├── parallel.py         # Parallel execution
│   │   └── subprocess.py       # Async subprocess wrapper
│   │
│   ├── transcoder/
│   │   ├── __init__.py
│   │   ├── video.py            # Video transcoding
│   │   ├── audio.py            # Audio extraction
│   │   └── subtitle.py         # Subtitle extraction
│   │
│   ├── sprites/
│   │   ├── __init__.py
│   │   └── generator.py        # Sprite generation
│   │
│   ├── playlist/
│   │   ├── __init__.py
│   │   └── generator.py        # HLS playlist generation
│   │
│   ├── validator/
│   │   ├── __init__.py
│   │   └── checker.py          # Output validation
│   │
│   ├── ui/
│   │   ├── __init__.py
│   │   ├── progress.py         # Progress monitoring
│   │   └── reporter.py         # Summary reporting
│   │
│   ├── utils/
│   │   ├── __init__.py
│   │   ├── logger.py           # Logging utilities
│   │   ├── errors.py           # Custom exceptions
│   │   └── helpers.py          # Helper functions
│   │
│   └── models/
│       ├── __init__.py
│       ├── media.py            # Media data models
│       ├── tasks.py            # Task data models
│       └── results.py          # Result data models
│
├── tests/
│   ├── __init__.py
│   ├── test_cli.py
│   ├── test_hardware.py
│   ├── test_inspector.py
│   ├── test_transcoder.py
│   └── fixtures/
│       └── sample.mp4          # Test video
│
└── docs/
    ├── System Design.md
    ├── API.md
    └── examples/
        └── usage.md
```

---

## 14. Error Handling & Recovery Module (`utils/errors.py`)

**Custom Exception Hierarchy**:

```python
class TranscoderError(Exception):
    """Base exception for all transcoder errors"""
    pass

class HardwareError(TranscoderError):
    """Hardware acceleration failed"""
    pass

class MediaInspectionError(TranscoderError):
    """Failed to inspect media file"""
    pass

class TranscodingError(TranscoderError):
    """Transcoding process failed"""
    pass

class ValidationError(TranscoderError):
    """Output validation failed"""
    pass

class ConfigurationError(TranscoderError):
    """Configuration is invalid"""
    pass
```

**Error Recovery Strategy**:

```python
class ErrorRecovery:
    def __init__(self, config: Config):
        self.config = config
        self.retry_count = 3
        self.fallback_chain = ['hardware', 'software']

    async def handle_hardware_failure(
        self,
        task: TranscodingTask,
        error: HardwareError
    ):
        """
        Handle hardware encoder failure with automatic fallback

        Strategy:
        1. Log the error with details
        2. Switch to next encoder in priority list
        3. If all HW fails, fallback to software
        4. Retry task with new encoder
        """
        logger.warning(f"Hardware encoding failed: {error}")

        # Try next hardware encoder
        next_encoder = self._get_next_encoder()
        if next_encoder:
            logger.info(f"Falling back to {next_encoder}")
            task.encoder = next_encoder
            return await self._retry_task(task)

        # Fall back to software
        if self.config.hardware.fallback == 'software':
            logger.info("Falling back to software encoding")
            task.encoder = 'libx264'
            return await self._retry_task(task)

        raise TranscodingError("All encoders failed")

    async def handle_process_timeout(
        self,
        task: TranscodingTask,
        timeout: int = 3600
    ):
        """
        Handle stuck FFmpeg processes

        Strategy:
        1. Monitor process runtime
        2. Compare with estimated duration
        3. Kill if exceeded timeout threshold
        4. Clean up partial outputs
        5. Optionally retry
        """
        if task.runtime > timeout:
            logger.error(f"Process timeout after {timeout}s")
            task.process.kill()
            self._cleanup_partial_output(task.output_dir)

            if task.retry_count < self.retry_count:
                task.retry_count += 1
                return await self._retry_task(task)

            raise TranscodingError(f"Task timeout after {self.retry_count} retries")

    def _cleanup_partial_output(self, output_dir: Path):
        """Remove incomplete segments and playlists"""
        for file in output_dir.glob("*.ts"):
            file.unlink()
        for file in output_dir.glob("*.m3u8"):
            file.unlink()
```

---

## 15. Async Subprocess Wrapper (`executor/subprocess.py`)

**Async FFmpeg Process Management**:

```python
import asyncio
from typing import AsyncIterator

class AsyncFFmpegProcess:
    """
    Wrapper for FFmpeg subprocess with async I/O
    """

    def __init__(self, command: list[str]):
        self.command = command
        self.process: asyncio.subprocess.Process | None = None
        self.return_code: int | None = None

    async def start(self):
        """Start FFmpeg process asynchronously"""
        self.process = await asyncio.create_subprocess_exec(
            *self.command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

    async def read_stderr(self) -> AsyncIterator[str]:
        """
        Stream stderr output line by line
        Used for progress tracking
        """
        if not self.process or not self.process.stderr:
            return

        while True:
            line = await self.process.stderr.readline()
            if not line:
                break
            yield line.decode('utf-8', errors='ignore')

    async def wait(self, timeout: int | None = None) -> int:
        """Wait for process to complete with optional timeout"""
        try:
            await asyncio.wait_for(
                self.process.wait(),
                timeout=timeout
            )
        except asyncio.TimeoutError:
            self.kill()
            raise TranscodingError(f"Process timeout after {timeout}s")

        self.return_code = self.process.returncode
        return self.return_code

    def kill(self):
        """Forcefully terminate the process"""
        if self.process:
            self.process.kill()

    async def get_output(self) -> tuple[str, str]:
        """Get stdout and stderr after process completes"""
        if not self.process:
            return "", ""

        stdout, stderr = await self.process.communicate()
        return (
            stdout.decode('utf-8', errors='ignore'),
            stderr.decode('utf-8', errors='ignore')
        )
```

**Integration with Progress Tracking**:

```python
class VideoTranscoder:
    async def transcode_async(
        self,
        input_file: Path,
        output_dir: Path,
        quality: QualityVariant,
        progress_callback: callable
    ):
        """Transcode with async progress updates"""

        cmd = self._build_ffmpeg_command(input_file, output_dir, quality)
        process = AsyncFFmpegProcess(cmd)

        await process.start()

        # Track progress from stderr
        async for line in process.read_stderr():
            if 'time=' in line:
                progress_data = self._parse_progress(line)
                await progress_callback(progress_data)

        # Wait for completion
        return_code = await process.wait(timeout=7200)  # 2 hour max

        if return_code != 0:
            _, stderr = await process.get_output()
            raise TranscodingError(f"FFmpeg failed: {stderr[-500:]}")
```

---

## 16. Logging Module (`utils/logger.py`)

**Structured Logging with Rich**:

```python
import logging
from rich.logging import RichHandler
from pathlib import Path

def setup_logger(
    name: str = "hls-transcoder",
    level: str = "INFO",
    log_file: Path | None = None,
    verbose: bool = False
) -> logging.Logger:
    """
    Setup logger with Rich handler and optional file output

    Features:
    - Beautiful console output with Rich
    - Optional file logging for debugging
    - Performance metrics tracking
    - Structured log format
    """

    logger = logging.getLogger(name)
    logger.setLevel(level if not verbose else "DEBUG")

    # Console handler with Rich
    console_handler = RichHandler(
        rich_tracebacks=True,
        markup=True,
        show_time=True,
        show_path=verbose
    )
    console_handler.setFormatter(
        logging.Formatter("%(message)s", datefmt="[%X]")
    )
    logger.addHandler(console_handler)

    # File handler for detailed logs
    if log_file:
        file_handler = logging.FileHandler(log_file)
        file_handler.setFormatter(
            logging.Formatter(
                '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
            )
        )
        logger.addHandler(file_handler)

    return logger

# Performance logging decorator
def log_performance(func):
    """Decorator to log function execution time"""
    async def wrapper(*args, **kwargs):
        import time
        start = time.time()
        result = await func(*args, **kwargs)
        duration = time.time() - start
        logger.info(f"{func.__name__} completed in {duration:.2f}s")
        return result
    return wrapper
```

---

## 17. Summary Reporter Module (`ui/reporter.py`)

**Final Report with Rich Tables**:

```python
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.text import Text

class SummaryReporter:
    def __init__(self):
        self.console = Console()

    def generate_report(
        self,
        input_file: Path,
        output_dir: Path,
        results: TranscodingResults,
        duration: float
    ):
        """Generate and display beautiful final report"""

        # Main summary
        summary_table = Table(title="✨ Transcoding Complete!", box=None)
        summary_table.add_column("Metric", style="cyan")
        summary_table.add_column("Value", style="green")

        summary_table.add_row("Input", str(input_file.name))
        summary_table.add_row("Output", str(output_dir))
        summary_table.add_row("Duration", self._format_duration(duration))
        summary_table.add_row("Speed", f"{results.total_frames / duration:.2f} fps")

        self.console.print(summary_table)
        self.console.print()

        # Video variants table
        video_table = Table(title="📹 Video Variants")
        video_table.add_column("Quality", style="cyan")
        video_table.add_column("Resolution", style="yellow")
        video_table.add_column("Bitrate", style="magenta")
        video_table.add_column("Size", style="green")
        video_table.add_column("Segments", style="blue")

        for variant in results.video_variants:
            video_table.add_row(
                variant.quality,
                f"{variant.width}x{variant.height}",
                variant.bitrate,
                self._format_size(variant.size),
                str(variant.segment_count)
            )

        self.console.print(video_table)
        self.console.print()

        # Audio tracks table
        audio_table = Table(title="🎵 Audio Tracks")
        audio_table.add_column("Track", style="cyan")
        audio_table.add_column("Language", style="yellow")
        audio_table.add_column("Codec", style="magenta")
        audio_table.add_column("Size", style="green")

        for track in results.audio_tracks:
            audio_table.add_row(
                f"Track {track.index}",
                track.language,
                track.codec,
                self._format_size(track.size)
            )

        self.console.print(audio_table)
        self.console.print()

        # Performance summary
        perf_panel = Panel(
            f"""
[cyan]Hardware:[/cyan] {results.hardware_used}
[cyan]Parallel Jobs:[/cyan] {results.parallel_jobs}
[cyan]Total Size:[/cyan] {self._format_size(results.total_size)}
[cyan]Compression:[/cyan] {results.compression_ratio:.1f}x smaller
[cyan]Master Playlist:[/cyan] {output_dir / 'master.m3u8'}
            """.strip(),
            title="📊 Performance",
            border_style="green"
        )

        self.console.print(perf_panel)

        # Playback instructions
        self.console.print()
        self.console.print("[bold green]✓[/bold green] Ready for playback!")
        self.console.print(f"[dim]Use: ffplay {output_dir / 'master.m3u8'}[/dim]")

    def _format_duration(self, seconds: float) -> str:
        """Format duration as HH:MM:SS"""
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"

    def _format_size(self, bytes: int) -> str:
        """Format file size"""
        for unit in ['B', 'KB', 'MB', 'GB']:
            if bytes < 1024:
                return f"{bytes:.1f} {unit}"
            bytes /= 1024
        return f"{bytes:.1f} TB"
```

---

## 18. Data Models (`models/`)

### Media Models (`models/media.py`):

```python
from dataclasses import dataclass
from pathlib import Path

@dataclass
class MediaInfo:
    """Complete media file information"""
    format: FormatInfo
    video_streams: list[VideoStream]
    audio_streams: list[AudioStream]
    subtitle_streams: list[SubtitleStream]
    duration: float
    size: int
    bitrate: int

@dataclass
class FormatInfo:
    format_name: str
    format_long_name: str
    duration: float
    size: int
    bitrate: int

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
    color_space: str | None = None

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

@dataclass
class SubtitleStream:
    index: int
    codec: str
    language: str
    title: str | None = None
    forced: bool = False
```

### Task Models (`models/tasks.py`):

```python
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

class TaskType(Enum):
    VIDEO = "video"
    AUDIO = "audio"
    SUBTITLE = "subtitle"
    SPRITE = "sprite"

class TaskStatus(Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"

@dataclass
class TranscodingTask:
    """Individual transcoding task"""
    task_id: str
    task_type: TaskType
    input_file: Path
    output_dir: Path
    status: TaskStatus = TaskStatus.PENDING
    progress: float = 0.0
    error: str | None = None
    retry_count: int = 0
    started_at: float | None = None
    completed_at: float | None = None

@dataclass
class VideoTask(TranscodingTask):
    """Video transcoding task"""
    quality: str
    width: int
    height: int
    bitrate: str
    crf: int
    encoder: str
    stream_index: int = 0

@dataclass
class AudioTask(TranscodingTask):
    """Audio extraction task"""
    stream_index: int
    language: str
    codec: str = "aac"
    bitrate: str = "128k"

@dataclass
class SubtitleTask(TranscodingTask):
    """Subtitle extraction task"""
    stream_index: int
    language: str
    format: str = "webvtt"

@dataclass
class SpriteTask(TranscodingTask):
    """Sprite generation task"""
    interval: int
    width: int
    height: int
    columns: int
    rows: int

@dataclass
class TaskPlan:
    """Complete execution plan"""
    video_tasks: list[VideoTask]
    audio_tasks: list[AudioTask]
    subtitle_tasks: list[SubtitleTask]
    sprite_task: SpriteTask | None = None
    estimated_duration: float = 0.0
    estimated_size: int = 0
```

### Result Models (`models/results.py`):

```python
from dataclasses import dataclass
from pathlib import Path

@dataclass
class VideoVariantResult:
    """Result of a single video variant"""
    quality: str
    width: int
    height: int
    bitrate: str
    size: int
    segment_count: int
    duration: float
    playlist_path: Path

@dataclass
class AudioTrackResult:
    """Result of audio extraction"""
    index: int
    language: str
    codec: str
    size: int
    playlist_path: Path

@dataclass
class SubtitleResult:
    """Result of subtitle extraction"""
    index: int
    language: str
    format: str
    file_path: Path

@dataclass
class SpriteResult:
    """Result of sprite generation"""
    sprite_path: Path
    vtt_path: Path
    thumbnail_count: int
    size: int

@dataclass
class TranscodingResults:
    """Complete transcoding results"""
    video_variants: list[VideoVariantResult]
    audio_tracks: list[AudioTrackResult]
    subtitle_tracks: list[SubtitleResult]
    sprite: SpriteResult | None
    master_playlist: Path
    metadata_file: Path
    total_size: int
    total_duration: float
    hardware_used: str
    parallel_jobs: int
    total_frames: int
    compression_ratio: float

@dataclass
class ValidationResult:
    """Output validation result"""
    success: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    master_playlist_valid: bool = True
    all_segments_present: bool = True
    audio_sync_valid: bool = True
    subtitle_files_valid: bool = True
```

---

## 19. Output Structure

**Generated HLS Output**:

```
output/
├── master.m3u8                 # Master playlist
├── metadata.json               # Metadata file
│
├── video/                      # Video variants
│   ├── 1080p/
│   │   ├── playlist.m3u8
│   │   ├── segment_000.ts
│   │   ├── segment_001.ts
│   │   └── ...
│   ├── 720p/
│   │   ├── playlist.m3u8
│   │   └── segment_*.ts
│   ├── 480p/
│   │   ├── playlist.m3u8
│   │   └── segment_*.ts
│   └── 360p/
│       ├── playlist.m3u8
│       └── segment_*.ts
│
├── audio/                      # Audio tracks
│   ├── eng/
│   │   ├── playlist.m3u8
│   │   └── segment_*.ts
│   ├── spa/
│   │   ├── playlist.m3u8
│   │   └── segment_*.ts
│   └── fre/
│       ├── playlist.m3u8
│       └── segment_*.ts
│
├── subtitles/                  # Subtitle tracks
│   ├── eng.vtt
│   ├── spa.vtt
│   └── fre.vtt
│
└── sprites/                    # Preview thumbnails
    ├── sprite.jpg              # Sprite sheet
    └── sprite.vtt              # WebVTT with coordinates
```

**Metadata JSON Structure**:

```json
{
  "source": {
    "filename": "movie.mkv",
    "size": 4500000000,
    "duration": 8130.5,
    "video": {
      "codec": "h264",
      "width": 1920,
      "height": 1080,
      "fps": 24.0,
      "bitrate": 4500000
    },
    "audio_tracks": [
      { "index": 0, "language": "eng", "channels": 6 },
      { "index": 1, "language": "spa", "channels": 2 }
    ]
  },
  "output": {
    "created_at": "2025-11-02T10:30:00Z",
    "transcoding_duration": 450.5,
    "hardware_used": "nvenc",
    "total_size": 2800000000,
    "compression_ratio": 1.6,
    "video_variants": [
      {
        "quality": "1080p",
        "resolution": "1920x1080",
        "bitrate": "8000k",
        "codec": "h264",
        "segments": 1355,
        "size": 1200000000,
        "playlist": "video/1080p/playlist.m3u8"
      }
    ],
    "audio_tracks": [
      {
        "language": "eng",
        "codec": "aac",
        "bitrate": "128k",
        "size": 130000000,
        "playlist": "audio/eng/playlist.m3u8"
      }
    ],
    "subtitles": [
      { "language": "eng", "format": "webvtt", "file": "subtitles/eng.vtt" }
    ],
    "sprites": {
      "interval": 10,
      "dimensions": "160x90",
      "grid": "10x10",
      "file": "sprites/sprite.jpg",
      "vtt": "sprites/sprite.vtt"
    }
  }
}
```

---

## 20. Testing Strategy

### Unit Tests:

```python
# tests/test_hardware.py
def test_nvidia_detection():
    """Test NVIDIA GPU detection"""
    detector = HardwareDetector()
    result = detector._detect_nvidia()
    assert isinstance(result, dict)
    assert 'available' in result

# tests/test_inspector.py
def test_media_inspection():
    """Test media file inspection"""
    inspector = MediaInspector()
    info = inspector.inspect(Path("tests/fixtures/sample.mp4"))
    assert info.video_streams
    assert info.duration > 0
```

### Integration Tests:

```python
# tests/test_transcoder.py
@pytest.mark.asyncio
async def test_full_transcoding():
    """Test complete transcoding pipeline"""
    input_file = Path("tests/fixtures/sample.mp4")
    output_dir = Path("tests/output")

    # Run transcoding
    results = await transcode(
        input_file=input_file,
        output_dir=output_dir,
        quality="medium",
        hardware="auto"
    )

    # Validate output
    assert (output_dir / "master.m3u8").exists()
    assert results.video_variants
    assert results.total_size > 0
```

### Performance Tests:

```python
def test_parallel_performance():
    """Test parallel execution is faster than sequential"""
    # Measure parallel execution
    start = time.time()
    results_parallel = transcode(parallel=4)
    parallel_time = time.time() - start

    # Measure sequential execution
    start = time.time()
    results_sequential = transcode(parallel=1)
    sequential_time = time.time() - start

    # Parallel should be significantly faster
    assert parallel_time < sequential_time * 0.4
```

---

## 21. Performance Optimization

### Memory Management:

- Stream-based processing to avoid loading entire files
- Chunked reading of FFmpeg output
- Cleanup temporary files immediately after use
- Limit concurrent processes based on available RAM

### CPU/GPU Optimization:

- Dynamic worker pool sizing based on available cores/GPUs
- Hardware encoder instance reuse
- Batch similar tasks together
- Priority queue for task scheduling

### I/O Optimization:

- Use buffered I/O for segment writing
- Parallel segment generation
- Direct filesystem operations (avoid unnecessary copies)
- SSD-aware temporary file placement

### Network Considerations (for future streaming):

- Implement segment preloading
- Adaptive bitrate switching logic
- CDN-friendly segment naming
- CORS headers in playlists

---

## 22. Security & Safety

### Input Validation:

- Verify file extensions and MIME types
- Sanitize user-provided paths
- Limit input file sizes (configurable)
- Check for path traversal attacks

### Process Safety:

- Set resource limits (CPU, memory, time)
- Isolate FFmpeg processes
- Handle signals gracefully (SIGTERM, SIGINT)
- Timeout protection for all operations

### Output Safety:

- Validate playlist content before writing
- Check disk space before starting
- Atomic file writes (write to temp, then rename)
- Permission checks on output directories

---

## 23. Future Enhancements

### Phase 2 Features:

- [ ] Resume incomplete transcoding jobs
- [ ] Multi-language CLI (i18n)
- [ ] Web UI for monitoring
- [ ] REST API for remote transcoding
- [ ] Queue system for batch processing
- [ ] Cloud storage integration (S3, GCS, Azure)

### Phase 3 Features:

- [ ] Live streaming support (RTMP → HLS)
- [ ] DRM support (Widevine, FairPlay)
- [ ] AI-powered quality optimization
- [ ] Scene detection for optimal segment boundaries
- [ ] Multi-audio track synchronization
- [ ] Dolby Atmos support

### Performance Goals:

- [ ] 2x realtime transcoding for 1080p on mid-range hardware
- [ ] Sub-60s startup time for large files
- [ ] < 1% CPU usage during idle monitoring
- [ ] Zero-copy segment transfers where possible

---

## 24. Deployment & Distribution

### Installation Methods:

```bash
# PyPI
pip install hls-transcoder

# Pipx (isolated)
pipx install hls-transcoder

# From source
git clone https://github.com/yourusername/hls-transcoder
cd hls-transcoder
poetry install

# Docker
docker pull yourusername/hls-transcoder
```

### System Requirements:

**Minimum**:

- Python 3.10+
- FFmpeg 6.0+
- 4GB RAM
- 2 CPU cores

**Recommended**:

- Python 3.11+
- FFmpeg 7.0+
- 16GB RAM
- 8 CPU cores
- NVIDIA GPU with NVENC support
- SSD for temporary files

### Platform Support:

- ✅ Linux (Ubuntu 20.04+, Debian 11+)
- ✅ macOS (12.0+)
- ✅ Windows (10/11 with WSL2)
- ⚠️ Native Windows (experimental)

---

## 25. Documentation & Resources

### User Documentation:

- Quick Start Guide
- Configuration Reference
- Hardware Acceleration Guide
- Troubleshooting Guide
- FAQ
- Video Tutorials

### Developer Documentation:

- API Reference
- Architecture Overview
- Contributing Guidelines
- Code Style Guide
- Testing Guide
- Release Process

### Example Usage:

```bash
# Basic usage
hls-transcoder input.mp4

# Custom quality profile
hls-transcoder input.mkv -q high -o ./output

# Force hardware acceleration
hls-transcoder input.mov --hardware nvenc

# Multiple audio tracks
hls-transcoder input.mkv --audio "0,1,2"

# Disable sprites
hls-transcoder input.mp4 --no-sprites

# Verbose output with logging
hls-transcoder input.mkv -v --log output.log

# Custom config
hls-transcoder input.mp4 --config my-config.yaml
```

---

## Conclusion

This system design provides a comprehensive blueprint for building a production-ready HLS video transcoder with:

- ✅ **Hardware Acceleration**: Multi-platform GPU support
- ✅ **Parallel Processing**: Optimal resource utilization
- ✅ **Error Handling**: Robust recovery mechanisms
- ✅ **Progress Tracking**: Beautiful real-time monitoring
- ✅ **Extensibility**: Modular architecture for future enhancements
- ✅ **Performance**: Optimized for speed and efficiency
- ✅ **Usability**: Simple CLI with powerful features

The design is ready for implementation with clear module responsibilities, data models, and integration patterns.

```

```
