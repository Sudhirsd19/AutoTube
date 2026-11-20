"""Trending Tech, AI, Science & Space News Collector.
Scans global RSS feeds and NASA API to select the #1 high-impact viral story of the day.
"""

import json
import logging
import os
import random
import re
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any, Dict, List, Optional, Set
import requests

from google import genai
from google.genai import types

from autotube.config import get_config, PROJECT_ROOT
from autotube.utils.console import print_error, print_info, print_success, print_warning

logger = logging.getLogger(__name__)

CACHE_DIR = PROJECT_ROOT / "assets" / "news_cache"
CACHE_DIR.mkdir(parents=True, exist_ok=True)
HISTORY_FILE = PROJECT_ROOT / "config" / "facebook_news_posts_history.json"
USED_NEWS_PHOTOS_FILE = PROJECT_ROOT / "config" / "used_news_photos.json"


def _load_used_news_photos() -> Set[str]:
    """Load previously used photo IDs or URLs to ensure 100% visual variety."""
    try:
        if USED_NEWS_PHOTOS_FILE.exists():
            with open(USED_NEWS_PHOTOS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, list):
                    return set(data)
    except Exception:
        pass
    return set()


def _record_used_news_photo(photo_id: str) -> None:
    """Record used photo ID or URL to prevent visual repetition."""
    try:
        used = _load_used_news_photos()
        used.add(str(photo_id))
        USED_NEWS_PHOTOS_FILE.parent.mkdir(parents=True, exist_ok=True)
        recent = list(used)[-500:]
        with open(USED_NEWS_PHOTOS_FILE, "w", encoding="utf-8") as f:
            json.dump(recent, f, indent=2)
    except Exception:
        pass

STOP_WORDS = {
    "this", "that", "with", "from", "have", "about", "will", "after", "into", "over",
    "under", "more", "most", "than", "been", "were", "what", "when", "where", "which",
    "their", "there", "these", "those", "could", "would", "should", "your", "news", "update",
    "says", "said", "just", "year", "years", "right", "report", "reported", "first", "second",
    "week", "month", "today", "yesterday", "also", "make", "makes", "time", "times", "team"
}

CLICKBAIT_BLACKLIST = {
    "forest on mars", "trees on mars", "face on mars", "alien face", "alien base",
    "pyramid on", "haunted", "ghost", "ufo secret", "ancient aliens", "conspiracy",
    "mars celebration", "eerie forest", "alien skull", "alien fossil", "spooky",
    "aliens built", "secret base on", "signs of aliens", "alien technology found",
    "alien civilization", "mysterious creature", "monster on"
}

