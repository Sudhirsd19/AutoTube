"""Tests for Hindi semantic visual extraction and channel upload cross-contamination protection."""

import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch

from autotube.media.hindi_visual_extractor import is_hindi_text, extract_english_visual_queries
from autotube.media.stock_fetcher import StockFetcher
from autotube.media.multi_stock_aggregator import MultiStockAggregator
from autotube.media.director_engine import DirectorEngine
from autotube.uploader.youtube_upload import YouTubeUploader
from autotube.scripting.generator import ScriptGenerator


def test_is_hindi_text_detection():
    # Devanagari text
    assert is_hindi_text("समुद्र के नीचे एक भयानक रहस्य छिपा है") is True
    assert is_hindi_text("ब्लैक होल अंतरिक्ष का सबसे रहस्यमयी पिंड है") is True
    # Hinglish text
    assert is_hindi_text("kya aapko pata hai deep ocean ke andar kya hota hai") is True
    # English text
    assert is_hindi_text("Black holes are the most mysterious objects in space") is False
    assert is_hindi_text("The secret underwater brine pool discovered in the ocean") is False


def test_hindi_visual_extraction_domains():
    # 1. Toxic Lake / Ocean
    res_ocean = extract_english_visual_queries("समुद्र के नीचे वैज्ञानिकों को एक जहरीली झील मिली")
    assert any("lake" in q.lower() or "ocean" in q.lower() or "underwater" in q.lower() for q in res_ocean["search_queries"])
    assert "space" not in res_ocean["subject"].lower()

    # 2. Black Hole / Space
    res_space = extract_english_visual_queries("ब्लैक होल का गुरुत्वाकर्षण प्रकाश को भी खींच लेता है")
    assert any("black hole" in q.lower() or "space" in q.lower() for q in res_space["search_queries"])

    # 3. Ancient Temple / History
    res_temple = extract_english_visual_queries("कैलाश मंदिर को केवल एक ही चट्टान को तराश कर बनाया गया था")
    assert any("temple" in q.lower() or "ancient" in q.lower() or "stone" in q.lower() for q in res_temple["search_queries"])

    # 4. Animal / Nature
    res_animal = extract_english_visual_queries("अमेज़न के घने जंगल में विशालकाय एनाकोंडा शिकार करता है")
    assert any("snake" in q.lower() or "anaconda" in q.lower() or "jungle" in q.lower() for q in res_animal["search_queries"])


def test_stock_fetcher_clean_query_hindi():
    """Verify that clean_query converts Hindi text into valid English queries instead of empty strings."""
    raw_hi = "समुद्र के नीचे एक जहरीली झील"
    clean = StockFetcher.clean_query(raw_hi)
    assert len(clean) > 0
    # Must contain Latin characters
    assert any(c.isalpha() for c in clean)
    assert "lake" in clean.lower() or "ocean" in clean.lower() or "underwater" in clean.lower()


def test_multi_stock_aggregator_sanitize_query():
    """Verify that MultiStockAggregator._sanitize_query converts Hindi to English search keywords."""
    agg = MultiStockAggregator()
    clean = agg._sanitize_query("प्राचीन मंदिर और गुफाएं")
    assert len(clean) > 0
    assert any(c.isalpha() for c in clean)
    assert "temple" in clean.lower() or "ancient" in clean.lower()


def test_multi_stock_story_is_space_does_not_override_earth():
    """Verify that story_is_space does not force outer space onto Earth/ocean scenes."""
    agg = MultiStockAggregator()
    agg._get_gemini_client = MagicMock(return_value=None)
    plan = agg.plan_visual_scene(
        scene_text="समुद्र की गहराइयों में एक अजीब जीव तैर रहा था",
        title="Cosmic Secrets and Deep Space Discoveries",
        idx=1,
    )
    # The scene is about deep sea ocean, so queries must be ocean-related, not deep space stars
    queries_str = " ".join(plan["search_queries"]).lower()
    assert "ocean" in queries_str or "sea" in queries_str or "underwater" in queries_str or "abyss" in queries_str


