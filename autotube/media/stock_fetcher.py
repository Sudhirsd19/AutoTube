"""Smart stock media fetcher with strict semantic relevance verification and multi-tier visual fallback."""

import os
import re
from pathlib import Path
from typing import Any, List, Optional
from PIL import Image, ImageDraw, ImageFilter
import requests

from autotube.config import get_config
from autotube.utils.console import print_error, print_info, print_success, print_warning
from autotube.utils.file_utils import sanitize_filename

STOP_WORDS = {
    "cinematic", "4k", "8k", "hd", "ultra", "slow", "motion", "hyperrealistic",
    "realistic", "high", "detail", "detailed", "quality", "footage", "video",
    "disaster", "sci-fi", "dramatic", "scene", "shot", "breathtaking", "intense",
    "extreme", "visual", "effects", "in", "on", "at", "the", "a", "an", "and",
    "or", "of", "for", "with", "into", "from", "by", "about", "to", "just", "is"
}


class StockFetcher:
    """Fetches royalty-free stock videos and images with strict relevance verification."""

    def __init__(self, pexels_key: Optional[str] = None):
        cfg = get_config()
        self.pexels_key = pexels_key or cfg.pexels_api_key or os.getenv("PEXELS_API_KEY")

    @staticmethod
    def clean_query(query: str) -> str:
        """Strip filler words, numbers, and buzzwords, keeping core subject terms."""
        clean = re.sub(r"[^a-zA-Z\s]", " ", query).lower().strip()
        words = [w for w in clean.split() if len(w) > 1 and w not in STOP_WORDS]
        if not words:
            return clean[:30]
        return " ".join(words[:4])

    @staticmethod
    def is_relevant(query: str, text: str) -> bool:
        """Verify that target text contains at least one core semantic token from query."""
        if not text:
            return False
        clean_target = text.lower().replace("-", " ").replace("_", " ")
        q_tokens = [w for w in re.sub(r"[^a-zA-Z\s]", " ", query).lower().split() if len(w) > 2 and w not in STOP_WORDS]
        if not q_tokens:
            return True
        matches = sum(1 for t in q_tokens if t in clean_target)
        return matches > 0

    def search_and_download_video(
        self,
        query: str,
        output_dir: Path,
        orientation: str = "portrait",  # portrait (9:16) or landscape (16:9)
        require_relevance: bool = True,
    ) -> Optional[Path]:
        """Search Pexels for a video matching query with strict relevance check."""
        if not self.pexels_key:
            return None

        clean_q = self.clean_query(query)
        if not clean_q:
            return None

        headers = {"Authorization": self.pexels_key}
        url = f"https://api.pexels.com/videos/search?query={requests.utils.quote(clean_q)}&orientation={orientation}&per_page=6"

        try:
            print_info(f"Searching stock video for: '{clean_q}' ({orientation})...")
            resp = requests.get(url, headers=headers, timeout=12)
            if resp.status_code != 200:
                return None

            data = resp.json()
            videos = data.get("videos", [])
            if not videos:
                return None

            # Find first relevant video candidate
            matched_video = None
            for v in videos:
                slug = v.get("url", "").split("/video/")[-1].rstrip("/")
                if not require_relevance or self.is_relevant(clean_q, slug):
                    matched_video = v
                    break

            if not matched_video and not require_relevance:
                matched_video = videos[0]

            if not matched_video:
                print_warning(f"No strictly relevant stock video found for '{clean_q}'. Will use visual fallback.")
                return None

            video_files = matched_video.get("video_files", [])
            # Sort by resolution descending
            sorted_files = sorted(
                video_files,
                key=lambda x: (x.get("width", 0) * x.get("height", 0)),
                reverse=True,
            )

            target_file = None
            for vf in sorted_files:
                if vf.get("quality") in ["hd", "sd"] and vf.get("link"):
                    target_file = vf
                    break
            if not target_file and sorted_files:
                target_file = sorted_files[0]

            if not target_file:
                return None

            file_name = f"stock_{sanitize_filename(clean_q)}_{matched_video['id']}.mp4"
            target_path = output_dir / file_name
            if target_path.exists() and target_path.stat().st_size > 0:
                return target_path

            print_info(f"Downloading relevant stock video: {file_name}...")
            with requests.get(target_file["link"], stream=True, timeout=30) as r:
                r.raise_for_status()
                with open(target_path, "wb") as f:
                    for chunk in r.iter_content(chunk_size=65536):
                        f.write(chunk)

            print_success(f"Stock video downloaded: {target_path.name}")
            return target_path

        except Exception as e:
            print_warning(f"Failed to fetch stock video for '{clean_q}': {e}")
            return None

    def search_and_download_photo(
        self,
        query: str,
        output_dir: Path,
        orientation: str = "portrait",
    ) -> Optional[Path]:
        """Search Pexels Photos for a verified, high-resolution still image."""
        if not self.pexels_key:
            return None

        clean_q = self.clean_query(query)
        if not clean_q:
            return None

        headers = {"Authorization": self.pexels_key}
        url = f"https://api.pexels.com/v1/search?query={requests.utils.quote(clean_q)}&orientation={orientation}&per_page=6"

        try:
            print_info(f"Searching high-res stock photo for: '{clean_q}' ({orientation})...")
            resp = requests.get(url, headers=headers, timeout=12)
            if resp.status_code != 200:
                return None

            data = resp.json()
            photos = data.get("photos", [])
            if not photos:
                return None

            # Pick first photo that matches alt text or URL slug
            matched_photo = None
            for p in photos:
                alt = p.get("alt", "")
                slug = p.get("url", "").split("/photo/")[-1].rstrip("/")
                if self.is_relevant(clean_q, alt) or self.is_relevant(clean_q, slug):
                    matched_photo = p
                    break

            if not matched_photo and photos:
                matched_photo = photos[0]

            if not matched_photo:
                return None

            src = matched_photo.get("src", {})
            img_url = src.get("large2x") or src.get("portrait") or src.get("original") or src.get("large")
            if not img_url:
                return None

            file_name = f"photo_{sanitize_filename(clean_q)}_{matched_photo['id']}.jpg"
            target_path = output_dir / file_name
            if target_path.exists() and target_path.stat().st_size > 0:
                return target_path

            print_info(f"Downloading matching stock photo: {file_name}...")
            r = requests.get(img_url, timeout=20)
            if r.status_code == 200 and len(r.content) > 5000:
                with open(target_path, "wb") as f:
                    f.write(r.content)
                print_success(f"Stock photo saved: {target_path.name}")
                return target_path

            return None
        except Exception as e:
            print_warning(f"Failed to fetch stock photo for '{clean_q}': {e}")
            return None

    def search_and_download_wiki_image(
        self,
        query: str,
        output_dir: Path,
    ) -> Optional[Path]:
        """Fetch authentic public domain illustration from Wikipedia / Wikimedia Commons."""
        clean_q = self.clean_query(query)
        if not clean_q:
            return None

        url = f"https://en.wikipedia.org/w/api.php?action=query&titles={requests.utils.quote(clean_q)}&prop=pageimages&format=json&pithumbsize=1080"
        headers = {"User-Agent": "AutoTube/1.0 (https://github.com/Sudhirsd19/AutoTube; contact: info@autotube.ai)"}

        try:
            resp = requests.get(url, headers=headers, timeout=10)
            if resp.status_code != 200:
                return None
            data = resp.json()
            pages = data.get("query", {}).get("pages", {})
            for pid, p in pages.items():
                if "thumbnail" in p and "source" in p["thumbnail"]:
                    thumb_url = p["thumbnail"]["source"]
                    file_name = f"wiki_{sanitize_filename(clean_q)}.jpg"
                    target_path = output_dir / file_name
                    if target_path.exists() and target_path.stat().st_size > 0:
                        return target_path

                    r = requests.get(thumb_url, headers=headers, timeout=15)
                    if r.status_code == 200 and len(r.content) > 3000:
                        with open(target_path, "wb") as f:
                            f.write(r.content)
                        print_success(f"Wikimedia authentic visual saved: {target_path.name}")
                        return target_path
        except Exception:
            pass

        return None

    def create_gradient_fallback(
        self,
        subject: str,
        output_path: Path,
        width: int = 1080,
        height: int = 1920,
    ) -> Path:
        """Create a clean, cinematic aesthetic background if no visual matched."""
        import random
        output_path.parent.mkdir(parents=True, exist_ok=True)
        img = Image.new("RGB", (width, height), (12, 16, 26))
        draw = ImageDraw.Draw(img)

        colors = [
            (29, 78, 216),   # Deep blue
            (109, 40, 217),  # Deep purple
            (190, 24, 93),   # Crimson
            (5, 150, 105),   # Emerald
        ]
        for _ in range(5):
            cx = random.randint(0, width)
            cy = random.randint(0, height)
            radius = random.randint(width // 3, width)
            draw.ellipse([cx - radius, cy - radius, cx + radius, cy + radius], fill=random.choice(colors))

        img = img.filter(ImageFilter.GaussianBlur(radius=120))
        overlay = Image.new("RGBA", (width, height), (0, 0, 0, 140))
        img.paste(overlay, (0, 0), overlay)
        img.save(output_path, "JPEG", quality=90)
        return output_path

    def fetch_best_visual_for_scene(
        self,
        subject: str,
        keywords: Optional[List[str]] = None,
        output_dir: Optional[Path] = None,
        orientation: str = "portrait",
    ) -> Path:
        """Multi-tier visual fetcher: verified video -> verified photo -> wiki image -> fallback."""
        cfg = get_config()
        out_dir = output_dir or cfg.paths.temp_dir
        out_dir.mkdir(parents=True, exist_ok=True)

        candidates = [subject]
        if keywords:
            candidates.extend(keywords)

        # 1. Try Pexels Video with strict relevance
        for q in candidates:
            if not q or not q.strip():
                continue
            vid = self.search_and_download_video(q, output_dir=out_dir, orientation=orientation, require_relevance=True)
            if vid and vid.exists():
                return vid

        # 2. Try Pexels High-Res Photo with verification
        for q in candidates:
            if not q or not q.strip():
                continue
            photo = self.search_and_download_photo(q, output_dir=out_dir, orientation=orientation)
            if photo and photo.exists():
                return photo

        # 3. Try Wikipedia / Wikimedia Commons
        for q in candidates:
            if not q or not q.strip():
                continue
            wiki_img = self.search_and_download_wiki_image(q, output_dir=out_dir)
            if wiki_img and wiki_img.exists():
                return wiki_img

        # 4. Fallback gradient canvas
        slug = sanitize_filename(subject or "scene")
        fallback_path = out_dir / f"fallback_{slug}.jpg"
        return self.create_gradient_fallback(subject, fallback_path, width=1080 if orientation == "portrait" else 1920, height=1920 if orientation == "portrait" else 1080)

    def fetch_scene_visual_assets(
        self,
        scenes: List[Any],
        output_dir: Path,
        orientation: str = "portrait",
    ) -> List[Path]:
        """Fetch a strictly verified visual asset (video or high-res photo) for every single scene."""
        assets: List[Path] = []
        for idx, scene in enumerate(scenes):
            subject = getattr(scene, "visual_subject", "")
            keywords = getattr(scene, "search_keywords", [])
            if not subject and hasattr(scene, "visual_query"):
                subject = getattr(scene, "visual_query", "")

            print_info(f"Acquiring Scene {idx+1}/{len(scenes)} Visual for subject: '{subject}'...")
            asset = self.fetch_best_visual_for_scene(
                subject=subject,
                keywords=keywords,
                output_dir=output_dir,
                orientation=orientation,
            )
            assets.append(asset)

        return assets

    def fetch_multi_scene_videos(
        self,
        queries: List[str],
        output_dir: Path,
        target_count: int = 4,
        orientation: str = "portrait",
    ) -> List[Path]:
        """Legacy helper: Fetch multiple video clips with relevance check."""
        downloaded: List[Path] = []
        for q in queries:
            if len(downloaded) >= target_count:
                break
            clean_q = q.strip()
            if not clean_q:
                continue
            video_path = self.search_and_download_video(
                query=clean_q,
                output_dir=output_dir,
                orientation=orientation,
                require_relevance=True,
            )
            if video_path and video_path.exists() and video_path not in downloaded:
                downloaded.append(video_path)

        return downloaded
