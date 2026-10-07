"""Cloud AI Video Generator for AutoTube.

Supports Replicate (Wan2.1-I2V, Kling AI, Minimax, LivePortrait),
Direct Kling AI API, and Hedra Talking Character API.
Converts canonical character portraits and scenes into full-motion cinematic movie clips (9:16 vertical HD).
"""

import base64
import json
import os
import time
from pathlib import Path
from typing import Any, Dict, Optional

import requests
from autotube.config import get_config
from autotube.utils.console import print_error, print_info, print_success, print_warning

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
CANONICAL_VIDEOS_DIR = PROJECT_ROOT / "assets" / "alien_interview" / "videos"


class CloudVideoGenerator:
    """Unified client for Cloud AI Image-to-Video and Talking Avatar generation."""

    def __init__(
        self,
        replicate_token: Optional[str] = None,
        kling_access_key: Optional[str] = None,
        kling_secret_key: Optional[str] = None,
        hedra_api_key: Optional[str] = None,
    ):
        self.cfg = get_config()
        self.replicate_token = (
            replicate_token
            or os.getenv("REPLICATE_API_TOKEN")
            or os.getenv("REPLICATE_API_KEY")
        )
        self.kling_access_key = kling_access_key or os.getenv("KLING_ACCESS_KEY")
        self.kling_secret_key = kling_secret_key or os.getenv("KLING_SECRET_KEY")
        self.hedra_api_key = hedra_api_key or os.getenv("HEDRA_API_KEY")

        CANONICAL_VIDEOS_DIR.mkdir(parents=True, exist_ok=True)

    def is_configured(self) -> bool:
        """Returns True if any supported Cloud Video API is configured."""
        return bool(
            self.replicate_token
            or (self.kling_access_key and self.kling_secret_key)
            or self.hedra_api_key
        )

    def get_active_provider(self) -> str:
        """Return the name of the currently active primary video provider."""
        if self.replicate_token:
            return "Replicate (Wan2.1 / Kling / Minimax)"
        if self.kling_access_key and self.kling_secret_key:
            return "Kling AI Direct API"
        if self.hedra_api_key:
            return "Hedra Talking Character API"
        return "None (API Key Required)"

    # -------------------------------------------------------------
    # 1. REPLICATE IMAGE-TO-VIDEO PIPELINE (WAN2.1 / KLING)
    # -------------------------------------------------------------
    def generate_i2v_replicate(
        self,
        image_path: Path,
        prompt: str,
        output_path: Path,
        model: str = "wan-video/wan-2.1-i2v-480p",
        duration_seconds: int = 5,
        aspect_ratio: str = "9:16",
    ) -> Optional[Path]:
        """Generate a realistic moving video from a still image using Replicate API."""
        if not self.replicate_token:
            print_warning("REPLICATE_API_TOKEN not set. Cannot run Replicate I2V.")
            return None

        if not image_path.exists():
            print_error(f"Source image not found: {image_path}")
            return None

        print_info(f"🚀 Submitting Image-to-Video to Replicate ({model})...")
        print_info(f"   Source Image: {image_path.name}")
        print_info(f"   Prompt: {prompt[:80]}...")

        # Convert image to base64 data URI
        with open(image_path, "rb") as f:
            encoded_image = base64.b64encode(f.read()).decode("utf-8")
        ext = image_path.suffix.lstrip(".").lower()
        if ext == "jpg":
            ext = "jpeg"
        data_uri = f"data:image/{ext};base64,{encoded_image}"

        headers = {
            "Authorization": f"Bearer {self.replicate_token}",
            "Content-Type": "application/json",
            "Prefer": "wait=60",
        }

        # Model mapping on Replicate
        # Wan 2.1 is top-tier open state of the art I2V
        payload = {
            "input": {
                "image": data_uri,
                "prompt": prompt,
                "aspect_ratio": aspect_ratio,
                "duration": duration_seconds,
            }
        }

        create_url = f"https://api.replicate.com/v1/models/{model}/predictions"

        try:
            resp = requests.post(create_url, headers=headers, json=payload, timeout=60)
            if resp.status_code not in (200, 201):
                print_error(f"Replicate API error ({resp.status_code}): {resp.text}")
                return None

            prediction = resp.json()
            pred_id = prediction.get("id")
            poll_url = prediction.get("urls", {}).get("get") or f"https://api.replicate.com/v1/predictions/{pred_id}"

            print_info(f"⏳ Video generation task started (ID: {pred_id}). Polling status...")

            # Poll for completion
            max_wait_seconds = 300
            start_time = time.time()
            while time.time() - start_time < max_wait_seconds:
                poll_resp = requests.get(
                    poll_url,
                    headers={"Authorization": f"Bearer {self.replicate_token}"},
                    timeout=30,
                )
                if poll_resp.status_code != 200:
                    time.sleep(5)
                    continue

                status_data = poll_resp.json()
                status = status_data.get("status")

                if status == "succeeded":
                    output_url = status_data.get("output")
                    if isinstance(output_url, list) and len(output_url) > 0:
                        output_url = output_url[0]

                    if output_url:
                        print_success(f"🎉 Replicate generation succeeded! Downloading MP4...")
                        return self._download_file(output_url, output_path)
                    else:
                        print_error("Replicate succeeded but output URL was empty.")
                        return None

                elif status in ("failed", "canceled"):
                    err = status_data.get("error", "Unknown error")
                    print_error(f"Replicate video generation {status}: {err}")
                    return None

                time.sleep(6)

            print_error("Replicate generation timed out after 5 minutes.")
            return None

        except Exception as e:
            print_error(f"Replicate invocation failed: {e}")
            return None

    # -------------------------------------------------------------
    # 2. DIRECT KLING AI API PIPELINE
    # -------------------------------------------------------------
    def generate_i2v_kling(
        self,
        image_path: Path,
        prompt: str,
        output_path: Path,
        duration: str = "5",
        mode: str = "std",
    ) -> Optional[Path]:
        """Generate a moving video using Kling AI's official HTTP API."""
        if not (self.kling_access_key and self.kling_secret_key):
            print_warning("KLING_ACCESS_KEY or KLING_SECRET_KEY missing. Cannot call Kling API.")
            return None

        try:
            import jwt
        except ImportError:
            print_error("PyJWT not installed for Kling API token generation.")
            return None

        # Build Kling JWT token
        now_ts = int(time.time())
        token_payload = {
            "iss": self.kling_access_key,
            "exp": now_ts + 1800,
            "nbf": now_ts - 5,
        }
        token = jwt.encode(token_payload, self.kling_secret_key, algorithm="HS256")

        with open(image_path, "rb") as f:
            encoded_image = base64.b64encode(f.read()).decode("utf-8")

        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }

        body = {
            "model_name": "kling-v1",
            "image": encoded_image,
            "prompt": prompt,
            "mode": mode,
            "duration": duration,
            "aspect_ratio": "9:16",
        }

        submit_url = "https://api.klingai.com/v1/videos/image2video"
        try:
            resp = requests.post(submit_url, headers=headers, json=body, timeout=40)
            data = resp.json()
            if data.get("code") != 0:
                print_error(f"Kling API error: {data.get('message')}")
                return None

            task_id = data.get("data", {}).get("task_id")
            print_info(f"⏳ Kling task {task_id} queued. Polling...")

            poll_url = f"https://api.klingai.com/v1/videos/image2video/{task_id}"
            start_time = time.time()
            while time.time() - start_time < 300:
                poll_resp = requests.get(poll_url, headers=headers, timeout=20)
                p_data = poll_resp.json()
                task_status = p_data.get("data", {}).get("task_status")

                if task_status == "succeed":
                    works = p_data.get("data", {}).get("task_result", {}).get("videos", [])
                    if works and len(works) > 0:
                        vid_url = works[0].get("url")
                        return self._download_file(vid_url, output_path)

                elif task_status in ("failed", "canceled"):
                    print_error(f"Kling task failed: {p_data.get('data', {}).get('task_status_msg')}")
                    return None

                time.sleep(8)

            print_error("Kling API timed out.")
            return None

        except Exception as e:
            print_error(f"Kling API exception: {e}")
            return None

    # -------------------------------------------------------------
    # 3. HIGH LEVEL UNIFIED METHOD (WITH AUTOMATIC CACHING)
    # -------------------------------------------------------------
    def get_or_generate_character_clip(
        self,
        asset_name: str,
        source_image: Path,
        motion_prompt: str,
        duration_seconds: int = 5,
    ) -> Path:
        """Returns the pre-generated motion video clip for an asset, or generates it if API is available.
        If no API or generation fails, falls back gracefully to the source image.
        """
        target_video = CANONICAL_VIDEOS_DIR / f"{asset_name}_motion.mp4"

        # 1. Already exists in canonical video cache
        if target_video.exists() and target_video.stat().st_size > 50000:
            return target_video

        # 2. If Cloud Video API is configured, generate now!
        if self.is_configured():
            print_info(f"🎬 Generating Movie-style Motion Clip for: {asset_name}...")
            res = None
            if self.replicate_token:
                res = self.generate_i2v_replicate(
                    image_path=source_image,
                    prompt=motion_prompt,
                    output_path=target_video,
                    duration_seconds=duration_seconds,
                )
            elif self.kling_access_key:
                res = self.generate_i2v_kling(
                    image_path=source_image,
                    prompt=motion_prompt,
                    output_path=target_video,
                )

            if res and res.exists():
                print_success(f"✨ Movie clip saved to: {res.name}")
                return res

        # 3. 100% FREE AUTOMATED PIPELINE: Wan2.1 ZeroGPU Space (Zero Cost!)
        try:
            print_info(f"🎬 Attempting 100% FREE Automated AI Video generation for: {asset_name} (Wan2.1)...")
            from autotube.media.free_video_gen import FreeVideoGenerator
            free_gen = FreeVideoGenerator()
            free_res = free_gen.generate_i2v(
                image_path=source_image,
                prompt=motion_prompt,
                output_path=target_video,
                timeout_seconds=240,
            )
            if free_res and free_res.exists() and free_res.stat().st_size > 50000:
                print_success(f"✨ 100% FREE Movie clip saved: {free_res.name}")
                return free_res
        except Exception as free_err:
            print_warning(f"Free I2V generator note: {free_err}")

        # 4. Seamless Fallback: Return canonical high-res image with smooth zoompan
        return source_image

    def _download_file(self, url: str, dest_path: Path) -> Optional[Path]:
        """Download remote video URL to local path."""
        try:
            dest_path.parent.mkdir(parents=True, exist_ok=True)
            r = requests.get(url, stream=True, timeout=60)
            if r.status_code == 200:
                with open(dest_path, "wb") as f:
                    for chunk in r.iter_content(chunk_size=65536):
                        f.write(chunk)
                return dest_path
            print_error(f"Download failed with status {r.status_code}")
            return None
        except Exception as e:
            print_error(f"Download exception: {e}")
            return None
