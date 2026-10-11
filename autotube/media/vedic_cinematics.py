"""Vedic & Granth Cinematic Situational Motion & FX Engine.

Purely local, 100% free procedural FFmpeg effects tailored specifically for
Vedic, Granth, Puranic, and Mythological storytelling.
Zero external API costs.
"""

from pathlib import Path
from typing import Any, Dict, Optional, Tuple
import subprocess

from autotube.utils.console import print_info, print_success, print_warning
from autotube.utils.ffmpeg_helper import get_ffmpeg_path


# ---------------------------------------------------------------------------
# Situational Mood Keywords (Hindi & English)
# ---------------------------------------------------------------------------

WAR_ASURA_KEYWORDS = (
    # Hindi / Sanskrit terms
    "असुर", "राक्षस", "दानव", "दैत्य", "रक्तबीज", "रावण", "कुम्भकर्ण", "कंस",
    "वध", "संहार", "युद्ध", "रणभूमि", "कुरुक्षेत्र", "सेना", "अस्त्र", "शस्त्र",
    "क्रोध", "अग्नि", "ज्वाला", "रक्त", "खून", "भस्म", "विनाश", "घमासान",
    "बाण", "त्रिशूल", "तलवार", "चीत्कार", "गर्जना", "तांडव", "पाप", "दुष्ट",
    "प्रहार", "मार", "मृत्यु", "भयानक", "सेनापति", "ज्वालामुखी", "क्रूर",
    # English terms
    "asura", "demon", "monster", "rakshasa", "raktabija", "ravan", "kansa",
    "battle", "war", "kurukshetra", "weapon", "weapons", "wrath", "rage",
    "fire", "flame", "flames", "blood", "slaughter", "destroy", "destruction",
    "roar", "roaring", "tandav", "volcanic", "warrior", "clash", "strike",
    "blade", "evil", "terrifying", "enemy", "furious", "fiery",
)

DIVINE_SACRED_KEYWORDS = (
    # Hindi / Sanskrit terms
    "कृष्ण", "विष्णु", "शिव", "महादेव", "राम", "हनुमान", "गंगा", "मंदिर",
    "श्लोक", "मंत्र", "उपनिषद", "गीता", "ज्ञान", "मोक्ष", "धर्म", "शांति",
    "ध्यान", "तपस्या", "दिव्य", "वरदान", "आशीर्वाद", "भगवान", "ईश्वर", "प्रभु",
    "साधना", "अमृत", "स्वर्ग", "वैकुंठ", "कैलाश", "प्रणाम", "भक्ति", "पवित्र",
    "ऋषि", "मुनि", "आश्रम", "करुणा", "सत्य", "प्रकाश", "ज्योति", "दर्शन",
    "मुरली", "सुदर्शन", "चक्र", "आरती", "नारायण", "श्रीहरि",
    # English terms
    "krishna", "vishnu", "shiva", "mahadev", "ram", "hanuman", "ganga",
    "temple", "shloka", "mantra", "gita", "wisdom", "moksha", "dharma",
    "peace", "divine", "sacred", "blessing", "god", "lord", "aura",
    "meditation", "heaven", "kailash", "holy", "sage", "monk", "enlightened",
    "serenity", "light", "halo", "flute", "grace", "spiritual",
)

MYSTERY_COSMIC_KEYWORDS = (
    # Hindi / Sanskrit terms
    "रहस्य", "गुप्त", "अनसुलझा", "कालचक्र", "महाकाल", "अनंत काल", "समय चक्र",
    "सृष्टि", "ब्रह्मांड", "विराट रूप", "नक्षत्र", "अदृश्य", "माया", "चमत्कार",
    "विस्मय", "अनंत", "शून्य", "अंतरीक्ष", "भविष्य", "कलयुग", "सतयुग",
    # English terms
    "mystery", "secret", "unsolved", "kalachakra", "cosmos",
    "universe", "virat", "miracle", "illusion", "maya", "celestial",
    "infinite", "dimension", "portal", "destiny", "prophecy",
)

EPIC_HISTORY_KEYWORDS = (
    "प्राचीन काल", "इतिहास", "राजा", "सम्राट", "सिंहासन", "दरबार", "राज्य",
    "साम्राज्य", "ऐतिहासिक", "परीक्षित", "हस्तिनापुर", "अयोध्या", "गांधार",
    "ancient", "history", "historical", "dynasty", "emperor", "kingdom", "palace",
)


