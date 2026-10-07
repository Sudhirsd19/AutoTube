"""Free AI Video Generator (Disabled - HuggingFace Spaces Removed).

HuggingFace community spaces (Wan-AI/Wan2.1) have been removed due to
frequent queue timeouts, lack of GPU availability, and high failure rates.
All video generation now uses high-reliability Pexels HD Stock Footage +
Pollinations AI Photorealistic Visuals or Gemini Veo.
"""

from pathlib import Path
from typing import Any, List, Optional
from autotube.utils.console import print_info, print_warning


class FreeVideoGenerator:
    """Legacy generator stub - HuggingFace integration permanently disabled."""

    def __init__(self):
        self._client = None
        self._space_name = None

    def is_available(self) -> bool:
        """HuggingFace spaces are disabled."""
        return False

    def _connect(self) -> bool:
        return False

    def generate_video(
        self,
        prompt: str,
        output_path: Path,
        orientation: str = "portrait",
        timeout_seconds: int = 120,
        seed: int = -1,
    ) -> Optional[Path]:
        print_warning("HuggingFace video generation is disabled. Using verified stock/AI visuals.")
        return None

    def generate_i2v(
        self,
        image_path: Path,
        prompt: str,
        output_path: Path,
        timeout_seconds: int = 300,
        seed: int = -1,
    ) -> Optional[Path]:
        print_warning("HuggingFace I2V generation is disabled. Using verified stock/AI visuals.")
        return None

    def generate_scene_videos(
        self,
        scenes: List[Any],
        output_dir: Path,
        orientation: str = "portrait",
        max_scenes: int = 3,
    ) -> List[Path]:
        return []
