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

# Custom 5-Slot Daily Timetable matching peak YouTube viewer behavior (3 English + 2 Hindi)
DAILY_SCHEDULE_SLOTS = [
    {"hour": 9, "niche": "mystery", "lang": "en", "voice": "christopher", "label": "09:00 AM - Mystery (English)"},
    {"hour": 12, "niche": "space", "lang": "en", "voice": "christopher", "label": "12:00 PM - Space (English)"},
    {"hour": 15, "niche": "science", "lang": "en", "voice": "christopher", "label": "03:00 PM - Science Facts (English)"},
    {"hour": 18, "niche": "history", "lang": "hi", "voice": "madhur", "label": "06:00 PM - History (Hindi - भारत का रहस्य)"},
    {"hour": 21, "niche": "psychology", "lang": "hi", "voice": "madhur", "label": "09:00 PM - Dark Psychology (Hindi - दिमाग के रहस्य)"},
]
DAILY_SCHEDULE_HOURS = [s["hour"] for s in DAILY_SCHEDULE_SLOTS]


class AutoPilot:
    """Orchestrates fully autonomous daily video generation and publishing."""

    def __init__(self, niche: str = "mixed", voice: Optional[str] = None, language: str = "mixed"):
        self.cfg = get_config()
        self.niche = niche
        self.language = language
        self.voice = voice
        self.trend_finder = TrendFinder()
        self.script_gen = ScriptGenerator()
        self.tts = TTSEngine(default_voice=self.voice or "christopher")
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
            f"• Niche Mode: [bold green]{'5-Slot Multi-Niche Daily Schedule' if self.niche in ('mixed', 'auto', 'daily', 'daily_slots') else self.niche.upper()}[/bold green]\n"
            f"• Language Distribution: [bold white]{'3 English + 2 Hindi' if self.language in ('mixed', 'auto', 'both') else self.language.upper()}[/bold white]\n"
            f"• Copyright Safety: [bold green]100% Commercial-Safe (Pexels CC0 / Original AI)[/bold green]\n"
            f"• Scheduled Publishing: [bold cyan]{'Yes (Staggered Peak Hours: 9AM, 12PM, 3PM, 6PM, 9PM)' if schedule else 'Immediate'}[/bold cyan]",
            title="AutoPilot Initialized",
        )

        is_multi_niche = self.niche in ("mixed", "auto", "daily", "daily_slots")
        is_mixed_lang = self.language in ("mixed", "auto", "both")

        # 1. Fetch trending non-repeating topics per slot
        topics_info = []
        if is_multi_niche:
            print_info(f"Discovering {count} fresh trending topics across 5 daily slots...")
            for idx in range(count):
                slot = DAILY_SCHEDULE_SLOTS[idx % len(DAILY_SCHEDULE_SLOTS)]
                topic_title = self.trend_finder.get_single_topic(niche=slot["niche"])
                item_lang = slot["lang"] if is_mixed_lang else self.language
                item_voice = self.voice or (slot["voice"] if is_mixed_lang else ("madhur" if item_lang in ("hi", "hindi") else "christopher"))
                topics_info.append({
                    "topic": topic_title,
                    "niche": slot["niche"],
                    "hour": slot["hour"],
                    "lang": item_lang,
                    "voice": item_voice,
                    "label": f"{slot['label']}",
                })
        else:
            print_info(f"Discovering {count} fresh trending topics in '{self.niche}'...")
            raw_topics = self.trend_finder.get_trending_topics(count=count, niche=self.niche)
            for idx, topic_title in enumerate(raw_topics):
                slot_hour = DAILY_SCHEDULE_HOURS[idx % len(DAILY_SCHEDULE_HOURS)]
                slot_fallback = DAILY_SCHEDULE_SLOTS[idx % len(DAILY_SCHEDULE_SLOTS)]
                item_lang = slot_fallback["lang"] if is_mixed_lang else self.language
                item_voice = self.voice or (slot_fallback["voice"] if is_mixed_lang else ("madhur" if item_lang in ("hi", "hindi") else "christopher"))
                topics_info.append({
                    "topic": topic_title,
                    "niche": self.niche,
                    "hour": slot_hour,
                    "lang": item_lang,
                    "voice": item_voice,
                    "label": f"{slot_hour:02d}:00 - {self.niche.capitalize()} ({'English' if item_lang == 'en' else 'Hindi'})",
                })

        uploaded_urls = []
        now = datetime.datetime.now(datetime.timezone.utc)
        ist = datetime.timezone(datetime.timedelta(hours=5, minutes=30))
        today = datetime.datetime.now(ist)

        for idx, item in enumerate(topics_info):
            topic = item["topic"]
            sched_hour = item["hour"]
            slot_label = item["label"]
            item_lang = item["lang"]
            item_voice = item["voice"]

            print_panel(
                f"[bold white]Processing Video {idx+1}/{count}:[/bold white] [bold yellow]{topic}[/bold yellow]\n"
                f"[bold cyan]Category & Slot:[/bold cyan] {slot_label}\n"
                f"[bold magenta]Language & Voice:[/bold magenta] {'English (' + item_voice + ')' if item_lang == 'en' else 'Hindi (' + item_voice + ')'}",
                border_style="magenta",
            )
            slug = sanitize_filename(topic)

            # Determine scheduled publish time in UTC ISO 8601
            publish_time_iso = None
            if schedule and upload:
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

            # Step A: Generate Script with 1-to-1 Matching Scenes
            script = self.script_gen.generate_short_script(
                topic, target_duration=45, language=item_lang
            )

            # Step B: Synthesize Voiceover & Extract Timings
            audio_path = self.cfg.paths.temp_dir / f"{slug}_voice.mp3"
            tts_res = self.tts.synthesize(
                text=script.narration,
                output_audio_path=audio_path,
                voice=item_voice,
            )

            # Calculate exact spoken duration for each scene!
            from autotube.voice.tts_engine import compute_scene_durations
            scene_durations = compute_scene_durations(
                scenes=script.scenes,
                words=tts_res.words,
                total_duration=tts_res.duration_seconds,
            )

            # Step C: Acquire Strictly Verified Visual Assets for Each Scene (1-to-1 Perfect Match!)
            print_info(f"Acquiring perfectly matching visual assets for {len(script.scenes) if script.scenes else 4} scenes...")
            if script.scenes:
                scene_assets = self.stock_fetcher.fetch_scene_visual_assets(
                    scenes=script.scenes,
                    output_dir=self.cfg.paths.temp_dir,
                    orientation="portrait",
                )
            else:
                queries = script.visual_keywords if script.visual_keywords else [topic]
                scene_assets = [
                    self.stock_fetcher.fetch_best_visual_for_scene(
                        subject=q,
                        output_dir=self.cfg.paths.temp_dir,
                        orientation="portrait",
                    )
                    for q in queries[:4]
                ]

            # Step D: Render Video & Subtitles with Exact Speech-to-Scene Alignment!
            output_short = self.cfg.paths.output_dir / "shorts" / f"{slug}.mp4"
            final_video = self.builder.build_short(
                audio_path=tts_res.audio_path,
                output_path=output_short,
                scene_assets=scene_assets,
                scene_durations=scene_durations,
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
            f"Daily Batch Complete! Generated {len(topics_info)} videos. Uploaded {len(uploaded_urls)} videos."
        )
        return uploaded_urls
