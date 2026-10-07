"""Custom AI Video Director Engine - End-to-end custom video composition with ElevenLabs, NVIDIA, BGM, and YouTube Publish."""

import os
import re
import json
import time
import shutil
from pathlib import Path
from typing import Dict, Any, List, Optional

from autotube.config import PROJECT_ROOT, get_config
from autotube.utils.console import print_info, print_success, print_warning, print_error
from autotube.utils.file_utils import sanitize_filename
from autotube.voice.tts_engine import TTSEngine, ELEVENLABS_VOICES
from autotube.media.background_music import BackgroundMusicManager
from autotube.video.shorts_builder import ShortsBuilder
from autotube.video.subtitle_burner import burn_subtitles
from autotube.uploader.youtube_upload import YouTubeUploader


DIRECTOR_OUTPUT_DIR = PROJECT_ROOT / "output" / "shorts"
TEMP_DIR = PROJECT_ROOT / "temp" / "director"


class DirectorEngine:
    """Orchestrates custom AI video creation based on user's exact script, voice, BGM, and styling."""

    def __init__(self):
        self.cfg = get_config()
        self.bgm_manager = BackgroundMusicManager()
        DIRECTOR_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        TEMP_DIR.mkdir(parents=True, exist_ok=True)

    def get_studio_options(self) -> Dict[str, Any]:
        """Return available voices, BGM audio tracks, and subtitle styles."""
        # Top-quality Voices
        voices = [
            # 🇮🇳 HINDI VOICES — SPACE / MYSTERY / SCIENCE
            {"id": "hi_deep_cinematic_male", "name": "🎙️ Deep Cinematic Male Hindi (Space, Universe, Black Holes) ⭐ BEST", "lang": "Hindi", "gender": "Male", "is_hindi": True, "speed": "0.92x"},
            {"id": "hi_calm_male", "name": "🎙️ Calm Male Hindi (Science Explanations, Astronomy, Planet Facts)", "lang": "Hindi", "gender": "Male", "is_hindi": True, "speed": "0.94x"},
            {"id": "hi_cinematic_male", "name": "🎙️ Cinematic Male Hindi (Mystery, रहस्य, Unsolved Stories)", "lang": "Hindi", "gender": "Male", "is_hindi": True, "speed": "0.91x"},
            {"id": "hi_authoritative_male", "name": "🎙️ Authoritative Male Hindi (History, Science Facts, Educational)", "lang": "Hindi", "gender": "Male", "is_hindi": True, "speed": "0.94x"},
            {"id": "hi_young_male", "name": "🎙️ Young Male Hindi (YouTube Shorts, Fast Facts, Viral Content)", "lang": "Hindi", "gender": "Male", "is_hindi": True, "speed": "1.02x"},
            {"id": "hi_deep_female", "name": "🎙️ Deep Female Hindi (Mystery, Paranormal, Dark Stories)", "lang": "Hindi", "gender": "Female", "is_hindi": True, "speed": "0.93x"},
            {"id": "hi_calm_female", "name": "🎙️ Calm Female Hindi (Science, Space & Storytelling)", "lang": "Hindi", "gender": "Female", "is_hindi": True, "speed": "0.95x"},
            {"id": "hi_cinematic_female", "name": "🎙️ Cinematic Female Hindi (Emotional & Mysterious Stories)", "lang": "Hindi", "gender": "Female", "is_hindi": True, "speed": "0.92x"},

            # 🇺🇸🇬🇧 ENGLISH VOICES — SPACE / MYSTERY / SCIENCE
            {"id": "en_deep_cinematic_male", "name": "🎙️ Deep Cinematic American Male (Space Shorts, Universe, Black Holes) ⭐ BEST", "lang": "English", "gender": "Male", "is_hindi": False, "speed": "0.92x"},
            {"id": "en_deep_british_male", "name": "🎙️ Deep British Male (Premium Space Documentary)", "lang": "English", "gender": "Male", "is_hindi": False, "speed": "0.92x"},
            {"id": "en_calm_british_male", "name": "🎙️ Calm British Male (Science, Astronomy, Universe)", "lang": "English", "gender": "Male", "is_hindi": False, "speed": "0.94x"},
            {"id": "en_cinematic_narrator", "name": "🎙️ Cinematic Male Narrator (Mystery, Aliens, Time Travel)", "lang": "English", "gender": "Male", "is_hindi": False, "speed": "0.92x"},
            {"id": "en_deep_warm_male", "name": "🎙️ Deep Warm Male (Black Holes, Cosmic Events, Deep Space)", "lang": "English", "gender": "Male", "is_hindi": False, "speed": "0.92x"},
            {"id": "en_authoritative_male", "name": "🎙️ Authoritative Male (Scientific Facts & Educational Content)", "lang": "English", "gender": "Male", "is_hindi": False, "speed": "0.93x"},
            {"id": "en_calm_female", "name": "🎙️ Calm Female (Space & Science Storytelling)", "lang": "English", "gender": "Female", "is_hindi": False, "speed": "0.95x"},
            {"id": "en_cinematic_female", "name": "🎙️ Cinematic Female (Mystery & Emotional Stories)", "lang": "English", "gender": "Female", "is_hindi": False, "speed": "0.93x"},

            # Classic / Legacy
            {"id": "akashvani", "name": "🎙️ आकाशवाणी (Cosmic Echo Devavani - Divine Echo)", "lang": "Hindi", "gender": "Divine", "is_hindi": True},
            {"id": "madhur", "name": "🎙️ Madhur (Natural Hindi Documentary Narrator)", "lang": "Hindi", "gender": "Male", "is_hindi": True},
            {"id": "adam", "name": "🎙️ Adam (US Male Cinematic #1 Viral)", "lang": "English", "gender": "Male", "is_hindi": False},
        ]

        # BGM Tracks & Categories
        bgm_tracks = [
            {"filename": "psychology", "title": "🧠 Dark Psychology (Ambient Tension)", "category": "Psychology"},
            {"filename": "space", "title": "🌌 Cosmic Space (Deep Ambient Void)", "category": "Space"},
            {"filename": "history", "title": "⚔️ History & Bharat (Ancient Epic Chords)", "category": "History"},
            {"filename": "mystery", "title": "🕵️ Eerie Mystery & Unsolved Cases", "category": "Mystery"},
            {"filename": "alien", "title": "🛸 Alien Sci-Fi (Atmospheric / Outer Space)", "category": "SciFi"},
            {"filename": "none", "title": "🔇 None (Speech / Voice Narration Only)", "category": "None"},
        ]

        # Subtitle Styles
        subtitle_styles = [
            {
                "id": "hormozi",
                "name": "🔥 Hormozi / Viral Pop (Yellow Highlights, Bold Outline)",
            },
            {
                "id": "cinematic",
                "name": "💎 Clean Cinematic (Bold White with Soft Shadow)",
            },
            {
                "id": "none",
                "name": "🚫 No Subtitles (Clean Video Only)",
            },
        ]

        return {
            "voices": voices,
            "bgm_tracks": bgm_tracks,
            "subtitle_styles": subtitle_styles,
        }

    def enhance_script_with_ai(
        self,
        raw_input: str,
        topic: Optional[str] = None,
        language: str = "hi",
        video_format: str = "short",
    ) -> Dict[str, Any]:
        """Enhance user's script or 1-line concept into a viral script formatted for Short or Long video."""
        lang_lower = (language or "hi").lower()
        is_hindi = lang_lower in ("hi", "hindi")
        is_hinglish = lang_lower in ("hinglish", "hi-en")
        is_long = (video_format == "landscape_long")
        gemini_key = os.getenv("GEMINI_API_KEY", "") or getattr(self.cfg, "gemini_api_key", "")

        target_words = "350 to 500 words (3.0 to 4.5 minutes documentary length)" if is_long else "160 to 195 words (minimum 60 to 75 seconds, full 1 minute viral Short length)"
        format_desc = "16:9 Landscape Documentary Video" if is_long else "9:16 Vertical YouTube Short"

        if gemini_key:
            try:
                from google import genai
                client = genai.Client(api_key=gemini_key)

                if is_hindi:
                    lang_instruction = "Write the entire narration in pure, thrilling, natural Hindi (Devanagari script) with high emotional engagement."
                elif is_hinglish:
                    lang_instruction = "Write the narration in viral conversational Hinglish (Hindi mixed with English words in Roman script) that young audiences in India love."
                else:
                    lang_instruction = "Write the narration in high-energy, suspenseful English with viral pacing and dramatic hooks."

                prompt = f"""You are a top-tier viral YouTube Short & Documentary scriptwriter who crafts scripts that retain 80%+ audience retention and drive massive subscriber conversion.

Task: Transform this user idea/topic/script into a high-retention, thrilling narration script for a {format_desc}.
Target word count: {target_words}.

User Topic / Concept / Request:
"{raw_input}"
Focus: {topic or 'Mysteries / Real Incidents / History / Mind-Blowing Facts'}

Language Instruction:
{lang_instruction}

IMPORTANT CREATIVE INSTRUCTION:
- If the user provided a 1-line concept, topic, or command (e.g. "Punarjanam pe ek short video banao real incident pe with proof", "Bermuda triangle mystery", etc.), you MUST research/generate a FULL, COMPLETE, deeply thrilling, factual story from scratch based on authentic real-world incidents, records, or historical evidence (e.g. for rebirth, use documented cases like Shanti Devi / Mahatma Gandhi 1935 investigation, Taranjit Singh, etc.).
- NEVER just echo or repeat the user's prompt as the narration text! Deliver the actual gripping narrative from the first word to the last!

CRITICAL 1-MINUTE MINIMUM DURATION MANDATE:
- For YouTube Shorts, the script narration MUST BE MINIMUM 1 FULL MINUTE (60 to 75 seconds spoken audio).
- At standard natural speaking pace (130-150 words/minute), this requires AT LEAST 160 TO 195 WORDS.
- DO NOT rush or make it brief (never under 150 words). Provide detailed, chilling storytelling with deep suspense and compelling scientific or historical depth!

STRICT RETENTION & SUBSCRIBER GROWTH BLUEPRINT:
1. THE 3-SECOND SCROLL-STOPPER OPENING HOOK (CRUCIAL):
   - ABSOLUTELY NO greetings, intros, or generic pleasantries (Never say "Hello dosto", "Aaj hum baat karenge", "Ek baar ki baat hai").
   - The opening MUST punch the viewer immediately with an Impossible Paradox, High-Stakes Warning, or Shocking Truth in the first 10-15 words.
   - Examples of opening hook styles:
     * "Agar aapko lagta hai ki maut ke baad sab khatam ho jata hai, toh agle 60 seconds aapke hosh uda denge!"
     * "1935 me ek 4 saal ki bachhi ne ek aisi sachayi bayaan ki jisne khud Mahatma Gandhi ko hairan kar diya..."
     * "99% log nahi jante ki is ghatna ko sarkar ne 50 saalon tak top-secret kyu rakha tha!"

2. SUSPENSE-DRIVEN STORY BEATS (BODY):
   - Fast-paced, curiosity-building sentence flow across 8-12 suspenseful story beats.
   - Present intriguing evidence, twists, or real eyewitness facts without unnecessary fluff.

3. THE ENGAGEMENT & SUBSCRIBER CONVERSION OUTRO (MANDATORY):
   - The ending MUST NOT just stop. It must include 3 distinct psychological elements:
     A. Mind-Bending Question / Open Loop: Leave a provocative question ringing in their head (e.g. "Kya ye sach me punarjanam ka saboot tha, ya science ka sabse bada anjaana rahasya?").
     B. Polarized Comment Debate Trigger: Challenge the viewer to comment their answer (e.g. "Agar aapko iska sach pata hai toh comment me 'YES' ya 'NO' likhkar batao!").
     C. High-Value Subscribe & Like CTA: Compel them to subscribe (e.g. "Aur aisi hi hairatangez sachhi ghatnao aur rahasyo ke liye, video ko LIKE karein aur channel ko abhi SUBSCRIBE karein!").

Output STRICT JSON with these keys:
- "hook": The explosive opening 1-2 sentences (the 3-second hook).
- "body": The main high-tension story scenes.
- "cliffhanger": The closing question + comment debate trigger + Like & Subscribe CTA.
- "full_narration": Complete continuous script combining hook + body + cliffhanger seamlessly (without any scene headings or bracketed labels).
- "titles": Array of 3 viral, high-CTR YouTube video titles (include relevant emojis, and {'#Shorts' if not is_long else ''}).
- "pinned_comment": Provocative debate question for pinned comments to drive 100+ replies.
- "tags": Array of 6 relevant tags / hashtags.
"""
                data = None
                models_to_try = [
                    "gemini-3.5-flash-lite",
                    "gemini-3.1-flash-lite",
                    "gemini-3.5-flash",
                    "gemini-3.8-flash",
                ]
                for model_name in models_to_try:
                    for attempt in range(2):
                        try:
                            resp = client.models.generate_content(
                                model=model_name,
                                contents=prompt,
                                config={"response_mime_type": "application/json"}
                            )
                            if resp and resp.text:
                                clean_text = resp.text.strip()
                                if "```json" in clean_text:
                                    clean_text = clean_text.split("```json")[1].split("```")[0].strip()
                                elif "```" in clean_text:
                                    clean_text = clean_text.split("```")[1].split("```")[0].strip()
                                data = json.loads(clean_text)
                                print_success(f"AI Script generated successfully with {model_name}!")
                                break
                        except Exception as me:
                            print_warning(f"Model {model_name} (attempt {attempt+1}) failed: {me}. Trying next...")
                            time.sleep(0.8)
                    if data:
                        break

                if not data:
                    raise RuntimeError("All Gemini models failed")

                narration = data.get("full_narration", raw_input)
                word_count = len(narration.split())
                est_seconds = round(word_count / 2.6, 1)

                return {
                    "success": True,
                    "full_narration": narration,
                    "hook": data.get("hook", ""),
                    "body": data.get("body", ""),
                    "cliffhanger": data.get("cliffhanger", ""),
                    "titles": data.get("titles", [f"{topic or 'Mystery'} Revealed {'#Shorts' if not is_long else ''}"]),
                    "pinned_comment": data.get("pinned_comment", "Aapka is baare me kya sochna hai? Comment karein 👇"),
                    "tags": data.get("tags", ["#Shorts", "#Mystery", "#Viral"] if not is_long else ["#Documentary", "#Mystery", "#History", "#Facts"]),
                    "word_count": word_count,
                    "est_seconds": est_seconds,
                    "is_long": is_long,
                }
            except Exception as e:
                print_warning(f"AI script enhancer error: {e}. Using heuristic fallback...")

        # Heuristic fallback if Gemini unavailable
        words = raw_input.strip().split()
        est_sec = round(len(words) / 2.6, 1)
        suffix = " #Shorts" if not is_long else ""
        hook = "Agar aapko lagta hai ki aap sab jante hain, toh agle 45 seconds aapke hosh uda denge!"
        cliffhanger = "Aapke hisaab se kya ye sach ho sakta hai? Comment me apna jawab zaroor batayein, video ko LIKE karein aur aisi hi hairatangez sachhi kahaniyo ke liye channel ko abhi SUBSCRIBE karein!"
        body_text = raw_input.strip()
        full_text = f"{hook} {body_text} {cliffhanger}"
        return {
            "success": True,
            "full_narration": full_text,
            "hook": hook,
            "body": body_text,
            "cliffhanger": cliffhanger,
            "titles": [
                f"{raw_input[:40]}... (Sach Kya Hai?){suffix}",
                f"99% Log Iska Sach Nahi Jante! 😱{suffix}",
                f"The Shocking Truth Revealed{suffix}",
            ],
            "pinned_comment": "Aapke hisaab se kya ye sach ho sakta hai? Comment me YES ya NO likhkar batao 👇",
            "tags": ["#Shorts", "#Mystery", "#MindBlown", "#Facts"] if not is_long else ["#Documentary", "#Mystery", "#Facts", "#Trending"],
            "word_count": len(full_text.split()),
            "est_seconds": round(len(full_text.split()) / 2.6, 1),
            "is_long": is_long,
        }

    def generate_voice_audition(self, voice_id: str, sample_text: Optional[str] = None) -> Path:
        """Generate a 3-second audio sample for the user to audition in browser."""
        text = sample_text or "This is a live preview of your selected AI narrator voice."
        output_file = TEMP_DIR / f"audition_{voice_id}_{int(time.time())}.mp3"
        tts = TTSEngine(default_voice=voice_id)
        res = tts.synthesize(text=text, output_audio_path=output_file, voice=voice_id)
        return res.audio_path

    def _extract_visual_search_query(self, sentence: str, topic: str, scene_idx: int) -> str:
        """Extract a clean, high-relevance English visual query for stock or AI video engines."""
        s_lower = sentence.lower()
        t_lower = topic.lower()

        # Keyword mapping from common Hindi/English concepts to visual keywords
        mappings = [
            (("black hole", "blackhole", "singularity", "event horizon", "accretion", "spaghetti"), "black hole space"),
            (("space", "antariksh", "brahmand", "galaxy", "solar system", "universe", "cosmos", "stars"), "deep space galaxy"),
            (("earth", "dharati", "planet", "neela grah"), "planet earth space"),
            (("ocean", "samundar", "sea", "underwater", "trench"), "dark deep ocean abyss"),
            (("brain", "dimag", "mind", "psychology", "soch"), "human brain neural networks glowing"),
            (("temple", "mandir", "ancient", "prachin", "stone"), "ancient stone temple ruins dramatic"),
            (("gandhi", "mahatma"), "Mahatma Gandhi archival portrait vintage"),
            (("shanti devi", "punarjanam", "rebirth", "child", "bachhi"), "vintage 1930s young girl thinking portrait"),
            (("crowd", "bheed", "station", "train"), "vintage crowd busy street 1930s"),
            (("police", "committee", "investigation", "jaanch", "report", "proof"), "vintage detective crime investigation papers"),
            (("alien", "ufo", "roswell"), "flying saucer ufo crash site vintage"),
        ]
        for triggers, query in mappings:
            if any(k in s_lower for k in triggers) or any(k in t_lower for k in triggers):
                return query

        # Fallback: find English words or topic
        eng_words = [w for w in re.findall(r"[a-zA-Z]{4,}", sentence) if w.lower() not in ("nahi", "hoga", "raha", "baat", "karein", "aur", "mein", "saal", "kuch", "apna")]
        if eng_words:
            return f"{' '.join(eng_words[:2])} cinematic"
        clean_top = re.sub(r"[#\-_/:|😱🤯👁️]", " ", topic).strip()
        return f"{clean_top[:25]} cinematic"

    def _extract_ai_scene_prompt(self, sentence: str, topic: str, scene_idx: int) -> str:
        """Generate high-aesthetic cinematic visual prompt matching the exact topic genre."""
        s_lower = sentence.lower()
        t_lower = topic.lower()

        # Check for Astronomy / Black Hole / Cosmic Space
        if any(k in t_lower or k in s_lower for k in ("black hole", "blackhole", "singularity", "event horizon", "spaghetti")):
            return "cinematic photorealistic black hole accretion disk warping spacetime and light near planet Earth, massive cosmic singularity, gravitational lensing, deep space void, IMAX astronomy movie still, 8k"
        elif any(k in t_lower or k in s_lower for k in ("space", "antariksh", "brahmand", "galaxy", "universe", "planet", "solar system", "stars", "cosmos")):
            if any(k in s_lower for k in ("earth", "dharati", "grah", "neela grah")):
                return "cinematic photorealistic view of planet Earth floating in deep space with glowing atmosphere and cosmic stars, 8k NASA James Webb telescope photo"
            return "cinematic deep space cosmic view of colorful swirling spiral galaxy, vibrant glowing nebulae and distant stars, IMAX astronomy documentary still, 8k"

        # Check for historical mysteries
        if "bose" in t_lower or "netaji" in t_lower:
            subject = "1945 Subhas Chandra Bose WWII mystery"
        elif "shanti devi" in t_lower or "punarjanam" in t_lower or "rebirth" in t_lower:
            subject = "1935 vintage India reincarnation mystery"
        elif "gandhi" in t_lower:
            subject = "1930s Mahatma Gandhi vintage India"
        elif "roswell" in t_lower or "ufo" in t_lower:
            subject = "1947 Roswell New Mexico military mystery"
        elif "kailasa" in t_lower or "temple" in t_lower:
            subject = "ancient Kailasa monolithic rock temple"
        else:
            subject = "cinematic documentary scene"

        # Context action
        if any(k in s_lower for k in ("crash", "plane", "uda", "airfield", "taiwan", "taihoku", "runway")):
            return "vintage 1945 twin-engine military transport aircraft on dark runway in heavy storm, atmospheric volumetric lights, cinematic IMAX movie still, 8k"
        elif any(k in s_lower for k in ("commission", "jaanch", "report", "file", "dastawej", "saboot", "khulase")):
            return "vintage 1940s detective room wooden desk with typed classified documents, aged yellowed paper, folder stamped CONFIDENTIAL, warm cinematic desk lamp lighting, 8k"
        elif any(k in s_lower for k in ("soviet", "russia", "nikal", "secret", "train", "station")):
            return "vintage 1940s steam train station in cold foggy night, shadowy mysterious traveler in overcoat, cinematic noir lighting, 8k"
        elif any(k in s_lower for k in ("bachhi", "shanti", "pati", "mathura", "parivar", "bheed")):
            return "vintage 1935 Indian old city street crowd, authentic historic architecture, thoughtful young Indian girl looking back, cinematic 35mm film photography, 8k"

        eng_q = self._extract_visual_search_query(sentence, topic, scene_idx)
        return f"{subject}, {eng_q}, highly detailed, dramatic atmospheric lighting, 8k movie still"

    def render_custom_video(
        self,
        script_text: str,
        title: str,
        voice: str = "hi_deep_cinematic_male",
        voice_speed: float = 0.92,
        bgm_filename: Optional[str] = None,
        bgm_volume: float = 0.16,
        subtitle_style_id: str = "hormozi",
        enable_classified_badge: bool = False,
        visual_engine: str = "auto",
        video_format: str = "short",
        language: str = "hi",
        real_incident_mode: bool = False,
        visual_mode: str = "hybrid",
        auto_viral_hook: bool = True,
        progress_callback = None,
    ) -> Dict[str, Any]:
        """Render complete custom Short (9:16) or Long (16:9) video matching user script, voice, BGM, and visual choices."""
        slug = sanitize_filename(title or "custom_video")
        is_long = (video_format == "landscape_long")
        target_width = 1920 if is_long else 1080
        target_height = 1080 if is_long else 1920
        orientation = "landscape" if is_long else "portrait"
        format_label = "16:9 Landscape Long Video" if is_long else "9:16 Vertical Short"
        # Respect user's explicit choice for real_incident_mode (no aggressive auto-override)
        if visual_mode == "real_only":
            real_incident_mode = True

        # Space / Cosmic / Science topics do not use historical incident mode archives
        is_space_or_sci = any(k in (title + " " + script_text).lower() for k in (
            "black hole", "space", "antariksh", "galaxy", "universe", "planet", "solar system", "cosmos", "gravity", "spaghettification"
        ))
        if is_space_or_sci:
            real_incident_mode = False

        output_dir = PROJECT_ROOT / "output" / ("longform" if is_long else "shorts")
        output_dir.mkdir(parents=True, exist_ok=True)
        final_video_path = output_dir / f"{slug}_{int(time.time())}.mp4"

        # Safeguard: Auto-Inject Ending Debate & Subscribe Outro ONLY if completely absent
        active_script = script_text.strip()
        if auto_viral_hook and not is_long:
            lower_s = active_script.lower()
            # If the script already has ANY mention of subscribe, like, comment, share, do NOT duplicate
            has_cta = any(k in lower_s for k in (
                "subscribe", "सब्सक्राइब", "like", "लाइक", "comment", "कमेंट", "follow", "फॉलो", "share", "शेयर"
            ))
            if not has_cta:
                lang_l = (language or "hi").lower()
                if lang_l in ("en", "english"):
                    cta_addon = " What is your opinion on this? Comment below and subscribe for more amazing facts!"
                else:
                    cta_addon = " कमेंट में अपनी राय बताएं, वीडियो को लाइक करें और चैनल को सब्सक्राइब जरूर करें!"
                active_script = f"{active_script} {cta_addon}"
                print_info("Auto Viral Booster: Injected 1 clean Subscribe & Like CTA.")

        if progress_callback: progress_callback(10, f"Synthesizing AI Voiceover ({voice}) for {format_label}...")

        # 1. Synthesize Voice
        voice_audio = TEMP_DIR / f"{slug}_voice.mp3"
        rate_str = f"+{int((voice_speed - 1.0) * 100)}%" if voice_speed >= 1.0 else f"-{int((1.0 - voice_speed) * 100)}%"
        tts = TTSEngine(default_voice=voice, rate=rate_str)
        tts_res = tts.synthesize(text=active_script, output_audio_path=voice_audio, voice=voice)
        total_duration = tts_res.duration_seconds

        if progress_callback: progress_callback(30, "Resolving and mixing Background Music (BGM)...")

        # 2. Select & Mix BGM (Guaranteed file check to avoid directory errors)
        mixed_audio = TEMP_DIR / f"{slug}_mixed.mp3"
        bgm_path = None
        if bgm_filename and bgm_filename != "none":
            cat_tracks = self.bgm_manager.get_music_tracks(category=bgm_filename)
            if cat_tracks:
                import random
                bgm_path = random.choice(cat_tracks)
                print_info(f"Custom Video: Selected category BGM '{bgm_filename}': {bgm_path.name}")
            else:
                audio_dir = PROJECT_ROOT / "assets" / "audio"
                found = [f for f in audio_dir.rglob(f"*{bgm_filename}*") if f.is_file() and f.suffix in (".mp3", ".wav")]
                if found:
                    bgm_path = found[0]
                    print_info(f"Custom Video: Found BGM audio file: {bgm_path.name}")

        self.bgm_manager.mix_voice_and_music(
            voice_path=tts_res.audio_path,
            output_mixed_path=mixed_audio,
            music_path=bgm_path,
            music_volume=bgm_volume,
            include_whoosh=not is_long,
        )

        # 1 Scene per Sentence / Line for rapid, high-retention visual pacing!
        sentences = [s.strip() for s in re.split(r"[.!?।\n]+", active_script) if len(s.strip()) > 3]
        if not sentences:
            sentences = [active_script]
        max_scene_count = min(35 if is_long else 25, len(sentences))
        sentences = sentences[:max_scene_count]

        # 3. Source Authentic Historical / Archival Proofs ONLY if Real Incident Mode explicitly enabled
        archival_visuals: List[Path] = []
        if real_incident_mode and (visual_mode in ("hybrid", "real_only", "multi_cinematic")):
            try:
                if progress_callback: progress_callback(42, "📜 Real Incident Mode: Searching historical archives & genuine proof photos...")
                from autotube.media.archival_fetcher import ArchivalFetcher
                fetcher = ArchivalFetcher()
                archival_visuals = fetcher.fetch_archival_visuals(
                    topic=title,
                    script_text=script_text,
                    count=max_scene_count,
                    progress_callback=progress_callback,
                )
                if archival_visuals:
                    print_success(f"Archival Mode: Sourced {len(archival_visuals)} authentic historical photos/documents!")
            except Exception as e:
                print_warning(f"Error fetching archival visuals: {e}")

        if progress_callback: progress_callback(55, f"Acquiring visual scenes ({orientation} {target_width}x{target_height}, Mode: {visual_mode})...")

        # 4. Acquire Video Scene Assets (Multi-Source AI Best Match / Hybrid Real Archives / AI Visuals)
        scene_videos: List[Path] = []
        from autotube.media.ai_visuals import VisualGenerator
        from autotube.media.nvidia_video import NvidiaVideoGenerator
        from autotube.media.pexels_video import PexelsVideoFetcher
        from autotube.media.multi_stock_aggregator import MultiStockAggregator

        vg = VisualGenerator()
        nvidia = NvidiaVideoGenerator()
        pexels = PexelsVideoFetcher()
        multi_agg = MultiStockAggregator()

        for idx, sentence in enumerate(sentences[:max_scene_count]):
            scene_target = TEMP_DIR / f"scene_{idx}_{slug}.mp4"
            acquired_video = None

            # Mode 1: Multi-Source AI Best Match (Mixkit + Coverr + Pexels + Archival) [RECOMMENDED]
            if visual_mode in ("multi_cinematic", "multi_best", "auto") and not (visual_mode in ("hybrid", "real_only", "ai_only", "stock")):
                # If real incident mode is active, alternate with archival proofs on odd cuts
                use_real = (idx % 2 == 1) if (real_incident_mode and archival_visuals) else False
                if use_real and archival_visuals:
                    acquired_video = archival_visuals[(idx // 2) % len(archival_visuals)]
                else:
                    if progress_callback:
                        progress_callback(55 + int((idx / max_scene_count) * 18), f"🔍 Multi-Stock AI Searching & Ranking Scene {idx+1}/{len(sentences[:max_scene_count])}...")
                    acquired_video = multi_agg.get_best_scene_asset(
                        scene_text=sentence,
                        title=title,
                        scene_index=idx,
                        orientation=orientation,
                        archival_pool=archival_visuals,
                        allow_ai_fallback=False,
                    )

            # Mode 2: 100% Real Archives Only
            elif visual_mode == "real_only" and archival_visuals:
                acquired_video = archival_visuals[idx % len(archival_visuals)]

            # Mode 3: Hybrid Mode (Real Archives + AI Visuals)
            elif visual_mode == "hybrid":
                use_real = (idx % 2 == 1) if archival_visuals else False
                if use_real and archival_visuals:
                    acquired_video = archival_visuals[(idx // 2) % len(archival_visuals)]
                else:
                    ai_prompt = self._extract_ai_scene_prompt(sentence, title, idx)
                    ai_img_path = TEMP_DIR / f"hybrid_ai_{idx}_{slug}.jpg"
                    if progress_callback:
                        progress_callback(55 + int((idx / max_scene_count) * 18), f"Generating AI Scene {idx+1}/{len(sentences[:max_scene_count])}...")
                    ai_res = vg.generate_image(prompt=ai_prompt, output_path=ai_img_path, width=target_width, height=target_height, style="cinematic")
                    if ai_res and ai_res.exists() and ai_res.stat().st_size > 4000:
                        acquired_video = ai_res
                    else:
                        # Fallback to multi-aggregator best stock video
                        acquired_video = multi_agg.get_best_scene_asset(
                            scene_text=sentence,
                            title=title,
                            scene_index=idx,
                            orientation=orientation,
                            archival_pool=archival_visuals,
                        )

            # Mode 4: Stock Videos Only across Mixkit, Coverr, Pexels
            elif visual_mode == "stock":
                if progress_callback:
                    progress_callback(55 + int((idx / max_scene_count) * 18), f"🎥 Multi-Stock Fetching Scene {idx+1}/{len(sentences[:max_scene_count])}...")
                acquired_video = multi_agg.get_best_scene_asset(
                    scene_text=sentence,
                    title=title,
                    scene_index=idx,
                    orientation=orientation,
                    archival_pool=archival_visuals,
                    allow_ai_fallback=False,
                )

            # Mode 5: Pure AI Generated Scenes
            elif visual_mode == "ai_only":
                ai_prompt = self._extract_ai_scene_prompt(sentence, title, idx)
                ai_img_path = TEMP_DIR / f"pure_ai_{idx}_{slug}.jpg"
                if progress_callback:
                    progress_callback(55 + int((idx / max_scene_count) * 18), f"Generating AI Scene {idx+1}/{len(sentences[:max_scene_count])}...")
                ai_res = vg.generate_image(prompt=ai_prompt, output_path=ai_img_path, width=target_width, height=target_height, style="cinematic")
                if ai_res and ai_res.exists():
                    acquired_video = ai_res

            # Fallbacks: Nvidia AI / Pexels Stock Video & Photo with English queries
            if not acquired_video and visual_engine in ("nvidia", "auto") and nvidia.is_configured():
                english_q = self._extract_visual_search_query(sentence, title, idx)
                acquired_video = nvidia.generate_video(prompt=english_q, output_path=scene_target)

            if not acquired_video and pexels.is_configured():
                english_q = self._extract_visual_search_query(sentence, title, idx)
                acquired_video = pexels.get_scene_video(search_query=english_q, orientation=orientation, scene_index=idx)

            if not acquired_video and pexels.is_configured():
                english_q = self._extract_visual_search_query(sentence, title, idx)
                acquired_video = pexels.get_scene_photo(search_query=english_q, orientation=orientation, scene_index=idx)

            if not acquired_video and archival_visuals:
                acquired_video = archival_visuals[idx % len(archival_visuals)]

            if not acquired_video:
                vault_dir = PROJECT_ROOT / "assets" / "ai_movie_clips"
                if vault_dir.exists():
                    vault_clips = sorted([f for f in vault_dir.glob("*.mp4") if f.stat().st_size > 10000])
                    if vault_clips:
                        acquired_video = vault_clips[idx % len(vault_clips)]

            if not acquired_video:
                canonical_dir = PROJECT_ROOT / "assets" / "alien_interview" / "videos"
                if canonical_dir.exists():
                    all_c = sorted(list(canonical_dir.glob("*.mp4")))
                    if all_c:
                        acquired_video = all_c[idx % len(all_c)]

            if acquired_video and acquired_video.exists():
                scene_videos.append(acquired_video)

        # GUARANTEE 100% VISUAL COVERAGE (Zero Blank Frame Guarantee!)
        if not scene_videos:
            if archival_visuals:
                scene_videos = list(archival_visuals)
            elif pexels.is_configured():
                fallback_v = pexels.get_scene_video("mysterious dramatic cinematic", orientation=orientation)
                if fallback_v:
                    scene_videos.append(fallback_v)

        # If some scenes were acquired but fewer than needed, cycle them so all cuts are covered
        needed_scenes = len(sentences[:max_scene_count])
        if scene_videos and len(scene_videos) < needed_scenes:
            base_pool = list(scene_videos)
            while len(scene_videos) < needed_scenes:
                scene_videos.append(base_pool[len(scene_videos) % len(base_pool)])

        if progress_callback: progress_callback(75, f"Compositing video timeline ({target_width}x{target_height}, {len(scene_videos)} scenes)...")

        # 4. Composite Video
        builder = ShortsBuilder()
        unsubtitled_video = TEMP_DIR / f"{slug}_unsubbed.mp4"

        num_scenes = max(1, len(scene_videos))
        # Word-proportional scene durations so scene cuts align with speech transitions
        scene_word_counts = [max(1, len(s.split())) for s in sentences[:num_scenes]]
        if len(scene_word_counts) < num_scenes:
            scene_word_counts.extend([1] * (num_scenes - len(scene_word_counts)))
        total_words = max(1, sum(scene_word_counts))
        scene_durations = [round(total_duration * (wc / total_words), 2) for wc in scene_word_counts]
        if scene_durations:
            diff = round(total_duration - sum(scene_durations), 2)
            scene_durations[-1] = max(1.0, round(scene_durations[-1] + diff, 2))

        builder.build_short(
            audio_path=mixed_audio if mixed_audio.exists() else tts_res.audio_path,
            output_path=unsubtitled_video,
            scene_videos=scene_videos if scene_videos else None,
            scene_durations=scene_durations,
            subtitles_file=None,
            width=target_width,
            height=target_height,
        )

        if progress_callback: progress_callback(88, "Applying styled subtitles and audio polish...")

        # 5. Burn Custom Subtitles
        if subtitle_style_id == "none":
            shutil.copy(unsubtitled_video, final_video_path)
        else:
            if is_long:
                style_map = {
                    "hormozi": "FontName=Arial Black,FontSize=22,PrimaryColour=&H0000FFFF,OutlineColour=&H00000000,BorderStyle=1,Outline=2.5,Shadow=1.5,Alignment=2,MarginV=55",
                    "cinematic": "FontName=Arial,FontSize=20,PrimaryColour=&H00FFFFFF,OutlineColour=&H00000000,BorderStyle=1,Outline=2,Shadow=1,Alignment=2,MarginV=50",
                }
            else:
                style_map = {
                    "hormozi": "FontName=Arial Black,FontSize=28,PrimaryColour=&H0000FFFF,OutlineColour=&H00000000,BorderStyle=1,Outline=3,Shadow=2,Alignment=2,MarginV=250",
                    "cinematic": "FontName=Arial,FontSize=24,PrimaryColour=&H00FFFFFF,OutlineColour=&H00000000,BorderStyle=1,Outline=2,Shadow=1,Alignment=2,MarginV=240",
                }
            chosen_style = style_map.get(subtitle_style_id, style_map["hormozi"])

            hook_badge = (PROJECT_ROOT / "assets" / "hook_badge.png") if (auto_viral_hook and not is_long) else None
            if enable_classified_badge and (PROJECT_ROOT / "assets" / "classified_badge.png").exists():
                hook_badge = PROJECT_ROOT / "assets" / "classified_badge.png"
            sub_badge = (PROJECT_ROOT / "assets" / "like_subscribe_bell_banner.png") if auto_viral_hook else None

            burn_subtitles(
                input_video=unsubtitled_video,
                subtitles_file=tts_res.subtitles_ass_path or tts_res.subtitles_srt_path,
                output_video=final_video_path,
                force_style=chosen_style,
                hook_badge=hook_badge,
                subscribe_badge=sub_badge,
                duration=total_duration,
            )

        if progress_callback: progress_callback(100, f"✅ {format_label} rendered successfully!")

        size_mb = round(final_video_path.stat().st_size / (1024 * 1024), 2)
        print_success(f"Director Video generated: {final_video_path.name} ({size_mb} MB, {total_duration:.1f}s)!")

        return {
            "success": True,
            "video_filename": final_video_path.name,
            "video_path": str(final_video_path),
            "stream_url": f"/api/media/stream/{final_video_path.name}",
            "size_mb": size_mb,
            "duration": total_duration,
            "title": title,
            "format": video_format,
            "is_long": is_long,
        }
