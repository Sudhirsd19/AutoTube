"""Pexels Video API - Search & download free HD stock video clips for scene backgrounds."""

import os
import hashlib
import requests
from pathlib import Path
from typing import Optional, List, Dict

from autotube.config import PROJECT_ROOT
from autotube.utils.console import print_info, print_success, print_warning, print_error


# Video cache directory
PEXELS_CACHE_DIR = PROJECT_ROOT / "assets" / "pexels_videos"


class PexelsVideoFetcher:
    """Search and download free HD stock videos from Pexels API."""

    API_BASE = "https://api.pexels.com/videos"

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.getenv("PEXELS_API_KEY", "")
        PEXELS_CACHE_DIR.mkdir(parents=True, exist_ok=True)

    def is_configured(self) -> bool:
        return bool(self.api_key)

    def search_videos(
        self,
        query: str,
        orientation: str = "portrait",
        per_page: int = 5,
        min_duration: int = 3,
        max_duration: int = 30,
    ) -> List[Dict]:
        """Search Pexels for videos matching the query.
        
        Returns list of video dicts with 'id', 'url', 'duration', 'width', 'height', 'download_url'.
        """
        if not self.api_key:
            print_warning("Pexels API key not set.")
            return []

        headers = {"Authorization": self.api_key}
        params = {
            "query": query,
            "orientation": orientation,
            "per_page": per_page,
            "size": "medium",
        }

        try:
            resp = requests.get(f"{self.API_BASE}/search", headers=headers, params=params, timeout=15)
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:
            print_warning(f"Pexels API error: {e}")
            return []

        results = []
        for video in data.get("videos", []):
            vid_duration = video.get("duration", 0)
            if vid_duration < min_duration or vid_duration > max_duration:
                continue

            # Find best portrait/HD video file
            best_file = None
            for vf in video.get("video_files", []):
                w = vf.get("width", 0)
                h = vf.get("height", 0)
                # Prefer portrait (height > width) and HD
                if orientation == "portrait" and h > w and h >= 720:
                    if best_file is None or h > best_file.get("height", 0):
                        best_file = vf
                elif orientation != "portrait" and w >= 720:
                    if best_file is None or w > best_file.get("width", 0):
                        best_file = vf

            # Fallback: any HD file
            if not best_file:
                for vf in video.get("video_files", []):
                    if vf.get("height", 0) >= 720 or vf.get("width", 0) >= 720:
                        best_file = vf
                        break

            if not best_file:
                continue

            results.append({
                "id": video["id"],
                "duration": vid_duration,
                "width": best_file.get("width", 0),
                "height": best_file.get("height", 0),
                "download_url": best_file.get("link", ""),
                "pexels_url": video.get("url", ""),
            })

        return results

    def download_video(self, download_url: str, output_path: Path) -> Optional[Path]:
        """Download a video file from URL to local path."""
        if output_path.exists() and output_path.stat().st_size > 50000:
            return output_path  # Already cached

        try:
            output_path.parent.mkdir(parents=True, exist_ok=True)
            resp = requests.get(download_url, stream=True, timeout=60)
            resp.raise_for_status()
            with open(output_path, "wb") as f:
                for chunk in resp.iter_content(chunk_size=1024 * 64):
                    f.write(chunk)
            if output_path.exists() and output_path.stat().st_size > 10000:
                return output_path
        except Exception as e:
            print_warning(f"Pexels download error: {e}")
        return None

    def get_scene_video(
        self,
        search_query: str,
        scene_index: int = 0,
        orientation: str = "portrait",
    ) -> Optional[Path]:
        """Search Pexels, download first matching video, cache it.
        
        Uses a hash of the query as cache key so the same query returns the same video.
        """
        if not self.is_configured():
            return None

        # Include scene_index in cache key so different scenes get distinct video clips
        query_hash = hashlib.md5(f"{search_query}_{scene_index}".encode()).hexdigest()[:12]
        safe_name = search_query.lower().replace(" ", "_")[:35]
        cache_path = PEXELS_CACHE_DIR / f"{safe_name}_{scene_index}_{query_hash}.mp4"

        # Check cache first
        if cache_path.exists() and cache_path.stat().st_size > 50000:
            print_info(f"   [Pexels video cache hit] {cache_path.name}")
            return cache_path

        # Search requested orientation
        results = self.search_videos(query=search_query, orientation=orientation, per_page=15)
        # If few/no clips found in portrait, also search all orientations (shorts builder center-crops landscape videos)
        if len(results) < 2 and orientation == "portrait":
            extra_vids = self.search_videos(query=search_query, orientation="", per_page=15)
            results.extend(extra_vids)

        if not results:
            print_warning(f"   No Pexels videos found for: '{search_query}'")
            return None

        # Pick result (use scene_index to vary across scenes)
        pick = results[scene_index % len(results)]
        print_info(f"   [Pexels] Downloading: '{search_query}' ({pick['duration']}s, {pick['width']}x{pick['height']})")

        downloaded = self.download_video(pick["download_url"], cache_path)
        if downloaded:
            size_mb = round(downloaded.stat().st_size / (1024 * 1024), 2)
            print_success(f"   [Pexels] Cached: {cache_path.name} ({size_mb} MB)")
        return downloaded

    def search_photos(
        self,
        query: str,
        orientation: str = "portrait",
        per_page: int = 5,
    ) -> List[Dict]:
        """Search Pexels for high-res photos matching query."""
        if not self.is_configured():
            return []
        headers = {"Authorization": self.api_key}
        params = {
            "query": query,
            "orientation": orientation,
            "per_page": per_page,
        }
        try:
            resp = requests.get("https://api.pexels.com/v1/search", headers=headers, params=params, timeout=12)
            if resp.status_code == 200:
                data = resp.json()
                results = []
                for p in data.get("photos", []):
                    src = p.get("src", {})
                    img_url = src.get("large2x") or src.get("large") or src.get("original")
                    if img_url:
                        results.append({
                            "id": p["id"],
                            "width": p.get("width", 0),
                            "height": p.get("height", 0),
                            "download_url": img_url,
                            "photographer": p.get("photographer", ""),
                        })
                return results
        except Exception as e:
            print_warning(f"Pexels photo search error: {e}")
        return []

    def get_scene_photo(
        self,
        search_query: str,
        scene_index: int = 0,
        orientation: str = "portrait",
    ) -> Optional[Path]:
        """Search Pexels, download matching high-res photo, cache it."""
        if not self.is_configured():
            return None
        query_hash = hashlib.md5(f"{search_query}_{scene_index}".encode()).hexdigest()[:12]
        safe_name = search_query.lower().replace(" ", "_")[:35]
        cache_path = PEXELS_CACHE_DIR / f"{safe_name}_{scene_index}_{query_hash}.jpg"
        if cache_path.exists() and cache_path.stat().st_size > 20000:
            return cache_path

        results = self.search_photos(query=search_query, orientation=orientation)
        if not results:
            return None

        pick = results[scene_index % len(results)]
        try:
            resp = requests.get(pick["download_url"], timeout=20)
            if resp.status_code == 200 and len(resp.content) > 10000:
                with open(cache_path, "wb") as f:
                    f.write(resp.content)
                print_success(f"   [Pexels Photo] Cached: {cache_path.name} ({round(len(resp.content)/(1024*1024), 2)} MB)")
                return cache_path
        except Exception as e:
            print_warning(f"Pexels photo download error: {e}")
        return None



