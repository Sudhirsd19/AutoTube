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
from autotube.media.veo_generator import VeoQuotaExceededError, VeoVideoGenerator
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
        table.add_row("Google Veo Video", "[green]Auto-Fallback[/green]", "Veo 3.1 with Smart Fallback Engine")
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
    duration: int = typer.Option(50, "--duration", "-d", help="Target duration in seconds (45-55s standard)"),
    lang: str = typer.Option("en", "--lang", "-l", help="Language: 'en' for English or 'hi' for Hindi"),
    visuals: str = typer.Option(
        "auto",
        "--visuals",
        help="Visuals mode: 'auto' (Veo AI Video with smart fallback), 'veo' (Pure AI Video), 'stock' (Pexels), or 'ai3d' (Pixar Animation)",
    ),
    upload: bool = typer.Option(False, "--upload", help="Automatically upload to YouTube after generation"),
    privacy: str = typer.Option("public", "--privacy", help="Privacy: private, unlisted, or public"),
):
    """Generate a high-retention 9:16 vertical YouTube Short with animated subtitles."""
    print_banner()
    cfg = get_config()
    slug = sanitize_filename(topic)
    total_steps = 5 if upload else 4

    if lang.lower() in ("hi", "hindi") and voice == "christopher":
        voice = "madhur"

    is_3d = visuals.lower() in ("ai3d", "3d", "pixar", "dltoons", "animation")
    is_auto_or_veo = visuals.lower() in ("auto", "veo")
    script_gen = ScriptGenerator()

    # 1. Script Generation
    if is_3d:
        print_step(1, total_steps, f"Generating 3D Pixar Story Script ({'Hindi' if lang.lower() in ('hi', 'hindi') else 'English'})")
        script = script_gen.generate_3d_animation_script(topic, target_duration=duration, language=lang)
    else:
        print_step(1, total_steps, f"Generating High-Retention AI Script ({'Hindi' if lang.lower() in ('hi', 'hindi') else 'English'})")
        script = script_gen.generate_short_script(topic, target_duration=duration, language=lang)

    print_panel(
        f"[bold yellow]Hook:[/bold yellow] {script.hook}\n\n"
        f"[bold white]Narration:[/bold white]\n{script.narration}\n\n"
        f"[bold cyan]Tags:[/bold cyan] {' '.join(script.tags)}",
        title=f"Generated Script: {script.title}",
    )

    # 2. Voiceover Synthesis
    print_step(2, total_steps, f"Synthesizing AI Voiceover ({voice}) & Word Timestamps")
    pitch_mod = "+14Hz" if voice.lower() in ("baby", "groot", "kid", "child") else "+0Hz"
    tts = TTSEngine(default_voice=voice, pitch=pitch_mod)
    audio_path = cfg.paths.temp_dir / f"{slug}_voice.mp3"
    tts_result = tts.synthesize(
        text=script.narration,
        output_audio_path=audio_path,
        voice=voice,
        pitch=pitch_mod,
    )

    from autotube.voice.tts_engine import compute_scene_durations
    scene_durations = compute_scene_durations(
        scenes=script.scenes,
        words=tts_result.words,
        total_duration=tts_result.duration_seconds,
    )

    # 3. Visuals Acquisition
    scene_visuals = None
    scene_videos = None
    scene_assets = None
    bg_video_path = None
    bg_image_path = None

    # --- Tier 1: Google AI Studio Veo Video Engine ---
    if is_auto_or_veo:
        print_step(3, total_steps, "Acquiring Visuals: Attempting Google AI Studio Video Generation (Veo Engine)")
        try:
            veo_gen = VeoVideoGenerator()
            if not veo_gen.is_available():
                raise VeoQuotaExceededError("No GEMINI_API_KEY found.")

            queries = script.visual_keywords if script.visual_keywords else [
                f"{topic}, cinematic close-up, dramatic lighting, 9:16 vertical",
                f"{topic}, dynamic motion scene, hyperrealistic, 9:16 vertical",
                f"{topic}, intense angle, cinematic 4k, 9:16 vertical",
                f"{topic}, breathtaking climax, ultra-detailed, 9:16 vertical",
            ]
            veo_scenes = veo_gen.generate_scenes(
                prompts=queries,
                output_dir=cfg.paths.temp_dir,
                slug=slug,
                aspect_ratio="9:16",
                max_scenes=5,
            )
            if veo_scenes and len(veo_scenes) >= 1:
                scene_videos = veo_scenes
                print_success(f"Generated {len(veo_scenes)} Veo AI video scenes successfully!")
        except (VeoQuotaExceededError, Exception) as veo_err:
            err_msg = getattr(veo_err, "message", str(veo_err))
            print_warning(f"⚠️ Google AI Studio (Veo) Quota Exceeded / Limit Reached ({err_msg})")
            print_info("🔄 Seamlessly switching to High-Fidelity Verified Visual Engine...")
            scene_videos = None

    # --- Tier 2: Fallback Engine (Strictly Verified Scene Assets or 3D AI Visuals) ---
    if not scene_videos:
        if is_3d:
            print_step(3, total_steps, "Generating 3D Pixar Animation Scene Visuals (Pollinations AI Engine)")
            visual_gen = VisualGenerator()
            queries = script.visual_keywords if script.visual_keywords else [
                f"{topic}, cute 3d character intro, pixar style",
                f"{topic}, cute 3d character emotional moment, pixar style",
                f"{topic}, dramatic 3d climax scene, pixar style",
                f"{topic}, happy 3d ending scene, pixar style",
            ]
            scene_visuals = visual_gen.fetch_scene_visuals(
                prompts=queries,
                output_dir=cfg.paths.temp_dir,
                slug=slug,
                width=1080,
                height=1920,
                style="ai3d",
                consistent_seed=True,
            )
        else:
            print_step(3, total_steps, "Acquiring Strictly Verified Scene Visuals (Perfect Subject Matching)")
            stock_fetcher = StockFetcher()
            if script.scenes:
                scene_assets = stock_fetcher.fetch_scene_visual_assets(
                    scenes=script.scenes,
                    output_dir=cfg.paths.temp_dir,
                    orientation="portrait",
                )
            else:
                queries = script.visual_keywords if script.visual_keywords else [topic]
                scene_assets = [
                    stock_fetcher.fetch_best_visual_for_scene(
                        subject=q,
                        output_dir=cfg.paths.temp_dir,
                        orientation="portrait",
                    )
                    for q in queries[:4]
                ]

    # 4. Vertical Video Compositing & Karaoke Subtitle Burning
    print_step(4, total_steps, "Rendering 9:16 Vertical Video & Burning Subtitles")
    builder = ShortsBuilder()
    output_short_path = cfg.paths.output_dir / "shorts" / f"{slug}.mp4"

    final_path = builder.build_short(
        audio_path=tts_result.audio_path,
        output_path=output_short_path,
        background_video=bg_video_path,
        background_image=bg_image_path,
        scene_visuals=scene_visuals if scene_visuals and len(scene_visuals) > 1 else None,
        scene_videos=scene_videos if scene_videos and len(scene_videos) > 1 else None,
        scene_assets=scene_assets,
        scene_durations=scene_durations,
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
    privacy: str = typer.Option("public", "--privacy", help="Privacy: private, unlisted, or public"),
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

    from autotube.voice.tts_engine import compute_scene_durations
    scene_durations = compute_scene_durations(
        scenes=script.scenes,
        words=tts_result.words,
        total_duration=tts_result.duration_seconds,
    )

    # 3. Visuals Generation for Each Scene
    print_step(3, total_steps, "Fetching Verified Scene Visuals (Relevance-Checked Stock & Fallback)")
    stock_fetcher = StockFetcher()
    scene_visuals = []

    for scene in script.scenes:
        asset = stock_fetcher.fetch_best_visual_for_scene(
            subject=scene.visual_query,
            keywords=[scene.visual_query],
            output_dir=cfg.paths.temp_dir,
            orientation="landscape",
        )
        scene_visuals.append(asset)

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
        scene_durations=scene_durations,
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
def stitch(
    folder: Path = typer.Option(..., "--folder", "-f", help="Folder containing AI generated video clips (.mp4)"),
    topic: str = typer.Option(..., "--topic", "-t", help="Topic for the story voiceover & subtitles"),
    voice: str = typer.Option("baby", "--voice", "-v", help="AI Voice (e.g. baby, guy, christopher, madhur)"),
    lang: str = typer.Option("en", "--lang", "-l", help="Language: 'en' for English or 'hi' for Hindi"),
    upload: bool = typer.Option(False, "--upload", help="Automatically upload to YouTube after stitching"),
    privacy: str = typer.Option("unlisted", "--privacy", help="Privacy: private, unlisted, or public"),
):
    """Stitch external AI video clips (from Google Colab / LTX / Kling), add voiceover, subtitles, and upload."""
    print_banner()
    cfg = get_config()
    slug = sanitize_filename(topic)
    total_steps = 4 if upload else 3

    if not folder.exists() or not folder.is_dir():
        print_error(f"Folder '{folder}' does not exist.")
        return

    clips = sorted([p for p in folder.iterdir() if p.suffix.lower() in (".mp4", ".mov", ".webm")])
    if not clips:
        print_error(f"No video files (.mp4) found in '{folder}'.")
        return

    print_info(f"Found {len(clips)} AI video clips in '{folder}'.")

    # 1. Script Generation
    print_step(1, total_steps, f"Generating matching script for {len(clips)} clips")
    script_gen = ScriptGenerator()
    script = script_gen.generate_short_script(topic, target_duration=len(clips) * 8, language=lang)

    # 2. Voiceover & Subtitles
    print_step(2, total_steps, f"Synthesizing voiceover ({voice}) & subtitles")
    pitch_mod = "+14Hz" if voice.lower() in ("baby", "groot", "kid", "child") else "+0Hz"
    tts = TTSEngine(default_voice=voice, pitch=pitch_mod)
    audio_path = cfg.paths.temp_dir / f"{slug}_stitch_voice.mp3"
    tts_result = tts.synthesize(
        text=script.narration,
        output_audio_path=audio_path,
        voice=voice,
        pitch=pitch_mod,
    )

    # Compute per-scene durations from TTS word timestamps for speech sync
    from autotube.voice.tts_engine import compute_scene_durations
    scene_durations = compute_scene_durations(
        scenes=script.scenes,
        words=tts_result.words,
        total_duration=tts_result.duration_seconds,
    )

    # 3. Stitch & Burn Subtitles
    print_step(3, total_steps, "Stitching video clips & burning animated subtitles")
    builder = ShortsBuilder()
    output_short_path = cfg.paths.output_dir / "shorts" / f"{slug}.mp4"

    final_path = builder.build_short(
        audio_path=tts_result.audio_path,
        output_path=output_short_path,
        scene_videos=clips,
        scene_durations=scene_durations,
        subtitles_file=tts_result.subtitles_ass_path,
    )

    if not final_path or not final_path.exists():
        print_error("Failed to stitch video.")
        return

    print_success(f"Final video successfully stitched: {final_path.resolve()}")

    # 4. Upload
    if upload:
        print_step(4, total_steps, "Uploading to YouTube")
        uploader = YouTubeUploader()
        uploader.upload_video(
            video_path=final_path,
            title=f"{script.title} #Shorts",
            description=f"{script.narration}\n\n{' '.join(script.tags)}",
            tags=script.tags,
            privacy_status=privacy,
        )


@app.command()
def cartoon(
    topic: str = typer.Option(..., "--topic", "-t", help="Topic or idea for the 3D animated short story"),
    style: str = typer.Option("pixar", "--style", "-s", help="Visual style: pixar, 3d, dltoons, anime, or comic"),
    voice: str = typer.Option("madhur", "--voice", "-v", help="AI Voice (e.g. madhur, swara, guy, andrew)"),
    lang: str = typer.Option("hi", "--lang", "-l", help="Language: 'hi' for Hindi or 'en' for English"),
    duration: int = typer.Option(45, "--duration", "-d", help="Target duration in seconds"),
    upload: bool = typer.Option(False, "--upload", help="Automatically upload to YouTube after generation"),
    privacy: str = typer.Option("private", "--privacy", help="Privacy: private, unlisted, or public"),
):
    """Generate a viral 3D Pixar/Disney/DL Toons style animated story short with voiceover & animated captions."""
    print_banner()
    cfg = get_config()
    slug = sanitize_filename(topic)
    total_steps = 5 if upload else 4

    if lang.lower() in ("hi", "hindi") and voice == "guy":
        voice = "madhur"

    # 1. Script Generation
    print_step(1, total_steps, f"Writing 3D Animated Story Script ({'Hindi' if lang.lower() in ('hi', 'hindi') else 'English'})")
    script_gen = ScriptGenerator()
    if lang.lower() in ("hi", "hindi") or style.lower() in ("pixar", "3d", "dltoons"):
        script = script_gen.generate_3d_animation_script(topic, target_duration=duration, language=lang)
    else:
        script = script_gen.generate_cartoon_script(topic, target_duration=duration)

    print_panel(
        f"[bold yellow]Hook:[/bold yellow] {script.hook}\n\n"
        f"[bold white]Narration:[/bold white]\n{script.narration}\n\n"
        f"[bold cyan]Tags:[/bold cyan] {' '.join(script.tags)}",
        title=f"3D Animation Script: {script.title}",
    )

    # 2. Voiceover Synthesis
    print_step(2, total_steps, f"Synthesizing Expressive AI Voice ({voice})")
    tts = TTSEngine(default_voice=voice, rate="+3%", pitch="+2Hz")
    audio_path = cfg.paths.temp_dir / f"{slug}_3d_voice.mp3"
    tts_result = tts.synthesize(
        text=script.narration,
        output_audio_path=audio_path,
        voice=voice,
    )

    # Compute per-scene durations from TTS word timestamps for speech sync
    from autotube.voice.tts_engine import compute_scene_durations
    scene_durations = compute_scene_durations(
        scenes=script.scenes,
        words=tts_result.words,
        total_duration=tts_result.duration_seconds,
    )

    # 3. Dynamic Multi-Scene 3D Cartoon AI Visuals
    print_step(3, total_steps, f"Generating Dynamic 3D [{style.upper()}] Story Scenes (Pollinations 3D Engine)")
    visual_gen = VisualGenerator()

    visual_queries = script.visual_keywords if script.visual_keywords and len(script.visual_keywords) >= 3 else [
        f"{topic}, cute 3d character intro, 3d pixar style",
        f"{topic}, cute character emotional challenge, 3d pixar style",
        f"{topic}, miraculous surprise action, 3d pixar style",
        f"{topic}, happy heartwarming ending, 3d pixar style",
    ]

    scene_visuals = visual_gen.fetch_scene_visuals(
        prompts=visual_queries[:6],
        output_dir=cfg.paths.temp_dir,
        slug=slug,
        width=1080,
        height=1920,
        style=style,
        consistent_seed=True,
    )

    # 4. Vertical Video Compositing & Karaoke Subtitle Burning
    print_step(4, total_steps, "Rendering 9:16 3D Animated Short & Burning Subtitles")
    builder = ShortsBuilder()
    output_short_path = cfg.paths.output_dir / "shorts" / f"{slug}_3d.mp4"

    final_path = builder.build_short(
        audio_path=tts_result.audio_path,
        output_path=output_short_path,
        scene_visuals=scene_visuals,
        scene_durations=scene_durations,
        subtitles_file=tts_result.subtitles_ass_path,
    )

    if not final_path or not final_path.exists():
        print_error("Failed to render 3D Short.")
        return

    print_success(f"3D Short successfully rendered: {final_path.resolve()}")

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
    niche: str = typer.Option("mixed", "--niche", "-n", help="Niche: mixed (all 5 daily slots), mystery, space, science, history, psychology, mythology"),
    voice: Optional[str] = typer.Option(None, "--voice", "-v", help="AI Voice narrator"),
    lang: str = typer.Option("mixed", "--lang", "-l", help="Language: 'mixed' (3 English + 2 Hindi), 'hi' (All Hindi), or 'en' (All English)"),
    upload: bool = typer.Option(True, "--upload/--no-upload", help="Upload to YouTube"),
    schedule: bool = typer.Option(True, "--schedule/--no-schedule", help="Stagger across peak hours (9 AM, 12 PM, 3 PM, 6 PM, 9 PM)"),
):
    """Fully automated batch creation and scheduled publishing for YouTube Shorts."""
    from autotube.scheduler.autopilot import AutoPilot

    pilot = AutoPilot(niche=niche, voice=voice, language=lang)
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


