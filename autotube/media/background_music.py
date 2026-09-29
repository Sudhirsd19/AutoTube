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

    def get_music_tracks(self) -> List[Path]:
        """List all audio tracks available in assets/audio (excluding SFX)."""
        if not self.assets_dir.exists():
            return []
        valid_exts = {".mp3", ".wav", ".aac", ".m4a", ".ogg"}
        # Filter out short SFX from regular BGM tracks
        return [
            p
            for p in self.assets_dir.iterdir()
            if p.suffix.lower() in valid_exts and not p.name.startswith("whoosh")
        ]

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
    ) -> Path:
        """Mix speech voiceover with background music and hook SFX with dynamic audio ducking."""
        import random

        volume = music_volume if music_volume is not None else self.music_volume

        # If no music specified, pick from assets
        if not music_path:
            tracks = self.get_music_tracks()
            if tracks:
                music_path = random.choice(tracks)

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

        # Voice enhancement filter: deep bass boost + crisp presence + subtle cinematic trailer echo
        voice_filter = "bass=g=6:f=115,treble=g=2:f=3500,aecho=0.8:0.88:45|70:0.22|0.12"

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