# ----- Scene keyword mapping for Alien Interview series -----

ALIEN_SCENE_KEYWORDS = {
    # Speaker-based defaults
    "nurse_default": ["vintage nurse 1940s hospital", "woman speaking microphone retro", "military nurse portrait vintage"],
    "alien_default": ["alien dark room sci-fi", "extraterrestrial close up dark", "mysterious alien eyes dark"],
    "narrator_default": ["classified documents vintage", "military briefing room retro", "top secret files desk"],
    
    # Topic-specific keywords
    "roswell_crash": ["ufo crash desert night", "flying saucer wreckage desert", "mysterious crash site desert"],
    "interrogation": ["interrogation room dark spotlight", "dark room questioning vintage", "dimly lit room mystery"],
    "military": ["military generals meeting", "army officers war room", "military briefing room vintage"],
    "space_domain": ["galaxy stars nebula space", "spaceship sci-fi cosmos", "deep space stars universe"],
    "documents": ["classified documents desk", "old typewriter papers vintage", "secret files stamped confidential"],
    "telepathy": ["mysterious energy waves dark", "psychic mind reading dark", "consciousness brain waves"],
    "prison_planet": ["earth from space dark", "planet earth atmosphere dark", "trapped earth dark moody"],
    "death_afterlife": ["soul spirit afterlife light", "mysterious light tunnel dark", "spiritual awakening light"],
    "ancient_history": ["ancient civilization ruins", "pyramids mysterious night", "archaeological discovery ancient"],
    "nuclear": ["nuclear explosion test", "atomic bomb blast vintage", "mushroom cloud explosion"],
    "eyes_macro": ["mysterious alien eyes close up", "dark eyes reflecting stars", "cosmic eyes macro dark"],
    "cliffhanger": ["suspense dark mystery shadows", "dramatic reveal dark room", "shocking discovery dark"],
}


