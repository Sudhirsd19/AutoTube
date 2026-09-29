"""Google AI Studio Veo Video Generator with Graceful Quota & Rate Limit Detection."""

import os
import time
from pathlib import Path
from typing import List, Optional

from google import genai
from google.genai import types

from autotube.config import get_config
from autotube.utils.console import print_error, print_info, print_success, print_warning

VEO_CANDIDATE_MODELS = [
    "veo-3.1-fast-generate-preview",
    "veo-3.1-lite-generate-preview",
    "veo-3.1-generate-preview",
]


class VeoQuotaExceededError(Exception):
    """Raised when Google Veo API quota is exhausted, rate limited, or billing required."""

    def __init__(self, message: str, original_error: Optional[Exception] = None):
        super().__init__(message)
        self.original_error = original_error


class VeoVideoGenerator:
    """Generates AI video clips using Google Veo via the Gemini API."""

    def __init__(self, api_key: Optional[str] = None):
        cfg = get_config()
        self.api_key = api_key or cfg.gemini_api_key or os.getenv("GEMINI_API_KEY")
        self.client = None
        if self.api_key:
            try:
                self.client = genai.Client(api_key=self.api_key)
            except Exception as e:
                print_warning(f"Could not initialize Gemini Client for Veo: {e}")

    def is_available(self) -> bool:
        """Check if client is configured."""
        return self.client is not None

    def generate_scene_video(
        self,
        prompt: str,
        output_path: Path,
        aspect_ratio: str = "9:16",
        timeout: int = 180,
    ) -> Path:
        """Generate a single 5-8s scene video from a prompt using Veo."""
        if not self.client:
            raise VeoQuotaExceededError("Gemini API Client not configured. No GEMINI_API_KEY found.")

        output_path.parent.mkdir(parents=True, exist_ok=True)

        last_error = None
        for model_name in VEO_CANDIDATE_MODELS:
            try:
                print_info(f"Submitting Veo video task to [{model_name}]...")
                operation = self.client.models.generate_videos(
                    model=model_name,
                    source=types.GenerateVideosSource(prompt=prompt),
                    config=types.GenerateVideosConfig(
                        aspect_ratio=aspect_ratio,
                    ),
                )
                print_info(f"Veo task accepted: {operation.name}. Waiting for rendering...")

                # Poll operation until done
                start_time = time.time()
                while not operation.done:
                    if time.time() - start_time > timeout:
                        raise TimeoutError(f"Veo generation timed out after {timeout} seconds.")
                    time.sleep(6)
                    operation = self.client.operations.get(operation)

                if operation.error:
                    err_msg = (
                        operation.error.message
                        if hasattr(operation.error, "message")
                        else str(operation.error)
                    )
                    if (
                        "429" in err_msg
                        or "RESOURCE_EXHAUSTED" in err_msg
                        or "quota" in err_msg.lower()
                        or "billing" in err_msg.lower()
                    ):
                        raise VeoQuotaExceededError(err_msg)
                    raise RuntimeError(f"Veo rendering error: {err_msg}")

                if not operation.response or not operation.response.generated_videos:
                    raise RuntimeError("No generated video found in operation response.")

                video = operation.response.generated_videos[0].video
                video.save(str(output_path))
                print_success(f"Veo scene clip saved: {output_path.name}")
                return output_path

            except Exception as e:
                err_str = str(e)
                last_error = e
                # Check for quota, 429, or permission/billing limits
                if (
                    "429" in err_str
                    or "RESOURCE_EXHAUSTED" in err_str
                    or "quota" in err_str.lower()
                    or "billing" in err_str.lower()
                    or "PERMISSION_DENIED" in err_str
                ):
                    raise VeoQuotaExceededError(err_str, original_error=e)
                print_warning(f"Veo model [{model_name}] attempt failed: {e}")
                continue

        raise VeoQuotaExceededError(
            f"All Veo models failed: {last_error}", original_error=last_error
        )

    def generate_scenes(
        self,
        prompts: List[str],
        output_dir: Path,
        slug: str,
        aspect_ratio: str = "9:16",
        max_scenes: int = 5,
    ) -> List[Path]:
        """Generate a series of video scenes for a story or short."""
        output_dir.mkdir(parents=True, exist_ok=True)
        selected_prompts = prompts[:max_scenes]
        rendered_scenes: List[Path] = []

        print_info(f"Starting Veo multi-scene generation ({len(selected_prompts)} scenes)...")
        for idx, prompt_text in enumerate(selected_prompts):
            scene_path = output_dir / f"{slug}_veo_scene_{idx+1:02d}.mp4"
            print_info(f"Generating Veo Scene {idx+1}/{len(selected_prompts)}: '{prompt_text[:60]}...'")
            out_file = self.generate_scene_video(
                prompt=prompt_text,
                output_path=scene_path,
                aspect_ratio=aspect_ratio,
            )
            rendered_scenes.append(out_file)

        return rendered_scenes
