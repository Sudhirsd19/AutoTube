"""High-CTR YouTube Viral Thumbnail Generator using Pillow and AI Hook Optimization."""

import os
import re
import math
import shutil
import textwrap
from pathlib import Path
from typing import Optional, Tuple, List, Dict, Any
from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont

from autotube.config import get_config, PROJECT_ROOT
from autotube.utils.console import print_info, print_success, print_warning, print_error
from autotube.utils.ffmpeg_helper import run_ffmpeg


class ThumbnailGenerator:
    """Creates click-compelling, high-CTR YouTube thumbnails with psychological curiosity hooks."""

    def __init__(self, width: int = 1280, height: int = 720):
        self.width = width
        self.height = height
        self.config = get_config()

    def _resolve_fonts(self, font_size: int, is_devanagari: bool = False) -> Tuple[ImageFont.FreeTypeFont, ImageFont.FreeTypeFont]:
        """Resolve primary hook font and badge font supporting Devanagari Hindi and English."""
        # Candidates for Devanagari
        hindi_candidates = [
            PROJECT_ROOT / "assets" / "fonts" / "NotoSansDevanagari-Bold.ttf",
            Path("C:/Windows/Fonts/Nirmala.ttc"),
            Path("C:/Windows/Fonts/mangal.ttf"),
            Path("/usr/share/fonts/truetype/noto/NotoSansDevanagari-Bold.ttf"),
            Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
        ]

        # Candidates for English / Impact
        english_candidates = [
            Path("C:/Windows/Fonts/impact.ttf"),
            Path("C:/Windows/Fonts/arialbd.ttf"),
            PROJECT_ROOT / "assets" / "fonts" / "NotoSansDevanagari-Bold.ttf",
            Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
            Path("/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"),
            Path("/usr/share/fonts/truetype/freefont/FreeSansBold.ttf"),
        ]

        candidates = hindi_candidates + english_candidates if is_devanagari else english_candidates + hindi_candidates

        main_font = None
        for fc in candidates:
            try:
                if isinstance(fc, Path) and fc.exists():
                    main_font = ImageFont.truetype(str(fc), font_size)
                    break
                elif isinstance(fc, str):
                    main_font = ImageFont.truetype(fc, font_size)
                    break
            except Exception:
                continue

        if not main_font:
            try:
                main_font = ImageFont.load_default()
            except Exception:
                main_font = None

        badge_font = None
        badge_size = max(18, int(font_size * 0.38))
        for fc in candidates:
            try:
                if isinstance(fc, Path) and fc.exists():
                    badge_font = ImageFont.truetype(str(fc), badge_size)
                    break
                elif isinstance(fc, str):
                    badge_font = ImageFont.truetype(fc, badge_size)
                    break
            except Exception:
                continue

        if not badge_font:
            try:
                badge_font = ImageFont.load_default()
            except Exception:
                badge_font = main_font

        return main_font, badge_font

    def extract_punchy_hook_text(
        self,
        title: str,
        script_text: Optional[str] = None,
        language: str = "hi",
    ) -> str:
        """Extract or generate a 2-4 word explosive curiosity hook for maximum thumbnail CTR."""
        title_clean = title.strip()
        # Remove hashtags and bracketed tags like #Shorts, (Part 1)
        title_clean = re.sub(r"#\w+", "", title_clean).strip()
        title_clean = re.sub(r"\(.*?\)", "", title_clean).strip()
        title_clean = re.sub(r"\[.*?\]", "", title_clean).strip()

        is_hindi = language.lower() in ("hi", "hindi") or any("\u0900" <= c <= "\u097F" for c in title_clean)

        # 1. Try Gemini AI Hook Optimization if API Key is configured
        gemini_key = self.config.gemini_api_key or os.getenv("GEMINI_API_KEY")
        if gemini_key:
            try:
                from google import genai
                client = genai.Client(api_key=gemini_key)
                lang_instruction = "Devanagari Hindi (शुद्ध देवनागरी हिंदी)" if is_hindi else "Bold punchy English"

                context_snippet = (script_text[:250] if script_text else title_clean)
                prompt = f"""You are a master YouTube thumbnail CTR strategist (like MrBeast).
Analyze this video title and context:
Title: "{title_clean}"
Context: "{context_snippet}"

Generate an EXPLOSIVE, high-curiosity YouTube thumbnail text hook.
STRICT RULES:
1. LENGTH: Exactly 2 to 4 words ONLY (Absolute maximum 4 words).
2. MUST TRIGGER EXTREME SHOCK, CURIOSITY, OR IMPOSSIBLE QUESTION.
3. LANGUAGE: {lang_instruction}.
4. DO NOT repeat the whole title. Focus on the core mystery or shocking contrast.
5. Examples of winning hooks:
   - Hindi: "यह सच छुपाया गया?!", "1000 साल पुराना रहस्य!", "वैज्ञानिक भी हैरान!", "महा-विनाशकारी अस्त्र!", "सूर्य को निगल लिया?!"
   - English: "THE FORBIDDEN TRUTH!", "99% DON'T KNOW!", "SCIENTISTS SHOCKED!", "IMPOSSIBLE DISCOVERY!"
6. Return ONLY the 2-4 words hook. NO quotes, NO punctuation explanation, NO filler."""

                for model_candidate in ["gemini-2.5-flash", "gemini-3.5-flash-lite", "gemini-1.5-flash"]:
                    try:
                        resp = client.models.generate_content(
                            model=model_candidate,
                            contents=prompt,
                        )
                        text = resp.text.strip().replace('"', '').replace("'", "")
                        # Verify word count <= 5
                        words = text.split()
                        if 1 <= len(words) <= 5:
                            return text.upper() if not is_hindi else text
                    except Exception:
                        continue
            except Exception as e:
                print_warning(f"Gemini thumbnail hook generation skipped: {e}")

        # 2. Heuristic fallback based on semantic keywords
        title_lower = title_clean.lower()
        if is_hindi:
            if "श्राप" in title_clean or "शाप" in title_clean:
                return "भयानक श्राप?!"
            elif "हनुमान" in title_clean:
                return "हनुमान जी का रहस्य!"
            elif "शिव" in title_clean or "महादेव" in title_clean or "रुद्र" in title_clean:
                return "महादेव का सच!"
            elif "कृष्ण" in title_clean or "महाभारत" in title_clean:
                return "महाभारत का सच!"
            elif "रामायण" in title_clean or "राम" in title_clean:
                return "रामायण का गुप्त रहस्य!"
            elif "मंदिर" in title_clean or "मंदिरों" in title_clean:
                return "मंदिर का रहस्य!"
            elif "एलियन" in title_clean or "alien" in title_lower:
                return "एलियन का सच सामने?!"
            elif "ब्लैक होल" in title_clean or "black hole" in title_lower:
                return "ब्रह्मांड का सबसे बड़ा रहस्य!"
            elif "वैज्ञानिक" in title_clean or "साइंस" in title_lower:
                return "वैज्ञानिक भी हैरान!"
            elif "जीव" in title_clean or "प्राणी" in title_clean:
                return "अमर जीव का रहस्य!"
            else:
                # Extract first 3-4 impactful words
                words = [w for w in title_clean.split() if len(w) > 2 and w not in ("और", "का", "की", "के", "में", "से", "पर", "है", "था", "ने")]
                if words:
                    return " ".join(words[:3]) + "!"
                return "यह सच छुपाया गया?!"
        else:
            if "alien" in title_lower or "ufo" in title_lower or "roswell" in title_lower:
                return "CLASSIFIED ALIEN TRUTH!"
            elif "black hole" in title_lower or "galaxy" in title_lower or "universe" in title_lower:
                return "UNIVERSE BROKEN?!"
            elif "immortal" in title_lower or "reset" in title_lower or "creature" in title_lower:
                return "CANNOT DIE?!"
            elif "secret" in title_lower or "forbidden" in title_lower:
                return "FORBIDDEN TRUTH!"
            elif "science" in title_lower or "scientist" in title_lower:
                return "SCIENTISTS SHOCKED!"
            else:
                words = [w for w in title_clean.split() if len(w) > 3 and w.lower() not in ("what", "when", "that", "this", "from", "with", "have", "been")]
                if words:
                    return (" ".join(words[:3]) + "!").upper()
                return "99% DON'T KNOW!"

    def extract_best_video_frame(self, video_path: Path, output_frame_path: Path) -> Optional[Path]:
        """Extract a high-contrast, visually engaging keyframe from a video file."""
        if not video_path.exists():
            return None

        output_frame_path.parent.mkdir(parents=True, exist_ok=True)
        # Try extracting candidate frame at 2.5s (past opening black frames / intro)
        timestamps = ["00:00:02.500", "00:00:01.500", "00:00:04.000", "00:00:00.500"]
        for ts in timestamps:
            try:
                run_ffmpeg([
                    "-ss", ts,
                    "-i", str(video_path),
                    "-vframes", "1",
                    "-q:v", "1",
                    "-y",
                    str(output_frame_path),
                ])
                if output_frame_path.exists() and output_frame_path.stat().st_size > 15000:
                    return output_frame_path
            except Exception:
                continue

        return output_frame_path if output_frame_path.exists() else None

    def generate_high_ctr_thumbnail(
        self,
        title: str,
        output_path: Path,
        script_text: Optional[str] = None,
        video_path: Optional[Path] = None,
        background_image: Optional[Path] = None,
        custom_hook_text: Optional[str] = None,
        language: str = "hi",
        topic_category: str = "auto",
        badge_text: Optional[str] = None,
        highlight_color: Tuple[int, int, int] = (255, 230, 0),  # Radiant Yellow
        text_color: Tuple[int, int, int] = (255, 255, 255),       # Crisp White
    ) -> Path:
        """Create a high-impact 1280x720 YouTube thumbnail that maximizes click-through rate (CTR)."""
        output_path.parent.mkdir(parents=True, exist_ok=True)
        print_info(f"🎨 Generating High-CTR Thumbnail for: '{title}'...")

        is_devanagari = (
            language.lower() in ("hi", "hindi")
            or any("\u0900" <= c <= "\u097F" for c in title)
            or (custom_hook_text and any("\u0900" <= c <= "\u097F" for c in custom_hook_text))
        )

        # 1. Acquire Base Image
        img = None
        base_img_path = None

        if background_image and background_image.exists():
            if background_image.suffix.lower() in [".mp4", ".mov", ".mkv", ".webm", ".avi"]:
                extracted = output_path.parent / f"{output_path.stem}_frame.jpg"
                base_img_path = self.extract_best_video_frame(background_image, extracted)
            else:
                base_img_path = background_image
        elif video_path and video_path.exists():
            extracted = output_path.parent / f"{output_path.stem}_frame.jpg"
            base_img_path = self.extract_best_video_frame(video_path, extracted)

        if base_img_path and base_img_path.exists():
            try:
                raw_img = Image.open(base_img_path).convert("RGB")
                # Scale and center-crop to 16:9 1280x720
                img = self._fit_and_crop(raw_img, self.width, self.height)
                # Apply Hollywood thumbnail color grading
                img = ImageEnhance.Contrast(img).enhance(1.32)
                img = ImageEnhance.Color(img).enhance(1.42)
                img = ImageEnhance.Sharpness(img).enhance(1.25)
            except Exception as e:
                print_warning(f"Could not load thumbnail base image: {e}")
                img = None

        # Fallback to AI Visual or Dramatic Canvas if no frame acquired
        if img is None:
            img = self._create_cinematic_canvas(title=title, topic_category=topic_category)

        # 2. Apply Cinematic Vignette & Bottom/Left Dark Contrast Gradient for Text
        img = self._apply_contrast_overlay(img)

        # 3. Determine Hook Text
        hook_text = (custom_hook_text or self.extract_punchy_hook_text(title, script_text=script_text, language=language)).strip()
        print_info(f"   🔥 Thumbnail Hook Text: '{hook_text}'")

        # 4. Resolve Typography
        # Decide font size based on text length
        text_len = len(hook_text)
        if text_len <= 12:
            font_size = 94
        elif text_len <= 22:
            font_size = 82
        elif text_len <= 32:
            font_size = 72
        else:
            font_size = 62

        main_font, badge_font = self._resolve_fonts(font_size=font_size, is_devanagari=is_devanagari)

        # 5. Render Badge (e.g. 🚩 सत्य or ⚠️ CLASSIFIED)
        draw = ImageDraw.Draw(img)
        effective_badge = badge_text
        if not effective_badge or effective_badge == "auto":
            if topic_category == "vedic" or "गिता" in title or "रामायण" in title or "वेद" in title:
                effective_badge = "🚩 सनातन सत्य"
            elif topic_category in ("alien", "mystery") or "alien" in title.lower() or "secret" in title.lower() or "रहस्य" in title:
                effective_badge = "⚠️ 100% REVEALED"
            elif topic_category == "space" or "अंतरिक्ष" in title or "ब्रह्मांड" in title:
                effective_badge = "🚀 COSMIC MYSTERY"
            else:
                effective_badge = "⚡ MUST WATCH"

        self._render_badge(draw, effective_badge, badge_font, is_vedic=(topic_category == "vedic" or "🚩" in effective_badge))

        # 6. Render Bold Multi-Layer 3D Hook Text
        self._render_bold_hook_text(
            draw=draw,
            text=hook_text,
            font=main_font,
            font_size=font_size,
            highlight_color=highlight_color,
            text_color=text_color,
            is_devanagari=is_devanagari,
        )

        # 7. Apply subtle cinematic frame border (High-CTR style)
        self._apply_border(draw)

        # Save high quality JPEG
        img.save(output_path, "JPEG", quality=95, optimize=True)
        print_success(f"✅ High-CTR Thumbnail saved: {output_path.name}")
        return output_path

    def _fit_and_crop(self, img: Image.Image, target_w: int, target_h: int) -> Image.Image:
        """Scale and center-crop any image (portrait or landscape) to target dimensions."""
        img_w, img_h = img.size
        target_aspect = target_w / target_h
        img_aspect = img_w / img_h

        if img_aspect > target_aspect:
            # Image is wider: fit height and crop width
            new_h = target_h
            new_w = int(new_h * img_aspect)
        else:
            # Image is taller: fit width and crop height
            new_w = target_w
            new_h = int(new_w / img_aspect)

        resized = img.resize((new_w, new_h), Image.Resampling.LANCZOS)
        left = max(0, (new_w - target_w) // 2)
        top = max(0, (new_h - target_h) // 2)
        return resized.crop((left, top, left + target_w, top + target_h))

    def _create_cinematic_canvas(self, title: str, topic_category: str) -> Image.Image:
        """Create a deep rich cinematic atmospheric gradient canvas."""
        canvas = Image.new("RGB", (self.width, self.height), (10, 14, 26))
        draw = ImageDraw.Draw(canvas)

        # Primary orb glow color
        if topic_category == "vedic" or "gita" in title.lower() or "vedic" in title.lower():
            glow_color = (255, 120, 20)  # Sacred Saffron Fire
            ambient_color = (50, 20, 8)
        elif topic_category in ("space", "black_hole") or "space" in title.lower():
            glow_color = (30, 110, 240)   # Cosmic Blue Singularity
            ambient_color = (8, 16, 40)
        else:
            glow_color = (220, 20, 60)    # Intense Crimson Warning
            ambient_color = (40, 10, 16)

        # Base ambient gradient
        draw.rectangle([0, 0, self.width, self.height], fill=ambient_color)

        # Right-side glowing orb (giving dramatic cinematic lighting behind potential subject)
        orb_x = int(self.width * 0.72)
        orb_y = int(self.height * 0.45)
        orb_r = 380
        draw.ellipse([orb_x - orb_r, orb_y - orb_r, orb_x + orb_r, orb_y + orb_r], fill=glow_color)

        # Heavy blur for atmospheric volumetric lighting
        canvas = canvas.filter(ImageFilter.GaussianBlur(130))
        return canvas

    def _apply_contrast_overlay(self, img: Image.Image) -> Image.Image:
        """Apply directional dark gradient overlay to ensure text is 100% readable."""
        overlay = Image.new("RGBA", (self.width, self.height), (0, 0, 0, 0))
        odraw = ImageDraw.Draw(overlay)

        # Left-to-right dark gradient for text background (strong on left, transparent on right)
        grad_width = int(self.width * 0.75)
        for x in range(grad_width):
            alpha = int(225 * math.pow(1 - (x / grad_width), 1.2))
            odraw.line([(x, 0), (x, self.height)], fill=(0, 0, 0, alpha))

        # Bottom subtle darkening for global contrast
        bottom_h = int(self.height * 0.40)
        for y_offset in range(bottom_h):
            y = self.height - bottom_h + y_offset
            alpha = int(140 * (y_offset / bottom_h))
            odraw.line([(0, y), (self.width, y)], fill=(0, 0, 0, alpha))

        img.paste(overlay, (0, 0), overlay)
        return img

    def _render_badge(
        self,
        draw: ImageDraw.ImageDraw,
        badge_text: str,
        font: ImageFont.FreeTypeFont,
        is_vedic: bool = False,
    ):
        """Render high-CTR badge in the top-left corner."""
        if not badge_text:
            return

        x = 55
        y = 48
        pad_x = 22
        pad_y = 10

        try:
            bbox = font.getbbox(badge_text)
            text_w = bbox[2] - bbox[0]
            text_h = bbox[3] - bbox[1]
        except Exception:
            text_w = len(badge_text) * 16
            text_h = 24

        badge_rect = [x, y, x + text_w + (pad_x * 2), y + text_h + (pad_y * 2)]

        bg_color = (230, 81, 0) if is_vedic else (220, 20, 60)       # Saffron or Crimson
        border_color = (255, 215, 0) if is_vedic else (255, 80, 80) # Gold or Bright Red

        # Badge pill background
        draw.rounded_rectangle(badge_rect, radius=12, fill=bg_color, outline=border_color, width=3)
        # Badge text
        draw.text((x + pad_x, y + pad_y - 2), badge_text, font=font, fill=(255, 255, 255))

    def _render_bold_hook_text(
        self,
        draw: ImageDraw.ImageDraw,
        text: str,
        font: ImageFont.FreeTypeFont,
        font_size: int,
        highlight_color: Tuple[int, int, int],
        text_color: Tuple[int, int, int],
        is_devanagari: bool = False,
    ):
        """Render 2-tone massive 3D text with thick black outline and drop shadow."""
        words = text.split()
        if len(words) <= 2:
            lines = [text]
        elif len(words) <= 4:
            # 2 words per line
            lines = [" ".join(words[:2]), " ".join(words[2:])]
        else:
            # Textwrap for longer hooks (max 2 lines)
            wrapped = textwrap.wrap(text, width=14)
            lines = wrapped[:2]

        line_spacing = int(font_size * 0.28)
        total_text_height = (len(lines) * font_size) + ((len(lines) - 1) * line_spacing)

        # Position text on left half, centered vertically
        x_offset = 60
        y_offset = (self.height - total_text_height) // 2 + 35

        for idx, line in enumerate(lines):
            y = y_offset + idx * (font_size + line_spacing)
            line_color = highlight_color if idx == 0 else text_color

            # 1. 3D Drop Shadow (soft offset)
            shadow_offset = 6
            for s_dx in range(2, shadow_offset + 1):
                for s_dy in range(2, shadow_offset + 1):
                    draw.text((x_offset + s_dx, y + s_dy), line, font=font, fill=(0, 0, 0))

            # 2. Heavy Outlines (stroke_width emulation for maximum contrast)
            stroke_width = max(4, int(font_size * 0.08))
            for dx in range(-stroke_width, stroke_width + 1):
                for dy in range(-stroke_width, stroke_width + 1):
                    if (dx * dx + dy * dy) <= (stroke_width * stroke_width) and (dx != 0 or dy != 0):
                        draw.text((x_offset + dx, y + dy), line, font=font, fill=(0, 0, 0))

            # 3. Main Vibrant Text
            draw.text((x_offset, y), line, font=font, fill=line_color)

    def _apply_border(self, draw: ImageDraw.ImageDraw):
        """Draw subtle high-CTR framing accent on the thumbnail edges."""
        # Top-left accent corner / neon border
        border_color = (255, 230, 0, 180)  # Bright Gold
        draw.line([(0, 0), (self.width, 0)], fill=(255, 215, 0), width=4)
        draw.line([(0, self.height - 1), (self.width, self.height - 1)], fill=(255, 215, 0), width=4)

    def generate_thumbnail(
        self,
        title: str,
        output_path: Path,
        background_image: Optional[Path] = None,
        highlight_color: Tuple[int, int, int] = (255, 230, 0),
        text_color: Tuple[int, int, int] = (255, 255, 255),
    ) -> Path:
        """Backward-compatible wrapper routing legacy calls to the new High-CTR engine."""
        return self.generate_high_ctr_thumbnail(
            title=title,
            output_path=output_path,
            background_image=background_image,
            highlight_color=highlight_color,
            text_color=text_color,
        )
