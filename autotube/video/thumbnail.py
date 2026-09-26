"""High-CTR YouTube Thumbnail Generator using Pillow."""

import textwrap
from pathlib import Path
from typing import Optional, Tuple
from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont
from autotube.utils.console import print_info, print_success


class ThumbnailGenerator:
    """Creates eye-catching YouTube thumbnails with bold text overlays."""

    def __init__(self, width: int = 1280, height: int = 720):
        self.width = width
        self.height = height

    def generate_thumbnail(
        self,
        title: str,
        output_path: Path,
        background_image: Optional[Path] = None,
        highlight_color: Tuple[int, int, int] = (255, 220, 0),  # Bright Yellow
        text_color: Tuple[int, int, int] = (255, 255, 255),
    ) -> Path:
        """Create a high-impact 1280x720 YouTube thumbnail."""
        output_path.parent.mkdir(parents=True, exist_ok=True)
        print_info(f"Generating high-CTR thumbnail for: '{title}'...")

        # Base Image
        if background_image and background_image.exists():
            img = Image.open(background_image).convert("RGB")
            img = img.resize((self.width, self.height), Image.Resampling.LANCZOS)
            # Increase contrast and saturation slightly
            img = ImageEnhance.Contrast(img).enhance(1.2)
            img = ImageEnhance.Color(img).enhance(1.25)
        else:
            # Gradient canvas
            img = Image.new("RGB", (self.width, self.height), (15, 23, 42))
            draw = ImageDraw.Draw(img)
            draw.rectangle(
                [0, 0, self.width, self.height],
                fill=(18, 24, 38),
            )
            # Glow orb
            draw.ellipse(
                [self.width // 2, -100, self.width + 300, self.height + 200],
                fill=(220, 38, 38),  # Dramatic crimson
            )
            img = img.filter(ImageFilter.GaussianBlur(100))

        # Add dark gradient overlay for text legibility
        overlay = Image.new("RGBA", (self.width, self.height), (0, 0, 0, 0))
        odraw = ImageDraw.Draw(overlay)
        # Left-to-right dark gradient
        for x in range(int(self.width * 0.7)):
            alpha = int(220 * (1 - (x / (self.width * 0.7))))
            odraw.line([(x, 0), (x, self.height)], fill=(0, 0, 0, alpha))
        img.paste(overlay, (0, 0), overlay)

        # Draw Bold High-Impact Text
        draw = ImageDraw.Draw(img)
        clean_title = title.upper()
        # Truncate or simplify title for thumbnail (max 4-5 words)
        words = clean_title.split()
        short_title = " ".join(words[:5]) if len(words) > 5 else clean_title

        wrapped_lines = textwrap.wrap(short_title, width=16)

        # Load font or fallback (Linux & Windows compatible)
        font_size = 76
        font = None
        font_candidates = [
            "arialbd.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
            "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
            "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf",
            "impact.ttf",
        ]
        for fc in font_candidates:
            try:
                font = ImageFont.truetype(fc, font_size)
                break
            except Exception:
                pass
        if not font:
            font = ImageFont.load_default()

        # Compute text block position
        y_offset = (self.height - (len(wrapped_lines) * (font_size + 15))) // 2
        x_offset = 60

        for idx, line in enumerate(wrapped_lines):
            line_color = highlight_color if idx == 0 else text_color
            y = y_offset + idx * (font_size + 18)

            # Heavy outline / drop shadow
            for dx in range(-4, 5):
                for dy in range(-4, 5):
                    if dx != 0 or dy != 0:
                        draw.text((x_offset + dx, y + dy), line, font=font, fill=(0, 0, 0))

            # Main text
            draw.text((x_offset, y), line, font=font, fill=line_color)

        img.save(output_path, "JPEG", quality=95)
        print_success(f"Thumbnail saved: {output_path.name}")
        return output_path
