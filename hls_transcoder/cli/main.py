"""
CLI interface for HLS Video Transcoder.

This module provides the command-line interface using Typer and Rich
for beautiful terminal output.
"""

import asyncio
import sys
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Confirm
from rich.table import Table
from rich.text import Text

from ..models import AudioTrackResult, TranscodingResults, VideoVariantResult
from ..config import get_config_manager
from ..executor import ParallelExecutor
from ..hardware import HardwareDetector
from ..inspector import MediaInspector
from ..planner import ExecutionPlanner
from ..playlist import (
    AudioTrackInfo,
    PlaylistGenerator,
    VideoVariantInfo,
    create_audio_track_info,
    create_video_variant_info,
)
from ..ui import SummaryReporter, TranscodingMonitor
from ..utils import (
    ConfigurationError,
    TranscoderError,
    format_duration,
    format_size,
    get_logger,
    setup_logger,
)
from ..validator import OutputValidator

# Initialize Typer app
app = typer.Typer(
    name="hls-transcoder",
    help="Convert video files to HLS format with hardware acceleration",
    add_completion=False,
)

# Console for rich output
console = Console()

# Logger
logger = get_logger(__name__)


@app.command()
def transcode(
    input_file: Path = typer.Argument(
        ...,
        exists=True,
        dir_okay=False,
        readable=True,
        help="Input video file to transcode",
    ),
    output_dir: Optional[Path] = typer.Option(
        None,
        "--output",
        "-o",
        help="Output directory (default: ./output)",
    ),
    quality: str = typer.Option(
        "medium",
        "--quality",
        "-q",
        help="Quality profile: low, medium, high",
    ),
    hardware: str = typer.Option(
        "auto",
        "--hardware",
        "-hw",
        help="Hardware acceleration: auto, nvenc, qsv, amf, vaapi, videotoolbox, none",
    ),
    original_only: bool = typer.Option(
        False,
        "--original-only",
        help="Only transcode to original resolution (no quality ladder)",
    ),
    no_audio: bool = typer.Option(
        False,
        "--no-audio",
        help="Skip audio extraction",
    ),
    no_subtitles: bool = typer.Option(
        False,
        "--no-subtitles",
        help="Skip subtitle extraction",
    ),
    no_sprites: bool = typer.Option(
        False,
        "--no-sprites",
        help="Skip sprite generation",
    ),
    audio_quality: str = typer.Option(
        "medium",
        "--audio-quality",
        help="Audio quality: low, medium, high",
    ),
    config_file: Optional[Path] = typer.Option(
        None,
        "--config",
        "-c",
        exists=True,
        dir_okay=False,
        help="Custom configuration file",
    ),
    verbose: bool = typer.Option(
        False,
        "--verbose",
        "-v",
        help="Enable verbose logging",
    ),
    log_file: Optional[Path] = typer.Option(
        None,
        "--log",
        help="Log file path",
    ),
    yes_flag: bool = typer.Option(
        False,
        "--yes",
        "-y",
        help="Automatic yes to prompts; run non-interactively",
    ),
) -> None:
    """
    Transcode a video file to HLS format.

    This command inspects the input video, detects available hardware acceleration,
    creates an execution plan, and transcodes the video in parallel with progress tracking.
    """
    # Setup logging with console integration
    log_level = "DEBUG" if verbose else "INFO"
    setup_logger(
        name="hls_transcoder",
        level=log_level,
        log_file=log_file,
        verbose=verbose,
        console=console,  # Pass console for Rich integration
    )

    # Display header
    console.print()
    console.print(
        Panel.fit(
            "[bold cyan]HLS Video Transcoder[/bold cyan]\n"
            "[dim]Fast • Parallel • Hardware Accelerated[/dim]",
            border_style="cyan",
        )
    )
    console.print()

    # Set output directory
    if output_dir is None:
        output_dir = Path.cwd() / "output"

    try:
        # Run async transcode
        asyncio.run(
            _transcode_async(
                input_file=input_file,
                output_dir=output_dir,
                quality=quality,
                hardware=hardware,
                original_only=original_only,
                no_audio=no_audio,
                no_subtitles=no_subtitles,
                no_sprites=no_sprites,
                audio_quality=audio_quality,
                config_file=config_file,
                verbose=verbose,
                yes_flag=yes_flag,
            )
        )

    except KeyboardInterrupt:
        console.print("\n[yellow]⚠ Transcoding cancelled by user[/yellow]")
        sys.exit(130)
    except TranscoderError as e:
        console.print(f"\n[bold red]✗ Error:[/bold red] {e}")
        if verbose:
            console.print_exception()
        sys.exit(1)
    except Exception as e:
        console.print(f"\n[bold red]✗ Unexpected error:[/bold red] {e}")
        if verbose:
            console.print_exception()
        sys.exit(1)