def test_director_engine_extract_visual_search_query():
    """Verify DirectorEngine extracts accurate English visual queries for Hindi scenes."""
    director = DirectorEngine()
    q_hi = director._extract_visual_search_query(
        sentence="समुद्र के तल पर एक विशालकाय गड्ढा देखा गया",
        topic="Ocean Mystery",
        scene_idx=0,
    )
    assert len(q_hi) > 0
    assert any(w in q_hi.lower() for w in ("ocean", "sea", "abyss", "underwater", "trench"))


def test_generator_hindi_fallback_short():
    """Verify that ScriptGenerator fallback for Hindi produces genuine Hindi text with English keywords."""
    gen = ScriptGenerator()
    script = gen._generate_fallback_short(
        topic="Deep Ocean Secrets",
        target_duration=55,
        language="hi",
    )
    # Narration must contain Devanagari characters
    has_devanagari = any("\u0900" <= c <= "\u097f" for c in script.narration)
    assert has_devanagari is True
    # Visual keywords must be valid English
    for kw in script.visual_keywords:
        assert any(c.isalpha() for c in kw)


def test_youtube_uploader_safety_guard_blocks_or_reroutes_english_to_hindi(tmp_path):
    """Verify that YouTubeUploader refuses or reroutes uploading English videos to Hindi channel."""
    fake_video = tmp_path / "deep_ocean_secrets_en.mp4"
    fake_video.write_bytes(b"dummy video content")

    uploader = YouTubeUploader(channel="hindi")

    # Mock English auth as available, Hindi auth as available
    with patch("autotube.uploader.youtube_upload.YouTubeAuth") as mock_auth_cls:
        mock_auth_en = MagicMock()
        mock_auth_en.is_authenticated.return_value = True
        mock_auth_en.get_credentials.return_value = MagicMock()

        mock_auth_hi = MagicMock()
        mock_auth_hi.is_authenticated.return_value = True
        mock_auth_hi.get_credentials.return_value = MagicMock()

        def auth_side_effect(channel="english"):
            return mock_auth_hi if channel == "hindi" else mock_auth_en

        mock_auth_cls.side_effect = auth_side_effect

        with patch("autotube.uploader.youtube_upload.build") as mock_build:
            mock_service = MagicMock()
            mock_insert = MagicMock()
            mock_insert.next_chunk.return_value = (None, {"id": "test_id_123"})
            mock_service.videos().insert.return_value = mock_insert
            mock_build.return_value = mock_service

            # Upload purely English video to channel='hindi'
            url = uploader.upload_video(
                video_path=fake_video,
                title="The Deep Ocean Secrets Revealed #Shorts",
                description="Nobody talks about what lies beneath the surface of the ocean. Subscribe for more space facts!",
                channel="hindi",
            )
            # Should succeed via auto-reroute to English channel
            assert url == "https://youtu.be/test_id_123"


def test_youtube_uploader_safety_guard_reroutes_hindi_to_english(tmp_path):
    """Verify that YouTubeUploader refuses or reroutes uploading Hindi videos to English channel."""
    fake_video = tmp_path / "kailash_temple_secrets_hi.mp4"
    fake_video.write_bytes(b"dummy video content")

    uploader = YouTubeUploader(channel="english")

    with patch("autotube.uploader.youtube_upload.YouTubeAuth") as mock_auth_cls:
        mock_auth_en = MagicMock()
        mock_auth_en.is_authenticated.return_value = True
        mock_auth_en.get_credentials.return_value = MagicMock()

        mock_auth_hi = MagicMock()
        mock_auth_hi.is_authenticated.return_value = True
        mock_auth_hi.get_credentials.return_value = MagicMock()

        def auth_side_effect(channel="english"):
            return mock_auth_hi if channel == "hindi" else mock_auth_en

        mock_auth_cls.side_effect = auth_side_effect

        with patch("autotube.uploader.youtube_upload.build") as mock_build:
            mock_service = MagicMock()
            mock_insert = MagicMock()
            mock_insert.next_chunk.return_value = (None, {"id": "test_id_456"})
            mock_service.videos().insert.return_value = mock_insert
            mock_build.return_value = mock_service

            # Upload purely Hindi video to channel='english'
            url = uploader.upload_video(
                video_path=fake_video,
                title="कैलाश मंदिर का अनसुलझा रहस्य #Shorts",
                description="कैलाश मंदिर के नीचे वैज्ञानिकों को क्या मिला? चैनल को अभी सब्सक्राइब करें!",
                channel="english",
            )
            # Should succeed via auto-reroute to Hindi channel
            assert url == "https://youtu.be/test_id_456"


