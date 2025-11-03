"""
Summary reporting for transcoding results.

This module provides rich console output for displaying transcoding
results, statistics, and validation information.
"""

from pathlib import Path
from typing import Optional

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich.tree import Tree

from ..models.results import TranscodingResults, ValidationResult
from ..utils import format_duration, format_size, get_logger

logger = get_logger(__name__)


class SummaryReporter:
    """
    Reporter for displaying transcoding results.

    This class creates formatted console output for:
    - Video variants summary
    - Audio tracks summary
    - Subtitle tracks summary
    - Sprite generation summary
    - Performance metrics
    - Validation results
    """

    def __init__(self, console: Optional[Console] = None):
        """
        Initialize summary reporter.

        Args:
            console: Rich console instance (creates new if not provided)
        """
        self.console = console or Console()
        self.logger = logger

    def display_summary(
        self,
        results: TranscodingResults,
        validation: Optional[ValidationResult] = None,
    ) -> None:
        """
        Display complete transcoding summary.

        Args:
            results: Transcoding results
            validation: Optional validation results
        """
        self.console.print()
        self.console.rule("[bold green]Transcoding Complete", style="green")
        self.console.print()

        # Overview
        self._display_overview(results)

        # Video variants
        if results.video_count > 0:
            self._display_video_variants(results)

        # Audio tracks
        if results.audio_count > 0:
            self._display_audio_tracks(results)

        # Subtitle tracks
        if results.subtitle_count > 0:
            self._display_subtitle_tracks(results)

        # Sprites
        if results.sprite is not None:
            self._display_sprites(results)

        # Performance metrics
        self._display_performance_metrics(results)

        # Validation results
        if validation:
            self._display_validation_results(validation)

        # Output location
        self._display_output_location(results)

        self.console.print()

    def _display_overview(self, results: TranscodingResults) -> None:
        """
        Display overview statistics.

        Args:
            results: Transcoding results
        """
        table = Table(title="Overview", show_header=False, box=None)
        table.add_column("Metric", style="cyan", width=30)
        table.add_column("Value", style="white")

        table.add_row("Video Variants", str(results.video_count))
        table.add_row("Audio Tracks", str(results.audio_count))
        table.add_row("Subtitle Tracks", str(results.subtitle_count))
        table.add_row("Sprites Generated", "Yes" if results.sprite is not None else "No")
        table.add_row(
            "Total Output Size",
            f"{format_size(results.total_size)} ({results.total_size_gb:.2f} GB)",
        )
        table.add_row("Duration", format_duration(results.total_duration))

        if results.compression_ratio > 0:
            table.add_row("Compression Ratio", f"{results.compression_ratio:.2f}x")

        self.console.print(table)
        self.console.print()

    def _display_video_variants(self, results: TranscodingResults) -> None:
        """
        Display video variants table.

        Args:
            results: Transcoding results
        """
        table = Table(title="Video Variants", show_header=True)
        table.add_column("Quality", style="cyan", width=12)
        table.add_column("Resolution", style="yellow", width=12)
        table.add_column("Bitrate", style="green", width=10)
        table.add_column("Segments", style="magenta", width=10)
        table.add_column("Size", style="blue", width=15)
        table.add_column("Playlist", style="white", width=30)

        for variant in results.video_variants:
            table.add_row(
                variant.quality,
                variant.resolution,
                variant.bitrate,
                str(variant.segment_count),
                format_size(variant.size),
                variant.playlist_path.name,
            )

        self.console.print(table)
        self.console.print()

    def _display_audio_tracks(self, results: TranscodingResults) -> None:
        """
        Display audio tracks table.

        Args:
            results: Transcoding results
        """
        table = Table(title="Audio Tracks", show_header=True)
        table.add_column("Index", style="cyan", width=8)
        table.add_column("Language", style="yellow", width=12)
        table.add_column("Codec", style="green", width=10)
        table.add_column("Size", style="blue", width=15)
        table.add_column("Playlist", style="white", width=30)

        for track in results.audio_tracks:
            table.add_row(
                str(track.index),
                track.language,
                track.codec,
                format_size(track.size),
                track.playlist_path.name,
            )

        self.console.print(table)
        self.console.print()

    def _display_subtitle_tracks(self, results: TranscodingResults) -> None:
        """
        Display subtitle tracks table.

        Args:
            results: Transcoding results
        """
        table = Table(title="Subtitle Tracks", show_header=True)
        table.add_column("Index", style="cyan", width=8)
        table.add_column("Language", style="yellow", width=12)
        table.add_column("Format", style="green", width=10)
        table.add_column("Status", style="magenta", width=10)
        table.add_column("File", style="white", width=35)

        for subtitle in results.subtitle_tracks:
            status = "✓ Exists" if subtitle.exists else "✗ Missing"
            status_style = "green" if subtitle.exists else "red"

            table.add_row(
                str(subtitle.index),
                subtitle.language,
                subtitle.format,
                Text(status, style=status_style),
                subtitle.file_path.name,
            )

        self.console.print(table)
        self.console.print()

    def _display_sprites(self, results: TranscodingResults) -> None:
        """
        Display sprite generation info.

        Args:
            results: Transcoding results
        """
        if not results.sprite:
            return

        sprite = results.sprite

        table = Table(title="Sprite Generation", show_header=False, box=None)
        table.add_column("Metric", style="cyan", width=30)
        table.add_column("Value", style="white")

        table.add_row("Thumbnails Generated", str(sprite.thumbnail_count))
        table.add_row("Sprite Image", sprite.sprite_path.name)
        table.add_row("VTT File", sprite.vtt_path.name)
        table.add_row("Total Size", format_size(sprite.size))

        status = "✓ Valid" if sprite.exists else "✗ Missing Files"
        status_style = "green" if sprite.exists else "red"
        table.add_row("Status", Text(status, style=status_style))

        self.console.print(table)
        self.console.print()

    def _display_performance_metrics(self, results: TranscodingResults) -> None:
        """
        Display performance metrics.

        Args:
            results: Transcoding results
        """
        table = Table(title="Performance Metrics", show_header=False, box=None)
        table.add_column("Metric", style="cyan", width=30)
        table.add_column("Value", style="white")

        table.add_row("Hardware Used", results.hardware_used)
        table.add_row("Parallel Jobs", str(results.parallel_jobs))

        if results.total_frames > 0:
            table.add_row("Total Frames", f"{results.total_frames:,}")

        self.console.print(table)
        self.console.print()

    def _display_validation_results(self, validation: ValidationResult) -> None:
        """
        Display validation results.

        Args:
            validation: Validation results
        """
        # Overall status
        if validation.is_valid:
            status_text = Text("✓ PASSED", style="bold green")
        else:
            status_text = Text("✗ FAILED", style="bold red")

        panel_title = f"Validation Status: {status_text.plain}"
        panel_style = "green" if validation.is_valid else "red"

        # Create validation details
        details = []

        # Component statuses
        components = [
            ("Master Playlist", validation.master_playlist_valid),
            ("Segments", validation.all_segments_present),
            ("Audio Sync", validation.audio_sync_valid),
            ("Subtitle Files", validation.subtitle_files_valid),
        ]

        component_status = []
        for name, valid in components:
            status = "✓" if valid else "✗"
            style = "green" if valid else "red"
            component_status.append(Text(f"{status} {name}", style=style))

        if component_status:
            details.append(Text.assemble(*[Text("\n").join(component_status)]))

        # Errors
        if validation.has_errors:
            details.append(Text())
            details.append(Text(f"Errors ({len(validation.errors)}):", style="bold red"))
            for error in validation.errors:
                details.append(Text(f"  • {error}", style="red"))

        # Warnings
        if validation.has_warnings:
            details.append(Text())
            details.append(Text(f"Warnings ({len(validation.warnings)}):", style="bold yellow"))
            for warning in validation.warnings:
                details.append(Text(f"  • {warning}", style="yellow"))

        # Show "no issues" message only if we have no errors or warnings
        if not validation.has_errors and not validation.has_warnings:
            details.append(Text())
            details.append(Text("No validation issues detected.", style="green"))

        panel_content = Text("\n").join(details)
        panel = Panel(panel_content, title=panel_title, border_style=panel_style)

        self.console.print(panel)
        self.console.print()

    def _display_output_location(self, results: TranscodingResults) -> None:
        """
        Display output file locations.

        Args:
            results: Transcoding results
        """
        tree = Tree("📁 [bold cyan]Output Files", guide_style="dim")

        # Master playlist
        if results.master_playlist:
            tree.add(f"[green]master.m3u8[/green] - {results.master_playlist}")

        # Video variants
        if results.video_count > 0:
            video_branch = tree.add("[cyan]Video Variants")
            for variant in results.video_variants:
                video_branch.add(f"[yellow]{variant.quality}[/yellow] - {variant.playlist_path}")

        # Audio tracks
        if results.audio_count > 0:
            audio_branch = tree.add("[cyan]Audio Tracks")
            for track in results.audio_tracks:
                audio_branch.add(f"[yellow]{track.language}[/yellow] - {track.playlist_path}")

        # Subtitles
        if results.subtitle_count > 0:
            subtitle_branch = tree.add("[cyan]Subtitles")
            for subtitle in results.subtitle_tracks:
                subtitle_branch.add(f"[yellow]{subtitle.language}[/yellow] - {subtitle.file_path}")

        # Sprites
        if results.sprite is not None:
            sprite_branch = tree.add("[cyan]Sprites")
            sprite_branch.add(f"[yellow]Image[/yellow] - {results.sprite.sprite_path}")
            sprite_branch.add(f"[yellow]VTT[/yellow] - {results.sprite.vtt_path}")

        # Metadata
        if results.metadata_file:
            tree.add(f"[green]metadata.json[/green] - {results.metadata_file}")

        self.console.print(tree)
        self.console.print()

    def display_error(self, message: str, error: Optional[Exception] = None) -> None:
        """
        Display error message.

        Args:
            message: Error message
            error: Optional exception object
        """
        error_text = Text(f"✗ {message}", style="bold red")

        if error:
            details = Text(f"\n{str(error)}", style="red")
            error_text.append(details)

        panel = Panel(error_text, title="Error", border_style="red")
        self.console.print()
        self.console.print(panel)
        self.console.print()

    def display_success(self, message: str) -> None:
        """
        Display success message.

        Args:
            message: Success message
        """
        success_text = Text(f"✓ {message}", style="bold green")
        panel = Panel(success_text, title="Success", border_style="green")
        self.console.print()
        self.console.print(panel)
        self.console.print()

    def display_info(self, message: str) -> None:
        """
        Display info message.

        Args:
            message: Info message
        """
        # Use Text object to prevent ANSI splitting issues
        info_text = Text.from_markup(f"[cyan]ℹ {message}[/cyan]")
        self.console.print(info_text)


