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
            calm_alien_track = self.assets_dir / "alien" / "roswell_mystery_calm.mp3"
            if calm_alien_track.exists():
                print_info(f"Selected Calm & Mysterious Ambient BGM: {calm_alien_track.name}")
                return calm_alien_track
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
        cut_timestamps: Optional[List[float]] = None,
    ) -> Path:
        """Mix speech voiceover with background music, hook SFX, and micro-transition cut whooshes."""
        import random

        # Calm, subtle, mysterious volume (0.12)
        volume = music_volume if music_volume is not None else (self.music_volume or 0.12)

        # If explicit 'none', skip BGM. Otherwise if no music specified, pick subject-matched BGM
        if str(music_path).lower() == "none" or (isinstance(music_path, Path) and music_path.name.lower() == "none"):
            music_path = None
        elif not music_path:
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

        # Voice clarity filter for crisp archival broadcast
        voice_filter = (
            "equalizer=f=80:width_type=o:width=1.5:g=3,"
            "equalizer=f=3000:width_type=o:width=1.2:g=2"
        )

        # Lowpass at 3500Hz removes high harsh frequencies, creating a warm, calm, mysterious ambient atmosphere
        bgm_filter = (
            f"aloop=loop=-1:size=2e+09,lowpass=f=3500,volume={volume},"
            f"afade=t=in:st=0:d=1.5,afade=t=out:st={fade_out_start:.2f}:d=2.0"
        )

        # Dynamic inputs & filter chain supporting Voice + BGM + Hook Whoosh + Micro-Cut Whooshes + Outro Bell Ding
        bell_sfx = self.get_sfx_path("youtube_bell_ding.wav")
        bell_delay_ms = max(0, int((duration - 4.2) * 1000)) if duration >= 8.0 else None

        inputs = ["-i", str(voice_path)]
        filter_parts = [f"[0:a]{voice_filter}[voice]"]
        mix_inputs = ["[voice]"]

        if music_path and music_path.exists():
            if music_path.is_dir():
                sub_files = [f for f in music_path.rglob("*.mp3") if f.is_file()] + [f for f in music_path.rglob("*.wav") if f.is_file()]
                music_path = sub_files[0] if sub_files else None

        if music_path and music_path.is_file():
            inputs.extend(["-i", str(music_path)])
            music_idx = (len(inputs) // 2) - 1
            filter_parts.append(f"[{music_idx}:a]{bgm_filter}[bg]")
            mix_inputs.append("[bg]")

        if whoosh_sfx and whoosh_sfx.exists():
            inputs.extend(["-i", str(whoosh_sfx)])
            whoosh_idx = (len(inputs) // 2) - 1
            filter_parts.append(f"[{whoosh_idx}:a]volume=0.15[sfx]")
            mix_inputs.append("[sfx]")

        # Micro SFX on scene cuts (Dopamine Reset every 4-6 seconds)
        valid_cuts = [t for t in (cut_timestamps or []) if 2.5 < t < (duration - 4.5)]
        if whoosh_sfx and whoosh_sfx.exists() and valid_cuts:
            inputs.extend(["-i", str(whoosh_sfx)])
            cut_whoosh_idx = (len(inputs) // 2) - 1
            n_cuts = min(12, len(valid_cuts))  # Cap at 12 cuts for clean audio mix
            selected_cuts = valid_cuts[:n_cuts]
            split_tags = "".join(f"[cw_{i}]" for i in range(n_cuts))
            filter_parts.append(f"[{cut_whoosh_idx}:a]asplit={n_cuts}{split_tags}")
            for i, ts in enumerate(selected_cuts):
                delay_ms = int(ts * 1000)
                filter_parts.append(f"[cw_{i}]adelay={delay_ms}|{delay_ms},volume=0.12[cut_sfx_{i}]")
                mix_inputs.append(f"[cut_sfx_{i}]")

        if bell_sfx and bell_sfx.exists() and bell_delay_ms is not None:
            inputs.extend(["-i", str(bell_sfx)])
            bell_idx = (len(inputs) // 2) - 1
            filter_parts.append(f"[{bell_idx}:a]adelay={bell_delay_ms}|{bell_delay_ms},volume=0.35[bell]")
            mix_inputs.append("[bell]")

        num_inputs = len(mix_inputs)
        if num_inputs == 1:
            return voice_path

        filter_parts.append(f"{''.join(mix_inputs)}amix=inputs={num_inputs}:duration=first:dropout_transition=2:normalize=0[mix]")
        filter_parts.append("[mix]loudnorm=I=-14:TP=-1.0:LRA=7[out]")

        filter_complex = ";".join(filter_parts)
        args = inputs + [
            "-filter_complex",
            filter_complex,
            "-map",
            "[out]",
            "-c:a",
            codec,
            "-b:a",
            "192k",
            "-t",
            f"{duration:.2f}",
            str(output_mixed_path),
        ]

        track_name = music_path.name if music_path else "none"
        success = run_ffmpeg(
            args,
            desc=f"Mixing voice with BGM [{track_name}] & Hook SFX",
        )
        if success and output_mixed_path.exists():
            return output_mixed_path

        return voice_path