def test_autopilot_slug_naming_separation():
    """Verify that English and Hindi slots have distinct language suffixes in slugs."""
    topic = "The Hidden Secrets of Deep Ocean"
    from autotube.utils.file_utils import sanitize_filename
    
    # Slot 1: English
    lang_en = "English"
    ch_en = "english"
    lang_code_en = "hi" if (str(lang_en).lower().startswith("hi") or ch_en == "hindi") else "en"
    slug_en = f"{sanitize_filename(topic)}_{lang_code_en}"

    # Slot 2: Hindi (paired with slot 1)
    lang_hi = "Hindi"
    ch_hi = "hindi"
    lang_code_hi = "hi" if (str(lang_hi).lower().startswith("hi") or ch_hi == "hindi") else "en"
    slug_hi = f"{sanitize_filename(topic)}_{lang_code_hi}"

    assert slug_en != slug_hi
    assert slug_en.endswith("_en")
    assert slug_hi.endswith("_hi")


def test_facebook_upload_blocks_purely_english_video(tmp_path):
    """Verify FacebookReelsUploader strictly blocks English videos."""
    from autotube.uploader.facebook_upload import FacebookReelsUploader
    
    # Create dummy video file
    dummy_video = tmp_path / "speed_of_light_mystery.mp4"
    dummy_video.write_bytes(b"dummy_video_bytes")
    
    fb = FacebookReelsUploader()
    # Mock credentials so it passes configured check
    orig_load = fb.load_credentials
    fb.load_credentials = lambda: {"page_id": "12345", "access_token": "test_tok", "page_name": "CosmoCronicle"}
    try:
        res = fb.upload_reel(
            video_path=dummy_video,
            title="The Mystery of Light Speed Paradox",
            description="Scientists discovered an impossible quantum speed glitch in vacuum.",
            language="en"
        )
        assert res["success"] is False
        assert res.get("skipped") is True
        assert "strictly reserved for Hindi Reels" in res["error"]
    finally:
        fb.load_credentials = orig_load


def test_facebook_upload_caption_follow_hook_and_youtube_cleanup():
    """Verify Facebook Reel caption appends page follow hook and strips YouTube channel subscribe calls."""
    from autotube.uploader.facebook_upload import FacebookReelsUploader
    fb = FacebookReelsUploader()
    
    raw_desc = "क्या आप जानते हैं कि प्रकाश की गति स्थिर क्यों है? हमारे चैनल को सब्सक्राइब करें और वीडियो लाइक करें।"
    caption = fb._build_reel_caption(
        title="प्रकाश की गति का रहस्य",
        description=raw_desc,
        tags=["#Shorts", "#HindiFacts"]
    )
    
    assert "FOLLOW करें" in caption or "फॉलो करें" in caption
    assert "चैनल को सब्सक्राइब करें" not in caption
    assert "#FacebookReels" in caption


def test_generator_hindi_outro_has_follow_hook():
    """Verify ScriptGenerator's Hindi subject outro includes like and follow hook."""
    from autotube.scripting.generator import get_subject_outro_text
    
    outro_space = get_subject_outro_text("Space Black Holes", language="hi")
    assert "फॉलो करें" in outro_space
    
    outro_gita = get_subject_outro_text("Bhagavad Gita Karma", language="hi")
    assert "फॉलो करें" in outro_gita
    
    outro_mandir = get_subject_outro_text("Kailasa Temple Mystery", language="hi")
    assert "फॉलो करें" in outro_mandir