async def _transcode_async(
    input_file: Path,
    output_dir: Path,
    quality: str,
    hardware: str,
    original_only: bool,
    no_audio: bool,
    no_subtitles: bool,
    no_sprites: bool,
    audio_quality: str,
    config_file: Optional[Path],
    verbose: bool,
    yes_flag: bool,
) -> None:
    """
    Async implementation of transcode workflow.
    """
    reporter = SummaryReporter(console)

    # Step 1: Load configuration
    console.print("[cyan]📋 Loading configuration...[/cyan]")
    config_manager = get_config_manager()

    if config_file:
        try:
            config_manager.load(config_file)
            console.print(f"   [green]✓[/green] Loaded config from {config_file}")
        except Exception as e:
            raise ConfigurationError(f"Failed to load config: {e}")
    else:
        config = config_manager.config

    config = config_manager.config

    # Override with CLI arguments
    if quality not in config.profiles:
        raise ConfigurationError(f"Unknown quality profile: {quality}")

    if hardware != "auto":
        config.hardware.prefer = hardware

    console.print()

    # Step 2: Detect hardware
    console.print("[cyan]🔍 Detecting hardware acceleration...[/cyan]")
    detector = HardwareDetector()
    hardware_info = await detector.detect(prefer=config.hardware.prefer, test_encoding=True)

    if hardware_info.selected_encoder:
        console.print(
            f"   [green]✓[/green] Using {hardware_info.selected_encoder.hardware_type.value.upper()}: "
            f"{hardware_info.selected_encoder.name}"
        )
    else:
        console.print(
            "   [yellow]⚠[/yellow] No hardware acceleration available, using software encoding"
        )

    console.print()

    # Step 3: Inspect media
    console.print("[cyan]🎬 Inspecting video file...[/cyan]")
    inspector = MediaInspector()

    try:
        media_info = await inspector.inspect(input_file)
    except Exception as e:
        raise TranscoderError(f"Failed to inspect video: {e}")

    # Display media info
    console.print(f"   [green]✓[/green] File: {input_file.name}")
    console.print(f"   Duration: {format_duration(media_info.duration)}")
    console.print(f"   Size: {format_size(media_info.size)}")

    if media_info.video_streams:
        video = media_info.video_streams[0]
        console.print(
            f"   Video: {video.codec} ({video.codec_long}), "
            f"{video.width}x{video.height}, {video.fps:.2f} FPS"
        )

    if media_info.audio_streams:
        console.print(f"   Audio: {len(media_info.audio_streams)} track(s)")

    if media_info.subtitle_streams:
        console.print(f"   Subtitles: {len(media_info.subtitle_streams)} track(s)")

    console.print()

    # Step 4: Create execution plan
    console.print("[cyan]📐 Creating execution plan...[/cyan]")
    planner = ExecutionPlanner(
        input_file=input_file,
        media_info=media_info,
        hardware_info=hardware_info,
        config=config,
        output_dir=output_dir,
        profile_name=quality,
    )

    try:
        plan = planner.create_plan(
            include_audio=not no_audio,
            include_subtitles=not no_subtitles,
            include_sprites=not no_sprites,
            original_only=original_only,
        )
    except Exception as e:
        raise TranscoderError(f"Failed to create plan: {e}")

    # Display plan summary
    console.print(f"   [green]✓[/green] Video variants: {len(plan.video_tasks)}")
    if not no_audio and media_info.audio_streams:
        console.print(f"   Audio tracks: {len(plan.audio_tasks)}")
    if not no_subtitles and media_info.subtitle_streams:
        console.print(f"   Subtitles: {len(plan.subtitle_tasks)}")
    if not no_sprites:
        console.print(f"   Sprites: {1 if plan.sprite_task else 0}")

    # Display resource estimates
    estimate = planner.estimate_resources(plan)
    console.print(f"   Estimated time: {format_duration(estimate.estimated_duration)}")
    console.print(f"   Estimated size: {format_size(estimate.estimated_output_size)}")

    console.print()

    # Ask for confirmation (skip if -y flag is provided)
    if not yes_flag:
        if not Confirm.ask("   [yellow]Proceed with transcoding?[/yellow]", default=True):
            console.print("[yellow]Transcoding cancelled[/yellow]")
            return

    console.print()

    # Step 5: Execute transcoding
    console.print("[cyan]⚙️  Starting transcoding...[/cyan]")
    console.print()

    # Create output directory
    output_dir.mkdir(parents=True, exist_ok=True)

    # Create execution strategy
    strategy = planner.create_execution_strategy(plan)

    # Create executor
    executor = ParallelExecutor(
        input_file=input_file,
        output_dir=output_dir,
        media_info=media_info,
        hardware_info=hardware_info,
        config=config,
        strategy=strategy,
    )

    # Execute tasks with TranscodingMonitor UI
    with TranscodingMonitor(console=console) as monitor:
        # Create tasks for monitoring
        task_monitors = {}

        # Video tasks
        for task in plan.video_tasks:
            task_id = f"video_{task.quality}"
            task_name = f"Video {task.quality.upper()}"
            monitor.create_task(task_id, task_name, total=100.0)
            monitor.start_task(task_id)
            task_monitors[task.task_id] = task_id

        # Audio tasks
        for idx, task in enumerate(plan.audio_tasks):
            # Safely get stream info
            if task.stream_index < len(media_info.audio_streams):
                stream = media_info.audio_streams[task.stream_index]
                language = stream.language or "und"
            else:
                language = task.language or "und"

            task_id = f"audio_{language}_{idx}"
            task_name = f"Audio {language.upper()}"
            monitor.create_task(task_id, task_name, total=100.0)
            monitor.start_task(task_id)
            task_monitors[task.task_id] = task_id

        # Subtitle tasks
        for idx, task in enumerate(plan.subtitle_tasks):
            # Safely get stream info
            if task.stream_index < len(media_info.subtitle_streams):
                stream = media_info.subtitle_streams[task.stream_index]
                language = stream.language or "und"
            else:
                language = "und"

            task_id = f"subtitle_{language}_{idx}"
            task_name = f"Subtitle {language.upper()}"
            monitor.create_task(task_id, task_name, total=100.0)
            monitor.start_task(task_id)
            task_monitors[task.task_id] = task_id

        # Sprite task
        if plan.sprite_task:
            task_id = "sprites"
            task_name = "Thumbnails"
            monitor.create_task(task_id, task_name, total=100.0)
            monitor.start_task(task_id)
            task_monitors[plan.sprite_task.task_id] = task_id

        # Track task progress
        task_progress = {tid: 0.0 for tid in task_monitors.keys()}

        # Progress callback
        def progress_callback(completed: int, total: int) -> None:
            # Overall progress callback (not used currently)
            pass

        # We need to update the executor to pass task-level progress
        # For now, we'll poll task status
        async def update_monitor():
            """Poll tasks and update monitor."""
            while True:
                for task_id, monitor_id in task_monitors.items():
                    # Find task in plan
                    all_tasks = (
                        plan.video_tasks
                        + plan.audio_tasks
                        + plan.subtitle_tasks
                        + ([plan.sprite_task] if plan.sprite_task else [])
                    )

                    for task in all_tasks:
                        if task.task_id == task_id:
                            # Update progress if changed
                            if task.progress != task_progress[task_id]:
                                task_progress[task_id] = task.progress
                                monitor.update_task(
                                    monitor_id, progress=task.progress, speed=task.speed
                                )

                            # Update status
                            if task.status.value == "completed":
                                monitor.complete_task(monitor_id)
                            elif task.status.value == "failed":
                                monitor.fail_task(monitor_id, task.error or "Unknown error")
                            break

                await asyncio.sleep(0.1)  # Update 10 times per second

        # Start monitor update task
        monitor_task = asyncio.create_task(update_monitor())

        # Execute
        try:
            summary = await executor.execute_tasks(
                video_tasks=plan.video_tasks,
                audio_tasks=plan.audio_tasks,
                subtitle_tasks=plan.subtitle_tasks,
                sprite_task=plan.sprite_task,
                progress_callback=progress_callback,
            )
        except Exception as e:
            raise TranscoderError(f"Transcoding failed: {e}")
        finally:
            # Stop monitor update task
            monitor_task.cancel()
            try:
                await monitor_task
            except asyncio.CancelledError:
                pass

    console.print()

    # Check for failures
    if summary.has_failures:
        console.print(
            f"[yellow]⚠ Transcoding completed with {summary.failed_tasks} failure(s)[/yellow]"
        )
        console.print()

    # Step 6: Generate playlists
    console.print("[cyan]📝 Generating playlists...[/cyan]")

    # Collect results
    video_variants: list[VideoVariantInfo] = []
    audio_tracks: list[AudioTrackInfo] = []

    from ..models import VideoTask, AudioTask

    for result in summary.results:
        if result.success and result.output_path and result.task.task_type.value == "video":
            # Get video task details - cast to VideoTask
            task = result.task
            if isinstance(task, VideoTask):
                variant_info = create_video_variant_info(
                    quality=task.quality,
                    width=task.width,
                    height=task.height,
                    bitrate=int(task.bitrate.rstrip("k")),
                    framerate=media_info.video_streams[0].fps,
                    playlist_path=result.output_path,
                    segment_count=0,  # Will be counted by validator
                )
                video_variants.append(variant_info)

        elif result.success and result.output_path and result.task.task_type.value == "audio":
            # Get audio task details - cast to AudioTask
            task = result.task
            if isinstance(task, AudioTask):
                # Find the audio stream by its absolute index
                stream = next(
                    (s for s in media_info.audio_streams if s.index == task.stream_index), None
                )

                if stream:
                    # Create descriptive track name
                    # Format: "Language [Bitrate]k [ChannelLayout]"
                    # Examples: "English 128k", "Hindi 192k 5.1", "Spanish 96k Stereo"
                    language_name = stream.language or "und"
                    bitrate_kbps = int(task.bitrate.rstrip("k"))

                    # Build track name with bitrate and channel info for clarity
                    channel_layouts = {1: "Mono", 2: "Stereo", 6: "5.1", 8: "7.1"}
                    channel_desc = channel_layouts.get(stream.channels, f"{stream.channels}ch")

                    # Include bitrate if multiple qualities might exist
                    # Include channel layout if not stereo (stereo is assumed default)
                    track_name = language_name.upper()
                    if stream.channels != 2:
                        track_name += f" {channel_desc}"

                    track_info = create_audio_track_info(
                        name=track_name,
                        language=stream.language or "und",
                        channels=stream.channels,
                        sample_rate=stream.sample_rate,
                        bitrate=bitrate_kbps,
                        playlist_path=result.output_path,
                        is_default=(stream == media_info.audio_streams[0]),
                    )
                    audio_tracks.append(track_info)
                else:
                    console.print(
                        f"[yellow]⚠ Warning: Audio stream with absolute index {task.stream_index} not found in media info, skipping track[/yellow]"
                    )

    if video_variants:
        generator = PlaylistGenerator(output_dir)

        try:
            master_path = generator.generate_master_playlist(
                video_variants=video_variants,
                audio_tracks=audio_tracks if audio_tracks else None,
            )
            console.print(f"   [green]✓[/green] Generated {master_path.name}")

            # Generate metadata
            metadata_path = generator.generate_metadata(
                video_variants=video_variants,
                audio_tracks=audio_tracks if audio_tracks else None,
                source_info={
                    "filename": input_file.name,
                    "size": media_info.size,
                    "duration": media_info.duration,
                },
            )
            console.print(f"   [green]✓[/green] Generated {metadata_path.name}")

        except Exception as e:
            console.print(f"   [yellow]⚠[/yellow] Failed to generate playlists: {e}")

    console.print()

    # Step 7: Validate output
    console.print("[cyan]✅ Validating output...[/cyan]")
    validator = OutputValidator(output_dir)

    # Create results for validation with actual data

    # Convert variant info objects to VideoVariantResult objects
    video_variant_results: list[VideoVariantResult] = []
    for variant in video_variants:
        # Count segments from playlist if it exists
        playlist_path = variant.playlist_path
        segment_count = 0
        variant_size = 0

        if playlist_path.exists():
            content = playlist_path.read_text()
            segment_count = content.count("#EXTINF:")

            # Calculate total size of all segments
            segment_dir = playlist_path.parent
            for segment_file in segment_dir.glob("*.ts"):
                variant_size += segment_file.stat().st_size

        video_variant_results.append(
            VideoVariantResult(
                quality=variant.quality,
                width=variant.width,
                height=variant.height,
                bitrate=str(variant.bitrate) + "k",
                size=variant_size,
                segment_count=segment_count,
                duration=media_info.duration,
                playlist_path=playlist_path,
            )
        )

    # Convert audio track info to AudioTrackResult objects
    audio_track_results: list[AudioTrackResult] = []
    for idx, track in enumerate(audio_tracks):
        # Calculate total size of all segments
        track_size = 0

        if track.playlist_path.exists():
            # Calculate total size of all segments
            segment_dir = track.playlist_path.parent
            for segment_file in segment_dir.glob("*.ts"):
                track_size += segment_file.stat().st_size

        audio_track_results.append(
            AudioTrackResult(
                index=idx,
                language=track.language,
                codec=config.audio.codec,  # Use actual codec from config
                size=track_size,
                playlist_path=track.playlist_path,
            )
        )

    # Build complete results object for validation and reporting
    results = TranscodingResults(
        video_variants=video_variant_results,
        audio_tracks=audio_track_results,
        subtitle_tracks=[],
        sprite=None,
        master_playlist=output_dir / "master.m3u8",
        metadata_file=output_dir / "metadata.json",
        total_duration=(
            summary.total_duration if hasattr(summary, "total_duration") else media_info.duration
        ),
        hardware_used=(
            hardware_info.selected_encoder.name if hardware_info.selected_encoder else "software"
        ),
        parallel_jobs=summary.total_tasks if hasattr(summary, "total_tasks") else plan.total_tasks,
    )

    try:
        validation = validator.validate(results)

        if validation.is_valid:
            console.print("   [green]✓[/green] Validation passed")
        else:
            console.print(
                f"   [yellow]⚠[/yellow] Validation found {len(validation.errors)} error(s)"
            )

    except Exception as e:
        console.print(f"   [yellow]⚠[/yellow] Validation failed: {e}")
        validation = None

    console.print()

    # Step 8: Display summary
    reporter.display_summary(results, validation)

    # Final message
    if validation and validation.is_valid:
        console.print(
            Panel.fit(
                "[bold green]✓ Transcoding completed successfully![/bold green]\n"
                f"[dim]Output: {output_dir}[/dim]",
                border_style="green",
            )
        )
    else:
        console.print(
            Panel.fit(
                "[bold yellow]⚠ Transcoding completed with issues[/bold yellow]\n"
                f"[dim]Output: {output_dir}[/dim]",
                border_style="yellow",
            )
        )