@app.command()
def cleanup(
    max_age: int = typer.Option(2, "--max-age", help="Delete temp files older than this many hours"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Show what would be deleted without actually deleting"),
):
    """Clean up temporary files to free disk space."""
    import time

    print_banner()
    cfg = get_config()
    temp_dir = cfg.paths.temp_dir
    if not temp_dir.exists():
        print_info("No temp directory found. Nothing to clean.")
        return

    cutoff = time.time() - (max_age * 3600)
    removed = 0
    freed_mb = 0.0
    total_files = 0
    total_mb = 0.0

    for f in temp_dir.iterdir():
        if f.is_file():
            size_mb = f.stat().st_size / (1024 * 1024)
            total_files += 1
            total_mb += size_mb
            if f.stat().st_mtime < cutoff:
                if dry_run:
                    print_info(f"  Would delete: {f.name} ({size_mb:.1f} MB)")
                else:
                    try:
                        f.unlink()
                        removed += 1
                        freed_mb += size_mb
                    except Exception as e:
                        print_warning(f"Could not delete {f.name}: {e}")

    if dry_run:
        print_info(f"Dry run: {total_files} files ({total_mb:.1f} MB total), would delete files older than {max_age}h.")
    elif removed > 0:
        print_success(f"Cleaned up {removed} temp files. Freed {freed_mb:.1f} MB of disk space.")
    else:
        print_info(f"No temp files older than {max_age}h found. ({total_files} files, {total_mb:.1f} MB total)")


if __name__ == "__main__":
    app()
