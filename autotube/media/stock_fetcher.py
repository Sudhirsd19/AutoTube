"""Smart stock media fetcher with strict semantic relevance verification, deduplication, and multi-tier visual fallback."""

import json
import os
import random
import re
from pathlib import Path
from typing import Any, List, Optional, Set
from PIL import Image, ImageDraw, ImageFilter
import requests

from autotube.config import PROJECT_ROOT, get_config
from autotube.utils.console import print_error, print_info, print_success, print_warning
from autotube.utils.file_utils import sanitize_filename

# Persistent file tracking which media IDs have been used across all videos
USED_MEDIA_HISTORY = PROJECT_ROOT / "config" / "used_media_history.json"

STOP_WORDS = {
    "cinematic", "4k", "8k", "hd", "ultra", "slow", "motion", "hyperrealistic",
    "realistic", "high", "detail", "detailed", "quality", "footage", "video",
    "disaster", "sci-fi", "dramatic", "scene", "shot", "breathtaking", "intense",
    "extreme", "visual", "effects", "in", "on", "at", "the", "a", "an", "and",
    "or", "of", "for", "with", "into", "from", "by", "about", "to", "just", "is"
}

# Semantic archetype mapping to guarantee real motion video footage matching spoken words
VOCAL_THEME_VIDEO_QUERIES = [
    # UFO, Saucer, Roswell, Crash, Mothership
    (r"\b(ufo|saucer|roswell|flying disc|alien ship|crash|mothership|debris)\b", [
        "ufo flying in sky", "flying saucer", "military radar", "alien aircraft", "night sky mystery"
    ]),
    # Alien, Airl, Extraterrestrial, Non-human, Gray alien
    (r"\b(alien|airl|extraterrestrial|non human|gray alien|entity|creature)\b", [
        "alien silhouette", "mysterious silhouette in dark", "creepy shadows", "sci fi creature"
    ]),
    # Newspaper, Headline, Records, Proof, Document, Affidavits
    (r"\b(newspaper|headline|press|article|record|paper|daily|memo|affidavit|proof|file|files)\b", [
        "vintage newspaper", "newspaper printing press", "reading newspaper", "retro television static", "classified documents"
    ]),
    # Interrogation, Interview, Matilda, Room, Military Base, Laboratory
    (r"\b(interrogation|interview|matilda|nurse|room|secret base|area 51|underground|military|facility)\b", [
        "interrogation room", "secret laboratory", "military base", "classified documents", "dark room light"
    ]),
    # Telepathy, Mind, Brain, Thought, Memory, EEG, Mental
    (r"\b(telepathic|telepathy|brain|mind|thought|memory|eeg|mental|consciousness)\b", [
        "human brain glowing", "neural network animation", "matrix code digital", "telepathy energy wave"
    ]),
    # IS-BE, Soul, Spirit, Immortal, Afterlife, Astral, Reincarnation
    (r"\b(is-be|soul|spirit|immortal|afterlife|body|reincarnation|astral)\b", [
        "glowing human silhouette", "astral universe", "ethereal light energy", "soul rising light"
    ]),
    # Prison Planet, Trap, Cage, Grid, Electronic screen, Barrier
    (r"\b(prison planet|prison|trap|cage|grid|barrier|amnesia|electric)\b", [
        "prison bars dark", "matrix digital code", "cyber electric grid", "foggy mysterious tunnel"
    ]),
    # Pyramid, Egypt, Giza, Sphinx, Ancient, Ruins
    (r"\b(pyramid|egypt|giza|sphinx|pharaoh|ancient civilization|ruins)\b", [
        "ancient pyramid desert", "egyptian giza aerial", "ancient temple ruins", "desert sand storm"
    ]),
    # Space, Universe, Galaxy, Cosmos, Stars, Planet, Earth
    (r"\b(space|universe|galaxy|cosmos|stars|planet|earth|orbit|black hole)\b", [
        "space galaxy stars", "earth rotating in space", "cosmic nebula colorful", "black hole void"
    ]),
    # Psychology, Manipulation, Hypnosis, Dark Mind
    (r"\b(psychology|dark psychology|manipulation|eyes|hypnosis|subconscious)\b", [
        "eye pupil dilating macro", "dark shadow walking", "pendulum swinging", "mysterious stare"
    ]),
    # Ocean, Mariana, Deep Sea, Trench, Abyss
    (r"\b(ocean|mariana|deep sea|underwater|trench|abyss|water)\b", [
        "deep underwater dark", "abyssal ocean waves", "submarine sonar ocean", "dark water bubbles"
    ]),
]

