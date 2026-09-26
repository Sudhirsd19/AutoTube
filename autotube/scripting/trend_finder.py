"""Trending Topic Finder & Deduplication Engine."""

import json
from pathlib import Path
from typing import List, Optional
from autotube.config import PROJECT_ROOT, get_config
from autotube.scripting.generator import CANDIDATE_MODELS
from autotube.utils.console import print_info, print_warning
from google import genai
from google.genai import types

HISTORY_FILE = PROJECT_ROOT / "config" / "published_history.json"

VIRAL_NICHES = {
    "space": "Space mysteries, black holes, rogue planets, universe boundaries, cosmic events",
    "science": "Mind-blowing physics, quantum mechanics, biology paradoxes, crazy inventions",
    "history": "Bizarre historical events, untold ancient secrets, ruthless rulers, hidden treasures",
    "psychology": "Dark psychology, human mind tricks, cognitive biases, body language secrets",
    "mystery": "Unsolved ancient mysteries, ocean anomalies, forbidden archaeological discoveries",
}


class TrendFinder:
    """Discovers viral, high-retention topics and prevents repetition."""

    def __init__(self):
        self.cfg = get_config()
        self.history_file = HISTORY_FILE
        self._ensure_history_file()

    def _ensure_history_file(self):
        if not self.history_file.exists():
            self.history_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self.history_file, "w", encoding="utf-8") as f:
                json.dump({"topics": [], "video_ids": []}, f, indent=2)

    def get_history(self) -> List[str]:
        try:
            with open(self.history_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                return data.get("topics", [])
        except Exception:
            return []

    def record_topic(self, topic: str, video_id: Optional[str] = None):
        try:
            with open(self.history_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            data["topics"].append(topic.strip().lower())
            if video_id:
                data["video_ids"].append(video_id)
            with open(self.history_file, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            print_warning(f"Could not update history: {e}")

    def get_trending_topics(self, count: int = 5, niche: str = "space") -> List[str]:
        """Generate unique, non-repeating viral topics using Gemini."""
        history = self.get_history()
        niche_focus = VIRAL_NICHES.get(niche.lower(), VIRAL_NICHES["space"])

        client = None
        if self.cfg.gemini_api_key:
            try:
                client = genai.Client(api_key=self.cfg.gemini_api_key)
            except Exception:
                pass

        if client:
            past_topics_str = ", ".join(f"'{t}'" for t in history[-30:]) if history else "None"
            prompt = f"""You are a viral YouTube Shorts growth strategist.
Generate {count} unique, mind-bending, high-CTR video topics in the niche: {niche_focus}.
Requirements:
1. Each topic must evoke intense curiosity, fear of missing out, or awe.
2. Formatted as punchy questions or shocking statements.
3. DO NOT repeat any of these previously covered topics: [{past_topics_str}].

Return ONLY a JSON list of strings, for example:
["Why You Would Age Backwards Near a Neutron Star", "The Rogue Planet Wandering Towards Our Solar System"]
"""
            for model_name in CANDIDATE_MODELS:
                try:
                    resp = client.models.generate_content(
                        model=model_name,
                        contents=prompt,
                        config=types.GenerateContentConfig(
                            response_mime_type="application/json",
                            temperature=0.85,
                        ),
                    )
                    topics = json.loads(resp.text)
                    if isinstance(topics, list) and len(topics) >= count:
                        clean_topics = [t for t in topics if t.strip().lower() not in history][:count]
                        if clean_topics:
                            return clean_topics
                except Exception as e:
                    print_warning(f"TrendFinder model attempt failed: {e}")
                    continue

        # Smart fallback list if API is unreachable
        fallbacks = [
            "What If Earth Lost Gravity For Just 5 Seconds",
            "The Scariest Sound Ever Recorded in Deep Space",
            "The Planet Where It Rains Molten Glass Sideways",
            "The Mystery of The Boomerang Nebula Coldest Place in Space",
            "What Existed Before The Big Bang Occurred",
            "The Massive Ocean Discovered Beneath Earths Crust",
            "Why Humans Can Never Travel Beyond The Milky Way",
        ]
        available = [f for f in fallbacks if f.lower() not in history]
        return available[:count] if len(available) >= count else fallbacks[:count]
