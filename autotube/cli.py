"""Main CLI interface for AutoTube using Typer and Rich."""

import os
from pathlib import Path
from typing import Optional
import typer
from rich.table import Table

from autotube.config import get_config
from autotube.media.ai_visuals import VisualGenerator
from autotube.media.background_music import BackgroundMusicManager
from autotube.media.stock_fetcher import StockFetcher
from autotube.scripting.generator import ScriptGenerator
from autotube.uploader.auth import YouTubeAuth
from autotube.uploader.youtube_upload import YouTubeUploader
from autotube.utils.console import (
    console,
    print_banner,
    print_error,
    print_info,
    print_panel,
    print_step,
    print_success,
    print_warning,
)
from autotube.utils.ffmpeg_helper import get_ffmpeg_path
from autotube.utils.file_utils import sanitize_filename
from autotube.video.longform_builder import LongformBuilder
from autotube.video.shorts_builder import ShortsBuilder
from autotube.video.thumbnail import ThumbnailGenerator
from autotube.voice.tts_engine import TTSEngine
from autotube.voice.voices import list_available_voices

app = typer.Typer(
    name="autotube",
    help="AutoTube: End-to-end AI YouTube Video Generator & Auto-Uploader",
    add_completion=False,
)


@app.callback(invoke_without_command=True)
def main(ctx: typer.Context):
    """AutoTube CLI Entrypoint."""
    if ctx.invoked_subcommand is None:
        print_banner()
        console.print(
            "Use [bold cyan]autotube --help[/bold cyan] to view available commands.\n"
        )


@app.command()
def init():
    """Verify environment setup, API keys, and test FFmpeg."""
    print_banner()
    cfg = get_config()
    cfg.paths.ensure_directories()

    table = Table(title="AutoTube System Status", show_header=True)
    table.add_column("Component", style="cyan", width=24)
    table.add_column("Status", width=16)
    table.add_column("Details", style="dim")

    # Check FFmpeg
    try:
        ffmpeg_exe = get_ffmpeg_path()
        table.add_row("FFmpeg Engine", "[green]Ready[/green]", ffmpeg_exe)
    except Exception as e:
        table.add_row("FFmpeg Engine", "[red]Missing[/red]", str(e))

    # Check Gemini API Key
    if cfg.gemini_api_key:
        table.add_row("Gemini AI API", "[green]Configured[/green]", "Active in .env")
    else:
        table.add_row(
            "Gemini AI API",
            "[yellow]Optional / Missing[/yellow]",
            "Add GEMINI_API_KEY in .env for custom AI generation",
        )

    # Check Pexels API Key
    if cfg.pexels_api_key:
        table.add_row("Pexels Stock API", "[green]Configured[/green]", "Active in .env")
    else:
        table.add_row(
            "Pexels Stock API",
            "[yellow]Optional[/yellow]",
            "Add PEXELS_API_KEY for automatic stock video downloading",
        )

    # Check YouTube Credentials
    if cfg.youtube.token_file.exists():
        table.add_row("YouTube Auth", "[green]Authenticated[/green]", "token.json ready")
    elif cfg.youtube.client_secrets_file.exists():
        table.add_row(
            "YouTube Auth",
            "[yellow]Client Secret Found[/yellow]",
            "Ready for OAuth login",
        )
    else:
        table.add_row(
            "YouTube Auth",
            "[dim]Not Configured[/dim]",
            "Place client_secrets.json in config/ for auto-upload",
        )

    console.print(table)
    print_success("AutoTube workspace initialized and verified!")


@app.command()
def voices():
    """List all available high-quality neural voices for voiceover."""
    print_banner()
    catalog = list_available_voices()
    table = Table(title="Available AI Voiceover Catalog", show_header=True)
    table.add_column("ID / Name", style="bold cyan")
    table.add_column("Language", style="magenta")
    table.add_column("Gender", style="yellow")
    table.add_column("Voice ID", style="dim")
    table.add_column("Description")

    for v in catalog:
        table.add_row(v.name.lower(), v.language, v.gender, v.id, v.description)

    console.print(table)


