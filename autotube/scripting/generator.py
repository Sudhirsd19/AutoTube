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
                # Ensure narration is 100% strictly constructed from individual scene narrations
                # so speech word counts and scene boundaries align with 100% precision
                if script.scenes:
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
                script = ShortScript(**data)
                if script.scenes:
                    script.narration = " ".join(s.narration.strip() for s in script.scenes if s.narration.strip())
                print_success(f"Cartoon Script generated with {model_name}!")
                return script
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
                script = ShortScript(**data)
                if script.scenes:
                    script.narration = " ".join(s.narration.strip() for s in script.scenes if s.narration.strip())
                print_success(f"3D Animation Script generated with {model_name}!")
                return script
            except Exception as e:
                print_warning(f"Model {model_name} attempt: {e}")
                continue

        return self._generate_fallback_short(topic, target_duration)

    def generate_alien_script(
        self,
        part: Optional[int] = None,
        language: str = "en",
        target_duration: int = 65,
    ) -> ShortScript:
        """Generate a viral episode for the Alien Interview book series with proof citations."""
        from autotube.scripting.alien_tracker import AlienSeriesTracker
        from autotube.scripting.prompts import ALIEN_INTERVIEW_EN_PROMPT, ALIEN_INTERVIEW_HI_PROMPT

        is_hindi = language.lower() in ("hi", "hindi")
        tracker = AlienSeriesTracker()
        chapter = tracker.get_current_chapter(part_override=part)

        part_num = chapter["part_number"]
        chapter_title = chapter["title_hi"] if is_hindi else chapter["title_en"]
        book_chapter = chapter["book_chapter"]
        core_theme = chapter["core_theme"]
        evidence = chapter["evidence_proof"]
        quote = chapter["key_quote"]

        if not self.client:
            return self._generate_fallback_short(f"Alien Interview Part {part_num} {chapter_title}", target_duration)

        sys_prompt = ALIEN_INTERVIEW_HI_PROMPT if is_hindi else ALIEN_INTERVIEW_EN_PROMPT
        lang_instruction = "in dramatic suspenseful Hindi/Hinglish" if is_hindi else "in gripping investigative English"

        prompt = f"""Write YouTube Short Episode: Part {part_num} of the 'Alien Interview' Book Series ({lang_instruction}).
Format: REAL 1947 INTERROGATION AUDIO TAPE between US Army Nurse Matilda MacElroy ('nurse') and Roswell Alien Airl ('alien').

Source Material:
- Book Chapter: {book_chapter}
- Episode Title: Part {part_num}: {chapter_title}
- Core Topic: {core_theme}
- Documented Evidence / Proof to Cite: {evidence}
- Key Quote from Alien Airl: "{quote}"

CRITICAL REQUIREMENTS:
1. TWO CHARACTERS DIALOGUE (REAL INTERVIEW):
   - Every single scene in 'scenes' MUST specify 'speaker': either 'nurse' or 'alien'!
   - Alternate between Nurse Matilda (asking intense questions into her 1947 microphone / writing in her notebook) and Alien Airl (transmitting eerie, mind-shattering telepathic answers).
   - This must feel like an authentic leaked military interrogation tape session!
2. MANDATORY DURATION: Video MUST be at least 1 minute long (65 to 75 seconds). Scripts shorter than 60 seconds are strictly unacceptable.
3. TOTAL SPOKEN WORDS: The total spoken dialogue across all scenes MUST be between 165 and 195 words (each scene MUST have 16 to 22 spoken words across 9 to 11 scenes). Ensure the total spoken words exceed 160 words so that spoken duration strictly reaches at least 65 seconds.
4. SCENES: Break the Short into 9 to 11 sequential dialogue scenes (each scene 6 to 7 seconds of spoken dialogue).
5. Hook & Evidence: Shock hook in scene 1 (Nurse opening the tape / setting date July 1947), cite documented proof '{evidence}', and explain Airl's quote '{quote}'.
6. Cliffhanger Ending (Last Scene): Tease what will be revealed in Part {part_num + 1} and tell viewers to subscribe right now so they don't miss Part {part_num + 1}!
7. Visual Requirement:
   - When speaker is 'nurse': 'visual_subject' MUST be 'nurse matilda interview' or '1947 military interrogation desk', describing the young US Army nurse in 1940s uniform at the wooden desk with vintage microphone in moody bunker lighting.
   - When speaker is 'alien': 'visual_subject' MUST be 'alien airl close up' or 'grey alien telepathic', describing the hyperrealistic extraterrestrial Airl with deep obsidian almond eyes and faint psychic blue glow.
"""

        for model_name in CANDIDATE_MODELS:
            try:
                print_info(f"Generating Alien Interview Part {part_num} ({'Hindi' if is_hindi else 'English'}) using [{model_name}]...")
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
                if script.scenes:
                    script.narration = " ".join(s.narration.strip() for s in script.scenes if s.narration.strip())
                word_count = len(script.narration.split())
                if word_count < 145:
                    print_warning(f"Model {model_name} generated only {word_count} words. Retrying to guarantee >= 60s...")
                    continue
                print_success(f"Alien Interview Script (Part {part_num}) successfully generated with {model_name} ({word_count} words)!")
                return script
            except Exception as e:
                print_warning(f"Model {model_name} attempt: {e}")
                continue

        return self._generate_fallback_short(f"Alien Interview Part {part_num}", target_duration)

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
        """Smart fallback short script when API key is not yet set - uses topic-specific scenes."""
        clean_topic = topic.strip().capitalize()
        # Extract core subject words for search (remove common filler)
        topic_words = [w for w in topic.lower().split() if len(w) > 2 and w not in {'the', 'and', 'for', 'how', 'why', 'what', 'when', 'about'}]
        search_term = ' '.join(topic_words[:3]) if topic_words else clean_topic.lower()

        hook = f"Nobody talks about the hidden truth behind {clean_topic}!"
        scenes = [
            ShortScene(
                scene_number=1,
                narration=f"Nobody talks about the hidden truth behind {clean_topic}!",
                visual_subject=search_term,
                visual_description=f"Dramatic reveal shot related to {clean_topic}",
                search_keywords=[search_term, topic_words[0] if topic_words else clean_topic.lower()],
            ),
            ShortScene(
                scene_number=2,
                narration=f"Most people think they understand {clean_topic}, but what was recently uncovered completely changes everything we thought we knew.",
                visual_subject=f"{search_term} closeup",
                visual_description=f"Detailed close-up view related to {clean_topic}",
                search_keywords=[f"{topic_words[0] if topic_words else clean_topic.lower()} detail",
                                 topic_words[1] if len(topic_words) > 1 else search_term],
            ),
            ShortScene(
                scene_number=3,
                narration=f"Hidden deep within {clean_topic} lies a secret that even experts are afraid to talk about publicly.",
                visual_subject=f"{search_term} mystery",
                visual_description=f"Mysterious and dramatic perspective of {clean_topic}",
                search_keywords=[f"{search_term} secret",
                                 topic_words[-1] if topic_words else clean_topic.lower()],
            ),
            ShortScene(
                scene_number=4,
                narration=f"What do you think about this? Drop your thoughts below and subscribe right now because part 2 reveals the most shocking detail!",
                visual_subject=f"{search_term} dramatic",
                visual_description=f"Epic dramatic perspective of {clean_topic} for the finale",
                search_keywords=[search_term, f"{search_term} dramatic"],
            ),
        ]
        narration = " ".join(s.narration for s in scenes)
        return ShortScript(
            title=f"The Hidden Truth About {clean_topic}! #Shorts",
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
        """Smart fallback multi-scene script when API key is not yet set - uses topic-specific scenes."""
        clean_topic = topic.strip().capitalize()
        topic_lower = topic.strip().lower()
        scenes = [
            Scene(
                scene_number=1,
                narration=f"In a world driven by constant change, one phenomenon has quietly rewritten the rules: {clean_topic}.",
                visual_query=f"{topic_lower} overview introduction",
                visual_description=f"Cinematic establishing shot related to {clean_topic}",
                estimated_duration_sec=6.0,
            ),
            Scene(
                scene_number=2,
                narration=f"To truly grasp the scale of {clean_topic}, we have to look back at where it all began.",
                visual_query=f"{topic_lower} history origins",
                visual_description=f"Historical perspective on {clean_topic}",
                estimated_duration_sec=6.0,
            ),
            Scene(
                scene_number=3,
                narration=f"Breakthrough after breakthrough in {clean_topic} paved the way, accelerating progress at an unprecedented rate.",
                visual_query=f"{topic_lower} development progress",
                visual_description=f"Dynamic shots showing the evolution of {clean_topic}",
                estimated_duration_sec=6.0,
            ),
            Scene(
                scene_number=4,
                narration=f"Yet, with extraordinary power comes unforeseen dilemmas in {clean_topic} that experts are only beginning to confront.",
                visual_query=f"{topic_lower} challenges problems",
                visual_description=f"Dramatic footage showing challenges related to {clean_topic}",
                estimated_duration_sec=6.0,
            ),
            Scene(
                scene_number=5,
                narration=f"The choices made in {clean_topic} over the next five years will determine the trajectory for generations to come.",
                visual_query=f"{topic_lower} future outlook",
                visual_description=f"Forward-looking perspective on {clean_topic}",
                estimated_duration_sec=6.0,
            ),
            Scene(
                scene_number=6,
                narration="The future is arriving faster than anyone anticipated. If you enjoyed this breakdown, like and subscribe.",
                visual_query=f"{topic_lower} conclusion summary",
                visual_description=f"Concluding montage related to {clean_topic}",
                estimated_duration_sec=5.0,
            ),
        ]
        return LongVideoScript(
            title=f"The Rise and Evolution of {clean_topic} | Full Documentary",
            topic=topic,
            description=f"An in-depth investigative exploration into {clean_topic}.\n\nTimestamps:\n0:00 - Introduction\n1:00 - The Origins\n2:30 - The Turning Point\n4:00 - What Lies Ahead\n\nSubscribe to AutoTube for daily documentaries!",
            tags=["documentary", topic_lower, "facts", "education", "explained"],
            scenes=scenes[:num_scenes],
            total_estimated_duration_sec=len(scenes[:num_scenes]) * 6,
        )
