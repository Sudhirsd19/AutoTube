"""YouTube Shorts Video Builder (9:16 Vertical Video Compositor with Multi-Scene Support)."""

from pathlib import Path
from typing import List, Optional
from autotube.config import get_config
from autotube.utils.console import print_error, print_info, print_success
from autotube.utils.ffmpeg_helper import get_media_duration, run_ffmpeg
from autotube.video.subtitle_burner import burn_subtitles


class ShortsBuilder:
    """Builds 1080x1920 vertical YouTube Shorts with single or multi-scene dynamic motion."""

    def __init__(self):
        self.cfg = get_config()
        self.width = self.cfg.video.shorts.width
        self.height = self.cfg.video.shorts.height
        self.fps = self.cfg.video.shorts.fps

    def build_short(
        self,
        audio_path: Path,
        output_path: Path,
        background_video: Optional[Path] = None,
        background_image: Optional[Path] = None,
        scene_visuals: Optional[List[Path]] = None,
        scene_videos: Optional[List[Path]] = None,
        subtitles_file: Optional[Path] = None,
    ) -> Optional[Path]:
        """Compose audio, background visuals, and animated subtitles into a final Short."""
        output_path.parent.mkdir(parents=True, exist_ok=True)
        temp_dir = self.cfg.paths.temp_dir
        temp_dir.mkdir(parents=True, exist_ok=True)

        duration = get_media_duration(audio_path)
        if duration <= 0:
            print_error("Audio duration could not be determined.")
            return None

        raw_video_path = temp_dir / f"raw_{output_path.stem}.mp4"
        success = False

        # Fallback single scene video if only 1 passed
        if scene_videos and len(scene_videos) == 1 and not background_video:
            background_video = scene_videos[0]

        # Case 0: Multiple Dynamic Moving Video Scenes (Fast Cuts Every 3-5 seconds for maximum retention!)
        if scene_videos and len(scene_videos) > 1:
            print_info(f"Assembling {len(scene_videos)} dynamic moving video scenes with fast cuts...")
            num_scenes = len(scene_videos)
            dur_per_scene = duration / num_scenes
            rendered_clips: List[Path] = []

            for idx, vid_clip in enumerate(scene_videos):
                clip_path = temp_dir / f"vidscene_{output_path.stem}_{idx:02d}.mp4"
                rendered_clips.append(clip_path)

                vf = (
                    f"scale={self.width}:{self.height}:force_original_aspect_ratio=increase,"
                    f"crop={self.width}:{self.height},format=yuv420p"
                )
                args = [
                    "-stream_loop",
                    "-1",
                    "-i",
                    str(vid_clip),
                    "-t",
                    f"{dur_per_scene:.2f}",
                    "-vf",
                    vf,
                    "-c:v",
                    "libx264",
                    "-preset",
                    "veryfast",
                    "-an",
                    str(clip_path),
                ]
                run_ffmpeg(args, desc=f"Rendering video scene cut {idx+1}/{num_scenes}")

            # Stitch all scene clips together
            concat_txt = temp_dir / f"concat_{output_path.stem}.txt"
            with open(concat_txt, "w", encoding="utf-8") as f:
                for c in rendered_clips:
                    f.write(f"file '{c.resolve().as_posix()}'\n")

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
                str(raw_video_path),
            ]
            success = run_ffmpeg(
                concat_args, desc="Stitching multi-video sequence"
            )

        # Case 1: Multiple Dynamic Scene Visuals (Images with Camera Motion cuts!)
        elif scene_visuals and len(scene_visuals) > 1:
            print_info(f"Assembling {len(scene_visuals)} dynamic cartoon scenes with motion cuts...")
            num_scenes = len(scene_visuals)
            dur_per_scene = duration / num_scenes
            rendered_clips: List[Path] = []

            for idx, vis in enumerate(scene_visuals):
                clip_path = temp_dir / f"scene_{output_path.stem}_{idx:02d}.mp4"
                rendered_clips.append(clip_path)

                # Alternate camera motion between scenes
                if idx % 2 == 0:
                    zoom_expr = "min(zoom+0.0006,1.08)"
                else:
                    zoom_expr = "max(1.08-0.0006*on,1.0)"

                vf = (
                    f"scale=1200:2133:force_original_aspect_ratio=increase,"
                    f"crop=1200:2133,"
                    f"zoompan=z='{zoom_expr}':d=1:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s={self.width}x{self.height}:fps={self.fps},"
                    f"format=yuv420p"
                )
                args = [
                    "-loop",
                    "1",
                    "-i",
                    str(vis),
                    "-t",
                    f"{dur_per_scene:.2f}",
                    "-vf",
                    vf,
                    "-c:v",
                    "libx264",
                    "-preset",
                    "veryfast",
                    "-an",
                    str(clip_path),
                ]
                run_ffmpeg(args, desc=f"Rendering animated scene {idx+1}/{num_scenes}")

            # Stitch all scene clips together
            concat_txt = temp_dir / f"concat_{output_path.stem}.txt"
            with open(concat_txt, "w", encoding="utf-8") as f:
                for c in rendered_clips:
                    f.write(f"file '{c.resolve().as_posix()}'\n")

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
                str(raw_video_path),
            ]
            success = run_ffmpeg(
                concat_args, desc="Stitching multi-scene video sequence"
            )

        # Case 2: Video background provided
        elif background_video and background_video.exists():
            print_info(f"Using background video: {background_video.name}")
            vf = (
                f"scale={self.width}:{self.height}:force_original_aspect_ratio=increase,"
                f"crop={self.width}:{self.height},format=yuv420p"
            )
            args = [
                "-stream_loop",
                "-1",
                "-i",
                str(background_video),
                "-i",
                str(audio_path),
                "-t",
                f"{duration:.2f}",
                "-vf",
                vf,
                "-c:v",
                "libx264",
                "-preset",
                "veryfast",
                "-c:a",
                "aac",
                "-b:a",
                "192k",
                str(raw_video_path),
            ]
            success = run_ffmpeg(args, desc="Compositing background video with audio")

        # Case 3: Single Image background provided with subtle motion
        elif background_image and background_image.exists():
            print_info(f"Using background visual: {background_image.name}")
            vf = (
                f"scale=1200:2133:force_original_aspect_ratio=increase,"
                f"crop=1200:2133,"
                f"zoompan=z='min(zoom+0.0004,1.08)':d=1:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s={self.width}x{self.height}:fps={self.fps},"
                f"format=yuv420p"
            )
            args = [
                "-loop",
                "1",
                "-i",
                str(background_image),
                "-i",
                str(audio_path),
                "-t",
                f"{duration:.2f}",
                "-vf",
                vf,
                "-c:v",
                "libx264",
                "-preset",
                "veryfast",
                "-c:a",
                "aac",
                "-b:a",
                "192k",
                str(raw_video_path),
            ]
            success = run_ffmpeg(args, desc="Rendering vertical video base with camera motion")

        # Case 4: Fallback motion canvas
        else:
            print_info("No background provided, creating aesthetic motion canvas...")
            vf = (
                f"color=c=0x0f172a:s={self.width}x{self.height}:r={self.fps},"
                f"format=yuv420p"
            )
            args = [
                "-f",
                "lavfi",
                "-i",
                vf,
                "-i",
                str(audio_path),
                "-t",
                f"{duration:.2f}",
                "-c:v",
                "libx264",
                "-preset",
                "veryfast",
                "-c:a",
                "aac",
                "-b:a",
                "192k",
                str(raw_video_path),
            ]
            success = run_ffmpeg(args, desc="Generating motion backdrop")

        if not success or not raw_video_path.exists():
            print_error("Failed to generate raw video base.")
            return None

        # Burn subtitles if available
        if subtitles_file and subtitles_file.exists():
            print_info(f"Burning animated subtitles from: {subtitles_file.name}")
            burn_success = burn_subtitles(
                input_video=raw_video_path,
                subtitles_file=subtitles_file,
                output_video=output_path,
            )
            try:
                raw_video_path.unlink()
            except Exception:
                pass

            if burn_success and output_path.exists():
                print_success(f"Final YouTube Short generated: {output_path.name}")
                return output_path
            else:
                print_error("Subtitle burning failed, using raw video as output.")
                if raw_video_path.exists():
                    raw_video_path.rename(output_path)
                return output_path

        # If no subtitles, move to output
        if raw_video_path.exists():
            if output_path.exists():
                output_path.unlink()
            raw_video_path.rename(output_path)
            print_success(f"Final YouTube Short generated: {output_path.name}")
            return output_path

        return None