@app.command()
def shorts(
    topic: str = typer.Option(..., "--topic", "-t", help="Topic for the YouTube Short"),
    voice: str = typer.Option(
        "christopher", "--voice", "-v", help="AI Voice (e.g. christopher, guy, madhur, swara)"
    ),
    duration: int = typer.Option(45, "--duration", "-d", help="Target duration in seconds"),
    upload: bool = typer.Option(False, "--upload", help="Automatically upload to YouTube after generation"),
    privacy: str = typer.Option("private", "--privacy", help="Privacy: private, unlisted, or public"),
):
    """Generate a high-retention 9:16 vertical YouTube Short with animated subtitles."""
    print_banner()
    cfg = get_config()
    slug = sanitize_filename(topic)
    total_steps = 5 if upload else 4

    # 1. Script Generation
    print_step(1, total_steps, "Generating High-Retention AI Script")
    script_gen = ScriptGenerator()
    script = script_gen.generate_short_script(topic, target_duration=duration)
    print_panel(
        f"[bold yellow]Hook:[/bold yellow] {script.hook}\n\n"
        f"[bold white]Narration:[/bold white]\n{script.narration}\n\n"
        f"[bold cyan]Tags:[/bold cyan] {' '.join(script.tags)}",
        title=f"Generated Script: {script.title}",
    )

    # 2. Voiceover Synthesis
    print_step(2, total_steps, "Synthesizing AI Voiceover & Word Timestamps")
    tts = TTSEngine(default_voice=voice)
    audio_path = cfg.paths.temp_dir / f"{slug}_voice.mp3"
    tts_result = tts.synthesize(
        text=script.narration,
        output_audio_path=audio_path,
        voice=voice,
    )

    # 3. Visuals Selection (Dynamic Multi-Scene Fast B-Roll Cuts)
    print_step(3, total_steps, "Acquiring Multi-Scene Visual Footage (Fast Pacing Cuts)")
    stock_fetcher = StockFetcher()
    queries = script.visual_keywords if script.visual_keywords else [topic]
    scene_videos = stock_fetcher.fetch_multi_scene_videos(
        queries=queries,
        output_dir=cfg.paths.temp_dir,
        target_count=4,
        orientation="portrait",
    )

    bg_video_path = None
    bg_image_path = None
    if not scene_videos:
        # Fallback to single stock search
        bg_video_path = stock_fetcher.search_and_download_video(
            query=queries[0],
            output_dir=cfg.paths.temp_dir,
            orientation="portrait",
        )
        if not bg_video_path:
            visual_gen = VisualGenerator()
            image_out = cfg.paths.temp_dir / f"{slug}_visual.jpg"
            bg_image_path = visual_gen.generate_image(
                prompt=queries[0],
                output_path=image_out,
                width=1080,
                height=1920,
            )

    # 4. Vertical Video Compositing & Karaoke Subtitle Burning
    print_step(4, total_steps, "Rendering 9:16 Vertical Video & Burning Subtitles")
    builder = ShortsBuilder()
    output_short_path = cfg.paths.output_dir / "shorts" / f"{slug}.mp4"

    final_path = builder.build_short(
        audio_path=tts_result.audio_path,
        output_path=output_short_path,
        background_video=bg_video_path,
        background_image=bg_image_path,
        scene_videos=scene_videos if len(scene_videos) > 1 else None,
        subtitles_file=tts_result.subtitles_ass_path,
    )

    if not final_path or not final_path.exists():
        print_error("Failed to render Short.")
        return

    print_success(f"YouTube Short successfully rendered: {final_path.resolve()}")

    # 5. YouTube Upload
    if upload:
        print_step(5, total_steps, "Uploading Short to YouTube")
        uploader = YouTubeUploader()
        uploader.upload_video(
            video_path=final_path,
            title=f"{script.title} #Shorts",
            description=f"{script.narration}\n\n{' '.join(script.tags)}",
            tags=script.tags,
            privacy_status=privacy,
            pinned_comment=getattr(script, "pinned_comment", None),
        )