def classify_vedic_scene_mood(
    narration: str = "",
    visual_prompt: str = "",
    visual_subject: str = "",
    explicit_mood: str = "auto",
) -> str:
    """Classify the scene into one of four situational moods:
    - 'war_asura': Battles, demons, anger, weapons, fire.
    - 'divine_sacred': Gods, avatars, peace, wisdom, temples, blessings.
    - 'mystery_cosmic': Cosmic time, universe, divine secrets, prophecy.
    - 'epic_history': Classic historical narration.
    """
    clean_explicit = str(explicit_mood or "").strip().lower()
    if clean_explicit in ("war_asura", "war", "asura"):
        return "war_asura"
    if clean_explicit in ("divine_sacred", "divine", "sacred"):
        return "divine_sacred"
    if clean_explicit in ("mystery_cosmic", "mystery", "cosmic"):
        return "mystery_cosmic"
    if clean_explicit in ("epic_history", "history", "classic"):
        return "epic_history"

    combined = f"{narration} {visual_prompt} {visual_subject}".lower()

    # Score each mood by keyword matches
    war_score = sum(1 for kw in WAR_ASURA_KEYWORDS if kw in combined)
    divine_score = sum(1 for kw in DIVINE_SACRED_KEYWORDS if kw in combined)
    mystery_score = sum(1 for kw in MYSTERY_COSMIC_KEYWORDS if kw in combined)
    history_score = sum(1 for kw in EPIC_HISTORY_KEYWORDS if kw in combined)

    if war_score > 0 and war_score >= divine_score and war_score >= mystery_score:
        return "war_asura"
    if divine_score > 0 and divine_score >= mystery_score:
        return "divine_sacred"
    if mystery_score > 0 and mystery_score >= history_score:
        return "mystery_cosmic"
    if history_score > 0:
        return "epic_history"

    return "epic_history"


def get_vedic_motion_and_filters(
    mood: str,
    scene_idx: int,
    total_scenes: int,
    duration: float,
    fps: int = 30,
    width: int = 1080,
    height: int = 1920,
) -> Tuple[str, str, str, str]:
    """Calculate the zoompan mathematical expressions and situational color/vignette filters.

    Returns: (zoom_expr, x_expr, y_expr, extra_filters)
    """
    total_frames = max(1, int(duration * fps))
    fade_d = min(0.30, max(0.15, duration * 0.08))

    if mood == "war_asura":
        # Dynamic Handheld Camera Shake + Intense Punch Zoom
        zoom_expr = f"min(1.26,1.05+0.21*on/{total_frames})"
        x_expr = "iw/2-(iw/zoom/2)+12*sin(0.35*on)*cos(0.2*on)"
        y_expr = "ih/2-(ih/zoom/2)+8*cos(0.3*on)*sin(0.18*on)"
        # Fiery grading + crimson shadow boost + intense dark vignette + impact cut fade
        extra_filters = (
            "eq=contrast=1.14:saturation=1.18:gamma_r=1.10:gamma_b=0.88,"
            "vignette=PI/4.2,"
            f"fade=t=in:st=0:d={fade_d:.2f}:c=black,"
            f"fade=t=out:st={duration-fade_d:.2f}:d={fade_d:.2f}:c=black"
        )

    elif mood == "divine_sacred":
        # Slow Majestic Float (Gentle Upward Drift, perfectly stable, serene)
        zoom_expr = f"min(1.18,1.02+0.16*on/{total_frames})"
        x_expr = "iw/2-(iw/zoom/2)"
        y_expr = f"ih/2-(ih/zoom/2)-(ih*0.04*on/{total_frames})"
        # Golden aura warm grade + soft bloom + gentle vignette + golden/white soft transition
        extra_filters = (
            "eq=contrast=1.05:saturation=1.10:brightness=0.03:gamma_r=1.08:gamma_g=1.04:gamma_b=0.90,"
            "vignette=PI/5.0,"
            f"fade=t=in:st=0:d={fade_d:.2f}:c=white,"
            f"fade=t=out:st={duration-fade_d:.2f}:d={fade_d:.2f}:c=white"
        )

    elif mood == "mystery_cosmic":
        # Deep Cosmic Diagonal Drift & Slow Zoom
        zoom_expr = f"min(1.22,1.03+0.19*on/{total_frames})"
        x_expr = f"(iw-iw/zoom)*(on/{total_frames})"
        y_expr = f"(ih-ih/zoom)*(on/{total_frames})"
        # Deep ethereal indigo contrast + dark mystic vignette + smooth fade
        extra_filters = (
            "eq=contrast=1.10:saturation=1.06:gamma_r=0.92:gamma_b=1.12,"
            "vignette=PI/4.0,"
            f"fade=t=in:st=0:d={fade_d:.2f}:c=black,"
            f"fade=t=out:st={duration-fade_d:.2f}:d={fade_d:.2f}:c=black"
        )

    else:
        # Epic History (Alternating Smooth Ken Burns: Zoom-In / Pan Left / Pan Right / Zoom-Out)
        m_type = scene_idx % 4
        if m_type == 0:
            zoom_expr = f"min(1.22,1.0+0.22*on/{total_frames})"
            x_expr = "iw/2-(iw/zoom/2)"
            y_expr = "ih/2-(ih/zoom/2)"
        elif m_type == 1:
            zoom_expr = "1.15"
            x_expr = f"(iw-iw/zoom)*(on/{total_frames})"
            y_expr = "ih/2-(ih/zoom/2)"
        elif m_type == 2:
            zoom_expr = f"max(1.04,1.22-0.18*on/{total_frames})"
            x_expr = "iw/2-(iw/zoom/2)"
            y_expr = "ih/2-(ih/zoom/2)"
        else:
            zoom_expr = "1.15"
            x_expr = f"(iw-iw/zoom)*(1.0-on/{total_frames})"
            y_expr = "ih/2-(ih/zoom/2)"

        extra_filters = (
            "eq=contrast=1.08:saturation=1.06:gamma_r=1.04,"
            "vignette=PI/4.6,"
            f"fade=t=in:st=0:d={fade_d:.2f}:c=black,"
            f"fade=t=out:st={duration-fade_d:.2f}:d={fade_d:.2f}:c=black"
        )

    return zoom_expr, x_expr, y_expr, extra_filters


