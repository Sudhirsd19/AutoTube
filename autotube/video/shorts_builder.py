"""YouTube Shorts Video Builder (9:16 Vertical Video Compositor with Multi-Scene Support)."""

from pathlib import Path
from typing import List, Optional
from autotube.config import get_config
from autotube.media.background_music import BackgroundMusicManager
from autotube.utils.console import print_error, print_info, print_success, print_warning
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
        music_path: Optional[Path] = None,
        width: Optional[int] = None,
        height: Optional[int] = None,
    ) -> Optional[Path]:
        """Compose audio, background visuals, and animated subtitles into a final Short or Landscape Video."""
        v_width = width or self.width
        v_height = height or self.height

        output_path.parent.mkdir(parents=True, exist_ok=True)
        temp_dir = self.cfg.paths.temp_dir
        temp_dir.mkdir(parents=True, exist_ok=True)

        duration = get_media_duration(audio_path)
        if duration <= 0:
            print_error("Audio duration could not be determined.")
            return None

        # Unified multi-scene asset list (supports mix of videos and high-res photos)
        multi_assets = scene_assets or scene_videos or scene_visuals
        if multi_assets:
            # Ensure assets actually exist on disk
            multi_assets = [Path(p) for p in multi_assets if p and Path(p).exists()]

        # Strict scene contract: never recycle or silently trim visuals.
        if scene_durations and multi_assets:
            target_scene_count = len(scene_durations)
            if len(multi_assets) != target_scene_count:
                print_error(
                    f"Scene/visual count mismatch: {len(multi_assets)} visual assets for {target_scene_count} speech scenes. "
                    "Render blocked; assets will not be recycled across narration."
                )
                return None

        # Calculate exact cut timestamps for micro-transition sound effects
        cut_timestamps: List[float] = []
        if multi_assets and len(multi_assets) > 1:
            curr_elapsed = 0.0
            for idx in range(len(multi_assets) - 1):
                if scene_durations and idx < len(scene_durations):
                    dur_p = float(scene_durations[idx])
                else:
                    dur_p = duration / len(multi_assets)
                curr_elapsed += dur_p
                cut_timestamps.append(round(curr_elapsed, 3))

        # Auto-mix narration speech with calm mysterious background music and micro-cut whooshes
        bgm_mgr = BackgroundMusicManager()
        mixed_audio_path = temp_dir / f"master_audio_{output_path.stem}.mp3"
        master_audio = bgm_mgr.mix_voice_and_music(
            voice_path=audio_path,
            output_mixed_path=mixed_audio_path,
            music_path=music_path,
            include_whoosh=False,
            topic=output_path.stem,
            cut_timestamps=cut_timestamps,
        )

        raw_video_path = temp_dir / f"raw_{output_path.stem}.mp4"
        success = False

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

            elapsed_rendered = 0.0
            for idx, asset in enumerate(multi_assets):
                clip_path = temp_dir / f"sync_scene_{output_path.stem}_{idx:02d}.mp4"
                rendered_clips.append(clip_path)

                if idx == num_scenes - 1:
                    # Final clip takes all remaining audio duration to guarantee exact overall duration
                    dur_per_scene = max(1.5, round(duration - elapsed_rendered, 3))
                elif scene_durations and idx < len(scene_durations):
                    dur_per_scene = float(scene_durations[idx])
                else:
                    dur_per_scene = round(duration / num_scenes, 3)

                elapsed_rendered += dur_per_scene

                is_video = asset.suffix.lower() in (".mp4", ".mov", ".webm", ".mkv")

                if is_video:
                    vf = (
                        f"fps={self.fps},"
                        f"scale={v_width}:{v_height}:force_original_aspect_ratio=increase,"
                        f"crop={v_width}:{v_height},"
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
                        "-fflags",
                        "+genpts",
                        "-avoid_negative_ts",
                        "make_zero",
                        "-video_track_timescale",
                        "30000",
                        "-c:v",
                        "libx264",
                        "-preset",
                        "ultrafast",
                        "-threads",
                        "4",
                        "-an",
                        str(clip_path),
                    ]
                    run_ffmpeg(args, desc=f"Rendering video scene cut {idx+1}/{num_scenes} ({dur_per_scene:.1f}s)")
                else:
                    # High-res photo / AI visual with dynamic continuous motion (0% Freeze Guarantee!)
                    total_frames = max(1, int(dur_per_scene * self.fps))
                    motion_type = idx % 5
                    p_factor = f"min(1.0,on/{total_frames})"
                    if motion_type == 0:
                        # Smooth continuous Zoom-In (1.0 -> 1.25) across entire scene duration
                        zoom_expr = f"min(1.25,1.0+0.25*{p_factor})"
                        x_expr = "iw/2-(iw/zoom/2)"
                        y_expr = "ih/2-(ih/zoom/2)"
                    elif motion_type == 1:
                        # Smooth continuous Zoom-Out (1.25 -> 1.05) across entire scene duration
                        zoom_expr = f"max(1.05,1.25-0.20*{p_factor})"
                        x_expr = "iw/2-(iw/zoom/2)"
                        y_expr = "ih/2-(ih/zoom/2)"
                    elif motion_type == 2:
                        # Cinematic Pan Left-to-Right with steady framing
                        zoom_expr = "1.15"
                        x_expr = f"(iw-iw/zoom)*{p_factor}"
                        y_expr = "ih/2-(ih/zoom/2)"
                    elif motion_type == 3:
                        # Cinematic Pan Right-to-Left with steady framing
                        zoom_expr = "1.15"
                        x_expr = f"(iw-iw/zoom)*(1.0-{p_factor})"
                        y_expr = "ih/2-(ih/zoom/2)"
                    else:
                        # Cinematic Diagonal Tilt & Zoom
                        zoom_expr = f"min(1.24,1.06+0.18*{p_factor})"
                        x_expr = f"(iw-iw/zoom)*{p_factor}"
                        y_expr = f"(ih-ih/zoom)*{p_factor}"

                    scale_res = "2560:1440" if v_width > v_height else "1200:2133"
                    vf = (
                        f"scale={scale_res}:force_original_aspect_ratio=increase,"
                        f"crop={scale_res},"
                        f"zoompan=z='{zoom_expr}':d={total_frames}:x='{x_expr}':y='{y_expr}':s={v_width}x{v_height}:fps={self.fps},"
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
                        "ultrafast",
                        "-threads",
                        "4",
                        "-an",
                        str(clip_path),
                    ]
                    run_ffmpeg(args, desc=f"Rendering dynamic scene {idx+1}/{num_scenes} ({dur_per_scene:.1f}s)")

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
                "-t",
                f"{duration:.3f}",
                str(raw_video_path),
            ]
            success = run_ffmpeg(concat_args, desc="Stitching synchronized multi-scene sequence")

        # Case 2: Video background provided
        elif background_video and background_video.exists():
            print_info(f"Using background video: {background_video.name}")
            vf = (
                f"fps={self.fps},"
                f"scale={v_width}:{v_height}:force_original_aspect_ratio=increase,"
                f"crop={v_width}:{v_height},"
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
            scale_res = "2560:1440" if v_width > v_height else "1200:2133"
            p_factor = f"min(1.0,on/{total_frames})"
            vf = (
                f"scale={scale_res}:force_original_aspect_ratio=increase,"
                f"crop={scale_res},"
                f"zoompan=z='min(1.25,1.0+0.22*{p_factor})':d={total_frames}:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s={v_width}x{v_height}:fps={self.fps},"
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
                f"color=c=0x0f172a:s={v_width}x{v_height}:r={self.fps},"
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
        res_video = None
        if burn_success and output_path.exists() and output_path.stat().st_size > 1000:
            try:
                if raw_video_path.exists():
                    raw_video_path.unlink()
            except Exception:
                pass
            print_success(f"Final Viral YouTube Short generated: {output_path.name}")
            res_video = output_path
        else:
            print_warning("Subtitle/overlay burning failed, falling back to raw video as output.")
            if raw_video_path.exists() and raw_video_path.stat().st_size > 1000:
                try:
                    import shutil
                    if output_path.exists():
                        output_path.unlink()
                    shutil.move(str(raw_video_path), str(output_path))
                    print_info(f"Using raw video without subtitles: {output_path.name}")
                    res_video = output_path
                except Exception as mv_err:
                    print_error(f"Failed to recover raw video as output: {mv_err}")

        if res_video and res_video.exists():
            final_dur = get_media_duration(res_video)
            is_vertical = (v_height > v_width)
            if is_vertical and final_dur >= 59.5:
                try:
                    res_video.unlink()
                except Exception:
                    pass
                raise RuntimeError(
                    f"Fail-Closed Duration Gate: Rendered Short duration is {final_dur:.2f}s, "
                    "which violates the strict 60.0s YouTube Shorts limit! Video blocked and deleted."
                )
            return res_video

        return None
