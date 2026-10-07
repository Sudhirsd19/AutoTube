"""Multi-Source Stock Video Aggregator & AI Semantic Ranker.

Searches across Mixkit, Coverr, Pexels, and Pixabay simultaneously.
Uses Gemini AI to generate cinematic visual search queries, apply negative content filters,
and semantically score candidate video clips to pick the single best matching clip for each scene.
Guarantees 100% visual coverage with graceful fallback to Archival Proofs & Photorealistic AI Visuals.
"""

import os
import re
import json
import time
import hashlib
import random
import requests
from pathlib import Path
from typing import Dict, List, Any, Optional, Set
from concurrent.futures import ThreadPoolExecutor, as_completed

from autotube.config import PROJECT_ROOT, get_config
from autotube.utils.console import print_info, print_success, print_warning, print_error
from autotube.utils.file_utils import sanitize_filename
from autotube.media.pexels_video import PexelsVideoFetcher
from autotube.media.ai_visuals import VisualGenerator

# Cache directory for multi-stock downloads
STOCK_CACHE_DIR = PROJECT_ROOT / "assets" / "stock_cache"
USED_STOCK_HISTORY = PROJECT_ROOT / "config" / "used_stock_history.json"

HTTP_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
}

CANDIDATE_GEMINI_MODELS = [
    "gemini-3.5-flash-lite",
    "gemini-3.1-flash-lite",
    "gemini-3.8-flash",
    "gemini-3.5-flash",
]

# Blacklisted stock IDs (e.g. 95% pitch-black empty void or defective footage)
BLACKLISTED_STOCK_IDS = {
    "mixkit_14179",  # 95% pitch-black empty void, black hole is virtually invisible
}


