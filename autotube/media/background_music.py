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
        """List all audio tracks available in assets/audio."""
        if not self.assets_dir.exists():
            return []
        valid_exts = {".mp3", ".wav", ".aac", ".m4a", ".ogg"}
        return [p for p in self.assets_dir.iterdir() if p.suffix.lower() in valid_exts]

    def mix_voice_and_music(
        self,
        voice_path: Path,
        output_mixed_path: Path,
        music_path: Optional[Path] = None,
        music_volume: Optional[float] = None,
    ) -> Path:
        """Mix speech voiceover with background music, ducking music volume."""
        volume = music_volume if music_volume is not None else self.music_volume

        # If no music specified, pick from assets
        if not music_path:
            tracks = self.get_music_tracks()
            if tracks:
                music_path = tracks[0]

        # If still no music available, copy voice directly
        if not music_path or not music_path.exists():
            return voice_path

        duration = get_media_duration(voice_path)
        if duration <= 0:
            return voice_path

        # FFmpeg filter:
        # Loop music, apply volume reduction, mix with voiceover, fade out at end
        fade_out_start = max(0.0, duration - 1.5)
        filter_complex = (
            f"[1:a]aloop=loop=-1:size=2e+09,volume={volume},"
            f"afade=t=out:st={fade_out_start:.2f}:d=1.5[bg];"
            f"[0:a][bg]amix=inputs=2:duration=first:dropout_transition=2[out]"
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
            "aac",
            "-b:a",
            "192k",
            str(output_mixed_path),
        ]

        success = run_ffmpeg(args, desc="Mixing narration voice with background music")
        if success and output_mixed_path.exists():
            return output_mixed_path

        return voice_path
