"""YouTube Shorts Video Builder (9:16 Vertical Video Compositor)."""

from pathlib import Path
from typing import Optional
from autotube.config import get_config
from autotube.utils.console import print_error, print_info, print_success
from autotube.utils.ffmpeg_helper import get_media_duration, run_ffmpeg
from autotube.video.subtitle_burner import burn_subtitles


class ShortsBuilder:
    """Builds 1080x1920 vertical YouTube Shorts."""

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

        # Case 1: Video background provided
        if background_video and background_video.exists():
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

        # Case 2: Image background provided
        elif background_image and background_image.exists():
            print_info(f"Using background visual: {background_image.name}")
            vf = (
                f"scale={self.width}:{self.height}:force_original_aspect_ratio=increase,"
                f"crop={self.width}:{self.height},format=yuv420p"
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
            success = run_ffmpeg(args, desc="Rendering vertical video base")

        # Case 3: Fallback motion canvas
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
            # Cleanup raw video
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
