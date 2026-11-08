"""Gemini 3.8 Flash & Flash Lite TTS Engine for AutoTube - Ultra-Realistic Human Speech.

Powered by Google GenAI Interactions & OpenMontage voice personas.
"""

import base64
import os
import re
import time
import requests
from pathlib import Path
from typing import Any, Dict, List, Optional
from google import genai
from pydantic import BaseModel

from autotube.config import get_config
from autotube.utils.console import print_info, print_success, print_warning, print_error
from autotube.utils.ffmpeg_helper import get_media_duration, run_ffmpeg
from autotube.voice.tts_engine import TimedWord, TTSResult


# Curated Gemini 3.8 Flash TTS Voice Personas (OpenMontage Multilingual)
GEMINI_VOICES: Dict[str, str] = {
    # Cinematic / Mystery / Authority Male
    "charon": "Charon",
    "gemini_charon": "Charon",
    "gemini_male_deep": "Charon",
    "en_deep_cinematic_male": "Charon",
    "hi_deep_cinematic_male": "Charon",
    "hi_astro_vibes_male": "Charon",
    "christopher": "Charon",
    "madhur": "Charon",
    # Energetic / Upbeat Storyteller Male
    "puck": "Puck",
    "gemini_puck": "Puck",
    "gemini_male_energetic": "Puck",
    "en_energetic_male": "Puck",
    "guy": "Puck",
    # Intense / Dramatic Male
    "fenrir": "Fenrir",
    "gemini_fenrir": "Fenrir",
    # Warm / Engaging Female
    "aoede": "Aoede",
    "gemini_aoede": "Aoede",
    "gemini_female_warm": "Aoede",
    "en_cinematic_female": "Aoede",
    "hi_cinematic_female": "Aoede",
    "swara": "Aoede",
    # Clear / Calm Female
    "kore": "Kore",
    "gemini_kore": "Kore",
}


class GeminiTTSEngine:
    """Ultra-realistic text-to-speech using Google's Gemini Flash TTS with resilient cascade & fallbacks."""

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
        """Synthesize ultra-realistic speech from text using Gemini Flash TTS with multi-model cascade."""
        resolved_voice = self._resolve_voice_name(voice or self.default_voice)
        output_audio_path.parent.mkdir(parents=True, exist_ok=True)

        print_info(f"🎙️ Synthesizing voice with OpenMontage Gemini TTS (Voice: {resolved_voice})...")

        audio_bytes = None
        last_error = None

        # Multi-model cascade: gemini-3.8-flash-lite-tts offers high speed & generous quota,
        # while gemini-3.8-flash-tts is the standard model.
        candidate_models = ["gemini-3.8-flash-lite-tts", "gemini-3.8-flash-tts"]
        pref = os.getenv("GEMINI_TTS_MODEL")
        if pref and pref in candidate_models:
            candidate_models.remove(pref)
            candidate_models.insert(0, pref)

        # Attempt 1: Fast direct HTTP invocation (bypasses SDK retry sleep loops on 429)
        endpoint = f"https://generativelanguage.googleapis.com/v1beta/interactions?key={self.api_key}"
        clean_text = text.strip()

        for model in candidate_models:
            payload = {
                "model": model,
                "input": [{"type": "user_input", "content": [{"type": "text", "text": clean_text}]}],
                "response_format": {"type": "audio"},
                "generation_config": {"speech_config": [{"voice": resolved_voice}]},
            }

            try:
                t0 = time.time()
                resp = requests.post(endpoint, json=payload, timeout=25.0)
                elapsed = time.time() - t0

                if resp.status_code == 200:
                    resp_json = resp.json()
                    raw_b64 = None
                    # Search steps
                    for step in resp_json.get("steps", []):
                        for part in step.get("content", []):
                            if part.get("type") == "audio" and part.get("data"):
                                raw_b64 = part.get("data")
                                break
                        if raw_b64:
                            break
                    if not raw_b64 and resp_json.get("output_audio", {}).get("data"):
                        raw_b64 = resp_json["output_audio"]["data"]

                    if raw_b64:
                        audio_bytes = base64.b64decode(raw_b64)
                        if audio_bytes and len(audio_bytes) > 500:
                            print_success(f"   ✨ Gemini TTS ({model}, {resolved_voice}) synthesized in {elapsed:.2f}s ({len(audio_bytes)} bytes)")
                            break
                elif resp.status_code == 429:
                    print_warning(f"   ⚡ Gemini TTS model '{model}' rate/quota limited (HTTP 429). Switching to alternate model...")
                    last_error = f"Model {model} 429: {resp.text[:120]}"
                else:
                    print_warning(f"   ⚠️ Gemini TTS model '{model}' returned HTTP {resp.status_code}: {resp.text[:150]}")
                    last_error = f"HTTP {resp.status_code}: {resp.text[:120]}"
            except Exception as net_err:
                last_error = net_err
                print_warning(f"   ⚠️ Gemini TTS HTTP call failed for '{model}': {net_err}")

        # Attempt 2: SDK Client Fallback if direct HTTP didn't produce audio
        if not audio_bytes:
            for model in candidate_models:
                try:
                    client = genai.Client(api_key=self.api_key)
                    response = client.interactions.create(
                        model=model,
                        input=[{"type": "user_input", "content": [{"type": "text", "text": clean_text}]}],
                        response_format={"type": "audio"},
                        generation_config={"speech_config": [{"voice": resolved_voice}]},
                    )
                    if hasattr(response, "output_audio") and response.output_audio and hasattr(response.output_audio, "data"):
                        raw_data = response.output_audio.data
                        if raw_data:
                            audio_bytes = base64.b64decode(raw_data)
                            if audio_bytes and len(audio_bytes) > 500:
                                print_success(f"   ✨ Gemini TTS SDK fallback ({model}) succeeded ({len(audio_bytes)} bytes)")
                                break
                except Exception as sdk_err:
                    last_error = sdk_err
                    print_warning(f"   ⚠️ Gemini TTS SDK attempt failed for '{model}': {sdk_err}")

        # Graceful fallback: If Gemini TTS is busy, blocked by safety filter, or unavailable,
        # fallback to Edge-TTS instead of crashing the pipeline!
        if not audio_bytes:
            print_warning(
                f"⚠️ Gemini Flash TTS unavailable ({last_error or 'empty response'}). "
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

        # Transcode cleanly: Google returns a valid 24kHz WAV file (starts with 'RIFF')
        temp_wav = output_audio_path.with_suffix(".temp.wav")
        temp_wav.write_bytes(audio_bytes)

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
        print_success(f"✅ OpenMontage Gemini TTS audio ready ({duration:.2f}s): {output_audio_path.name}")

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


# Export alias so `from autotube.voice.gemini_tts import GeminiTTS` works everywhere
GeminiTTS = GeminiTTSEngine
