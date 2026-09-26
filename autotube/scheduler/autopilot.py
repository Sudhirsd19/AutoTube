"""AutoPilot Engine for hands-free daily batch video creation and scheduling."""

import datetime
from pathlib import Path
from typing import List, Optional
from autotube.config import get_config
from autotube.media.ai_visuals import VisualGenerator
from autotube.media.stock_fetcher import StockFetcher
from autotube.scripting.generator import ScriptGenerator
from autotube.scripting.trend_finder import TrendFinder
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
from autotube.utils.file_utils import sanitize_filename
from autotube.video.shorts_builder import ShortsBuilder
from autotube.voice.tts_engine import TTSEngine

# Optimal peak hours (IST / Local time) for 5 daily Shorts
DAILY_SCHEDULE_HOURS = [9, 12, 15, 18, 21]  # 9 AM, 12 PM, 3 PM, 6 PM, 9 PM


class AutoPilot:
    """Orchestrates fully autonomous daily video generation and publishing."""

    def __init__(self, niche: str = "space", voice: str = "christopher"):
        self.cfg = get_config()
        self.niche = niche
        self.voice = voice
        self.trend_finder = TrendFinder()
        self.script_gen = ScriptGenerator()
        self.tts = TTSEngine(default_voice=voice)
        self.stock_fetcher = StockFetcher()
        self.visual_gen = VisualGenerator()
        self.builder = ShortsBuilder()
        self.uploader = YouTubeUploader()

    def run_daily_batch(
        self,
        count: int = 5,
        upload: bool = True,
        schedule: bool = True,
    ) -> List[str]:
        """Generate and schedule a batch of viral videos for the day."""
        print_banner()
        print_panel(
            f"[bold cyan]AutoTube Autonomous AutoPilot Activated[/bold cyan]\n"
            f"• Target Daily Videos: [bold yellow]{count}[/bold yellow]\n"
            f"• Niche: [bold green]{self.niche.upper()}[/bold green]\n"
            f"• AI Voice: [bold white]{self.voice}[/bold white]\n"
            f"• Copyright Safety: [bold green]100% Commercial-Safe (Pexels CC0 / Original AI)[/bold green]\n"
            f"• Scheduled Publishing: [bold cyan]{'Yes (Staggered Peak Hours)' if schedule else 'Immediate'}[/bold cyan]",
            title="AutoPilot Initialized",
        )

        # 1. Fetch trending non-repeating topics
        print_info(f"Discovering {count} fresh trending topics in '{self.niche}'...")
        topics = self.trend_finder.get_trending_topics(count=count, niche=self.niche)

        uploaded_urls = []
        now = datetime.datetime.now(datetime.timezone.utc)
        ist = datetime.timezone(datetime.timedelta(hours=5, minutes=30))
        today = datetime.datetime.now(ist)

        for idx, topic in enumerate(topics):
            print_panel(
                f"[bold white]Processing Video {idx+1}/{count}:[/bold white] [bold yellow]{topic}[/bold yellow]",
                border_style="magenta",
            )
            slug = sanitize_filename(topic)

            # Determine scheduled publish time in UTC ISO 8601
            publish_time_iso = None
            if schedule and upload:
                sched_hour = DAILY_SCHEDULE_HOURS[idx % len(DAILY_SCHEDULE_HOURS)]
                sched_dt = datetime.datetime(
                    today.year,
                    today.month,
                    today.day,
                    sched_hour,
                    0,
                    0,
                    tzinfo=ist,
                )
                # If scheduled time already passed today, schedule for tomorrow
                if sched_dt.astimezone(datetime.timezone.utc) <= now:
                    sched_dt += datetime.timedelta(days=1)

                publish_time_iso = (
                    sched_dt.astimezone(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
                )
                print_info(
                    f"Scheduled Release Time: [bold yellow]{sched_hour:02d}:00 (Local Time)[/bold yellow] ({publish_time_iso} UTC)"
                )

            # Step A: Generate Script
            script = self.script_gen.generate_short_script(topic, target_duration=45)

            # Step B: Synthesize Voiceover & Timing
            audio_path = self.cfg.paths.temp_dir / f"{slug}_voice.mp3"
            tts_res = self.tts.synthesize(
                text=script.narration,
                output_audio_path=audio_path,
                voice=self.voice,
            )

            # Step C: Dynamic Multi-Scene Visual Footage (Cuts every 3-5 seconds!)
            queries = script.visual_keywords if script.visual_keywords else [topic]
            scene_videos = self.stock_fetcher.fetch_multi_scene_videos(
                queries=queries,
                output_dir=self.cfg.paths.temp_dir,
                target_count=4,
                orientation="portrait",
            )
            bg_video = None
            bg_image = None
            if not scene_videos:
                bg_video = self.stock_fetcher.search_and_download_video(
                    query=queries[0],
                    output_dir=self.cfg.paths.temp_dir,
                    orientation="portrait",
                )
                if not bg_video:
                    img_out = self.cfg.paths.temp_dir / f"{slug}_visual.jpg"
                    bg_image = self.visual_gen.generate_image(
                        prompt=f"{queries[0]}, hyper-detailed cinematic 8k",
                        output_path=img_out,
                        width=1080,
                        height=1920,
                    )

            # Step D: Render Video & Subtitles
            output_short = self.cfg.paths.output_dir / "shorts" / f"{slug}.mp4"
            final_video = self.builder.build_short(
                audio_path=tts_res.audio_path,
                output_path=output_short,
                background_video=bg_video,
                background_image=bg_image,
                scene_videos=scene_videos if len(scene_videos) > 1 else None,
                subtitles_file=tts_res.subtitles_ass_path,
            )

            # Step E: Upload & Schedule on YouTube
            if upload and final_video and final_video.exists():
                video_url = self.uploader.upload_video(
                    video_path=final_video,
                    title=f"{script.title} #Shorts",
                    description=(
                        f"{script.narration}\n\n"
                        f"Subscribe to the channel for daily mind-bending space & science facts!\n\n"
                        f"{' '.join(script.tags)}"
                    ),
                    tags=script.tags,
                    privacy_status="private" if publish_time_iso else "public",
                    publish_at=publish_time_iso,
                    pinned_comment=getattr(script, "pinned_comment", None),
                )
                if video_url:
                    uploaded_urls.append(video_url)
                    self.trend_finder.record_topic(topic, video_id=video_url.split("/")[-1])
            else:
                self.trend_finder.record_topic(topic)

        print_success(
            f"Daily Batch Complete! Generated {len(topics)} videos. Uploaded {len(uploaded_urls)} videos."
        )
        return uploaded_urls