def get_pexels_keywords_for_scene(speaker: str, visual_subject: str, scene_index: int = 0) -> str:
    """Extract the best Pexels search query for a given scene."""
    subject_lower = visual_subject.lower()
    speaker_lower = speaker.lower()
    
    # Match topic-specific keywords first
    if any(w in subject_lower for w in ("crash", "roswell", "desert", "wreckage")):
        keywords = ALIEN_SCENE_KEYWORDS["roswell_crash"]
    elif any(w in subject_lower for w in ("interrogation", "two shot", "room", "building", "hangar")):
        keywords = ALIEN_SCENE_KEYWORDS["interrogation"]
    elif any(w in subject_lower for w in ("general", "ramey", "officer", "glass", "military")):
        keywords = ALIEN_SCENE_KEYWORDS["military"]
    elif any(w in subject_lower for w in ("domain", "fleet", "starship", "cosmic", "space", "disc")):
        keywords = ALIEN_SCENE_KEYWORDS["space_domain"]
    elif any(w in subject_lower for w in ("document", "evidence", "proof", "memo", "paper", "loop", "press")):
        keywords = ALIEN_SCENE_KEYWORDS["documents"]
    elif any(w in subject_lower for w in ("telepathic", "mind", "thought", "communication")):
        keywords = ALIEN_SCENE_KEYWORDS["telepathy"]
    elif any(w in subject_lower for w in ("prison", "earth", "trap", "amnesia")):
        keywords = ALIEN_SCENE_KEYWORDS["prison_planet"]
    elif any(w in subject_lower for w in ("death", "afterlife", "soul", "spirit", "immortal")):
        keywords = ALIEN_SCENE_KEYWORDS["death_afterlife"]
    elif any(w in subject_lower for w in ("ancient", "pyramid", "civilization", "history")):
        keywords = ALIEN_SCENE_KEYWORDS["ancient_history"]
    elif any(w in subject_lower for w in ("nuclear", "atomic", "detonation", "white sands")):
        keywords = ALIEN_SCENE_KEYWORDS["nuclear"]
    elif any(w in subject_lower for w in ("eye", "macro", "stare", "cliffhanger")):
        keywords = ALIEN_SCENE_KEYWORDS["eyes_macro"]
    elif "nurse" in speaker_lower:
        keywords = ALIEN_SCENE_KEYWORDS["nurse_default"]
    elif "alien" in speaker_lower:
        keywords = ALIEN_SCENE_KEYWORDS["alien_default"]
    else:
        keywords = ALIEN_SCENE_KEYWORDS["narrator_default"]
    
    # Rotate keywords based on scene index for variety
    return keywords[scene_index % len(keywords)]
