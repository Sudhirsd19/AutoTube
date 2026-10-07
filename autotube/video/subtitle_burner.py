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
    subtitles_file: Optional[Path],
    output_video: Path,
    force_style: Optional[str] = None,
    hook_badge: Optional[Path] = None,
    subscribe_badge: Optional[Path] = None,
    duration: Optional[float] = None,
) -> bool:
    """Burn subtitles (ASS or SRT) onto video along with optional viral hook and subscribe badges."""
    from autotube.utils.ffmpeg_helper import get_media_duration

    inputs = ["-i", str(input_video)]
    filter_steps = []
    current_v = "[0:v]"

    # 1. Subtitles filter
    if subtitles_file and subtitles_file.exists():
        sub_path_str = format_ffmpeg_subtitle_path(subtitles_file)
        fonts_dir = Path("assets/fonts")
        if fonts_dir.exists():
            fonts_dir_str = format_ffmpeg_subtitle_path(fonts_dir)
            sub_filter = f"subtitles='{sub_path_str}':fontsdir='{fonts_dir_str}'"
        else:
            sub_filter = f"subtitles='{sub_path_str}'"
        if force_style:
            sub_filter += f":force_style='{force_style}'"
        filter_steps.append(f"{current_v}{sub_filter}[v_sub]")
        current_v = "[v_sub]"

    vid_dur = duration or get_media_duration(input_video)

    # 2. Hook badge overlay (First 2.8 seconds)
    if hook_badge and hook_badge.exists():
        inputs.extend(["-i", str(hook_badge)])
        hook_idx = (len(inputs) // 2) - 1
        filter_steps.append(
            f"{current_v}[{hook_idx}:v]overlay=(W-w)/2:220:enable='between(t,0,2.8)'[v_hook]"
        )
        current_v = "[v_hook]"

    # 3. Like, Subscribe & Bell outro banner (Appears during last 6.5s during spoken Outro CTA)
    bell_banner = Path("assets/like_subscribe_bell_banner.png")
    if bell_banner.exists():
        inputs.extend(["-i", str(bell_banner)])
        bell_idx = (len(inputs) // 2) - 1
        outro_start = max(1.0, vid_dur - 6.5)
        outro_end = max(1.5, vid_dur - 0.2)
        filter_steps.append(
            f"{current_v}[{bell_idx}:v]overlay=(W-w)/2:H-h-180:enable='between(t,{outro_start:.1f},{outro_end:.1f})'[v_sub_cta]"
        )
        current_v = "[v_sub_cta]"
    elif subscribe_badge and subscribe_badge.exists():
        inputs.extend(["-i", str(subscribe_badge)])
        sub_idx = (len(inputs) // 2) - 1
        sub_start = max(4.0, vid_dur * 0.60)
        sub_end = min(vid_dur - 0.5, sub_start + 7.0)
        filter_steps.append(
            f"{current_v}[{sub_idx}:v]overlay=(W-w)/2:1320:enable='between(t,{sub_start:.1f},{sub_end:.1f})'[v_sub_cta]"
        )
        current_v = "[v_sub_cta]"

    # 4. Classified TOP SECRET stamp badge overlay (Appears from t=0.5 to t=4.0 for intense hook retention)
    classified_badge = Path("assets/classified_badge.png")
    if classified_badge.exists():
        inputs.extend(["-i", str(classified_badge)])
        class_idx = (len(inputs) // 2) - 1
        filter_steps.append(
            f"{current_v}[{class_idx}:v]overlay=(W-w)/2:280:enable='between(t,0.4,4.2)'[v_class]"
        )
        current_v = "[v_class]"

    # 5. Sleek Neon Progress Bar (Psychological Completion Booster for 9:16 Vertical Shorts)
    try:
        from autotube.utils.ffmpeg_helper import get_media_dimensions
        w_val, h_val = get_media_dimensions(input_video)
        if h_val > w_val and vid_dur > 0:
            filter_steps.append(
                f"{current_v}drawbox=x=0:y=ih-8:w='iw*(t/{vid_dur:.2f})':h=6:color=0x38bdf8@0.9:t=fill[v_prog]"
            )
            current_v = "[v_prog]"
    except Exception:
        pass

    # If no filters applied, just copy
    if not filter_steps:
        args = ["-i", str(input_video), "-c", "copy", str(output_video)]
        return run_ffmpeg(args, desc=f"Exporting video {output_video.name}")

    args = (
        inputs
        + [
            "-filter_complex",
            ";".join(filter_steps),
            "-map",
            current_v,
            "-map",
            "0:a?",
            "-c:v",
            "libx264",
            "-crf",
            "23",
            "-preset",
            "ultrafast",
            "-threads",
            "4",
            "-c:a",
            "copy",
            str(output_video),
        ]
    )

    return run_ffmpeg(args, desc=f"Burning subtitles & viral overlays onto {output_video.name}")

