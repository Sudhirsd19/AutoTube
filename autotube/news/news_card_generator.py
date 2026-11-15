"""1080x1080 Breaking News & Infographic Card Generator using Headless Browser & Pillow.
Renders 100% pure Devanagari Hindi typography, cinematic lighting, and brand badges.
"""

import base64
import html
import logging
import os
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any, Dict, Optional
from PIL import Image

from autotube.config import PROJECT_ROOT
from autotube.utils.console import print_error, print_info, print_success, print_warning

logger = logging.getLogger(__name__)

TEMP_DIR = PROJECT_ROOT / "temp"
TEMP_DIR.mkdir(parents=True, exist_ok=True)


class NewsCardGenerator:
    """Renders 1080x1080 social media news cards with studio typography and branding."""

    def __init__(self):
        self.browser_bin = self._find_browser_binary()

    @staticmethod
    def _find_browser_binary() -> Optional[str]:
        """Locate Chrome, Chromium, or Edge binary on Windows or Linux."""
        candidates = [
            # Linux candidates (Oracle VM)
            "/usr/bin/chromium-browser",
            "/usr/bin/chromium",
            "/usr/bin/google-chrome",
            "/usr/bin/google-chrome-stable",
            # Windows candidates
            r"C:\Program Files\Google\Chrome\Application\chrome.exe",
            r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
            r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
        ]

        for path in candidates:
            if os.path.exists(path):
                return path

        for cmd in ["chromium-browser", "chromium", "google-chrome", "chrome", "msedge"]:
            found = shutil.which(cmd)
            if found:
                return found

        return None

    def render_card(
        self,
        image_path: Path,
        content: Dict[str, Any],
        output_path: Optional[Path] = None,
    ) -> Path:
        """Render a 1080x1080 News Card image.
        
        Args:
            image_path: High-resolution source photo path.
            content: Dict containing headlines, tags, speaker, and category.
            output_path: Target path for rendered 1080x1080 JPEG image.
        """
        img_path = Path(image_path)
        if not img_path.exists():
            raise FileNotFoundError(f"Input image not found: {image_path}")

        if not output_path:
            ts = int(time.time())
            output_path = PROJECT_ROOT / "content" / "facebook" / f"news_card_{ts}.jpg"
        
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        category = content.get("card_category", "TECH & AI UPDATE")
        tag_hindi = content.get("card_tag_hindi", "ताज़ा टेक अपडेट")
        line1 = content.get("card_headline_line1", "")
        line2 = content.get("card_headline_line2", "")
        highlight = content.get("card_highlight_text", "")
        speaker = content.get("card_speaker", "")

        # Format line2 with yellow highlight span if requested
        if highlight and highlight in line2:
            formatted_line2 = line2.replace(
                highlight, f'<span class="highlight-yellow">{html.escape(highlight)}</span>'
            )
        else:
            formatted_line2 = f'<span class="highlight-yellow">{html.escape(line2)}</span>'

        # Read and encode image as base64 to avoid cross-origin / file protocol security blocks
        with open(img_path, "rb") as f:
            b64_data = base64.b64encode(f.read()).decode("utf-8")
        mime = "image/png" if img_path.suffix.lower() == ".png" else "image/jpeg"

        html_template = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
  @import url('https://fonts.googleapis.com/css2?family=Poppins:wght@600;700;800&family=Yantramanav:wght@500;700;900&display=swap');
  
  * {{
    margin: 0;
    padding: 0;
    box-sizing: border-box;
  }}
  
  body {{
    width: 1080px;
    height: 1080px;
    overflow: hidden;
    background: #070a0f;
    font-family: 'Yantramanav', 'Nirmala UI', 'Segoe UI', sans-serif;
    position: relative;
  }}
  
  .bg-image {{
    position: absolute;
    top: 0;
    left: 0;
    width: 1080px;
    height: 1080px;
    object-fit: cover;
    object-position: center 15%;
  }}
  
  .top-vignette {{
    position: absolute;
    top: 0;
    left: 0;
    width: 100%;
    height: 220px;
    background: linear-gradient(180deg, rgba(6,9,14,0.85) 0%, rgba(6,9,14,0) 100%);
  }}
  
  .bottom-vignette {{
    position: absolute;
    bottom: 0;
    left: 0;
    width: 100%;
    height: 620px;
    background: linear-gradient(180deg, 
      rgba(7, 10, 15, 0) 0%, 
      rgba(7, 10, 15, 0.45) 25%, 
      rgba(7, 10, 15, 0.94) 65%, 
      rgba(5, 7, 11, 0.99) 100%
    );
  }}
  
  .badge-container {{
    position: absolute;
    top: 48px;
    left: 48px;
    display: flex;
    align-items: center;
    gap: 12px;
    background: rgba(14, 18, 26, 0.88);
    border: 1.5px solid rgba(118, 185, 0, 0.8);
    box-shadow: 0 4px 20px rgba(0, 0, 0, 0.6), 0 0 15px rgba(118, 185, 0, 0.25);
    padding: 10px 24px;
    border-radius: 30px;
  }}
  
  .badge-dot {{
    width: 12px;
    height: 12px;
    border-radius: 50%;
    background: #ff2a2a;
    box-shadow: 0 0 10px #ff2a2a;
  }}
  
  .badge-text {{
    font-family: 'Poppins', sans-serif;
    color: #ffffff;
    font-size: 21px;
    font-weight: 700;
    letter-spacing: 1.2px;
  }}
  
  .badge-divider {{
    color: rgba(255, 255, 255, 0.35);
    font-weight: 300;
  }}
  
  .badge-brand {{
    font-family: 'Poppins', sans-serif;
    color: #76b900;
    font-size: 21px;
    font-weight: 800;
    letter-spacing: 1.5px;
  }}
  
  .content {{
    position: absolute;
    bottom: 0;
    left: 0;
    width: 1080px;
    padding: 0 54px 44px 54px;
    z-index: 10;
  }}
  
  .tag-row {{
    display: flex;
    align-items: center;
    gap: 12px;
    margin-bottom: 14px;
  }}
  
  .tag-bar {{
    width: 6px;
    height: 30px;
    background: #76b900;
    border-radius: 4px;
    box-shadow: 0 0 10px #76b900;
  }}
  
  .tag-label {{
    font-family: 'Yantramanav', 'Nirmala UI', sans-serif;
    font-size: 27px;
    font-weight: 700;
    color: #76b900;
    letter-spacing: 0.5px;
    text-transform: uppercase;
  }}
  
  .headline {{
    font-family: 'Yantramanav', 'Nirmala UI', sans-serif;
    font-size: 52px;
    font-weight: 900;
    line-height: 1.25;
    color: #ffffff;
    margin-bottom: 18px;
    text-shadow: 0 4px 16px rgba(0, 0, 0, 0.95);
  }}
  
  .highlight-yellow {{
    color: #ffd600;
    text-shadow: 0 2px 14px rgba(255, 214, 0, 0.4);
  }}
  
  .speaker-box {{
    display: flex;
    align-items: center;
    gap: 12px;
    margin-bottom: 26px;
  }}
  
  .speaker-name {{
    font-family: 'Yantramanav', 'Nirmala UI', sans-serif;
    font-size: 32px;
    font-weight: 700;
    color: #e2e8f0;
  }}
  
  .footer-row {{
    display: flex;
    justify-content: space-between;
    align-items: center;
    border-top: 1px solid rgba(255, 255, 255, 0.14);
    padding-top: 16px;
  }}
  
  .footer-left {{
    font-family: 'Poppins', sans-serif;
    font-size: 20px;
    font-weight: 600;
    color: #94a3b8;
    letter-spacing: 0.8px;
  }}
  
  .footer-right {{
    font-family: 'Yantramanav', 'Nirmala UI', sans-serif;
    font-size: 24px;
    font-weight: 700;
    color: #76b900;
  }}
