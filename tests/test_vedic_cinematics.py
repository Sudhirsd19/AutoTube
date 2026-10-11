"""Tests for Vedic & Granth cinematic situational FX engine."""

from pathlib import Path
import pytest

from autotube.media.vedic_cinematics import (
    classify_vedic_scene_mood,
    get_vedic_motion_and_filters,
    render_vedic_cinematic_clip,
)


def test_classify_vedic_scene_mood_war():
    # Asura / Raktabija war scene
    text = "रक्तबीज के शरीर से जैसे ही रक्त की एक बूंद गिरती, एक नया असुर पैदा हो जाता।"
    prompt = "Cinematic 8K shot of terrifying asura demon Raktabija on volcanic battlefield"
    mood = classify_vedic_scene_mood(narration=text, visual_prompt=prompt)
    assert mood == "war_asura"


def test_classify_vedic_scene_mood_divine():
    # Krishna / Gita divine wisdom scene
    text = "भगवान श्री कृष्ण ने अर्जुन को गीता का अमर ज्ञान देते हुए कहा कि कर्म ही पूजा है।"
    prompt = "Lord Krishna divine form in golden aura blessing Arjuna in Kurukshetra"
    mood = classify_vedic_scene_mood(narration=text, visual_prompt=prompt)
    assert mood == "divine_sacred"


def test_classify_vedic_scene_mood_mystery():
    # Cosmic mystery / Kalachakra scene
    text = "सृष्टि और कालचक्र का यह रहस्य आज भी किसी के समझ में नहीं आया।"
    prompt = "Cosmic wheel of time kalachakra universe infinite celestial dimensions"
    mood = classify_vedic_scene_mood(narration=text, visual_prompt=prompt)
    assert mood == "mystery_cosmic"


def test_classify_vedic_scene_mood_history():
    # General historical scene
    text = "प्राचीन काल में राजा परीक्षित ने एक महत्वपूर्ण निर्णय लिया।"
    prompt = "Ancient Vedic royal court palace assembly"
    mood = classify_vedic_scene_mood(narration=text, visual_prompt=prompt)
    assert mood == "epic_history"


def test_classify_explicit_mood_override():
    assert classify_vedic_scene_mood(explicit_mood="war_asura") == "war_asura"
    assert classify_vedic_scene_mood(explicit_mood="divine_sacred") == "divine_sacred"
    assert classify_vedic_scene_mood(explicit_mood="mystery_cosmic") == "mystery_cosmic"
    assert classify_vedic_scene_mood(explicit_mood="epic_history") == "epic_history"


def test_get_vedic_motion_and_filters():
    for mood in ("war_asura", "divine_sacred", "mystery_cosmic", "epic_history"):
        z, x, y, f = get_vedic_motion_and_filters(mood, 0, 4, 5.0)
        assert len(z) > 0
        assert len(x) > 0
        assert len(y) > 0
        assert len(f) > 0


def test_render_vedic_cinematic_clip(tmp_path):
    # Create a small dummy test image
    import subprocess
    from autotube.utils.ffmpeg_helper import get_ffmpeg_path

    img_p = tmp_path / "test_input.jpg"
    out_p = tmp_path / "test_output.mp4"
    ff = get_ffmpeg_path()

    # Generate a dummy 1080x1920 test image via ffmpeg
    gen_cmd = [ff, "-y", "-f", "lavfi", "-i", "color=c=darkred:s=1080x1920:d=1", "-vframes", "1", str(img_p)]
    subprocess.run(gen_cmd, check=True, capture_output=True)
    assert img_p.exists()

    res = render_vedic_cinematic_clip(
        image_path=img_p,
        output_path=out_p,
        duration=2.0,
        fps=30,
        width=1080,
        height=1920,
        scene_idx=0,
        total_scenes=1,
        narration="रक्तबीज का भयानक युद्ध और ज्वाला",
        visual_prompt="Demon Asura warrior on battlefield",
    )
    assert res is not None
    assert out_p.exists()
    assert out_p.stat().st_size > 10000
