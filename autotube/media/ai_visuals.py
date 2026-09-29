"""AI visual generation using free Pollinations API and Pillow fallbacks."""

import random
import time
from pathlib import Path
from typing import List, Optional
from PIL import Image, ImageDraw, ImageFilter
import requests
from autotube.utils.console import print_error, print_info, print_success, print_warning
from autotube.utils.file_utils import sanitize_filename


class VisualGenerator:
    """Generates AI visual imagery or dynamic high-aesthetic fallbacks."""

    def generate_image(
        self,
        prompt: str,
        output_path: Path,
        width: int = 1080,
        height: int = 1920,
        style: str = "realistic",
        seed: Optional[int] = None,
    ) -> Path:
        """Generate an AI image or fallback graphic with custom style."""
        output_path.parent.mkdir(parents=True, exist_ok=True)

        # Attempt free AI image generation via Pollinations
        success = self._fetch_pollinations_image(
            prompt, output_path, width, height, style=style, seed=seed
        )
        if success and output_path.exists() and output_path.stat().st_size > 5000:
            return output_path

        # Fallback to local Pillow graphic
        return self.create_gradient_fallback(
            prompt, output_path, width=width, height=height
        )

    def fetch_scene_visuals(
        self,
        prompts: List[str],
        output_dir: Path,
        slug: str,
        width: int = 1080,
        height: int = 1920,
        style: str = "ai3d",
        consistent_seed: bool = True,
    ) -> List[Path]:
        """Generate a coherent sequence of 3D AI visuals for all scenes with character consistency."""
        output_dir.mkdir(parents=True, exist_ok=True)
        seed = random.randint(100000, 999999) if consistent_seed else None
        scene_paths: List[Path] = []

        print_info(f"Generating {len(prompts)} 3D AI scene visuals (Style: {style}, Seed: {seed})...")
        for idx, prompt_text in enumerate(prompts):
            if idx > 0:
                time.sleep(2)  # Avoid rate limiting
            img_path = output_dir / f"{slug}_ai3d_scene_{idx+1:02d}.jpg"
            img = self.generate_image(
                prompt=prompt_text,
                output_path=img_path,
                width=width,
                height=height,
                style=style,
                seed=seed,
            )
            scene_paths.append(img)

        return scene_paths

    def _fetch_pollinations_image(
        self,
        prompt: str,
        output_path: Path,
        width: int,
        height: int,
        style: str = "realistic",
        seed: Optional[int] = None,
    ) -> bool:
        if seed is None:
            seed = random.randint(1000, 999999)

        if style.lower() in ("cartoon", "pixar", "3d", "ai3d", "dltoons", "3danimation"):
            style_suffix = "3D Pixar Disney animation style, cute expressive 3D character, Unreal Engine 5 render, cinematic lighting, high detail, masterpiece"
        elif style.lower() in ("anime", "ghibli"):
            style_suffix = "Studio Ghibli modern anime animation style, lush aesthetic, vibrant colorful, beautiful anime digital art"
        elif style.lower() in ("comic", "2d"):
            style_suffix = "funny 2D cartoon illustration, bold comic ink outlines, saturated colors, modern cartoon network aesthetic"
        else:
            style_suffix = "8k resolution, cinematic lighting, photorealistic, dramatic contrast"

        enhanced_prompt = f"{prompt}, {style_suffix}"
        encoded = requests.utils.quote(enhanced_prompt)

        # Sana native aspect ratio handling for fast rendering
        is_vertical = height > width
        gen_w = 768 if is_vertical else 1344
        gen_h = 1344 if is_vertical else 768

        endpoints = [
            f"https://image.pollinations.ai/prompt/{encoded}?model=sana&width={gen_w}&height={gen_h}&nologo=true&seed={seed}",
            f"https://image.pollinations.ai/prompt/{encoded}?width={gen_w}&height={gen_h}&nologo=true&seed={seed}",
        ]

        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }

        for attempt in range(2):
            for url in endpoints:
                try:
                    print_info(f"Generating AI [{style.upper()}] visual for: '{prompt[:45]}...'")
                    resp = requests.get(url, headers=headers, timeout=60)
                    if resp.status_code == 200 and len(resp.content) > 5000 and "image" in resp.headers.get("content-type", ""):
                        with open(output_path, "wb") as f:
                            f.write(resp.content)
                        print_success(f"AI visual saved: {output_path.name}")
                        return True
                except Exception as e:
                    print_warning(f"Pollinations fetch attempt error: {e}")
                    time.sleep(1)
                    continue

        return False

    def create_gradient_fallback(
        self, title: str, output_path: Path, width: int = 1080, height: int = 1920
    ) -> Path:
        """Create a modern dark-themed aesthetic background with glowing accents."""
        print_info(f"Generating local aesthetic background: {output_path.name}...")
        img = Image.new("RGB", (width, height), (15, 20, 32))
        draw = ImageDraw.Draw(img)

        # Generate radial glow circles in background
        num_circles = 5
        colors = [
            (37, 99, 235),  # Electric blue
            (124, 58, 237),  # Vibrant purple
            (219, 39, 119),  # Neon pink
            (16, 185, 129),  # Emerald glow
        ]

        for _ in range(num_circles):
            cx = random.randint(0, width)
            cy = random.randint(0, height)
            radius = random.randint(width // 3, width)
            color = random.choice(colors)
            draw.ellipse(
                [cx - radius, cy - radius, cx + radius, cy + radius],
                fill=color,
            )

        # Blur circles heavily to form smooth ambient gradients
        img = img.filter(ImageFilter.GaussianBlur(radius=120))

        # Add subtle dark vignette overlay
        overlay = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        odraw = ImageDraw.Draw(overlay)
        odraw.rectangle([0, 0, width, height], fill=(10, 15, 26, 140))
        img.paste(overlay, (0, 0), overlay)

        img.save(output_path, "JPEG", quality=92)
        return output_path
