# HLS Video Transcoder

Convert video files to HLS format with hardware acceleration and parallel processing.

## 🚀 Features

- **Hardware Acceleration**: Support for NVIDIA NVENC, Intel QSV, AMD AMF, Apple VideoToolbox, and VAAPI
- **Parallel Processing**: Transcode multiple quality variants simultaneously
- **Multiple Audio Tracks**: Extract and process multiple audio streams
- **Subtitles**: Convert and include subtitle tracks
- **Preview Sprites**: Generate thumbnail sprite sheets for video scrubbing
- **Beautiful CLI**: Rich terminal output with progress bars and tables
- **Configurable**: YAML/TOML configuration with quality profiles

## 📋 Requirements

- Python 3.10+
- FFmpeg 6.0+ with hardware acceleration support
- 4GB+ RAM (16GB recommended)
- GPU with hardware encoding support (optional but recommended)

## 🛠️ Installation

### Using Poetry (Recommended)

```bash
git clone https://github.com/yourusername/hls-transcoder
cd hls-transcoder
poetry install
```

### Using pip

```bash
pip install hls-transcoder
```

## 🎯 Quick Start

```bash
# Basic usage
hls-transcoder input.mp4

# Specify output directory
hls-transcoder input.mkv -o ./output

# Use high quality profile
hls-transcoder input.mov -q high

# Force hardware acceleration
hls-transcoder input.mp4 --hardware nvenc

# Verbose output
hls-transcoder input.mkv -v
```

## 📖 Documentation

See the [docs](./docs/) directory for complete documentation:

- [System Design](./docs/System%20Design.md) - Complete technical specification
- [Implementation Plan](./docs/Implementation%20Plan.md) - Development roadmap
- API Reference (coming soon)
- Examples (coming soon)

## 🏗️ Project Status

**Current Phase**: Foundation & Core Infrastructure (Phase 1)

### Completed ✅

- [x] Project structure setup
- [x] Data models (media, tasks, results)
- [x] Error handling system
- [x] Logging infrastructure
- [x] Helper utilities
- [x] pyproject.toml configuration

### In Progress 🚧

- [ ] Configuration system
- [ ] Hardware detection
- [ ] Media inspector

### Upcoming 📅

- [ ] Async subprocess wrapper
- [ ] Video transcoder
- [ ] Audio extractor
- [ ] Parallel execution engine
- [ ] CLI interface

## 🧪 Testing

```bash
# Run all tests
poetry run pytest

# Run with coverage
poetry run pytest --cov=hls_transcoder

# Run specific test file
poetry run pytest tests/test_models.py
```

## 🤝 Contributing

Contributions are welcome! Please read the contributing guidelines (coming soon).

## 📝 License

MIT License - see LICENSE file for details.

## 🙏 Acknowledgments

- FFmpeg team for the amazing multimedia framework
- Rich library for beautiful terminal output
- Typer for the modern CLI framework

---

**Note**: This project is under active development. See [Implementation Plan](./docs/Implementation%20Plan.md) for the current roadmap.