NASA_BANNED_WORDS = {
    "pennsylvania", "celebration", "festival", "parade", "award", "ceremony",
    "administrator", "conference", "symposium", "meeting", "booth", "exhibit",
    "street", "store", "shop", "carpet", "hardware", "town", "headquarters",
    "visit", "handshake", "signing", "gala", "reception", "portrait", "speech"
}


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

    @staticmethod
    def extract_keywords(text: str) -> set:
        """Extract set of clean lowercase content tokens (>= 4 chars)."""
        words = re.findall(r"[a-zA-Z0-9]+", str(text).lower())
        return {w for w in words if len(w) >= 4 and w not in STOP_WORDS}

    def get_past_published_history(self, days: int = 14) -> List[Dict[str, Any]]:
        """Retrieve recent Facebook news posts history to prevent repeating the same story."""
        if not HISTORY_FILE.exists():
            return []
        try:
            with open(HISTORY_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                if not isinstance(data, list):
                    return []
                now = time.time()
                cutoff = now - (days * 86400)
                recent = []
                for entry in data:
                    ts = entry.get("timestamp", 0)
                    if ts > cutoff or not ts:
                        headline_en = entry.get("story", {}).get("headline_en", "") or entry.get("title", "")
                        subject = entry.get("story", {}).get("subject", "")
                        tokens = self.extract_keywords(headline_en)
                        if subject:
                            tokens.update(self.extract_keywords(subject))
                        recent.append({
                            "title": entry.get("title", ""),
                            "headline_en": headline_en,
                            "subject": subject,
                            "tokens": tokens,
                            "timestamp": ts,
                        })
                return recent
        except Exception as e:
            logger.warning(f"Could not load news history for deduplication: {e}")
            return []

    def is_duplicate_story(self, candidate_title: str, past_records: List[Dict[str, Any]]) -> bool:
        """Check if candidate headline matches or overlaps heavily with a recently published post."""
        cand_tokens = self.extract_keywords(candidate_title)
        if not cand_tokens:
            return False

        for rec in past_records:
            rec_tokens = rec.get("tokens", set())
            overlap = cand_tokens.intersection(rec_tokens)
            # 1. Direct key pair match (e.g. openai + robotics, or jensen + programming)
            if len(overlap) >= 2:
                return True
            # 2. Subject + 1 token match
            rec_subj = str(rec.get("subject", "")).lower()
            if rec_subj and rec_subj in candidate_title.lower() and len(overlap) >= 1:
                return True
            # 3. High Jaccard similarity
            union_len = len(cand_tokens.union(rec_tokens))
            if union_len > 0 and (len(overlap) / union_len) >= 0.30:
                return True

        return False

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

    def curate_top_story(
        self,
        candidates: List[Dict[str, str]],
        past_records: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """Use Gemini to evaluate candidates and select the #1 most viral FRESH story for CosmoChronicle."""
        if past_records is None:
            past_records = self.get_past_published_history(days=14)

        # 1. Programmatic Deduplication & Clickbait Guard: Strip duplicates & sensational pseudoscience
        fresh_candidates = [
            c for c in candidates
            if not self.is_duplicate_story(c["title"], past_records)
            and not any(bad in c["title"].lower() for bad in CLICKBAIT_BLACKLIST)
        ]
        if fresh_candidates:
            diff = len(candidates) - len(fresh_candidates)
            if diff > 0:
                print_info(f"🛡️ Quality & Anti-Repetition Guard: {diff} duplicate/tabloid stories filtered out.")
            candidates = fresh_candidates
        else:
            print_warning("All candidates filtered! Falling back to curated authoritative scientific milestones.")

        if not candidates:
            # Curated rotation of high-impact discoveries that have not been posted
            fallback_options = [
                {
                    "headline_en": "James Webb Space Telescope Unveils Cosmic Megastructure from Early Universe",
                    "category": "SPACE & SCIENCE UPDATE",
                    "tag_hindi": "जेम्स वेब का चौंकाने वाला खुलासा",
                    "subject": "James Webb Telescope",
                    "summary": "NASA's James Webb Space Telescope has uncovered an immense cosmic megastructure near the dawn of time, baffling astronomers and testing the standard model of cosmology.",
                    "search_query": "James Webb Space Telescope",
                    "photo_credit": "NASA / ESA / CSA",
                },
                {
                    "headline_en": "NVIDIA Unveils Revolutionary Quantum-AI Supercomputing Architecture",
                    "category": "TECH & AI UPDATE",
                    "tag_hindi": "NVIDIA का नया सुपरकंप्यूटिंग धमाका",
                    "subject": "Jensen Huang",
                    "summary": "NVIDIA announced a hybrid Quantum-Classical platform designed to simulate quantum physics using accelerated computing, accelerating breakthroughs in medicine and materials science.",
                    "search_query": "Jensen Huang NVIDIA",
                    "photo_credit": "NVIDIA Press",
                },
                {
                    "headline_en": "Neuralink Telepathy Patient Controls Computer Brain Interface Flawlessly in Live Demo",
                    "category": "TECH & AI UPDATE",
                    "tag_hindi": "न्यूरालिंक का नया लाइव चमत्कार",
                    "subject": "Neuralink",
                    "summary": "The first human recipient of the Neuralink brain-computer interface demonstrated rapid mental control over digital devices, setting a new benchmark for paralyzed patients.",
                    "search_query": "Neuralink",
                    "photo_credit": "Neuralink / Elon Musk",
                },
            ]
            for fb in fallback_options:
                if not self.is_duplicate_story(fb["headline_en"], past_records):
                    return fb
            return fallback_options[0]

        # 2. Build Prompt with explicit blacklist of recent stories
        titles_text = "\n".join([f"{i+1}. {c['title']}" for i, c in enumerate(candidates[:25])])
        blacklist_lines = [
            f"- {p.get('headline_en') or p.get('title')}"
            for p in past_records[:8]
            if p.get("headline_en") or p.get("title")
        ]
        blacklist_text = "\n".join(blacklist_lines) if blacklist_lines else "None recently."

        prompt = f"""You are the Editor-in-Chief for CosmoChronicle, an authoritative science, space, and tech media brand.
Analyze these current trending news headlines and select the SINGLE MOST AUTHORITATIVE, GROUNDBREAKING, AND CREDIBLE SCIENTIFIC/TECH STORY.

STRICT EDITORIAL RULES:
1. ABSOLUTE BAN ON TABLOID CLICKBAIT & PSEUDOSCIENCE: Reject any sensationalized stories claiming optical illusions or pareidolia are real (e.g. reject any story claiming "forest on Mars", "face on Moon", "pyramids in Antarctica", or secret alien bases). CosmoChronicle NEVER posts fake news or tabloid nonsense.
2. FOCUS ON REAL MILESTONES:
   - Genuine Space Discoveries: Authentic research from James Webb Space Telescope, Hubble, Mars Perseverance/Curiosity rovers, NASA, ESA, ISRO, or SpaceX missions.
   - Artificial Intelligence & Technology: Real product releases, breakthroughs, or scientific papers from OpenAI, Google DeepMind, Anthropic, NVIDIA, Meta, Microsoft, Apple.
   - Quantum Computing & Advanced Hardware: TSMC, Intel, IBM, NVIDIA supercomputers.
   - Neuroscience & Medicine: Neuralink, brain-computer interfaces, CRISPR, genetics, medical robotics.
3. The story MUST be authentic, exciting, and scientifically accurate.

STRICT ANTI-REPETITION MANDATE:
The following topics, themes, or events have ALREADY been published on our page recently:
{blacklist_text}

MANDATORY RULES:
1. You MUST NOT select any story that discusses, repeats, or covers the same events, companies doing the same actions, or subjects as the above list (e.g. if OpenAI Robotics or Robotics team disbandment is listed, DO NOT pick any robotics or OpenAI disbandment story).
2. Pick a COMPLETELY DIFFERENT, FRESH breakthrough topic (e.g. from NVIDIA, NASA/James Webb, SpaceX, Quantum Computing, Neuroscience/Neuralink, or Deep Space Discoveries).

Headlines:
{titles_text}

Respond STRICTLY with a valid JSON object matching this schema:
{{
  "selected_index": <1-based number>,
  "category": "<TECH & AI UPDATE or SPACE & SCIENCE UPDATE>",
  "tag_hindi": "<Short 4-5 words Hindi tag e.g. NVIDIA CEO का बड़ा ऐलान or जेम्स वेब का बड़ा खुलासा>",
  "headline_en": "<Engaging English news summary title>",
  "subject": "<Main person, mission, or company e.g. Jensen Huang or James Webb or Elon Musk or Neuralink>",
  "summary": "<2-3 sentence explanation of the news facts>",
  "search_query": "<Exact 1-2 words search query to find high-res press photo e.g. Jensen Huang or James Webb Telescope or Neuralink>",
  "photo_credit": "<Likely press credit e.g. Reuters / NASA / NVIDIA Press / SpaceX>"
}}
"""
        if self.client:
            for model_name in ["gemini-3.5-flash-lite", "gemini-flash-lite-latest", "gemini-3.1-flash-lite"]:
                try:
                    resp = self.client.models.generate_content(
                        model=model_name,
                        contents=prompt,
                        config=types.GenerateContentConfig(
                            temperature=0.5,
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

        # Fallback to first non-duplicate candidate
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

    def fetch_high_res_photo(
        self,
        search_query: str,
        subject: str = "",
        category: str = "",
        headline: str = "",
    ) -> Optional[Path]:
        """Download high-resolution, unique press or editorial photo tailored to the specific story."""
        query = search_query.strip() or subject.strip() or "technology"
        combined_text = f"{category} {query} {subject} {headline}".lower()
        used_ids = _load_used_news_photos()

        # Clean query tokens (strip stop words and punctuation)
        words = [w for w in re.findall(r"[a-zA-Z0-9]+", query) if w.lower() not in STOP_WORDS]
        clean_q = " ".join(words[:4]) or query
        ts = int(time.time())
        query_slug = re.sub(r'[^a-zA-Z0-9]', '_', clean_q).lower()[:25]

        headers = {"User-Agent": "AutoTube/1.0 (contact@cosmochronicle.com)"}

        # 1. Tier 1: NASA Images API (for Space, Astronomy, Cosmic, Telescopes)
        is_space = (
            "space" in combined_text
            or any(k in combined_text for k in ("nasa", "webb", "telescope", "mars", "galaxy", "cosmic", "starship", "spacex", "asteroid", "black hole", "universe", "planet", "astronomy"))
        )
        if is_space:
            try:
                if "mars" in combined_text:
                    space_term = "mars planet surface rover"
                elif "webb" in combined_text or "jwst" in combined_text:
                    space_term = "james webb space telescope deep field"
                elif "spacex" in combined_text or "starship" in combined_text:
                    space_term = "spacex starship rocket launch"
                elif "black hole" in combined_text:
                    space_term = "black hole event horizon accretion"
                else:
                    space_term = f"{clean_q} planet space astronomy"

                nasa_url = f"https://images-api.nasa.gov/search?q={urllib.parse.quote(space_term)}&media_type=image"
                r = requests.get(nasa_url, headers=headers, timeout=10)
                if r.status_code == 200:
                    items = r.json().get("collection", {}).get("items", [])
                    candidates = []
                    for it in items[:25]:
                        data_elem = it.get("data", [{}])[0]
                        nasa_id = data_elem.get("nasa_id", "")
                        title_str = str(data_elem.get("title", "")).lower()
                        desc_str = str(data_elem.get("description", "")).lower()
                        center_str = str(data_elem.get("center", "")).upper()
                        meta_text = f"{title_str} {desc_str}"

                        # Strictly reject PR events, town festivals (e.g. Mars, PA), ceremonies, handshakes
                        if center_str == "HQ" or any(bad in meta_text for bad in NASA_BANNED_WORDS):
                            continue

                        if nasa_id and nasa_id not in used_ids:
                            links = it.get("links", [])
                            for lk in links:
                                href = lk.get("href", "")
                                if href and (href.endswith(".jpg") or href.endswith(".png")):
                                    candidates.append((nasa_id, href))
                                    break
                    if candidates:
                        chosen_id, chosen_url = random.choice(candidates[:5])
                        img_resp = requests.get(chosen_url, headers=headers, timeout=15)
                        if img_resp.status_code == 200 and len(img_resp.content) > 25000:
                            out_file = CACHE_DIR / f"nasa_{query_slug}_{ts}.jpg"
                            with open(out_file, "wb") as f:
                                f.write(img_resp.content)
                            _record_used_news_photo(chosen_id)
                            print_success(f"Downloaded authentic NASA space photo: {out_file.name}")
                            return out_file
            except Exception as e:
                logger.warning(f"NASA image fetch failed for '{clean_q}': {e}")

        # 2. Tier 2: Pexels High-Resolution Stock Photos
        pexels_key = getattr(self.config, "pexels_api_key", None)
        if pexels_key:
            search_attempts = [clean_q]
            if subject and subject.lower() != clean_q.lower():
                search_attempts.append(subject)
            # Try key nouns from headline
            hl_nouns = [w for w in re.findall(r"[A-Za-z]{4,}", headline) if w.lower() not in STOP_WORDS]
            if hl_nouns:
                search_attempts.append(" ".join(hl_nouns[:3]))

            for attempt in search_attempts:
                try:
                    p_url = f"https://api.pexels.com/v1/search?query={urllib.parse.quote(attempt)}&per_page=15"
                    r = requests.get(p_url, headers={"Authorization": pexels_key}, timeout=10)
                    if r.status_code == 200:
                        photos = r.json().get("photos", [])
                        valid_photos = [
                            p for p in photos
                            if str(p.get("id")) not in used_ids and (p.get("width", 0) >= 800 or p.get("height", 0) >= 800)
                        ]
                        if valid_photos:
                            selected_photo = random.choice(valid_photos[:5])
                            photo_id = str(selected_photo.get("id"))
                            src = selected_photo.get("src", {})
                            dl_url = src.get("large2x") or src.get("large") or src.get("original")
                            if dl_url:
                                img_resp = requests.get(dl_url, timeout=15)
                                if img_resp.status_code == 200 and len(img_resp.content) > 30000:
                                    out_file = CACHE_DIR / f"pexels_{photo_id}_{query_slug}.jpg"
                                    with open(out_file, "wb") as f:
                                        f.write(img_resp.content)
                                    _record_used_news_photo(photo_id)
                                    print_success(f"Downloaded Pexels editorial photo for '{attempt}': {out_file.name}")
                                    return out_file
                except Exception as p_err:
                    logger.warning(f"Pexels photo fetch error for '{attempt}': {p_err}")

        # 3. Tier 3: Pixabay Photo API
        pixabay_key = getattr(self.config, "pixabay_api_key", None)
        if pixabay_key:
            try:
                pix_query = urllib.parse.quote(clean_q)
                pix_url = (
                    f"https://pixabay.com/api/?key={pixabay_key}"
                    f"&q={pix_query}&image_type=photo&per_page=15&min_width=800&min_height=800"
                )
                r = requests.get(pix_url, timeout=10)
                if r.status_code == 200:
                    hits = r.json().get("hits", [])
                    valid_hits = [h for h in hits if str(h.get("id")) not in used_ids]
                    if valid_hits:
                        chosen = random.choice(valid_hits[:5])
                        chosen_id = str(chosen.get("id"))
                        dl_url = chosen.get("largeImageURL") or chosen.get("webformatURL")
                        if dl_url:
                            img_resp = requests.get(dl_url, timeout=15)
                            if img_resp.status_code == 200 and len(img_resp.content) > 25000:
                                out_file = CACHE_DIR / f"pixabay_{chosen_id}_{query_slug}.jpg"
                                with open(out_file, "wb") as f:
                                    f.write(img_resp.content)
                                _record_used_news_photo(chosen_id)
                                print_success(f"Downloaded Pixabay photo: {out_file.name}")
                                return out_file
            except Exception as pix_err:
                logger.warning(f"Pixabay photo fetch error for '{clean_q}': {pix_err}")

        # 4. Tier 4: Wikimedia Commons / Wikipedia (targeted for named prominent persons)
        is_named_person = any(w[0].isupper() for w in subject.split() if len(w) > 2) and len(subject.split()) in (2, 3)
        if is_named_person or "ceo" in combined_text or "scientist" in combined_text or "founder" in combined_text:
            for term in [subject, clean_q]:
                if not term:
                    continue
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
                            if thumb and thumb not in used_ids:
                                img_resp = requests.get(thumb, headers=headers, timeout=12)
                                if img_resp.status_code == 200 and len(img_resp.content) > 20000:
                                    out_file = CACHE_DIR / f"wiki_{re.sub(r'[^a-zA-Z0-9]', '_', term).lower()}_{ts}.jpg"
                                    with open(out_file, "wb") as f:
                                        f.write(img_resp.content)
                                    _record_used_news_photo(thumb)
                                    print_success(f"Downloaded Wikipedia person portrait for '{term}': {out_file.name}")
                                    return out_file
                except Exception as wp_err:
                    logger.warning(f"Wikipedia portrait fetch failed for '{term}': {wp_err}")

        # 5. Tier 5: Themed Contextual Fallbacks (strictly category-matched, NEVER Jensen Huang for unrelated news)
        fb_dir = PROJECT_ROOT / "assets" / "news_fallback"
        if ("jensen" in combined_text or "nvidia" in combined_text) and (fb_dir / "jensen_huang.jpg").exists():
            print_info("Using verified Jensen Huang fallback photo.")
            return fb_dir / "jensen_huang.jpg"
        elif "mars" in combined_text and (fb_dir / "mars_surface.jpg").exists():
            print_info("Using verified NASA Mars Surface fallback photo.")
            return fb_dir / "mars_surface.jpg"
        elif ("webb" in combined_text or "jwst" in combined_text) and (fb_dir / "james_webb.jpg").exists():
            print_info("Using verified James Webb Cosmic Deep Field fallback photo.")
            return fb_dir / "james_webb.jpg"
        elif is_space and (fb_dir / "space_galaxy.jpg").exists():
            print_info("Using verified Space & Galaxy fallback photo.")
            return fb_dir / "space_galaxy.jpg"
        elif ("robot" in combined_text or "automation" in combined_text) and (fb_dir / "robotics.jpg").exists():
            print_info("Using verified Robotics fallback photo.")
            return fb_dir / "robotics.jpg"
        elif ("quantum" in combined_text or "chip" in combined_text or "semiconductor" in combined_text) and (fb_dir / "quantum_chip.jpg").exists():
            print_info("Using verified Quantum/Chip fallback photo.")
            return fb_dir / "quantum_chip.jpg"
        elif ("dna" in combined_text or "biology" in combined_text or "medical" in combined_text or "health" in combined_text) and (fb_dir / "biotech_dna.jpg").exists():
            print_info("Using verified Biotech/Medical fallback photo.")
            return fb_dir / "biotech_dna.jpg"
        elif ("ai" in combined_text or "neural" in combined_text or "intelligence" in combined_text or "model" in combined_text) and (fb_dir / "ai_neural.jpg").exists():
            print_info("Using verified AI/Neural Network fallback photo.")
            return fb_dir / "ai_neural.jpg"
        elif (fb_dir / "future_tech.jpg").exists():
            print_info("Using verified Future Technology fallback photo.")
            return fb_dir / "future_tech.jpg"
            return fb_dir / "biotech_dna.jpg"
        elif ("ai" in combined_text or "neural" in combined_text or "intelligence" in combined_text or "model" in combined_text) and (fb_dir / "ai_neural.jpg").exists():
            print_info("Using verified AI/Neural Network fallback photo.")
            return fb_dir / "ai_neural.jpg"
        elif (fb_dir / "future_tech.jpg").exists():
            print_info("Using verified Future Technology fallback photo.")
            return fb_dir / "future_tech.jpg"

        return None

    def get_todays_featured_story(self) -> Dict[str, Any]:
        """Full pipeline: Multi-Pillar Discover -> Deduplicate -> Curate -> Download Photo -> Return Story Dict."""
        print_info("🌐 Scanning global tech, AI & science news feeds across multiple pillars...")

        past_records = self.get_past_published_history(days=14)

        # Multi-pillar search queries to ensure rich variety every day
        queries = [
            "NASA OR 'James Webb' OR SpaceX OR Mars OR asteroid OR cosmic when:3d",
            "NVIDIA OR 'AI breakthrough' OR 'Quantum computing' OR DeepMind when:3d",
            "humanoid robot OR 'Boston Dynamics' OR Neuralink OR 'brain interface' when:3d",
            None,  # General Google News Science & Tech sections
        ]

        all_candidates = []
        seen_titles = set()
        for q in queries:
            try:
                items = self.fetch_rss_items(query=q, max_items=15)
                for it in items:
                    t_lower = it["title"].lower().strip()
                    if t_lower not in seen_titles:
                        seen_titles.add(t_lower)
                        all_candidates.append(it)
            except Exception as q_err:
                logger.warning(f"Error fetching candidates for query '{q}': {q_err}")

        print_info(f"📰 Evaluating {len(all_candidates)} collected news candidates with Gemini (with Anti-Repetition Guard)...")
        story = self.curate_top_story(candidates=all_candidates, past_records=past_records)

        print_info(f"🎯 Selected Fresh Story: {story.get('headline_en')}")
        img_path = self.fetch_high_res_photo(
            search_query=story.get("search_query", story.get("subject", "")),
            subject=story.get("subject", ""),
            category=story.get("category", ""),
            headline=story.get("headline_en", ""),
        )
        story["image_path"] = str(img_path) if img_path else ""

        return story
