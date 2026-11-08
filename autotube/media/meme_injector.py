"""Meme Injector Module for Viral Comedy Shorts.

Automatically splices iconic viral laughing memes (Akshay Kumar laugh, Rajpal
Yadav reaction, Babu Rao, etc.) or laugh sound effects into comedy shorts at the
punchline beat (~70% mark of the video) to maximize retention, viral engagement,
and comment sections.
"""

import os
import random
import subprocess
import time
from pathlib import Path
from typing import List, Optional, Tuple

from autotube.utils.console import print_error, print_info, print_success, print_warning
from autotube.utils.ffmpeg_helper import get_ffmpeg_path, get_media_duration


class MemeInjector:
    """Injects punchline memes and laugh reactions into short videos."""

    def __init__(self, memes_root: Optional[Path] = None):
        if memes_root is None:
            # Default to assets/memes relative to project root or current directory
            project_root = Path(__file__).resolve().parent.parent.parent
            self.memes_root = project_root / "assets" / "memes"
        else:
            self.memes_root = Path(memes_root)

        self.video_dir = self.memes_root / "video"
        self.audio_dir = self.memes_root / "audio"
        self.video_dir.mkdir(parents=True, exist_ok=True)
        self.audio_dir.mkdir(parents=True, exist_ok=True)

    def get_available_video_memes(self) -> List[Path]:
        """Return list of available video meme clips (.mp4)."""
        if not self.video_dir.exists():
            return []
        return [
            f for f in self.video_dir.glob("*.mp4")
            if f.is_file() and f.stat().st_size > 50000
        ]

    def get_available_audio_memes(self) -> List[Path]:
        """Return list of available audio meme sound effects (.mp3, .wav)."""
        if not self.audio_dir.exists():
            return []
        return [
            f for f in self.audio_dir.glob("*.*")
            if f.is_file() and f.suffix.lower() in {".mp3", ".wav", ".aac"} and f.stat().st_size > 10000
        ]

    def inject_meme(
        self,
        video_path: Path,
        output_path: Path,
        style: str = "cut",
        punchline_ratio: float = 0.70,
        preferred_meme: Optional[str] = None
    ) -> Path:
        """Inject a viral laughing meme into the video.

        Args:
            video_path: Input short video path.
            output_path: Destination path for meme-injected short video.
            style: 'cut' (1.8s video reaction cut inserted at punchline),
                   'audio_sfx' (laugh audio track mixed at punchline without cutting video).
            punchline_ratio: Fraction of video duration where punchline lands (0.60 to 0.85).
            preferred_meme: Optional specific meme name (e.g. 'akshay_laugh', 'rajpal_reaction').

        Returns:
            output_path if successfully transformed, or original video_path on failure/skip.
        """
        video_path = Path(video_path)
        output_path = Path(output_path)

        if not video_path.exists() or video_path.stat().st_size < 50000:
            print_warning(f"MemeInjector: Source video invalid or missing: {video_path}")
            return video_path

        total_dur = get_media_duration(video_path)
        if total_dur < 6.0:
            print_info("MemeInjector: Video too short (<6s) for meme insertion. Skipping.")
            return video_path

        # Determine cut time
        cut_time = round(max(2.5, min(total_dur - 2.5, total_dur * punchline_ratio)), 2)

        if style == "audio_sfx":
            return self._inject_audio_laugh(
                video_path=video_path,
                output_path=output_path,
                cut_time=cut_time,
                preferred_meme=preferred_meme
            )
        else:
            return self._inject_video_cut(
                video_path=video_path,
                output_path=output_path,
                cut_time=cut_time,
                preferred_meme=preferred_meme
            )

    def _inject_video_cut(
        self,
        video_path: Path,
        output_path: Path,
        cut_time: float,
        preferred_meme: Optional[str] = None
    ) -> Path:
        """Splice a 1.5-2.0s laughing reaction meme cut into the video at cut_time."""
        memes = self.get_available_video_memes()
        if not memes:
            print_warning("MemeInjector: No video memes found in assets/memes/video. Checking audio...")
            return self._inject_audio_laugh(video_path, output_path, cut_time, preferred_meme)

        # Select meme
        chosen_meme: Optional[Path] = None
        if preferred_meme:
            for m in memes:
                if preferred_meme.lower() in m.stem.lower():
                    chosen_meme = m
                    break

        if not chosen_meme:
            chosen_meme = random.choice(memes)

        print_info(f"😂 [Meme Injector] Splicing viral meme '{chosen_meme.stem}' at {cut_time}s beat...")
        ffmpeg_exe = get_ffmpeg_path()
        output_path.parent.mkdir(parents=True, exist_ok=True)

        # Build FFmpeg filtergraph:
        # Input 0: Main Video
        # Input 1: Meme Video (Already 1080x1920 30fps)
        # 1. Trim 0..cut_time from Input 0 -> [v1][a1]
        # 2. Input 1 -> [vm][am] (scaled and resampled just in case)
        # 3. Trim cut_time..end from Input 0 -> [v2][a2]
        # 4. Concat [v1][a1][vm][am][v2][a2] -> [outv][outa]

        filtergraph = (
            f"[0:v]trim=start=0:end={cut_time},setpts=PTS-STARTPTS,setsar=1[v1];"
            f"[0:a]atrim=start=0:end={cut_time},asetpts=PTS-STARTPTS[a1];"
            f"[1:v]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,fps=30,setpts=PTS-STARTPTS,setsar=1[vm];"
            f"[1:a]aformat=sample_rates=44100:channel_layouts=stereo,asetpts=PTS-STARTPTS[am];"
            f"[0:v]trim=start={cut_time},setpts=PTS-STARTPTS,setsar=1[v2];"
            f"[0:a]atrim=start={cut_time},asetpts=PTS-STARTPTS[a2];"
            f"[v1][a1][vm][am][v2][a2]concat=n=3:v=1:a=1[outv][outa]"
        )

        cmd = [
            ffmpeg_exe, "-y",
            "-i", str(video_path),
            "-i", str(chosen_meme),
            "-filter_complex", filtergraph,
            "-map", "[outv]",
            "-map", "[outa]",
            "-c:v", "libx264",
            "-preset", "veryfast",
            "-crf", "22",
            "-c:a", "aac",
            "-b:a", "192k",
            "-movflags", "+faststart",
            str(output_path)
        ]

        try:
            start_t = time.time()
            res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=120)
            elapsed = time.time() - start_t

            if output_path.exists() and output_path.stat().st_size > 50000:
                print_success(
                    f"✅ [Meme Injected Successfully] Injected '{chosen_meme.stem}' in {elapsed:.1f}s -> {output_path.name}"
                )
                return output_path
            else:
                err_msg = res.stderr.decode("utf-8", errors="ignore")[-400:]
                print_error(f"FFmpeg failed to inject meme cut: {err_msg}")
        except Exception as exc:
            print_error(f"Exception during meme cut injection: {exc}")

        # Fallback to original
        return video_path

    def _inject_audio_laugh(
        self,
        video_path: Path,
        output_path: Path,
        cut_time: float,
        preferred_meme: Optional[str] = None
    ) -> Path:
        """Overlay a funny laugh track sound effect at cut_time without cutting the video."""
        audio_memes = self.get_available_audio_memes()
        if not audio_memes:
            print_warning("MemeInjector: No audio memes available. Returning original video.")
            return video_path

        chosen_audio: Optional[Path] = None
        if preferred_meme:
            for a in audio_memes:
                if preferred_meme.lower() in a.stem.lower():
                    chosen_audio = a
                    break

        if not chosen_audio:
            chosen_audio = random.choice(audio_memes)

        print_info(f"🔊 [Meme Injector] Layering laugh SFX '{chosen_audio.stem}' at {cut_time}s...")
        ffmpeg_exe = get_ffmpeg_path()
        output_path.parent.mkdir(parents=True, exist_ok=True)

        delay_ms = int(cut_time * 1000)
        filtergraph = (
            f"[1:a]adelay={delay_ms}|{delay_ms},volume=1.3[laugh];"
            f"[0:a][laugh]amix=inputs=2:duration=first:dropout_transition=2[outa]"
        )

        cmd = [
            ffmpeg_exe, "-y",
            "-i", str(video_path),
            "-i", str(chosen_audio),
            "-filter_complex", filtergraph,
            "-map", "0:v",
            "-map", "[outa]",
            "-c:v", "copy",
            "-c:a", "aac",
            "-b:a", "192k",
            "-movflags", "+faststart",
            str(output_path)
        ]

        try:
            res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=60)
            if output_path.exists() and output_path.stat().st_size > 50000:
                print_success(f"✅ [Laugh SFX Layered] Added '{chosen_audio.stem}' -> {output_path.name}")
                return output_path
            else:
                print_error(f"FFmpeg laugh SFX failed: {res.stderr.decode()[:300]}")
        except Exception as exc:
            print_error(f"Exception during laugh SFX injection: {exc}")

        return video_path
