"""Text-to-speech engine using ElevenLabs with automatic Thanos Edge-TTS fallback."""

import asyncio
import base64
import json
from pathlib import Path
from typing import Any, Dict, List, Optional
import urllib.error
import urllib.request
import edge_tts
from pydantic import BaseModel
from autotube.utils.console import print_info, print_success, print_warning
from autotube.utils.ffmpeg_helper import get_media_duration
from autotube.voice.voices import get_voice_id


ELEVENLABS_VOICES: Dict[str, str] = {
    # Most Popular Viral Voices (YouTube Shorts, Reels, Documentaries)
    "adam": "pNInz6obpgDQGcFmaJgB",         # #1 Most Popular Voice on YouTube Shorts & TikTok (Smooth, viral narrator)
    "madhur": "pNInz6obpgDQGcFmaJgB",       # #1 Viral Hindi documentary narrator (Adam Multilingual v2)
    "antoni": "ErXwobaYiN019PkySvjV",       # Upbeat energetic storytelling
    "rachel": "21m00Tcm4TlvDq8ikWAM",       # #1 Most Popular Female Narrator
    "daniel": "onwK4e9ZLuTAKqWW03F9",       # Deep authoritative British broadcaster
    "christopher": "pNInz6obpgDQGcFmaJgB",  # Viral faceless channel narrator (mapped to Adam)
    "guy": "ErXwobaYiN019PkySvjV",          # Conversational storyteller (Antoni)
    "swara": "21m00Tcm4TlvDq8ikWAM",        # Expressive female
    "arnold": "VR6AewLTigWG4xSOukaG",       # Action / gruff voice
    "thanos": "VR6AewLTigWG4xSOukaG",       # Villain style
}


class TimedWord(BaseModel):
    word: str
    start: float  # in seconds
    end: float  # in seconds
    duration: float  # in seconds


class TTSResult(BaseModel):
    audio_path: Path
    subtitles_srt_path: Optional[Path] = None
    subtitles_ass_path: Optional[Path] = None
    words: List[TimedWord]
    duration_seconds: float


def compute_scene_durations(
    scenes: List[Any],
    words: List[TimedWord],
    total_duration: float,
) -> List[float]:
    """Calculate the precise spoken duration for each scene using word timestamps."""
    if not scenes:
        return [round(total_duration, 2)] if total_duration > 0 else [5.0]

    num_scenes = len(scenes)
    if num_scenes == 1:
        return [round(total_duration, 2)]

    scene_word_counts = []
    for s in scenes:
        narration = getattr(s, "narration", "") or ""
        count = len(narration.split())
        scene_word_counts.append(max(1, count))

    total_words = sum(scene_word_counts)
    if not words or len(words) < num_scenes:
        # Fallback to proportional duration based on word count
        proportions = [count / total_words for count in scene_word_counts]
        return [round(max(1.5, total_duration * p), 2) for p in proportions]

    durations: List[float] = []
    current_word_idx = 0
    prev_end_time = 0.0

    for idx, s in enumerate(scenes):
        if idx == num_scenes - 1:
            dur = max(1.5, total_duration - prev_end_time)
            durations.append(round(dur, 2))
            break

        w_count = scene_word_counts[idx]
        target_idx = min(len(words) - 1, current_word_idx + w_count - 1)
        end_time = words[target_idx].end
        dur = max(1.5, end_time - prev_end_time)
        durations.append(round(dur, 2))
        prev_end_time = end_time
        current_word_idx = target_idx + 1

    return durations


