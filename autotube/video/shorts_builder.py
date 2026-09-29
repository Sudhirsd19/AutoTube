"""YouTube Shorts Video Builder (9:16 Vertical Video Compositor with Multi-Scene Support)."""

from pathlib import Path
from typing import List, Optional
from autotube.config import get_config
from autotube.media.background_music import BackgroundMusicManager
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
        scene_assets: Optional[List[Path]] = None,
        scene_durations: Optional[List[float]] = None,
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

        # Auto-mix narration speech with dramatic background music and hook SFX
        bgm_mgr = BackgroundMusicManager()
        mixed_audio_path = temp_dir / f"master_audio_{output_path.stem}.mp3"
        master_audio = bgm_mgr.mix_voice_and_music(
            voice_path=audio_path,
            output_mixed_path=mixed_audio_path,
            include_whoosh=True,
        )

        raw_video_path = temp_dir / f"raw_{output_path.stem}.mp4"
        success = False

        # Unified multi-scene asset list (supports mix of videos and high-res photos)
        multi_assets = scene_assets or scene_videos or scene_visuals

        # Fallback single scene video if only 1 passed
        if multi_assets and len(multi_assets) == 1 and not background_video and not background_image:
            first_asset = multi_assets[0]
            if first_asset.suffix.lower() in (".mp4", ".mov", ".webm", ".mkv"):
                background_video = first_asset
            else:
                background_image = first_asset
            multi_assets = None

        # Case 0: Synchronized Multi-Scene Visuals (Videos or Photos with Exact Speech Timing!)
        if multi_assets and len(multi_assets) > 1:
            print_info(f"Assembling {len(multi_assets)} synchronized scene visual cuts...")
            num_scenes = len(multi_assets)
            rendered_clips: List[Path] = []

            for idx, asset in enumerate(multi_assets):
                clip_path = temp_dir / f"sync_scene_{output_path.stem}_{idx:02d}.mp4"
                rendered_clips.append(clip_path)

                if scene_durations and idx < len(scene_durations):
                    dur_per_scene = float(scene_durations[idx])
                else:
                    dur_per_scene = duration / num_scenes

                is_video = asset.suffix.lower() in (".mp4", ".mov", ".webm", ".mkv")

                if is_video:
                    vf = (
                        f"fps={self.fps},"
                        f"scale={self.width}:{self.height}:force_original_aspect_ratio=increase,"
                        f"crop={self.width}:{self.height},"
                        f"setsar=1,"
                        f"format=yuv420p"
                    )
                    args = [
                        "-stream_loop",
                        "-1",
                        "-i",
                        str(asset),
                        "-t",
                        f"{dur_per_scene:.2f}",
                        "-vf",
                        vf,
                        "-r",
                        str(self.fps),
                        "-video_track_timescale",
                        "30000",
                        "-c:v",
                        "libx264",
                        "-preset",
                        "veryfast",
                        "-an",
                        str(clip_path),
                    ]
                    run_ffmpeg(args, desc=f"Rendering video scene cut {idx+1}/{num_scenes} ({dur_per_scene:.1f}s)")
                else:
                    # High-res photo with dynamic Ken Burns camera motion
                    total_frames = max(1, int(dur_per_scene * self.fps))
                    motion_type = idx % 3
                    if motion_type == 0:
                        zoom_expr = "min(zoom+0.0015,1.28)"
                        x_expr = "iw/2-(iw/zoom/2)"
                        y_expr = "ih/2-(ih/zoom/2)"
                    elif motion_type == 1:
                        zoom_expr = "1.18"
                        x_expr = f"(iw-iw/zoom)*(on/{total_frames})"
                        y_expr = "ih/2-(ih/zoom/2)"
                    else:
                        zoom_expr = "if(eq(on,1),1.25,max(1.0,zoom-0.0012))"
                        x_expr = "iw/2-(iw/zoom/2)"
                        y_expr = "ih/2-(ih/zoom/2)"

                    vf = (
                        f"scale=1200:2133:force_original_aspect_ratio=increase,"
                        f"crop=1200:2133,"
                        f"zoompan=z='{zoom_expr}':d={total_frames}:x='{x_expr}':y='{y_expr}':s={self.width}x{self.height}:fps={self.fps},"
                        f"setsar=1,"
                        f"format=yuv420p"
                    )
                    args = [
                        "-loop",
                        "1",
                        "-i",
                        str(asset),
                        "-t",
                        f"{dur_per_scene:.2f}",
                        "-vf",
                        vf,
                        "-r",
                        str(self.fps),
                        "-video_track_timescale",
                        "30000",
                        "-c:v",
                        "libx264",
                        "-preset",
                        "veryfast",
                        "-an",
                        str(clip_path),
                    ]
                    run_ffmpeg(args, desc=f"Rendering animated scene {idx+1}/{num_scenes} ({dur_per_scene:.1f}s)")

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
                str(master_audio),
                "-c:v",
                "libx264",
                "-preset",
                "veryfast",
                "-r",
                str(self.fps),
                "-pix_fmt",
                "yuv420p",
                "-c:a",
                "aac",
                "-b:a",
                "192k",
                "-shortest",
                str(raw_video_path),
            ]
            success = run_ffmpeg(concat_args, desc="Stitching synchronized multi-scene sequence")

        # Case 2: Video background provided
        elif background_video and background_video.exists():
            print_info(f"Using background video: {background_video.name}")
            vf = (
                f"fps={self.fps},"
                f"scale={self.width}:{self.height}:force_original_aspect_ratio=increase,"
                f"crop={self.width}:{self.height},"
                f"setsar=1,"
                f"format=yuv420p"
            )
            args = [
                "-stream_loop",
                "-1",
                "-i",
                str(background_video),
                "-i",
                str(master_audio),
                "-t",
                f"{duration:.2f}",
                "-vf",
                vf,
                "-r",
                str(self.fps),
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

        # Case 3: Single Image background provided with continuous smooth cinematic motion
        elif background_image and background_image.exists():
            print_info(f"Using background visual with continuous zoom: {background_image.name}")
            total_frames = max(1, int(duration * self.fps))
            vf = (
                f"scale=1200:2133:force_original_aspect_ratio=increase,"
                f"crop=1200:2133,"
                f"zoompan=z='min(zoom+0.0008,1.22)':d={total_frames}:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s={self.width}x{self.height}:fps={self.fps},"
                f"setsar=1,"
                f"format=yuv420p"
            )
            args = [
                "-loop",
                "1",
                "-i",
                str(background_image),
                "-i",
                str(master_audio),
                "-t",
                f"{duration:.2f}",
                "-vf",
                vf,
                "-r",
                str(self.fps),
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
                str(master_audio),
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

        # Burn subtitles and viral hook/subscribe badges
        hook_badge = self.cfg.paths.assets_dir / "hook_badge.png"
        subscribe_badge = self.cfg.paths.assets_dir / "subscribe_badge.png"

        print_info("Burning high-retention subtitles & viral overlay badges...")
        burn_success = burn_subtitles(
            input_video=raw_video_path,
            subtitles_file=subtitles_file if subtitles_file and subtitles_file.exists() else None,
            output_video=output_path,
            hook_badge=hook_badge if hook_badge.exists() else None,
            subscribe_badge=subscribe_badge if subscribe_badge.exists() else None,
            duration=duration,
        )
        try:
            raw_video_path.unlink()
        except Exception:
            pass

        if burn_success and output_path.exists():
            print_success(f"Final Viral YouTube Short generated: {output_path.name}")
            return output_path
        else:
            print_error("Subtitle/overlay burning failed, using raw video as output.")
            if raw_video_path.exists():
                raw_video_path.rename(output_path)
            return output_path
