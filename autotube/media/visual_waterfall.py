"""Smart 3-Tier Visual Acquisition Waterfall Engine.

Order of Execution:
Tier 1: Hugging Face AI Video (Primary & Persistent Retry).
        If before 8:00 AM morning cutoff, retries persistently with backoff.
Tier 2: Gemini AI Video (Veo Engine).
        Triggers if 8:00 AM morning deadline is reached or HF exhausted.
Tier 3: Current Enhanced Logic (Verified Stock + Pollinations Photorealistic AI).
        Triggers automatically when Gemini quota/limit is exceeded.
"""

import datetime
from pathlib import Path
from typing import Any, List, Optional

from autotube.config import get_config
from autotube.media.free_video_gen import FreeVideoGenerator
from autotube.media.stock_fetcher import StockFetcher
from autotube.media.veo_generator import VeoQuotaExceededError, VeoVideoGenerator
from autotube.utils.console import (
    print_error,
    print_info,
    print_step,
    print_success,
    print_warning,
)


def is_past_morning_cutoff(cutoff_hour: int = 8, cutoff_minute: int = 0) -> bool:
    """Check if current time in IST (UTC+5:30) is at or past the morning cutoff."""
    ist = datetime.timezone(datetime.timedelta(hours=5, minutes=30))
    now_ist = datetime.datetime.now(ist)
    cutoff_time = now_ist.replace(hour=cutoff_hour, minute=cutoff_minute, second=0, microsecond=0)
    return now_ist >= cutoff_time


def acquire_scene_visuals_waterfall(
    script: Any,
    output_dir: Path,
    slug: str,
    orientation: str = "portrait",
    max_scenes: int = 12,
    max_hf_retries: int = 2,
    cutoff_hour: int = 8,
) -> List[Path]:
    """Execute the 3-Tier Visual Acquisition Waterfall:
    1. Hugging Face (persistent retry until 8 AM cutoff)
    2. Gemini (Veo) if 8 AM cutoff reached or HF unavailable
    3. Current Enhanced Logic (Stock + Pollinations AI) if Gemini quota exceeded
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    scenes = getattr(script, "scenes", []) or []

    # -------------------------------------------------------------
    # TIER 1: Hugging Face (Primary & Persistent Retry)
    # -------------------------------------------------------------
    hf_gen = FreeVideoGenerator()
    cutoff_reached = is_past_morning_cutoff(cutoff_hour=cutoff_hour)

    if hf_gen.is_available() and scenes:
        print_info(f"🚀 [Tier 1] Initiating Hugging Face AI Video Generation (Target: {min(len(scenes), max_scenes)} scenes)...")
        # If before 8 AM, do persistent retries; if after 8 AM, do 1 fast attempt
        max_attempts = max_hf_retries if not cutoff_reached else 1
        for attempt in range(1, max_attempts + 1):
            print_info(f"Hugging Face generation attempt {attempt}/{max_attempts}...")
            try:
                hf_videos = hf_gen.generate_scene_videos(
                    scenes=scenes,
                    output_dir=output_dir,
                    orientation=orientation,
                    max_scenes=min(len(scenes), max_scenes),
                )
                if hf_videos and len(hf_videos) >= len(scenes[:max_scenes]):
                    print_success(f"🎬 [Tier 1 Succeeded] Generated {len(hf_videos)} scenes with Hugging Face!")
                    return hf_videos
                elif hf_videos:
                    print_warning(f"Hugging Face generated partial scenes ({len(hf_videos)}/{len(scenes[:max_scenes])}). Retrying...")
            except Exception as e:
                print_warning(f"Hugging Face attempt {attempt} error: {e}")

            if attempt < max_attempts and not is_past_morning_cutoff(cutoff_hour=cutoff_hour):
                import time
                wait_sec = 15 * attempt
                print_info(f"Retrying Hugging Face in {wait_sec}s...")
                time.sleep(wait_sec)

        print_warning("Hugging Face Space busy or timed out. Handing over to Tier 2 (Gemini Veo)...")

    # -------------------------------------------------------------
    # TIER 2: Gemini (Veo Video Generation)
    # -------------------------------------------------------------
    cfg = get_config()
    if cfg.gemini_api_key:
        print_info("🤖 [Tier 2] Initiating Gemini (Veo Engine) Video Generation...")
        try:
            veo_gen = VeoVideoGenerator()
            # Build scene prompts
            queries = [
                f"{getattr(s, 'visual_subject', '')}, {getattr(s, 'visual_description', '')}"
                for s in scenes[:max_scenes]
            ]
            if not queries:
                queries = [getattr(script, "topic", "cinematic scene")]

            veo_scenes = veo_gen.generate_scenes(
                prompts=queries,
                output_dir=output_dir,
                slug=slug,
                aspect_ratio="9:16" if orientation == "portrait" else "16:9",
                max_scenes=max_scenes,
            )
            if veo_scenes and len(veo_scenes) >= 1:
                print_success(f"🎬 [Tier 2 Succeeded] Generated {len(veo_scenes)} scenes with Gemini Veo!")
                return veo_scenes
        except (VeoQuotaExceededError, Exception) as gemini_err:
            err_msg = getattr(gemini_err, "message", str(gemini_err))
            print_warning(f"⚠️ Gemini (Veo) Quota / Limit Exceeded: {err_msg}")
            print_info("🔄 Switching to Tier 3 (Vocal-Aligned Real Motion Stock Video Footage)...")

    # -------------------------------------------------------------
    # TIER 3: Vocal-Aligned Real Motion Stock Footage + AI Visuals
    # -------------------------------------------------------------
    print_info("🎬 [Tier 3] Acquiring Vocal-Aligned Visual Assets (Stock Videos & Photorealistic AI)...")
    stock_fetcher = StockFetcher()
    if scenes:
        scene_assets = stock_fetcher.fetch_scene_visual_assets(
            scenes=scenes[:max_scenes],
            output_dir=output_dir,
            orientation=orientation,
            require_video=False,
        )
    else:
        queries = getattr(script, "visual_keywords", []) or [getattr(script, "topic", "scene")]
        scene_assets = [
            stock_fetcher.fetch_best_visual_for_scene(
                subject=q,
                narration=getattr(script, "narration", None),
                output_dir=output_dir,
                orientation=orientation,
                require_video=False,
            )
            for q in queries[:max_scenes]
        ]

    print_success(f"🎬 [Tier 3 Succeeded] Acquired {len(scene_assets)} synchronized scene visual assets!")
    return scene_assets
