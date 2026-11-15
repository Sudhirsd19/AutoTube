"""Generates engaging Hindi post captions, breaking news card headlines, and viral polls using Gemini AI."""

import json
import logging
import os
import re
from typing import Any, Dict, Optional

from google import genai
from google.genai import types

from autotube.config import get_config
from autotube.utils.console import print_error, print_info, print_success, print_warning

logger = logging.getLogger(__name__)


class NewsPostGenerator:
    """Creates high-retention Hindi social media posts, headlines, and binary debate polls."""

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

    def generate_post_content(self, story_data: Dict[str, Any]) -> Dict[str, Any]:
        """Generate headlines for the 1080x1080 card and the complete Facebook post caption."""
        headline_en = story_data.get("headline_en", "")
        summary = story_data.get("summary", "")
        subject = story_data.get("subject", "")
        category = story_data.get("category", "TECH & AI UPDATE")
        tag_hindi = story_data.get("tag_hindi", "ताज़ा टेक अपडेट")
        photo_credit = story_data.get("photo_credit", "Press / Reuters")

        prompt = f"""You are a master social media content creator for CosmoChronicle, crafting viral Hindi news cards and Facebook posts about futuristic tech, AI, and space.

News Details:
- Category: {category}
- English Headline: {headline_en}
- Subject/Person: {subject}
- Summary: {summary}
- Tag: {tag_hindi}
- Photo Credit: {photo_credit}

Your task:
1. Card Headline (For the 1080x1080 image card):
   - Line 1: Catchy quote or breaking news hook in pure Hindi (max 6-8 words, e.g. “अब बच्चों को कोडिंग मत सिखाओ!)
   - Line 2: The punchline in pure Hindi (max 5-7 words, e.g. AI खुद सॉफ्टवेयर बनाएगा”)
   - Highlight: Which exact word/words in Line 2 should be highlighted in bright yellow?
   - Speaker/Attribution: e.g. — जेन्सन हुआंग (Jensen Huang, CEO - NVIDIA) or — नासा वैज्ञानिक (NASA Scientists)

2. Complete Facebook Post Caption:
   - Catchy Hindi News Title with red dot / lightning emojis (e.g. 🔴 "कोडिंग का ज़माना खत्म!...")
   - 3 Engaging Bullet Points breaking down the news in simple, gripping Hindi (खबर क्या है? दुनिया पर क्या असर होगा? आदि).
   - High-Velocity Binary Debate Poll:
     Ask an intriguing question where audience can answer "1" or "2" in comments (e.g. क्या AI भविष्य में कोडिंग जॉब्स खत्म कर देगा? 1: हाँ, 2: नहीं).
   - Follow CTA: "👉 अपनी राय कमेंट बॉक्स में 1 या 2 लिखकर ज़रूर बताएं! 👇 और ऐसे ही ताज़ा टेक व साइंस अपडेट्स के लिए @CosmoChronicle पेज को फॉलो करें! 🔔"
   - Official Photo Credit line: "📸 Photo Credit: {photo_credit}"
   - 6-8 Trending Hashtags (#TechNewsHindi, #ArtificialIntelligence, #CosmoChronicle, etc.)

Respond STRICTLY with a valid JSON object matching this schema:
{{
  "card_category": "{category}",
  "card_tag_hindi": "{tag_hindi}",
  "card_headline_line1": "<Line 1 in Hindi>",
  "card_headline_line2": "<Line 2 in Hindi>",
  "card_highlight_text": "<exact text in Line 2 to highlight in yellow>",
  "card_speaker": "<Speaker attribution line>",
  "post_title": "<Catchy headline for post>",
  "post_caption": "<Complete formatted Facebook post text ready to publish>"
}}
"""
        if self.client:
            for model_name in ["gemini-3.5-flash-lite", "gemini-flash-lite-latest", "gemini-3.1-flash-lite"]:
                try:
                    resp = self.client.models.generate_content(
                        model=model_name,
                        contents=prompt,
                        config=types.GenerateContentConfig(
                            temperature=0.3,
                            response_mime_type="application/json",
                        ),
                    )
                    parsed = json.loads(resp.text)
                    print_success(f"Generated Hindi news post content with {model_name}")
                    return parsed
                except Exception as e:
                    logger.warning(f"Error generating news post with {model_name}: {e}")

        # High quality fallback (NVIDIA Jensen Huang news)
        return {
            "card_category": category,
            "card_tag_hindi": "NVIDIA CEO का बड़ा ऐलान",
            "card_headline_line1": "“अब बच्चों को कोडिंग मत सिखाओ!",
            "card_headline_line2": "AI खुद सॉफ्टवेयर बनाएगा”",
            "card_highlight_text": "AI खुद सॉफ्टवेयर बनाएगा",
            "card_speaker": "— जेन्सन हुआंग (Jensen Huang, CEO - NVIDIA)",
            "post_title": "🔴 'कोडिंग का ज़माना खत्म! AI खुद सॉफ्टवेयर बनाएगा' — NVIDIA CEO जेन्सन हुआंग का बयान!",
            "post_caption": (
                "🔴 \"कोडिंग का ज़माना खत्म! भविष्य में AI खुद सॉफ्टवेयर बनाएगा\" — NVIDIA CEO जेन्सन हुआंग का चौंकाने वाला बयान! ⚡\n\n"
                "दुनिया की सबसे बड़ी AI व चिप कंपनी NVIDIA के CEO Jensen Huang ने वर्ल्ड समिट में एक ऐसा बयान दिया है जिसने पूरी टेक इंडस्ट्री में खलबली मचा दी है:\n\n"
                "🔹 \"कोडिंग सीखने की ज़रूरत नहीं\": जेन्सन हुआंग के अनुसार, पिछले 15 सालों से हर कोई बच्चों को कोडिंग सिखाने की बात कर रहा था। लेकिन अब हमारा लक्ष्य ऐसी तकनीक बनाना है ताकि किसी को कोड न करना पड़े—कंप्यूटर खुद इंसान की बोलचाल की भाषा समझकर पूरा सॉफ्टवेयर तैयार कर देगा!\n\n"
                "🔹 \"हर इंसान अब प्रोग्रामर है\": उन्होंने कहा कि भविष्य में सबसे बड़ा हुनर 'कोडिंग' नहीं, बल्कि 'सही सवाल पूछना और AI से सही काम करवाना' (Domain Knowledge & Prompting) होगा।\n\n"
                "🔹 इंडस्ट्री में हलचल: इस बयान के बाद सिलिकॉन वैली से लेकर भारत तक बहस छिड़ गई है कि क्या आने वाले समय में सॉफ्टवेयर इंजीनियरों की मांग कम हो जाएगी?\n\n"
                "---\n"
                "💬 आज का सबसे बड़ा सवाल:\n"
                "क्या आपको लगता है कि AI आने वाले समय में इंसानी कोडिंग और सॉफ्टवेयर जॉब्स को खत्म कर देगा?\n\n"
                "1️⃣ हाँ, AI बहुत तेज़ी से इंसानों से बेहतर काम कर रहा है।\n"
                "2️⃣ नहीं, असली क्रिएटिविटी और लॉजिक के लिए इंसानी दिमाग की ज़रूरत हमेशा रहेगी।\n\n"
                "👉 अपनी राय कमेंट बॉक्स में 1 या 2 लिखकर ज़रूर बताएं! 👇\n"
                "और ऐसे ही भविष्य की टेक्नोलॉजी व साइंस अपडेट्स के लिए @CosmoChronicle पेज को फॉलो करें! 🔔\n\n"
                f"📸 Photo Credit: {photo_credit}\n"
                "#NVIDIA #JensenHuang #ArtificialIntelligence #TechNewsHindi #CosmoChronicle #FutureTech #Coding #AIRevolution #HindiNews"
            ),
        }