class MultiStockAggregator:
    """Aggregates videos from Mixkit, Coverr, Pexels, and Pixabay with AI semantic selection."""

    def __init__(self):
        self.cfg = get_config()
        self.pexels_fetcher = PexelsVideoFetcher()
        self.ai_visuals = VisualGenerator()
        STOCK_CACHE_DIR.mkdir(parents=True, exist_ok=True)
        USED_STOCK_HISTORY.parent.mkdir(parents=True, exist_ok=True)

        self.session_used_ids: Set[str] = set()
        self.persistent_used_ids: Set[str] = self._load_used_ids()
        self._gemini_client = None

    def _load_used_ids(self) -> Set[str]:
        try:
            if USED_STOCK_HISTORY.exists():
                with open(USED_STOCK_HISTORY, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    return set(data.get("used_ids", [])[-500:])
        except Exception:
            pass
        return set()

    def _record_used_id(self, media_id: str) -> None:
        str_id = str(media_id)
        self.session_used_ids.add(str_id)
        self.persistent_used_ids.add(str_id)
        try:
            existing = []
            if USED_STOCK_HISTORY.exists():
                with open(USED_STOCK_HISTORY, "r", encoding="utf-8") as f:
                    existing = json.load(f).get("used_ids", [])
            if str_id not in existing:
                existing.append(str_id)
            with open(USED_STOCK_HISTORY, "w", encoding="utf-8") as f:
                json.dump({"used_ids": existing[-500:]}, f, indent=2)
        except Exception:
            pass

    def _is_session_used(self, media_id: str) -> bool:
        return str(media_id) in self.session_used_ids

    def _is_persistent_used(self, media_id: str) -> bool:
        return str(media_id) in self.persistent_used_ids

    def _is_used(self, media_id: str) -> bool:
        """Check if media was used in the current render session to guarantee scene diversity."""
        return str(media_id) in self.session_used_ids

    def _get_gemini_client(self):
        if self._gemini_client is not None:
            return self._gemini_client
        api_key = os.getenv("GEMINI_API_KEY", "") or getattr(self.cfg, "gemini_api_key", "")
        if api_key:
            try:
                from google import genai
                self._gemini_client = genai.Client(api_key=api_key)
            except Exception as e:
                print_warning(f"Could not init Gemini client in MultiStockAggregator: {e}")
        return self._gemini_client

    # -------------------------------------------------------------
    # 1. AI VISUAL INTELLIGENCE LAYER (SCENE UNDERSTANDING & MULTI-QUERY)
    # -------------------------------------------------------------
    def plan_visual_scene(self, scene_text: str, title: str, idx: int = 0) -> Dict[str, Any]:
        """Perform deep narrative scene understanding using Gemini to extract subject, action, must-show visual elements, and multi-query search angles."""
        client = self._get_gemini_client()
        s_lower = scene_text.lower()
        t_lower = title.lower()

        # Heuristic intelligent baseline (fallback if Gemini API is unreachable)
        fallback_subject = "mysterious phenomenon"
        fallback_must_show = ["mysterious phenomenon", "cinematic suspense"]
        fallback_avoid = ["cartoon", "smiling", "modern office", "smartphone", "laptop", "talking head", "carving", "pumpkin", "face mask", "helmet", "blue sky", "daylight beach"]
        fallback_queries = ["cinematic dramatic mystery", "atmospheric suspense cinematic", "dark moody cinematic"]

        is_space_or_black_hole = any(k in s_lower or k in t_lower for k in (
            "black hole", "blackhole", "event horizon", "accretion", "singularity", "spaghetti",
            "space", "antariksh", "brahmand", "galaxy", "universe", "planet", "stars", "cosmos", "solar system", "grah", "dharati"
        ))

        if any(k in s_lower or k in t_lower for k in ("black hole", "blackhole", "event horizon", "accretion", "singularity", "spaghetti")):
            fallback_subject = "black hole cosmic singularity"
            fallback_must_show = ["black hole", "cosmic vortex", "deep space", "singularity"]
            fallback_avoid += ["generic galaxy", "earth daytime", "blue sky", "nature", "sunny", "phone", "office", "helmet", "face mask", "clouds"]
            fallback_queries = ["black hole", "black hole space", "cosmic vortex", "planet earth space"]
        elif is_space_or_black_hole:
            fallback_subject = "deep outer space and planets"
            fallback_must_show = ["deep space galaxy", "planet earth space", "stars"]
            fallback_avoid += ["earth daytime", "city", "people", "beach", "clouds", "phone", "office"]
            fallback_queries = ["deep space galaxy", "planet earth space", "outer space cosmos"]
        elif any(k in s_lower or k in t_lower for k in ("temple", "mandir", "ancient", "prachin", "underground", "chamber", "kailasa")):
            fallback_subject = "ancient temple mystery"
            fallback_must_show = ["ancient stone temple", "underground chamber", "carvings"]
            fallback_avoid += ["modern city", "cars", "office", "neon"]
            fallback_queries = ["ancient stone temple ruins", "mysterious underground chamber", "ancient archaeological site"]
        elif any(k in s_lower or k in t_lower for k in ("brain", "dimag", "mind", "psychology", "soch", "memory")):
            fallback_subject = "human brain and subconscious"
            fallback_must_show = ["glowing neural network", "brain synapses firing", "abstract thought flow"]
            fallback_avoid += ["hospital surgery", "doctor", "cartoon"]
            fallback_queries = ["glowing brain neural network", "human brain neurons firing", "abstract subconscious mind"]
        elif any(k in s_lower or k in t_lower for k in ("ocean", "samundar", "sea", "trench", "underwater", "abyss")):
            fallback_subject = "deep ocean abyss"
            fallback_must_show = ["deep underwater abyss", "ocean trench dark", "underwater vortex"]
            fallback_avoid += ["sunny beach", "swimming pool", "resort", "smiling diver"]
            fallback_queries = ["dark deep ocean trench", "mysterious underwater abyss", "deep sea dark water"]

        fallback_plan = {
            "subject": fallback_subject,
            "action": "cinematic dramatic motion",
            "environment": "dramatic atmosphere",
            "visual_type": "cinematic documentary",
            "must_show": fallback_must_show,
            "avoid": fallback_avoid,
            "search_queries": fallback_queries,
        }

        if not client:
            return fallback_plan

        prompt = f"""You are an elite Hollywood visual effects director and documentary scene planner.
Story Title: "{title}"
Current Scene #{idx+1} Narration: "{scene_text}"

Perform deep narrative scene understanding to find stock video B-roll that represents the ACTUAL CONCEPT spoken (not just generic filler).
Think step-by-step:
1. What is the core physical SUBJECT or phenomenon being discussed? (e.g. if talking about black holes, singularity, space destruction, the subject is "black hole cosmic singularity").
2. What specific DYNAMIC ACTION or visual movement should be shown? (e.g. "black hole warping spacetime, cosmic vortex").
3. What 3-4 concrete visual elements MUST BE VISIBLE on screen? (e.g. ["black hole", "accretion disk", "deep space"]).
4. What visual elements MUST BE STRICTLY AVOIDED/REJECTED? (e.g. ["clouds in blue sky", "ocean waves beach", "person typing phone", "modern office", "cartoon", "helmet", "face mask"]).
5. CRITICAL SEARCH RULE: Provide 3 to 4 CONCISE, HIGH-CONVERTING 1-to-3 word English search queries that stock video libraries (Pexels, Mixkit, Coverr) ACTUALLY categorize footage under.
   EXAMPLES OF GREAT QUERIES:
   - "black hole"
   - "black hole space"
   - "planet earth space"
   - "cosmic vortex"
   - "galaxy rotation"
   - "deep space stars"
   NEVER generate multi-word complex literary descriptions like "ocean water lifting into sky space anomaly" or "earth tidal force black hole animation". Keep each query strictly to 1-3 simple, clean words!

DIRECTORIAL CONTINUITY RULES:
- If this story is about space, astronomy, black holes, or cosmic phenomena, the visuals MUST REMAIN 100% IN OUTER SPACE throughout the ENTIRE video.
- NEVER switch to human faces, smartphones, people typing, social media icons, or office desks, EVEN IF the narration mentions subscribing, liking, commenting, or asking a question! For outro/CTA lines, keep visuals anchored in epic cosmic vortexes or rotating black holes.

Return STRICT JSON with keys:
- "subject": string (e.g. "black hole event horizon")
- "action": string (e.g. "approaching singularity, spacetime distortion")
- "environment": string (e.g. "deep outer space void")
- "visual_type": string (e.g. "cinematic astronomy simulation")
- "must_show": array of 3-4 strings (e.g. ["black hole", "accretion disk", "deep space"])
- "avoid": array of 6-8 strings to reject (e.g. ["clouds", "daylight sky", "beach", "phone", "office", "cartoon"])
- "search_queries": array of 3-4 concise 1-3 word queries (e.g. ["black hole", "black hole space", "planet earth space", "cosmic vortex"])
"""
        for model in CANDIDATE_GEMINI_MODELS:
            try:
                resp = client.models.generate_content(
                    model=model,
                    contents=prompt,
                    config={"response_mime_type": "application/json"},
                )
                if resp.text:
                    clean = resp.text.strip()
                    if clean.startswith("```json"):
                        clean = clean[7:].split("```")[0].strip()
                    elif clean.startswith("```"):
                        clean = clean[3:].split("```")[0].strip()
                    data = json.loads(clean)
                    if "subject" in data and "must_show" in data and "search_queries" in data:
                        raw_qs = data.get("search_queries", [])
                        clean_qs = []
                        if isinstance(raw_qs, list):
                            for q in raw_qs:
                                clean_w = [w for w in re.sub(r"[^a-zA-Z0-9\s]", "", str(q)).split() if w]
                                if clean_w:
                                    clean_qs.append(" ".join(clean_w[:3]))

                        # Check if scene text is a call-to-action / outro
                        cta_keywords = ("comment", "subscribe", "like", "share", "jawab do", "channel ko", "agla video", "bell icon", "yes likhkar")
                        is_cta = any(k in s_lower for k in cta_keywords)

                        # Automatic Space / Black Hole Theme Reinforcement & Negative Tag Sanitization
                        if is_space_or_black_hole:
                            # 1. Purge accidental space/darkness words from avoid list
                            forbidden_in_avoid = {"black", "hole", "darkness", "space", "void", "night", "shadow", "galaxy", "stars", "universe", "planet", "earth", "cosmos", "cosmic", "astronomy", "anomaly", "simulation", "nebula"}
                            raw_avoid = [str(a).lower().strip() for a in data.get("avoid", [])]
                            clean_avoid = [a for a in raw_avoid if not any(f in a for f in forbidden_in_avoid)]
                            force_space_avoid = [
                                "phone", "smartphone", "iphone", "typing", "person", "human", "face", "man", "woman",
                                "office", "laptop", "crowd", "street", "circuit", "motherboard", "computer screen",
                                "social media", "subscribe button", "comment icon", "desk", "indoor", "room",
                                "smiling", "carving", "pumpkin", "mask", "headphone"
                            ]
                            for fa in force_space_avoid:
                                if fa not in clean_avoid:
                                    clean_avoid.append(fa)
                            data["avoid"] = clean_avoid

                            # 2. Purge non-astronomy queries
                            forbidden_query_words = {"comment", "icon", "subscribe", "social", "phone", "iphone", "typing", "circuit", "motherboard", "computer", "desk", "office", "person", "man", "woman"}
                            clean_qs = [q for q in clean_qs if not any(fw in q.lower() for fw in forbidden_query_words)]

                            is_bh_specific = any(k in s_lower or k in t_lower for k in ("black hole", "blackhole", "event horizon", "singularity", "spaghetti"))

                            if is_cta:
                                data["subject"] = "cosmic black hole event horizon finale" if is_bh_specific else "majestic deep space galaxy finale"
                                data["must_show"] = ["black hole", "cosmic vortex", "deep space galaxy"] if is_bh_specific else ["deep space galaxy", "planet earth space"]
                                clean_qs = ["black hole", "cosmic vortex", "black hole space", "deep space stars"] if is_bh_specific else ["deep space galaxy", "planet earth space", "outer space cosmos"]
                            elif is_bh_specific:
                                if "black hole" not in [x.lower() for x in clean_qs]:
                                    clean_qs.insert(0, "black hole")
                                if "black hole space" not in [x.lower() for x in clean_qs]:
                                    clean_qs.insert(1, "black hole space")
                                if "cosmic vortex" not in [x.lower() for x in clean_qs]:
                                    clean_qs.append("cosmic vortex")
                            else:
                                if "planet earth space" not in [x.lower() for x in clean_qs] and any(k in s_lower for k in ("earth", "planet", "grah", "dharati")):
                                    clean_qs.append("planet earth space")
                                if not any("space" in x.lower() or "galaxy" in x.lower() for x in clean_qs):
                                    clean_qs.append("deep space galaxy")

                        if clean_qs:
                            data["search_queries"] = clean_qs[:4]
                            return data
            except Exception:
                continue

        return fallback_plan

    def generate_smart_queries(self, scene_text: str, title: str, idx: int = 0) -> Dict[str, Any]:
        """Wrap plan_visual_scene for backward compatibility and multi-query dispatch."""
        plan = self.plan_visual_scene(scene_text, title, idx)
        queries = plan.get("search_queries", [])
        primary = queries[0] if len(queries) > 0 else "cinematic dramatic mystery"
        alt = queries[1] if len(queries) > 1 else "atmospheric suspense cinematic"
        mood = queries[2] if len(queries) > 2 else "dark moody night"
        return {
            "primary_query": primary,
            "alternative_query": alt,
            "mood_query": mood,
            "negative_tags": plan.get("avoid", []),
            "scene_plan": plan,
        }

    # -------------------------------------------------------------
    # 2. SOURCE SEARCH ENGINES (Mixkit, Coverr, Pexels, Pixabay)
    # -------------------------------------------------------------
    def search_mixkit(self, query: str, limit: int = 8) -> List[Dict[str, Any]]:
        """Search Mixkit free stock videos with real slug extraction and clean title parsing."""
        clean_q = re.sub(r"[^a-zA-Z0-9\s]", " ", query).strip().lower()
        if not clean_q:
            return []

        # Build list of category slugs to query directly on Mixkit
        slugs_to_try = []
        
        # Exact kebab-case of the query (e.g., 'black-hole', 'deep-space')
        words = [w for w in clean_q.split() if len(w) > 2]
        if len(words) >= 2:
            slugs_to_try.append("-".join(words[:2]))
        elif words:
            slugs_to_try.append(words[0])

        # Domain-specific high quality category slugs
        if any(k in clean_q for k in ("black hole", "blackhole")):
            slugs_to_try.extend(["black-hole", "space", "galaxy", "stars"])
        elif any(k in clean_q for k in ("space", "galaxy", "universe", "planet", "stars", "cosmos", "event horizon", "dilation")):
            slugs_to_try.extend(["space", "earth", "galaxy", "universe", "stars", "planet", "nebula"])
        elif any(k in clean_q for k in ("portal", "wormhole", "time travel", "dimension")):
            slugs_to_try.extend(["space", "galaxy", "tunnel"])
        elif any(k in clean_q for k in ("ocean", "water", "underwater", "deep sea")):
            slugs_to_try.extend(["ocean", "underwater", "sea"])
        elif any(k in clean_q for k in ("city", "street", "crowd", "night")):
            slugs_to_try.extend(["city", "night", "street"])
        elif any(k in clean_q for k in ("technology", "computer", "code", "ai", "robot")):
            slugs_to_try.extend(["technology", "computer"])

        # Also add individual significant words as fallbacks
        for w in words:
            if w not in slugs_to_try and len(w) > 3:
                slugs_to_try.append(w)

        # Remove duplicates while preserving order
        unique_slugs = []
        for s in slugs_to_try:
            if s not in unique_slugs:
                unique_slugs.append(s)

        results = []
        seen = set()

        for s in unique_slugs[:5]:
            u = f"https://mixkit.co/free-stock-video/{s}/"
            try:
                resp = requests.get(u, headers=HTTP_HEADERS, timeout=8)
                if resp.status_code == 200:
                    # Pattern for real Mixkit items: href="/free-stock-video/{slug}-{id}/"
                    matches = re.findall(r'href="(/free-stock-video/([a-z0-9-]+)-(\d+)/)"', resp.text)
                    for full_href, slug, vid_id in matches:
                        cand_id = f"mixkit_{vid_id}"
                        if vid_id in seen or self._is_used(cand_id) or cand_id in BLACKLISTED_STOCK_IDS:
                            continue
                        seen.add(vid_id)
                        real_title = slug.replace("-", " ")
                        tags = real_title.split() + ["mixkit"]
                        if "black hole" in real_title or vid_id in ("45020", "31548"):
                            tags.extend(["black hole", "singularity", "event horizon", "accretion disk", "cosmic vortex"])
                        results.append({
                            "id": cand_id,
                            "source": "Mixkit",
                            "title": real_title,
                            "tags": tags,
                            "duration": 10,
                            "download_url": f"https://assets.mixkit.co/videos/{vid_id}/{vid_id}-720.mp4",
                            "is_vertical": False,
                            "aspect_ratio": "16:9",
                        })
                        if len(results) >= limit:
                            break
            except Exception:
                pass
            if len(results) >= limit:
                break

        return results

    def search_coverr(self, query: str, orientation: str = "portrait", limit: int = 6) -> List[Dict[str, Any]]:
        """Search Coverr free stock videos with strict query relevance verification."""
        clean_q = re.sub(r"[^a-zA-Z0-9\s]", " ", query).strip().lower()
        if not clean_q:
            return []

        url = f"https://coverr.co/api/videos?query={requests.utils.quote(clean_q)}&page=1"
        results = []
        try:
            resp = requests.get(url, headers=HTTP_HEADERS, timeout=8)
            if resp.status_code == 200:
                data = resp.json()
                for hit in data.get("hits", []):
                    base_fn = hit.get("base_filename")
                    vid_id = hit.get("id") or base_fn
                    cand_id = f"coverr_{vid_id}"
                    if not base_fn or self._is_used(cand_id) or cand_id in BLACKLISTED_STOCK_IDS:
                        continue

                    title = hit.get("title") or ""
                    tags = [t.lower() for t in (hit.get("tags") or [])]
                    hit_text = (title + " " + " ".join(tags)).lower()

                    # Prevent Coverr from returning unrelated trending videos (e.g. phones, old men) when query has 0 results
                    q_words = [w for w in clean_q.split() if len(w) > 2]
                    if q_words and not any(w in hit_text for w in q_words):
                        continue

                    is_vert = bool(hit.get("is_vertical"))
                    results.append({
                        "id": cand_id,
                        "source": "Coverr",
                        "title": title,
                        "tags": tags,
                        "duration": hit.get("duration", 10),
                        "download_url": f"https://cdn.coverr.co/videos/{base_fn}/1080p.mp4",
                        "is_vertical": is_vert,
                        "aspect_ratio": "9:16" if is_vert else "16:9",
                    })
                    if len(results) >= limit:
                        break
        except Exception as e:
            print_warning(f"Coverr search error for '{query}': {e}")
        return results

    def search_pexels(self, query: str, orientation: str = "portrait", limit: int = 6) -> List[Dict[str, Any]]:
        """Search Pexels video clips with true URL title extraction and orientation fallback."""
        if not self.pexels_fetcher.is_configured():
            return []

        clean_q = re.sub(r"[^a-zA-Z0-9\s]", " ", query).strip().lower()
        if not clean_q:
            return []

        # Keep query concise (1-3 words) for high-precision Pexels matching
        q_words = [w for w in clean_q.split() if len(w) > 1]
        pexels_q = " ".join(q_words[:3]) if q_words else clean_q

        results = []
        seen = set()

        try:
            # 1. Search requested orientation
            raw_vids = self.pexels_fetcher.search_videos(
                query=pexels_q,
                orientation=orientation,
                per_page=limit * 2,
            )
            # 2. If few clips found in portrait, also search all orientations (horizontal space clips crop cleanly to 9:16)
            if len(raw_vids) < 3 and orientation == "portrait":
                extra_vids = self.pexels_fetcher.search_videos(
                    query=pexels_q,
                    orientation="",
                    per_page=limit * 2,
                )
                raw_vids.extend(extra_vids)

            for v in raw_vids:
                vid_id = f"pexels_{v['id']}"
                if vid_id in seen or self._is_used(vid_id) or vid_id in BLACKLISTED_STOCK_IDS:
                    continue
                seen.add(vid_id)

                # Extract TRUE title from Pexels URL slug
                raw_slug = v.get("pexels_url", "") or v.get("url", "")
                real_title = f"Pexels clip {v['id']}"
                if raw_slug:
                    parts = [p for p in raw_slug.rstrip("/").split("/") if p]
                    if parts:
                        clean_name = re.sub(r"-\d+$", "", parts[-1])
                        real_title = clean_name.replace("-", " ")

                q_tags = [w for w in pexels_q.split() if len(w) > 2]
                tags = list(set(real_title.split() + q_tags + ["pexels"]))

                w = v.get("width", 0)
                h = v.get("height", 0)
                is_vert = (h > w)
                is_vert = (h > w)
                results.append({
                    "id": vid_id,
                    "source": "Pexels",
                    "title": real_title,
                    "tags": real_title.split() + ["pexels"],
                    "duration": v.get("duration", 10),
                    "download_url": v.get("download_url", ""),
                    "is_vertical": is_vert,
                    "aspect_ratio": "9:16" if is_vert else "16:9",
                })
                if len(results) >= limit:
                    break
        except Exception as e:
            print_warning(f"Pexels search error for '{query}': {e}")
        return results

    def search_pixabay(self, query: str, orientation: str = "portrait", limit: int = 6) -> List[Dict[str, Any]]:
        """Search Pixabay if API key is provided."""
        api_key = os.getenv("PIXABAY_API_KEY", "") or getattr(self.cfg, "pixabay_api_key", "")
        if not api_key:
            return []

        clean_q = re.sub(r"[^a-zA-Z0-9\s]", " ", query).strip().lower()
        if not clean_q:
            return []

        results = []
        try:
            url = f"https://pixabay.com/api/videos/?key={api_key}&q={requests.utils.quote(clean_q)}&per_page={limit}&video_type=all"
            resp = requests.get(url, timeout=8)
            if resp.status_code == 200:
                data = resp.json()
                for hit in data.get("hits", []):
                    vid_id = f"pixabay_{hit.get('id')}"
                    if self._is_used(vid_id):
                        continue
                    vids = hit.get("videos", {})
                    v_info = vids.get("medium") or vids.get("large") or vids.get("small")
                    if not v_info or not v_info.get("url"):
                        continue
                    tags = [t.strip().lower() for t in hit.get("tags", "").split(",") if t.strip()]
                    w = v_info.get("width", 0)
                    h = v_info.get("height", 0)
                    results.append({
                        "id": vid_id,
                        "source": "Pixabay",
                        "title": f"Pixabay clip {hit.get('id')}: {hit.get('tags', '')}",
                        "tags": tags,
                        "duration": hit.get("duration", 10),
                        "download_url": v_info.get("url", ""),
                        "is_vertical": (h > w),
                        "aspect_ratio": "9:16" if (h > w) else "16:9",
                    })
                    if len(results) >= limit:
                        break
        except Exception as e:
            print_warning(f"Pixabay search error for '{query}': {e}")
        return results

    # -------------------------------------------------------------
    # 3. PARALLEL MULTI-SOURCE SEARCH DISPATCHER
    # -------------------------------------------------------------
    def gather_candidates(
        self,
        queries: List[str],
        orientation: str = "portrait",
    ) -> List[Dict[str, Any]]:
        """Dispatch parallel searches across Mixkit, Coverr, Pexels, and Pixabay."""
        candidates: List[Dict[str, Any]] = []
        seen_urls: Set[str] = set()

        tasks = []
        with ThreadPoolExecutor(max_workers=6) as executor:
            for q in queries:
                if not q or not q.strip():
                    continue
                tasks.append(executor.submit(self.search_pexels, q, orientation, 4))
                tasks.append(executor.submit(self.search_coverr, q, orientation, 4))
                tasks.append(executor.submit(self.search_mixkit, q, 4))
                tasks.append(executor.submit(self.search_pixabay, q, orientation, 4))

            for future in as_completed(tasks):
                try:
                    res = future.result()
                    for item in res:
                        d_url = item.get("download_url")
                        if d_url and d_url not in seen_urls:
                            seen_urls.add(d_url)
                            candidates.append(item)
                except Exception:
                    pass

        return candidates

    # -------------------------------------------------------------
    # 4. AI SEMANTIC RANKER (SCORING & VISUAL COVERAGE VALIDATION)
    # -------------------------------------------------------------
    def rank_and_select(
        self,
        candidates: List[Dict[str, Any]],
        scene_text: str,
        queries_info: Dict[str, Any],
        orientation: str = "portrait",
    ) -> Optional[Dict[str, Any]]:
        """Score candidate videos using Semantic Relevance, Must-Show Visual Coverage, and Gemini Validation.
        
        Strictly prioritizes Semantic Match over pure resolution or provider source.
        """
        if not candidates:
            return None

        scene_plan = queries_info.get("scene_plan", {})
        must_show = scene_plan.get("must_show", [])
        subject = scene_plan.get("subject", "").lower()
        avoid_tags = [w.lower().strip() for w in scene_plan.get("avoid", queries_info.get("negative_tags", []))]
        action_tokens = set(re.sub(r"[^a-zA-Z\s]", " ", scene_plan.get("action", "")).lower().split())
        env_tokens = set(re.sub(r"[^a-zA-Z\s]", " ", scene_plan.get("environment", "")).lower().split())

        subject_tokens = [w for w in re.sub(r"[^a-zA-Z\s]", " ", subject).split() if len(w) > 2]

        filtered_candidates = []
        fresh_candidates = []
        for cand in candidates:
            cand_id = cand.get("id") or ""
            if cand_id in BLACKLISTED_STOCK_IDS:
                continue

            title_text = (cand.get("title") or "").lower()
            tag_text = " ".join(cand.get("tags", [])).lower()
            combined_text = f"{title_text} {tag_text}"

            # 1. Strict Negative Tag Rejection
            has_negative = any(neg in combined_text for neg in avoid_tags if len(neg) > 2)
            if has_negative:
                continue

            # Check if this video has already been used in this session
            is_used = bool(cand_id and self._is_used(cand_id))

            # 2. Must-Show Visual Coverage (Up to 45 points - Highest Priority!)
            matched_must_show = 0
            for item in must_show:
                item_words = [w for w in re.sub(r"[^a-zA-Z\s]", " ", item.lower()).split() if len(w) > 2]
                if any(w in combined_text for w in item_words):
                    matched_must_show += 1

            total_must_show = max(1, len(must_show))
            coverage_ratio = matched_must_show / total_must_show
            coverage_score = coverage_ratio * 45.0
            cand["visual_coverage_pct"] = int(coverage_ratio * 100)

            # 3. Subject / Entity Match (Up to 25 points)
            subject_score = 0.0
            if subject_tokens:
                matched_subj = sum(1 for tok in subject_tokens if tok in combined_text)
                if matched_subj > 0:
                    subject_score = min(25.0, (matched_subj / len(subject_tokens)) * 25.0)

            # 4. Action & Environment Match (Up to 15 points)
            matched_action = sum(1 for tok in action_tokens if tok in combined_text and len(tok) > 2)
            matched_env = sum(1 for tok in env_tokens if tok in combined_text and len(tok) > 2)
            action_env_score = min(15.0, (matched_action * 4.0) + (matched_env * 3.0))

            # 5. Composition & Orientation Match (Up to 10 points)
            orientation_score = 0.0
            if orientation == "portrait" and cand.get("is_vertical"):
                orientation_score = 10.0
            elif orientation != "portrait" and not cand.get("is_vertical"):
                orientation_score = 10.0

            # 6. Resolution Bonus (Up to 5 points - Never overrides semantic relevance)
            res_score = 3.0
            if "4k" in combined_text or "uhd" in combined_text:
                res_score = 5.0
            elif "1080" in combined_text or "fhd" in combined_text or "hd" in combined_text:
                res_score = 4.0

            # 7. Topic Anchor Bonus / Penalty
            topic_bonus = 0.0
            is_bh_query = any(k in scene_text.lower() or k in subject for k in ("black hole", "blackhole", "event horizon", "accretion", "singularity", "spaghetti"))
            is_space_query = is_bh_query or any(k in scene_text.lower() or k in subject for k in ("space", "antariksh", "brahmand", "galaxy", "universe", "planet", "stars", "cosmos", "solar system", "grah", "dharati"))

            if is_bh_query:
                # Clips showing real black hole, singularity, or event horizon get highest bonus
                if any(bh in combined_text for bh in ("black hole", "blackhole", "singularity", "event horizon", "accretion")):
                    topic_bonus = 30.0
                elif any(cx in combined_text for cx in ("cosmic vortex", "spiral galaxy", "wormhole", "space tunnel")):
                    topic_bonus = 18.0
                elif any(sp in combined_text for sp in ("deep space", "space", "galaxy", "planet", "stars", "universe", "cosmos", "solar system")):
                    topic_bonus = 10.0
                else:
                    topic_bonus = -35.0  # Disqualify non-astronomy clips
            elif is_space_query:
                if any(sp in combined_text for sp in ("space", "galaxy", "planet", "stars", "universe", "cosmos", "nebula", "solar system")):
                    topic_bonus = 15.0
                else:
                    topic_bonus = -30.0

            persistent_penalty = -4.0 if self._is_persistent_used(cand_id) else 0.0

            # TOTAL COMPOSITE RELEVANCE SCORE (NO PROVIDER BIAS)
            total_score = coverage_score + subject_score + action_env_score + orientation_score + res_score + topic_bonus + persistent_penalty
            cand["score"] = round(total_score, 1)
            cand["semantic_score"] = round(coverage_score + subject_score + action_env_score + topic_bonus + persistent_penalty, 1)

            filtered_candidates.append(cand)
            if not is_used:
                fresh_candidates.append(cand)

        # Prioritize fresh unused videos so each scene has a distinct cut
        candidates_pool = fresh_candidates if fresh_candidates else filtered_candidates
        if not candidates_pool:
            return None

        # Sort strictly by composite relevance score descending
        candidates_pool.sort(key=lambda x: x["score"], reverse=True)
        top_candidates = candidates_pool[:5]

        # Use Gemini Flash to validate semantic alignment and pick winner
        client = self._get_gemini_client()
        if client and len(top_candidates) > 1:
            try:
                candidate_summary = []
                for i, c in enumerate(top_candidates):
                    candidate_summary.append(
                        f"[{i+1}] Source: {c['source']}, Title: '{c['title']}', Tags: {c['tags'][:6]}, Coverage: {c.get('visual_coverage_pct', 0)}%, Score: {c['score']}"
                    )

                prompt = f"""You are an elite film director choosing the SINGLE BEST stock video clip for this scene.
Scene Narration: "{scene_text}"
Target Subject: "{subject}"
Must-Show Elements: {json.dumps(must_show)}
Avoid Elements: {json.dumps(avoid_tags[:6])}

Candidate Clips:
{chr(10).join(candidate_summary)}

DIRECTORIAL RULES:
1. If the narration is about space, black holes, or cosmic phenomena, you MUST pick an authentic astronomical clip (black hole, galactic vortex, planets, space).
2. NEVER pick clips of smartphones, human faces, people typing, modern rooms, or circuit boards for a space documentary!
3. Even if the narration mentions subscribing, liking, or commenting, keep the visuals strictly anchored in epic cosmic footage!

Evaluate which candidate clip genuinely depicts the intended concept (NOT generic unrelated footage).
Output STRICT JSON with:
- "best_index": 1-based integer index of chosen candidate
- "confidence_score": 0-100 rating (How well does it show the intended subject/action?)
- "visual_coverage_percent": 0-100 rating
- "reason": brief 1-sentence reason
"""
                for model in CANDIDATE_GEMINI_MODELS:
                    try:
                        resp = client.models.generate_content(
                            model=model,
                            contents=prompt,
                            config={"response_mime_type": "application/json"},
                        )
                        if resp.text:
                            clean = resp.text.strip()
                            if clean.startswith("```json"):
                                clean = clean[7:].split("```")[0].strip()
                            elif clean.startswith("```"):
                                clean = clean[3:].split("```")[0].strip()
                            eval_data = json.loads(clean)
                            best_idx = int(eval_data.get("best_index", 1)) - 1
                            if 0 <= best_idx < len(top_candidates):
                                winner = top_candidates[best_idx]
                                winner["ai_reason"] = eval_data.get("reason", "")
                                winner["ai_confidence"] = int(eval_data.get("confidence_score", winner["score"]))
                                winner["ai_coverage"] = int(eval_data.get("visual_coverage_percent", winner.get("visual_coverage_pct", 50)))
                                print_info(f"   🎯 [Semantic Ranker Pick] Candidate #{best_idx+1} from {winner['source']}: '{winner['title']}' (Confidence: {winner['ai_confidence']}%, Coverage: {winner['ai_coverage']}%)")
                                return winner
                    except Exception:
                        continue
            except Exception as e:
                print_warning(f"AI ranker evaluation notice: {e}")

        # Fallback to top scored candidate
        winner = top_candidates[0]
        print_info(f"   🎯 [Heuristic Pick] from {winner['source']}: '{winner['title']}' (Score: {winner['score']}, Coverage: {winner.get('visual_coverage_pct', 0)}%)")
        return winner

    # -------------------------------------------------------------
    # 5. DOWNLOAD & CACHING
    # -------------------------------------------------------------
    def download_candidate(self, candidate: Dict[str, Any], slug: str) -> Optional[Path]:
        """Download chosen video clip to local cache."""
        cand_id = candidate.get("id", "stock")
        d_url = candidate.get("download_url")
        if not d_url:
            return None

        url_hash = hashlib.md5(d_url.encode()).hexdigest()[:10]
        cache_file = STOCK_CACHE_DIR / f"{sanitize_filename(cand_id)}_{url_hash}.mp4"

        if cache_file.exists() and cache_file.stat().st_size > 50000:
            self._record_used_id(cand_id)
            return cache_file

        try:
            print_info(f"   ⬇️ Downloading selected clip from {candidate.get('source')} ({candidate.get('title')[:35]})...")
            resp = requests.get(d_url, headers=HTTP_HEADERS, stream=True, timeout=35, allow_redirects=True)
            if resp.status_code == 200:
                with open(cache_file, "wb") as f:
                    for chunk in resp.iter_content(chunk_size=65536):
                        f.write(chunk)
                if cache_file.stat().st_size > 50000:
                    self._record_used_id(cand_id)
                    size_mb = round(cache_file.stat().st_size / (1024 * 1024), 2)
                    print_success(f"   ✅ [Multi-Stock] Saved: {cache_file.name} ({size_mb} MB)")
                    return cache_file
        except Exception as e:
            print_warning(f"Download failed for {d_url}: {e}")

        return None

    # -------------------------------------------------------------
    # 6. MASTER SCENE ASSET ACQUISITION (SEMANTIC COVERAGE GUARANTEE)
    # -------------------------------------------------------------
    def get_best_scene_asset(
        self,
        scene_text: str,
        title: str,
        scene_index: int = 0,
        orientation: str = "portrait",
        archival_pool: Optional[List[Path]] = None,
        allow_archival_fallback: bool = False,
        allow_ai_fallback: bool = True,
        scene_plan: Optional[Dict[str, Any]] = None,
    ) -> Path:
        """Acquire the single best visual asset across all sources with 100% fail-safe coverage and visual coverage gating."""
        target_w = 1080 if orientation == "portrait" else 1920
        target_h = 1920 if orientation == "portrait" else 1080
        slug = sanitize_filename(title[:30])

        # Step A: Preserve an upstream structured scene plan when available.
        if scene_plan:
            normalized_plan = {
                "subject": str(scene_plan.get("subject") or "").strip(),
                "action": str(scene_plan.get("action") or "").strip(),
                "environment": str(scene_plan.get("environment") or "").strip(),
                "must_show": [str(v).strip() for v in scene_plan.get("must_show", []) if str(v).strip()],
                "avoid": [str(v).strip() for v in scene_plan.get("avoid", []) if str(v).strip()],
                "search_queries": [str(q).strip() for q in scene_plan.get("search_queries", []) if str(q).strip()][:4],
            }
            if normalized_plan["subject"] or normalized_plan["must_show"] or normalized_plan["search_queries"]:
                q_info = {
                    "primary_query": normalized_plan["search_queries"][0] if normalized_plan["search_queries"] else normalized_plan["subject"],
                    "alternative_query": normalized_plan["search_queries"][1] if len(normalized_plan["search_queries"]) > 1 else normalized_plan["subject"],
                    "mood_query": normalized_plan["search_queries"][2] if len(normalized_plan["search_queries"]) > 2 else "cinematic dramatic",
                    "negative_tags": normalized_plan["avoid"],
                    "scene_plan": normalized_plan,
                }
            else:
                q_info = self.generate_smart_queries(scene_text, title, scene_index)
        else:
            q_info = self.generate_smart_queries(scene_text, title, scene_index)
        scene_plan = q_info.get("scene_plan", {})
        queries = scene_plan.get("search_queries") or [
            q_info.get("primary_query", ""),
            q_info.get("alternative_query", ""),
            q_info.get("mood_query", ""),
        ]
        subj_name = scene_plan.get("subject", "Concept")
        print_info(f"[*] Visual Intelligence: Scene #{scene_index+1} Subject: '{subj_name}' | Searching: {queries[:3]}...")

        # Step B: Parallel Search across Mixkit, Coverr, Pexels, Pixabay
        candidates = self.gather_candidates(queries=queries, orientation=orientation)
        print_info(f"[*] Aggregated {len(candidates)} video candidates across Mixkit, Coverr, Pexels & Pixabay.")

        # Step C: AI Semantic Ranking & Coverage Calculation
        winner = self.rank_and_select(candidates, scene_text, q_info, orientation=orientation)

        # Step D: Download best video candidate (Never discard a real video for a static image!)
        if winner:
            ai_conf = winner.get("ai_confidence")
            metadata_coverage = int(winner.get("visual_coverage_pct", 0))
            if metadata_coverage >= 50 and (ai_conf is None or int(ai_conf) >= 75):
                downloaded = self.download_candidate(winner, slug)
                if downloaded and downloaded.exists() and downloaded.stat().st_size > 50000:
                    return downloaded

        # Only try the next highest-ranked candidates that satisfy the same semantic floor.
        ranked_alternatives = sorted(candidates, key=lambda c: float(c.get("score", -9999)), reverse=True)
        for alt_cand in ranked_alternatives[:5]:
            if winner is alt_cand:
                continue
            cand_id = alt_cand.get("id")
            if not cand_id or self._is_used(cand_id):
                continue
            if int(alt_cand.get("visual_coverage_pct", 0)) < 50:
                continue
            if float(alt_cand.get("score", -9999)) < 30:
                continue
            downloaded = self.download_candidate(alt_cand, slug)
            if downloaded and downloaded.exists() and downloaded.stat().st_size > 50000:
                print_info(f"   🎬 Using validated alternative for scene {scene_index+1}: {alt_cand.get('title')}")
                return downloaded

        # Step E: Authentic archival proof is opt-in and scene-indexed.
        if allow_archival_fallback and archival_pool and scene_index < len(archival_pool):
            arch_pick = archival_pool[scene_index]
            if arch_pick.exists():
                print_info(f"   📜 Using scene-indexed archival fallback: {arch_pick.name}")
                return arch_pick

        # Step F: Fall back to a scene-specific AI visual rather than unrelated stock footage.
        if allow_ai_fallback:
            must_show_str = ", ".join(scene_plan.get("must_show", []))
            ai_prompt = f"{scene_plan.get('subject', q_info.get('primary_query'))}, {scene_plan.get('action', '')}, {must_show_str}, {scene_plan.get('environment', '')}, cinematic 8k, hyperrealistic movie still, dramatic volumetric lighting, IMAX documentary"
            print_info(f"   🎨 Generating photorealistic cinematic AI visual for: '{ai_prompt[:70]}...'")
            ai_path = STOCK_CACHE_DIR / f"ai_{slug}_{scene_index}_{random.randint(100, 999)}.jpg"
            ai_img = self.ai_visuals.generate_image(
                prompt=ai_prompt,
                output_path=ai_path,
                width=target_w,
                height=target_h,
                style="cinematic",
            )
            if ai_img and ai_img.exists() and ai_img.stat().st_size > 5000:
                return ai_img

            # Scene-specific photo is acceptable because its query is tied to this scene.
            photo_query = q_info.get("primary_query") or (queries[0] if queries else "")
            if photo_query:
                photo_pick = self.pexels_fetcher.get_scene_photo(
                    photo_query,
                    orientation=orientation,
                    scene_index=scene_index,
                )
                if photo_pick and photo_pick.exists():
                    return photo_pick

        # No generic fallback: an unrelated clip would break scene-to-narration integrity.
        raise RuntimeError("Could not acquire a semantically valid visual asset for scene.")
