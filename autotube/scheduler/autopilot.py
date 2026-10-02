"""AutoPilot Engine for hands-free daily batch video creation and scheduling."""

import datetime
import time
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

def get_timezone(tz_key: str) -> datetime.tzinfo:
    """Return timezone object for US Eastern (EDT/EST) or India (IST).
    Resilient across both Linux (system tzdata) and Windows (fallback offset).
    """
    key = str(tz_key).lower()
    if key in ("us", "usa", "edt", "est", "en", "america/new_york"):
        try:
            from zoneinfo import ZoneInfo
            return ZoneInfo("America/New_York")
        except Exception:
            month = datetime.datetime.now(datetime.timezone.utc).month
            offset_hours = -4 if 3 <= month <= 11 else -5
            return datetime.timezone(datetime.timedelta(hours=offset_hours))
    elif key in ("ist", "in", "india", "hi", "asia/kolkata"):
        try:
            from zoneinfo import ZoneInfo
            return ZoneInfo("Asia/Kolkata")
        except Exception:
            return datetime.timezone(datetime.timedelta(hours=5, minutes=30))
    return datetime.timezone.utc


# Custom 7-Slot Daily Timetable matching USA peak hours for English and India peak hours for Hindi:
# - English (USA Peak Hours):
#     11:00 AM EDT -> Space Mysteries (Lunch Peak)
#     02:00 PM EDT -> Science Facts & Paradoxes (Afternoon Peak)
#     06:30 PM EDT -> Alien Interview (English Series - Prime Time, Min 1 Min)
#     09:00 PM EDT -> Unsolved Ancient Mysteries (Late Evening Peak)
# - Hindi (India Peak Hours):
#     05:00 PM IST -> Bharat Ke Rahasya (Evening Tea Peak)
#     07:30 PM IST -> Alien Interview (Hindi Series - Prime Time, Min 1 Min)
#     09:30 PM IST -> Dark Psychology (Night Peak)
DAILY_SCHEDULE_SLOTS = [
    {
        "hour": 11,
        "minute": 0,
        "tz": "us",
        "niche": "space",
        "lang": "en",
        "voice": "adam",
        "label": "11:00 AM EDT (USA Lunch Peak) - Space Mysteries (English - Viral Narrator)",
    },
    {
        "hour": 14,
        "minute": 0,
        "tz": "us",
        "niche": "science",
        "lang": "en",
        "voice": "adam",
        "label": "02:00 PM EDT (USA Afternoon Peak) - Science Facts & Paradoxes (English - Viral Narrator)",
    },
    {
        "hour": 18,
        "minute": 30,
        "tz": "us",
        "niche": "alien",
        "lang": "en",
        "voice": "adam",
        "label": "06:30 PM EDT (USA Prime Time) - Alien Interview English (Min 1 Minute)",
    },
    {
        "hour": 21,
        "minute": 0,
        "tz": "us",
        "niche": "mystery",
        "lang": "en",
        "voice": "adam",
        "label": "09:00 PM EDT (USA Evening Peak) - Unsolved Ancient Mysteries (English - Viral Narrator)",
    },
    {
        "hour": 17,
        "minute": 0,
        "tz": "ist",
        "niche": "history",
        "lang": "hi",
        "voice": "madhur",
        "label": "05:00 PM IST (India Evening Peak) - Bharat Ke Rahasya (Hindi - Viral Narrator)",
    },
    {
        "hour": 19,
        "minute": 30,
        "tz": "ist",
        "niche": "alien",
        "lang": "hi",
        "voice": "madhur",
        "label": "07:30 PM IST (India Prime Time) - Alien Interview Hindi (Min 1 Minute)",
    },
    {
        "hour": 21,
        "minute": 30,
        "tz": "ist",
        "niche": "psychology",
        "lang": "hi",
        "voice": "madhur",
        "label": "09:30 PM IST (India Night Peak) - Dark Psychology (Hindi - Viral Narrator)",
    },
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
        count: int = 7,
        upload: bool = True,
        schedule: bool = True,
    ) -> List[str]:
        """Generate and schedule a batch of viral videos for the day (7 slots per day)."""
        print_banner()
        print_panel(
            f"[bold cyan]AutoTube Autonomous AutoPilot Activated[/bold cyan]\n"
            f"• Target Daily Videos: [bold yellow]{count}[/bold yellow]\n"
            f"• Niche Mode: [bold green]{'7-Slot Multi-Niche Daily Schedule' if self.niche in ('mixed', 'auto', 'daily', 'daily_slots') else self.niche.upper()}[/bold green]\n"
            f"• Language Distribution: [bold white]{'4 English + 3 Hindi' if self.language in ('mixed', 'auto', 'both') else self.language.upper()}[/bold white]\n"
            f"• Copyright Safety: [bold green]100% Commercial-Safe (Pexels CC0 / Original AI)[/bold green]\n"
            f"• Scheduled Publishing: [bold cyan]{'Yes (USA Peak for English + India Peak for Hindi)' if schedule else 'Immediate'}[/bold cyan]",
            title="AutoPilot Initialized",
        )

        is_multi_niche = self.niche in ("mixed", "auto", "daily", "daily_slots")
        is_mixed_lang = self.language in ("mixed", "auto", "both")

        # 1. Fetch trending non-repeating topics per slot
        topics_info = []
        if is_multi_niche:
            print_info(f"Discovering {count} fresh trending topics across 7 daily slots...")
            from autotube.scripting.alien_tracker import AlienSeriesTracker
            alien_tracker = AlienSeriesTracker()
            current_alien_chapter = alien_tracker.get_current_chapter()

            for idx in range(count):
                slot = DAILY_SCHEDULE_SLOTS[idx % len(DAILY_SCHEDULE_SLOTS)]
                item_lang = slot["lang"] if is_mixed_lang else self.language
                item_voice = self.voice or (slot["voice"] if is_mixed_lang else ("madhur" if item_lang in ("hi", "hindi") else "christopher"))
                item_tz = slot.get("tz", "us" if item_lang == "en" else "ist")

                if slot["niche"] == "alien":
                    topic_title = current_alien_chapter["title_hi"] if item_lang in ("hi", "hindi") else current_alien_chapter["title_en"]
                    alien_part = current_alien_chapter["part_number"]
                else:
                    topic_title = self.trend_finder.get_single_topic(niche=slot["niche"])
                    alien_part = None

                topics_info.append({
                    "topic": topic_title,
                    "niche": slot["niche"],
                    "hour": slot["hour"],
                    "minute": slot.get("minute", 0),
                    "tz": item_tz,
                    "lang": item_lang,
                    "voice": item_voice,
                    "label": f"{slot['label']}",
                    "alien_part": alien_part,
                })
        else:
            print_info(f"Discovering {count} fresh trending topics in '{self.niche}'...")
            raw_topics = self.trend_finder.get_trending_topics(count=count, niche=self.niche)
            for idx, topic_title in enumerate(raw_topics):
                slot_fallback = DAILY_SCHEDULE_SLOTS[idx % len(DAILY_SCHEDULE_SLOTS)]
                item_lang = slot_fallback["lang"] if is_mixed_lang else self.language
                item_voice = self.voice or (slot_fallback["voice"] if is_mixed_lang else ("madhur" if item_lang in ("hi", "hindi") else "christopher"))
                item_tz = slot_fallback.get("tz", "us" if item_lang == "en" else "ist")
                topics_info.append({
                    "topic": topic_title,
                    "niche": self.niche,
                    "hour": slot_fallback["hour"],
                    "minute": slot_fallback.get("minute", 0),
                    "tz": item_tz,
                    "lang": item_lang,
                    "voice": item_voice,
                    "label": f"{slot_fallback['hour']:02d}:{slot_fallback.get('minute', 0):02d} ({item_tz.upper()}) - {self.niche.capitalize()} ({'English' if item_lang == 'en' else 'Hindi'})",
                    "alien_part": None,
                })

        uploaded_urls = []
        failed_count = 0
        now = datetime.datetime.now(datetime.timezone.utc)

        for idx, item in enumerate(topics_info):
            topic = item["topic"]
            sched_hour = item["hour"]
            sched_minute = item.get("minute", 0)
            slot_label = item["label"]
            item_lang = item["lang"]
            item_voice = item["voice"]
            item_niche = item["niche"]
            item_tz_key = item.get("tz", "us" if item_lang == "en" else "ist")

            print_panel(
                f"[bold white]Processing Video {idx+1}/{count}:[/bold white] [bold yellow]{topic}[/bold yellow]\n"
                f"[bold cyan]Category & Slot:[/bold cyan] {slot_label}\n"
                f"[bold magenta]Language & Voice:[/bold magenta] {'English (' + item_voice + ')' if item_lang == 'en' else 'Hindi (' + item_voice + ')'}",
                border_style="magenta",
            )

            try:
                slug = sanitize_filename(topic)

                # Determine scheduled publish time in UTC ISO 8601 using local peak timezone
                publish_time_iso = None
                if schedule and upload:
                    slot_tz = get_timezone(item_tz_key)
                    local_now = datetime.datetime.now(slot_tz)
                    sched_dt = datetime.datetime(
                        local_now.year,
                        local_now.month,
                        local_now.day,
                        sched_hour,
                        sched_minute,
                        0,
                        tzinfo=slot_tz,
                    )
                    # If scheduled time already passed today in the target timezone, schedule for tomorrow
                    if sched_dt.astimezone(datetime.timezone.utc) <= now:
                        sched_dt += datetime.timedelta(days=1)

                    publish_time_iso = (
                        sched_dt.astimezone(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
                    )
                    tz_display = "USA EDT/EST" if item_tz_key in ("us", "usa", "edt", "est", "en") else "India IST"
                    print_info(
                        f"Scheduled Release Time: [bold yellow]{sched_hour:02d}:{sched_minute:02d} {tz_display}[/bold yellow] ({publish_time_iso} UTC)"
                    )

                # Step A: Generate Script with 1-to-1 Matching Scenes
                if item_niche == "alien":
                    script = self.script_gen.generate_alien_script(
                        part=item.get("alien_part"),
                        language=item_lang,
                        target_duration=65,  # Mandatory >= 60 seconds (1 minute minimum)
                    )
                else:
                    script = self.script_gen.generate_short_script(
                        topic, target_duration=45, language=item_lang
                    )

                # Step B: Synthesize Voiceover & Extract Timings
                audio_path = self.cfg.paths.temp_dir / f"{slug}_voice.mp3"
                if item_niche == "alien":
                    print_info(f"Synthesizing Real Dialogue (Nurse Matilda + Alien Airl)...")
                    tts_res = self.tts.synthesize_dialogue(
                        scenes=script.scenes,
                        output_audio_path=audio_path,
                        language=item_lang,
                    )
                    if tts_res.scene_durations and len(tts_res.scene_durations) == len(script.scenes):
                        scene_durations = tts_res.scene_durations
                    else:
                        from autotube.voice.tts_engine import compute_scene_durations
                        scene_durations = compute_scene_durations(
                            scenes=script.scenes,
                            words=tts_res.words,
                            total_duration=tts_res.duration_seconds,
                        )
                else:
                    tts_res = self.tts.synthesize(
                        text=script.narration,
                        output_audio_path=audio_path,
                        voice=item_voice,
                    )
                    from autotube.voice.tts_engine import compute_scene_durations
                    scene_durations = compute_scene_durations(
                        scenes=script.scenes,
                        words=tts_res.words,
                        total_duration=tts_res.duration_seconds,
                    )

                # Step C: 3-Tier Visual Waterfall (Hugging Face -> 8 AM Gemini cutoff -> Verified Stock/AI)
                from autotube.media.visual_waterfall import acquire_scene_visuals_waterfall
                print_info(f"Acquiring visual scenes using 3-Tier Waterfall (HF -> Gemini -> Verified Stock)...")
                scene_assets = acquire_scene_visuals_waterfall(
                    script=script,
                    output_dir=self.cfg.paths.temp_dir,
                    slug=slug,
                    orientation="portrait",
                    max_scenes=len(script.scenes) if (script.scenes and len(script.scenes) > 0) else 8,
                    max_hf_retries=2,
                    cutoff_hour=8,
                )

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

                # Record Alien Interview series completion atomically (Zero-Skip Guarantee)
                if item_niche == "alien" and item.get("alien_part"):
                    from autotube.scripting.alien_tracker import AlienSeriesTracker
                    vid_id = video_url.split("/")[-1] if (upload and video_url) else "rendered"
                    AlienSeriesTracker().mark_part_completed(
                        part=item["alien_part"],
                        lang=item_lang,
                        video_id=vid_id,
                    )

            except Exception as e:
                failed_count += 1
                print_error(f"Failed to generate video {idx+1}/{count} ('{topic}'): {e}")
                print_warning("Continuing with next video in the batch...")
                self.trend_finder.record_topic(topic)
                continue

        # Cleanup stale temp files to prevent disk space bloat
        self._cleanup_temp()

        print_success(
            f"Daily Batch Complete! Generated {len(topics_info)} videos. "
            f"Uploaded {len(uploaded_urls)}. Failed {failed_count}."
        )
        return uploaded_urls

    def _cleanup_temp(self, max_age_hours: int = 2):
        """Remove temp files older than max_age_hours to prevent disk bloat."""
        temp_dir = self.cfg.paths.temp_dir
        if not temp_dir.exists():
            return
        cutoff = time.time() - (max_age_hours * 3600)
        removed = 0
        freed_mb = 0.0
        for f in temp_dir.iterdir():
            if f.is_file() and f.stat().st_mtime < cutoff:
                try:
                    freed_mb += f.stat().st_size / (1024 * 1024)
                    f.unlink()
                    removed += 1
                except Exception:
                    pass
        if removed > 0:
            print_info(f"Cleaned up {removed} stale temp files ({freed_mb:.1f} MB freed).")
