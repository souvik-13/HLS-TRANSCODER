"""
Output validation for HLS transcoded files.

This module provides validation for transcoded HLS output, including:
- Master playlist validation
- Segment file verification
- Playlist syntax checking
- Audio/video sync validation
- Subtitle file verification
"""

import json
import re
from pathlib import Path
from typing import Optional

from ..models.results import TranscodingResults, ValidationResult
from ..utils import ValidationError, get_logger

logger = get_logger(__name__)


class OutputValidator:
    """
    Validator for HLS transcoding output.

    This class validates:
    - Master playlist existence and format
    - Video variant playlists and segments
    - Audio track playlists and segments
    - Subtitle files
    - Sprite files
    - Metadata file
    """

    def __init__(self, output_dir: Path):
        """
        Initialize output validator.

        Args:
            output_dir: Directory containing transcoding output
        """
        self.output_dir = Path(output_dir)
        self.logger = logger

    def validate(self, results: TranscodingResults) -> ValidationResult:
        """
        Validate complete transcoding output.

        Args:
            results: Transcoding results to validate

        Returns:
            ValidationResult with validation outcome
        """
        validation = ValidationResult(success=True)

        self.logger.info(f"Validating transcoding output in {self.output_dir}")

        # Validate master playlist
        if not self._validate_master_playlist(results, validation):
            validation.master_playlist_valid = False

        # Validate video variants
        if not self._validate_video_variants(results, validation):
            validation.all_segments_present = False

        # Validate audio tracks
        if not self._validate_audio_tracks(results, validation):
            validation.audio_sync_valid = False

        # Validate subtitle tracks
        if not self._validate_subtitle_tracks(results, validation):
            validation.subtitle_files_valid = False

        # Validate sprites
        self._validate_sprites(results, validation)

        # Validate metadata
        self._validate_metadata(results, validation)

        # Final validation summary
        if validation.has_errors:
            self.logger.error(
                f"Validation failed with {len(validation.errors)} error(s) "
                f"and {len(validation.warnings)} warning(s)"
            )
        elif validation.has_warnings:
            self.logger.warning(f"Validation passed with {len(validation.warnings)} warning(s)")
        else:
            self.logger.info("Validation passed successfully")

        return validation

    def _validate_master_playlist(
        self, results: TranscodingResults, validation: ValidationResult
    ) -> bool:
        """
        Validate master playlist.

        Args:
            results: Transcoding results
            validation: Validation result to update

        Returns:
            True if valid, False otherwise
        """
        if not results.master_playlist:
            validation.add_error("Master playlist path not set in results")
            return False

        master_path = results.master_playlist

        # Check file exists
        if not master_path.exists():
            validation.add_error(f"Master playlist not found: {master_path}")
            return False

        # Check file not empty
        if master_path.stat().st_size == 0:
            validation.add_error(f"Master playlist is empty: {master_path}")
            return False

        # Parse and validate content
        try:
            content = master_path.read_text()

            # Check for required HLS tags
            if not content.startswith("#EXTM3U"):
                validation.add_error("Master playlist missing #EXTM3U header")
                return False

            if "#EXT-X-VERSION:" not in content:
                validation.add_warning("Master playlist missing #EXT-X-VERSION tag")

            # Check for video variants
            if results.video_count > 0 and "#EXT-X-STREAM-INF:" not in content:
                validation.add_error("Master playlist missing video variant entries")
                return False

            # Check for audio tracks
            if results.audio_count > 0 and "TYPE=AUDIO" not in content:
                validation.add_warning("Master playlist missing audio track entries")

            # Check for subtitles
            if results.subtitle_count > 0 and "TYPE=SUBTITLES" not in content:
                validation.add_warning("Master playlist missing subtitle entries")

            self.logger.debug(f"Master playlist validated: {master_path}")
            return True

        except Exception as e:
            validation.add_error(f"Failed to parse master playlist: {e}")
            return False

    def _validate_video_variants(
        self, results: TranscodingResults, validation: ValidationResult
    ) -> bool:
        """
        Validate video variant playlists and segments.

        Args:
            results: Transcoding results
            validation: Validation result to update

        Returns:
            True if all valid, False otherwise
        """
        if results.video_count == 0:
            validation.add_warning("No video variants to validate")
            return True

        all_valid = True

        for variant in results.video_variants:
            # Check playlist exists
            if not variant.playlist_path.exists():
                validation.add_error(f"Video variant playlist not found: {variant.playlist_path}")
                all_valid = False
                continue

            # Validate playlist content
            try:
                content = variant.playlist_path.read_text()

                # Check HLS tags
                if not content.startswith("#EXTM3U"):
                    validation.add_error(
                        f"Video playlist missing #EXTM3U header: {variant.quality}"
                    )
                    all_valid = False
                    continue

                # Check for segment entries
                if "#EXTINF:" not in content:
                    validation.add_error(
                        f"Video playlist missing segment entries: {variant.quality}"
                    )
                    all_valid = False
                    continue

                # Check segment count matches
                segment_count = content.count("#EXTINF:")
                if segment_count != variant.segment_count:
                    validation.add_warning(
                        f"Video playlist segment count mismatch: {variant.quality} "
                        f"(expected {variant.segment_count}, found {segment_count})"
                    )

                # Validate segment files exist
                segments = self._extract_segment_paths(content, variant.playlist_path.parent)
                missing_segments = [seg for seg in segments if not seg.exists()]

                if missing_segments:
                    validation.add_error(
                        f"Video variant {variant.quality} missing {len(missing_segments)} segment(s)"
                    )
                    all_valid = False

                self.logger.debug(f"Video variant validated: {variant.quality}")

            except Exception as e:
                validation.add_error(f"Failed to validate video variant {variant.quality}: {e}")
                all_valid = False

        return all_valid

    def _validate_audio_tracks(
        self, results: TranscodingResults, validation: ValidationResult
    ) -> bool:
        """
        Validate audio track playlists and segments.

        Args:
            results: Transcoding results
            validation: Validation result to update

        Returns:
            True if all valid, False otherwise
        """
        if results.audio_count == 0:
            validation.add_warning("No audio tracks to validate")
            return True

        all_valid = True

        for track in results.audio_tracks:
            # Check playlist exists
            if not track.playlist_path.exists():
                validation.add_error(f"Audio track playlist not found: {track.language}")
                all_valid = False
                continue

            # Validate playlist content
            try:
                content = track.playlist_path.read_text()

                # Check HLS tags
                if not content.startswith("#EXTM3U"):
                    validation.add_error(f"Audio playlist missing #EXTM3U header: {track.language}")
                    all_valid = False
                    continue

                # Check for segment entries
                if "#EXTINF:" not in content:
                    validation.add_error(
                        f"Audio playlist missing segment entries: {track.language}"
                    )
                    all_valid = False
                    continue

                # Validate segment files exist
                segments = self._extract_segment_paths(content, track.playlist_path.parent)
                missing_segments = [seg for seg in segments if not seg.exists()]

                if missing_segments:
                    validation.add_error(
                        f"Audio track {track.language} missing {len(missing_segments)} segment(s)"
                    )
                    all_valid = False

                self.logger.debug(f"Audio track validated: {track.language}")

            except Exception as e:
                validation.add_error(f"Failed to validate audio track {track.language}: {e}")
                all_valid = False

        return all_valid

    def _validate_subtitle_tracks(
        self, results: TranscodingResults, validation: ValidationResult
    ) -> bool:
        """
        Validate subtitle files.

        Args:
            results: Transcoding results
            validation: Validation result to update

        Returns:
            True if all valid, False otherwise
        """
        if results.subtitle_count == 0:
            return True  # No error if no subtitles

        all_valid = True

        for subtitle in results.subtitle_tracks:
            # Check file exists
            if not subtitle.file_path.exists():
                validation.add_error(
                    f"Subtitle file not found: {subtitle.language} ({subtitle.file_path})"
                )
                all_valid = False
                continue

            # Check file not empty
            if subtitle.file_path.stat().st_size == 0:
                validation.add_warning(f"Subtitle file is empty: {subtitle.language}")
                continue

            # Validate format-specific content
            try:
                content = subtitle.file_path.read_text()

                if subtitle.format.lower() == "webvtt":
                    if not content.startswith("WEBVTT"):
                        validation.add_error(
                            f"WebVTT subtitle missing WEBVTT header: {subtitle.language}"
                        )
                        all_valid = False
                elif subtitle.format.lower() == "srt":
                    # SRT should have numbered entries
                    if not re.search(r"^\d+\s*$", content, re.MULTILINE):
                        validation.add_warning(
                            f"SRT subtitle may have invalid format: {subtitle.language}"
                        )

                self.logger.debug(f"Subtitle validated: {subtitle.language}")

            except Exception as e:
                validation.add_error(f"Failed to validate subtitle {subtitle.language}: {e}")
                all_valid = False

        return all_valid

    def _validate_sprites(self, results: TranscodingResults, validation: ValidationResult) -> bool:
        """
        Validate sprite files.

        Args:
            results: Transcoding results
            validation: Validation result to update

        Returns:
            True if valid, False otherwise
        """
        if not results.sprite:
            return True  # No error if no sprites

        sprite = results.sprite

        # Check sprite images exist (handle both single path and list of paths)
        sprite_paths = (
            [sprite.sprite_path] if isinstance(sprite.sprite_path, Path) else sprite.sprite_path
        )

        for sprite_path in sprite_paths:
            if not sprite_path.exists():
                validation.add_error(f"Sprite image not found: {sprite_path}")
                return False

        # Check VTT file exists
        if not sprite.vtt_path.exists():
            validation.add_error(f"Sprite VTT file not found: {sprite.vtt_path}")
            return False

        # Validate VTT content
        try:
            content = sprite.vtt_path.read_text()

            if not content.startswith("WEBVTT"):
                validation.add_error("Sprite VTT missing WEBVTT header")
                return False

            # Check for cue entries
            if sprite.thumbnail_count > 0 and "-->" not in content:
                validation.add_error("Sprite VTT missing cue entries")
                return False

            # Count cue entries
            cue_count = content.count("-->")
            if cue_count != sprite.thumbnail_count:
                validation.add_warning(
                    f"Sprite VTT cue count mismatch "
                    f"(expected {sprite.thumbnail_count}, found {cue_count})"
                )

            self.logger.debug(f"Sprite files validated ({len(sprite_paths)} sheet(s))")
            return True

        except Exception as e:
            validation.add_error(f"Failed to validate sprite VTT: {e}")
            return False

    def _validate_metadata(self, results: TranscodingResults, validation: ValidationResult) -> bool:
        """
        Validate metadata file.

        Args:
            results: Transcoding results
            validation: Validation result to update

        Returns:
            True if valid, False otherwise
        """
        if not results.metadata_file:
            validation.add_warning("No metadata file specified")
            return True

        metadata_path = results.metadata_file

        # Check file exists
        if not metadata_path.exists():
            validation.add_warning(f"Metadata file not found: {metadata_path}")
            return False

        # Check file not empty
        if metadata_path.stat().st_size == 0:
            validation.add_warning("Metadata file is empty")
            return False

        # Validate JSON format
        try:
            with metadata_path.open() as f:
                metadata = json.load(f)

            # Check for expected keys
            expected_keys = ["version", "master_playlist"]
            for key in expected_keys:
                if key not in metadata:
                    validation.add_warning(f"Metadata missing key: {key}")

            self.logger.debug("Metadata file validated")
            return True

        except json.JSONDecodeError as e:
            validation.add_warning(f"Invalid JSON in metadata file: {e}")
            return False
        except Exception as e:
            validation.add_warning(f"Failed to validate metadata: {e}")
            return False

    def _extract_segment_paths(self, playlist_content: str, playlist_dir: Path) -> list[Path]:
        """
        Extract segment file paths from playlist.

        Args:
            playlist_content: Playlist file content
            playlist_dir: Directory containing playlist

        Returns:
            List of segment file paths
        """
        segments = []
        lines = playlist_content.split("\n")

        for line in lines:
            line = line.strip()
            # Skip comments and empty lines
            if line.startswith("#") or not line:
                continue
            # Segment filenames don't start with # and typically end with .ts or .m4s
            if line.endswith((".ts", ".m4s", ".mp4", ".aac")):
                segment_path = playlist_dir / line
                segments.append(segment_path)

        return segments

    def validate_playlist_syntax(self, playlist_path: Path) -> ValidationResult:
        """
        Validate HLS playlist syntax.

        Args:
            playlist_path: Path to playlist file

        Returns:
            ValidationResult with syntax validation
        """
        validation = ValidationResult(success=True)

        if not playlist_path.exists():
            validation.add_error(f"Playlist not found: {playlist_path}")
            return validation

        try:
            content = playlist_path.read_text()

            # Must start with #EXTM3U
            if not content.startswith("#EXTM3U"):
                validation.add_error("Playlist missing #EXTM3U header")

            # Check for common HLS tags
            lines = content.split("\n")
            has_extinf = False
            has_endlist = False

            for line in lines:
                line = line.strip()
                if line.startswith("#EXTINF:"):
                    has_extinf = True
                if line == "#EXT-X-ENDLIST":
                    has_endlist = True

            if has_extinf and not has_endlist:
                validation.add_warning("Playlist missing #EXT-X-ENDLIST tag")

            self.logger.debug(f"Playlist syntax validated: {playlist_path}")

        except Exception as e:
            validation.add_error(f"Failed to validate playlist syntax: {e}")

        return validation

    def check_segments_complete(
        self, playlist_path: Path, expected_count: Optional[int] = None
    ) -> tuple[bool, int, int]:
        """
        Check if all segments referenced in playlist exist.

        Args:
            playlist_path: Path to playlist file
            expected_count: Expected number of segments (optional)

        Returns:
            Tuple of (all_present, found_count, missing_count)
        """
        if not playlist_path.exists():
            return (False, 0, 0)

        try:
            content = playlist_path.read_text()
            segments = self._extract_segment_paths(content, playlist_path.parent)

            found = 0
            missing = 0

            for segment in segments:
                if segment.exists():
                    found += 1
                else:
                    missing += 1
                    self.logger.warning(f"Missing segment: {segment}")

            if expected_count is not None and found != expected_count:
                self.logger.warning(
                    f"Segment count mismatch: expected {expected_count}, found {found}"
                )

            return (missing == 0, found, missing)

        except Exception as e:
            self.logger.error(f"Failed to check segments: {e}")
            return (False, 0, 0)


def validate_output(output_dir: Path, results: TranscodingResults) -> ValidationResult:
    """
    Convenience function to validate transcoding output.

    Args:
        output_dir: Output directory path
        results: Transcoding results

    Returns:
        ValidationResult
    """
    validator = OutputValidator(output_dir)
    return validator.validate(results)


def quick_validate(output_dir: Path, master_playlist: Path) -> bool:
    """
    Quick validation of output directory.

    Args:
        output_dir: Output directory path
        master_playlist: Master playlist path

    Returns:
        True if basic validation passes
    """
    # Check output directory exists
    if not output_dir.exists():
        logger.error(f"Output directory not found: {output_dir}")
        return False

    # Check master playlist exists
    if not master_playlist.exists():
        logger.error(f"Master playlist not found: {master_playlist}")
        return False

    # Check master playlist not empty
    if master_playlist.stat().st_size == 0:
        logger.error("Master playlist is empty")
        return False

    # Check master playlist has proper header
    try:
        content = master_playlist.read_text()
        if not content.startswith("#EXTM3U"):
            logger.error("Master playlist missing #EXTM3U header")
            return False
    except Exception as e:
        logger.error(f"Failed to read master playlist: {e}")
        return False

    logger.info("Quick validation passed")
    return True