</style>
</head>
<body>

  <img class="bg-image" src="data:{mime};base64,{b64_data}" alt="News Photo">
  
  <div class="top-vignette"></div>
  <div class="bottom-vignette"></div>
  
  <div class="badge-container">
    <div class="badge-dot"></div>
    <div class="badge-text">{html.escape(category)}</div>
    <div class="badge-divider">|</div>
    <div class="badge-brand">COSMOCHRONICLE</div>
  </div>
  
  <div class="content">
    <div class="tag-row">
      <div class="tag-bar"></div>
      <div class="tag-label">{html.escape(tag_hindi)}</div>
    </div>
    
    <div class="headline">
      {html.escape(line1)}<br>
      {formatted_line2}
    </div>
    
    <div class="speaker-box">
      <span class="speaker-name">{html.escape(speaker)}</span>
    </div>
    
    <div class="footer-row">
      <div class="footer-left">⚡ CosmoChronicle Insights</div>
      <div class="footer-right">👉 अपनी राय कमेंट में बताएं • Follow Page</div>
    </div>
  </div>

</body>
</html>
"""
        temp_html = TEMP_DIR / f"card_render_{int(time.time()*1000)}.html"
        temp_png = TEMP_DIR / f"card_render_{int(time.time()*1000)}.png"

        try:
            temp_html.write_text(html_template, encoding="utf-8")

            if self.browser_bin:
                print_info(f"Rendering card with browser binary: {self.browser_bin}")
                # Cross-platform browser invocation
                if os.name == "nt":
                    # Windows PowerShell Start-Process
                    cmd = (
                        f'powershell -Command "Start-Process -FilePath \'{self.browser_bin}\' '
                        f'-ArgumentList \'--headless --disable-gpu --screenshot={temp_png} '
                        f'--window-size=1080,1080 --hide-scrollbars file:///{temp_html.as_posix()}\' -Wait"'
                    )
                    subprocess.run(cmd, shell=True, check=True)
                else:
                    # Linux headless Chromium command
                    cmd = [
                        self.browser_bin,
                        "--headless",
                        "--no-sandbox",
                        "--disable-gpu",
                        "--disable-dev-shm-usage",
                        f"--screenshot={temp_png}",
                        "--window-size=1080,1080",
                        "--hide-scrollbars",
                        f"file://{temp_html.resolve().as_posix()}",
                    ]
                    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

                if temp_png.exists():
                    im = Image.open(temp_png).convert("RGB")
                    im.save(output_path, "JPEG", quality=95)
                    print_success(f"🎨 News Card successfully rendered to: {output_path.name}")
                    return output_path

            # Fallback to direct Pillow rendering if browser unavailable
            print_warning("Browser binary not found or failed; falling back to Pillow render.")
            return self._render_pillow_fallback(img_path, content, output_path)

        finally:
            if temp_html.exists():
                try:
                    temp_html.unlink()
                except Exception:
                    pass
            if temp_png.exists():
                try:
                    temp_png.unlink()
                except Exception:
                    pass

    def _render_pillow_fallback(
        self,
        img_path: Path,
        content: Dict[str, Any],
        output_path: Path,
    ) -> Path:
        """Pillow fallback when headless browser is not available."""
        from PIL import ImageDraw, ImageFont

        card_w, card_h = 1080, 1080
        raw = Image.open(img_path).convert("RGBA")
        aspect_target = card_w / card_h
        aspect_img = raw.width / raw.height

        if aspect_img > aspect_target:
            new_h = card_h
            new_w = int(raw.width * (card_h / raw.height))
        else:
            new_w = card_w
            new_h = int(raw.height * (card_w / raw.width))

        resized = raw.resize((new_w, new_h), Image.Resampling.LANCZOS)
        left = (new_w - card_w) // 2
        top = max(0, int((new_h - card_h) * 0.2))
        if top + card_h > new_h:
            top = new_h - card_h

        card = resized.crop((left, top, left + card_w, top + card_h))

        overlay = Image.new("RGBA", (card_w, card_h), (0, 0, 0, 0))
        ov_draw = ImageDraw.Draw(overlay)

        grad_start = 450
        for y in range(grad_start, card_h):
            prog = (y - grad_start) / float(card_h - grad_start)
            alpha = int(248 * (prog ** 1.3))
            ov_draw.line([(0, y), (card_w, y)], fill=(7, 10, 15, min(252, alpha)))

        card = Image.alpha_composite(card, overlay)
        final_im = card.convert("RGB")
        final_im.save(output_path, "JPEG", quality=95)
        return output_path
