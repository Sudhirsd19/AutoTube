"""Free AI Video Generator using HuggingFace Spaces (Wan2.1).

Generates realistic 3D cinematic AI videos from text prompts using
community-hosted open-source models on HuggingFace — 100% FREE!

The Wan-AI/Wan2.1 Space uses an async pattern:
1. Submit via /t2v_generation_async → starts GPU job
2. Poll via /status_refresh → returns progress + video when done
3. The gradio_client.submit() handles session state properly

Usage:
    generator = FreeVideoGenerator()
    video_path = generator.generate_video(
        prompt="A black hole swallowing a star, cinematic 4K",
        output_path=Path("output.mp4"),
        orientation="portrait",
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

        import os
        token = os.getenv("HF_TOKEN")

        for space in WAN21_SPACES:
            try:
                print_info(f"Connecting to free AI video model: {space}...")
                self._client = Client(space, token=token, verbose=False)
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
        timeout_seconds: int = 120,
        seed: int = -1,
    ) -> Optional[Path]:
        """Generate a single AI video clip from a text prompt.

        Uses the Wan-AI/Wan2.1 Space async pattern:
        1. Submit job via /t2v_generation_async
        2. Poll via /status_refresh until video appears
        3. Use gradio_client.submit() to maintain session state

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

            # Step 1: Submit async generation job
            submit_job = self._client.submit(
                prompt=prompt,
                size=size,
                watermark_wan=False,
                seed=float(seed),
                api_name="/t2v_generation_async",
            )

            # Wait for submission to complete
            try:
                init_result = submit_job.result(timeout=60)
                print_info(f"Job queued on free GPU. Waiting for generation...")
            except Exception:
                print_info("Job submitted. Waiting for generation...")

            # Step 2: Poll for completion using submit() to maintain session
            start_time = time.time()
            poll_interval = 10

            while (time.time() - start_time) < timeout_seconds:
                time.sleep(poll_interval)
                elapsed = int(time.time() - start_time)

                try:
                    # Use submit() for session-aware polling
                    status_job = self._client.submit(api_name="/status_refresh")
                    status = status_job.result(timeout=30)

                    if not isinstance(status, (list, tuple)):
                        status = (status,)

                    video_info = status[0]

                    # Extract video from result
                    video_path = self._extract_video_path(video_info)
                    if video_path:
                        shutil.copy2(video_path, str(output_path))
                        if output_path.exists() and output_path.stat().st_size > 10000:
                            size_mb = output_path.stat().st_size / (1024 * 1024)
                            print_success(f"🎬 AI Video generated: {output_path.name} ({size_mb:.1f} MB) in {elapsed}s")
                            return output_path

                    # Show progress
                    progress_info = status[3] if len(status) > 3 else None
                    progress_text = self._extract_progress(progress_info)
                    if elapsed % 30 == 0:  # Log every 30 seconds
                        print_info(f"  Generating... ({elapsed}s elapsed) {progress_text}")

                except Exception as poll_err:
                    if elapsed > 120 and elapsed % 60 == 0:
                        print_warning(f"  Still waiting... ({elapsed}s, {poll_err})")

            # Step 3: Final attempt via /online_process_change
            try:
                print_info("Attempting final video retrieval...")
                final_result = self._client.predict(api_name="/online_process_change")
                video_path = self._extract_video_path(final_result)
                if video_path:
                    shutil.copy2(video_path, str(output_path))
                    if output_path.exists() and output_path.stat().st_size > 10000:
                        size_mb = output_path.stat().st_size / (1024 * 1024)
                        print_success(f"🎬 AI Video generated: {output_path.name} ({size_mb:.1f} MB)")
                        return output_path
            except Exception:
                pass

            print_warning(f"AI video generation timed out after {timeout_seconds}s. Space may be overloaded.")
            return None

        except Exception as e:
            print_error(f"AI video generation failed: {e}")
            return None

    @staticmethod
    def _extract_video_path(result: Any) -> Optional[str]:
        """Extract actual video file path from various Gradio response formats."""
        if result is None:
            return None

        # Dict responses
        if isinstance(result, dict):
            # Check nested value if it's an update dict
            if "value" in result and result["value"] is not None:
                nested = FreeVideoGenerator._extract_video_path(result["value"])
                if nested:
                    return nested

            # Standard video key
            video_val = result.get("video")
            if video_val and isinstance(video_val, str) and not video_val.startswith("{"):
                return video_val

            # Path key
            path_val = result.get("path")
            if path_val and isinstance(path_val, str) and path_val.endswith((".mp4", ".webm", ".mov")):
                return path_val

            return None

        # Direct file path string
        if isinstance(result, str):
            if result.endswith((".mp4", ".webm", ".mov")):
                return result

        # Tuple/list containing a video dict
        if isinstance(result, (list, tuple)) and len(result) > 0:
            for item in result:
                extracted = FreeVideoGenerator._extract_video_path(item)
                if extracted:
                    return extracted

        return None

    @staticmethod
    def _extract_progress(progress_info: Any) -> str:
        """Extract human-readable progress from Gradio response."""
        if progress_info is None:
            return ""
        if isinstance(progress_info, dict):
            label = progress_info.get("label", "")
            value = progress_info.get("value", "")
            if label:
                return f"[{label}]"
            if value:
                return f"[{value}%]"
        if isinstance(progress_info, (int, float)):
            return f"[{int(progress_info)}%]"
        return ""

    def generate_scene_videos(
        self,
        scenes: List[Any],
        output_dir: Path,
        orientation: str = "portrait",
        max_scenes: int = 3,
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
                print_warning(f"Scene {idx+1} AI generation failed/timed out. Space is busy, immediately switching to smart visual fallback.")
                break

        return generated

    @staticmethod
    def _build_cinematic_prompt(subject: str, description: str) -> str:
        """Create a cinematic-quality prompt optimized for Wan2.1."""
        base = description if description else subject
        if not base:
            return "cinematic dramatic scene, 4K ultra HD"

        quality_tags = "cinematic lighting, photorealistic, dramatic atmosphere, ultra detailed, 4K"
        prompt = f"{base}, {quality_tags}"

        if len(prompt) > 200:
            prompt = prompt[:197] + "..."

        return prompt

    def is_available(self) -> bool:
        """Check if the free video generation service is reachable."""
        return self._connect()
