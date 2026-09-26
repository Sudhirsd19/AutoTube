"""Long-form YouTube Video Builder (16:9 Widescreen Compositor)."""

from pathlib import Path
from typing import List, Optional
from autotube.config import get_config
from autotube.scripting.models import LongVideoScript, Scene
from autotube.utils.console import print_error, print_info, print_success
from autotube.utils.ffmpeg_helper import get_media_duration, run_ffmpeg
from autotube.video.subtitle_burner import burn_subtitles


class LongformBuilder:
    """Builds 1920x1080 widescreen YouTube videos from multi-scene scripts."""

    def __init__(self):
        self.cfg = get_config()
        self.width = self.cfg.video.longform.width
        self.height = self.cfg.video.longform.height
        self.fps = self.cfg.video.longform.fps

    def build_video(
        self,
        audio_path: Path,
        scene_visuals: List[Path],
        output_path: Path,
        subtitles_file: Optional[Path] = None,
    ) -> Optional[Path]:
        """Combine multiple scene visuals with narration audio and subtitles."""
        output_path.parent.mkdir(parents=True, exist_ok=True)
        temp_dir = self.cfg.paths.temp_dir
        temp_dir.mkdir(parents=True, exist_ok=True)

        total_duration = get_media_duration(audio_path)
        if total_duration <= 0:
            print_error("Audio duration could not be determined.")
            return None

        if not scene_visuals:
            print_error("No scene visuals provided for long-form video.")
            return None

        # Calculate duration per scene visual
        num_scenes = len(scene_visuals)
        duration_per_scene = total_duration / num_scenes

        # Render each scene clip to a standard 1920x1080 30fps clip
        rendered_clips: List[Path] = []
        for idx, visual in enumerate(scene_visuals):
            clip_path = temp_dir / f"scene_clip_{idx:03d}.mp4"
            rendered_clips.append(clip_path)

            if visual.suffix.lower() in [".jpg", ".jpeg", ".png", ".webp"]:
                vf = (
                    f"scale={self.width}:{self.height}:force_original_aspect_ratio=increase,"
                    f"crop={self.width}:{self.height},format=yuv420p"
                )
                args = [
                    "-loop",
                    "1",
                    "-i",
                    str(visual),
                    "-t",
                    f"{duration_per_scene:.2f}",
                    "-vf",
                    vf,
                    "-c:v",
                    "libx264",
                    "-preset",
                    "veryfast",
                    "-an",
                    str(clip_path),
                ]
            else:
                # Video clip: loop or trim to duration_per_scene
                vf = (
                    f"scale={self.width}:{self.height}:force_original_aspect_ratio=increase,"
                    f"crop={self.width}:{self.height},format=yuv420p"
                )
                args = [
                    "-stream_loop",
                    "-1",
                    "-i",
                    str(visual),
                    "-t",
                    f"{duration_per_scene:.2f}",
                    "-vf",
                    vf,
                    "-c:v",
                    "libx264",
                    "-preset",
                    "fast",
                    "-an",
                    str(clip_path),
                ]

            run_ffmpeg(args, desc=f"Rendering scene {idx+1}/{num_scenes}")

        # Concatenate scene clips
        concat_txt = temp_dir / "concat_list.txt"
        with open(concat_txt, "w", encoding="utf-8") as f:
            for c in rendered_clips:
                f.write(f"file '{c.resolve().as_posix()}'\n")

        raw_stitched_video = temp_dir / f"stitched_{output_path.stem}.mp4"
        concat_args = [
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(concat_txt),
            "-i",
            str(audio_path),
            "-c:v",
            "copy",
            "-c:a",
            "aac",
            "-b:a",
            "192k",
            "-shortest",
            str(raw_stitched_video),
        ]
        concat_success = run_ffmpeg(
            concat_args, desc="Stitching scenes and syncing master audio"
        )
        if not concat_success or not raw_stitched_video.exists():
            print_error("Failed to stitch scene clips.")
            return None

        # Burn subtitles if provided
        if subtitles_file and subtitles_file.exists():
            print_info(f"Burning subtitles: {subtitles_file.name}")
            burn_success = burn_subtitles(
                input_video=raw_stitched_video,
                subtitles_file=subtitles_file,
                output_video=output_path,
            )
            # Cleanup temp stitched
            try:
                raw_stitched_video.unlink()
                concat_txt.unlink()
                for c in rendered_clips:
                    c.unlink()
            except Exception:
                pass

            if burn_success and output_path.exists():
                print_success(f"Final YouTube Video generated: {output_path.name}")
                return output_path

        # If no subtitles, move to output
        if raw_stitched_video.exists():
            if output_path.exists():
                output_path.unlink()
            raw_stitched_video.rename(output_path)
            try:
                concat_txt.unlink()
                for c in rendered_clips:
                    c.unlink()
            except Exception:
                pass
            print_success(f"Final YouTube Video generated: {output_path.name}")
            return output_path

        return None
