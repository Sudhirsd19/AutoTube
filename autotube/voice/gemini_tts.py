"""Gemini 3.8 Flash TTS Engine for AutoTube - Ultra-Realistic Human Speech."""

import base64
import os
import re
import time
from pathlib import Path
from typing import Any, Dict, List, Optional
from google import genai
from pydantic import BaseModel

from autotube.config import get_config
from autotube.utils.console import print_info, print_success, print_warning, print_error
from autotube.utils.ffmpeg_helper import get_media_duration, run_ffmpeg
from autotube.voice.tts_engine import TimedWord, TTSResult


# Curated Gemini 3.8 Flash TTS Voice Personas
GEMINI_VOICES: Dict[str, str] = {
    # Cinematic / Mystery / Authority Male
    "charon": "Charon",
    "gemini_charon": "Charon",
    "gemini_male_deep": "Charon",
    # Energetic / Upbeat Storyteller Male
    "puck": "Puck",
    "gemini_puck": "Puck",
    "gemini_male_energetic": "Puck",
    # Intense / Dramatic Male
    "fenrir": "Fenrir",
    "gemini_fenrir": "Fenrir",
    # Warm / Engaging Female
    "aoede": "Aoede",
    "gemini_aoede": "Aoede",
    "gemini_female_warm": "Aoede",
    # Clear / Calm Female
    "kore": "Kore",
    "gemini_kore": "Kore",
}


class GeminiTTSEngine:
    """Ultra-realistic text-to-speech using Google's Gemini 3.8 Flash TTS with resilient fallbacks."""

    def __init__(self, default_voice: str = "Charon"):
        self.cfg = get_config()
        self.api_key = os.getenv("GEMINI_API_KEY")
        if not self.api_key:
            raise RuntimeError("GEMINI_API_KEY environment variable is required for Gemini TTS.")
        self.default_voice = self._resolve_voice_name(default_voice)

    def _resolve_voice_name(self, voice_id: Optional[str]) -> str:
        clean = (voice_id or "").strip().lower()
        if clean in GEMINI_VOICES:
            return GEMINI_VOICES[clean]
        for v in ("Charon", "Puck", "Fenrir", "Aoede", "Kore"):
            if clean == v.lower():
                return v
        return "Charon"

    def synthesize(
        self,
        text: str,
        output_audio_path: Path,
        voice: Optional[str] = None,
        scenes: Optional[List[Dict[str, Any]]] = None,
    ) -> TTSResult:
        """Synthesize ultra-realistic speech from text using Gemini 3.8 Flash TTS with retry & fallback."""
        resolved_voice = self._resolve_voice_name(voice or self.default_voice)
        output_audio_path.parent.mkdir(parents=True, exist_ok=True)

        print_info(f"🎙️ Synthesizing voice with Gemini 3.8 Flash TTS (Voice: {resolved_voice})...")

        audio_bytes = None
        max_attempts = 3
        last_error = None

        for attempt in range(1, max_attempts + 1):
            try:
                client = genai.Client(api_key=self.api_key)
                response = client.interactions.create(
                    model="gemini-3.8-flash-tts",
                    input=[{"type": "user_input", "content": [{"type": "text", "text": text.strip()}]}],
                    response_format={"type": "audio"},
                    generation_config={"speech_config": [{"voice": resolved_voice}]},
                )

                if hasattr(response, "output_audio") and response.output_audio and hasattr(response.output_audio, "data"):
                    raw_data = response.output_audio.data
                    if raw_data:
                        audio_bytes = base64.b64decode(raw_data)
                        if audio_bytes and len(audio_bytes) > 500:
                            break
            except Exception as e:
                last_error = e
                print_warning(
                    f"⚠️ Gemini 3.8 Flash TTS attempt {attempt}/{max_attempts} failed ({e}). "
                    f"{'Retrying in ' + str(attempt * 2) + 's...' if attempt < max_attempts else ''}"
                )
                if attempt < max_attempts:
                    time.sleep(attempt * 2)

        # Graceful fallback: If Gemini TTS is busy, blocked by safety filter, or unavailable,
        # fallback to Edge-TTS instead of crashing the pipeline!
        if not audio_bytes:
            print_warning(
                f"⚠️ Gemini 3.8 Flash TTS unavailable ({last_error or 'empty response'}). "
                "Seamlessly falling back to high-fidelity Edge-TTS engine..."
            )
            from autotube.voice.tts_engine import TTSEngine
            is_hindi = any("ऀ" <= c <= "ॿ" for c in text)
            is_female = resolved_voice.lower() in ("aoede", "kore")
            fallback_voice = ("hi_cinematic_female" if is_female else "hi_deep_cinematic_male") if is_hindi else ("en_cinematic_female" if is_female else "en_deep_cinematic_male")
            edge_engine = TTSEngine(default_voice=fallback_voice)
            return edge_engine.synthesize(
                text=text,
                output_audio_path=output_audio_path,
                voice=fallback_voice,
                scenes=scenes,
            )

        # Save as WAV first, then normalize/transcode to target output path
        temp_wav = output_audio_path.with_suffix(".temp.wav")
        temp_wav.write_bytes(audio_bytes)

        # Transcode according to requested target extension
        is_wav_target = output_audio_path.suffix.lower() == ".wav"
        if is_wav_target:
            transcode_cmd = [
                "-i", str(temp_wav),
                "-c:a", "pcm_s16le",
                "-ar", "48000",
                str(output_audio_path),
            ]
        else:
            transcode_cmd = [
                "-i", str(temp_wav),
                "-c:a", "libmp3lame",
                "-b:a", "192k",
                "-ar", "48000",
                str(output_audio_path),
            ]

        run_ffmpeg(
            transcode_cmd,
            desc=f"Encoding synthesized audio to {output_audio_path.suffix.upper()}",
        )

        try:
            temp_wav.unlink(missing_ok=True)
        except Exception:
            pass

        duration = get_media_duration(output_audio_path)
        print_success(f"✅ Gemini 3.8 Flash TTS audio ready ({duration:.2f}s): {output_audio_path.name}")

        # Compute scene durations proportional to narration word counts if scenes provided
        scene_durations: List[float] = []
        if scenes:
            valid_narrations = [
                str(s.get("narration") or s.get("text") or "").strip()
                for s in scenes
            ]
            valid_narrations = [n for n in valid_narrations if n]
            total_words = sum(len(n.split()) for n in valid_narrations)
            if total_words > 0 and duration > 0:
                elapsed = 0.0
                for idx, n in enumerate(valid_narrations):
                    w_count = len(n.split())
                    if idx == len(valid_narrations) - 1:
                        dur_s = max(1.5, duration - elapsed)
                    else:
                        dur_s = round((w_count / total_words) * duration, 2)
                        dur_s = max(1.5, dur_s)
                    scene_durations.append(dur_s)
                    elapsed += dur_s

        # Basic timed words approximation for subtitle aligners
        words = text.split()
        timed_words: List[TimedWord] = []
        if words and duration > 0:
            word_time = duration / len(words)
            for i, w in enumerate(words):
                st = round(i * word_time, 2)
                en = round((i + 1) * word_time, 2)
                timed_words.append(TimedWord(word=w, start=st, end=en, duration=round(en - st, 2)))

        return TTSResult(
            audio_path=output_audio_path,
            duration_seconds=duration,
            words=timed_words,
            scene_durations=scene_durations if scene_durations else None,
        )
