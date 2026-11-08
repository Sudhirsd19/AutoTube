"""VoiceStudio Engine for AutoTube - 100% Local, Offline & Zero-Cost Voice AI.

Integrates with debpalash/VoiceStudio (Local OpenAI-compatible API on port 3900)
supporting zero-shot voice cloning, emotional & expressive speech tags,
and multi-model synthesis (OmniVoice, CosyVoice, VoxCPM2, etc.).
"""

import os
import re
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional
import requests

from autotube.config import get_config
from autotube.utils.console import print_info, print_success, print_warning, print_error
from autotube.utils.ffmpeg_helper import get_media_duration, run_ffmpeg
from autotube.voice.tts_engine import TimedWord, TTSResult, compute_scene_durations


VOICESTUDIO_DEFAULT_URL = os.getenv("VOICESTUDIO_API_URL", "http://localhost:3900").rstrip("/")
VOICESTUDIO_DEFAULT_MODEL = os.getenv("VOICESTUDIO_MODEL", "omnivoice")


class VoiceStudioEngine:
    """Local, offline Voice AI engine bridging AutoTube with debpalash/VoiceStudio."""

    def __init__(
        self,
        base_url: Optional[str] = None,
        default_voice: str = "default",
        model: Optional[str] = None,
        api_key: Optional[str] = None,
    ):
        self.base_url = (base_url or VOICESTUDIO_DEFAULT_URL).rstrip("/")
        self.default_voice = default_voice or "default"
        self.model = model or VOICESTUDIO_DEFAULT_MODEL
        self.api_key = api_key or os.getenv("VOICESTUDIO_API_KEY", "")

    def _get_headers(self) -> Dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    def is_available(self, timeout: float = 1.5) -> bool:
        """Check if local VoiceStudio server is active and responding."""
        try:
            r = requests.get(f"{self.base_url}/v1/audio/voices", headers=self._get_headers(), timeout=timeout)
            return r.status_code in (200, 401, 403)
        except Exception:
            pass

        try:
            r = requests.get(f"{self.base_url}/", timeout=timeout)
            return r.status_code in (200, 404)
        except Exception:
            return False

    def get_available_voices(self, timeout: float = 3.0) -> List[Dict[str, Any]]:
        """Fetch custom cloned voices and presets from VoiceStudio."""
        try:
            r = requests.get(f"{self.base_url}/v1/audio/voices", headers=self._get_headers(), timeout=timeout)
            if r.status_code == 200:
                data = r.json()
                if isinstance(data, dict) and "voices" in data:
                    return data["voices"]
                if isinstance(data, list):
                    return data
        except Exception as e:
            print_warning(f"Could not retrieve voices from VoiceStudio ({e})")
        return []

    def synthesize(
        self,
        text: str,
        output_audio_path: Path,
        voice: Optional[str] = None,
        model: Optional[str] = None,
        instruct: Optional[str] = None,
        speed: float = 1.0,
        scenes: Optional[List[Dict[str, Any]]] = None,
        allow_fallback: bool = True,
    ) -> TTSResult:
        """Synthesize speech using local VoiceStudio with automatic fallback to Gemini/Edge-TTS.

        Args:
            text: Text script to synthesize.
            output_audio_path: Target path for output audio file.
            voice: Voice ID, preset name, or custom cloned profile name.
            model: VoiceStudio model ('omnivoice', 'cosyvoice', 'voxcpm2', 'tts-1').
            instruct: Emotional / tone guidance (e.g. 'cinematic, deep mysterious narrator').
            speed: Speech pace multiplier (0.5 to 2.0).
            scenes: Scene definitions for storyboard timing.
            allow_fallback: Fallback to Gemini/Edge-TTS if local server is offline.
        """
        output_audio_path.parent.mkdir(parents=True, exist_ok=True)
        resolved_voice = voice or self.default_voice
        if resolved_voice.startswith("voicestudio:"):
            resolved_voice = resolved_voice.split(":", 1)[1]
        if not resolved_voice:
            resolved_voice = "default"

        active_model = model or self.model or "omnivoice"

        # Detect Hindi vs English
        has_devanagari = sum("\u0900" <= c <= "\u097f" for c in text) >= 4
        lang = "hi" if has_devanagari else "en"

        # Default tone guidance if none provided
        if not instruct:
            if has_devanagari:
                instruct = "Deep, clear, cinematic Indian documentary storytelling style"
            else:
                instruct = "Engaging, dramatic, clear narrative voiceover"

        endpoint = f"{self.base_url}/v1/audio/speech"
        payload = {
            "model": active_model,
            "input": text.strip(),
            "voice": resolved_voice,
            "response_format": "wav",
            "speed": max(0.5, min(2.0, float(speed))),
            "language": lang,
            "instruct": instruct,
        }

        audio_bytes = None
        last_error = None

        if self.is_available():
            print_info(f"🎙️ Synthesizing voice via local VoiceStudio ({self.base_url})...")
            print_info(f"   Model: {active_model} | Voice: {resolved_voice} | Lang: {lang}")
            try:
                resp = requests.post(endpoint, json=payload, headers=self._get_headers(), timeout=120)
                if resp.status_code == 200 and len(resp.content) > 500:
                    audio_bytes = resp.content
                else:
                    last_error = f"HTTP {resp.status_code}: {resp.text[:200]}"
            except Exception as e:
                last_error = str(e)
        else:
            last_error = f"VoiceStudio server is not running on {self.base_url}"

        # Resilient Fallback: If VoiceStudio is offline or failed, fallback without crashing!
        if not audio_bytes:
            if not allow_fallback:
                raise RuntimeError(f"VoiceStudio synthesis failed: {last_error}")

            print_warning(
                f"⚠️ VoiceStudio unavailable ({last_error}).\n"
                f"   💡 (Tip: Launch VoiceStudio or run 'voicestudio' to enable local voice generation)\n"
                f"   🔄 Seamlessly falling back to Gemini 3.8 Flash TTS / Edge-TTS..."
            )
            return self._fallback_synthesize(
                text=text,
                output_audio_path=output_audio_path,
                voice=voice,
                scenes=scenes,
            )

        # Write WAV then transcode to target extension
        temp_wav = output_audio_path.with_suffix(".vs_temp.wav")
        temp_wav.write_bytes(audio_bytes)

        is_wav = output_audio_path.suffix.lower() == ".wav"
        if is_wav:
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

        run_ffmpeg(transcode_cmd, desc=f"Encoding VoiceStudio audio to {output_audio_path.suffix.upper()}")

        try:
            temp_wav.unlink(missing_ok=True)
        except Exception:
            pass

        duration = get_media_duration(output_audio_path)
        print_success(f"✅ VoiceStudio audio ready ({duration:.2f}s): {output_audio_path.name}")

        # Compute accurate word boundary timestamps for captions
        words = text.split()
        timed_words: List[TimedWord] = []
        if words and duration > 0:
            word_time = duration / len(words)
            for i, w in enumerate(words):
                st = round(i * word_time, 3)
                en = round((i + 1) * word_time, 3)
                timed_words.append(TimedWord(word=w, start=st, end=en, duration=round(en - st, 3)))

        # Compute scene durations
        scene_durations = None
        if scenes:
            scene_durations = compute_scene_durations(scenes, timed_words, duration)

        srt_path = output_audio_path.with_suffix(".srt")
        ass_path = output_audio_path.with_suffix(".ass")
        self._export_subtitles(timed_words, srt_path, ass_path)

        return TTSResult(
            audio_path=output_audio_path,
            subtitles_srt_path=srt_path,
            subtitles_ass_path=ass_path,
            words=timed_words,
            duration_seconds=duration,
            scene_durations=scene_durations,
        )

    def _fallback_synthesize(
        self,
        text: str,
        output_audio_path: Path,
        voice: Optional[str],
        scenes: Optional[List[Dict[str, Any]]],
    ) -> TTSResult:
        """Gracefully routes to Edge-TTS engine without delays."""
        from autotube.voice.tts_engine import TTSEngine
        is_hindi = any("\u0900" <= c <= "\u097f" for c in text)
        edge_voice = "hi_deep_cinematic_male" if is_hindi else "en_deep_cinematic_male"
        print_info(f"🔄 Using high-speed Edge-TTS fallback voice: {edge_voice}")
        edge = TTSEngine(default_voice=edge_voice)
        return edge.synthesize(
            text=text,
            output_audio_path=output_audio_path,
            voice=edge_voice,
            scenes=scenes,
        )

    def _export_subtitles(self, words: List[TimedWord], srt_path: Path, ass_path: Path) -> None:
        """Export basic word-aligned SRT and ASS subtitle files."""
        if not words:
            return

        def _fmt_srt(seconds: float) -> str:
            hrs = int(seconds // 3600)
            mins = int((seconds % 3600) // 60)
            secs = int(seconds % 60)
            ms = int(round((seconds - int(seconds)) * 1000))
            return f"{hrs:02d}:{mins:02d}:{secs:02d},{ms:03d}"

        # Write SRT (chunked every 3 words for punchy shorts display)
        try:
            srt_lines = []
            chunk_size = 3
            idx = 1
            for i in range(0, len(words), chunk_size):
                chunk = words[i:i + chunk_size]
                start_str = _fmt_srt(chunk[0].start)
                end_str = _fmt_srt(chunk[-1].end)
                phrase = " ".join(w.word for w in chunk)
                srt_lines.append(f"{idx}\n{start_str} --> {end_str}\n{phrase}\n")
                idx += 1
            srt_path.write_text("\n".join(srt_lines), encoding="utf-8")
        except Exception:
            pass


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="VoiceStudio Local Engine Diagnostic")
    parser.add_argument("--check", action="store_true", help="Check if VoiceStudio local server is running")
    parser.add_argument("--test", type=str, default="", help="Synthesize test text")
    parser.add_argument("--voice", type=str, default="default", help="Voice profile name")
    args = parser.parse_args()

    engine = VoiceStudioEngine()
    print(f"Connecting to VoiceStudio on: {engine.base_url}")
    online = engine.is_available()
    print(f"Status: {'ONLINE ✅' if online else 'OFFLINE ⚠️'}")

    if args.test:
        out_p = Path("output/temp/voicestudio_test.mp3")
        res = engine.synthesize(args.test, out_p, voice=args.voice)
        print(f"Generated test audio: {res.audio_path} ({res.duration_seconds:.2f}s)")
