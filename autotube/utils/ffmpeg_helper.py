"""FFmpeg execution wrapper leveraging bundled imageio-ffmpeg."""

import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import List, Optional
import imageio_ffmpeg
from autotube.utils.console import print_error, print_info


def get_ffmpeg_path() -> str:
    """Return path to ffmpeg binary, prioritizing bundled imageio-ffmpeg."""
    try:
        bundled = imageio_ffmpeg.get_ffmpeg_exe()
        if bundled and os.path.exists(bundled):
            return bundled
    except Exception:
        pass

    system_ffmpeg = shutil.which("ffmpeg")
    if system_ffmpeg:
        return system_ffmpeg

    raise RuntimeError(
        "FFmpeg binary not found. Please install imageio-ffmpeg or add ffmpeg to PATH."
    )


def run_ffmpeg(args: List[str], desc: Optional[str] = None) -> bool:
    """Run an FFmpeg command with the specified arguments."""
    ffmpeg_exe = get_ffmpeg_path()
    cmd = [ffmpeg_exe, "-y"] + args

    if desc:
        print_info(f"{desc}...")

    try:
        result = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        if result.returncode != 0:
            print_error(f"FFmpeg failed with exit code {result.returncode}")
            # Print last few lines of stderr
            err_lines = result.stderr.strip().splitlines()[-10:]
            print_error("\n".join(err_lines))
            return False
        return True
    except Exception as e:
        print_error(f"Failed to execute FFmpeg: {e}")
        return False


def get_media_duration(file_path: Path) -> float:
    """Get the duration of an audio or video file in seconds."""
    ffmpeg_exe = get_ffmpeg_path()
    cmd = [
        ffmpeg_exe,
        "-i",
        str(file_path),
        "-f",
        "null",
        "-",
    ]
    result = subprocess.run(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    # Search for Duration: HH:MM:SS.xx in stderr
    for line in result.stderr.splitlines():
        if "Duration:" in line:
            try:
                part = line.split("Duration:")[1].split(",")[0].strip()
                h, m, s = part.split(":")
                return float(h) * 3600 + float(m) * 60 + float(s)
            except Exception:
                pass
    return 0.0


def create_solid_color_video(
    output_path: Path,
    duration: float,
    width: int = 1080,
    height: int = 1920,
    fps: int = 30,
    color: str = "0x111827",  # Dark slate
) -> bool:
    """Generate a placeholder solid color video for when no footage is provided."""
    args = [
        "-f",
        "lavfi",
        "-i",
        f"color=c={color}:s={width}x{height}:r={fps}",
        "-t",
        f"{duration:.2f}",
        "-c:v",
        "libx264",
        "-pix_fmt",
        "yuv420p",
        str(output_path),
    ]
    return run_ffmpeg(args, desc="Generating background canvas")
