"""High-Impact Visual Hook Engine for Viral YouTube Shorts, Reels & Thumbnails.

Generates explosive curiosity hooks (text + top video banner overlay + thumbnail sync)
that force viewers to stop scrolling, read the hook in 0.5s, and watch the entire video.
"""

import os
import re
import math
from pathlib import Path
from typing import Optional, Tuple, Dict, Any, List
from PIL import Image, ImageDraw, ImageFont, ImageFilter

from autotube.config import get_config, PROJECT_ROOT
from autotube.utils.console import print_info, print_success, print_warning


class VisualHookManager:
    """Orchestrates viral text hooks, video top header banners, and high-CTR thumbnail consistency."""

    def __init__(self):
        self.config = get_config()
        self.temp_dir = self.config.paths.temp_dir
        self.temp_dir.mkdir(parents=True, exist_ok=True)

    def _resolve_font(self, font_size: int, is_devanagari: bool = True) -> ImageFont.FreeTypeFont:
        """Resolve highest-quality bold font supporting Devanagari Hindi or English."""
        universal_candidates = [
            PROJECT_ROOT / "assets" / "fonts" / "Poppins-ExtraBold.ttf",
            PROJECT_ROOT / "assets" / "fonts" / "Poppins-Bold.ttf",
            PROJECT_ROOT / "assets" / "fonts" / "Poppins-Black.ttf",
            Path("C:/Windows/Fonts/Nirmala.ttc"),
        ]

        hindi_candidates = [
            PROJECT_ROOT / "assets" / "fonts" / "NotoSansDevanagari-Bold.ttf",
            Path("C:/Windows/Fonts/mangal.ttf"),
            Path("/usr/share/fonts/truetype/noto/NotoSansDevanagari-Bold.ttf"),
            Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
            Path("/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"),
        ]

        english_candidates = [
            Path("C:/Windows/Fonts/impact.ttf"),
            Path("C:/Windows/Fonts/arialbd.ttf"),
            Path("C:/Windows/Fonts/seguiemj.ttf"),
            Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
            Path("/usr/share/fonts/truetype/freefont/FreeSansBold.ttf"),
        ]

        candidates = universal_candidates + (hindi_candidates + english_candidates if is_devanagari else english_candidates + hindi_candidates)

        for fc in candidates:
            try:
                if isinstance(fc, Path) and fc.exists():
                    return ImageFont.truetype(str(fc), font_size)
                elif isinstance(fc, str):
                    return ImageFont.truetype(fc, font_size)
            except Exception:
                continue

        try:
            return ImageFont.load_default()
        except Exception:
            return None

    def generate_hook_text(
        self,
        title: str,
        script_text: Optional[str] = None,
        language: str = "hi",
        topic_category: str = "auto",
    ) -> str:
        """Generate an irresistible 3-6 word curiosity hook that creates an open loop in the viewer's mind."""
        title_clean = title.strip()
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
                lang_rule = "Devanagari Hindi (शुद्ध देवनागरी हिंदी)" if is_hindi else "Punchy Bold English"

                context_snippet = (script_text[:300] if script_text else title_clean)
                prompt = f"""You are an elite YouTube Shorts/Reels viral retention specialist.
Create an EXPLOSIVE, high-curiosity video hook text that will appear in BOLD at the top of the video and on the thumbnail.
When a viewer scrolling through Shorts reads this in 0.5 seconds, they MUST feel compelled to stop and watch.

Title: "{title_clean}"
Context: "{context_snippet}"
Category: "{topic_category}"

STRICT RULES:
1. LENGTH: Exactly 3 to 6 words ONLY.
2. Must trigger extreme curiosity, sacred mystery, shocking contrast, or an urgent question.
3. LANGUAGE: {lang_rule}.
4. ENDING: Must end with '?' or '!' (or '?!').
5. EXAMPLES:
   - Hindi: "मरने के बाद आत्मा कहाँ जाती है?", "श्री कृष्ण की 1 गुप्त सीख!", "कलयुग का अंत कैसे होगा?", "यमराज का सबसे बड़ा रहस्य!", "वैज्ञानिक भी हैरान रह गए!"
   - English: "WHAT HAPPENS AFTER DEATH?", "THE FORBIDDEN ANCIENT SECRET!", "99% WILL NEVER KNOW THIS!", "WHY SCIENTISTS ARE TERRIFIED!"
6. Output ONLY the hook text. No quotes, no markdown, no explanation."""

                for model_candidate in ["gemini-3.5-flash-lite", "gemini-flash-lite-latest", "gemini-3.1-flash-lite-preview", "gemini-3-flash-preview"]:
                    try:
                        resp = client.models.generate_content(
                            model=model_candidate,
                            contents=prompt,
                        )
                        text = resp.text.strip().replace('"', '').replace("'", "")
                        words = text.split()
                        if 2 <= len(words) <= 8:
                            print_info(f"⚡ AI Visual Hook Generated: '{text}'")
                            return text
                    except Exception:
                        continue
            except Exception as e:
                print_warning(f"AI hook generation skipped ({e}), falling back to heuristic engine.")

        # 2. Semantic Fallback Engine
        title_lower = title_clean.lower()
        if is_hindi:
            if any(k in title_clean for k in ["मृत्यु", "आत्मा", "यमराज", "गरुड़", "मरने"]):
                return "मरने के बाद क्या होता है?"
            elif any(k in title_clean for k in ["कृष्ण", "गीता", "अर्जुन", "महाभारत"]):
                return "श्री कृष्ण की यह बात कभी मत भूलना!"
            elif any(k in title_clean for k in ["कलयुग", "कल्कि", "विनाश", "प्रलय"]):
                return "कलयुग का अंत कब और कैसे?"
            elif any(k in title_clean for k in ["शिव", "महादेव", "रुद्र", "कैलाश"]):
                return "महादेव का सबसे गुप्त रहस्य!"
            elif any(k in title_clean for k in ["हनुमान", "बजरंग", "रामायण"]):
                return "हनुमान जी का अमर रहस्य!"
            elif any(k in title_clean for k in ["मंदिर", "रहस्यमय"]):
                return "इस प्राचीन मंदिर का सच क्या है?"
            elif any(k in title_clean for k in ["एलियन", "alien", "ufo", "अंतरिक्ष"]):
                return "क्या अंतरिक्ष में कोई और भी है?"
            elif any(k in title_clean for k in ["वैज्ञानिक", "साइंस", "खोज"]):
                return "वैज्ञानिक भी देखकर काँप उठे!"
            elif any(k in title_clean for k in ["सच", "झूठ", "रहस्य"]):
                return "यह कड़वा सच छुपाया गया था!"
            else:
                words = [w for w in title_clean.split() if len(w) > 2 and w not in ("और", "का", "की", "के", "में", "से", "पर", "है", "था", "ने")]
                if len(words) >= 3:
                    return f"{' '.join(words[:4])} का सच!"
                return "यह सच जानकर हैरान रह जाओगे!"
        else:
            if any(k in title_lower for k in ["death", "soul", "afterlife", "die"]):
                return "WHAT HAPPENS AFTER YOU DIE?"
            elif any(k in title_lower for k in ["krishna", "gita", "vedic"]):
                return "THE SECRET LESSON YOU MUST KNOW!"
            elif any(k in title_lower for k in ["alien", "ufo", "roswell", "extraterrestrial"]):
                return "THE CLASSIFIED TRUTH IS OUT!"
            elif any(k in title_lower for k in ["black hole", "universe", "space", "cosmic"]):
                return "THE UNIVERSE MIGHT BE A LIE?!"
            elif any(k in title_lower for k in ["secret", "mystery", "forbidden", "hidden"]):
                return "THE TRUTH THEY CONCEALED!"
            else:
                return "99% OF PEOPLE DON'T KNOW THIS!"

    def create_top_hook_banner(
        self,
        hook_text: str,
        video_width: int = 1080,
        video_height: int = 1920,
        topic_category: str = "auto",
        output_path: Optional[Path] = None,
    ) -> Path:
        """Create a large, bold 3D translucent PNG banner with glowing neon outline and complex text shaping.
        
        Designed for placing at the top of vertical shorts (y=150) or landscape videos (y=45).
        """
        from autotube.media.text_shaper import get_shaped_text_dimensions, shape_and_render_line, clean_display_text

        clean_hook = clean_display_text(hook_text)
        is_vertical = (video_height > video_width)
        banner_w = int(video_width * 0.92) if is_vertical else int(video_width * 0.72)
        banner_h = 165 if is_vertical else 120

        if output_path is None:
            slug = re.sub(r"[^\w\-_]", "", clean_hook[:20]).strip() or "hook"
            output_path = self.temp_dir / f"top_hook_banner_{slug}_{banner_w}x{banner_h}.png"

        # Calculate optimal font size to fit within banner width with safety padding
        base_font_size = 62 if is_vertical else 48
        max_text_w = banner_w - 70

        optimal_font_size = 36
        for test_size in range(base_font_size, 32, -2):
            tw, _ = get_shaped_text_dimensions(clean_hook, font_size=test_size)
            if tw <= max_text_w:
                optimal_font_size = test_size
                break

        # Create transparent canvas with generous room for outer glow / border
        canvas = Image.new("RGBA", (banner_w, banner_h), (0, 0, 0, 0))
        draw = ImageDraw.Draw(canvas)

        # Theme color palettes
        is_vedic = (topic_category == "vedic" or "श्री" in clean_hook or "कृष्ण" in clean_hook or "गीता" in clean_hook or "🚩" in hook_text)
        is_space = (topic_category in ("space", "black_hole") or "अंतरिक्ष" in clean_hook or "ब्रह्मांड" in clean_hook)
        is_mystery = (topic_category in ("mystery", "alien", "horror") or "alien" in clean_hook.lower() or "secret" in clean_hook.lower())

        if is_vedic:
            border_glow = (255, 185, 0, 245)      # Radiant Saffron Gold
            accent_color = (255, 230, 0)           # Bright Golden Yellow
            bg_fill = (15, 12, 10, 230)            # Deep Sacred Charcoal
        elif is_space:
            border_glow = (56, 189, 248, 245)      # Cosmic Electric Cyan
            accent_color = (56, 189, 248)          # Cyan Highlight
            bg_fill = (8, 14, 28, 230)             # Midnight Space Blue
        elif is_mystery:
            border_glow = (255, 60, 60, 245)       # High-Alert Red Glow
            accent_color = (255, 230, 0)           # Vibrant Yellow
            bg_fill = (14, 14, 18, 230)            # Stealth Black
        else:
            border_glow = (255, 215, 0, 245)       # Radiant Gold
            accent_color = (255, 230, 0)           # Vibrant Yellow
            bg_fill = (14, 12, 14, 230)            # Deep Translucent Carbon

        # 1. Draw 3D Translucent Glassmorphism Rounded Pill Box
        pill_rect = [6, 6, banner_w - 6, banner_h - 6]
        radius = 28 if is_vertical else 20

        # Ambient drop shadow underneath pill
        draw.rounded_rectangle([pill_rect[0] - 3, pill_rect[1] - 3, pill_rect[2] + 3, pill_rect[3] + 3], radius=radius + 3, fill=(0, 0, 0, 110))
        # Inner dark frosted glass
        draw.rounded_rectangle(pill_rect, radius=radius, fill=bg_fill, outline=border_glow, width=4)
        # Subtle 3D upper inner highlight rim (glass gloss reflection)
        highlight_rim = (255, 220, 140, 140) if is_vedic else (border_glow[0], border_glow[1], border_glow[2], 120)
        draw.line([(pill_rect[0] + radius, pill_rect[1] + 3), (pill_rect[2] - radius, pill_rect[1] + 3)], fill=highlight_rim, width=2)

        # 2. Render 3D Shaped Text using HarfBuzz + FreeType engine
        text_img, tw, th = shape_and_render_line(
            text=clean_hook,
            font_size=optimal_font_size,
            fill_color=accent_color,
            stroke_color=(0, 0, 0),
            stroke_px=5,
            shadow_color=(0, 0, 0),
            shadow_offset=6,
        )

        tx = (banner_w - text_img.width) // 2
        ty = (banner_h - text_img.height) // 2
        canvas.paste(text_img, (tx, ty), text_img)

        output_path.parent.mkdir(parents=True, exist_ok=True)
        canvas.save(output_path, "PNG")
        print_success(f"✅ Big Bold 3D Translucent Top Banner Created ({banner_w}x{banner_h}): '{clean_hook}' -> {output_path.name}")
        return output_path