@app.command()
def video(
    topic: str = typer.Option(..., "--topic", "-t", help="Topic for the YouTube video"),
    scenes: int = typer.Option(5, "--scenes", "-s", help="Number of scenes in the documentary"),
    voice: str = typer.Option("christopher", "--voice", "-v", help="AI Voice narrator"),
    upload: bool = typer.Option(False, "--upload", help="Automatically upload to YouTube after generation"),
    privacy: str = typer.Option("private", "--privacy", help="Privacy: private, unlisted, or public"),
):
    """Generate a full 16:9 widescreen YouTube documentary video with multi-scenes and thumbnail."""
    print_banner()
    cfg = get_config()
    slug = sanitize_filename(topic)
    total_steps = 6 if upload else 5

    # 1. Script Generation
    print_step(1, total_steps, "Generating Multi-Scene Documentary Script")
    script_gen = ScriptGenerator()
    script = script_gen.generate_long_script(topic, num_scenes=scenes)
    print_panel(
        f"[bold white]Title:[/bold white] {script.title}\n"
        f"[bold cyan]Total Scenes:[/bold cyan] {len(script.scenes)}\n\n"
        + "\n".join(
            f"[yellow]Scene {s.scene_number}:[/yellow] {s.narration[:80]}..."
            for s in script.scenes
        ),
        title="Documentary Script",
    )

    # 2. Voiceover Synthesis
    print_step(2, total_steps, "Synthesizing Narration Voiceover")
    tts = TTSEngine(default_voice=voice)
    audio_path = cfg.paths.temp_dir / f"{slug}_long_voice.mp3"
    tts_result = tts.synthesize(
        text=script.full_narration,
        output_audio_path=audio_path,
        voice=voice,
    )

    # 3. Visuals Generation for Each Scene
    print_step(3, total_steps, "Fetching Scene Visuals (Stock Footage & AI Visuals)")
    visual_gen = VisualGenerator()
    stock_fetcher = StockFetcher()
    scene_visuals = []

    for scene in script.scenes:
        # Check stock video first
        vid = stock_fetcher.search_and_download_video(
            query=scene.visual_query,
            output_dir=cfg.paths.temp_dir,
            orientation="landscape",
        )
        if vid:
            scene_visuals.append(vid)
        else:
            # Generate AI image
            img_path = cfg.paths.temp_dir / f"{slug}_scene_{scene.scene_number:02d}.jpg"
            img = visual_gen.generate_image(
                prompt=f"{scene.visual_query}, cinematic documentary shot",
                output_path=img_path,
                width=1920,
                height=1080,
            )
            scene_visuals.append(img)

    # 4. Thumbnail Generation
    print_step(4, total_steps, "Generating High-CTR Custom Thumbnail")
    thumb_gen = ThumbnailGenerator()
    thumb_path = cfg.paths.output_dir / "videos" / f"{slug}_thumb.jpg"
    first_visual = scene_visuals[0] if scene_visuals else None
    thumb_gen.generate_thumbnail(
        title=script.title,
        output_path=thumb_path,
        background_image=first_visual,
    )

    # 5. Video Assembly & Audio Mixing
    print_step(5, total_steps, "Compositing 16:9 Video & Syncing Master Narration")
    builder = LongformBuilder()
    output_video_path = cfg.paths.output_dir / "videos" / f"{slug}.mp4"

    final_path = builder.build_video(
        audio_path=tts_result.audio_path,
        scene_visuals=scene_visuals,
        output_path=output_video_path,
        subtitles_file=tts_result.subtitles_srt_path,
    )

    if not final_path or not final_path.exists():
        print_error("Failed to render documentary video.")
        return

    print_success(f"YouTube Video successfully rendered: {final_path.resolve()}")
    print_success(f"Custom Thumbnail saved: {thumb_path.resolve()}")

    # 6. YouTube Upload
    if upload:
        print_step(6, total_steps, "Uploading Video & Thumbnail to YouTube")
        uploader = YouTubeUploader()
        uploader.upload_video(
            video_path=final_path,
            title=script.title,
            description=script.description,
            tags=script.tags,
            privacy_status=privacy,
            thumbnail_path=thumb_path,
        )


