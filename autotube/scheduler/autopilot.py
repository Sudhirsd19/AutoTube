"""AutoPilot Engine for hands-free daily batch video creation and scheduling."""

import datetime
import json
import time
from pathlib import Path
from typing import List, Optional
from autotube.config import get_config, PROJECT_ROOT

PAIRED_TOPICS_FILE = PROJECT_ROOT / "config" / "daily_paired_topics.json"


def _load_paired_topics() -> dict:
    try:
        if PAIRED_TOPICS_FILE.exists():
            with open(PAIRED_TOPICS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                today_str = datetime.date.today().isoformat()
                return data.get(today_str, {})
    except Exception:
        pass
    return {}


def _save_paired_topic(slot_id: str, topic: str):
    try:
        data = {}
        today_str = datetime.date.today().isoformat()
        if PAIRED_TOPICS_FILE.exists():
            with open(PAIRED_TOPICS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
        cutoff = (datetime.date.today() - datetime.timedelta(days=7)).isoformat()
        data = {k: v for k, v in data.items() if k >= cutoff}
        day_dict = data.setdefault(today_str, {})
        day_dict[slot_id] = topic
        PAIRED_TOPICS_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(PAIRED_TOPICS_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    except Exception:
        pass
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
from autotube.voice.voice_director import resolve_voice_for_content

try:
    from zoneinfo import ZoneInfo
except ImportError:
    ZoneInfo = None


def get_timezone(tz_key: str) -> datetime.tzinfo:
    """Return timezone object for US Eastern (EDT/EST) or India (IST).
    Resilient across both Linux (system tzdata) and Windows (fallback offset).
    """
    key = str(tz_key).lower()
    if key in ("us", "usa", "edt", "est", "en", "america/new_york"):
        if ZoneInfo is not None:
            try:
                return ZoneInfo("America/New_York")
            except Exception:
                pass
        month = datetime.datetime.now(datetime.timezone.utc).month
        offset_hours = -4 if 3 <= month <= 11 else -5
        return datetime.timezone(datetime.timedelta(hours=offset_hours))
    elif key in ("ist", "in", "india", "hi", "asia/kolkata"):
        if ZoneInfo is not None:
            try:
                return ZoneInfo("Asia/Kolkata")
            except Exception:
                pass
        return datetime.timezone(datetime.timedelta(hours=5, minutes=30))
    return datetime.timezone.utc


def get_viral_voice_for_slot(configured_voice: Optional[str], lang: str) -> str:
    """Return the configured voice, defaulting to OpenMontage Gemini TTS (Charon)."""
    v = (configured_voice or "").strip().lower()
    if not v or v in ("auto", "default"):
        return "Charon"
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
        "voice": "auto",
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
        "voice": "auto",
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
        "voice": "auto",
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
        "voice": "auto",
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
        "voice": "auto",
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
        "voice": "auto",
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
        "voice": "auto",
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
        "voice": "auto",
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
        "voice": "auto",
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
        "voice": "auto",
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
        "voice": "auto",
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
        "voice": "auto",
        "format": "short",
        "label": "05:45 AM IST (08:15 PM EDT) - Bizarre Unsolved Conspiracies (English Short)",
    },
]
DAILY_SCHEDULE_HOURS = [s["hour"] for s in DAILY_SCHEDULE_SLOTS]


class AutoPilot:
    """Orchestrates fully autonomous daily video generation and publishing."""

    def __init__(self, niche: str = "mixed", voice: Optional[str] = None, language: str = "mixed", engine: str = "openmontage"):
        self.cfg = get_config()
        self.niche = niche
        self.language = language
        self.voice = voice
        self.engine = "openmontage" if str(engine or "").strip().lower() in ("openmontage", "remotion", "auto", "default", "") else str(engine).strip().lower()
        self.trend_finder = TrendFinder()
        self.script_gen = ScriptGenerator()
        self.tts = TTSEngine(default_voice=self.voice or "Charon")
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

        pid_file = Path("autopilot.pid")
        if pid_file.exists():
            try:
                old_pid = int(pid_file.read_text(encoding="utf-8").strip())
                import psutil
                if psutil.pid_exists(old_pid):
                    proc = psutil.Process(old_pid)
                    age = time.time() - proc.create_time()
                    if age > 7200:
                        print_warning(f"⚠️ Terminating hung AutoPilot process (PID {old_pid}, age: {age/3600:.1f}h)...")
                        proc.kill()
                        time.sleep(1)
                    else:
                        print_warning(f"⚠️ Another AutoPilot instance (PID {old_pid}) is already active. Skipping duplicate run.")
                        return []
            except Exception:
                pass
        try:
            pid_file.write_text(str(os.getpid()), encoding="utf-8")
        except Exception:
            pass

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

        is_multi_niche = self.niche in ("mixed", "auto", "daily", "daily_slots", "daily_mirror", "day_wise")
        is_mixed_lang = self.language in ("mixed", "auto", "both")

        # 1. Fetch trending non-repeating topics per slot (with mirror pair support)
        topics_info = []
        generated_topics_by_id = _load_paired_topics()
        if is_multi_niche or slot_id:
            print_info(f"Discovering {count} fresh trending topics across configured slots...")
            for idx in range(count):
                slot_data = active_slots[idx % len(active_slots)]
                curr_slot_id = slot_data.get("id", f"slot_{idx+1}")
                pair_target = slot_data.get("pair_with")

                raw_slot_niche = slot_data.get("niche", "mystery")
                if self.niche not in ("mixed", "auto", "daily", "daily_slots", "daily_mirror", "day_wise"):
                    raw_slot_niche = self.niche

                canon_niche, niche_desc = self.trend_finder.resolve_niche(raw_slot_niche)

                item_lang = (slot_data.get("language") or slot_data.get("lang")) if is_mixed_lang else self.language
                item_voice = self.voice or get_viral_voice_for_slot(slot_data.get("voice"), item_lang)
                item_tz = slot_data.get("tz", "us" if str(item_lang).lower().startswith("en") else "ist")
                item_format = slot_data.get("format", "short")

                slot_bgm = slot_data.get("bgm", "auto")
                if slot_bgm == "auto":
                    if canon_niche in ("space", "ocean", "quantum_matrix", "science"):
                        slot_bgm = "space"
                    elif canon_niche in ("ancient_engineering", "bharat_vigyan", "history", "conspiracy"):
                        slot_bgm = "history"

                # Check if this slot mirrors a previous slot
                if pair_target and pair_target in generated_topics_by_id:
                    topic_title = generated_topics_by_id[pair_target]
                    print_info(f"Mirror Slot [{curr_slot_id}] paired with [{pair_target}]: Reusing topic '{topic_title}' ({item_lang})")
                else:
                    topic_title = self.trend_finder.get_single_topic(
                        niche=canon_niche,
                        language=str(item_lang or "en"),
                    )
                generated_topics_by_id[curr_slot_id] = topic_title
                _save_paired_topic(curr_slot_id, topic_title)

                label_str = slot_data.get("label") or f"{slot_data.get('hour', 8):02d}:{slot_data.get('minute', 0):02d} ({item_tz.upper()}) - {canon_niche} ({item_lang})"

                topics_info.append({
                    "id": curr_slot_id,
                    "topic": topic_title,
                    "niche": canon_niche,
                    "channel": slot_data.get("channel") or ("hindi" if str(item_lang).lower().startswith("hi") else "english"),
                    "hour": slot_data.get("hour", 8),
                    "minute": slot_data.get("minute", 0),
                    "tz": item_tz,
                    "lang": item_lang,
                    "voice": item_voice,
                    "format": item_format,
                    "bgm": slot_bgm,
                    "label": label_str,
                })
        else:
            print_info(f"Discovering {count} fresh trending topics in '{self.niche}'...")
            raw_topics = self.trend_finder.get_trending_topics(
                count=count, niche=self.niche, language=self.language
            )
            for idx, topic_title in enumerate(raw_topics):
                slot_data = active_slots[idx % len(active_slots)]
                item_lang = (slot_data.get("language") or slot_data.get("lang")) if is_mixed_lang else self.language
                item_voice = self.voice or get_viral_voice_for_slot(slot_data.get("voice"), item_lang)
                item_tz = slot_data.get("tz", "us" if str(item_lang).lower() == "en" else "ist")
                item_format = slot_data.get("format", "short")

                topics_info.append({
                    "id": slot_data.get("id", f"slot_{idx+1}"),
                    "topic": topic_title,
                    "niche": self.niche,
                    "channel": slot_data.get("channel") or ("hindi" if str(item_lang).lower().startswith("hi") else "english"),
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
            item_channel = item.get("channel") or ("hindi" if str(item_lang).lower().startswith("hi") else "english")
            item_tz_key = item.get("tz", "us" if str(item_lang).lower().startswith("en") else "ist")

            print_panel(
                f"[bold white]Processing Video {idx+1}/{count}:[/bold white] [bold yellow]{topic}[/bold yellow]\n"
                f"[bold cyan]Category & Slot:[/bold cyan] {slot_label}\n"
                f"[bold blue]Target Channel:[/bold blue] {'🇬🇧 English Shorts' if item_channel == 'english' else '🇮🇳 Hindi Shorts'}\n"
                f"[bold magenta]Language & Voice:[/bold magenta] {'English (' + item_voice + ')' if str(item_lang).lower().startswith('en') else 'Hindi (' + item_voice + ')'}\n"
                f"[bold green]BGM Music Track:[/bold green] {item_bgm.upper()}",
                border_style="magenta",
            )

            try:
                lang_code = "hi" if (str(item_lang).lower().startswith("hi") or item_channel == "hindi") else "en"
                slug = f"{sanitize_filename(topic)}_{lang_code}" 

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
                # Read configured duration from slot or global config or settings.yaml (defaults to 25s viral sweet spot)
                configured_dur = (
                    item.get("duration")
                    or item.get("target_duration")
                    or getattr(self.cfg.video.shorts, "default_duration", None)
                    or 25
                )
                target_dur = 180 if is_landscape else int(configured_dur)
                orientation = "landscape" if is_landscape else "portrait"
                video_subfolder = "longform" if is_landscape else "shorts"
                v_w = 1920 if is_landscape else 1080
                v_h = 1080 if is_landscape else 1920

                # Step A: Generate Script with 1-to-1 Matching Scenes
                script = self.script_gen.generate_short_script(
                    topic, target_duration=target_dur, language=item_lang
                )

                # Step B: Resolve the narrator from the complete generated narration.
                # Topic-only selection is intentionally avoided so the exact script determines
                # the subject category (space/history/science/mystery/etc.).
                item_voice = resolve_voice_for_content(
                    configured_voice=item_voice,
                    title=script.title or topic,
                    script_text=script.narration,
                    language=item_lang,
                )
                item["voice"] = item_voice
                print_info(
                    f"🎙️ Voice Director: {item_voice} "
                    f"(language={item_lang}, subject matched from generated narration)"
                )

                # Step C: Setup Output Destination, BGM, and Hook Text
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

                # Generate viral visual hook text synchronized for both Video Header Banner and Thumbnail
                auto_hook_text = None
                topic_cat = (
                    "vedic" if ("vedic" in str(item_niche).lower() or "bharat" in str(item_niche).lower() or "history" in str(item_niche).lower())
                    else ("space" if "space" in str(item_niche).lower() else "auto")
                )
                try:
                    from autotube.media.visual_hook import VisualHookManager
                    vm = VisualHookManager()
                    auto_hook_text = vm.generate_hook_text(
                        title=script.title,
                        script_text=script.narration,
                        language=item_channel,
                        topic_category=topic_cat,
                    )
                except Exception as h_err:
                    print_warning(f"Could not generate autopilot hook text: {h_err}")

                # Step D: Render Video Timeline (OpenMontage Remotion Priority + Classic Fallback)
                use_openmontage = self.engine in ("openmontage", "remotion")
                if self.engine in ("auto", "default"):
                    try:
                        from autotube.video.remotion_bridge import REMOTION_DIR
                        use_openmontage = REMOTION_DIR.exists()
                    except Exception:
                        use_openmontage = False

                final_video = None
                if use_openmontage:
                    try:
                        print_info("🎬 AutoPilot: Using OpenMontage Remotion Engine for video rendering...")
                        from autotube.video.remotion_bridge import RemotionBridge
                        r_bridge = RemotionBridge()
                        final_video = r_bridge.render_reel(
                            title=script.title,
                            script_text=script.narration,
                            hook_text=auto_hook_text,
                            voice=item_voice or self.voice or ("Charon" if (item_lang in ("hi", "hindi") or item_channel in ("hi", "hindi")) else "Puck"),
                            scenes=[
                                {
                                    "scene_number": i + 1,
                                    "narration": getattr(sc, "narration", ""),
                                    "visual_subject": getattr(sc, "visual_subject", ""),
                                    "visual_description": getattr(sc, "visual_description", ""),
                                    "search_keywords": getattr(sc, "search_keywords", []),
                                }
                                for i, sc in enumerate(script.scenes)
                            ] if hasattr(script, "scenes") and script.scenes else None,
                            bgm_path=selected_music_path if (selected_music_path and selected_music_path.name != "none") else None,
                            output_format="landscape_16x9" if is_landscape else "vertical_9x16",
                            enable_subscribe_cta=True,
                            target_platform="youtube",
                            output_dir=output_video_path.parent,
                        )
                    except Exception as rb_err:
                        print_warning(f"Remotion render failed ({rb_err}); falling back to classic builder.")
                        final_video = None

                # Fallback to Classic Builder if OpenMontage was not used or failed
                if not final_video or not final_video.exists():
                    print_info("🎬 AutoPilot: Running Classic Waterfall Engine (Voiceover & Visual Waterfall)...")
                    audio_path = self.cfg.paths.temp_dir / f"{slug}_voice.mp3"
                    tts_res = None
                    try:
                        from autotube.voice.gemini_tts import GeminiTTS
                        g_tts = GeminiTTS()
                        gemini_voice = item_voice or self.voice or ("Charon" if (item_lang in ("hi", "hindi") or item_channel in ("hi", "hindi")) else "Puck")
                        print_info(f"🎙️ AutoPilot: Synthesizing voice with OpenMontage Gemini 3.8 Flash TTS (Voice: {gemini_voice})...")
                        tts_res = g_tts.synthesize(
                            text=script.narration,
                            output_audio_path=audio_path,
                            voice=gemini_voice,
                            scenes=[{"narration": getattr(sc, "narration", "")} for sc in script.scenes] if hasattr(script, "scenes") else None,
                        )
                    except Exception as g_err:
                        print_warning(f"OpenMontage Gemini TTS fallback notice: {g_err}")

                    if not tts_res:
                        tts_res = self.tts.synthesize(
                            text=script.narration,
                            output_audio_path=audio_path,
                            voice=item_voice,
                            rate="+6%" if (item_lang == "hi" or "hi" in str(item_voice).lower()) else None,
                        )

                    if not is_landscape:
                        tts_res = self.tts.clamp_duration(
                            tts_res=tts_res,
                            max_seconds=58.5,
                            target_seconds=56.5,
                            width=v_w,
                            height=v_h,
                        )

                    from autotube.voice.tts_engine import compute_scene_durations
                    scene_durations = compute_scene_durations(
                        scenes=script.scenes,
                        words=tts_res.words,
                        total_duration=tts_res.duration_seconds,
                    )

                    from autotube.media.visual_waterfall import acquire_scene_visuals_waterfall
                    print_info(f"Acquiring visual scenes using Vocal-Aligned Engine ({orientation})...")
                    scene_assets = acquire_scene_visuals_waterfall(
                        script=script,
                        output_dir=self.cfg.paths.temp_dir,
                        slug=slug,
                        orientation=orientation,
                        max_scenes=len(script.scenes) if (script.scenes and len(script.scenes) > 0) else 8,
                    )

                    final_video = self.builder.build_short(
                        audio_path=tts_res.audio_path,
                        output_path=output_video_path,
                        scene_assets=scene_assets,
                        scene_durations=scene_durations,
                        subtitles_file=tts_res.subtitles_ass_path,
                        music_path=selected_music_path,
                        width=v_w,
                        height=v_h,
                        hook_text=auto_hook_text,
                    )

                # Universal Fail-Closed Shorts Duration Gate with Auto-Compression
                if not is_landscape and final_video and final_video.exists():
                    from autotube.utils.ffmpeg_helper import get_media_duration, get_ffmpeg_path
                    final_dur = get_media_duration(final_video)
                    if final_dur >= 59.5:
                        if final_dur <= 75.0:
                            # Auto-compress duration to safe 57.0s instead of deleting video!
                            speed_factor = round(final_dur / 57.0, 3)
                            print_info(f"⚡ [Duration Optimizer] Short is {final_dur:.2f}s (>59.5s). Auto-compressing {speed_factor:.2f}x to fit 57.0s sweet spot...")
                            compressed_out = final_video.with_name(f"opt_{final_video.name}")
                            ffmpeg_exe = get_ffmpeg_path()
                            cmd_opt = [
                                ffmpeg_exe, "-y",
                                "-i", str(final_video),
                                "-filter_complex", f"[0:v]setpts=PTS/{speed_factor}[v];[0:a]atempo={speed_factor}[a]",
                                "-map", "[v]", "-map", "[a]",
                                "-c:v", "libx264", "-preset", "fast", "-crf", "20",
                                "-c:a", "aac", "-b:a", "192k",
                                str(compressed_out)
                            ]
                            import subprocess
                            res_opt = subprocess.run(cmd_opt, capture_output=True, text=True)
                            if res_opt.returncode == 0 and compressed_out.exists() and compressed_out.stat().st_size > 50000:
                                final_video.unlink(missing_ok=True)
                                compressed_out.rename(final_video)
                                print_success(f"✅ [Duration Optimized] Short successfully fitted to 57.0s: {final_video.name}")
                            else:
                                print_warning(f"Duration auto-compression notice: {res_opt.stderr[:200]}")
                        else:
                            try:
                                final_video.unlink()
                            except Exception:
                                pass
                            raise RuntimeError(
                                f"Fail-Closed Duration Gate: AutoPilot Short duration is {final_dur:.2f}s, "
                                "violating the YouTube Shorts 60.0s feed limit! Video blocked and deleted."
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

                    sub_cta = (
                        "रोमांचक और रहस्यमयी जानकारियों के लिए चैनल को लाइक और सब्सक्राइब करें!"
                        if item_channel == "hindi"
                        else "Subscribe to the channel for daily mind-bending space & science facts!"
                    )

                    # Generate High-CTR Thumbnail for automated video
                    auto_thumb_path = final_video.parent / f"{final_video.stem}_thumb.jpg"
                    try:
                        from autotube.video.thumbnail import ThumbnailGenerator
                        th_gen = ThumbnailGenerator()
                        topic_cat = (
                            "vedic" if ("vedic" in str(item_niche).lower() or "bharat" in str(item_niche).lower() or "history" in str(item_niche).lower())
                            else ("space" if "space" in str(item_niche).lower() else "auto")
                        )
                        th_gen.generate_high_ctr_thumbnail(
                            title=v_title,
                            output_path=auto_thumb_path,
                            script_text=script.narration,
                            video_path=final_video,
                            custom_hook_text=auto_hook_text,
                            language=item_channel,
                            topic_category=topic_cat,
                        )
                    except Exception as th_err:
                        print_warning(f"Autopilot thumbnail generation skipped: {th_err}")
                        auto_thumb_path = None

                    video_url = self.uploader.upload_video(
                        video_path=final_video,
                        title=v_title,
                        description=(
                            f"{script.narration}\n\n"
                            f"{sub_cta}\n\n"
                            f"{' '.join(script.tags)}"
                        ),
                        tags=script.tags,
                        thumbnail_path=auto_thumb_path if auto_thumb_path and auto_thumb_path.exists() else None,
                        privacy_status="private" if publish_time_iso else "public",
                        publish_at=publish_time_iso,
                        pinned_comment=getattr(script, "pinned_comment", None),
                        chapters=chapters if is_landscape else None,
                        channel=item_channel,
                    )
                    if video_url:
                        uploaded_urls.append(video_url)
                        self.trend_finder.record_topic(topic, video_id=video_url.split("/")[-1])
                        print_success(f"Video uploaded & scheduled successfully: {video_url}")
                    else:
                        print_warning(
                            f"Upload could not be completed for '{topic}'. "
                            f"Rendered video is safely preserved at: {output_video_path.name if output_video_path else 'unknown'}"
                        )

                    # Step F: Auto-publish to Facebook Page (CosmoChronicle) strictly for Hindi vertical reels
                    is_hindi_video = (
                        str(item_lang).lower().startswith("hi")
                        or item_channel == "hindi"
                        or any("\u0900" <= c <= "\u097F" for c in (script.narration or ""))
                        or any("\u0900" <= c <= "\u097F" for c in (script.title or ""))
                    )

                    if not is_landscape and final_video and final_video.exists():
                        if not is_hindi_video:
                            print_info(
                                f"⏭️ Skipping Facebook Reel auto-publish: Video is English ('{topic}'). "
                                "Facebook Page is strictly reserved for Hindi Reels."
                            )
                        else:
                            try:
                                from autotube.uploader.facebook_upload import FacebookReelsUploader
                                fb_uploader = FacebookReelsUploader()
                                if fb_uploader.is_configured():
                                    fb_creds = fb_uploader.load_credentials()
                                    page_name = fb_creds.get('page_name', 'CosmoChronicle')
                                    print_info(f"📤 Auto-publishing Hindi Reel to Facebook Page '{page_name}'...")

                                    import re
                                    # Clean YouTube-specific channel phrases from Facebook caption
                                    clean_narration = re.sub(
                                        r"(चैनल को सब्सक्राइब|चैनल को subscribe|subscribe to (the )?channel|subscribe करें)[^.!?\n]*[.!?]?",
                                        "",
                                        script.narration,
                                        flags=re.IGNORECASE
                                    ).strip()

                                    fb_caption = (
                                        f"{v_title}\n\n"
                                        f"{clean_narration}\n\n"
                                        f"👉 ऐसे ही रोंगटे खड़े कर देने वाले रहस्यों और अनसुने तथ्यों के लिए अभी @{page_name} पेज को फॉलो करें! 🔔✨\n\n"
                                        f"{' '.join(script.tags)}"
                                    )
                                    fb_res = fb_uploader.upload_reel(
                                        video_path=final_video,
                                        title=v_title,
                                        description=fb_caption,
                                        tags=[t.replace('#', '') for t in script.tags],
                                        language="hi",
                                    )
                                    if fb_res.get("success"):
                                        fb_id = fb_res.get("video_id") or fb_res.get("id")
                                        print_success(f"🎉 Facebook Reel published successfully to {page_name}! ID: {fb_id}")
                                    else:
                                        print_warning(f"Facebook Reel upload notice: {fb_res.get('error')}")
                            except Exception as fb_err:
                                print_warning(f"Facebook Reels publishing notice: {fb_err}")
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

        successful_gen = max(0, len(topics_info) - failed_count)
        print_success(
            f"Daily Batch Complete! Generated {successful_gen} videos. "
            f"Uploaded {len(uploaded_urls)}. Failed {failed_count}."
        )
        return uploaded_urls

    def _cleanup_temp(self, max_age_hours: int = 2):
        """Remove temp files older than max_age_hours across all temp directories to prevent disk bloat."""
        # Active job guard: do not purge temp files while a video generation task is in progress
        try:
            from autotube.web.app import GENERATION_STATUS
            if GENERATION_STATUS.get("is_running"):
                print_info("Skipping temp cleanup: active video generation job in progress.")
                return
        except Exception:
            pass

        from autotube.config import PROJECT_ROOT
        target_dirs = [
            self.cfg.paths.temp_dir,
            PROJECT_ROOT / "temp" / "director",
            PROJECT_ROOT / "temp",
        ]
        now = time.time()
        cutoff = now - (max_age_hours * 3600)
        recent_threshold = now - 1800  # 30 minutes
        removed = 0
        freed_mb = 0.0

        for t_dir in target_dirs:
            if not t_dir.exists():
                continue
            for f in t_dir.rglob("*"):
                if f.is_file():
                    try:
                        st = f.stat()
                        # Only delete files modified before cutoff AND not accessed in the last 30 minutes
                        if st.st_mtime < cutoff and getattr(st, "st_atime", cutoff) < recent_threshold:
                            freed_mb += st.st_size / (1024 * 1024)
                            f.unlink()
                            removed += 1
                    except Exception:
                        pass
        if removed > 0:
            print_info(f"Cleaned up {removed} stale temp files ({freed_mb:.1f} MB freed).")