class TTSEngine:
    """Generates audio voiceover with word-level synchronization timestamps."""

    def __init__(
        self,
        default_voice: Optional[str] = None,
        rate: Optional[str] = None,
        pitch: Optional[str] = None,
    ):
        from autotube.config import get_config
        cfg = get_config()
        voice_key = default_voice or cfg.voice.default_voice
        self.default_voice = get_voice_id(voice_key)
        # For Hindi voices, default to brisk energetic pacing (+4%) for lively Shorts delivery
        is_hindi = "hi-IN" in self.default_voice or (voice_key and voice_key.lower() in ("madhur", "swara"))
        default_rate = "+4%" if is_hindi else (cfg.voice.rate or "+0%")
        self.rate = rate or default_rate
        self.pitch = pitch or cfg.voice.pitch or "+0Hz"
        self.elevenlabs_api_key = cfg.elevenlabs_api_key

    def _synthesize_elevenlabs(
        self,
        text: str,
        output_audio_path: Path,
        voice: Optional[str] = None,
        api_key: Optional[str] = None,
    ) -> TTSResult:
        """Synthesize voiceover using ElevenLabs API with character-level alignment."""
        has_devanagari = any("\u0900" <= c <= "\u097f" for c in text)
        v_key = (voice or "").lower().strip()

        if len(v_key) >= 18 and not (" " in v_key):
            voice_id = voice
        elif v_key in ELEVENLABS_VOICES:
            voice_id = ELEVENLABS_VOICES[v_key]
        elif has_devanagari or v_key in ("madhur", "swara", "hindi", "hi"):
            voice_id = "pNInz6obpgDQGcFmaJgB"  # Adam Multilingual v2 (Super natural viral Hindi narrator)
        else:
            voice_id = ELEVENLABS_VOICES.get(v_key, "pNInz6obpgDQGcFmaJgB")  # Default to Adam (#1 most used viral voice)

        print_info(f"Synthesizing ElevenLabs voiceover (Voice ID: {voice_id}, Model: eleven_multilingual_v2)...")

        url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}/with-timestamps"
        payload = json.dumps({
            "text": text,
            "model_id": "eleven_multilingual_v2",
            "voice_settings": {
                "stability": 0.50,
                "similarity_boost": 0.75,
                "style": 0.0,
                "use_speaker_boost": True,
            },
        }).encode("utf-8")

        req = urllib.request.Request(
            url,
            data=payload,
            headers={
                "xi-api-key": api_key,
                "Content-Type": "application/json",
            },
        )
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = json.loads(resp.read().decode("utf-8"))

        raw_audio = base64.b64decode(data["audio_base64"])
        output_audio_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_audio_path, "wb") as f:
            f.write(raw_audio)

        duration = get_media_duration(output_audio_path)

        align = data.get("alignment", {})
        chars = align.get("characters", [])
        starts = align.get("character_start_times_seconds", [])
        ends = align.get("character_end_times_seconds", [])

        words: List[TimedWord] = []
        current_word = []
        current_start = None
        current_end = None

        for c, s, e in zip(chars, starts, ends):
            if c.isspace():
                if current_word:
                    words.append(
                        TimedWord(
                            word="".join(current_word),
                            start=round(current_start, 3),
                            end=round(current_end, 3),
                            duration=round(current_end - current_start, 3),
                        )
                    )
                    current_word = []
                    current_start = None
                    current_end = None
            else:
                if current_start is None:
                    current_start = s
                current_end = e
                current_word.append(c)

        if current_word and current_start is not None and current_end is not None:
            words.append(
                TimedWord(
                    word="".join(current_word),
                    start=round(current_start, 3),
                    end=round(current_end, 3),
                    duration=round(current_end - current_start, 3),
                )
            )

        srt_path = output_audio_path.with_suffix(".srt")
        ass_path = output_audio_path.with_suffix(".ass")

        self._export_srt(words, srt_path)
        self._export_karaoke_ass(words, ass_path)

        print_success(
            f"ElevenLabs voiceover generated: {output_audio_path.name} ({duration:.2f}s, {len(words)} words, voice: {voice_id})"
        )
        return TTSResult(
            audio_path=output_audio_path,
            subtitles_srt_path=srt_path,
            subtitles_ass_path=ass_path,
            words=words,
            duration_seconds=duration,
        )

    @staticmethod
    def _preprocess_for_naturalness(text: str) -> str:
        """Add subtle punctuation and pauses to make TTS sound more human and less robotic.

        Edge-TTS Neural voices respond to punctuation for natural pacing:
        - Periods, purna viram (।), and commas create breathing pauses
        - Ellipsis (...) creates dramatic pauses
        - Question marks add rising intonation
        - Commas before conjunctions create natural human speech rhythm
        """
        import re
        if not text:
            return ""

        # Normalize dashes to micro-pauses
        text = text.replace(" - ", "... ")
        text = text.replace(" — ", "... ")

        # Ensure space after Devanagari purna viram (।) and punctuation
        text = re.sub(r'([।॥!?.,])(?=[^\s\d])', r'\1 ', text)

        # Conjunction words across English, Hindi (Devanagari), and Hinglish
        break_words = {
            # English
            'and', 'but', 'or', 'that', 'which', 'because', 'when', 'where', 'while', 'so', 'yet', 'then', 'however', 'although', 'actually', 'instead',
            # Hindi (Devanagari)
            'और', 'लेकिन', 'मगर', 'परंतु', 'क्योंकि', 'इसलिए', 'ताकि', 'बल्कि', 'हालांकि', 'जब', 'तब', 'जैसे', 'अगर', 'तो', 'जिसने', 'जिसका', 'जिसके', 'शायद', 'दरअसल',
            # Hinglish
            'aur', 'lekin', 'magar', 'kyunki', 'isliye', 'balki', 'jaise', 'agar', 'toh', 'shayad',
        }

        # Split into sentences considering English and Devanagari full stops
        sentences = re.split(r'(?<=[.!?।॥])\s+', text)
        processed = []
        for sentence in sentences:
            words = sentence.split()
            # If clause is long (>10 words), insert natural breathing commas before conjunctions
            if len(words) > 10:
                new_words = []
                words_since_pause = 0
                for w in words:
                    clean_w = w.lower().strip('.,!?।॥"\'')
                    if clean_w in break_words and words_since_pause >= 5:
                        # Add comma before conjunction if previous word didn't end with punctuation
                        if new_words and not any(new_words[-1].endswith(p) for p in (',', '.', '!', '?', '।', '॥', '...')):
                            new_words[-1] = new_words[-1] + ','
                        words_since_pause = 0
                    else:
                        words_since_pause += 1
                    new_words.append(w)
                sentence = ' '.join(new_words)
            processed.append(sentence)

        result = ' '.join(processed)
        # Clean up any duplicate commas or awkward spaces
        result = re.sub(r',\s*,+', ',', result)
        result = re.sub(r'\s+', ' ', result).strip()
        return result

    def synthesize(
        self,
        text: str,
        output_audio_path: Path,
        voice: Optional[str] = None,
        rate: Optional[str] = None,
        pitch: Optional[str] = None,
    ) -> TTSResult:
        """Synchronous wrapper to run async synthesis."""
        return asyncio.run(
            self.synthesize_async(
                text=text,
                output_audio_path=output_audio_path,
                voice=voice,
                rate=rate,
                pitch=pitch,
            )
        )

    async def synthesize_async(
        self,
        text: str,
        output_audio_path: Path,
        voice: Optional[str] = None,
        rate: Optional[str] = None,
        pitch: Optional[str] = None,
    ) -> TTSResult:
        """Synthesize text into speech and extract word & sentence boundaries."""
        # Tier 1: ElevenLabs Ultra-Realistic Synthesis (with character-level synchronization)
        if self.elevenlabs_api_key:
            try:
                return await asyncio.to_thread(
                    self._synthesize_elevenlabs,
                    text=text,
                    output_audio_path=output_audio_path,
                    voice=voice,
                    api_key=self.elevenlabs_api_key,
                )
            except Exception as e:
                print_warning(
                    f"ElevenLabs synthesis unavailable or quota reached ({e}). Falling back to Edge-TTS..."
                )

        selected_voice = get_voice_id(voice) if voice else self.default_voice
        is_thanos = any(k in (voice or "").lower() for k in ("thanos", "warlord", "titan")) or any(k in selected_voice.lower() for k in ("roger", "thanos"))
        is_hindi = "hi-IN" in selected_voice or (voice and voice.lower() in ("madhur", "swara", "thanos_hi", "thanos"))

        if is_thanos:
            selected_rate = rate or "-8%"
            selected_pitch = pitch or ("-25Hz" if is_hindi else "-22Hz")
        else:
            selected_rate = rate or (self.rate if self.rate != "+0%" else ("+4%" if is_hindi else "+0%"))
            selected_pitch = pitch or self.pitch

        output_audio_path.parent.mkdir(parents=True, exist_ok=True)
        print_info(f"Synthesizing voiceover with voice: '{selected_voice}' (Pitch: {selected_pitch}, Rate: {selected_rate})...")

        # Preprocess text for natural breathing pauses and cadence
        processed_text = self._preprocess_for_naturalness(text)

        communicate = edge_tts.Communicate(
            text=processed_text,
            voice=selected_voice,
            rate=selected_rate,
            pitch=selected_pitch,
        )

        submaker = edge_tts.SubMaker()
        total_audio_bytes = bytearray()
        raw_boundaries = []

        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                total_audio_bytes.extend(chunk["data"])
            elif chunk["type"] in ("WordBoundary", "SentenceBoundary"):
                submaker.feed(chunk)
                raw_boundaries.append(chunk)

        with open(output_audio_path, "wb") as f:
            f.write(total_audio_bytes)

        # Get authoritative duration using ffmpeg
        duration = get_media_duration(output_audio_path)

        # Convert boundaries to TimedWords
        words: List[TimedWord] = []
        for b in raw_boundaries:
            start_sec = b["offset"] / 10_000_000.0
            dur_sec = b["duration"] / 10_000_000.0
            b_text = b["text"].strip()

            if b["type"] == "WordBoundary":
                words.append(
                    TimedWord(
                        word=b_text,
                        start=round(start_sec, 3),
                        end=round(start_sec + dur_sec, 3),
                        duration=round(dur_sec, 3),
                    )
                )
            elif b["type"] == "SentenceBoundary":
                # Break sentence into words with proportional duration
                sentence_words = b_text.split()
                if not sentence_words:
                    continue
                total_chars = max(1, sum(len(w) for w in sentence_words))
                current_time = start_sec
                for w in sentence_words:
                    w_dur = dur_sec * (len(w) / total_chars)
                    words.append(
                        TimedWord(
                            word=w,
                            start=round(current_time, 3),
                            end=round(current_time + w_dur, 3),
                            duration=round(w_dur, 3),
                        )
                    )
                    current_time += w_dur

        # Export SRT and Karaoke ASS
        srt_path = output_audio_path.with_suffix(".srt")
        ass_path = output_audio_path.with_suffix(".ass")

        # Save SRT from SubMaker or words
        srt_content = submaker.get_srt()
        if srt_content.strip():
            with open(srt_path, "w", encoding="utf-8") as f:
                f.write(srt_content)
        else:
            self._export_srt(words, srt_path)

        self._export_karaoke_ass(words, ass_path)

        print_success(
            f"Voiceover generated: {output_audio_path.name} ({duration:.2f}s, {len(words)} words)"
        )
        return TTSResult(
            audio_path=output_audio_path,
            subtitles_srt_path=srt_path,
            subtitles_ass_path=ass_path,
            words=words,
            duration_seconds=duration,
        )

    def _export_srt(
        self, words: List[TimedWord], srt_path: Path, words_per_chunk: int = 4
    ) -> None:
        """Group words into small readable subtitle chunks and export as SRT."""
        if not words:
            return

        def format_time(seconds: float) -> str:
            hours = int(seconds // 3600)
            minutes = int((seconds % 3600) // 60)
            secs = int(seconds % 60)
            millis = int(round((seconds - int(seconds)) * 1000))
            return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"

        lines = []
        chunk_idx = 1
        for i in range(0, len(words), words_per_chunk):
            group = words[i : i + words_per_chunk]
            start_str = format_time(group[0].start)
            end_str = format_time(group[-1].end)
            text_str = " ".join(w.word for w in group)
            lines.append(f"{chunk_idx}\n{start_str} --> {end_str}\n{text_str}\n")
            chunk_idx += 1

        with open(srt_path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))

    def _export_karaoke_ass(
        self,
        words: List[TimedWord],
        ass_path: Path,
        words_per_line: int = 3,
    ) -> None:
        """Export Advanced SubStation Alpha (.ass) with viral Hormozi-style word-by-word karaoke highlighting."""
        if not words:
            return

        def format_ass_time(seconds: float) -> str:
            hours = int(seconds // 3600)
            minutes = int((seconds % 3600) // 60)
            secs = int(seconds % 60)
            centis = int(round((seconds - int(seconds)) * 100))
            if centis >= 100:
                centis = 99
            return f"{hours}:{minutes:02d}:{secs:02d}.{centis:02d}"

        # Check if words contain Devanagari (Hindi) characters
        has_devanagari = any(
            any("\u0900" <= c <= "\u097f" for c in w.word) for w in words
        )
        font_name = "Noto Sans Devanagari" if has_devanagari else "Arial"

        # Safe zone positioning: MarginV 780 ensures it is vertically centered above YouTube Shorts UI
        header = f"""[Script Info]
Title: AutoTube Animated Subtitles
ScriptType: v4.00+
WrapStyle: 0
ScaledBorderAndShadow: yes
YCbCr Matrix: None
PlayResX: 1080
PlayResY: 1920

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,{font_name},68,&H00FFFFFF,&H0000FFFF,&H00000000,&H80000000,-1,0,0,0,100,100,0,0,1,6,3,2,60,60,780,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
        events = []
        for i in range(0, len(words), words_per_line):
            group = words[i : i + words_per_line]
            line_start = group[0].start
            line_end = group[-1].end + 0.1

            karaoke_text = ""
            for w in group:
                duration_cs = max(1, int(round(w.duration * 100)))
                clean_word = (
                    w.word.replace("{", "")
                    .replace("}", "")
                    .strip()
                    .upper()
                )
                karaoke_text += f"{{\\k{duration_cs}}}{clean_word} "

            events.append(
                f"Dialogue: 0,{format_ass_time(line_start)},{format_ass_time(line_end)},Default,,0,0,0,,{karaoke_text.strip()}"
            )

        with open(ass_path, "w", encoding="utf-8") as f:
            f.write(header + "\n".join(events))