@app.command("config")
def config_command(
    action: str = typer.Argument(..., help="Action: init, show"),
    output: Optional[Path] = typer.Option(
        None,
        "--output",
        "-o",
        help="Output file for 'init' action",
    ),
) -> None:
    """
    Manage configuration files.

    Actions:
    - init: Create a default configuration file
    - show: Display current configuration
    """
    if action == "init":
        config_manager = get_config_manager()
        output_path = output or Path(".hls-transcoder.yaml")

        try:
            config_manager.init_default_config(output_path)
            console.print(f"[green]✓[/green] Created config file: {output_path}")
        except Exception as e:
            console.print(f"[red]✗ Error:[/red] {e}")
            sys.exit(1)

    elif action == "show":
        config_manager = get_config_manager()
        config = config_manager.config

        # Display configuration
        console.print()
        console.print(Panel("[bold cyan]Current Configuration[/bold cyan]", border_style="cyan"))
        console.print()

        # Hardware
        table = Table(title="Hardware Settings", show_header=True)
        table.add_column("Setting", style="cyan")
        table.add_column("Value", style="white")
        table.add_row("Prefer", config.hardware.prefer)
        table.add_row("Fallback", config.hardware.fallback)
        table.add_row("Max Instances", str(config.hardware.max_instances))
        console.print(table)
        console.print()

        # Profiles
        console.print("[bold]Quality Profiles:[/bold]")
        for profile_name, variants in config.profiles.items():
            console.print(f"  • {profile_name}: {len(variants)} variant(s)")
        console.print()

    else:
        console.print(f"[red]✗ Unknown action:[/red] {action}")
        console.print("Valid actions: init, show")
        sys.exit(1)


