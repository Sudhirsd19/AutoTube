"""Text-to-speech engine using Edge-TTS with word and sentence boundary extraction."""

import asyncio
from pathlib import Path
from typing import List, Optional
import edge_tts
from pydantic import BaseModel
from autotube.utils.console import print_info, print_success
from autotube.utils.ffmpeg_helper import get_media_duration
from autotube.voice.voices import get_voice_id


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


class TTSEngine:
    """Generates audio voiceover with word-level synchronization timestamps."""

    def __init__(
        self,
        default_voice: str = "en-US-ChristopherNeural",
        rate: str = "+0%",
        pitch: str = "+0Hz",
    ):
        self.default_voice = get_voice_id(default_voice)
        self.rate = rate
        self.pitch = pitch

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
        selected_voice = get_voice_id(voice) if voice else self.default_voice
        selected_rate = rate or self.rate
        selected_pitch = pitch or self.pitch

        output_audio_path.parent.mkdir(parents=True, exist_ok=True)
        print_info(f"Synthesizing voiceover with voice: '{selected_voice}'...")

        communicate = edge_tts.Communicate(
            text=text,
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
        words_per_line: int = 4,
    ) -> None:
        """Export Advanced SubStation Alpha (.ass) with word-by-word highlight karaoke style."""
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

        header = """[Script Info]
Title: AutoTube Animated Subtitles
ScriptType: v4.00+
WrapStyle: 0
ScaledBorderAndShadow: yes
YCbCr Matrix: None
PlayResX: 1080
PlayResY: 1920

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,Arial,62,&H00FFFFFF,&H0000FFFF,&H00000000,&H80000000,-1,0,0,0,100,100,0,0,1,5,2,2,40,40,320,1

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
                clean_word = w.word.replace("{", "").replace("}", "")
                karaoke_text += f"{{\\k{duration_cs}}}{clean_word} "

            events.append(
                f"Dialogue: 0,{format_ass_time(line_start)},{format_ass_time(line_end)},Default,,0,0,0,,{karaoke_text.strip()}"
            )

        with open(ass_path, "w", encoding="utf-8") as f:
            f.write(header + "\n".join(events))
