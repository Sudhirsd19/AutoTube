from autotube.voice.voice_director import choose_subject_voice, detect_language, is_voice_language_compatible


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
