from autotube.voice.voice_director import (
    choose_subject_voice,
    detect_language,
    is_voice_language_compatible,
    resolve_voice_for_content,
)


def test_auto_voice_black_hole_hindi():
    assert choose_subject_voice("Black Hole", "यह अंतरिक्ष का सबसे रहस्यमय black hole है", "hi") == "hi_deep_cinematic_male"


def test_auto_voice_history_english():
    assert choose_subject_voice("Indian History", "The empire changed the course of history.", "en") == "en_deep_british_male"


def test_auto_voice_science_hindi():
    assert choose_subject_voice("Science Facts", "यह एक scientific experiment है", "hi") == "hi_calm_male"


def test_auto_voice_mystery_english():
    assert choose_subject_voice("Unsolved Mystery", "An unexplained case shocked investigators.", "en") == "en_cinematic_narrator"


def test_language_detection():
    assert detect_language("यह एक हिंदी कहानी है", "auto") == "hi"
    assert detect_language("This is an English story.", "auto") == "en"


def test_language_compatibility():
    assert is_voice_language_compatible("hi_deep_cinematic_male", "hi")
    assert not is_voice_language_compatible("en_deep_cinematic_male", "hi")
    assert is_voice_language_compatible("en_deep_british_male", "en")


def test_resolve_auto_voice_uses_generated_subject():
    assert resolve_voice_for_content(
        "auto",
        "What Happens Inside a Black Hole?",
        "A black hole bends spacetime around its event horizon.",
        "en",
    ) == "en_deep_cinematic_male"


def test_resolve_incompatible_voice_fails_closed_to_language_safe_voice():
    assert resolve_voice_for_content(
        "en_deep_cinematic_male",
        "Mahabharat Mystery",
        "यह महाभारत का एक रहस्यमय प्रसंग है।",
        "hi",
    ) == "hi_authoritative_male"


def test_resolve_explicit_compatible_voice_preserves_choice():
    assert resolve_voice_for_content(
        "hi_deep_cinematic_male",
        "Black Hole",
        "यह अंतरिक्ष की कहानी है।",
        "hi",
    ) == "hi_deep_cinematic_male"
