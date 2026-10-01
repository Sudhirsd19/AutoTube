"""Background music manager and audio mixer."""

import os
from pathlib import Path
from typing import List, Optional
from autotube.config import get_config
from autotube.utils.console import print_info, print_warning
from autotube.utils.ffmpeg_helper import get_media_duration, run_ffmpeg


class BackgroundMusicManager:
    """Manages background music tracks and mixes them with narration."""

    def __init__(self, assets_dir: Optional[Path] = None):
        cfg = get_config()
        self.assets_dir = assets_dir or (cfg.paths.assets_dir / "audio")
        self.music_volume = cfg.media.background_music_volume

    def get_music_tracks(self, category: Optional[str] = None) -> List[Path]:
        """List all audio tracks available in assets/audio (optionally filtered by subject category)."""
        if not self.assets_dir.exists():
            return []
        valid_exts = {".mp3", ".wav", ".aac", ".m4a", ".ogg"}

        # If category specified, look in that subfolder first
        if category:
            cat_dir = self.assets_dir / category.lower().strip()
            if cat_dir.exists():
                cat_tracks = [p for p in cat_dir.iterdir() if p.suffix.lower() in valid_exts]
                if cat_tracks:
                    return cat_tracks

        # Search recursively in all subdirectories of assets/audio
        all_tracks = []
        for p in self.assets_dir.rglob("*"):
            if p.is_file() and p.suffix.lower() in valid_exts and not p.name.startswith("whoosh"):
                all_tracks.append(p)
        return all_tracks

    def get_music_for_subject(self, niche: Optional[str] = None, topic: Optional[str] = None) -> Optional[Path]:
        """Select a high-quality, Hollywood-grade BGM track matched directly to the video's subject."""
        import random
        text = f"{niche or ''} {topic or ''}".lower()

        cat = "mystery"
        if any(w in text for w in ("alien", "roswell", "airl", "ufo", "domain", "extraterrestrial")):
            cat = "alien"
        elif any(w in text for w in ("space", "galaxy", "universe", "black hole", "cosmos", "stars", "planet")):
            cat = "space"
        elif any(w in text for w in ("history", "bharat", "king", "emperor", "war", "battle", "empire", "ancient rome")):
            cat = "history"
        elif any(w in text for w in ("psychology", "manipulation", "mind", "subconscious", "brain", "trick")):
            cat = "psychology"
        elif any(w in text for w in ("mystery", "sphinx", "pyramid", "tomb", "atlantis", "anomal")):
            cat = "mystery"

        tracks = self.get_music_tracks(category=cat)
        if tracks:
            chosen = random.choice(tracks)
            print_info(f"Selected subject-matched BGM ({cat}): {chosen.name}")
            return chosen

        # Fallback to any available track
        all_tracks = self.get_music_tracks()
        return random.choice(all_tracks) if all_tracks else None

    def get_sfx_path(self, sfx_name: str = "whoosh_hit.wav") -> Optional[Path]:
        """Get path to a specific sound effect in assets/audio."""
        sfx_file = self.assets_dir / sfx_name
        return sfx_file if sfx_file.exists() else None

    def mix_voice_and_music(
        self,
        voice_path: Path,
        output_mixed_path: Path,
        music_path: Optional[Path] = None,
        music_volume: Optional[float] = None,
        include_whoosh: bool = True,
        niche: Optional[str] = None,
        topic: Optional[str] = None,
    ) -> Path:
        """Mix speech voiceover with background music and hook SFX with dynamic audio ducking and Thanos DSP."""
        import random

        volume = music_volume if music_volume is not None else (self.music_volume or 0.14)

        # If no music specified, pick subject-matched BGM
        if not music_path:
            music_path = self.get_music_for_subject(niche=niche, topic=topic)

        whoosh_sfx = self.get_sfx_path("whoosh_hit.wav") if include_whoosh else None

        # If neither music nor whoosh available, return voice directly
        if (not music_path or not music_path.exists()) and not whoosh_sfx:
            return voice_path

        duration = get_media_duration(voice_path)
        if duration <= 0:
            return voice_path

        output_mixed_path.parent.mkdir(parents=True, exist_ok=True)
        fade_out_start = max(0.0, duration - 1.5)

        codec = "libmp3lame" if output_mixed_path.suffix.lower() == ".mp3" else "aac"

        # Thanos Titan Resonance DSP: sub-bass weight (75Hz), chest resonance (150Hz), presence, and broadcast trailer compression
        voice_filter = (
            "equalizer=f=75:width_type=o:width=1.5:g=6,"
            "equalizer=f=150:width_type=o:width=1.2:g=5,"
            "equalizer=f=3200:width_type=o:width=1.2:g=2.5,"
            "compand=attacks=0.02:decays=0.2:points=-80/-80|-30/-18|-15/-8|0/-2:gain=3.5,"
            "loudnorm=I=-14:TP=-1.0:LRA=7"
        )

        if music_path and music_path.exists() and whoosh_sfx:
            # 3-input mix: heavy voice + audible bgm + opening whoosh SFX
            filter_complex = (
                f"[0:a]{voice_filter}[voice];"
                f"[1:a]aloop=loop=-1:size=2e+09,volume={volume},"
                f"afade=t=out:st={fade_out_start:.2f}:d=1.5[bg];"
                f"[2:a]volume=0.35[sfx];"
                f"[voice][bg][sfx]amix=inputs=3:duration=first:dropout_transition=2:normalize=0[out]"
            )
            args = [
                "-i",
                str(voice_path),
                "-i",
                str(music_path),
                "-i",
                str(whoosh_sfx),
                "-filter_complex",
                filter_complex,
                "-map",
                "[out]",
                "-c:a",
                codec,
                "-b:a",
                "192k",
                str(output_mixed_path),
            ]
        elif music_path and music_path.exists():
            # 2-input mix: heavy voice + audible bgm
            filter_complex = (
                f"[0:a]{voice_filter}[voice];"
                f"[1:a]aloop=loop=-1:size=2e+09,volume={volume},"
                f"afade=t=out:st={fade_out_start:.2f}:d=1.5[bg];"
                f"[voice][bg]amix=inputs=2:duration=first:dropout_transition=2:normalize=0[out]"
            )
            args = [
                "-i",
                str(voice_path),
                "-i",
                str(music_path),
                "-filter_complex",
                filter_complex,
                "-map",
                "[out]",
                "-c:a",
                codec,
                "-b:a",
                "192k",
                str(output_mixed_path),
            ]
        else:
            return voice_path

        track_name = music_path.name if music_path else "none"
        success = run_ffmpeg(
            args,
            desc=f"Mixing voice with BGM [{track_name}] & Hook SFX",
        )
        if success and output_mixed_path.exists():
            return output_mixed_path

        return voice_path
