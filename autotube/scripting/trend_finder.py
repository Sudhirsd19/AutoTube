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
    "psychology": "Dark psychology, human mind tricks, cognitive biases, body language secrets, subconscious hacks",
    "mystery": "Unsolved ancient mysteries, ocean anomalies, forbidden archaeological discoveries, eerie legends",
    "mythology": "Ancient Indian mythological secrets, sacred divine weapons, unsolved epic mysteries, lost temples and celestial beings",
    "cartoon": "Funny 3D Pixar animated animal adventures, quirky pets with secret superhero lives, hilarious baby dinosaur mishaps, funny mischievous robot fails, adorable comedy cartoon stories",
}


class TrendFinder:
    """Discovers viral, high-retention topics and prevents repetition."""

    def __init__(self):
        self.cfg = get_config()
        self.history_file = HISTORY_FILE
        self._ensure_history_file()
        self.session_used_topics = set()

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
        clean_topic = topic.strip().lower()
        self.session_used_topics.add(clean_topic)
        try:
            with open(self.history_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            data["topics"].append(clean_topic)
            if video_id:
                data["video_ids"].append(video_id)
            with open(self.history_file, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            print_warning(f"Could not update history: {e}")

    def get_trending_topics(self, count: int = 5, niche: str = "space") -> List[str]:
        """Generate unique, non-repeating viral topics using Gemini."""
        history = [t.lower() for t in self.get_history()] + list(self.session_used_topics)
        niche_focus = VIRAL_NICHES.get(niche.lower(), VIRAL_NICHES["space"])

        client = None
        if self.cfg.gemini_api_key:
            try:
                client = genai.Client(api_key=self.cfg.gemini_api_key)
            except Exception:
                pass

        if client:
            past_topics_str = ", ".join(f"'{t}'" for t in history[-40:]) if history else "None"
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
                    if isinstance(topics, list) and len(topics) >= 1:
                        clean_topics = [t for t in topics if t.strip().lower() not in history][:count]
                        if clean_topics:
                            for ct in clean_topics:
                                self.session_used_topics.add(ct.strip().lower())
                            return clean_topics
                except Exception as e:
                    print_warning(f"TrendFinder model attempt failed: {e}")
                    continue

        # Niche-specific fallbacks to guarantee diversity
        niche_fallbacks = {
            "mystery": [
                "The Bizarre Bermuda Triangle Incident That Scientists Still Fear",
                "Deep Sea Sonar Detected An Unknown Structure Beneath The Mariana Trench",
                "The Forbidden Voynich Manuscript That No Cryptographer Can Decode",
                "The 500-Year-Old Map Depicting Antarctica Without Ice",
                "The Unexplained Hum Heard Across The Globe In Total Silence",
            ],
            "space": [
                "What If Earth Lost Gravity For Just 5 Seconds",
                "The Scariest Sound Ever Recorded In Deep Space",
                "The Planet Where It Rains Molten Glass Sideways At 5000 MPH",
                "The Mystery Of The Boomerang Nebula The Coldest Place In Space",
                "What Would Happen If A Black Hole Entered Our Solar System",
            ],
            "science": [
                "What Actually Happens In Your Brain When You Experience Deja Vu",
                "The Bizarre Quantum Experiment Proving The Past Can Be Changed",
                "The Biological Glitch In The Immortal Jellyfish That Defies Aging",
                "Why Boiling Water Freezes Faster Than Cold Water In Science",
                "What Existed In The Universe One Second Before The Big Bang",
            ],
            "history": [
                "The Forbidden Secret Chambers Discovered Beneath The Great Sphinx",
                "The Roman Emperor Who Declared War On The Entire Ocean",
                "The Ancient Nuclear Glass Found In The Deserts Of Mohenjo Daro",
                "The Mysterious Lost Library Of Alexandria And What Was Burned",
                "The 2000-Year-Old Computer Discovered At The Bottom Of The Sea",
            ],
            "psychology": [
                "The Inception Loop A Dark Psychology Trick To Plant An Idea",
                "3 Subconscious Tricks Politicians Use To Control Any Crowd",
                "Why Staying Completely Silent Terrifies Manipulators",
                "The Bystander Paradox Why People Wont Help In Crowded Disasters",
                "How Spotting Micro Expressions Can Reveal If Anyone Is Lying",
            ],
            "mythology": [
                "The Ancient Brahmastra The First Described Weapon Of Mass Destruction",
                "The Secret 7th Vault Of Padmanabhaswamy Temple That No One Can Open",
                "The Unbelievable Architectural Mystery Of Kailasa Temple Carved From Top To Bottom",
                "The Flying Vimanas Described With Propulsion In Ancient Indian Texts",
                "The Hidden Sanjeevani Herb And Its Connection To Modern Biology",
            ],
        }

        pool = niche_fallbacks.get(niche.lower(), niche_fallbacks["space"])
        available = [f for f in pool if f.lower() not in history]
        selected = available[:count] if len(available) >= count else pool[:count]
        for s in selected:
            self.session_used_topics.add(s.strip().lower())
        return selected

    def get_single_topic(self, niche: str) -> str:
        """Get 1 fresh non-repeating viral topic for the given niche."""
        topics = self.get_trending_topics(count=1, niche=niche)
        if topics:
            return topics[0]
        fallback = "The Most Mind-Blowing Unsolved Mystery In The Universe"
        self.session_used_topics.add(fallback.lower())
        return fallback
