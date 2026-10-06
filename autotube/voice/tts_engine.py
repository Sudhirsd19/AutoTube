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
from autotube.voice.voices import get_voice_id, get_voice_profile


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
    scene_durations: Optional[List[float]] = None


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
        width: int = 1080,
        height: int = 1920,
    ) -> TTSResult:
        """Synchronous wrapper to run async synthesis (safe inside running event loops)."""
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if loop and loop.is_running():
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as executor:
                future = executor.submit(
                    asyncio.run,
                    self.synthesize_async(
                        text=text,
                        output_audio_path=output_audio_path,
                        voice=voice,
                        rate=rate,
                        pitch=pitch,
                        width=width,
                        height=height,
                    )
                )
                return future.result()

        return asyncio.run(
            self.synthesize_async(
                text=text,
                output_audio_path=output_audio_path,
                voice=voice,
                rate=rate,
                pitch=pitch,
                width=width,
                height=height,
            )
        )

    async def synthesize_async(
        self,
        text: str,
        output_audio_path: Path,
        voice: Optional[str] = None,
        rate: Optional[str] = None,
        pitch: Optional[str] = None,
        width: int = 1080,
        height: int = 1920,
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

        profile = get_voice_profile(voice)
        selected_voice = profile.edge_voice_id if profile else (get_voice_id(voice) if voice else self.default_voice)
        is_akashvani = any(k in (voice or "").lower() for k in ("akashvani", "akashwani"))
        is_thanos = any(k in (voice or "").lower() for k in ("thanos", "warlord", "titan")) or any(k in selected_voice.lower() for k in ("roger", "thanos"))
        is_hindi = "hi-IN" in selected_voice or (voice and any(k in voice.lower() for k in ("hi", "hindi", "madhur", "swara", "akashvani")))

        if is_akashvani:
            selected_rate = rate or "-7%"
            selected_pitch = pitch or "-14Hz"
        elif is_thanos:
            selected_rate = rate or "-8%"
            selected_pitch = pitch or ("-25Hz" if is_hindi else "-22Hz")
        elif profile:
            # Use profile's tuned deep pitch and rate (default 0.90x-0.95x speed)
            selected_rate = rate or profile.rate
            selected_pitch = pitch or profile.pitch
        else:
            selected_rate = rate or (self.rate if self.rate != "+0%" else ("-8%" if is_hindi else "-8%"))
            selected_pitch = pitch or ("-10Hz" if is_hindi else self.pitch)

        output_audio_path.parent.mkdir(parents=True, exist_ok=True)
        print_info(f"Synthesizing voiceover with voice: '{selected_voice}' (Pitch: {selected_pitch}, Rate: {selected_rate})...")

        # Preprocess text for natural breathing pauses and cadence
        processed_text = self._preprocess_for_naturalness(text)

        submaker = edge_tts.SubMaker()
        total_audio_bytes = bytearray()
        raw_boundaries = []
        max_attempts = 3
        last_error = None
        succeeded = False

        for attempt in range(1, max_attempts + 1):
            try:
                curr_voice = selected_voice
                # On final attempt, fallback to bulletproof baseline voice if specialized voice had issues
                if attempt == max_attempts:
                    curr_voice = "hi-IN-MadhurNeural" if is_hindi else "en-US-ChristopherNeural"

                communicate = edge_tts.Communicate(
                    text=processed_text,
                    voice=curr_voice,
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

                if len(total_audio_bytes) < 500:
                    raise RuntimeError("Edge-TTS returned empty or truncated audio stream")

                succeeded = True
                break
            except Exception as e:
                last_error = e
                print_warning(f"Edge-TTS attempt {attempt}/{max_attempts} failed ({e}). Retrying in {attempt * 2}s...")
                await asyncio.sleep(attempt * 2)

        if not succeeded:
            raise RuntimeError(f"Edge-TTS failed after {max_attempts} attempts: {last_error}")

        with open(output_audio_path, "wb") as f:
            f.write(total_audio_bytes)

        # Apply Voice Acoustic Filter (Deep Bass, Cinematic Studio Equalizer, or Subtle Echo)
        audio_filter_to_apply = None
        if is_akashvani:
            audio_filter_to_apply = "aecho=0.85:0.75:100|220:0.35|0.2,equalizer=f=120:width_type=o:width=1.5:g=4,equalizer=f=3500:width_type=o:width=1.2:g=2"
        elif profile and profile.audio_filter:
            audio_filter_to_apply = profile.audio_filter

        if audio_filter_to_apply:
            temp_filtered = output_audio_path.with_name(f"fx_{output_audio_path.name}")
            from autotube.utils.ffmpeg_helper import run_ffmpeg
            ok = run_ffmpeg(["-i", str(output_audio_path), "-af", audio_filter_to_apply, str(temp_filtered)])
            if ok and temp_filtered.exists() and temp_filtered.stat().st_size > 1000:
                temp_filtered.replace(output_audio_path)

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

        self._export_karaoke_ass(words, ass_path, width=width, height=height)

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
        width: int = 1080,
        height: int = 1920,
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

        is_landscape = width > height
        res_x = 1920 if is_landscape else 1080
        res_y = 1080 if is_landscape else 1920
        font_size = 52 if is_landscape else 68
        margin_v = 110 if is_landscape else 780

        # Safe zone positioning: MarginV 780 for 9:16 Shorts, 110 for 16:9 Landscape Widescreen
        header = f"""[Script Info]
Title: AutoTube Animated Subtitles
ScriptType: v4.00+
WrapStyle: 0
ScaledBorderAndShadow: yes
YCbCr Matrix: None
PlayResX: {res_x}
PlayResY: {res_y}

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,{font_name},{font_size},&H00FFFFFF,&H0000FFFF,&H00000000,&H80000000,-1,0,0,0,100,100,0,0,1,6,3,2,60,60,{margin_v},1

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

    def synthesize_dialogue(
        self,
        scenes: List[Any],
        output_audio_path: Path,
        language: str = "en",
    ) -> TTSResult:
        """Synthesize real two-character dialogue interview (Nurse Matilda + Alien Airl)."""
        import subprocess
        import imageio_ffmpeg

        ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
        output_audio_path.parent.mkdir(parents=True, exist_ok=True)
        is_hindi = language.lower() in ("hi", "hindi")

        # Map speakers to character voices
        if is_hindi:
            voice_map = {
                "nurse": "swara",    # Female Nurse Matilda in Hindi
                "alien": "madhur",   # Alien Airl in Hindi (with telepathic resonance)
                "narrator": "madhur",  # Documentarian Narrator in Hindi (clean broadcast)
            }
        else:
            voice_map = {
                "nurse": "rachel",   # Female Nurse Matilda in English (JennyNeural)
                "alien": "daniel",   # Alien Airl in English (ChristopherNeural with telepathic resonance)
                "narrator": "guy",   # Documentarian Narrator in English (GuyNeural)
            }

        scene_audio_files = []
        scene_durations: List[float] = []
        all_words: List[TimedWord] = []
        scene_events_data = []
        current_time_offset = 0.0

        print_info(f"🎙️ Synthesizing Real Dialogue Interview ({len(scenes)} scenes, {'Hindi' if is_hindi else 'English'})...")

        for idx, scene in enumerate(scenes):
            speaker_raw = getattr(scene, "speaker", "").lower().strip()
            if "narrator" in speaker_raw:
                role = "narrator"
            elif "nurse" in speaker_raw or "matilda" in speaker_raw:
                role = "nurse"
            elif "alien" in speaker_raw or "airl" in speaker_raw:
                role = "alien"
            elif idx % 2 == 0:
                role = "nurse"
            else:
                role = "alien"

            chosen_voice = voice_map.get(role, voice_map.get("alien" if idx % 2 != 0 else "nurse"))
            scene_text = getattr(scene, "narration", "").strip()
            if not scene_text:
                continue

            scene_raw_path = output_audio_path.parent / f"dialogue_scene_{idx:02d}_{role}_raw.mp3"
            scene_final_path = output_audio_path.parent / f"dialogue_scene_{idx:02d}_{role}.mp3"

            print_info(f"  Scene {idx+1}/{len(scenes)} [{role.upper()}]: Speaking with voice '{chosen_voice}'...")
            res = self.synthesize(
                text=scene_text,
                output_audio_path=scene_raw_path,
                voice=chosen_voice,
            )

            # If Alien, apply telepathic mind-resonance filter
            if role == "alien":
                filter_str = "aecho=0.8:0.88:60:0.35,equalizer=f=3000:t=q:w=1:g=2"
                cmd = [
                    ffmpeg_exe, "-y", "-i", str(scene_raw_path),
                    "-af", filter_str,
                    str(scene_final_path),
                ]
                try:
                    subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
                except Exception:
                    scene_final_path = scene_raw_path
            else:
                if scene_final_path.exists():
                    scene_final_path.unlink()
                scene_raw_path.rename(scene_final_path)

            actual_duration = get_media_duration(scene_final_path)
            scene_durations.append(round(actual_duration, 2))

            # Adjust word timestamps to global timeline
            duration_ratio = (actual_duration / res.duration_seconds) if res.duration_seconds > 0 else 1.0
            scene_timed_words = []
            for w in res.words:
                w_start = current_time_offset + (w.start * duration_ratio)
                w_end = current_time_offset + (w.end * duration_ratio)
                tw = TimedWord(
                    word=w.word,
                    start=round(w_start, 3),
                    end=round(w_end, 3),
                    duration=round(w_end - w_start, 3),
                )
                all_words.append(tw)
                scene_timed_words.append(tw)

            scene_events_data.append((role, scene_timed_words))
            scene_audio_files.append(scene_final_path)
            current_time_offset += actual_duration

        # Concatenate scene audio files into single final audio
        concat_list_file = output_audio_path.parent / f"concat_{output_audio_path.stem}.txt"
        with open(concat_list_file, "w", encoding="utf-8") as f:
            for sf in scene_audio_files:
                f.write(f"file '{sf.resolve().as_posix()}'\n")

        cmd_concat = [
            ffmpeg_exe, "-y", "-f", "concat", "-safe", "0",
            "-i", str(concat_list_file),
            "-c:a", "libmp3lame", "-q:a", "2",
            str(output_audio_path),
        ]
        subprocess.run(cmd_concat, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)

        final_duration = get_media_duration(output_audio_path)

        # Export SRT and Dialogue-styled Karaoke ASS
        srt_path = output_audio_path.with_suffix(".srt")
        ass_path = output_audio_path.with_suffix(".ass")
        self._export_srt(all_words, srt_path)
        self._export_dialogue_karaoke_ass(scene_events_data, ass_path)

        # Clean up temporary scene audio slices
        for sf in scene_audio_files:
            try:
                sf.unlink(missing_ok=True)
            except Exception:
                pass
        concat_list_file.unlink(missing_ok=True)

        print_success(
            f"🎬 Real Dual-Voice Interview Audio Generated: {output_audio_path.name} ({final_duration:.2f}s, {len(all_words)} words across {len(scenes)} scenes)"
        )
        return TTSResult(
            audio_path=output_audio_path,
            subtitles_srt_path=srt_path,
            subtitles_ass_path=ass_path,
            words=all_words,
            duration_seconds=final_duration,
            scene_durations=scene_durations,
        )

    def _export_dialogue_karaoke_ass(
        self,
        scene_events_data: List[Any],
        ass_path: Path,
        words_per_line: int = 3,
    ) -> None:
        """Export Advanced SubStation Alpha (.ass) with character-specific styles:
        - Nurse: Crisp White with bright Gold/Cyan highlight
        - Alien: Eerie Neon Green with Cyan highlight
        """
        def format_ass_time(seconds: float) -> str:
            hours = int(seconds // 3600)
            minutes = int((seconds % 3600) // 60)
            secs = int(seconds % 60)
            centis = int(round((seconds - int(seconds)) * 100))
            if centis >= 100:
                centis = 99
            return f"{hours}:{minutes:02d}:{secs:02d}.{centis:02d}"

        # Check for Devanagari characters
        has_devanagari = False
        for _, words in scene_events_data:
            if any(any("\u0900" <= c <= "\u097f" for c in w.word) for w in words):
                has_devanagari = True
                break

        font_name = "Noto Sans Devanagari" if has_devanagari else "Arial"

        header = f"""[Script Info]
Title: AutoTube Alien Interview Animated Subtitles
ScriptType: v4.00+
WrapStyle: 0
ScaledBorderAndShadow: yes
YCbCr Matrix: None
PlayResX: 1080
PlayResY: 1920

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,{font_name},68,&H00FFFFFF,&H0000FFFF,&H00000000,&H80000000,-1,0,0,0,100,100,0,0,1,6,3,2,60,60,780,1
Style: Nurse,{font_name},68,&H00FFFFFF,&H00FFFF00,&H00000000,&H80000000,-1,0,0,0,100,100,0,0,1,6,3,2,60,60,780,1
Style: Alien,{font_name},68,&H0039FF14,&H0000FFFF,&H00000000,&H80000000,-1,0,0,0,100,100,0,0,1,6,3,2,60,60,780,1
Style: HUD_REC,Arial,34,&H00FFFFFF,&H000000FF,&H00000000,&H80000000,-1,0,0,0,100,100,0,0,1,3,2,7,50,50,80,1
Style: HUD_TOPSECRET,Arial,30,&H0000D7FF,&H000000FF,&H00000000,&H80000000,-1,0,0,0,100,100,0,0,1,3,2,9,50,50,82,1
Style: HUD_STAMP,Arial,46,&H000000FF,&H000000FF,&H00FFFFFF,&H90000000,-1,0,0,0,100,100,0,0,1,5,3,8,40,40,240,1
Style: HUD_NEXT,Arial,38,&H0000FFFF,&H0000FFFF,&H00000000,&H80000000,-1,0,0,0,100,100,0,0,1,4,2,2,40,40,1180,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
        events = []
        
        # Calculate total video duration for permanent HUD overlay
        all_ends = [w.end for _, words in scene_events_data for w in words]
        max_duration = max(all_ends) if all_ends else 70.0
        hud_end_str = format_ass_time(max_duration + 0.5)

        # 1. Permanent Leaked Military HUD (Top-Left REC timestamp & Top-Right Classified watermark)
        events.append(
            f"Dialogue: 1,0:00:00.00,{hud_end_str},HUD_REC,,0,0,0,,{{\\c&H0000FF&}}● {{\\c&HFFFFFF&}}REC  08-JUL-1947"
        )
        events.append(
            f"Dialogue: 1,0:00:00.00,{hud_end_str},HUD_TOPSECRET,,0,0,0,,[TOP SECRET // MAJESTIC-12]"
        )

        # 2. Instant Curiosity Hook: Opening Classified Stamp (First 2.5 seconds)
        events.append(
            f"Dialogue: 2,0:00:00.10,0:00:02.50,HUD_STAMP,,0,0,0,,[ RESTRICTED - EYES ONLY ]"
        )

        # 3. Next Part Teaser & Subscriber CTA (Final 4.5 seconds)
        cta_start = max(0.0, max_duration - 4.5)
        events.append(
            f"Dialogue: 2,{format_ass_time(cta_start)},{hud_end_str},HUD_NEXT,,0,0,0,,🔥 NEXT PART UNLOCKING SOON! SUBSCRIBE 👇"
        )

        # 4. Spoken Dialogue Lines (Dual-Styled Karaoke)
        for role, words in scene_events_data:
            if not words:
                continue
            style_name = "Alien" if role == "alien" else "Nurse"
            prefix = "[AIRL]: " if role == "alien" else "[MATILDA]: "

            for i in range(0, len(words), words_per_line):
                group = words[i : i + words_per_line]
                line_start = group[0].start
                line_end = group[-1].end + 0.1

                karaoke_text = ""
                if i == 0:
                    karaoke_text += f"{prefix}"

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
                    f"Dialogue: 0,{format_ass_time(line_start)},{format_ass_time(line_end)},{style_name},,0,0,0,,{karaoke_text.strip()}"
                )

        with open(ass_path, "w", encoding="utf-8") as f:
            f.write(header + "\n".join(events))


