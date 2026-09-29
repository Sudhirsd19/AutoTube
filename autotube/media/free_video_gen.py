"""Free AI Video Generator using HuggingFace Spaces (Wan2.1, CogVideoX).

Generates realistic 3D cinematic AI videos from text prompts using
community-hosted open-source models on HuggingFace — 100% FREE!

Supported models:
- Wan2.1 (Alibaba/Wan-AI) — Best quality, 5-second clips
- CogVideoX (THUDM) — Alternative fallback

Usage:
    generator = FreeVideoGenerator()
    video_path = generator.generate_video(
        prompt="A black hole swallowing a star, cinematic 4K",
        output_path=Path("output.mp4"),
        orientation="portrait",  # for YouTube Shorts (720x1280)
    )
"""

import shutil
import time
from pathlib import Path
from typing import Any, List, Optional

from autotube.utils.console import print_error, print_info, print_success, print_warning

# HuggingFace Spaces with free Wan2.1 access (priority order)
WAN21_SPACES = [
    "Wan-AI/Wan2.1",
    "multimodalart/wan2.1-fast",
]

# Orientation → Wan2.1 size mapping
SIZE_MAP = {
    "portrait": "720*1280",     # 9:16 vertical (YouTube Shorts)
    "landscape": "1280*720",    # 16:9 horizontal (YouTube Videos)
    "square": "960*960",        # 1:1
}


class FreeVideoGenerator:
    """Generate realistic AI videos using free HuggingFace Spaces."""

    def __init__(self):
        self._client = None
        self._space_name = None

    def _connect(self) -> bool:
        """Connect to the first available Wan2.1 HuggingFace Space."""
        if self._client is not None:
            return True

        try:
            from gradio_client import Client
        except ImportError:
            print_error("gradio_client not installed. Run: pip install gradio_client")
            return False

        for space in WAN21_SPACES:
            try:
                print_info(f"Connecting to free AI video model: {space}...")
                self._client = Client(space, verbose=False)
                self._space_name = space
                print_success(f"Connected to {space} (Wan2.1 — free AI video)!")
                return True
            except Exception as e:
                print_warning(f"Space {space} unavailable: {e}")
                continue

        print_error("No free AI video Space available right now. Will use stock video fallback.")
        return False

    def generate_video(
        self,
        prompt: str,
        output_path: Path,
        orientation: str = "portrait",
        timeout_seconds: int = 600,
        seed: int = -1,
    ) -> Optional[Path]:
        """Generate a single AI video clip from a text prompt.

        Args:
            prompt: Text description of the video to generate
            output_path: Where to save the generated .mp4
            orientation: "portrait" (9:16), "landscape" (16:9), or "square"
            timeout_seconds: Max wait time (default 10 minutes)
            seed: Random seed (-1 for random)

        Returns:
            Path to generated video, or None if failed
        """
        if not self._connect():
            return None

        output_path.parent.mkdir(parents=True, exist_ok=True)
        size = SIZE_MAP.get(orientation, SIZE_MAP["portrait"])

        try:
            print_info(f"🎬 Generating AI video: '{prompt[:60]}...' ({size})")

            # Submit async generation job
            result = self._client.predict(
                prompt=prompt,
                size=size,
                watermark_wan=False,
                seed=float(seed),
                api_name="/t2v_generation_async",
            )

            cost_est = result[0] if isinstance(result, (list, tuple)) else 0
            queue_est = result[1] if isinstance(result, (list, tuple)) and len(result) > 1 else 0
            print_info(f"Job queued. Estimated GPU time: {cost_est:.0f}s, Queue wait: {queue_est:.0f}s")

            # Poll for completion
            start_time = time.time()
            poll_interval = 8  # seconds between polls
            last_progress = -1

            while (time.time() - start_time) < timeout_seconds:
                time.sleep(poll_interval)
                try:
                    status = self._client.predict(api_name="/status_refresh")
                    video_info = status[0]
                    progress = status[3] if isinstance(status, (list, tuple)) and len(status) > 3 else 0

                    if progress != last_progress:
                        elapsed = int(time.time() - start_time)
                        print_info(f"  AI Video generation: {progress:.0f}% ({elapsed}s elapsed)")
                        last_progress = progress

                    # Check if video is ready
                    if video_info and isinstance(video_info, dict) and video_info.get("video"):
                        video_src = video_info["video"]
                        shutil.copy2(video_src, str(output_path))

                        if output_path.exists() and output_path.stat().st_size > 10000:
                            size_mb = output_path.stat().st_size / (1024 * 1024)
                            print_success(f"🎬 AI Video generated: {output_path.name} ({size_mb:.1f} MB)")
                            return output_path
                        else:
                            print_warning("Generated video file too small, may be incomplete.")
                            return None

                except Exception as poll_err:
                    # Polling can fail transiently, continue waiting
                    elapsed = int(time.time() - start_time)
                    if elapsed > 60:
                        print_warning(f"  Still waiting... ({elapsed}s, error: {poll_err})")

            print_warning(f"AI video generation timed out after {timeout_seconds}s")
            return None

        except Exception as e:
            print_error(f"AI video generation failed: {e}")
            return None

    def generate_scene_videos(
        self,
        scenes: List[Any],
        output_dir: Path,
        orientation: str = "portrait",
        max_scenes: int = 4,
    ) -> List[Path]:
        """Generate AI videos for multiple script scenes.

        Args:
            scenes: List of ShortScene objects with visual_subject and visual_description
            output_dir: Directory to save generated videos
            orientation: "portrait" or "landscape"
            max_scenes: Maximum number of scenes to generate (free tier is slow)

        Returns:
            List of paths to generated videos
        """
        output_dir.mkdir(parents=True, exist_ok=True)
        generated: List[Path] = []

        for idx, scene in enumerate(scenes[:max_scenes]):
            subject = getattr(scene, "visual_subject", "")
            description = getattr(scene, "visual_description", "")

            # Build a cinematic prompt from scene data
            prompt = self._build_cinematic_prompt(subject, description)

            output_path = output_dir / f"ai_scene_{idx+1:02d}.mp4"
            print_info(f"Scene {idx+1}/{min(len(scenes), max_scenes)}: Generating AI video for '{subject}'")

            video = self.generate_video(
                prompt=prompt,
                output_path=output_path,
                orientation=orientation,
            )

            if video:
                generated.append(video)
            else:
                print_warning(f"Scene {idx+1} AI generation failed. Will use stock fallback for this scene.")

        return generated

    @staticmethod
    def _build_cinematic_prompt(subject: str, description: str) -> str:
        """Create a cinematic-quality prompt optimized for Wan2.1."""
        base = description if description else subject
        if not base:
            return "cinematic dramatic scene, 4K ultra HD"

        # Add cinematic quality tags
        quality_tags = "cinematic lighting, photorealistic, dramatic atmosphere, ultra detailed, 4K"
        prompt = f"{base}, {quality_tags}"

        # Keep under 200 chars for best results
        if len(prompt) > 200:
            prompt = prompt[:197] + "..."

        return prompt

    def is_available(self) -> bool:
        """Check if the free video generation service is reachable."""
        return self._connect()
