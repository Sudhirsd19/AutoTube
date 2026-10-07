"""NVIDIA AI Video Generator - Integrates NVIDIA NIM Cosmos Video models with smart fallback."""

import os
import time
import json
import urllib.request
import urllib.error
from pathlib import Path
from typing import Optional, Dict, Any

from autotube.config import PROJECT_ROOT, get_config
from autotube.utils.console import print_info, print_success, print_warning, print_error

NVIDIA_CACHE_DIR = PROJECT_ROOT / "assets" / "nvidia_videos"


class NvidiaVideoGenerator:
    """NVIDIA NIM Cosmos / Video AI Generator with smart fallback to Wan2.1 and Pexels."""

    API_BASE = "https://integrate.api.nvidia.com/v1"

    def __init__(self, api_key: Optional[str] = None):
        cfg = get_config()
        self.api_key = api_key or os.getenv("NVIDIA_API_KEY", "") or getattr(cfg, "nvidia_api_key", "")
        NVIDIA_CACHE_DIR.mkdir(parents=True, exist_ok=True)

    def is_configured(self) -> bool:
        return bool(self.api_key and len(self.api_key.strip()) > 10)

    def generate_video(
        self,
        prompt: str,
        image_path: Optional[Path] = None,
        output_path: Optional[Path] = None,
        duration_seconds: int = 5,
        allow_stock_fallback: bool = True,
    ) -> Optional[Path]:
        """Generate a video clip using NVIDIA NIM. If key missing or busy, falls back smoothly."""
        if not output_path:
            clean_stem = "".join(c for c in prompt[:30] if c.isalnum() or c in (" ", "_")).replace(" ", "_")
            output_path = NVIDIA_CACHE_DIR / f"nvidia_{clean_stem}_{int(time.time())}.mp4"

        # Check cache
        if output_path.exists() and output_path.stat().st_size > 50000:
            return output_path

        # Step 1: Try NVIDIA NIM API if key configured
        if self.is_configured():
            try:
                print_info(f"Connecting to NVIDIA NIM Video API (Prompt: '{prompt[:45]}...')...")
                url = f"{self.API_BASE}/genai/nvidia/cosmos-1.0-diffusion-7b-video2world"
                
                headers = {
                    "Authorization": f"Bearer {self.api_key.strip()}",
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                }
                payload = {
                    "prompt": prompt,
                    "num_frames": int(duration_seconds * 16),
                    "fps": 16,
                    "aspect_ratio": "9:16",
                }

                req = urllib.request.Request(
                    url,
                    data=json.dumps(payload).encode("utf-8"),
                    headers=headers,
                    method="POST",
                )

                with urllib.request.urlopen(req, timeout=90) as resp:
                    res_data = json.loads(resp.read().decode("utf-8"))
                    video_url = res_data.get("video_url") or res_data.get("output", {}).get("url")
                    if video_url:
                        # Download output video
                        urllib.request.urlretrieve(video_url, output_path)
                        if output_path.exists() and output_path.stat().st_size > 10000:
                            print_success(f"NVIDIA Cosmos Video generated successfully: {output_path.name}")
                            return output_path
            except Exception as e:
                print_warning(f"NVIDIA NIM API call failed or queued: {e}. Activating smart fallback...")

        # Optional provider-local Pexels fallback. Director Studio disables this
        # because it has a centralized global reuse/content-fingerprint guard.
        if not allow_stock_fallback:
            return None

        print_info("Smart Fallback: Searching HD Portrait Stock Clips (Pexels)...")
        try:
            from autotube.media.pexels_video import PexelsVideoFetcher
            pexels = PexelsVideoFetcher()
            if pexels.is_configured():
                res = pexels.get_scene_video(search_query=prompt[:40], orientation="portrait")
                if res and res.exists():
                    print_success(f"Pexels HD Stock video acquired: {res.name}")
                    return res
        except Exception as e:
            print_warning(f"Pexels fallback failed: {e}")

        return None