UNIVERSAL_MOTION_FALLBACKS = [
    "cinematic mystery lights",
    "space galaxy stars",
    "classified archive documents",
    "retro television static",
    "foggy dark corridor",
    "military radar screen",
    "alien silhouette",
]


class StockFetcher:
    """Fetches royalty-free stock videos and images with strict relevance verification and deduplication."""

    def __init__(self, pexels_key: Optional[str] = None):
        cfg = get_config()
        self.pexels_key = pexels_key or cfg.pexels_api_key or os.getenv("PEXELS_API_KEY")
        self.pixabay_key = cfg.pixabay_api_key or os.getenv("PIXABAY_API_KEY")
        # Track used media IDs to prevent repetition across videos
        self._session_used_ids: Set[str] = set()
        self._persistent_used_ids: Set[str] = self._load_used_media_ids()

    def _load_used_media_ids(self) -> Set[str]:
        """Load previously used media IDs from persistent history."""
        try:
            if USED_MEDIA_HISTORY.exists():
                with open(USED_MEDIA_HISTORY, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    # Keep only last 500 IDs to prevent unbounded growth
                    ids = data.get("used_ids", [])
                    return set(ids[-500:])
        except Exception:
            pass
        return set()

    def _record_used_media(self, media_id: str) -> None:
        """Record a media ID as used in both session and persistent storage."""
        str_id = str(media_id)
        self._session_used_ids.add(str_id)
        self._persistent_used_ids.add(str_id)
        try:
            USED_MEDIA_HISTORY.parent.mkdir(parents=True, exist_ok=True)
            existing_ids = []
            if USED_MEDIA_HISTORY.exists():
                with open(USED_MEDIA_HISTORY, "r", encoding="utf-8") as f:
                    existing_ids = json.load(f).get("used_ids", [])
            if str_id not in existing_ids:
                existing_ids.append(str_id)
            # Keep only last 500
            with open(USED_MEDIA_HISTORY, "w", encoding="utf-8") as f:
                json.dump({"used_ids": existing_ids[-500:]}, f, indent=2)
        except Exception:
            pass

    def _is_media_used(self, media_id: str) -> bool:
        """Check if a media ID has been used recently."""
        str_id = str(media_id)
        return str_id in self._session_used_ids or str_id in self._persistent_used_ids

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
        """Verify that target text contains a meaningful portion of core semantic tokens from query."""
        if not text:
            return False
        clean_target = text.lower().replace("-", " ").replace("_", " ")
        # Only use tokens with 4+ chars for meaningful matching (avoid false positives from 'art', 'man', 'run')
        q_tokens = [w for w in re.sub(r"[^a-zA-Z\s]", " ", query).lower().split() if len(w) > 3 and w not in STOP_WORDS]
        if not q_tokens:
            return True
        matches = sum(1 for t in q_tokens if t in clean_target)
        # Require at least 40% of meaningful tokens to match (stricter than before)
        return matches >= max(1, len(q_tokens) * 0.4)

    def search_and_download_video(
        self,
        query: str,
        output_dir: Path,
        orientation: str = "portrait",  # portrait (9:16) or landscape (16:9)
        require_relevance: bool = True,
    ) -> Optional[Path]:
        """Search Pexels for a video matching query with relevance check, dedup, and randomization."""
        if not self.pexels_key:
            return None

        clean_q = self.clean_query(query)
        if not clean_q:
            return None

        headers = {"Authorization": self.pexels_key}
        # Randomize page offset (1-5) to avoid always getting the same first results
        page = random.randint(1, 5)
        url = (
            f"https://api.pexels.com/videos/search?"
            f"query={requests.utils.quote(clean_q)}"
            f"&orientation={orientation}&per_page=15&page={page}"
        )

        try:
            print_info(f"Searching stock video for: '{clean_q}' (page {page}, {orientation})...")
            resp = requests.get(url, headers=headers, timeout=12)
            if resp.status_code != 200:
                return None

            data = resp.json()
            videos = data.get("videos", [])
            if not videos:
                return None

            # Collect ALL relevant candidates, then randomly pick one that hasn't been used
            relevant_candidates = []
            for v in videos:
                vid_id = str(v.get("id", ""))
                slug = v.get("url", "").split("/video/")[-1].rstrip("/")
                if self._is_media_used(vid_id):
                    continue  # Skip already-used clips
                if not require_relevance or self.is_relevant(clean_q, slug):
                    relevant_candidates.append(v)

            if not relevant_candidates and not require_relevance:
                # Use any non-duplicate video
                relevant_candidates = [v for v in videos if not self._is_media_used(str(v.get("id", "")))]

            if not relevant_candidates:
                print_warning(f"No fresh relevant stock video found for '{clean_q}'. Will use visual fallback.")
                return None

            # Randomly select from candidates to prevent same-first-result pattern
            matched_video = random.choice(relevant_candidates)

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
                self._record_used_media(str(matched_video['id']))
                return target_path

            print_info(f"Downloading relevant stock video: {file_name}...")
            with requests.get(target_file["link"], stream=True, timeout=30) as r:
                r.raise_for_status()
                with open(target_path, "wb") as f:
                    for chunk in r.iter_content(chunk_size=65536):
                        f.write(chunk)

            self._record_used_media(str(matched_video['id']))
            print_success(f"Stock video downloaded: {target_path.name}")
            return target_path

        except Exception as e:
            print_warning(f"Failed to fetch stock video for '{clean_q}': {e}")
            return None

    def search_pixabay_video(
        self,
        query: str,
        output_dir: Path,
        orientation: str = "portrait",
    ) -> Optional[Path]:
        """Search Pixabay for a free video clip matching the query with dedup."""
        if not self.pixabay_key:
            return None

        clean_q = self.clean_query(query)
        if not clean_q:
            return None

        try:
            url = (
                f"https://pixabay.com/api/videos/?"
                f"key={self.pixabay_key}&q={requests.utils.quote(clean_q)}"
                f"&per_page=10&video_type=all"
            )
            resp = requests.get(url, timeout=12)
            if resp.status_code != 200:
                return None

            data = resp.json()
            hits = data.get("hits", [])
            if not hits:
                return None

            # Filter candidates that haven't been used
            fresh_hits = [h for h in hits if not self._is_media_used(str(h.get("id", "")))]
            chosen = random.choice(fresh_hits) if fresh_hits else hits[0]

            vid_id = str(chosen.get("id", ""))
            videos = chosen.get("videos", {})
            video_info = videos.get("medium") or videos.get("large") or videos.get("small")
            if not video_info or not video_info.get("url"):
                return None

            file_name = f"pixabay_{sanitize_filename(clean_q)}_{vid_id}.mp4"
            target_path = output_dir / file_name
            if target_path.exists() and target_path.stat().st_size > 0:
                self._record_used_media(vid_id)
                return target_path

            print_info(f"Downloading Pixabay stock video: {file_name}...")
            with requests.get(video_info["url"], stream=True, timeout=30) as r:
                r.raise_for_status()
                with open(target_path, "wb") as f:
                    for chunk in r.iter_content(chunk_size=65536):
                        f.write(chunk)

            self._record_used_media(vid_id)
            print_success(f"Pixabay video downloaded: {target_path.name}")
            return target_path
        except Exception as e:
            print_warning(f"Pixabay video search failed for '{clean_q}': {e}")
            return None

    def search_and_download_photo(
        self,
        query: str,
        output_dir: Path,
        orientation: str = "portrait",
    ) -> Optional[Path]:
        """Search Pexels Photos for a verified, high-resolution still image with dedup."""
        if not self.pexels_key:
            return None

        clean_q = self.clean_query(query)
        if not clean_q:
            return None

        headers = {"Authorization": self.pexels_key}
        # Randomize page offset to get variety
        page = random.randint(1, 3)
        url = (
            f"https://api.pexels.com/v1/search?"
            f"query={requests.utils.quote(clean_q)}"
            f"&orientation={orientation}&per_page=15&page={page}"
        )

        try:
            print_info(f"Searching high-res stock photo for: '{clean_q}' (page {page}, {orientation})...")
            resp = requests.get(url, headers=headers, timeout=12)
            if resp.status_code != 200:
                return None

            data = resp.json()
            photos = data.get("photos", [])
            if not photos:
                return None

            # Collect relevant, non-duplicate photo candidates
            relevant_candidates = []
            for p in photos:
                photo_id = str(p.get("id", ""))
                if self._is_media_used(photo_id):
                    continue  # Skip already-used photos
                alt = p.get("alt", "")
                slug = p.get("url", "").split("/photo/")[-1].rstrip("/")
                if self.is_relevant(clean_q, alt) or self.is_relevant(clean_q, slug):
                    relevant_candidates.append(p)

            # DO NOT fall back to photos[0] — only use truly relevant photos
            if not relevant_candidates:
                print_warning(f"No relevant stock photo found for '{clean_q}'. Will try fallback.")
                return None

            # Randomly select from relevant candidates
            matched_photo = random.choice(relevant_candidates)

            src = matched_photo.get("src", {})
            img_url = src.get("large2x") or src.get("portrait") or src.get("original") or src.get("large")
            if not img_url:
                return None

            file_name = f"photo_{sanitize_filename(clean_q)}_{matched_photo['id']}.jpg"
            target_path = output_dir / file_name
            if target_path.exists() and target_path.stat().st_size > 0:
                self._record_used_media(str(matched_photo['id']))
                return target_path

            print_info(f"Downloading matching stock photo: {file_name}...")
            r = requests.get(img_url, timeout=20)
            if r.status_code == 200 and len(r.content) > 5000:
                with open(target_path, "wb") as f:
                    f.write(r.content)
                self._record_used_media(str(matched_photo['id']))
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

    @staticmethod
    def get_vocal_theme_video_queries(text: str) -> List[str]:
        """Extract high-relevance motion video queries from vocal narration or subject based on semantic archetypes."""
        if not text:
            return []
        matched_queries: List[str] = []
        lower_text = text.lower()
        for pattern, queries in VOCAL_THEME_VIDEO_QUERIES:
            if re.search(pattern, lower_text):
                for q in queries:
                    if q not in matched_queries:
                        matched_queries.append(q)
        return matched_queries

    def fetch_best_visual_for_scene(
        self,
        subject: str,
        keywords: Optional[List[str]] = None,
        narration: Optional[str] = None,
        output_dir: Optional[Path] = None,
        orientation: str = "portrait",
        require_video: bool = False,
    ) -> Path:
        """Multi-tier visual fetcher:
        1. Genuine Relevant Pexels Stock Video
        2. Genuine Pixabay Stock Video (if key available)
        3. Pollinations Photorealistic AI Visual matching the exact spoken lyrics (with continuous Ken Burns motion!)
        4. Universal motion footage fallback
        """
        cfg = get_config()
        out_dir = output_dir or cfg.paths.temp_dir
        out_dir.mkdir(parents=True, exist_ok=True)

        candidates = [subject]
        if keywords:
            candidates.extend(keywords)

        # 1. Try Pexels Video with direct subject and keywords (with strict relevance)
        for q in candidates:
            if not q or not q.strip():
                continue
            vid = self.search_and_download_video(q, output_dir=out_dir, orientation=orientation, require_relevance=True)
            if vid and vid.exists():
                return vid

        # 1.2. Try Pixabay Video if API key is provided
        if self.pixabay_key:
            for q in candidates:
                if not q or not q.strip():
                    continue
                vid = self.search_pixabay_video(q, output_dir=out_dir, orientation=orientation)
                if vid and vid.exists():
                    return vid

        # 1.3. Thematic Video Queries (if vocal narration has clear semantic archetypes)
        context_text = f"{subject} {' '.join(keywords or [])} {narration or ''}"
        thematic_queries = self.get_vocal_theme_video_queries(context_text)
        for q in thematic_queries:
            vid = self.search_and_download_video(q, output_dir=out_dir, orientation=orientation, require_relevance=True)
            if vid and vid.exists():
                return vid

        # 2. Perfect Lyrics Matching: Generate a Photorealistic AI Visual via Pollinations AI (100% Free & Unlimited!)
        # This guarantees the visual DIRECTLY illustrates the exact spoken line without random mystery lights!
        try:
            from autotube.media.ai_visuals import VisualGenerator
            vis_gen = VisualGenerator()
            clean_subj = self.clean_query(subject) or subject
            ai_path = out_dir / f"ai_{sanitize_filename(clean_subj)}_{random.randint(1000, 9999)}.jpg"

            # Enrich AI prompt with concrete cinematic scene context
            lower_subj = clean_subj.lower()
            lower_narr = (narration or "").lower()

            if any(k in lower_subj or k in lower_narr for k in ("nurse", "matilda", "interrogat")):
                ai_prompt = "cinematic 1947 photograph, young US Army nurse Matilda MacElroy in vintage uniform, wooden interrogation desk, steel microphone, notebook, moody classified Roswell military bunker, dramatic lighting, 8k resolution, photorealistic"
            elif any(k in lower_subj or k in lower_narr for k in ("alien", "airl", "extraterrestrial", "grey")):
                ai_prompt = "hyperrealistic cinematic close-up of extraterrestrial grey alien Airl, smooth porcelain skin, piercing black obsidian almond eyes, faint psychic blue glow from temple, dark classified Roswell bunker, dramatic volumetric lighting, 8k photorealistic documentary photography"
            elif any(k in lower_subj or k in lower_narr for k in ("fbi", "memo", "document", "classified")):
                ai_prompt = "authentic 1947 classified FBI memo stamped TOP SECRET about recovered flying disc in Roswell New Mexico, vintage typewriter text, old aged yellowed paper, dim bunker desk lamp, 8k resolution"
            elif any(k in lower_subj or k in lower_narr for k in ("prison", "barrier", "grid", "soul", "matrix")):
                ai_prompt = "cinematic view of planet Earth surrounded by glowing electronic amnesia grid barrier in deep space, cosmic prison matrix, hyperrealistic 8k, dark dramatic universe"
            else:
                ai_prompt = f"{clean_subj}"
                if narration:
                    clean_narr = self.clean_query(narration)
                    if clean_narr and clean_narr != clean_subj:
                        ai_prompt += f", {clean_narr[:50]}"
                ai_prompt += ", cinematic lighting, documentary photography, 8k resolution, dramatic atmosphere, ultra detailed"

            img = vis_gen.generate_image(
                prompt=ai_prompt,
                output_path=ai_path,
                width=1080 if orientation == "portrait" else 1920,
                height=1920 if orientation == "portrait" else 1080,
                style="realistic",
            )
            if img and img.exists() and img.stat().st_size > 5000:
                print_success(f"Generated AI photorealistic visual matching lyrics: '{subject}'")
                return img
        except Exception as e:
            print_warning(f"AI visual generation fallback failed: {e}")

        # 3. Universal motion video fallbacks (if AI generation failed or video strictly requested)
        for q in UNIVERSAL_MOTION_FALLBACKS:
            vid = self.search_and_download_video(q, output_dir=out_dir, orientation=orientation, require_relevance=True)
            if vid and vid.exists():
                return vid

        # 4. Fallback gradient canvas (absolute last resort)
        slug = sanitize_filename(subject or "scene")
        fallback_path = out_dir / f"fallback_{slug}_{random.randint(1000, 9999)}.jpg"
        return self.create_gradient_fallback(subject, fallback_path, width=1080 if orientation == "portrait" else 1920, height=1920 if orientation == "portrait" else 1080)

    def fetch_scene_visual_assets(
        self,
        scenes: List[Any],
        output_dir: Path,
        orientation: str = "portrait",
        require_video: bool = True,
    ) -> List[Path]:
        """Fetch a strictly verified, unique video/visual asset for every scene (no duplicates within a video)."""
        assets: List[Path] = []
        used_paths: Set[Path] = set()  # Prevent same clip within one video

        for idx, scene in enumerate(scenes):
            subject = getattr(scene, "visual_subject", "")
            keywords = getattr(scene, "search_keywords", [])
            narration = getattr(scene, "narration", "")
            if not subject and hasattr(scene, "visual_query"):
                subject = getattr(scene, "visual_query", "")

            print_info(f"Acquiring Scene {idx+1}/{len(scenes)} Visual for subject: '{subject}' (Footage required: {require_video})...")
            asset = self.fetch_best_visual_for_scene(
                subject=subject,
                keywords=keywords,
                narration=narration,
                output_dir=output_dir,
                orientation=orientation,
                require_video=require_video,
            )

            # If this exact file was already used in a previous scene, try alternate keywords
            if asset in used_paths and keywords:
                print_warning(f"Scene {idx+1} got duplicate visual, trying alternate keyword...")
                for alt_kw in keywords:
                    alt_asset = self.fetch_best_visual_for_scene(
                        subject=alt_kw,
                        keywords=[subject],
                        narration=narration,
                        output_dir=output_dir,
                        orientation=orientation,
                        require_video=require_video,
                    )
                    if alt_asset not in used_paths:
                        asset = alt_asset
                        break

            used_paths.add(asset)
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
