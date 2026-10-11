"""AI image generation through Pollinations with verified native-resolution mode."""

import random
import time
import re
import shutil
from pathlib import Path
from typing import List, Optional
from io import BytesIO
import os
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
        allow_fallback: bool = False,
        require_native_resolution: bool = False,
        allow_photo_fallback: bool = True,
    ) -> Optional[Path]:
        """Generate an AI image or fallback graphic with custom style."""
        output_path.parent.mkdir(parents=True, exist_ok=True)

        # Attempt AI image generation via the configured Pollinations image API
        success = self._fetch_pollinations_image(
            prompt,
            output_path,
            width,
            height,
            style=style,
            seed=seed,
            require_native_resolution=require_native_resolution,
            allow_photo_fallback=allow_photo_fallback,
        )
        if success and output_path.exists() and output_path.stat().st_size > 5000:
            return output_path

        # Only create gradient graphic if explicitly requested
        if allow_fallback:
            return self.create_gradient_fallback(
                prompt, output_path, width=width, height=height
            )
        return None

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
        require_native_resolution: bool = False,
        allow_photo_fallback: bool = True,
    ) -> bool:
        if seed is None:
            seed = random.randint(1000, 999999)

        if style.lower() in ("cartoon", "pixar", "ai3d", "dltoons", "3danimation"):
            style_suffix = "3D Pixar Disney animation style, cute expressive 3D character, Unreal Engine 5 render, cinematic lighting, high detail, masterpiece"
        elif style.lower() in ("3d_cinematic", "cinematic_3d", "realistic_3d", "3d_realistic", "3d", "cinematic"):
            style_suffix = "3D cinematic hyperrealistic CGI render, Unreal Engine 5, Octane Render, 8k resolution, ray tracing, volumetric atmospheric lighting, photorealistic textures, dramatic cinematic depth of field, IMAX cinematography, highly detailed"
        elif style.lower() in ("spiritual_photorealistic", "divine_photorealistic", "gita_4k"):
            style_suffix = (
                "respectful photorealistic Indian spiritual cinema, natural skin and fabric textures, "
                "historically grounded Indian environments, realistic stone, brass, gold and palm-leaf textures, "
                "cinematic natural lighting, detailed composition, true photographic detail, no cartoon, "
                "no anime, no toy-like CGI, no logo, no watermark, no written text"
            )
        elif style.lower() in ("anime", "ghibli"):
            style_suffix = "Studio Ghibli modern anime animation style, lush aesthetic, vibrant colorful, beautiful anime digital art"
        elif style.lower() in ("comic", "2d"):
            style_suffix = "funny 2D cartoon illustration, bold comic ink outlines, saturated colors, modern cartoon network aesthetic"
        else:
            style_suffix = "8k resolution, cinematic lighting, photorealistic, dramatic contrast"

        enhanced_prompt = f"{prompt}, {style_suffix}"
        encoded = requests.utils.quote(enhanced_prompt)

        is_vertical = height > width
        pollinations_key = os.getenv("POLLINATIONS_API_KEY", "").strip()

        if require_native_resolution:
            # Current Pollinations image API requires authentication and documents a
            # maximum 4096-pixel side. Reject unsupported 8K requests instead of
            # silently pretending a smaller image is 8K.
            if width > 4096 or height > 4096:
                print_error(
                    f"Native {width}x{height} image exceeds this provider's 4096-pixel side limit; "
                    "configure an AI super-resolution backend for 8K output."
                )
                return False
            if not pollinations_key:
                print_error(
                    "Native 4K spiritual image mode requires POLLINATIONS_API_KEY; "
                    "stock-photo fallback is disabled for these scenes."
                )
                return False
            models = ("flux", "zimage", "sana")
            endpoints = [
                f"https://gen.pollinations.ai/image/{encoded}?model={model}&width={width}&height={height}&nologo=true&seed={seed}&enhance=true"
                for model in models
            ]
            gen_w, gen_h = width, height
            attempt_count = 1
        else:
            # Fast legacy/default mode retains the original lighter request sizes.
            gen_w = 768 if is_vertical else 1344
            gen_h = 1344 if is_vertical else 768
            endpoints = [
                f"https://image.pollinations.ai/prompt/{encoded}?model=sana&width={gen_w}&height={gen_h}&nologo=true&seed={seed}",
                f"https://image.pollinations.ai/prompt/{encoded}?model=sana&width={gen_w}&height={gen_h}&nologo=true&seed={random.randint(100, 99999)}",
                f"https://image.pollinations.ai/prompt/{encoded}?model=sana&width={gen_w}&height={gen_h}&nologo=true",
            ]
            attempt_count = 2

        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }

        for attempt in range(attempt_count):
            for url in endpoints:
                try:
                    request_headers = dict(headers)
                    if require_native_resolution:
                        request_headers["Authorization"] = f"Bearer {pollinations_key}"
                    print_info(
                        f"Generating AI [{style.upper()}] visual for: '{prompt[:45]}...' "
                        f"({gen_w}x{gen_h})"
                    )
                    resp = requests.get(
                        url,
                        headers=request_headers,
                        timeout=90 if require_native_resolution else 25,
                    )
                    if (
                        resp.status_code == 200
                        and len(resp.content) > 5000
                        and "image" in resp.headers.get("content-type", "")
                    ):
                        if require_native_resolution:
                            try:
                                with Image.open(BytesIO(resp.content)) as source_img:
                                    actual_w, actual_h = source_img.size
                                    actual_ratio = actual_w / actual_h if actual_h else 0
                                    requested_ratio = width / height
                                    if (
                                        actual_w < width
                                        or actual_h < height
                                        or abs(actual_ratio - requested_ratio) > 0.025
                                    ):
                                        print_warning(
                                            f"Rejected undersized/misframed AI image ({actual_w}x{actual_h}); "
                                            f"requested at least {width}x{height}."
                                        )
                                        continue
                                    source_img.convert("RGB").save(
                                        output_path,
                                        format="JPEG",
                                        quality=95,
                                        subsampling=0,
                                    )
                            except Exception as image_err:
                                print_warning(f"Generated image could not be verified: {image_err}")
                                continue
                            print_success(
                                f"Native-resolution AI image saved: {output_path.name} "
                                f"({actual_w}x{actual_h})."
                            )
                            return True

                        with open(output_path, "wb") as f:
                            f.write(resp.content)
                        print_success(f"AI visual saved: {output_path.name}")
                        return True
                    elif resp.status_code in (401, 402, 403):
                        print_warning(
                            f"Pollinations image API returned {resp.status_code}; check API key/credits."
                        )
                        break
                except Exception as e:
                    print_warning(f"Pollinations fetch attempt error: {e}")
                    time.sleep(1)
                    continue

        # Never substitute stock photography for a strict native-resolution AI image.
        if not allow_photo_fallback:
            return False

        # If Pollinations failed or 402 rate-limited, fall back to high-res Pexels Photo
        try:
            from autotube.media.pexels_video import PexelsVideoFetcher
            pv = PexelsVideoFetcher()
            if pv.is_configured():
                # Extract clean English keywords from prompt
                stop_w = {"masterpiece", "detailed", "lighting", "render", "resolution", "cinematic", "photorealistic", "style", "vintage", "highly", "dramatic"}
                words = [w for w in re.findall(r"[a-zA-Z]{3,}", prompt) if w.lower() not in stop_w]
                clean_q = " ".join(words[:3]) if words else prompt[:30]
                if clean_q:
                    photo_path = pv.get_scene_photo(clean_q, orientation="portrait" if is_vertical else "landscape")
                    if photo_path and photo_path.exists() and photo_path.stat().st_size > 10000:
                        shutil.copy(photo_path, output_path)
                        print_success(f"Pexels authentic photo fallback saved: {output_path.name}")
                        return True
        except Exception as pe:
            print_warning(f"Pexels photo fallback notice: {pe}")

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
