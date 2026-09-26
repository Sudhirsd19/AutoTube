"""AI Script Generator for YouTube Shorts and Long-form content."""

import json
import os
from typing import Optional
from google import genai
from google.genai import types

from autotube.config import get_config
from autotube.scripting.models import LongVideoScript, Scene, ShortScript
from autotube.scripting.prompts import LONGFORM_SYSTEM_PROMPT, SHORTS_SYSTEM_PROMPT
from autotube.utils.console import print_error, print_info, print_warning


class ScriptGenerator:
    """Handles script generation using Gemini or built-in fallback presets."""

    def __init__(self, api_key: Optional[str] = None):
        cfg = get_config()
        self.api_key = api_key or cfg.gemini_api_key or os.getenv("GEMINI_API_KEY")
        self.client = None
        if self.api_key:
            try:
                self.client = genai.Client(api_key=self.api_key)
            except Exception as e:
                print_warning(f"Could not initialize Gemini client: {e}")

    def generate_short_script(
        self, topic: str, target_duration: int = 50
    ) -> ShortScript:
        """Generate a viral YouTube Short script for the given topic."""
        if not self.client:
            print_warning(
                "No GEMINI_API_KEY found or client unavailable. Using smart built-in template for testing."
            )
            return self._generate_fallback_short(topic, target_duration)

        prompt = f"""Generate a high-retention YouTube Short script about: '{topic}'.
Target duration: {target_duration} seconds.
Write compelling narration, strong first 3 seconds hook, 4-6 visual search keywords, and relevant tags."""

        try:
            print_info(f"Generating AI Short script for topic: '{topic}'...")
            response = self.client.models.generate_content(
                model="gemini-2.5-flash",
                contents=prompt,
                config=types.GenerateContentConfig(
                    system_instruction=SHORTS_SYSTEM_PROMPT,
                    response_mime_type="application/json",
                    response_schema=ShortScript,
                    temperature=0.7,
                ),
            )
            data = json.loads(response.text)
            return ShortScript(**data)
        except Exception as e:
            print_error(f"Gemini API generation failed: {e}. Falling back to template.")
            return self._generate_fallback_short(topic, target_duration)

    def generate_long_script(
        self, topic: str, num_scenes: int = 6
    ) -> LongVideoScript:
        """Generate a multi-scene long-form YouTube script."""
        if not self.client:
            print_warning(
                "No GEMINI_API_KEY found or client unavailable. Using smart built-in template for testing."
            )
            return self._generate_fallback_long(topic, num_scenes)

        prompt = f"""Generate a captivating YouTube documentary script about: '{topic}'.
Structure it into exactly {num_scenes} distinct visual scenes.
Provide title, description, tags, and each scene with spoken narration and visual search query."""

        try:
            print_info(f"Generating AI Long-form script for topic: '{topic}'...")
            response = self.client.models.generate_content(
                model="gemini-2.5-flash",
                contents=prompt,
                config=types.GenerateContentConfig(
                    system_instruction=LONGFORM_SYSTEM_PROMPT,
                    response_mime_type="application/json",
                    response_schema=LongVideoScript,
                    temperature=0.7,
                ),
            )
            data = json.loads(response.text)
            return LongVideoScript(**data)
        except Exception as e:
            print_error(f"Gemini API generation failed: {e}. Falling back to template.")
            return self._generate_fallback_long(topic, num_scenes)

    def _generate_fallback_short(
        self, topic: str, target_duration: int
    ) -> ShortScript:
        """Smart fallback short script when API key is not yet set."""
        clean_topic = topic.strip().capitalize()
        hook = f"Did you know the darkest secret behind {clean_topic}?"
        narration = (
            f"Did you know the darkest secret behind {clean_topic}? "
            f"Most people think they understand how {clean_topic} works, but scientists recently discovered "
            f"something that completely changes everything. "
            f"Deep beneath the surface, forces operate in ways never predicted by modern physics. "
            f"If this continues, the entire industry could be flipped upside down by next year. "
            f"What do you think about this? Drop your thoughts below and subscribe for more mind-bending facts!"
        )
        return ShortScript(
            title=f"The Shocking Truth About {clean_topic}! #Shorts",
            topic=topic,
            hook=hook,
            narration=narration,
            call_to_action="Subscribe for more mind-blowing facts!",
            visual_keywords=[
                f"{clean_topic} futuristic cinematic",
                "technology mystery dark lighting",
                "abstract glowing digital network",
                "dramatic reveal high tech",
            ],
            tags=["#Shorts", "#viral", "#facts", f"#{clean_topic.replace(' ', '')}"],
            estimated_duration_sec=target_duration,
        )

    def _generate_fallback_long(
        self, topic: str, num_scenes: int
    ) -> LongVideoScript:
        """Smart fallback multi-scene script when API key is not yet set."""
        clean_topic = topic.strip().capitalize()
        scenes = [
            Scene(
                scene_number=1,
                narration=f"In a world driven by constant change, one phenomenon has quietly rewritten the rules: {clean_topic}.",
                visual_query=f"{clean_topic} futuristic cinematic dark",
                visual_description="Cinematic slow panning shot with atmospheric lighting",
                estimated_duration_sec=6.0,
            ),
            Scene(
                scene_number=2,
                narration="To truly grasp the scale of what is happening today, we have to look back at where it all began.",
                visual_query="vintage archives history turning point documentary",
                visual_description="Historical black and white or archival retro footage",
                estimated_duration_sec=6.0,
            ),
            Scene(
                scene_number=3,
                narration="Breakthrough after breakthrough paved the way, accelerating progress at an unprecedented rate.",
                visual_query="modern laboratory researchers high tech innovation",
                visual_description="Dynamic shots of technology and high-speed data flow",
                estimated_duration_sec=6.0,
            ),
            Scene(
                scene_number=4,
                narration="Yet, with extraordinary power comes unforeseen dilemmas that experts are only beginning to confront.",
                visual_query="dramatic city skyline time lapse night lights",
                visual_description="Moody aerial drone footage of glowing metropolis",
                estimated_duration_sec=6.0,
            ),
            Scene(
                scene_number=5,
                narration="The choices made over the next five years will determine the trajectory for generations to come.",
                visual_query="future horizon dawn sunrise landscape inspiring",
                visual_description="Golden hour landscape with expanding sun rays",
                estimated_duration_sec=6.0,
            ),
            Scene(
                scene_number=6,
                narration="The future is arriving faster than anyone anticipated. If you enjoyed this breakdown, like and subscribe.",
                visual_query="youtube subscribe button graphic neon glow",
                visual_description="Clean modern end screen motion graphics",
                estimated_duration_sec=5.0,
            ),
        ]
        return LongVideoScript(
            title=f"The Rise and Evolution of {clean_topic} | Full Documentary",
            topic=topic,
            description=f"An in-depth investigative exploration into {clean_topic}.\n\nTimestamps:\n0:00 - Introduction\n1:00 - The Origins\n2:30 - The Turning Point\n4:00 - What Lies Ahead\n\nSubscribe to AutoTube for daily documentaries!",
            tags=["documentary", clean_topic.lower(), "technology", "future", "history"],
            scenes=scenes[:num_scenes],
            total_estimated_duration_sec=len(scenes[:num_scenes]) * 6,
        )