@app.command()
def upload(
    video_path: Path = typer.Argument(..., help="Path to the video file to upload"),
    title: str = typer.Option(..., "--title", "-t", help="Video Title"),
    description: str = typer.Option("", "--description", "--desc", "-d", help="Video Description"),
    tags: str = typer.Option("AutoTube,AI", "--tags", help="Comma-separated tags"),
    privacy: str = typer.Option("private", "--privacy", help="Privacy status (private, unlisted, public)"),
    thumbnail: Optional[Path] = typer.Option(None, "--thumbnail", help="Path to custom thumbnail image"),
    schedule: Optional[str] = typer.Option(None, "--schedule", help="Publish time in ISO 8601 (e.g. 2026-10-01T15:00:00Z)"),
):
    """Directly upload any video to YouTube using YouTube Data API v3."""
    print_banner()
    uploader = YouTubeUploader()
    tag_list = [t.strip() for t in tags.split(",") if t.strip()]

    uploader.upload_video(
        video_path=video_path,
        title=title,
        description=description,
        tags=tag_list,
        privacy_status=privacy,
        publish_at=schedule,
        thumbnail_path=thumbnail,
    )


@app.command()
def cartoon(
    topic: str = typer.Option(..., "--topic", "-t", help="Topic or idea for the cartoon short story"),
    style: str = typer.Option("pixar", "--style", "-s", help="Visual style: pixar, anime, or comic"),
    voice: str = typer.Option("guy", "--voice", "-v", help="AI Voice (e.g. guy, andrew, aria, swara)"),
    duration: int = typer.Option(45, "--duration", "-d", help="Target duration in seconds"),
    upload: bool = typer.Option(False, "--upload", help="Automatically upload to YouTube after generation"),
    privacy: str = typer.Option("private", "--privacy", help="Privacy: private, unlisted, or public"),
):
    """Generate a viral 3D Pixar/Disney style animated cartoon short with voiceover & animated captions."""
    print_banner()
    cfg = get_config()
    slug = sanitize_filename(topic)
    total_steps = 5 if upload else 4

    # 1. Script Generation
    print_step(1, total_steps, "Writing Fun 3D Cartoon Story Script")
    script_gen = ScriptGenerator()
    script = script_gen.generate_cartoon_script(topic, target_duration=duration)
    print_panel(
        f"[bold yellow]Hook:[/bold yellow] {script.hook}\n\n"
        f"[bold white]Narration:[/bold white]\n{script.narration}\n\n"
        f"[bold cyan]Tags:[/bold cyan] {' '.join(script.tags)}",
        title=f"Cartoon Script: {script.title}",
    )

    # 2. Voiceover Synthesis
    print_step(2, total_steps, f"Synthesizing Expressive Cartoon Voice ({voice})")
    tts = TTSEngine(default_voice=voice, rate="+6%", pitch="+4Hz")
    audio_path = cfg.paths.temp_dir / f"{slug}_cartoon_voice.mp3"
    tts_result = tts.synthesize(
        text=script.narration,
        output_audio_path=audio_path,
        voice=voice,
    )

    # 3. Dynamic Multi-Scene 3D Cartoon AI Visuals
    print_step(3, total_steps, f"Generating Dynamic 3D [{style.upper()}] Story Scenes")
    visual_gen = VisualGenerator()
    scene_visuals = []

    visual_queries = script.visual_keywords if script.visual_keywords and len(script.visual_keywords) >= 3 else [
        f"{topic}, cute character intro",
        f"{topic}, hilarious comedy challenge",
        f"{topic}, silly action sequence",
        f"{topic}, shocking funny surprise",
        f"{topic}, happy comical ending",
    ]

    for s_idx, v_query in enumerate(visual_queries[:6]):
        s_img_path = cfg.paths.temp_dir / f"{slug}_scene_{s_idx+1:02d}.jpg"
        img = visual_gen.generate_image(
            prompt=v_query,
            output_path=s_img_path,
            width=1080,
            height=1920,
            style=style,
        )
        scene_visuals.append(img)

    # 4. Vertical Video Compositing & Karaoke Subtitle Burning
    print_step(4, total_steps, "Rendering 9:16 Cartoon Short & Burning Comic Subtitles")
    builder = ShortsBuilder()
    output_short_path = cfg.paths.output_dir / "shorts" / f"{slug}_cartoon.mp4"

    final_path = builder.build_short(
        audio_path=tts_result.audio_path,
        output_path=output_short_path,
        scene_visuals=scene_visuals,
        subtitles_file=tts_result.subtitles_ass_path,
    )

    if not final_path or not final_path.exists():
        print_error("Failed to render Cartoon Short.")
        return

    print_success(f"Cartoon Short successfully rendered: {final_path.resolve()}")

    # 5. YouTube Upload
    if upload:
        print_step(5, total_steps, "Uploading Cartoon Short to YouTube")
        uploader = YouTubeUploader()
        uploader.upload_video(
            video_path=final_path,
            title=f"{script.title} #Shorts #Animation",
            description=f"{script.narration}\n\n{' '.join(script.tags)} #Cartoon #3DAnimation",
            tags=script.tags + ["cartoon", "animation", "pixar", "funny"],
            privacy_status=privacy,
        )


