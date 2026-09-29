"""AI Script Generator for YouTube Shorts and Long-form content with multi-model fallback."""

import json
import os
from typing import List, Optional
from google import genai
from google.genai import types

from autotube.config import get_config
from autotube.scripting.models import LongVideoScript, Scene, ShortScene, ShortScript
from autotube.scripting.prompts import LONGFORM_SYSTEM_PROMPT, SHORTS_SYSTEM_PROMPT
from autotube.utils.console import print_error, print_info, print_success, print_warning

# Recommended modern models with automatic fallback
CANDIDATE_MODELS = [
    "gemini-3.1-flash-lite-preview",
    "gemini-3.8-flash",
    "gemini-flash-latest",
    "gemini-3-flash-preview",
]


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
        self, topic: str, target_duration: int = 50, language: str = "en"
    ) -> ShortScript:
        """Generate a viral YouTube Short script for the given topic in English or Hindi."""
        is_hindi = language.lower() in ("hi", "hindi")
        from autotube.scripting.prompts import HINDI_SHORTS_SYSTEM_PROMPT, SHORTS_SYSTEM_PROMPT

        if not self.client:
            print_warning(
                "No GEMINI_API_KEY found or client unavailable. Using smart built-in template."
            )
            return self._generate_fallback_short(topic, target_duration)

        sys_prompt = HINDI_SHORTS_SYSTEM_PROMPT if is_hindi else SHORTS_SYSTEM_PROMPT
        lang_note = "in natural Hindi/Hinglish (narration) with English visual search keywords" if is_hindi else "in English"

        min_words = 125 if target_duration >= 45 else int(target_duration * 2.5)
        max_words = 145 if target_duration >= 45 else int(target_duration * 2.9)

        prompt = f"""Generate a high-retention viral YouTube Short script about: '{topic}' {lang_note}.
Target duration: {target_duration} seconds (MANDATORY: 45 to 55 seconds).

MANDATORY STRUCTURAL REQUIREMENTS:
1. Break the entire script into 4 to 6 sequential scenes in 'scenes'.
2. For each scene in 'scenes':
   - 'scene_number': 1, 2, 3, 4, 5...
   - 'narration': 1-2 punchy spoken sentences for this scene ({'in Hindi' if is_hindi else 'in English'}).
   - 'visual_subject': The exact physical subject on screen in 1-3 simple English words (e.g. 'black hole space', 'earth from space', 'pyramid egypt', 'deep ocean storm', 'glowing brain'). MUST directly match the spoken words!
   - 'visual_description': Vivid description in English of the visual scene.
   - 'search_keywords': 2-3 clean, simple English search words (e.g. ['black hole', 'space galaxy']).
3. TOTAL SPOKEN WORDS across all scenes MUST be between {min_words} and {max_words} words.
4. Set the top-level 'narration' field to the combined text of all scene narrations.
5. High-converting climax cliffhanger CTA in the final scene.
6. Seamless infinite loop: ending sentence flows back into opening hook."""

        for model_name in CANDIDATE_MODELS:
            try:
                print_info(f"Generating AI Short script ({'Hindi' if is_hindi else 'English'}) using [{model_name}]...")
                response = self.client.models.generate_content(
                    model=model_name,
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        system_instruction=sys_prompt,
                        response_mime_type="application/json",
                        response_schema=ShortScript,
                        temperature=0.75,
                    ),
                )
                data = json.loads(response.text)
                script = ShortScript(**data)
                # Ensure narration is filled if scenes present
                if script.scenes and not script.narration:
                    script.narration = " ".join(s.narration.strip() for s in script.scenes if s.narration.strip())
                print_success(f"AI Script successfully generated with {model_name}!")
                return script
            except Exception as e:
                print_warning(f"Model {model_name} attempt: {e}")
                continue

        print_error("All Gemini models busy or failed. Falling back to template.")
        return self._generate_fallback_short(topic, target_duration)

    def generate_cartoon_script(
        self, topic: str, target_duration: int = 45
    ) -> ShortScript:
        """Generate a viral, funny, or heartwarming 3D animated cartoon short script."""
        from autotube.scripting.prompts import CARTOON_SYSTEM_PROMPT

        if not self.client:
            return self._generate_fallback_short(topic, target_duration)

        prompt = f"""Generate a hilarious, heartwarming, or surprising 3D Pixar/Disney style animated cartoon short about: '{topic}'.
Target duration: {target_duration} seconds.
Rules:
1. Quirky, funny hook in the first 2 seconds.
2. Expressive characters and dialogue.
3. Funny or clever twist ending.
4. Visual keywords MUST describe cute, expressive 3D Pixar animated characters and scenes.
"""

        for model_name in CANDIDATE_MODELS:
            try:
                print_info(f"Generating Cartoon Script using [{model_name}]...")
                response = self.client.models.generate_content(
                    model=model_name,
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        system_instruction=CARTOON_SYSTEM_PROMPT,
                        response_mime_type="application/json",
                        response_schema=ShortScript,
                        temperature=0.85,
                    ),
                )
                data = json.loads(response.text)
                print_success(f"Cartoon Script generated with {model_name}!")
                return ShortScript(**data)
            except Exception as e:
                print_warning(f"Model {model_name} attempt: {e}")
                continue

        return self._generate_fallback_short(topic, target_duration)

    def generate_3d_animation_script(
        self, topic: str, target_duration: int = 45, language: str = "hi"
    ) -> ShortScript:
        """Generate a captivating 3D Pixar/Disney style animated story script (Hindi or English)."""
        is_hindi = language.lower() in ("hi", "hindi")
        from autotube.scripting.prompts import CARTOON_SYSTEM_PROMPT, HINDI_3D_ANIMATION_PROMPT

        if not self.client:
            return self._generate_fallback_short(topic, target_duration)

        sys_prompt = HINDI_3D_ANIMATION_PROMPT if is_hindi else CARTOON_SYSTEM_PROMPT
        lang_note = "in touching conversational Hindi (narration) with 4-6 detailed 3D Pixar English visual keywords" if is_hindi else "in English with 3D Pixar visual keywords"

        min_words = 125 if target_duration >= 45 else int(target_duration * 2.5)
        max_words = 145 if target_duration >= 45 else int(target_duration * 2.9)

        prompt = f"""Generate an emotional or entertaining 3D Pixar Disney style animated story about: '{topic}' {lang_note}.
Target duration: {target_duration} seconds (MANDATORY: 45 to 55 seconds).
STRICT LENGTH RULE:
The 'narration' field MUST be between {min_words} and {max_words} words long so that spoken speech comfortably takes 48-55 seconds.
Rules:
1. Emotionally gripping hook in the first 2 seconds.
2. Consistent cute 3D character described across all visual prompts (e.g. skin, clothes, expressions, details).
3. 5 to 6 detailed English visual prompts for 3D CGI rendering (Unreal Engine 5 / Pixar style).
4. Full detailed narration between {min_words} and {max_words} words.
5. High-converting climax cliffhanger CTA in the final 5 seconds."""

        for model_name in CANDIDATE_MODELS:
            try:
                print_info(f"Generating 3D Animation Script ({'Hindi' if is_hindi else 'English'}) using [{model_name}]...")
                response = self.client.models.generate_content(
                    model=model_name,
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        system_instruction=sys_prompt,
                        response_mime_type="application/json",
                        response_schema=ShortScript,
                        temperature=0.8,
                    ),
                )
                data = json.loads(response.text)
                print_success(f"3D Animation Script generated with {model_name}!")
                return ShortScript(**data)
            except Exception as e:
                print_warning(f"Model {model_name} attempt: {e}")
                continue

        return self._generate_fallback_short(topic, target_duration)

    def generate_long_script(
        self, topic: str, num_scenes: int = 6
    ) -> LongVideoScript:
        """Generate a multi-scene long-form YouTube script."""
        if not self.client:
            print_warning(
                "No GEMINI_API_KEY found or client unavailable. Using smart built-in template."
            )
            return self._generate_fallback_long(topic, num_scenes)

        prompt = f"""Generate a captivating YouTube documentary script about: '{topic}'.
Structure it into exactly {num_scenes} distinct visual scenes.
Provide title, description, tags, and each scene with spoken narration and visual search query."""

        for model_name in CANDIDATE_MODELS:
            try:
                print_info(f"Generating AI Long-form script using [{model_name}]...")
                response = self.client.models.generate_content(
                    model=model_name,
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        system_instruction=LONGFORM_SYSTEM_PROMPT,
                        response_mime_type="application/json",
                        response_schema=LongVideoScript,
                        temperature=0.7,
                    ),
                )
                data = json.loads(response.text)
                print_success(f"Documentary Script generated with {model_name}!")
                return LongVideoScript(**data)
            except Exception as e:
                print_warning(f"Model {model_name} attempt: {e}")
                continue

        print_error("All Gemini models busy or failed. Falling back to template.")
        return self._generate_fallback_long(topic, num_scenes)

    def _generate_fallback_short(
        self, topic: str, target_duration: int
    ) -> ShortScript:
        """Smart fallback short script when API key is not yet set."""
        clean_topic = topic.strip().capitalize()
        hook = f"Did you know the darkest secret behind {clean_topic}?"
        scenes = [
            ShortScene(
                scene_number=1,
                narration=f"Did you know the darkest secret behind {clean_topic}?",
                visual_subject=clean_topic.lower(),
                visual_description=f"Shocking reveal of {clean_topic}",
                search_keywords=[clean_topic.lower(), "space mystery"],
            ),
            ShortScene(
                scene_number=2,
                narration=f"Most people think they understand how {clean_topic} works, but scientists recently discovered something that completely changes everything.",
                visual_subject="scientific discovery",
                visual_description="Scientists examining glowing data in high-tech research facility",
                search_keywords=["science discovery", "research lab"],
            ),
            ShortScene(
                scene_number=3,
                narration="Deep beneath the surface, forces operate in ways never predicted by modern physics.",
                visual_subject="deep cosmic energy",
                visual_description="Energy vortex and glowing cosmic particles in motion",
                search_keywords=["cosmic energy", "space vortex"],
            ),
            ShortScene(
                scene_number=4,
                narration="What do you think about this? Drop your thoughts below and subscribe right now so you don't miss part 2!",
                visual_subject="earth space",
                visual_description="Epic cinematic perspective of deep space looking back at planet",
                search_keywords=["earth space", "galaxy stars"],
            ),
        ]
        narration = " ".join(s.narration for s in scenes)
        return ShortScript(
            title=f"The Shocking Truth About {clean_topic}! #Shorts",
            topic=topic,
            hook=hook,
            scenes=scenes,
            narration=narration,
            call_to_action="Subscribe for more mind-blowing facts!",
            visual_keywords=[s.visual_subject for s in scenes],
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
