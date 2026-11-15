"""Trending Tech, AI, Science & Space News Collector.
Scans global RSS feeds and NASA API to select the #1 high-impact viral story of the day.
"""

import json
import logging
import os
import re
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any, Dict, List, Optional
import requests

from google import genai
from google.genai import types

from autotube.config import get_config, PROJECT_ROOT
from autotube.utils.console import print_error, print_info, print_success, print_warning

logger = logging.getLogger(__name__)

CACHE_DIR = PROJECT_ROOT / "assets" / "news_cache"
CACHE_DIR.mkdir(parents=True, exist_ok=True)


class TrendingNewsCollector:
    """Discovers and curates the single most compelling viral Tech, AI, or Space story."""

    def __init__(self):
        self.config = get_config()
        self.api_key = os.getenv("GEMINI_API_KEY") or getattr(self.config, "gemini_api_key", "")
        self.client = None
        if self.api_key:
            try:
                self.client = genai.Client(
                    api_key=self.api_key,
                    http_options=types.HttpOptions(timeout=30000),
                )
            except Exception as e:
                logger.warning(f"Could not initialize Gemini client: {e}")

    def fetch_rss_items(self, query: Optional[str] = None, max_items: int = 40) -> List[Dict[str, str]]:
        """Fetch news headlines from Google News RSS."""
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AutoTube/1.0"}
        urls = []
        if query:
            q_enc = urllib.parse.quote(query)
            urls.append(f"https://news.google.com/rss/search?q={q_enc}&hl=en-US&gl=US&ceid=US:en")
        else:
            urls.append("https://news.google.com/rss/headlines/section/topic/TECHNOLOGY?hl=en-US&gl=US&ceid=US:en")
            urls.append("https://news.google.com/rss/headlines/section/topic/SCIENCE?hl=en-US&gl=US&ceid=US:en")

        collected = []
        seen_titles = set()

        for url in urls:
            try:
                req = urllib.request.Request(url, headers=headers)
                with urllib.request.urlopen(req, timeout=12) as resp:
                    xml_data = resp.read()
                root = ET.fromstring(xml_data)
                for item in root.findall("./channel/item"):
                    title_elem = item.find("title")
                    link_elem = item.find("link")
                    date_elem = item.find("pubDate")
                    desc_elem = item.find("description")

                    if title_elem is not None and title_elem.text:
                        raw_title = title_elem.text.strip()
                        # Clean source suffix like " - Reuters" or " - The Verge"
                        clean_title = re.sub(r"\s+-\s+[^-]+$", "", raw_title).strip()
                        if clean_title.lower() not in seen_titles:
                            seen_titles.add(clean_title.lower())
                            collected.append({
                                "title": clean_title,
                                "raw_title": raw_title,
                                "link": link_elem.text.strip() if link_elem is not None else "",
                                "date": date_elem.text.strip() if date_elem is not None else "",
                                "snippet": desc_elem.text.strip() if desc_elem is not None else "",
                            })
                            if len(collected) >= max_items:
                                break
            except Exception as e:
                logger.warning(f"Error fetching RSS from {url}: {e}")

        return collected

    def curate_top_story(self, candidates: List[Dict[str, str]]) -> Dict[str, Any]:
        """Use Gemini to evaluate candidates and select the #1 most viral story for CosmoChronicle."""
        if not candidates:
            # Fallback story if network fails
            return {
                "headline_en": "NVIDIA CEO Declares Future of Coding is Dead Due to AI",
                "category": "TECH & AI UPDATE",
                "tag_hindi": "NVIDIA CEO का बड़ा ऐलान",
                "subject": "Jensen Huang",
                "summary": "NVIDIA CEO Jensen Huang stated at the World Government Summit that people should stop learning to program because AI will do all programming in human language.",
                "search_query": "Jensen Huang",
                "source": "World Government Summit",
            }

        titles_text = "\n".join([f"{i+1}. {c['title']}" for i, c in enumerate(candidates[:25])])
        prompt = f"""You are the Editor-in-Chief for CosmoChronicle, a futuristic science, space, and tech media brand.
Analyze these current trending news headlines and select the SINGLE MOST SHOCKING, VIRAL, AND ENGAGING STORY that will trigger massive debate and comments on social media (topics like NVIDIA, Jensen Huang, OpenAI/AGI, Elon Musk/SpaceX, humanoid robots, NASA breakthroughs, or quantum physics are preferred).

Headlines:
{titles_text}

Respond STRICTLY with a valid JSON object matching this schema:
{{
  "selected_index": <1-based number>,
  "category": "<TECH & AI UPDATE or SPACE & SCIENCE UPDATE>",
  "tag_hindi": "<Short 4-5 words Hindi tag e.g. NVIDIA CEO का बड़ा ऐलान or जेम्स वेब का बड़ा खुलासा>",
  "headline_en": "<Engaging English news summary title>",
  "subject": "<Main person, mission, or company e.g. Jensen Huang or James Webb or Elon Musk>",
  "summary": "<2-3 sentence explanation of the news facts>",
  "search_query": "<Exact 1-2 words search query to find high-res press photo e.g. Jensen Huang or James Webb Telescope>",
  "photo_credit": "<Likely press credit e.g. Reuters / NASA / NVIDIA Press>"
}}
"""
        if self.client:
            for model_name in ["gemini-3.5-flash-lite", "gemini-flash-lite-latest", "gemini-3.1-flash-lite"]:
                try:
                    resp = self.client.models.generate_content(
                        model=model_name,
                        contents=prompt,
                        config=types.GenerateContentConfig(
                            temperature=0.2,
                            response_mime_type="application/json",
                        ),
                    )
                    parsed = json.loads(resp.text)
                    sel_idx = parsed.get("selected_index", 1) - 1
                    if 0 <= sel_idx < len(candidates):
                        parsed["source_url"] = candidates[sel_idx].get("link", "")
                    return parsed
                except Exception as e:
                    logger.warning(f"Error curating story with {model_name}: {e}")

        # Fallback to first candidate
        first = candidates[0]
        return {
            "category": "TECH & AI UPDATE",
            "tag_hindi": "ताज़ा टेक अपडेट",
            "headline_en": first["title"],
            "subject": first["title"].split()[0],
            "summary": first["title"],
            "search_query": first["title"].split()[0],
            "photo_credit": "Press / Global Media",
            "source_url": first.get("link", ""),
        }

    def fetch_high_res_photo(self, search_query: str, subject: str = "") -> Optional[Path]:
        """Download high-resolution press photo from Wikipedia/Wikimedia Commons API or NASA Image API."""
        query = search_query.strip() or subject.strip() or "technology"
        cache_file = CACHE_DIR / f"{re.sub(r'[^a-zA-Z0-9]', '_', query).lower()[:30]}_hd.jpg"

        if cache_file.exists() and cache_file.stat().st_size > 20000:
            print_info(f"Using cached high-res photo: {cache_file.name}")
            return cache_file

        headers = {"User-Agent": "AutoTube/1.0 (contact@cosmochronicle.com)"}

        # 1. Try Wikimedia Commons API
        try:
            wiki_url = "https://commons.wikimedia.org/w/api.php"
            params = {
                "action": "query",
                "format": "json",
                "generator": "search",
                "gsrsearch": f"{query} photo",
                "gsrlimit": 8,
                "prop": "imageinfo",
                "iiprop": "url|size|mime",
            }
            r = requests.get(wiki_url, params=params, headers=headers, timeout=12)
            if r.status_code == 200:
                pages = r.json().get("query", {}).get("pages", {})
                for pid, p in pages.items():
                    info = p.get("imageinfo", [{}])[0]
                    mime = info.get("mime", "")
                    w = info.get("width", 0)
                    h = info.get("height", 0)
                    dl_url = info.get("url")
                    if "image" in mime and (w >= 800 or h >= 800) and dl_url and not dl_url.endswith(".svg"):
                        img_resp = requests.get(dl_url, headers=headers, timeout=15)
                        if img_resp.status_code == 200 and len(img_resp.content) > 30000:
                            with open(cache_file, "wb") as f:
                                f.write(img_resp.content)
                            print_success(f"Downloaded Wikimedia photo ({w}x{h}): {cache_file.name}")
                            return cache_file
        except Exception as e:
            logger.warning(f"Wikimedia photo fetch failed for '{query}': {e}")

        # 2. Try Wikipedia Page Thumbnail API
        search_terms = [t for t in [subject, query, " ".join(query.split()[:2])] if t]
        for term in search_terms:
            try:
                wp_url = "https://en.wikipedia.org/w/api.php"
                params = {
                    "action": "query",
                    "titles": term,
                    "prop": "pageimages",
                    "pithumbsize": "1280",
                    "format": "json",
                }
                r = requests.get(wp_url, params=params, headers=headers, timeout=8)
                if r.status_code == 200:
                    pages = r.json().get("query", {}).get("pages", {})
                    for pid, p in pages.items():
                        thumb = p.get("thumbnail", {}).get("source")
                        if thumb:
                            img_resp = requests.get(thumb, headers=headers, timeout=12)
                            if img_resp.status_code == 200 and len(img_resp.content) > 20000:
                                with open(cache_file, "wb") as f:
                                    f.write(img_resp.content)
                                print_success(f"Downloaded Wikipedia thumbnail: {cache_file.name}")
                                return cache_file
            except Exception as e:
                logger.warning(f"Wikipedia thumbnail fetch failed for '{term}': {e}")

        # 3. High quality fallback assets
        fb_dir = PROJECT_ROOT / "assets" / "news_fallback"
        if "jensen" in query.lower() or "nvidia" in query.lower():
            target = fb_dir / "jensen_huang.jpg"
            if target.exists():
                return target
        elif any(k in query.lower() for k in ("space", "nasa", "star", "galaxy", "telescope")):
            target = fb_dir / "space_galaxy.jpg"
            if target.exists():
                return target
        
        # Default to any available fallback
        for fb_candidate in [fb_dir / "jensen_huang.jpg", fb_dir / "space_galaxy.jpg"]:
            if fb_candidate.exists():
                return fb_candidate

        return None

    def get_todays_featured_story(self) -> Dict[str, Any]:
        """Full pipeline: Discover -> Curate -> Download Photo -> Return Story Dict."""
        print_info("🌐 Scanning global tech, AI & science news feeds...")
        query = "NVIDIA OR AI breakthrough OR OpenAI OR SpaceX OR NASA OR humanoid robot when:2d"
        candidates = self.fetch_rss_items(query=query, max_items=50)

        if not candidates:
            # Fallback to general tech
            candidates = self.fetch_rss_items(query=None, max_items=30)

        print_info(f"📰 Evaluating {len(candidates)} news candidates with Gemini...")
        story = self.curate_top_story(candidates)

        print_info(f"🎯 Selected Story: {story.get('headline_en')}")
        img_path = self.fetch_high_res_photo(
            search_query=story.get("search_query", story.get("subject", "")),
            subject=story.get("subject", ""),
        )
        story["image_path"] = str(img_path) if img_path else ""

        return story