@app.command()
def autopilot(
    count: int = typer.Option(5, "--count", "-c", help="Number of videos to generate and schedule daily"),
    niche: str = typer.Option("space", "--niche", "-n", help="Niche: space, science, history, psychology, mystery"),
    voice: str = typer.Option("christopher", "--voice", "-v", help="AI Voice narrator"),
    upload: bool = typer.Option(True, "--upload/--no-upload", help="Upload to YouTube"),
    schedule: bool = typer.Option(True, "--schedule/--no-schedule", help="Stagger across peak hours (9 AM, 12 PM, 3 PM, 6 PM, 9 PM)"),
):
    """Fully automated batch creation and scheduled publishing for YouTube Shorts."""
    from autotube.scheduler.autopilot import AutoPilot

    pilot = AutoPilot(niche=niche, voice=voice)
    pilot.run_daily_batch(count=count, upload=upload, schedule=schedule)


@app.command()
def setup_task(
    hour: str = typer.Option("08:00", "--time", "-t", help="Time of day to run AutoTube (24hr format HH:MM e.g. 08:00)"),
):
    """Configure Windows Task Scheduler to run AutoTube automatically every morning."""
    import subprocess
    from autotube.config import PROJECT_ROOT

    bat_file = PROJECT_ROOT / "run_daily.bat"
    cmd = [
        "schtasks",
        "/create",
        "/tn",
        "AutoTubeDaily",
        "/tr",
        str(bat_file),
        "/sc",
        "daily",
        "/st",
        hour,
        "/f",
    ]

    print_info(f"Registering Windows Scheduled Task for daily run at {hour}...")
    try:
        res = subprocess.run(cmd, capture_output=True, text=True)
        if res.returncode == 0:
            print_success(f"Windows Task 'AutoTubeDaily' successfully registered! Will run daily at {hour}.")
        else:
            print_error(f"Could not register task: {res.stderr}")
    except Exception as e:
        print_error(f"Error registering task: {e}")



if __name__ == "__main__":
    app()