@app.command("hardware")
def hardware_command() -> None:
    """
    Detect and display available hardware acceleration.
    """
    console.print()
    console.print(Panel("[bold cyan]Hardware Detection[/bold cyan]", border_style="cyan"))
    console.print()

    console.print("[cyan]Detecting hardware encoders...[/cyan]")
    console.print()

    detector = HardwareDetector()
    hardware_info = asyncio.run(detector.detect(test_encoding=True))

    # Display results
    table = Table(show_header=True)
    table.add_column("Hardware Type", style="cyan")
    table.add_column("Encoder", style="yellow")
    table.add_column("Status", style="green")

    for encoder in hardware_info.available_encoders:
        status = "✓ Available" if encoder.available else "✗ Not Available"
        table.add_row(
            encoder.hardware_type.value.upper(),
            encoder.name,
            status,
        )

    console.print(table)
    console.print()

    if hardware_info.selected_encoder:
        console.print(
            f"[green]✓ Recommended:[/green] {hardware_info.selected_encoder.hardware_type.value.upper()} "
            f"({hardware_info.selected_encoder.name})"
        )
    else:
        console.print("[yellow]⚠ No hardware acceleration available[/yellow]")
        console.print("[dim]Using software encoding (slower)[/dim]")

    console.print()


@app.command("profiles")
def profiles_command(
    action: str = typer.Argument(..., help="Action: list"),
) -> None:
    """
    Manage quality profiles.

    Actions:
    - list: List available quality profiles
    """
    if action == "list":
        config_manager = get_config_manager()
        config = config_manager.config

        console.print()
        console.print(Panel("[bold cyan]Quality Profiles[/bold cyan]", border_style="cyan"))
        console.print()

        for profile_name, variants in config.profiles.items():
            console.print(f"[bold]{profile_name}:[/bold]")
            for variant in variants:
                console.print(
                    f"  • {variant.quality}, " f"{variant.bitrate} bitrate, " f"CRF {variant.crf}"
                )
            console.print()

    else:
        console.print(f"[red]✗ Unknown action:[/red] {action}")
        console.print("Valid actions: list")
        sys.exit(1)


@app.command("version")
def version_command() -> None:
    """
    Display version information.
    """
    from .. import __version__

    console.print()
    console.print(
        Panel.fit(
            f"[bold cyan]HLS Video Transcoder[/bold cyan]\n"
            f"[dim]Version {__version__}[/dim]\n"
            f"[dim]Fast • Parallel • Hardware Accelerated[/dim]",
            border_style="cyan",
        )
    )
    console.print()


def main() -> None:
    """
    Main entry point for CLI.
    """
    app()


if __name__ == "__main__":
    main()
