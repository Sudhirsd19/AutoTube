"""Archival & Real Incident Visual Fetcher.

Fetches authentic historical photographs, original newspaper scans, government inquiry documents,
and real historical artifacts from Wikimedia Commons and Wikipedia for real stories & true incidents.
"""

import os
import re
import json
import time
from pathlib import Path
from typing import List, Dict, Any, Optional

import requests
from PIL import Image

from autotube.config import PROJECT_ROOT, get_config
from autotube.utils.console import print_info, print_success, print_warning, print_error
from autotube.utils.file_utils import sanitize_filename

USER_AGENT = "AutoTubeArchivalBot/1.0 (https://autotube.ai; contact@autotube.ai) python-requests/2.31.0"
REQUEST_HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8",
}


class ArchivalFetcher:
    """Discovers and downloads authentic historical images, newspaper archives, and documentary proof photos."""

    def __init__(self):
        self.cfg = get_config()
        self.cache_dir = PROJECT_ROOT / "assets" / "archival_cache"
        self.temp_dir = PROJECT_ROOT / "temp" / "archival"
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.temp_dir.mkdir(parents=True, exist_ok=True)
        self.session = requests.Session()
        self.session.headers.update(REQUEST_HEADERS)

    def extract_archival_queries(self, topic: str, script_text: str, count: int = 6) -> List[str]:
        """Generate high-precision, concise English entity queries for archives using Gemini or smart heuristics."""
        gemini_key = os.getenv("GEMINI_API_KEY", "") or getattr(self.cfg, "gemini_api_key", "")

        ai_queries: List[str] = []
        if gemini_key:
            try:
                from google import genai
                client = genai.Client(api_key=gemini_key)

                prompt = f"""You are an archival documentary researcher.
We are making a documentary video about a real story / historical incident:
Title/Topic: "{topic}"
Script excerpt: "{script_text[:1400]}"

We need authentic historical photographs, genuine person portraits, vintage newspaper clippings, inquiry documents, and real location artifacts from public archives (Wikimedia Commons / Wikipedia).

CRITICAL SEARCH ENGINE RULE:
Archive search engines (Wikimedia Commons & Wikipedia) STRICTLY REQUIRE CONCISE ENTITY KEYWORDS!
- Each query MUST be 1 to 3 words maximum! (e.g. ["Shanti Devi", "Lugdi Devi", "Mahatma Gandhi", "Mathura", "Reincarnation", "1935 India", "Kedar Nath"]).
- NEVER output long descriptive phrases like "vintage street photography of Mathura" or "Shanti Devi reincarnation Delhi 1935".
- Target concrete real person names, aliases, historical years, specific cities/locations, and committee/case names.
- Return strictly a valid JSON array of strings: ["Entity 1", "Entity 2", ...]"""

                resp = None
                for model_name in ["gemini-3.5-flash-lite", "gemini-3.1-flash-lite", "gemini-3.5-flash", "gemini-3.8-flash"]:
                    for attempt in range(2):
                        try:
                            resp = client.models.generate_content(
                                model=model_name,
                                contents=prompt,
                                config={"response_mime_type": "application/json"}
                            )
                            if resp and resp.text:
                                break
                        except Exception:
                            time.sleep(0.5)
                    if resp and resp.text:
                        break

                raw_text = (resp.text if resp else "").strip()
                if "```json" in raw_text:
                    raw_text = raw_text.split("```json")[1].split("```")[0].strip()
                elif "```" in raw_text:
                    raw_text = raw_text.split("```")[1].split("```")[0].strip()

                queries = json.loads(raw_text) if raw_text else []
                if isinstance(queries, list) and len(queries) > 0:
                    for q in queries:
                        cleaned = str(q).strip()
                        # Enforce concise keywords (max 3 words)
                        w = cleaned.split()
                        if len(w) > 3:
                            cleaned = " ".join(w[:3])
                        if cleaned and cleaned not in ai_queries:
                            ai_queries.append(cleaned)
                    print_info(f"Archival AI extracted {len(ai_queries)} targeted entities: {ai_queries}")
            except Exception as e:
                print_warning(f"Gemini query extractor warning: {e}. Falling back to heuristic queries.")

        # Always supplement with extracted proper nouns and clean keywords from script & topic
        combined_text = f"{topic} {script_text}"
        named_entities = re.findall(r"\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*\b", combined_text)
        common_ignore = {
            "The", "This", "That", "When", "What", "Where", "Why", "How", "And", "For", "With",
            "Delhi", "India", "True", "Story", "Shorts", "Real", "Incident", "Like", "Subscribe",
            "Comment", "Yes", "No", "Video", "Shocking", "Truth", "Mystery", "Channel",
            "Jab", "Usne", "Yeh", "Woh", "Agar", "Lekin", "Kyunki", "Aap", "Aapka", "Aise",
            "Hume", "Inhe", "Unhone", "Yahan", "Baat", "Sabhi", "Sabse", "Bina", "Khud"
        }
        supplement_queries = []
        for e in named_entities:
            if e not in common_ignore and len(e.split()) <= 3 and e not in supplement_queries and e not in ai_queries:
                supplement_queries.append(e)

        # Determine primary historical entity/subject
        primary_subject = ""
        if ai_queries:
            # When AI extracted entities, the first entity is the primary historical subject
            primary_subject = ai_queries[0]
            final_queries = list(ai_queries)
        else:
            final_queries = list(supplement_queries)
            clean_topic = re.sub(r"[#\-_/:|😱🤯👁️]", " ", topic).strip()
            # Only use words if they are pure ASCII (English)
            topic_ascii_words = [w for w in clean_topic.split() if w.isascii() and len(w) > 2]
            if topic_ascii_words:
                primary_subject = " ".join(topic_ascii_words[:3])

        # If primary subject is clean English (ASCII), add targeted variations if not already present
        if primary_subject and primary_subject.isascii():
            variations = [f"{primary_subject} portrait", f"{primary_subject} vintage", f"{primary_subject} document"]
            for v in variations:
                if v not in final_queries and len(final_queries) < count + 3:
                    final_queries.append(v)

        # Fallback if queries still empty
        if not final_queries:
            final_queries = ["historical mystery", "vintage investigation", "ancient document", "archive photo"]

        print_info(f"Archival Search Engine: Resolved {len(final_queries)} clean search queries: {final_queries[:6]}")
        return final_queries[:max(count + 2, 8)]

    def search_wikimedia_commons(self, query: str, limit: int = 5) -> List[Dict[str, Any]]:
        """Search Wikimedia Commons for authentic image files matching the query."""
        try:
            # Keep query concise (max 3-4 words for Commons search precision)
            q_clean = " ".join(query.strip().split()[:4])
            url = "https://commons.wikimedia.org/w/api.php"
            params = {
                "action": "query",
                "format": "json",
                "generator": "search",
                "gsrnamespace": 6,
                "gsrsearch": q_clean,
                "gsrlimit": limit,
                "prop": "imageinfo",
                "iiprop": "url|mime|size|dimensions",
            }
            resp = self.session.get(url, params=params, timeout=10)
            if resp.status_code != 200:
                return []

            data = resp.json()
            pages = data.get("query", {}).get("pages", {})
            results = []
            forbidden_substrings = [
                "flag_of", "icon_", "symbol_", "logo_", "disambig_", "wikisource",
                "stub_", "crystal_clear", "folder", "arrow_", "red_pencile", ".svg",
                "blank", "map_", "location_map", "saarbrücken", "waldstraße", "empire_state",
                "street", "house", "hotel", "flower", "stamp_of_india_-_1993", "stamp_of_india_-_1964",
                "pxl_", "boarding pass", "terminal", "canso"
            ]
            if "airport" not in query.lower():
                forbidden_substrings.append("airport")

            for p in pages.values():
                title = p.get("title", "")
                title_lower = title.lower()
                if any(bad in title_lower for bad in forbidden_substrings):
                    continue

                imageinfo = p.get("imageinfo", [])
                if not imageinfo:
                    continue

                info = imageinfo[0]
                url_img = info.get("url")
                mime = info.get("mime", "").lower()
                width = info.get("width", 0)
                height = info.get("height", 0)

                if mime in ("image/jpeg", "image/png", "image/webp") and url_img:
                    if width >= 250 and height >= 250:
                        results.append({
                            "title": title.replace("File:", "").strip(),
                            "url": url_img,
                            "mime": mime,
                            "width": width,
                            "height": height,
                            "source": "wikimedia_commons"
                        })

            return results
        except Exception as e:
            print_warning(f"Wikimedia search failed for '{query}': {e}")
            return []

    def search_wikipedia_multi(self, query: str, limit: int = 3) -> List[Dict[str, Any]]:
        """Search Wikipedia using generator=search to get top matching articles and their lead authentic photos."""
        try:
            q_clean = " ".join(query.strip().split()[:3])
            url = "https://en.wikipedia.org/w/api.php"
            params = {
                "action": "query",
                "format": "json",
                "generator": "search",
                "gsrsearch": q_clean,
                "gsrlimit": limit,
                "prop": "pageimages|images",
                "pithumbsize": 1280,
            }
            resp = self.session.get(url, params=params, timeout=10)
            if resp.status_code != 200:
                return []

            data = resp.json()
            pages = data.get("query", {}).get("pages", {})
            results = []
            forbidden_substrings = [
                "flag_of", "icon_", "symbol_", "logo_", "disambig_", "wikisource",
                "stub_", ".svg", "blank", "map_", "location_map", "saarbrücken",
                "waldstraße", "empire_state", "street", "house", "hotel", "flower",
                "airport", "baggage_claim", "stamp_of"
            ]
            for p in pages.values():
                t = p.get("title", "")
                t_lower = t.lower()
                if any(bad in t_lower for bad in forbidden_substrings):
                    continue

                thumb = p.get("thumbnail", {}).get("source")
                if thumb:
                    results.append({
                        "title": f"Wikipedia: {p.get('title')}",
                        "url": thumb,
                        "mime": "image/jpeg",
                        "width": p.get("thumbnail", {}).get("width", 1000),
                        "height": p.get("thumbnail", {}).get("height", 1000),
                        "source": "wikipedia_article"
                    })
            return results
        except Exception as e:
            print_warning(f"Wikipedia search failed for '{query}': {e}")
            return []

    def search_wikipedia_article(self, topic: str) -> List[Dict[str, Any]]:
        """Fetch lead and article gallery images from specific Wikipedia article."""
        try:
            clean_topic = re.sub(r"[#\-_/:|😱🤯👁️]", " ", topic).strip()
            # Extract main 2-3 words
            words = [w for w in clean_topic.split() if len(w) > 2]
            clean_title = " ".join(words[:3]) if words else clean_topic
            url = "https://en.wikipedia.org/w/api.php"
            params = {
                "action": "query",
                "titles": clean_title,
                "prop": "pageimages|images",
                "pithumbsize": 1280,
                "format": "json"
            }
            resp = self.session.get(url, params=params, timeout=10)
            if resp.status_code != 200:
                return []

            data = resp.json()
            pages = data.get("query", {}).get("pages", {})
            results = []
            for p in pages.values():
                thumb = p.get("thumbnail", {}).get("source")
                if thumb:
                    results.append({
                        "title": f"Wikipedia Lead: {p.get('title')}",
                        "url": thumb,
                        "mime": "image/jpeg",
                        "width": p.get("thumbnail", {}).get("width", 1000),
                        "height": p.get("thumbnail", {}).get("height", 1000),
                        "source": "wikipedia_lead"
                    })

            return results
        except Exception as e:
            print_warning(f"Wikipedia search failed for '{topic}': {e}")
            return []

    def download_and_prepare_image(self, url: str, output_path: Path) -> Optional[Path]:
        """Download image, validate integrity, and save as crisp RGB image for FFmpeg Ken Burns zoompan."""
        try:
            resp = self.session.get(url, timeout=12)
            if resp.status_code != 200:
                return None

            data = resp.content
            if len(data) < 4096:  # Reject corrupted/tiny files
                return None

            with open(output_path, "wb") as f:
                f.write(data)

            # Validate and convert using PIL
            with Image.open(output_path) as img:
                img.verify()

            with Image.open(output_path) as img:
                if img.mode != "RGB":
                    img_rgb = img.convert("RGB")
                    img_rgb.save(output_path, format="JPEG", quality=95)

            return output_path
        except Exception as e:
            print_warning(f"Error downloading archival image ({url[:70]}...): {e}")
            if output_path.exists():
                try:
                    output_path.unlink()
                except Exception:
                    pass
            return None

    def fetch_archival_visuals(
        self,
        topic: str,
        script_text: str,
        count: int = 6,
        progress_callback = None
    ) -> List[Path]:
        """End-to-end archival acquisition: finds and prepares authentic historical photos & document proofs."""
        slug = sanitize_filename(topic[:30])
        queries = self.extract_archival_queries(topic=topic, script_text=script_text, count=count)

        if progress_callback:
            progress_callback(46, f"Querying historical archives for: {', '.join(queries[:3])}...")

        all_candidates: List[Dict[str, Any]] = []
        seen_urls = set()

        # 1. First check Wikipedia article for canonical lead photo
        canonical_target = queries[0] if queries else topic
        wiki_lead = []
        if canonical_target and canonical_target.isascii():
            wiki_lead = self.search_wikipedia_article(canonical_target)
            for item in wiki_lead:
                u = item["url"]
                if u not in seen_urls:
                    seen_urls.add(u)
                    all_candidates.append(item)

        # 2. Query both Wikipedia and Wikimedia Commons for each targeted entity query
        candidates_by_entity: Dict[str, List[Dict[str, Any]]] = {}
        for q in queries:
            cands = []
            # Search Wikipedia for authentic article lead images
            wiki_found = self.search_wikipedia_multi(q, limit=2)
            for item in wiki_found:
                if item["url"] not in seen_urls:
                    seen_urls.add(item["url"])
                    cands.append(item)

            # Search Wikimedia Commons for original historical photographs & archives
            commons_found = self.search_wikimedia_commons(q, limit=3)
            for item in commons_found:
                if item["url"] not in seen_urls:
                    seen_urls.add(item["url"])
                    cands.append(item)

            if cands:
                candidates_by_entity[q] = cands

        # 3. If archival candidates still low, supplement with Pexels authentic photos
        if len(all_candidates) + sum(len(v) for v in candidates_by_entity.values()) < count:
            try:
                from autotube.media.pexels_video import PexelsVideoFetcher
                pv = PexelsVideoFetcher()
                if pv.is_configured():
                    for q in queries[:4]:
                        p_photos = pv.search_photos(query=q, per_page=2)
                        for ph in p_photos:
                            if ph.get("download_url") and ph["download_url"] not in seen_urls:
                                seen_urls.add(ph["download_url"])
                                if q not in candidates_by_entity:
                                    candidates_by_entity[q] = []
                                candidates_by_entity[q].append({
                                    "title": f"Pexels Photo: {q}",
                                    "url": ph["download_url"],
                                    "mime": "image/jpeg",
                                    "width": ph["width"],
                                    "height": ph["height"],
                                    "source": "pexels_photo"
                                })
            except Exception as pe:
                print_warning(f"Archival Pexels supplement error: {pe}")

        # Round-robin selection across distinct entities to guarantee diverse story coverage
        all_candidates = list(wiki_lead)
        while len(all_candidates) < count * 2 and any(candidates_by_entity.values()):
            added = 0
            for q in list(candidates_by_entity.keys()):
                items = candidates_by_entity[q]
                if items:
                    all_candidates.append(items.pop(0))
                    added += 1
            if added == 0:
                break

        print_info(f"Archival search selected {len(all_candidates)} diverse authentic candidates across {len(candidates_by_entity)} entities.")

        downloaded_paths: List[Path] = []
        for idx, cand in enumerate(all_candidates):
            if len(downloaded_paths) >= count:
                break

            media_kind = cand.get("media_kind", "image")
            suffix = ".mp4" if media_kind == "video" else ".jpg"
            target_media = self.temp_dir / f"archival_{slug}_{idx}_{int(time.time())}{suffix}"
            if progress_callback:
                progress_callback(
                    48 + int((len(downloaded_paths) / max(1, count)) * 6),
                    f"Acquiring authentic archival media ({len(downloaded_paths)+1}/{count}): {cand.get('title', '')[:35]}..."
                )

            if media_kind == "video":
                saved = self.download_and_prepare_video(cand["url"], target_media)
            else:
                saved = self.download_and_prepare_image(cand["url"], target_media)
            if saved and saved.exists():
                downloaded_paths.append(saved)
                print_success(f"Archival Proof Sourced: [{cand.get('source')}] {cand.get('title')} -> {saved.name}")

        return downloaded_paths
