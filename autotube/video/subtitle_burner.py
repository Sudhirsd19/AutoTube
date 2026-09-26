"""Subtitle burning engine using FFmpeg."""

import os
from pathlib import Path
from typing import Optional
from autotube.utils.console import print_error, print_info
from autotube.utils.ffmpeg_helper import run_ffmpeg


def format_ffmpeg_subtitle_path(path: Path) -> str:
    """Format file path safely for FFmpeg filter graph on Windows."""
    try:
        # Prefer relative path to avoid drive letter colons on Windows
        rel = path.resolve().relative_to(Path.cwd().resolve())
        return rel.as_posix()
    except Exception:
        # Fallback to escaped absolute path
        p_str = path.resolve().as_posix()
        # Escape colon (e.g. D: -> D\:)
        p_str = p_str.replace(":", r"\:")
        return p_str


def burn_subtitles(
    input_video: Path,
    subtitles_file: Path,
    output_video: Path,
    force_style: Optional[str] = None,
) -> bool:
    """Burn subtitles (ASS or SRT) onto video using FFmpeg."""
    sub_path_str = format_ffmpeg_subtitle_path(subtitles_file)
    filter_expr = f"subtitles='{sub_path_str}'"
    if force_style:
        filter_expr += f":force_style='{force_style}'"

    args = [
        "-i",
        str(input_video),
        "-vf",
        filter_expr,
        "-c:v",
        "libx264",
        "-crf",
        "23",
        "-preset",
        "veryfast",
        "-c:a",
        "copy",
        str(output_video),
    ]

    return run_ffmpeg(args, desc=f"Burning subtitles onto {output_video.name}")
