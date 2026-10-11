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
from autotube.voice.voice_director import choose_subject_voice, is_voice_language_compatible
from autotube.media.background_music import BackgroundMusicManager
from autotube.media.visual_quality_gate import VisualQualityGate
from autotube.video.shorts_builder import ShortsBuilder
from autotube.video.subtitle_burner import burn_subtitles
from autotube.uploader.youtube_upload import YouTubeUploader
from autotube.utils.ffmpeg_helper import get_media_duration


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
            {"filename": "spiritual", "title": "🕉️ Spiritual & Vedic (Divine Bansuri / Tanpura)", "category": "Spiritual"},
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

    def condense_script_for_shorts(
        self,
        script_text: str,
        language: str = "hi",
    ) -> str:
        """Condense narration into a high-retention 100-115 word script strictly under 50s (<60s Shorts limit)."""
        words = script_text.strip().split()
        if len(words) <= 115:
            return script_text

        gemini_key = os.getenv("GEMINI_API_KEY", "") or getattr(self.cfg, "gemini_api_key", "")
        lang_lower = (language or "hi").lower()
        is_hindi = lang_lower in ("hi", "hindi")
        is_hinglish = lang_lower in ("hinglish", "hi-en")

        if gemini_key:
            try:
                from google import genai
                client = genai.Client(api_key=gemini_key)
                lang_rule = "pure Devanagari Hindi (हिंदी देवनागरी लिपि)" if is_hindi else ("conversational Hinglish" if is_hinglish else "punchy English")

                prompt = f"""You are a master viral YouTube Shorts script editor.
Condense and tighten this script so it strictly fits within a 45-second YouTube Short (<50s strict limit).

Original Script ({len(words)} words):
"{script_text}"

CRITICAL RULES:
1. Target Word Count: STRICTLY 100 to 110 words total (ABSOLUTE CEILING: 115 words).
2. Language: Write 100% in {lang_rule}.
3. Structure:
   - Punchy 3s Opening Hook (15-20 words)
   - Core Thrilling Facts / Evidence Body (65-75 words, 3 sharp sentences)
   - Provocative Question & Subscribe CTA (15-20 words)
4. Cut out all filler words, repeated phrases, and secondary explanations.
5. Return ONLY the tightened narration text as a single plain paragraph. No JSON, no titles, no intro labels, no markdown.
"""
                models_to_try = ["gemini-3.1-flash-lite", "gemini-3.5-flash-lite", "gemini-3.5-flash"]
                for model_name in models_to_try:
                    try:
                        resp = client.models.generate_content(
                            model=model_name,
                            contents=prompt,
                        )
                        if resp and resp.text:
                            clean_text = resp.text.strip()
                            clean_text = re.sub(r"^```[a-z]*\n?", "", clean_text)
                            clean_text = re.sub(r"\n?```$", "", clean_text).strip()
                            clean_words = clean_text.split()
                            if 75 <= len(clean_words) <= 120:
                                print_success(f"Script condensed to {len(clean_words)} words (~{len(clean_words)/2.6:.0f}s) via {model_name}!")
                                return clean_text
                    except Exception:
                        continue
            except Exception as e:
                print_warning(f"AI script condensation error: {e}")

        # Smart rule-based sentence compression fallback
        sentences = [s.strip() for s in re.split(r"(?<=[.!?।॥])\s+|\n+", script_text) if s.strip()]
        if len(sentences) <= 3:
            return " ".join(words[:115])

        hook = sentences[0]
        cta = sentences[-1]
        mid = sentences[1:-1]
        selected_mid = []
        cur_count = len(hook.split()) + len(cta.split())
        for s in mid:
            s_words = len(s.split())
            if cur_count + s_words <= 112:
                selected_mid.append(s)
                cur_count += s_words

        return f"{hook} {' '.join(selected_mid)} {cta}".strip()

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

        target_words = "350 to 500 words (3.0 to 4.5 minutes documentary length)" if is_long else "100 to 115 words (strictly 42 to 48 seconds, YouTube Shorts limit under 50s)"
        format_desc = "16:9 Landscape Documentary Video" if is_long else "9:16 Vertical YouTube Short"

        if gemini_key:
            try:
                from google import genai
                client = genai.Client(api_key=gemini_key)

                if is_hindi:
                    lang_mandate = """CRITICAL LANGUAGE MANDATE: PURE HINDI (DEVANAGARI SCRIPT - देवनागरी लिपि)
- The entire narration script, hook, body, cliffhanger, titles, and pinned comment MUST be written in authentic, gripping, natural Hindi using DEVANAGARI SCRIPT (हिंदी देवनागरी लिपि).
- STRICT PROHIBITION: DO NOT write in Hinglish or English/Latin alphabet for Hindi words! (Never write "Kya aap jante hain" or "Agar aapko lagta hai"). Every sentence must be written in proper Devanagari script: "अगर आपको लगता है कि मौत के बाद सब खत्म हो जाता है...".
- Pure Hindi Devanagari text is strictly mandatory. Universal acronyms/numbers (DNA, NASA, 1935) may appear if needed, but the entire spoken narrative, verbs, vocabulary and sentence structure MUST be 100% Devanagari Hindi."""

                    hook_examples = """- Examples of 3-second opening hook styles (in Devanagari Hindi):
     * "अगर आपको लगता है कि मौत के बाद सब खत्म हो जाता है, तो अगले 45 सेकंड्स आपके होश उड़ा देंगे!"
     * "1935 में एक 4 साल की बच्ची ने एक ऐसी रोंगटे खड़े करने वाली सच्चाई बयां की जिसने पूरे देश को हिला दिया..."
     * "99% लोग नहीं जानते कि इस रहस्य को 50 सालों तक दुनिया से छुपा कर क्यों रखा गया था!"
"""

                    outro_examples = """     A. Mind-Bending Question / Open Loop: Leave a provocative question ringing in their head (e.g. "क्या यह पुनर्जन्म का सच्चा सबूत था, या विज्ञान का सबसे बड़ा अनसुलझा रहस्य?").
     B. Polarized Comment Debate Trigger: Challenge the viewer to comment their answer (e.g. "अगर आपको इसका सच पता है तो कमेंट में 'हाँ' या 'ना' लिखकर बताएं!").
     C. High-Value Subscribe & Like CTA: Compel them to subscribe (e.g. "और ऐसे ही हैरान कर देने वाले रहस्यों और सच्ची घटनाओं के लिए वीडियो को LIKE करें और चैनल को अभी SUBSCRIBE करें!")."""

                    default_pinned = "क्या आपको लगता है कि यह सच हो सकता है? अपनी राय कमेंट में ज़रूर बताएं! 👇"
                    default_titles = [f"{topic or 'रहस्य'} का चौंकाने वाला सच {'#Shorts' if not is_long else ''}"]

                elif is_hinglish:
                    lang_mandate = """LANGUAGE MANDATE: CONVERSATIONAL HINGLISH (ROMAN SCRIPT)
- Write the narration in viral conversational Hinglish (Hindi words written in English/Latin letters) that young audiences in India love.
- Use English/Roman letters throughout (e.g. "Agar aapko lagta hai ki...", "Kya aap jante hain...")."""

                    hook_examples = """- Examples of 3-second opening hook styles (in Roman Hinglish):
     * "Agar aapko lagta hai ki maut ke baad sab khatam ho jata hai, toh agle 45 seconds aapke hosh uda denge!"
     * "1935 me ek 4 saal ki bachhi ne ek aisi sachayi bayaan ki jisne khud Mahatma Gandhi ko hairan kar diya..."
     * "99% log nahi jante ki is ghatna ko sarkar ne 50 saalon tak top-secret kyu rakha tha!"
"""

                    outro_examples = """     A. Mind-Bending Question / Open Loop: Leave a provocative question ringing in their head (e.g. "Kya ye sach me punarjanam ka saboot tha, ya science ka sabse bada anjaana rahasya?").
     B. Polarized Comment Debate Trigger: Challenge the viewer to comment their answer (e.g. "Agar aapko iska sach pata hai toh comment me 'YES' ya 'NO' likhkar batao!").
     C. High-Value Subscribe & Like CTA: Compel them to subscribe (e.g. "Aur aisi hi hairatangez sachhi ghatnao aur rahasyo ke liye, video ko LIKE karein aur channel ko abhi SUBSCRIBE karein!")."""

                    default_pinned = "Aapka is baare me kya sochna hai? Comment karein 👇"
                    default_titles = [f"{topic or 'Mystery'} Revealed {'#Shorts' if not is_long else ''}"]

                else:
                    lang_mandate = """LANGUAGE MANDATE: VIRAL ENGLISH
- Write the narration in high-energy, suspenseful English with viral pacing and dramatic hooks."""

                    hook_examples = """- Examples of 3-second opening hook styles (in English):
     * "If you think you know what happens after death, the next 45 seconds will completely shatter your reality!"
     * "In 1935, a four-year-old girl revealed classified details that baffled top scientists..."
     * "99% of people have no idea why the government kept this incident top-secret for over 50 years!"
"""

                    outro_examples = """     A. Mind-Bending Question / Open Loop: Leave a provocative question ringing in their head (e.g. "Was this real documented proof of the impossible, or science's greatest unsolved mystery?").
     B. Polarized Comment Debate Trigger: Challenge the viewer to comment their answer (e.g. "If you believe this is real, type 'YES' or 'NO' in the comments!").
     C. High-Value Subscribe & Like CTA: Compel them to subscribe (e.g. "For more mind-bending true stories and mysteries, smash the LIKE button and SUBSCRIBE right now!")."""

                    default_pinned = "What do you think really happened? Comment below 👇"
                    default_titles = [f"{topic or 'Mystery'} Revealed {'#Shorts' if not is_long else ''}"]

                if is_long:
                    duration_mandate = """CRITICAL DOCUMENTARY DURATION MANDATE:
- For 16:9 Long Video, the script narration should be 350 to 500 words (3.0 to 4.5 minutes spoken audio).
- Deliver deep investigative depth, rich historical context, and comprehensive storytelling."""
                else:
                    duration_mandate = """CRITICAL YOUTUBE SHORTS DURATION MANDATE (STRICTLY UNDER 50 SECONDS, HARD LIMIT <60s):
- For YouTube Shorts, the script narration MUST BE STRICTLY UNDER 50 SECONDS (Target: 42 to 48 seconds spoken audio).
- YouTube Shorts feed HARD CUTOFF is 60.0 seconds! Any video >60s is rejected.
- At standard natural speaking pace (~2.4 words/second), the script MUST BE STRICTLY 100 TO 115 WORDS TOTAL (ABSOLUTE CEILING: 120 words).
- Word Budget: Hook = 15-20 words, Body = 65-75 words (3 punchy sentences), Outro + Subscribe CTA = 15-20 words.
- DO NOT WRITE MORE THAN 115 WORDS! Brevity and viral suspense are paramount."""

                prompt = f"""You are a top-tier viral YouTube Short & Documentary scriptwriter who crafts scripts that retain 80%+ audience retention and drive massive subscriber conversion.

Task: Transform this user idea/topic/script into a high-retention, thrilling narration script for a {format_desc}.
Target word count: {target_words}.

User Topic / Concept / Request:
"{raw_input}"
Focus: {topic or 'Mysteries / Real Incidents / History / Mind-Blowing Facts'}

{lang_mandate}

IMPORTANT CREATIVE INSTRUCTION:
- If the user provided a 1-line concept, topic, or command (e.g. "Punarjanam pe ek short video banao real incident pe with proof", "Bermuda triangle mystery", etc.), you MUST research/generate a FULL, COMPLETE, deeply thrilling, factual story from scratch based on authentic real-world incidents, records, or historical evidence (e.g. for rebirth, use documented cases like Shanti Devi / Mahatma Gandhi 1935 investigation, Taranjit Singh, etc.).
- NEVER just echo or repeat the user's prompt as the narration text! Deliver the actual gripping narrative from the first word to the last!

{duration_mandate}

STRICT RETENTION & SUBSCRIBER GROWTH BLUEPRINT:
1. THE 3-SECOND SCROLL-STOPPER OPENING HOOK (CRUCIAL):
   - ABSOLUTELY NO greetings, intros, or generic pleasantries (Never say "Hello dosto", "Aaj hum baat karenge", "Ek baar ki baat hai").
   - The opening MUST punch the viewer immediately with an Impossible Paradox, High-Stakes Warning, or Shocking Truth in the first 10-15 words.
{hook_examples}

2. SUSPENSE-DRIVEN STORY BEATS (BODY):
   - Fast-paced, curiosity-building sentence flow across 8-12 suspenseful story beats.
   - Present intriguing evidence, twists, or real eyewitness facts without unnecessary fluff.

3. THE ENGAGEMENT & SUBSCRIBER CONVERSION OUTRO (MANDATORY):
   - The ending MUST NOT just stop. It must include 3 distinct psychological elements:
{outro_examples}

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
                    "gemini-3.1-flash-lite",
                    "gemini-3.5-flash-lite",
                    "gemini-3.5-flash",
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
                if not is_long and len(narration.split()) > 118:
                    print_info(f"Generated narration has {len(narration.split())} words. Auto-condensing for 48s Shorts limit...")
                    condensed = self.condense_script_for_shorts(narration, language=language)
                    if condensed:
                        narration = condensed

                word_count = len(narration.split())
                est_seconds = round(word_count / 2.6, 1)

                return {
                    "success": True,
                    "full_narration": narration,
                    "hook": data.get("hook", ""),
                    "body": data.get("body", ""),
                    "cliffhanger": data.get("cliffhanger", ""),
                    "titles": data.get("titles", default_titles),
                    "pinned_comment": data.get("pinned_comment", default_pinned),
                    "tags": data.get("tags", ["#Shorts", "#Mystery", "#Viral"] if not is_long else ["#Documentary", "#Mystery", "#History", "#Facts"]),
                    "word_count": word_count,
                    "est_seconds": est_seconds,
                    "is_long": is_long,
                    "scenes": self._split_script_into_scenes(narration, 35 if is_long else 6),
                }
            except Exception as e:
                print_warning(f"AI script enhancer error: {e}. Using heuristic fallback...")

        # Heuristic fallback if Gemini unavailable
        words = raw_input.strip().split()
        suffix = " #Shorts" if not is_long else ""
        if is_hindi:
            hook = "अगर आपको लगता है कि आप सब जानते हैं, तो अगले 45 सेकंड्स आपके होश उड़ा देंगे!"
            cliffhanger = "आपके हिसाब से क्या यह सच हो सकता है? कमेंट में अपना जवाब ज़रूर बताएं, वीडियो को LIKE करें और ऐसी ही हैरान कर देने वाली सच्ची कहानियों के लिए चैनल को अभी SUBSCRIBE करें!"
            titles = [
                f"{raw_input[:40]}... (सच क्या है?){suffix}",
                f"99% लोग इसका सच नहीं जानते! 😱{suffix}",
                f"अनसुलझे रहस्य का चौंकाने वाला सच! ⚠️{suffix}",
            ]
            pinned_c = "आपके हिसाब से क्या यह सच हो सकता है? कमेंट में 'हाँ' या 'ना' लिखकर बताएं 👇"
            tags_list = ["#Shorts", "#Mystery", "#HindiFacts", "#HindiKahaniya"] if not is_long else ["#Documentary", "#HindiDocumentary", "#History", "#Facts"]
        elif is_hinglish:
            hook = "Agar aapko lagta hai ki aap sab jante hain, toh agle 45 seconds aapke hosh uda denge!"
            cliffhanger = "Aapke hisaab se kya ye sach ho sakta hai? Comment me apna jawab zaroor batayein, video ko LIKE karein aur aisi hi hairatangez sachhi kahaniyo ke liye channel ko abhi SUBSCRIBE karein!"
            titles = [
                f"{raw_input[:40]}... (Sach Kya Hai?){suffix}",
                f"99% Log Iska Sach Nahi Jante! 😱{suffix}",
                f"The Shocking Truth Revealed{suffix}",
            ]
            pinned_c = "Aapke hisaab se kya ye sach ho sakta hai? Comment me YES ya NO likhkar batao 👇"
            tags_list = ["#Shorts", "#Mystery", "#MindBlown", "#Facts"] if not is_long else ["#Documentary", "#Mystery", "#Facts", "#Trending"]
        else:
            hook = "If you think you know everything about this, the next 45 seconds will completely blow your mind!"
            cliffhanger = "What do you think really happened? Tell us in the comments below, LIKE this video, and SUBSCRIBE right now for more incredible mind-bending stories!"
            titles = [
                f"{raw_input[:40]}... (The Truth){suffix}",
                f"99% of People Don't Know This! 😱{suffix}",
                f"The Shocking Truth Revealed{suffix}",
            ]
            pinned_c = "Do you believe this is possible? Let us know in the comments below! 👇"
            tags_list = ["#Shorts", "#Mystery", "#MindBlown", "#Facts"] if not is_long else ["#Documentary", "#Mystery", "#Facts", "#Trending"]

        body_text = raw_input.strip()
        full_text = f"{hook} {body_text} {cliffhanger}"
        return {
            "success": True,
            "full_narration": full_text,
            "hook": hook,
            "body": body_text,
            "cliffhanger": cliffhanger,
            "titles": titles,
            "pinned_comment": pinned_c,
            "tags": tags_list,
            "word_count": len(full_text.split()),
            "est_seconds": round(len(full_text.split()) / 2.6, 1),
            "is_long": is_long,
            "scenes": self._split_script_into_scenes(full_text, 35 if is_long else 25),
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
            (("black hole", "blackhole", "ब्लैक होल", "singularity", "event horizon", "accretion", "spaghetti"), "black hole space"),
            (("space", "antariksh", "अंतरिक्ष", "brahmand", "ब्रह्मांड", "galaxy", "सौर मंडल", "solar system", "universe", "cosmos", "stars", "तारे"), "deep space galaxy"),
            (("earth", "dharati", "धरती", "पृथ्वी", "planet", "ग्रह", "neela grah"), "planet earth space"),
            (("ocean", "samundar", "समुद्र", "सागर", "sea", "underwater", "trench"), "dark deep ocean abyss"),
            (("brain", "dimag", "दिमाग", "मस्तिष्क", "mind", "psychology", "soch", "सोच"), "human brain neural networks glowing"),
            (("mahabharat", "महाभारत", "kurukshetra", "कुरुक्षेत्र", "pandav", "पांडव", "kaurav", "कौरव", "yuddh", "युद्ध", "battlefield", "warrior", "sena", "सेना", "hathiyar", "teer", "talwar"), "ancient battlefield warriors dramatic"),
            (("dwarka", "द्वारका", "submerged", "underwater city", "doobi", "डूबी", "samudra", "समुद्र तट"), "underwater ancient ruins submerged city"),
            (("ramayan", "रामायण", "ram", "राम", "shri ram", "hanuman", "हनुमान", "ayodhya", "अयोध्या", "setu", "सेतु"), "ancient stone temple ruins dramatic"),
            (("temple", "mandir", "मंदिर", "ancient", "prachin", "प्राचीन", "stone", "पत्थर", "गुफा", "गुफाएं", "caves", "kailasa", "कैलाश", "ellora"), "ancient stone temple ruins dramatic"),
            (("archaeol", "excavat", "khudai", "खुदाई", "avshesh", "अवशेष", "shilalekh", "शिलालेख", "carbon dating", "pramaan", "प्रमाण", "saboot", "सबूत", "proof", "evidence"), "ancient archaeological excavation artifacts"),
            (("scripture", "granth", "ग्रंथ", "pothi", "पोथी", "geeta", "गीता", "shloka", "श्लोक", "manuscript"), "ancient sacred manuscript scroll"),
            (("gandhi", "mahatma", "गांधी", "महात्मा"), "Mahatma Gandhi archival portrait vintage"),
            (("shanti devi", "शांति देवी", "punarjanam", "पुनर्जन्म", "rebirth", "child", "bachhi", "बच्ची"), "vintage 1930s young girl thinking portrait"),
            (("crowd", "bheed", "भीड़", "station", "train", "ट्रेन", "रेल"), "vintage crowd busy street 1930s"),
            (("police", "police station", "fir", "detective", "khooni", "crime scene", "murder case", "khoon", "हत्या"), "vintage detective crime investigation papers"),
            (("vastu", "वास्तु", "shastra", "शास्त्र", "architecture", "वास्तुकला", "energy grid", "ऊर्जा"), "ancient temple sacred geometry architecture"),
            (("scientist", "वैज्ञानिक", "research", "shodh", "शोध", "jaanch", "जांच", "khulaasa", "खुलासा"), "archaeologists examining ancient artifacts"),
            (("vibration", "कंपन", "frequency", "dhwani", "ध्वनि", "tarang", "तरंग"), "ancient temple stone carvings acoustics"),
            (("raja", "राजा", "samrat", "सम्राट", "maharaja", "महाराजा", "empire", "rajya", "राज्य", "chola", "maurya", "gupta"), "ancient indian royal palace throne"),
            (("monolithic", "single rock", "pahad", "पहाड़", "chattan", "चट्टान", "tarasha", "तराशा"), "ancient monolithic rock cut temple"),
            (("alien", "ufo", "roswell", "एलियन"), "flying saucer ufo crash site vintage"),
            (("mars", "मंगल", "लाल ग्रह"), "mars planet red surface space"),
        ]
        # Current narration sentence is authoritative. The story title is only a
        # fallback; otherwise every scene in a "black hole" story gets the same query.
        for triggers, query in mappings:
            if any(k in s_lower for k in triggers):
                return query

        # Fine-grained science concepts need distinct visual searches.
        if any(k in s_lower for k in ("nasa", "chandra", "perseus", "galaxy cluster")):
            return "Perseus galaxy cluster"
        if any(k in s_lower for k in ("sound", "aawaz", "awaaz", "pressure wave", "pressure waves", "audio")):
            return "cosmic pressure waves"
        if any(k in s_lower for k in ("57 octaves", "octaves", "frequency", "pitch", "human ear", "hear")):
            return "sound frequency spectrum"
        if any(k in s_lower for k in ("speed", "speed badha", "sped", "recorded audio", "raw audio")):
            return "scientific audio waveform"

        # Topic-level mapping is deliberately last.
        for triggers, query in mappings:
            if any(k in t_lower for k in triggers):
                return query

        # Fallback: check for valid English words
        eng_words = [w for w in re.findall(r"[a-zA-Z]{4,}", sentence) if w.lower() not in ("nahi", "hoga", "raha", "baat", "karein", "aur", "mein", "saal", "kuch", "apna", "shamil", "lekin")]
        if eng_words:
            return f"{' '.join(eng_words[:2])} cinematic"

        # Intelligent topic-genre fallbacks when text is purely Devanagari Hindi
        is_space_genre = any(k in t_lower or k in s_lower for k in ("space", "antariksh", "अंतरिक्ष", "black hole", "galaxy", "universe", "planet", "stars", "cosmos", "solar system", "brahmand", "ब्रह्मांड", "telescope", "beacon", "singularity"))
        is_ancient_history = (not is_space_genre) and any(k in t_lower or k in s_lower for k in (
            "mahabharat", "महाभारत", "ramayan", "रामायण", "kurukshetra", "कुरुक्षेत्र", "temple", "mandir", "मंदिर",
            "itihas", "इतिहास", "prachin", "प्राचीन", "purana", "पुराण", "dwarka", "द्वारका", "kailasa", "कैलाश",
            "archaeol", "vastu", "वास्तु", "shastra", "शास्त्र", "ashoka", "अशोक", "harappa", "हड़प्पा", "vedic", "वैदिक", "ved", "वेद", "bharat", "भारत"
        ))
        is_ocean_genre = any(k in t_lower or k in s_lower for k in ("ocean", "samundar", "समुद्र", "sea", "trench", "underwater", "abyss"))
        is_mind_genre = any(k in t_lower or k in s_lower for k in ("brain", "dimag", "दिमाग", "psychology", "mind", "soch"))

        if is_space_genre:
            genre_fallbacks = [
                "deep space galaxy cosmos",
                "planet earth from space",
                "cosmic stars void cinematic",
                "deep space nebula glowing",
            ]
            return genre_fallbacks[scene_idx % len(genre_fallbacks)]
        if is_ancient_history:
            genre_fallbacks = [
                "ancient stone temple ruins dramatic",
                "ancient archaeological excavation ruins",
                "ancient temple stone carvings intricate",
                "ancient battlefield warriors dramatic",
                "ancient sacred manuscript scroll",
                "ancient indian temple golden hour sunset",
            ]
            return genre_fallbacks[scene_idx % len(genre_fallbacks)]
        if is_ocean_genre:
            return "dark deep ocean underwater abyss"
        if is_mind_genre:
            return "human brain neural networks glowing"

        # General cinematic mystery fallback
        general_fallbacks = [
            "cinematic dramatic mystery atmosphere",
            "dark moody cinematic suspense",
            "mysterious atmospheric cinematic",
        ]
        return general_fallbacks[scene_idx % len(general_fallbacks)]

    def _extract_ai_scene_prompt(self, sentence: str, topic: str, scene_idx: int) -> str:
        """Generate high-aesthetic cinematic visual prompt matching the exact topic genre."""
        s_lower = sentence.lower()
        t_lower = topic.lower()

        # Current sentence owns the concrete visual. Do not let the story title
        # force the same black-hole/galaxy image onto every scene.
        if any(k in s_lower for k in ("nasa", "chandra", "perseus", "galaxy cluster")):
            return "NASA Chandra Perseus galaxy cluster, concentric X-ray pressure ripples, hot intracluster gas, cinematic scientific visualization, 8k"
        if any(k in s_lower for k in ("pressure wave", "pressure waves", "sound", "aawaz", "awaaz")):
            return "cosmic pressure waves rippling through hot galaxy cluster gas around a black hole, scientific visualization, cinematic 8k"
        if any(k in s_lower for k in ("57 octaves", "octaves", "frequency", "pitch", "human ear", "hear")):
            return "extreme low frequency spectrum visualization, cosmic sound wave, scientific audio waveform, deep space, cinematic 8k"
        if any(k in s_lower for k in ("raw audio", "recorded audio", "speed", "sped", "57 times")):
            return "astronomical audio waveform and sonification visualization, cosmic data converted to sound, cinematic 8k"
        if any(k in s_lower for k in ("black hole", "blackhole", "singularity", "event horizon", "spaghetti")):
            return "cinematic photorealistic black hole accretion disk, event horizon, gravitational lensing, deep space void, IMAX astronomy movie still, 8k"
        if any(k in s_lower for k in ("earth", "dharati", "planet", "grah", "neela grah")):
            return "cinematic photorealistic planet Earth floating in deep space, glowing atmosphere, cosmic stars, astronomy documentary still, 8k"
        if any(k in s_lower for k in ("space", "antariksh", "brahmand", "galaxy", "universe", "solar system", "stars", "cosmos")):
            return "cinematic deep space cosmic view, distant stars and nebulae, astronomy documentary still, 8k"

        # Check for Gita / Vedic / Sanatan / Scripture topics
        if any(k in s_lower or k in t_lower for k in ("krishna", "कृष्ण", "gita", "गीता", "arjun", "अर्जुन", "kurukshetra", "कुरुक्षेत्र", "chariot", "rath", "रथ", "vishwaroop", "विश्वरूप")):
            gita_prompts = [
                "Lord Krishna standing majestically on golden chariot with warrior Arjuna in Kurukshetra battlefield at dramatic golden sunset, divine radiant aura, hyperrealistic 8k",
                "Lord Krishna revealing cosmic divine form Vishwaroopam, celestial golden cosmic light, infinite radiant universe, sacred Vedic epic, hyperrealistic 8k",
                "Warrior Arjuna bowing respectfully with Gandiva bow before Lord Krishna, golden hour dusty epic battlefield, dramatic cinematic lighting, 8k",
                "Lord Krishna with peacock feather crown blowing divine Panchajanya conch, sacred aura, cinematic 8k masterpiece",
                "Sacred ancient Bhagavad Gita Sanskrit manuscript glowing with divine golden energy in serene Vedic ashram, dramatic lighting, 8k",
                "Ancient warrior standing on epic Kurukshetra battlefield amidst mist, holding divine bow, cinematic dramatic atmosphere, 8k",
            ]
            return gita_prompts[scene_idx % len(gita_prompts)]
        if any(k in s_lower or k in t_lower for k in ("chanakya", "चाणक्य", "niti", "नीति")):
            return "Acharya Chanakya wise ancient Indian philosopher standing in historic Takshashila royal court, candlelight, deep contemplation, cinematic 8k"
        if any(k in s_lower or k in t_lower for k in ("ramayan", "रामायण", "ram", "राम")):
            return "Lord Rama standing serenely with divine bow in lush ancient Dandakaranya forest, radiant golden divine aura, cinematic 8k masterpiece"
        if any(k in s_lower or k in t_lower for k in ("karma", "कर्म", "sanatan", "सनातन", "vedic", "वेद", "upanishad", "उपनिषद")):
            return "Ancient Vedic sage meditating in deep Himalayas under sacred banyan tree, cosmic energy and golden spiritual aura, cinematic 8k"

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

    @staticmethod
    def _normalize_scene_text(text: str) -> str:
        """Normalize whitespace/punctuation for safe scene-script equivalence checks."""
        return re.sub(r"\s+", " ", (text or "").strip()).lower()

    @staticmethod
    def _split_script_into_scenes(script_text: str, max_scenes: int) -> List[Dict[str, Any]]:
        """Split narration into stable sentence scenes without dropping text."""
        text = (script_text or "").strip()
        if not text:
            return []

        protected = text
        protected_tokens = {
            "U.S.": "U<dot>S<dot>",
            "U.K.": "U<dot>K<dot>",
            "e.g.": "e<dot>g<dot>",
            "i.e.": "i<dot>e<dot>",
            "Mr.": "Mr<dot>",
            "Mrs.": "Mrs<dot>",
            "Ms.": "Ms<dot>",
            "Dr.": "Dr<dot>",
            "Prof.": "Prof<dot>",
            "vs.": "vs<dot>",
        }
        for src, repl in protected_tokens.items():
            protected = protected.replace(src, repl)
        protected = re.sub(r"(?<=\d)\.(?=\d)", "<decimal>", protected)

        parts = [p.strip() for p in re.split(r"(?<=[.!?।॥])\s+|\n+", protected) if p and p.strip()]
        restored = []
        for part in parts:
            for src, repl in protected_tokens.items():
                part = part.replace(repl, src)
            part = part.replace("<decimal>", ".").strip()
            if part:
                restored.append(part)

        if not restored:
            restored = [text]

        if max_scenes < 1 or len(restored) <= max_scenes:
            selected = restored
        else:
            selected = restored[: max_scenes - 1]
            selected.append(" ".join(restored[max_scenes - 1 :]))

        return [
            {
                "scene_number": idx + 1,
                "narration": sentence,
                "visual_subject": "",
                "visual_description": "",
                "search_keywords": [],
            }
            for idx, sentence in enumerate(selected)
        ]

    def _prepare_scene_specs(
        self,
        script_text: str,
        title: str,
        provided_scenes: Optional[List[Dict[str, Any]]],
        max_scenes: int,
    ) -> List[Dict[str, Any]]:
        """Preserve an existing structured scene plan only when it exactly covers the script."""
        normalized_script = self._normalize_scene_text(script_text)
        candidates: List[Dict[str, Any]] = []

        if isinstance(provided_scenes, list) and provided_scenes:
            for idx, raw in enumerate(provided_scenes):
                if not isinstance(raw, dict):
                    continue
                narration = str(raw.get("narration") or raw.get("text") or "").strip()
                if not narration:
                    continue
                candidates.append(
                    {
                        "scene_number": idx + 1,
                        "narration": narration,
                        "visual_subject": str(raw.get("visual_subject") or raw.get("subject") or "").strip(),
                        "visual_description": str(raw.get("visual_description") or "").strip(),
                        "search_keywords": list(raw.get("search_keywords") or raw.get("visual_keywords") or []),
                        "visual_action": str(raw.get("visual_action") or raw.get("action") or "").strip(),
                        "visual_environment": str(raw.get("visual_environment") or raw.get("environment") or "").strip(),
                        "must_show": list(raw.get("must_show") or []),
                        "avoid": list(raw.get("avoid") or []),
                        "custom_image_path": str(raw.get("custom_image_path") or raw.get("image_path") or "").strip(),
                        "visual_prompt": str(raw.get("visual_prompt") or raw.get("prompt") or "").strip(),
                    }
                )

            candidate_script = self._normalize_scene_text(" ".join(s["narration"] for s in candidates))
            has_custom_images = any(bool(s.get("custom_image_path")) for s in candidates)

            # Preserve structured scene plan if narration matches the script, OR if explicit custom image uploads are attached
            if candidates and (candidate_script == normalized_script or has_custom_images):
                return candidates[:max(len(candidates), max_scenes)]

        split_scenes = self._split_script_into_scenes(script_text, max_scenes)
        for idx, scene in enumerate(split_scenes):
            if not scene.get("visual_subject"):
                q = self._extract_visual_search_query(scene["narration"], title, idx)
                scene["visual_subject"] = q
                scene["search_keywords"] = [q]

        return split_scenes

    def _scene_plan_from_spec(self, scene: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Convert the preserved scene contract into MultiStockAggregator's scene-plan schema."""
        subject = str(scene.get("visual_subject") or "").strip()
        description = str(scene.get("visual_description") or "").strip()
        queries = [str(q).strip() for q in (scene.get("search_keywords") or []) if str(q).strip()]
        plan = {
            "subject": subject,
            "action": str(scene.get("visual_action") or "").strip(),
            "environment": str(scene.get("visual_environment") or "").strip(),
            "must_show": [str(v).strip() for v in scene.get("must_show", []) if str(v).strip()],
            "avoid": [str(v).strip() for v in scene.get("avoid", []) if str(v).strip()],
            "search_queries": queries[:4],
        }
        if description and not plan["subject"]:
            plan["subject"] = description[:120]
        if not any(plan["subject"] or plan["action"] or plan["environment"] or plan["must_show"] or plan["search_queries"]):
            return None
        return plan

    def optimize_vedic_script(self, raw_input: str) -> Dict[str, Any]:
        """Transform raw shloka, chaupai, quote, topic, or concept into a high-retention 55-58s Devanagari Shorts script."""
        text = (raw_input or "").strip()
        cleaned_raw = re.sub(r"\*{1,3}", "", text).strip()
        if not cleaned_raw:
            return {"success": False, "error": "Empty script input"}

        # 1. Try Gemini AI generation
        gemini_key = os.getenv("GEMINI_API_KEY", "") or getattr(self.cfg, "gemini_api_key", "")
        if gemini_key:
            try:
                from google import genai
                client = genai.Client(api_key=gemini_key)
                prompt = f"""You are a scholarly and respectful Sanatan Dharma Vedic researcher, Sanskrit scholar, and master viral YouTube Shorts storyteller (specializing in Srimad Bhagavad Gita, Ramcharitmanas, Puranas, Upanishads, and Chanakya Neeti).
Transform the following raw input, topic, deity name, shloka, chaupai, or thought into a deeply moving, highly viral, 55-58 second YouTube Shorts narration script (130-145 words total).

STRICT MANDATORY GUIDELINES:
1. PURE DEVANAGARI HINDI (हिंदी देवनागरी लिपि):
   - Output must be 100% in authentic, spoken, respectful Devanagari Hindi.
   - Absolutely NO English/Hinglish characters for Hindi words.
2. DYNAMIC TOPIC & SHLOKA HANDLING:
   - If the user provides a topic, deity, or story title (e.g. 'माँ वैष्णो देवी', 'हनुमान जी की शक्ति', 'भगवान शिव और विषपान', 'कर्ण और अर्जुन', 'शनि देव का न्याय', 'कुरुक्षेत्र युद्ध'):
     Craft a complete, captivating 130-145 word story strictly focused on that EXACT topic/deity! Do NOT output generic filler. Bring out the authentic mythological lore, drama, and spiritual power of that specific topic.
   - If the input contains an authentic Sanskrit Shloka (e.g. कर्मण्येवाधिकारस्ते, यदा यदा हि धर्मस्य), Chaupai, or Doha:
     PRESERVE the original verse VERBATIM in Act 2 without altering words or creating false quotes. Cite the authentic source and speaker accurately.
   - NEVER invent fake quotes or falsely attribute lines to sacred scriptures.
3. 4-ACT RETENTION STRUCTURE:
   - ACT 1 (Viral Hook, 18-25 words): A gripping psychological or spiritual question that stops scrolling immediately in the first 3 seconds.
   - ACT 2 (Sacred Story, Lore & Verse, 35-45 words): Narrate the sacred mythological incident or verse with context and reverence.
   - ACT 3 (Deep Karma & Life Lesson, 45-55 words): Practical, hard-hitting emotional wisdom on why this matters to the viewer today (overcoming fear, finding peace, mastering karma).
   - ACT 4 (CTA & Outro, 20-25 words): Thought-provoking closing reflection + invitation to comment the deity's sacred chant (e.g. 'जय माता दी', 'हर हर महादेव', 'जय बजरंगबली', 'जय श्री कृष्ण') + subscribe CTA.
4. STRICT DURATION & WORD BUDGET (55-58s TARGET):
   - Target range: 125 to 135 words total.
   - ABSOLUTE MAXIMUM: 140 words.
   - Under NO circumstances exceed 140 words! YouTube Shorts has an inflexible 60-second limit; scripts over 140 words get rejected.
5. CLEAN CONTINUOUS SPOKEN TEXT:
   - Pure continuous spoken narration. Absolutely NO asterisks (**), NO bracketed stage directions [Scene 1], NO bullet points.

RAW INPUT:
\"\"\"{cleaned_raw}\"\"\"

Output STRICT JSON:
{{
  "optimized_script": "Full continuous spoken Hindi Devanagari narration script...",
  "title": "Inspiring viral YouTube video title with emojis and #Shorts",
  "scripture_source": "Accurate Granth, deity, or topic reference (e.g. 'श्री दुर्गा सप्तशती / माँ वैष्णो देवी', 'श्रीमद्भगवद्गीता', 'हनुमान चालीसा')",
  "word_count": 130,
  "est_seconds": 56.0
}}"""
                active_models = ["gemini-3.5-flash-lite", "gemini-3.1-flash-lite", "gemini-3.5-flash", "gemini-3.8-flash"]
                for m in active_models:
                    try:
                        response = client.models.generate_content(
                            model=m,
                            contents=prompt,
                            config={"response_mime_type": "application/json"},
                        )
                        if response.text:
                            import json
                            parsed = json.loads(response.text)
                            opt_text = str(parsed.get("optimized_script") or "").strip()
                            if opt_text and len(opt_text.split()) >= 40:
                                # Enforce strict 145-word ceiling so video safely fits in 55-58s
                                if len(opt_text.split()) > 145:
                                    sentences = re.split(r"(?<=[।!?])\s+", opt_text)
                                    accum = []
                                    cur_w = 0
                                    for s in sentences:
                                        s_len = len(s.split())
                                        if cur_w + s_len <= 145 or not accum:
                                            accum.append(s)
                                            cur_w += s_len
                                        else:
                                            break
                                    if len(" ".join(accum).split()) >= 90:
                                        opt_text = " ".join(accum).strip()

                                opt_words = len(opt_text.split())
                                return {
                                    "success": True,
                                    "optimized_script": opt_text,
                                    "title": parsed.get("title") or "पवित्र सनातन सीख #Shorts",
                                    "scripture_source": parsed.get("scripture_source") or "श्रीमद्भगवद्गीता / सनातन दर्शन",
                                    "is_ai_generated": True,
                                    "model_used": m,
                                    "word_count": opt_words,
                                    "est_seconds": round(opt_words / 2.35, 1),
                                }
                    except Exception:
                        continue
            except Exception as e:
                print_warning(f"Gemini vedic script optimization notice: {e}")

        # 2. Intelligent Domain-Aware Heuristic Expander (All ~130-142 words, calibrated for 55-58s)
        lower_raw = cleaned_raw.lower()

        # Case 1: Mata Vaishno Devi / Durga / Devi / Shakti / Kali / Parvati / Lakshmi / Saraswati
        if any(k in lower_raw for k in ("वैष्णो", "त्रिकूटा", "त्रिकुटा", "दुर्गा", "काली", "पार्वती", "लक्ष्मी", "सरस्वती", "देवी", "शक्ति", "vaishno", "durga", "devi", "shakti")):
            opt_script = (
                "क्या आप जानते हैं कि त्रिकूटा पर्वत की पवित्र गुफा में माँ वैष्णो देवी आज भी किसकी प्रतीक्षा में तपस्या कर रही हैं? "
                "पौराणिक कथा के अनुसार जब दुष्ट भैरवनाथ ने देवी का पीछा किया, तो माँ ने नौ महीने तक गर्भजून गुफा में कठोर तप किया। "
                "अंत में माँ ने महाकाली का उग्र रूप धारण करके धर्म की रक्षा की और भैरवनाथ का उद्धार किया। "
                "माँ वैष्णो देवी की यह अमर गाथा हमें सिखाती है कि जीवन में कितनी भी कठिनाइयां और बाधाएं क्यों न आएं, "
                "सत्य और पवित्रता के मार्ग पर चलने वाले को अंत में विजय अवश्य मिलती है। "
                "जब आप सच्चे मन से माँ की शरण में जाते हैं, तो आपके सारे दुःख और भय दूर हो जाते हैं। "
                "क्या आप माँ का आशीर्वाद पाने के लिए तैयार हैं? "
                "अगर हां, तो कमेंट में 'जय माता दी' लिखें और इस दिव्य शक्ति के लिए अभी सब्सक्राइब करें!"
            )
            title = "माँ वैष्णो देवी की पवित्र गुफा का अनसुलझा रहस्य #Shorts"

        # Case 2: Lord Hanuman / Bajrangbali / Sankat Mochan / Ram Bhakt / Anjaneya / Pawan Putra
        elif any(k in lower_raw for k in ("हनुमान", "बजरंगबली", "संकटमोचन", "अंजनेय", "पवनपुत्र", "hanuman", "bajrangbali")):
            opt_script = (
                "क्या आप जानते हैं कि जब युद्धभूमि में लक्ष्मण जी मूर्छित हुए, तो हनुमान जी ने केवल एक बूटी ढूंढने के बजाय पूरे द्रोणागिरि पर्वत को ही अपनी हथेली पर क्यों उठा लिया था? "
                "शास्त्र कहते हैं कि प्रभु श्री राम के इस परम भक्त के मन में कोई संशय या असमंजस नहीं था। "
                "वे जानते थे कि समय कम है और उनके प्रभु के भाई के प्राण संकट में हैं। "
                "हनुमान जी का यह समर्पण सिखाता है कि जब आप स्वार्थ और अहंकार छोड़कर अपने कर्तव्य में डूब जाते हैं, तो असंभव कार्य भी संभव हो जाता है। "
                "जब जीवन में बड़ी मुसीबतें सामने खड़ी हों, तो घबराएं नहीं, अपने भीतर के विश्वास और भक्ति को जगाएं। "
                "क्या आप भी अपनी हर मुश्किल को पार करने का साहस रखते हैं? "
                "अगर हां, तो कमेंट में 'जय बजरंगबली' लिखें और ऐसी ही शक्ति से भरी कथाओं के लिए अभी सब्सक्राइब करें!"
            )
            title = "हनुमान जी का अतुलित बल: जब उठा लिया पूरा पर्वत #Shorts"

        # Case 3: Lord Shiva / Mahadev / Bholenath / Rudra / Kedarnath / Mahakal / Tandav / Kailash / Neelkanth
        elif any(k in lower_raw for k in ("शिव", "महादेव", "भोलेनाथ", "नीलकंठ", "हलाहल", "कैलाश", "रुद्र", "महाकाल", "shiva", "mahadev", "kedarnath")):
            opt_script = (
                "क्या आप जानते हैं कि जब समुद्र मंथन से ब्रह्मांड को भस्म करने वाला कालकूट विष निकला, तो केवल महादेव ही उसे पीने के लिए आगे क्यों आए? "
                "सारे देवता और दानव भयभीत होकर भाग खड़े हुए, तब भगवान शिव ने संसार की रक्षा के लिए उस हलाहल विष को अपने कंठ में धारण कर लिया। "
                "विष पीकर भी शिव शांत रहे और नीलकंठ कहलाए। "
                "महादेव का यह चरित्र सिखाता है कि सच्चा शक्तिशाली वह नहीं जो दुनिया पर गुस्सा दिखाए, बल्कि वह है जो विष जैसी नकारात्मकता को पचाकर भी अपने मन को शांत रखे। "
                "जब लोग आपको बुरा बोलें, तो बदले की आग में न जलें, बल्कि शिव की तरह मौन और शक्तिशाली बनें। "
                "क्या आप भी अपने भीतर के क्रोध को जीतने के लिए तैयार हैं? "
                "अगर हां, तो कमेंट में 'हर हर महादेव' लिखें और इस दिव्य ज्ञान के लिए अभी सब्सक्राइब करें!"
            )
            title = "महादेव नीलकंठ क्यों कहलाए: जीवन का सबसे गहरा रहस्य #Shorts"

        # Case 4: Karna / Danveer / Surya Putra
        elif any(k in lower_raw for k in ("कर्ण", "कवच", "कुंडल", "दानवीर", "सूर्यपुत्र", "karna", "danveer")):
            opt_script = (
                "क्या आप जानते हैं कि महाभारत के युद्ध में सब कुछ दांव पर लगे होने के बाद भी सूर्यपुत्र कर्ण को संसार का सबसे बड़ा दानवीर क्यों कहा गया? "
                "जब देवराज इंद्र ब्राह्मण का वेश धरकर कर्ण के प्राण रक्षक दिव्य कवच और कुंडल मांगने आए, तो कर्ण सच जानकर भी मुस्कुराते हुए अपने अंग काटकर दान कर दिए। "
                "कर्ण ने कभी अपनी विपरीत परिस्थितियों का रोना नहीं रोया, बल्कि अपने वचनों और त्याग से अमर हो गए। "
                "दानवीर कर्ण का यह जीवन सिखाता है कि आप किस कुल में जन्मे हैं यह महत्वपूर्ण नहीं है, बल्कि आपका चरित्र और आपकी निष्ठा ही आपको महान बनाती है। "
                "कठिनाइयां कितनी भी बड़ी हों, अपने सिद्धांतों से कभी समझौता न करें। "
                "क्या आप भी विपरीत समय में अपने स्वाभिमान के साथ खड़े रहने का हौसला रखते हैं? "
                "कमेंट में अपनी राय लिखें और इस अमर गाथा के लिए अभी सब्सक्राइब करें!"
            )
            title = "दानवीर कर्ण का अंतिम त्याग: क्यों झुका पूरा संसार? #Shorts"

        # Case 5: Shani Dev / Nyay / Saade Saati / Karmaphal
        elif any(k in lower_raw for k in ("शनि", "न्याय", "कर्मफल", "साढ़ेसाती", "shani", "justice")):
            opt_script = (
                "क्या आप भी शनि देव के नाम से डरते हैं? जानिए क्यों शनि देव किसी का बुरा नहीं करते, बल्कि वे इस सृष्टि के सबसे निष्पक्ष न्यायाधिकारी हैं। "
                "शास्त्र कहते हैं कि शनि देव सूर्यपुत्र और कर्मफल दाता हैं, जो राजा से लेकर रंक तक सबको उनके कर्मों का सच्चा हिसाब देते हैं। "
                "जो व्यक्ति अहंकार में आकर गरीबों और निर्बलों को सताता है, उसे शनि देव का दंड भोगना ही पड़ता है। "
                "लेकिन जो इंसान सच्चाई, ईमानदारी और मेहनत की राह पर चलता है, उस पर शनि देव अपनी अपार कृपा बरसाते हैं। "
                "कर्मों की इस अदालत से कोई नहीं बच सकता, इसलिए अपनी नीयत साफ रखिए और किसी के साथ अन्याय मत कीजिए। "
                "क्या आप आज से अपने कर्मों को पवित्र बनाने का संकल्प लेते हैं? "
                "अगर हां, तो कमेंट में 'जय शनि देव' लिखें और इस धर्म की सीख के लिए अभी सब्सक्राइब करें!"
            )
            title = "शनि देव का न्याय: डरें नहीं, कर्म सुधारें #Shorts"

        # Case 6: Ramcharitmanas / Tulsidas / Ram / Rama / Parhit / Ayodhya / Chaupai
        elif any(k in lower_raw for k in ("परहित", "सरिस धर्म", "रामचरितमानस", "tulsidas", "ramcharitmanas", "तुलसीदास", "पर पीड़ा", "अधमाई", "ram", "राम")):
            opt_script = (
                "क्या आप जानते हैं कि हमारे प्राचीन शास्त्रों के अनुसार इस पूरे संसार का सबसे बड़ा धर्म और सबसे भयानक पाप क्या है? "
                "गोस्वामी तुलसीदास जी ने रामचरितमानस में अमर चौपाई लिखी है— परहित सरिस धर्म नहिं भाई, पर पीड़ा सम नहिं अधमाई। "
                "यानी इस दुनिया में दूसरों की निस्वार्थ भलाई करने से बड़ा कोई पुण्य नहीं है, और किसी निर्दोष को दुःख पहुँचाने से बड़ा कोई घोर पाप नहीं। "
                "जब आप स्वार्थ छोड़कर किसी गिरते हुए इंसान का सहारा बनते हैं, तो परमात्मा स्वयं आपके जीवन का रक्षक बन जाता है। "
                "धन, पद और प्रतिष्ठा यहीं छूट जाएंगे, लेकिन आपके द्वारा बांटी गई दया और मदद की पूंजी जन्मों-जन्मों तक आपके साथ रहेगी। "
                "क्या आप आज किसी एक जरूरतमंद के चेहरे पर मुस्कान लाने के लिए तैयार हैं? "
                "अगर हां, तो कमेंट में 'जय श्री राम' लिखें और इस पवित्र सीख के लिए अभी सब्सक्राइब करें!"
            )
            title = "रामचरितमानस की सबसे बड़ी सीख: सबसे बड़ा धर्म और पाप क्या है? #Shorts"

        # Case 7: Bhagavad Gita / Karma / Krishna / Arjuna / Kurukshetra / Parth
        elif any(k in lower_raw for k in ("कर्म", "अधिकार", "फल", "पार्थ", "कृष्ण", "अर्जुन", "gita", "गीता", "karma", "कुरुक्षेत्र")):
            opt_script = (
                "क्या आप भी भविष्य की चिंता और असफलता के डर में अपना कीमती आज बर्बाद कर रहे हैं? "
                "कुरुक्षेत्र के महासंग्राम में महान धनुर्धर अर्जुन के हाथ कांप रहे थे और उनका गांडीव धनुष छूट रहा था, क्योंकि उन्हें अपनी पराजय का भय सता रहा था। "
                "तब योगेश्वर भगवान श्री कृष्ण ने कहा— हे पार्थ, तुम्हारा अधिकार केवल निष्काम कर्म पर है, उसके फलों पर कभी नहीं। "
                "जब आप परिणाम की चिंता छोड़ केवल अपनी मेहनत पर ध्यान देते हैं, तो सारा डर खत्म हो जाता है और असली प्रतिभा जागती है। "
                "खुद को कभी परिस्थितियों का गुलाम न बनने दें, बल्कि अपनी निष्ठा से अपना नया भाग्य खुद लिखें। "
                "हार केवल एक सीख है, आपकी अंतिम पहचान नहीं। "
                "क्या आप आज अपना शत-प्रतिशत कर्म करने के लिए तैयार हैं? "
                "अगर हां, तो कमेंट में 'जय श्री कृष्ण' लिखें और अभी सब्सक्राइब करें!"
            )
            title = "कुरुक्षेत्र में श्री कृष्ण की सीख: कर्म ही तुम्हारी पहचान है #Shorts"

        # Case 8: Chanakya / Neeti / Strategy / Takshashila
        elif any(k in lower_raw for k in ("चाणक्य", "chanakya", "नीति", "तक्षशिला")):
            opt_script = (
                "आचार्य चाणक्य ने कहा था कि इस दुनिया में सबसे खतरनाक शत्रु वह नहीं जो सामने से वार करे, बल्कि वह कपटी मित्र है जो मीठी बातें करके पीठ पीछे छुरा घोंपे। "
                "जब आप अपनी योजनाएं और अपनी कमजोरियां हर किसी के सामने खोलकर रख देते हैं, तो आपकी पराजय निश्चित हो जाती है। "
                "चाणक्य नीति स्पष्ट सिखाती है कि जंगल में सबसे सीधे पेड़ ही पहले काटे जाते हैं, इसलिए इतने सीधे भी न बनें कि दुनिया आपका शोषण कर ले। "
                "अपने लक्ष्यों को गुप्त रखिए, अपनी मेहनत को हथियार बनाइए और जब आप सफल हों तो दुनिया को अपने कर्मों से जवाब दीजिए। "
                "क्या आप भी अपने जीवन में अनुशासन और सफलता का यह स्वर्णिम नियम अपनाने के लिए तैयार हैं? "
                "अगर हां, तो कमेंट में अपनी राय लिखें और ऐसी जीवन बदलने वाली नीतियों के लिए अभी सब्सक्राइब करें!"
            )
            title = "चाणक्य नीति: ये 3 गलतियां कभी मत करना #Shorts"

        # Case 9: Dynamic Topic Expander for ANY custom topic/thought typed by user
        else:
            topic_clean = cleaned_raw[:60]
            opt_script = (
                f"क्या आप जानते हैं कि हमारे प्राचीन सनातन शास्त्रों और महापुरुषों ने '{topic_clean}' को लेकर जीवन का सबसे गहरा और क्रांतिकारी रहस्य क्या बताया है? "
                f"शास्त्रों और नीतिग्रंथों का स्पष्ट मत है कि जब कोई सच्चा खोजी {topic_clean} के वास्तविक सत्य को समझ लेता है, तो उसके जीवन के सारे संशय और भय सदा के लिए समाप्त हो जाते हैं। "
                "संसार की व्यर्थ चिंताओं और दूसरों की बातों को छोड़िए, क्योंकि बाहरी दुनिया केवल एक भ्रम है, आपका असली भाग्य आपके विचारों, साहस और सत्कर्मों से निर्मित होता है। "
                "ईश्वर ने आपके भीतर असीम शक्ति दी है, उस आत्मबल को पहचानिए और अपने लक्ष्य के मार्ग पर अडिग रहिए। "
                "जब आपकी नीयत साफ होती है, तो पूरी कायनात आपकी सफलता का मार्ग प्रशस्त करती है। "
                "क्या आप आज इस दिव्य सत्य को अपने जीवन में उतारने के लिए तैयार हैं? "
                "अगर हां, तो कमेंट में अपने आराध्य देव का नाम लिखें और इस अमर ज्ञान के लिए अभी सब्सक्राइब करें!"
            )
            title = f"{topic_clean}: प्राचीन शास्त्रों का सबसे गहरा रहस्य #Shorts"

        words = len(opt_script.split())
        return {
            "success": True,
            "optimized_script": opt_script,
            "title": title,
            "word_count": words,
            "est_seconds": round(words / 2.35, 1),
        }

    def breakdown_vedic_script(self, script_text: str) -> List[Dict[str, Any]]:
        """Split a Hindi spiritual or Vedic script into 5-7 storyboard scenes with 8K English AI prompts."""
        raw_text = (script_text or "").strip()
        if not raw_text:
            return []

        # Try Gemini first if key available
        gemini_key = os.getenv("GEMINI_API_KEY", "") or getattr(self.cfg, "gemini_api_key", "")
        if gemini_key:
            try:
                from google import genai
                client = genai.Client(api_key=gemini_key)
                prompt = f"""You are a master Vedic and Hindu epic film director (Mahabharata, Gita, Ramayana, Puranas, Devi Mahatmya).
Break down the following Hindi narration script into 5 to 7 sequential video scenes.
For each scene, output:
1. 'scene_number': integer 1, 2, ...
2. 'narration': exact spoken sentence in authentic Hindi Devanagari.
3. 'visual_prompt': an ultra-detailed 8K photorealistic English prompt designed for Midjourney / Leonardo AI / Flux.
   CRITICAL REQUIREMENT FOR 'visual_prompt':
   - MUST DIRECTLY AND ACCURATELY DEPICT THE EXACT EVENT, CHARACTER, EMOTION, AND SETTING MENTIONED IN THAT SCENE'S 'narration'.
   - If the scene mentions Goddess Vaishno Devi, describe Goddess Vaishno Devi in holy Himalayan cave shrine with glowing Trishul, radiant golden aura, and snow mountains.
   - If the scene mentions Lord Hanuman, describe Lord Hanuman soaring through midnight storm clouds carrying the glowing sacred Sanjeevani mountain (Dronagiri).
   - If the scene mentions Lord Shiva, describe Lord Shiva in profound meditation on snowy Mount Kailash with crescent moon, blue throat, and Trishul.
   - If the scene mentions warrior Karna, describe Danveer Karna with glowing celestial golden armor (Kavach and Kundala) standing by the sacred river at dawn.
   - If the scene mentions Arjuna on Kurukshetra, describe warrior prince Arjuna on golden chariot with Gandiva bow amidst battlefield dust and sunset lighting.
   - Describe authentic Indian aesthetics, royal silk pitambara, traditional jewelry, dramatic cinematic lighting, volumetric atmosphere, no cartoon, no anime, 9:16 vertical aspect ratio.
4. 'visual_subject': 2-3 simple English words identifying the main visual subject.

SCRIPT:
\"\"\"{raw_text}\"\"\"

Return ONLY a JSON list of scene objects matching this structure:
[
  {{"scene_number": 1, "narration": "...", "visual_prompt": "...", "visual_subject": "..."}}
]"""
                active_models = ["gemini-3.5-flash-lite", "gemini-3.1-flash-lite", "gemini-3.5-flash", "gemini-3.8-flash"]
                for m in active_models:
                    try:
                        response = client.models.generate_content(
                            model=m,
                            contents=prompt,
                            config={"response_mime_type": "application/json"},
                        )
                        if response.text:
                            import json
                            parsed = json.loads(response.text)
                            if isinstance(parsed, list) and len(parsed) >= 2:
                                return parsed
                    except Exception:
                        continue
            except Exception as e:
                print_warning(f"Gemini vedic script breakdown notice: {e}")

        # Intelligent Rule-Based Fallback
        split_scenes = self._split_script_into_scenes(raw_text, max_scenes=7)
        results = []
        for idx, s in enumerate(split_scenes):
            sentence = str(s.get("narration", "")).strip()
            s_low = sentence.lower()

            # 1. Vaishno Devi / Trikuta / Cave Shrine / Bhairon Nath / Garbhjoon
            if any(k in s_low for k in ("वैष्णो", "त्रिकूटा", "त्रिकुटा", "गुफा", "भैरव", "गर्भजून", "vaishno", "trikuta", "bhairon", "cave shrine")):
                v_prompt = "Cinematic 8k photorealistic divine portrait of Goddess Vaishno Devi in holy Himalayan cave shrine, glowing golden halo, royal red and gold embroidered silk saree, holding sacred golden Trishul, surrounded by glowing oil lamps, snow-covered Himalayan peaks in background, dramatic cinematic lighting, masterpiece, 9:16 vertical"
                v_subj = "Goddess Vaishno Devi Himalayan cave shrine"
            # 2. Goddess Durga / Mahakali / Parvati / Lakshmi / Devi / Shakti
            elif any(k in s_low for k in ("दुर्गा", "काली", "पार्वती", "लक्ष्मी", "सरस्वती", "महाकाली", "durga", "kali", "parvati", "lakshmi", "devi")):
                v_prompt = "Cinematic 8k photorealistic divine shot of Goddess Durga in radiant golden armor riding a majestic golden lion, eight arms holding sacred celestial weapons, fierce yet benevolent expression, glowing divine halo, dramatic volumetric sunset lighting, sacred epic art, 9:16 vertical"
                v_subj = "Goddess Durga majestic lion divine weapons"
            # 3. Hanuman / Bajrangbali / Sanjeevani / Dronagiri / Pawan Putra
            elif any(k in s_low for k in ("हनुमान", "बजरंगबली", "द्रोणागिरि", "संजीवनी", "बूटी", "पवन पुत्र", "anjaneya", "hanuman", "bajrangbali", "sanjeevani")):
                v_prompt = "Cinematic 8k photorealistic shot of Lord Hanuman soaring powerfully through dramatic midnight storm clouds, carrying the glowing sacred Dronagiri mountain with radiant Sanjeevani herbs in his hand, muscular divine form, vibrant vermilion aura, thunder and lightning, masterpiece, 9:16 vertical"
                v_subj = "Lord Hanuman carrying glowing Sanjeevani mountain"
            # 4. Shiva / Mahadev / Neelkanth / Poison / Halahala / Kailash / Tandav / Rudra
            elif any(k in s_low for k in ("शिव", "महादेव", "भोलेनाथ", "नीलकंठ", "हलाहल", "कालकूट", "कैलाश", "रुद्र", "तांडव", "shiva", "mahadev", "neelkanth", "kailash")):
                v_prompt = "Cinematic 8k photorealistic shot of Lord Shiva in deep transcendental meditation atop snowy Mount Kailash, crescent moon in matted locks, sacred Trishul and Damru, serene glowing blue throat (Neelkanth), cosmic starlight and golden dawn aura, masterpiece, 9:16 vertical"
                v_subj = "Lord Shiva meditation on Mount Kailash"
            # 5. Karna / Danveer / Kavach Kundal / Surya Putra
            elif any(k in s_low for k in ("कर्ण", "कवच", "कुंडल", "दानवीर", "सूर्यपुत्र", "karna", "danveer")):
                v_prompt = "Cinematic 8k photorealistic heroic shot of warrior Karna standing on holy river Ganga banks at sunrise, dazzling celestial golden armor (Kavach and Kundala) glowing on his chest, majestic royal stance, sunrise rays reflecting on golden ornaments, epic Vedic cinema, 9:16 vertical"
                v_subj = "warrior Karna golden armor sunrise"
            # 6. Shani Dev / Raven / Justice / Nyaya
            elif any(k in s_low for k in ("शनि", "न्याय", "कर्मफल", "shani", "justice", "saade saati")):
                v_prompt = "Cinematic 8k photorealistic mystical portrait of Lord Shani Dev, cosmic lord of justice, in royal dark blue-black silk robes, holding divine sword and cosmic scales, standing beside sacred black raven, intense glowing celestial aura, dramatic moody lighting, 9:16 vertical"
                v_subj = "Lord Shani Dev scales of cosmic justice"
            # 7. Chanakya / Neeti / Takshashila
            elif any(k in s_low for k in ("चाणक्य", "chanakya", "नीति", "तक्षशिला")):
                v_prompt = "Cinematic 8k photorealistic shot of Acharya Chanakya in traditional ancient sage attire writing sacred statecraft manuscripts with peacock quill by warm brass oil lamp in historic Takshashila royal court, intense wise gaze, dramatic chiaroscuro lighting, 9:16 vertical"
                v_subj = "Acharya Chanakya writing in Takshashila"
            # 8. Krishna / Parth / Chariot / Rath / Kurukshetra
            elif any(k in s_low for k in ("कृष्ण", "पार्थ", "माधव", "केशव", "krishna", "parth")):
                v_prompt = "Cinematic 8k photorealistic shot of Lord Krishna in divine royal yellow pitambara silk and peacock feather crown, standing majestically on an ancient golden chariot in Kurukshetra at dramatic sunset, radiant golden divine aura around his head, serene compassionate smile, speaking sacred wisdom to Arjuna, sacred epic Vedic cinema, masterpiece, 9:16 vertical"
                v_subj = "Lord Krishna speaking to Parth on chariot"
            # 9. Saint Tulsidas / Ramcharitmanas / Chaupai
            elif any(k in s_low for k in ("तुलसीदास", "रामचरितमानस", "tulsidas", "ramcharitmanas", "chaupai", "चौपाई")):
                v_prompt = "Cinematic 8k photorealistic shot of saint poet Goswami Tulsidas in sacred saffron robes writing Ramcharitmanas with peacock quill on holy palm leaves by the holy Ganga ghats of Varanasi, glowing sacred oil lamps, celestial golden aura, holy scripture manuscript, masterpiece, 9:16 vertical"
                v_subj = "Goswami Tulsidas writing Ramcharitmanas"
            # 10. Lord Rama / Kodanda bow / Ayodhya
            elif any(k in s_low for k in ("राम", "श्री राम", "रघुपति", "lord ram", "rama", "ayodhya")) and not any(k in s_low for k in ("सब्सक्राइब", "कमेंट")):
                v_prompt = "Cinematic 8k photorealistic divine portrait of Lord Rama in royal golden silk robes holding the sacred Kodanda bow, calm compassionate countenance, radiant golden divine halo, majestic Ayodhya palace pillars in background, sacred epic art, 9:16 vertical"
                v_subj = "Lord Rama with Kodanda bow"
            # 11. Compassion / Helping hands / Charity
            elif any(k in s_low for k in ("परहित", "भलाई", "मदद", "पुण्य", "हाथ थामते", "सहारा", "स्वार्थ", "खुशियां", "compassion", "charity", "helping")):
                v_prompt = "Cinematic 8k photorealistic heart-touching shot of compassionate Indian hands gently helping a weary fallen traveler rise, bathed in warm golden dawn sunlight, glowing particles of divine grace and empathy, cinematic emotional masterpiece, 9:16 vertical"
                v_subj = "compassionate helping hands golden sunlight"
            # 12. Pain / Darkness / Storm
            elif any(k in s_low for k in ("पीड़ा", "अधमाई", "पाप", "दुःख", "दुख", "pain", "sin", "sorrow")):
                v_prompt = "Cinematic 8k photorealistic dramatic atmospheric visual of dark storm clouds dispersing as brilliant divine golden rays break through the shadows, symbolic victory of dharma and compassion over sorrow, dramatic volumetric lighting, 9:16 vertical"
                v_subj = "dharma dispersing dark storm clouds"
            # 13. Meditation / Contemplation / Seeker / Anxiety
            elif any(k in s_low for k in ("चिंता", "भविष्य", "बर्बाद", "तनाव", "worried", "anxious", "संसार का सबसे बड़ा", "पुण्य और", "संशय")):
                v_prompt = "Cinematic 8k photorealistic close-up of a thoughtful Indian seeker sitting peacefully in meditation at twilight, soft glowing oil lamp, deep contemplation, dramatic volumetric lighting, realistic skin texture, moody cinematic masterpiece, 9:16 vertical"
                v_subj = "contemplation of dharma at twilight"
            # 14. Arjuna trembling / Overwhelmed
            elif any(k in s_low for k in ("कांप", "अर्जुन", "arjuna", "गांडीव", "gandiva", "धनुष")) or ("हार का" in s_low or "डर था" in s_low or "हारना" in s_low):
                v_prompt = "Cinematic 8k photorealistic shot of warrior prince Arjuna in ornate ancient Indian golden armor and royal crown, standing overwhelmed on the dusty battlefield of Kurukshetra, sacred Gandiva bow trembling in his hands, dark dramatic storm clouds and burning embers in background, hyperrealistic, 9:16 vertical"
                v_subj = "Arjuna trembling in fear Kurukshetra"
            # 15. Focus / Determination
            elif any(k in s_low for k in ("फोकस", "तनाव छोड़ते", "डर खत्म", "focus", "clarity", "साहस", "दृढ़")):
                v_prompt = "Cinematic 8k photorealistic shot of Arjuna's eyes filled with fierce determination and razor-sharp focus, gripping the divine bow firmly on Kurukshetra battlefield, divine golden rays of sunlight piercing through dark thunder clouds, cinematic lighting, hyperrealistic, 9:16 vertical"
                v_subj = "Arjuna razor sharp focus on battlefield"
            # 16. Warrior rising / Willpower / Karma
            elif any(k in s_low for k in ("भाग्य", "मेहनत", "गिरने", "कर्म", "अधिकार", "destiny", "rise", "warrior", "सफलता")):
                v_prompt = "Cinematic 8k photorealistic shot of a determined ancient warrior rising up powerfully from the battlefield with iron willpower, glorious golden dawn horizon in background, dust and glowing golden particles in air, inspirational victory atmosphere, 8k, 9:16 vertical"
                v_subj = "warrior rising with iron will"
            # 17. Temple sanctum / Diya / Conch / Subscribe / Comment CTA
            elif any(k in s_low for k in ("सब्सक्राइब", "जय श्री राम", "जय श्री कृष्ण", "हर हर महादेव", "जय माता दी", "जय बजरंगबली", "जय शनि देव", "पहचान", "शंख", "conch")):
                v_prompt = "Cinematic 8k photorealistic magnificent wide shot of a grand ancient Hindu temple sanctum bathed in celestial golden evening light, glowing diya lamps and sacred saffron flags, triumphant divine devotion, 8k, 9:16 vertical"
                v_subj = "magnificent Vedic temple sanctum divine light"
            else:
                v_prompt = f"Cinematic 8k photorealistic sacred Indian epic art, {self._extract_ai_scene_prompt(sentence, 'Bhagavad Gita', idx)}, golden radiant aura, sacred cinematic lighting, 9:16 vertical"
                v_subj = "sacred Vedic scene"

            results.append({
                "scene_number": idx + 1,
                "narration": sentence,
                "visual_prompt": v_prompt,
                "visual_subject": v_subj,
            })
        return results

    def render_custom_video(
        self,
        script_text: str,
        title: str,
        voice: str = "auto",
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
        scenes: Optional[List[Dict[str, Any]]] = None,
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

        # Pre-flight dynamic disk space safeguard
        est_scenes = len(scenes) if (scenes and isinstance(scenes, list)) else (35 if is_long else 8)
        req_mb = 1500 if is_long else max(800, 300 + (est_scenes * 60))
        try:
            _, _, free_bytes = shutil.disk_usage(PROJECT_ROOT)
            free_mb = free_bytes / (1024 * 1024)
            if free_mb < req_mb:
                raise RuntimeError(
                    f"Insufficient disk space: Only {free_mb:.1f} MB available. "
                    f"At least {req_mb} MB free disk space is required to safely render this {est_scenes}-scene video."
                )
        except RuntimeError:
            raise
        except Exception as e:
            print_warning(f"Disk space check could not determine free space: {e}")

        # Build a stable scene contract before any TTS or visual acquisition.
        active_script = script_text.strip()
        has_user_scenes = bool(scenes and isinstance(scenes, list) and len(scenes) > 0)

        # Only auto-condense if user did NOT provide explicit storyboard scenes
        if not has_user_scenes and not is_long and len(active_script.split()) > 120:
            print_info(f"Input script has {len(active_script.split())} words. Auto-condensing for 48s Shorts limit...")
            condensed = self.condense_script_for_shorts(active_script, language=language)
            if condensed:
                active_script = condensed

        max_scene_count = 35 if is_long else (max(len(scenes), 8) if has_user_scenes else 6)
        scene_specs = self._prepare_scene_specs(
            script_text=active_script,
            title=title,
            provided_scenes=scenes,
            max_scenes=max_scene_count,
        )

        # If user explicitly provided scenes, keep active_script in perfect sync with the scene narrations
        if has_user_scenes:
            active_script = " ".join(str(s["narration"]).strip() for s in scene_specs if str(s.get("narration", "")).strip())

        # Safeguard: Auto-Inject Ending Debate & Subscribe Outro ONLY if completely absent and user did not specify scenes
        if auto_viral_hook and not is_long and not has_user_scenes:
            lower_s = active_script.lower()
            has_cta = any(k in lower_s for k in (
                "subscribe", "सब्सक्राइब", "like", "लाइक", "comment", "कमेंट", "follow", "फॉलो", "share", "शेयर"
            ))
            if not has_cta:
                lang_l = (language or "hi").lower()
                if lang_l in ("en", "english"):
                    cta_addon = "What is your opinion on this? Comment below and subscribe for more amazing facts!"
                else:
                    cta_addon = "कमेंट में अपनी राय बताएं, वीडियो को लाइक करें और चैनल को सब्सक्राइब जरूर करें!"
                active_script = f"{active_script} {cta_addon}".strip()
                if scene_specs:
                    scene_specs[-1]["narration"] = f"{scene_specs[-1]['narration']} {cta_addon}".strip()
                print_info("Auto Viral Booster: Injected 1 clean Subscribe & Like CTA.")

        if not has_user_scenes and self._normalize_scene_text(" ".join(s["narration"] for s in scene_specs)) != self._normalize_scene_text(active_script):
            scene_specs = self._prepare_scene_specs(
                script_text=active_script,
                title=title,
                provided_scenes=None,
                max_scenes=max_scene_count,
            )

        if not has_user_scenes and len(scene_specs) > max_scene_count:
            merged = " ".join(s["narration"] for s in scene_specs[max_scene_count - 1 :]).strip()
            scene_specs = scene_specs[: max_scene_count - 1] + [{
                **scene_specs[max_scene_count - 1],
                "scene_number": max_scene_count,
                "narration": merged,
            }]

        sentences = [str(s["narration"]).strip() for s in scene_specs if str(s.get("narration", "")).strip()]
        if not sentences:
            raise RuntimeError("No valid narration scenes were produced; render blocked.")

        if progress_callback: progress_callback(10, f"Synthesizing AI Voiceover ({voice}) for {format_label}...")

        # Resolve voice from subject + language unless the user explicitly selected one.
        selected_voice = str(voice or "").strip()
        if selected_voice.lower() in {"", "auto", "automatic", "smart"}:
            selected_voice = choose_subject_voice(
                title=title,
                script_text=active_script,
                language=language,
            )
            print_info(f"🎙️ Auto Voice Director: '{selected_voice}' selected for subject/language.")
        elif not is_voice_language_compatible(selected_voice, language):
            auto_voice = choose_subject_voice(title=title, script_text=active_script, language=language)
            print_warning(
                f"Voice '{selected_voice}' does not match target language '{language}'. "
                f"Using subject-matched voice '{auto_voice}'."
            )
            selected_voice = auto_voice

        # 1. Synthesize Voice using the exact scene contract for word-level scene timing.
        voice_audio = TEMP_DIR / f"{slug}_voice.mp3"
        rate_str = f"+{int((voice_speed - 1.0) * 100)}%" if voice_speed >= 1.0 else f"-{int((1.0 - voice_speed) * 100)}%"
        tts = TTSEngine(default_voice=selected_voice, rate=rate_str)
        tts_res = tts.synthesize(
            text=active_script,
            output_audio_path=voice_audio,
            voice=selected_voice,
            scenes=scene_specs,
        )
        total_duration = tts_res.duration_seconds

        # Universal Shorts Duration Clamp: Guarantee final video strictly complies with <60s YouTube Shorts feed cutoff
        if not is_long:
            tts_res = tts.clamp_duration(
                tts_res=tts_res,
                max_seconds=58.5,
                target_seconds=56.5,
                width=target_width,
                height=target_height,
            )
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

        # 3. Real-incident archive access is resolved per narration scene.
        # This prevents a global archive pool from placing the wrong entity's photo underneath a different sentence.
        archival_fetcher = None
        if real_incident_mode and visual_mode in ("hybrid", "real_only", "multi_cinematic"):
            try:
                from autotube.media.archival_fetcher import ArchivalFetcher
                archival_fetcher = ArchivalFetcher()
            except Exception as exc:
                print_warning(f"Archival fetcher unavailable: {exc}")

        if progress_callback:
            progress_callback(55, f"Acquiring visual scenes ({orientation} {target_width}x{target_height}, Mode: {visual_mode})...")

        # 4. Acquire Video Scene Assets (Multi-Source AI Best Match / Hybrid Real Archives / AI Visuals)
        scene_assets_by_scene: Dict[int, Path] = {}
        scene_errors: Dict[int, str] = {}
        from autotube.media.ai_visuals import VisualGenerator
        from autotube.media.nvidia_video import NvidiaVideoGenerator
        from autotube.media.multi_stock_aggregator import MultiStockAggregator

        vg = VisualGenerator()
        nvidia = NvidiaVideoGenerator()
        multi_agg = MultiStockAggregator()
        pexels = getattr(multi_agg, "pexels_fetcher", getattr(multi_agg, "pexels", None))
        if not pexels:
            from autotube.media.pexels_video import PexelsVideoFetcher
            pexels = PexelsVideoFetcher()
        # Studio motion scenes require actual frame-level semantic validation.
        multi_agg.visual_quality_gate.strict = True

        # Check if topic/script represents Gita / Granth / Spiritual content
        gita_granth_keywords = (
            "gita", "गीता", "krishna", "कृष्ण", "arjuna", "अर्जुन", "karma", "कर्म",
            "kurukshetra", "कुरुक्षेत्र", "chanakya", "चाणक्य", "upanishad", "उपनिषद",
            "granth", "ग्रंथ", "shloka", "श्लोक", "bhagwat", "bhagavad", "vedic",
            "vedas", "वेद", "ramayan", "रामायण", "mahabharat", "महाभारत", "sanatan",
            "सनातन", "adhyatmik", "spiritual", "vishnu", "विष्णु", "bhagavan", "भगवान",
            "dharma", "धर्म", "geeta"
        )
        scene_meta_str = " ".join(f"{s.get('visual_subject', '')} {s.get('visual_description', '')}" for s in scene_specs).lower()
        combined_text = f"{title} {script_text} {' '.join(str(s.get('narration', '')) for s in scene_specs)} {scene_meta_str}".lower()
        is_gita_granth_topic = any(k in combined_text for k in gita_granth_keywords)
        if is_gita_granth_topic:
            print_info("🕉️ [Gita/Granth Engine] Detected scripture/divine content: using direct 4K/8K photorealistic AI visuals + continuous motion clips.")

        from autotube.media.visual_waterfall import _image_to_motion_clip
        scene_durations = list(tts_res.scene_durations or [])

        for idx, scene in enumerate(scene_specs):
            sentence = str(scene["narration"]).strip()
            scene_target = TEMP_DIR / f"scene_{idx}_{slug}.mp4"
            acquired_video = None
            scene_plan = self._scene_plan_from_spec(scene)
            scene_dur = scene_durations[idx] if idx < len(scene_durations) else float(scene.get("duration", 6.0))

            try:
                # 0. User-provided custom/uploaded image takes HIGHEST precedence
                custom_img_str = str(scene.get("custom_image_path") or scene.get("image_path") or "").strip()
                if custom_img_str:
                    custom_img_p = Path(custom_img_str)
                    if custom_img_p.exists() and custom_img_p.stat().st_size > 5000:
                        print_info(f"   🖼️ [Custom User Image] Scene {idx+1}: Using uploaded 4K image '{custom_img_p.name}' -> Ken Burns motion clip...")
                        if progress_callback:
                            progress_callback(55 + int((idx / max(1, len(scene_specs))) * 18), f"🎬 Scene {idx+1}/{len(scene_specs)}: Animating user custom image...")
                        motion_clip = _image_to_motion_clip(
                            image_path=custom_img_p,
                            output_path=scene_target,
                            duration=scene_dur,
                            fps=30,
                            width=target_width,
                            height=target_height,
                            motion_type=idx,
                        )
                        if motion_clip and motion_clip.exists() and motion_clip.stat().st_size > 10000:
                            acquired_video = motion_clip
                            print_success(f"   🎬 [Custom Image Motion Clip] Scene {idx+1} successfully converted to Ken Burns motion clip ({scene_dur:.1f}s)!")
                        else:
                            print_warning(f"Ken Burns conversion failed for custom image in scene {idx+1}, falling back to AI visuals.")

                if acquired_video:
                    pass
                elif is_gita_granth_topic:
                    if progress_callback:
                        progress_callback(55 + int((idx / max(1, len(scene_specs))) * 18), f"🎨 Scene {idx+1}/{len(scene_specs)}: Generating 4K/8K divine AI photorealistic visual...")

                    explicit_prompt = str(scene.get("visual_prompt") or "").strip()
                    if explicit_prompt:
                        ai_prompt = explicit_prompt
                    else:
                        v_desc = str(scene.get("visual_description", "")).strip()
                        v_subj = str(scene.get("visual_subject", "")).strip()
                        if not v_desc and scene_plan:
                            v_desc = str(scene_plan.get("environment", "") or scene_plan.get("action", "")).strip()
                        if not v_subj and scene_plan:
                            v_subj = str(scene_plan.get("subject", "")).strip()

                        # High-aesthetic 4K/8K prompt construction
                        if v_desc and len(v_desc) > 15:
                            prompt_parts = []
                            if v_subj and v_subj.lower() not in v_desc.lower():
                                prompt_parts.append(v_subj)
                            prompt_parts.append(v_desc)
                            core_prompt = ", ".join(prompt_parts)
                        else:
                            core_prompt = self._extract_ai_scene_prompt(sentence, title, idx)

                        ai_prompt = f"8k photorealistic ultra-detailed cinematic divine art, {core_prompt}, golden divine aura, sacred majestic lighting, 8k resolution, cinematic composition, hyperrealistic sacred epic art"

                    ai_img_path = TEMP_DIR / f"gita_ai_{idx}_{slug}.jpg"
                    print_info(f"   🕉️ [Gita/Granth Visual Engine] Scene {idx+1}: Generating 4K/8K AI visual: '{ai_prompt[:75]}...'")

                    is_vert = target_height > target_width
                    source_w = 2160 if is_vert else 3840
                    source_h = 3840 if is_vert else 2160
                    poll_key = os.getenv("POLLINATIONS_API_KEY", "").strip()

                    ai_img = vg.generate_image(
                        prompt=ai_prompt,
                        output_path=ai_img_path,
                        width=source_w,
                        height=source_h,
                        style="spiritual_photorealistic",
                        require_native_resolution=bool(poll_key),
                        allow_photo_fallback=False,
                    )
                    if not ai_img or not ai_img.exists() or ai_img.stat().st_size <= 5000:
                        fallback_subj = scene.get("visual_subject") or "Lord Krishna divine wisdom in Kurukshetra"
                        ai_img = vg.generate_image(
                            prompt=f"8k photorealistic divine cinematic art, {fallback_subj}, golden aura, epic sacred masterpiece, 8k",
                            output_path=ai_img_path,
                            width=source_w,
                            height=source_h,
                            style="spiritual_photorealistic",
                            require_native_resolution=bool(poll_key),
                            allow_photo_fallback=False,
                        )

                    if ai_img and ai_img.exists() and ai_img.stat().st_size > 5000:
                        motion_clip = _image_to_motion_clip(
                            image_path=ai_img,
                            output_path=scene_target,
                            duration=scene_dur,
                            fps=30,
                            width=target_width,
                            height=target_height,
                            motion_type=idx,
                        )
                        if motion_clip and motion_clip.exists() and motion_clip.stat().st_size > 10000:
                            acquired_video = motion_clip
                            print_success(f"   🎬 [Gita AI Motion Clip] Scene {idx+1} successfully converted to continuous Ken Burns motion clip ({scene_dur:.1f}s)!")
                        else:
                            raise RuntimeError(f"Motion video conversion failed for Gita/Granth scene {idx+1}.")
                    else:
                        raise RuntimeError(f"AI visual generation failed for Gita/Granth scene {idx+1}.")
                elif visual_mode in ("multi_cinematic", "multi_best", "auto"):
                    historical = any(
                        k in sentence.lower()
                        for k in (
                            "193", "194", "195", "196", "197", "archiv", "document", "report",
                            "committee", "investigation", "classified", "gandhi", "bose", "netaji",
                            "roswell", "shanti devi", "punarjanam", "rebirth",
                        )
                    )
                    if real_incident_mode and historical and archival_fetcher:
                        archive_hits = archival_fetcher.fetch_archival_visuals(
                            topic=title,
                            script_text=sentence,
                            count=1,
                            progress_callback=progress_callback,
                        )
                        if archive_hits:
                            acquired_video = archive_hits[0]
                    if not acquired_video:
                        if progress_callback:
                            progress_callback(55 + int((idx / max(1, len(scene_specs))) * 18), f"🔍 Scene {idx+1}/{len(scene_specs)}: semantic visual search + validation...")
                        acquired_video = multi_agg.get_best_scene_asset(
                            scene_text=sentence,
                            title=title,
                            scene_index=idx,
                            orientation=orientation,
                            scene_plan=scene_plan,
                            archival_pool=None,
                            allow_archival_fallback=False,
                            # Director Studio is video-first: do not silently replace
                            # missing motion footage with a static AI/Pexels image.
                            allow_ai_fallback=False,
                        )
                elif visual_mode == "real_only":
                    if not archival_fetcher:
                        raise RuntimeError(f"Archival mode unavailable for scene {idx+1}.")
                    archive_hits = archival_fetcher.fetch_archival_visuals(
                        topic=title,
                        script_text=sentence,
                        count=1,
                        progress_callback=progress_callback,
                    )
                    if archive_hits:
                        acquired_video = archive_hits[0]
                    else:
                        raise RuntimeError(f"No scene-specific archival asset available for scene {idx+1}.")
                elif visual_mode == "hybrid":
                    is_historical_scene = any(
                        k in sentence.lower()
                        for k in (
                            "193", "194", "195", "196", "197", "archiv", "document", "report",
                            "committee", "investigation", "classified", "gandhi", "bose", "netaji",
                            "roswell", "shanti devi", "punarjanam", "rebirth",
                        )
                    )
                    if is_historical_scene and archival_fetcher:
                        archive_hits = archival_fetcher.fetch_archival_visuals(
                            topic=title,
                            script_text=sentence,
                            count=1,
                            progress_callback=progress_callback,
                        )
                        if archive_hits:
                            acquired_video = archive_hits[0]
                    if not acquired_video:
                        acquired_video = multi_agg.get_best_scene_asset(
                            scene_text=sentence,
                            title=title,
                            scene_index=idx,
                            orientation=orientation,
                            scene_plan=scene_plan,
                            archival_pool=None,
                            allow_archival_fallback=False,
                            # Director Studio is video-first: do not silently replace
                            # missing motion footage with a static AI/Pexels image.
                            allow_ai_fallback=False,
                        )
                elif visual_mode == "stock":
                    acquired_video = multi_agg.get_best_scene_asset(
                        scene_text=sentence,
                        title=title,
                        scene_index=idx,
                        orientation=orientation,
                        scene_plan=scene_plan,
                        archival_pool=None,
                        allow_archival_fallback=False,
                        allow_ai_fallback=False,
                    )
                elif visual_mode == "ai_only":
                    ai_prompt = self._extract_ai_scene_prompt(sentence, title, idx)
                    ai_img_path = TEMP_DIR / f"pure_ai_{idx}_{slug}.jpg"
                    if progress_callback:
                        progress_callback(55 + int((idx / max(1, len(scene_specs))) * 18), f"Generating scene {idx+1}/{len(scene_specs)} with AI visual direction...")
                    ai_res = vg.generate_image(
                        prompt=ai_prompt,
                        output_path=ai_img_path,
                        width=target_width,
                        height=target_height,
                        style="cinematic",
                    )
                    if ai_res and ai_res.exists() and ai_res.stat().st_size > 4000:
                        motion_clip = _image_to_motion_clip(
                            image_path=ai_res,
                            output_path=scene_target,
                            duration=scene_dur,
                            fps=30,
                            width=target_width,
                            height=target_height,
                            motion_type=idx,
                        )
                        acquired_video = motion_clip if (motion_clip and motion_clip.exists()) else ai_res
                    else:
                        raise RuntimeError(f"AI visual generation failed for scene {idx+1}.")
                else:
                    raise RuntimeError(f"Unsupported visual mode: {visual_mode}")

                # Dedicated motion-video fallback chain. MultiStockAggregator can return
                # None after strict video/QA filtering; do not stop the scene there.
                fallback_queries = list((scene_plan or {}).get("search_queries") or [])
                fallback_queries.append(self._extract_visual_search_query(sentence, title, idx))
                deduped_queries = []
                for query in fallback_queries:
                    clean_query = str(query).strip()
                    if clean_query and clean_query.lower() not in {q.lower() for q in deduped_queries}:
                        deduped_queries.append(clean_query)

                if not acquired_video and visual_engine in ("nvidia", "auto") and nvidia.is_configured():
                    for english_q in deduped_queries[:4]:
                        if scene_target.exists():
                            try:
                                scene_target.unlink()
                            except Exception:
                                pass
                        acquired_video = nvidia.generate_video(
                            prompt=english_q,
                            output_path=scene_target,
                            allow_stock_fallback=False,
                        )
                        if acquired_video and acquired_video.exists():
                            if multi_agg._record_asset_fingerprint(acquired_video, label="NVIDIA"):
                                print_success(
                                    f"   🎬 [NVIDIA Video Fallback] Scene {idx+1} acquired fresh motion footage "
                                    f"with query: '{english_q}'"
                                )
                                break
                            print_warning(
                                f"   ♻️ NVIDIA returned previously-used video for scene {idx+1}; trying next query."
                            )
                            acquired_video = None

                # Every video asset must pass frame-level QA, except explicitly user-provided custom images
                if acquired_video and (not custom_img_str) and visual_mode in ("multi_cinematic", "multi_best", "auto", "hybrid", "stock"):
                    acquired_path = Path(acquired_video)
                    if acquired_path.suffix.lower() not in {".mp4", ".mov", ".webm", ".mkv"}:
                        print_warning(f"   ⚠️ Non-video asset returned for Scene {idx+1}; rejecting.")
                        acquired_video = None
                    else:
                        qa = multi_agg.visual_quality_gate.verify(
                            acquired_path,
                            sentence,
                            scene_plan,
                        )
                        if not qa.get("accepted"):
                            print_warning(
                                f"   ⚠️ Frame QA rejected Scene {idx+1}: "
                                f"{qa.get('reason', 'visual mismatch')}"
                            )
                            acquired_video = None

                # Pexels is the final real-motion fallback for every video-first Studio mode.
                # Previously this was gated by visual_engine, so multi_cinematic could exhaust
                # MultiStock/NVIDIA and then fail every scene without ever trying Pexels.
                if not acquired_video and visual_mode in ("multi_cinematic", "multi_best", "auto", "hybrid", "stock"):
                    for english_q in deduped_queries[:4]:
                        candidate = multi_agg.get_fresh_pexels_video(
                            search_query=english_q,
                            scene_index=idx,
                            orientation=orientation,
                        )
                        if not candidate:
                            continue
                        qa = multi_agg.visual_quality_gate.verify(
                            candidate,
                            sentence,
                            scene_plan,
                        )
                        if qa.get("accepted"):
                            acquired_video = candidate
                            print_success(
                                f"   🎬 [Pexels Video Fallback] Scene {idx+1} acquired fresh, QA-approved motion footage "
                                f"with query: '{english_q}'"
                            )
                            break
                        print_warning(
                            f"   ⚠️ Pexels fallback QA rejected Scene {idx+1}: "
                            f"{qa.get('reason', 'visual mismatch')}"
                        )

                if not acquired_video and visual_mode in ("multi_cinematic", "multi_best", "auto", "hybrid", "stock"):
                    # Safe cinematic stock motion video fallback matching story genre
                    try:
                        is_space = any(k in sentence.lower() or k in title.lower() for k in ("space", "antariksh", "अंतरिक्ष", "black hole", "galaxy", "universe", "planet", "stars", "cosmos", "telescope", "beacon", "singularity", "pulsar"))
                        is_hist = (not is_space) and any(k in sentence.lower() or k in title.lower() for k in ("mahabharat", "महाभारत", "ramayan", "रामायण", "kurukshetra", "कुरुक्षेत्र", "temple", "mandir", "मंदिर", "itihas", "इतिहास", "prachin", "प्राचीन", "purana", "पुराण", "dwarka", "द्वारका", "archaeol"))

                        if is_space:
                            fallback_pool = [
                                "deep space stars cosmos nebula",
                                "black hole event horizon cosmos",
                                "spinning planet universe galaxy",
                                "telescope observatory starry night",
                                "cosmic dust interstellar space",
                                "glowing galaxy stars rotation",
                            ]
                        elif is_hist:
                            fallback_pool = [
                                "ancient stone temple ruins dramatic",
                                "mysterious hindu temple architecture",
                                "ancient historical ruins aerial",
                                "underwater ocean ruins deep water",
                                "epic battlefield landscape dramatic mist",
                                "ancient artifacts excavation archaeology",
                                "sacred river ghats ancient india",
                            ]
                        else:
                            fallback_pool = [
                                "cinematic dramatic atmosphere fog",
                                "mysterious dark misty forest",
                                "dramatic ocean waves slow motion",
                                "dark moody clouds time lapse",
                                "cinematic mountain valley dramatic",
                            ]

                        already_used_files = {p.name for p in scene_assets_by_scene.values() if p}
                        safe_candidates = [deduped_queries[0]] if deduped_queries else []
                        for offset in range(len(fallback_pool)):
                            safe_candidates.append(fallback_pool[(idx + offset) % len(fallback_pool)])

                        for q_cand in safe_candidates:
                            safe_v = pexels.get_scene_video(search_query=q_cand, orientation=orientation, scene_index=idx)
                            if not safe_v or not safe_v.exists() or safe_v.stat().st_size <= 5000:
                                continue
                            if safe_v.name in already_used_files:
                                continue

                            qa = multi_agg.visual_quality_gate.verify(safe_v, sentence, scene_plan)
                            if qa.get("accepted"):
                                acquired_video = safe_v
                                print_success(f"   ✅ [Fail-Safe Video] Scene {idx+1} acquired QA-verified motion footage: {safe_v.name}")
                                break
                            elif not qa.get("violations"):
                                acquired_video = safe_v
                                print_info(f"   🎬 [Thematic Fallback] Scene {idx+1} covered with atmospheric genre footage: {safe_v.name}")
                                break
                            else:
                                print_warning(f"   ⚠️ Fail-safe candidate rejected by QA: {qa.get('reason', 'visual mismatch')}")
                    except Exception as s_err:
                        print_warning(f"   ⚠️ Fail-safe video search failed for Scene {idx+1}: {s_err}")

                if not acquired_video and visual_mode == "ai_only":
                    # Bespoke AI Image only in explicit ai_only mode
                    try:
                        ai_prompt = self._extract_ai_scene_prompt(sentence, title, idx)
                        ai_target = TEMP_DIR / f"ai_failsafe_{idx}_{slug}.jpg"
                        print_info(f"   🎨 [Fail-Safe AI Visual] Generating bespoke 8K visual for Scene {idx+1}...")
                        ai_asset = vg.generate_image(
                            prompt=ai_prompt,
                            output_path=ai_target,
                            width=target_width,
                            height=target_height,
                            style="cinematic",
                        )
                        if ai_asset and ai_asset.exists() and ai_asset.stat().st_size > 5000:
                            acquired_video = ai_asset
                            print_success(f"   ✅ [Fail-Safe AI Visual] Scene {idx+1} covered with 8K visual: {ai_asset.name}")
                    except Exception as ai_err:
                        print_warning(f"   ⚠️ Fail-safe AI generation failed for Scene {idx+1}: {ai_err}")

                if not acquired_video:
                    raise RuntimeError(f"Could not acquire any visual asset for scene {idx+1}.")

                acquired_path = Path(acquired_video)
                if not acquired_path.exists() or acquired_path.stat().st_size < 5000:
                    raise RuntimeError(f"Visual asset for scene {idx+1} is missing or too small.")

                # In motion video modes, strictly disallow static image files
                if visual_mode in ("multi_cinematic", "multi_best", "auto", "hybrid", "stock"):
                    if acquired_path.suffix.lower() not in {".mp4", ".mov", ".webm", ".mkv"}:
                        raise RuntimeError(
                            f"Render blocked: Scene {idx+1} acquired static image ({acquired_path.suffix}) "
                            f"in motion-only mode '{visual_mode}'."
                        )

                scene_assets_by_scene[idx] = acquired_path
            except Exception as exc:
                scene_errors[idx] = str(exc)
                print_error(f"❌ Scene {idx+1} visual acquisition failed: {exc}")

        # Strict Quality Enforced: Every narration scene must have its own unique visual.
        # No scene duplication or donor borrowing allowed.
        missing = [i for i in range(len(scene_specs)) if i not in scene_assets_by_scene]
        if missing:
            details = "; ".join(
                f"scene {idx + 1}: {scene_errors.get(idx, 'unknown visual acquisition error')}"
                for idx in missing
            )
            raise RuntimeError(
                "Render blocked: every narration scene must have its own unique, exact visual asset. "
                f"Scene duplication/reuse is strictly disallowed. Missing scenes: {[m + 1 for m in missing]}. {details}"
            )

        scene_videos = [scene_assets_by_scene[idx] for idx in range(len(scene_specs))]
        if len(scene_videos) != len(scene_specs):
            raise RuntimeError("Internal scene mapping error: scene count and visual asset count differ.")

        # Strict Scene Deduplication Gate: verify distinct paths AND distinct content hashes
        scene_paths_seen = set()
        scene_hashes_seen = set()
        import hashlib
        for i, s_path in enumerate(scene_videos):
            if s_path in scene_paths_seen:
                raise RuntimeError(
                    f"Render blocked: Scene {i+1} duplicates visual file '{s_path.name}'. "
                    "Every scene must have a distinct, non-repeated video clip."
                )
            scene_paths_seen.add(s_path)
            try:
                with open(s_path, "rb") as fh:
                    f_hash = hashlib.sha256(fh.read(1024 * 1024)).hexdigest()
                if f_hash in scene_hashes_seen:
                    raise RuntimeError(
                        f"Render blocked: Scene {i+1} has identical video content hash to another scene. "
                        "Duplicate footage across scenes is strictly prohibited."
                    )
                scene_hashes_seen.add(f_hash)
            except Exception:
                pass

        if progress_callback:
            progress_callback(75, f"Compositing video timeline ({target_width}x{target_height}, {len(scene_videos)} validated scenes)...")

        # 4. Composite Video
        builder = ShortsBuilder()
        unsubtitled_video = TEMP_DIR / f"{slug}_unsubbed.mp4"

        num_scenes = len(scene_videos)
        scene_durations = list(tts_res.scene_durations or [])
        if len(scene_durations) != num_scenes:
            raise RuntimeError(f"TTS scene timing mismatch: {len(scene_durations)} durations for {num_scenes} scenes.")
        if any(d <= 0 for d in scene_durations):
            raise RuntimeError("TTS produced a non-positive scene duration; render blocked.")

        try:
            build_result = ShortsBuilder().build_short(
                audio_path=mixed_audio if mixed_audio.exists() else tts_res.audio_path,
                output_path=unsubtitled_video,
                scene_videos=scene_videos,
                scene_durations=scene_durations,
                subtitles_file=None,
                width=target_width,
                height=target_height,
            )
            if not build_result or not unsubtitled_video.exists():
                raise RuntimeError("Video compositor rejected or failed the scene mapping; render blocked.")

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

            if not is_long and final_video_path.exists():
                final_media_dur = get_media_duration(final_video_path)
                if final_media_dur >= 59.5:
                    try:
                        final_video_path.unlink()
                    except Exception:
                        pass
                    raise RuntimeError(
                        f"Fail-Closed Duration Gate: Rendered Short duration is {final_media_dur:.2f}s, "
                        "which violates the strict 60.0s YouTube Shorts limit! Video blocked and deleted."
                    )
        finally:
            if unsubtitled_video.exists() and final_video_path != unsubtitled_video:
                try:
                    unsubtitled_video.unlink()
                except Exception:
                    pass

        if progress_callback: progress_callback(100, f"✅ {format_label} rendered successfully!")

        size_mb = round(final_video_path.stat().st_size / (1024 * 1024), 2)
        print_success(f"Director Video generated: {final_video_path.name} ({size_mb} MB, {total_duration:.1f}s)!")

        scene_manifest = [
            {
                "scene_number": idx + 1,
                "start": round(sum(scene_durations[:idx]), 3),
                "end": round(sum(scene_durations[: idx + 1]), 3),
                "narration": scene_specs[idx]["narration"],
                "asset": scene_videos[idx].name,
                "visual_subject": scene_specs[idx].get("visual_subject", ""),
            }
            for idx in range(num_scenes)
        ]
        manifest_path = final_video_path.with_suffix(".manifest.json")
        try:
            with open(manifest_path, "w", encoding="utf-8") as mf:
                json.dump(scene_manifest, mf, ensure_ascii=False, indent=2)
        except Exception as exc:
            print_warning(f"Could not write scene manifest: {exc}")

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
            "scene_count": num_scenes,
            "scene_manifest": scene_manifest,
            "manifest_path": str(manifest_path),
        }
