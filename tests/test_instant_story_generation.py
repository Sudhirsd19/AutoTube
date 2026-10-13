"""Test instant story generation and non-blocking fallback engine."""

import time
import pytest
from autotube.media.director_engine import DirectorEngine


def test_amazon_jungle_story_generation():
    engine = DirectorEngine()
    t0 = time.time()
    res = engine.enhance_script_with_ai(
        raw_input="amazon jungle ka rahays aur waha paye jaane wale jiv jantu",
        topic=None,
        language="hi",
        video_format="short",
    )
    duration = time.time() - t0

    assert res["success"] is True
    assert duration < 12.0  # Must never hang or exceed 12s
    assert 70 <= res["word_count"] <= 120
    assert 25.0 <= res["est_seconds"] <= 55.0
    assert len(res["titles"]) >= 3
    assert len(res["scenes"]) >= 4

    # Verify content relevance
    full_text = res["full_narration"]
    assert any(k in full_text for k in ["अमेज़न", "जंगल", "वर्षावन", "चींटी", "एनाकोंडा", "रहस्य"])
    assert res["hook"] != ""
    assert res["cliffhanger"] != ""


def test_smart_fallback_story_genres():
    engine = DirectorEngine()

    # Rebirth / Punarjanam
    res_rebirth = engine._generate_smart_fallback_story("punarjanam real incident proof", language="hi")
    assert "1935" in res_rebirth["full_narration"] or "पुनर्जन्म" in res_rebirth["full_narration"]
    assert res_rebirth["word_count"] <= 120

    # Bermuda Triangle
    res_bermuda = engine._generate_smart_fallback_story("bermuda triangle mystery", language="hi")
    assert "बरमूडा" in res_bermuda["full_narration"] or "जहाज़" in res_bermuda["full_narration"]
    assert res_bermuda["word_count"] <= 120

    # Vedic / Gita
    res_vedic = engine._generate_smart_fallback_story("bhagavad gita krishna updesh", language="hi")
    assert "कृष्ण" in res_vedic["full_narration"] or "गीता" in res_vedic["full_narration"]
    assert res_vedic["word_count"] <= 120

    # Space / Black hole
    res_space = engine._generate_smart_fallback_story("black hole secret nasa", language="hi")
    assert "ब्लैक होल" in res_space["full_narration"] or "अंतरिक्ष" in res_space["full_narration"]
    assert res_space["word_count"] <= 120


def test_condense_rule_based():
    engine = DirectorEngine()
    long_script = (
        "अगर आपको लगता है कि आप सब जानते हैं तो रुकिए! "
        "यह एक बहुत ही लंबी कहानी का पहला भाग है जहाँ हम अनेक रहस्यों की बात करेंगे। "
        "इसके बाद दूसरा दृश्य आता है जिसमें कई नए खुलासे और सबूत पेश किए जाते हैं। "
        "तीसरा दृश्य और भी गहरा है जहाँ वैज्ञानिक भी हैरान रह जाते हैं। "
        "चौथा दृश्य बताता है कि इतिहास में ऐसी घटनाएं पहले कभी नहीं देखी गईं। "
        "पाँचवाँ दृश्य इस बात की पुष्टि करता है कि पर्दे के पीछे कुछ बड़ा छुपाया जा रहा था। "
        "छठा दृश्य दुनिया भर के शोधकर्ताओं को अपनी सोच बदलने पर मजबूर कर देता है। "
        "सातवाँ दृश्य इस रहस्य को एक नए मोड़ पर ले जाता है। "
        "आठवाँ दृश्य सभी साक्ष्यों को एक साथ जोड़ता है। "
        "वीडियो को लाइक करें और चैनल को अभी सब्सक्राइब करें!"
    )
    condensed = engine._condense_rule_based(long_script, max_words=115)
    assert len(condensed.split()) <= 115
    assert condensed.startswith("अगर आपको लगता है")
    assert "सब्सक्राइब करें" in condensed