def display_transcoding_summary(
    results: TranscodingResults,
    validation: Optional[ValidationResult] = None,
    console: Optional[Console] = None,
) -> None:
    """
    Convenience function to display transcoding summary.

    Args:
        results: Transcoding results
        validation: Optional validation results
        console: Optional console instance
    """
    reporter = SummaryReporter(console)
    reporter.display_summary(results, validation)


def create_summary_table(results: TranscodingResults) -> Table:
    """
    Create a summary table for transcoding results.

    Args:
        results: Transcoding results

    Returns:
        Rich Table object
    """
    table = Table(title="Transcoding Summary", show_header=True)
    table.add_column("Component", style="cyan")
    table.add_column("Count", style="yellow")
    table.add_column("Total Size", style="green")

    table.add_row(
        "Video Variants",
        str(results.video_count),
        format_size(sum(v.size for v in results.video_variants)),
    )

    table.add_row(
        "Audio Tracks",
        str(results.audio_count),
        format_size(sum(a.size for a in results.audio_tracks)),
    )

    table.add_row(
        "Subtitle Tracks",
        str(results.subtitle_count),
        "N/A",
    )

    if results.has_sprites and results.sprite:
        table.add_row(
            "Sprites",
            str(results.sprite.thumbnail_count),
            format_size(results.sprite.size),
        )

    table.add_row(
        "[bold]Total[/bold]",
        "",
        f"[bold]{format_size(results.total_size)}[/bold]",
    )

    return table
