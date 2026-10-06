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


def get_viral_voice_for_slot(configured_voice: Optional[str], lang: str) -> str:
    """Ensure the #1 most used, viral voice is selected for YouTube Shorts & Documentaries.
    - Hindi: 'madhur' (hi-IN-MadhurNeural, authentic documentary storytelling tone)
    - English: 'christopher' (en-US-ChristopherNeural, deep blockbuster documentary tone)
    """
    is_hindi = str(lang).lower() in ("hi", "hindi")
    v = (configured_voice or "").strip().lower()
    if not v or v in ("auto", "default", "akashvani", "swara"):
        return "madhur" if is_hindi else "christopher"
    return configured_voice


# Master 12-Slot Daily Timetable: 10 Shorts (9:16 Vertical) + 2 Long Videos (16:9 Landscape Widescreen)
# - 10 Shorts spaced cleanly across the 24h cycle (5 Hindi + 5 English)
# - 2 Long Landscape Videos (1 Hindi at 08:00 PM IST Prime Time, 1 English at 06:30 PM EDT US Prime Time)
DAILY_SCHEDULE_SLOTS = [
    # Slot 1 (Short 1 - Hindi): 07:30 AM IST
    {
        "hour": 7,
        "minute": 30,
        "tz": "ist",
        "niche": "psychology",
        "lang": "hi",
        "voice": "hi_deep_cinematic_male",
        "format": "short",
        "label": "07:30 AM IST - Mind Glitch & Subconscious (Hindi Short)",
    },
    # Slot 2 (Short 2 - English): 09:30 AM IST (12:00 AM EDT)
    {
        "hour": 9,
        "minute": 30,
        "tz": "ist",
        "niche": "science",
        "lang": "en",
        "voice": "en_deep_cinematic_male",
        "format": "short",
        "label": "09:30 AM IST (12:00 AM EDT) - Quantum Science & Paradoxes (English Short)",
    },
    # Slot 3 (Short 3 - Hindi): 12:00 PM IST
    {
        "hour": 12,
        "minute": 0,
        "tz": "ist",
        "niche": "bharat_vigyan",
        "lang": "hi",
        "voice": "hi_deep_cinematic_male",
        "format": "short",
        "label": "12:00 PM IST - Bharat Ka Prachin Vigyan (Hindi Short)",
    },
    # Slot 4 (Short 4 - English): 02:30 PM IST (05:00 AM EDT)
    {
        "hour": 14,
        "minute": 30,
        "tz": "ist",
        "niche": "glitch_matrix",
        "lang": "en",
        "voice": "en_deep_cinematic_male",
        "format": "short",
        "label": "02:30 PM IST (05:00 AM EDT) - Simulation / Matrix Glitch (English Short)",
    },
    # Slot 5 (Short 5 - Hindi): 04:30 PM IST
    {
        "hour": 16,
        "minute": 30,
        "tz": "ist",
        "niche": "psychology",
        "lang": "hi",
        "voice": "hi_deep_cinematic_male",
        "format": "short",
        "label": "04:30 PM IST - Dark Psychology & Body Language (Hindi Short)",
    },
    # Slot 6 (Short 6 - English): 06:15 PM IST (08:45 AM EDT)
    {
        "hour": 18,
        "minute": 15,
        "tz": "ist",
        "niche": "mystery",
        "lang": "en",
        "voice": "en_deep_cinematic_male",
        "format": "short",
        "label": "06:15 PM IST (08:45 AM EDT) - Ocean & Deep Earth Terrors (English Short)",
    },
    # Slot 7 (LONG VIDEO 1 - Hindi): 08:00 PM IST (10:30 AM EDT) -> 16:9 Landscape
    {
        "hour": 20,
        "minute": 0,
        "tz": "ist",
        "niche": "bharat_vigyan",
        "lang": "hi",
        "voice": "hi_deep_cinematic_male",
        "format": "landscape_long",
        "label": "08:00 PM IST - प्राचीन भारत के अनसुलझे रहस्य व खोया विज्ञान [16:9 Landscape Documentary] (Hindi Long)",
    },
    # Slot 8 (Short 7 - Hindi): 09:45 PM IST
    {
        "hour": 21,
        "minute": 45,
        "tz": "ist",
        "niche": "history",
        "lang": "hi",
        "voice": "hi_deep_cinematic_male",
        "format": "short",
        "label": "09:45 PM IST - Rahasyamay Itihas & Khopiya Sach (Hindi Short)",
    },
    # Slot 9 (Short 8 - English): 11:30 PM IST (02:00 PM EDT)
    {
        "hour": 23,
        "minute": 30,
        "tz": "ist",
        "niche": "space",
        "lang": "en",
        "voice": "en_deep_cinematic_male",
        "format": "short",
        "label": "11:30 PM IST (02:00 PM EDT) - Cosmic Horror & Deep Space (English Short)",
    },
    # Slot 10 (Short 9 - English): 01:30 AM IST (04:00 PM EDT)
    {
        "hour": 1,
        "minute": 30,
        "tz": "ist",
        "niche": "science",
        "lang": "en",
        "voice": "en_deep_cinematic_male",
        "format": "short",
        "label": "01:30 AM IST (04:00 PM EDT) - AI & Future World Anomalies (English Short)",
    },
    # Slot 11 (LONG VIDEO 2 - English): 06:30 PM EDT (04:00 AM IST) -> 16:9 Landscape
    {
        "hour": 18,
        "minute": 30,
        "tz": "us",
        "niche": "mystery",
        "lang": "en",
        "voice": "en_deep_cinematic_male",
        "format": "landscape_long",
        "label": "06:30 PM EDT (04:00 AM IST) - Declassified Government Secrets & Cosmic Mysteries [16:9 Landscape Documentary] (English Long)",
    },
    # Slot 12 (Short 10 - English): 05:45 AM IST (08:15 PM EDT)
    {
        "hour": 5,
        "minute": 45,
        "tz": "ist",
        "niche": "mystery",
        "lang": "en",
        "voice": "en_deep_cinematic_male",
        "format": "short",
        "label": "05:45 AM IST (08:15 PM EDT) - Bizarre Unsolved Conspiracies (English Short)",
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

    def load_configured_slots(self, slot_id: Optional[str] = None) -> List[dict]:
        """Load slots from config/slots_config.json or fallback to DAILY_SCHEDULE_SLOTS."""
        slots = []
        cfg_path = Path("config/slots_config.json")
        if cfg_path.exists():
            try:
                import json
                with open(cfg_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    slots = data.get("slots", [])
            except Exception as e:
                print_warning(f"Could not load slots_config.json: {e}")

        if not slots:
            slots = DAILY_SCHEDULE_SLOTS

        if slot_id:
            matched = [s for s in slots if s.get("id") == slot_id]
            if matched:
                return matched

        return slots

    def run_daily_batch(
        self,
        count: Optional[int] = None,
        upload: bool = True,
        schedule: bool = True,
        slot_id: Optional[str] = None,
    ) -> List[str]:
        """Generate and schedule a batch of viral videos for the day (Dynamic slots supported)."""
        print_banner()

        active_slots = self.load_configured_slots(slot_id=slot_id)
        if slot_id and active_slots:
            count = 1
        elif count is None:
            count = len(active_slots)

        print_panel(
            f"[bold cyan]AutoTube Autonomous AutoPilot Activated[/bold cyan]\n"
            f"• Target Daily Videos: [bold yellow]{count}[/bold yellow]\n"
            f"• Slot Mode: [bold green]{f'Single Slot ({slot_id})' if slot_id else f'{len(active_slots)}-Slot Configured Matrix'}[/bold green]\n"
            f"• Niche Mode: [bold green]{'Multi-Niche Daily Schedule' if self.niche in ('mixed', 'auto', 'daily', 'daily_slots') else self.niche.upper()}[/bold green]\n"
            f"• Language Distribution: [bold white]{'English & Hindi Dynamic' if self.language in ('mixed', 'auto', 'both') else self.language.upper()}[/bold white]\n"
            f"• Copyright Safety: [bold green]100% Commercial-Safe (Pexels CC0 / Original AI)[/bold green]\n"
            f"• Scheduled Publishing: [bold cyan]{'Yes (USA Peak for English + India Peak for Hindi)' if schedule else 'Immediate'}[/bold cyan]",
            title="AutoPilot Initialized",
        )

        is_multi_niche = self.niche in ("mixed", "auto", "daily", "daily_slots")
        is_mixed_lang = self.language in ("mixed", "auto", "both")

        # 1. Fetch trending non-repeating topics per slot
        topics_info = []
        if is_multi_niche or slot_id:
            print_info(f"Discovering {count} fresh trending topics across configured slots...")
            for idx in range(count):
                slot_data = active_slots[idx % len(active_slots)]
                item_lang = slot_data.get("language") or slot_data.get("lang") if is_mixed_lang else self.language
                item_voice = self.voice or get_viral_voice_for_slot(slot_data.get("voice"), item_lang)
                item_tz = slot_data.get("tz", "us" if str(item_lang).lower() == "en" else "ist")
                item_format = slot_data.get("format", "short")
                topic_title = self.trend_finder.get_single_topic(
                    niche=slot_data.get("niche", "mystery"),
                    language=str(item_lang or "en"),
                )

                label_str = slot_data.get("label") or f"{slot_data.get('hour', 8):02d}:{slot_data.get('minute', 0):02d} ({item_tz.upper()}) - {slot_data.get('niche')} ({item_lang})"

                topics_info.append({
                    "id": slot_data.get("id", f"slot_{idx+1}"),
                    "topic": topic_title,
                    "niche": slot_data.get("niche", "mystery"),
                    "hour": slot_data.get("hour", 8),
                    "minute": slot_data.get("minute", 0),
                    "tz": item_tz,
                    "lang": item_lang,
                    "voice": item_voice,
                    "format": item_format,
                    "bgm": slot_data.get("bgm", "auto"),
                    "label": label_str,
                })
        else:
            print_info(f"Discovering {count} fresh trending topics in '{self.niche}'...")
            raw_topics = self.trend_finder.get_trending_topics(
                count=count, niche=self.niche, language=self.language
            )
            for idx, topic_title in enumerate(raw_topics):
                slot_data = active_slots[idx % len(active_slots)]
                item_lang = slot_data.get("language") or slot_data.get("lang") if is_mixed_lang else self.language
                item_voice = self.voice or get_viral_voice_for_slot(slot_data.get("voice"), item_lang)
                item_tz = slot_data.get("tz", "us" if str(item_lang).lower() == "en" else "ist")
                item_format = slot_data.get("format", "short")

                topics_info.append({
                    "id": slot_data.get("id", f"slot_{idx+1}"),
                    "topic": topic_title,
                    "niche": self.niche,
                    "hour": slot_data.get("hour", 8),
                    "minute": slot_data.get("minute", 0),
                    "tz": item_tz,
                    "lang": item_lang,
                    "voice": item_voice,
                    "format": item_format,
                    "bgm": slot_data.get("bgm", "auto"),
                    "label": f"{slot_data.get('hour', 8):02d}:{slot_data.get('minute', 0):02d} ({item_tz.upper()}) - {self.niche.capitalize()} ({'English' if str(item_lang).lower() == 'en' else 'Hindi'})",
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
            item_bgm = item.get("bgm", "auto")
            item_tz_key = item.get("tz", "us" if item_lang == "en" else "ist")

            print_panel(
                f"[bold white]Processing Video {idx+1}/{count}:[/bold white] [bold yellow]{topic}[/bold yellow]\n"
                f"[bold cyan]Category & Slot:[/bold cyan] {slot_label}\n"
                f"[bold magenta]Language & Voice:[/bold magenta] {'English (' + item_voice + ')' if item_lang == 'en' else 'Hindi (' + item_voice + ')'}\n"
                f"[bold green]BGM Music Track:[/bold green] {item_bgm.upper()}",
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

                item_fmt = item.get("format", "short")
                is_landscape = (item_fmt == "landscape_long")
                target_dur = 180 if is_landscape else 65
                orientation = "landscape" if is_landscape else "portrait"
                video_subfolder = "longform" if is_landscape else "shorts"
                v_w = 1920 if is_landscape else 1080
                v_h = 1080 if is_landscape else 1920

                # Step A: Generate Script with 1-to-1 Matching Scenes
                script = self.script_gen.generate_short_script(
                    topic, target_duration=target_dur, language=item_lang
                )

                # Step B: Synthesize Voiceover & Extract Timings
                audio_path = self.cfg.paths.temp_dir / f"{slug}_voice.mp3"
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

                # Step C: Vocal-Aligned Visual Acquisition (Veo / Verified Stock & AI Visuals)
                from autotube.media.visual_waterfall import acquire_scene_visuals_waterfall
                print_info(f"Acquiring visual scenes using Vocal-Aligned Engine ({orientation})...")
                scene_assets = acquire_scene_visuals_waterfall(
                    script=script,
                    output_dir=self.cfg.paths.temp_dir,
                    slug=slug,
                    orientation=orientation,
                    max_scenes=len(script.scenes) if (script.scenes and len(script.scenes) > 0) else 8,
                )

                # Step D: Render Video & Subtitles with Exact Speech-to-Scene Alignment!
                output_video_path = self.cfg.paths.output_dir / video_subfolder / f"{slug}.mp4"

                # Resolve BGM Music Track from Slot Config
                selected_music_path = None
                from autotube.media.background_music import BackgroundMusicManager
                bgm_mgr = BackgroundMusicManager()
                if item_bgm == "none":
                    selected_music_path = Path("none")
                elif item_bgm and item_bgm != "auto":
                    cat_tracks = bgm_mgr.get_music_tracks(category=item_bgm)
                    if cat_tracks:
                        import random
                        selected_music_path = random.choice(cat_tracks)
                        print_info(f"Selected slot BGM ({item_bgm}): {selected_music_path.name}")
                    else:
                        selected_music_path = bgm_mgr.get_music_for_subject(niche=item_niche, topic=topic)
                else:
                    selected_music_path = bgm_mgr.get_music_for_subject(niche=item_niche, topic=topic)

                final_video = self.builder.build_short(
                    audio_path=tts_res.audio_path,
                    output_path=output_video_path,
                    scene_assets=scene_assets,
                    scene_durations=scene_durations,
                    subtitles_file=tts_res.subtitles_ass_path,
                    music_path=selected_music_path,
                    width=v_w,
                    height=v_h,
                )

                # Step E: Upload & Schedule on YouTube
                if upload and final_video and final_video.exists():
                    v_title = f"{script.title} [Full Documentary]" if is_landscape else f"{script.title} #Shorts"
                    chapters = []
                    if is_landscape and script.scenes:
                        curr_sec = 0.0
                        for idx, sc in enumerate(script.scenes):
                            ch_name = getattr(sc, "visual_subject", f"Part {idx + 1}").strip().title()
                            if not ch_name or ch_name == f"Part {idx + 1}":
                                ch_name = f"Chapter {idx + 1}: {sc.narration[:30]}..."
                            chapters.append((curr_sec, ch_name))
                            if idx < len(scene_durations):
                                curr_sec += scene_durations[idx]
                            else:
                                curr_sec += 5.5

                    video_url = self.uploader.upload_video(
                        video_path=final_video,
                        title=v_title,
                        description=(
                            f"{script.narration}\n\n"
                            f"Subscribe to the channel for daily mind-bending space & science facts!\n\n"
                            f"{' '.join(script.tags)}"
                        ),
                        tags=script.tags,
                        privacy_status="private" if publish_time_iso else "public",
                        publish_at=publish_time_iso,
                        pinned_comment=getattr(script, "pinned_comment", None),
                        chapters=chapters if is_landscape else None,
                    )
                    if video_url:
                        uploaded_urls.append(video_url)
                        self.trend_finder.record_topic(topic, video_id=video_url.split("/")[-1])
                        print_success(f"Video uploaded & scheduled successfully: {video_url}")
                    else:
                        print_warning(
                            f"Upload could not be completed for '{topic}'. "
                            f"Rendered video is safely preserved at: {output_video_path.name}"
                        )
                else:
                    self.trend_finder.record_topic(topic)

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