def render_vedic_cinematic_clip(
    image_path: Path,
    output_path: Path,
    duration: float = 6.0,
    fps: int = 30,
    width: int = 1080,
    height: int = 1920,
    scene_idx: int = 0,
    total_scenes: int = 1,
    narration: str = "",
    visual_prompt: str = "",
    visual_subject: str = "",
    explicit_mood: str = "auto",
) -> Optional[Path]:
    """Render a 4K image into a high-impact, situational cinematic video clip.

    Applies situational camera dynamics (handheld shake, majestic float, or cosmic drift),
    mood-specific color grading/vignette, and smooth boundary transitions.
    """
    if not image_path.exists() or image_path.stat().st_size < 1000:
        print_warning(f"Vedic cinematic renderer: Source image {image_path} does not exist or is too small.")
        return None

    mood = classify_vedic_scene_mood(
        narration=narration,
        visual_prompt=visual_prompt,
        visual_subject=visual_subject,
        explicit_mood=explicit_mood,
    )

    mood_labels = {
        "war_asura": "🔥 War / Asura Mode (Handheld Shake + Fiery Contrast + Ember Vignette)",
        "divine_sacred": "✨ Divine Sacred Mode (Majestic Float + Golden Aura + Sacred Glow)",
        "mystery_cosmic": "🌌 Cosmic Mystery Mode (Deep Drift + Indigo Contrast + Void Vignette)",
        "epic_history": "🏛️ Epic History Mode (Smooth Ken Burns + Film Grade)",
    }
    print_info(f"   🕉️ [Vedic Cinematic FX] Scene {scene_idx + 1}/{total_scenes}: {mood_labels.get(mood, mood)}")

    total_frames = max(1, int(duration * fps))
    zoom_expr, x_expr, y_expr, extra_filters = get_vedic_motion_and_filters(
        mood=mood,
        scene_idx=scene_idx,
        total_scenes=total_scenes,
        duration=duration,
        fps=fps,
        width=width,
        height=height,
    )

    ffmpeg_exe = get_ffmpeg_path()
    scale_res = f"{int(width * 1.25)}:{int(height * 1.25)}"

    vf_parts = [
        f"scale={scale_res}:force_original_aspect_ratio=increase",
        f"crop={scale_res}",
        f"zoompan=z='{zoom_expr}':d={total_frames}:x='{x_expr}':y='{y_expr}':s={width}x{height}:fps={fps}",
    ]
    if extra_filters:
        vf_parts.append(extra_filters)
    vf_parts.extend(["setsar=1", "format=yuv420p"])

    vf_string = ",".join(vf_parts)

    args = [
        ffmpeg_exe, "-y", "-loop", "1", "-i", str(image_path), "-t", f"{duration:.2f}",
        "-vf", vf_string, "-r", str(fps), "-c:v", "libx264", "-preset", "ultrafast",
        "-pix_fmt", "yuv420p", "-an", str(output_path)
    ]

    try:
        res = subprocess.run(args, capture_output=True, text=True, timeout=45)
        if res.returncode == 0 and output_path.exists() and output_path.stat().st_size > 10000:
            print_success(f"   🎬 [Vedic FX Rendered] Scene {scene_idx + 1} ({mood}) created ({output_path.stat().st_size // 1024} KB)!")
            return output_path
        else:
            print_warning(f"Vedic FX render failed with returncode {res.returncode}: {res.stderr[-300:] if res.stderr else ''}")
    except Exception as exc:
        print_warning(f"Vedic FX render exception for {image_path.name}: {exc}")

    # Fallback to standard motion clip if anything goes wrong
    try:
        from autotube.media.visual_waterfall import _image_to_motion_clip
        print_info(f"   🔄 Falling back to standard motion clip for Scene {scene_idx + 1}...")
        return _image_to_motion_clip(
            image_path=image_path,
            output_path=output_path,
            duration=duration,
            fps=fps,
            width=width,
            height=height,
            motion_type=scene_idx,
        )
    except Exception as fb_exc:
        print_warning(f"Standard motion fallback also failed: {fb_exc}")
        return None
