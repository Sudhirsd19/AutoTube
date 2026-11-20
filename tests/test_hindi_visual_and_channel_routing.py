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
    """Verify ScriptGenerator's Hindi subject outro includes dignified subscription CTA."""
    from autotube.scripting.generator import get_subject_outro_text
    
    outro_space = get_subject_outro_text("Space Black Holes", language="hi")
    assert "सब्सक्राइब करें" in outro_space
    
    outro_gita = get_subject_outro_text("Bhagavad Gita Karma", language="hi")
    assert "सब्सक्राइब करें" in outro_gita
    
    outro_mandir = get_subject_outro_text("Kailasa Temple Mystery", language="hi")
    assert "सब्सक्राइब करें" in outro_mandir


def test_extract_hindi_subject_purity():
    """Verify that extract_hindi_subject always returns pure Devanagari Hindi with zero English words."""
    from autotube.scripting.generator import extract_hindi_subject
    import re

    # 1. English topic with stupa / brick
    subj1 = extract_hindi_subject("The 1,500-year-old 'Self-Cooling' brick chemistry of ancient stupas")
    assert any('\u0900' <= c <= '\u097f' for c in subj1)
    assert not re.search(r'[a-zA-Z]', subj1)

    # 2. English topic with animal / jellyfish
    subj2 = extract_hindi_subject("The Immortal Jellyfish biological glitch that reverses aging")
    assert any('\u0900' <= c <= '\u097f' for c in subj2)
    assert not re.search(r'[a-zA-Z]', subj2)

    # 3. English topic with space / black hole
    subj3 = extract_hindi_subject("Why You Would Age Backwards Near a Supermassive Neutron Star")
    assert any('\u0900' <= c <= '\u097f' for c in subj3)
    assert not re.search(r'[a-zA-Z]', subj3)

    # 4. Mixed Hindi topic with English parenthetical
    subj4 = extract_hindi_subject("अमर जेलीफ़िश (Immortal Jellyfish) का जैविक चमत्कार")
    assert any('\u0900' <= c <= '\u097f' for c in subj4)
    assert not re.search(r'[a-zA-Z]', subj4)


def test_generator_hindi_fallback_zero_english_in_narration():
    """Verify that ScriptGenerator fallback for Hindi produces 100% pure Devanagari with ZERO English words in spoken narration."""
    from autotube.scripting.generator import ScriptGenerator
    import re

    gen = ScriptGenerator()
    english_topic = (
        "The 1,500-year-old 'Self-Cooling' brick chemistry of ancient stupas: "
        "How did architects bake ceramic-like bricks that absorb 95% of heat while maintaining structural integrity for centuries?"
    )
    script = gen._generate_fallback_short(
        topic=english_topic,
        target_duration=25,
        language="hi",
    )

    assert script.scenes and len(script.scenes) >= 3
    for s in script.scenes:
        # Spoken narration must have Devanagari
        assert any('\u0900' <= c <= '\u097f' for c in s.narration)
        # Spoken narration must have ZERO English words (no Latin character words >= 2 chars)
        assert not re.search(r'[a-zA-Z]{2,}', s.narration), f"Found English word in narration: '{s.narration}'"

    # Title must have Devanagari and no long English phrases
    assert any('\u0900' <= c <= '\u097f' for c in script.title)
    assert "The 1,500-year-old" not in script.title


def test_trend_finder_hindi_fallback_purity():
    """Verify that TrendFinder produces pure Devanagari Hindi topics when fallback pool is used."""
    from autotube.scripting.trend_finder import TrendFinder

    tf = TrendFinder()
    # Mock client as None to test fallback
    tf.cfg.gemini_api_key = None
    topic = tf.get_single_topic(niche="ancient_engineering", language="hi")
    assert any('\u0900' <= c <= '\u097f' for c in topic)


def test_render_facebook_variant_updates_props_with_fb_follow_hook(tmp_path):
    """Verify that render_facebook_variant modifies Remotion props to use fb_follow_like_banner and follow hook text."""
    import json
    from autotube.video.remotion_bridge import RemotionBridge, REMOTION_PUBLIC_DIR

    bridge = RemotionBridge()
    test_slug = "test_jellyfish_reel"
    props_path = REMOTION_PUBLIC_DIR / "demo-props" / f"{test_slug}.json"
    props_path.parent.mkdir(parents=True, exist_ok=True)

    fake_props = {
        "cuts": [{"id": "scene-1", "out_seconds": 25.0}],
        "overlays": [
            {
                "type": "subscribe_cta",
                "text": "लाइक और सब्सक्राइब करें",
                "subtitle": "🔔 नए वीडियो के लिए सब्सक्राइब करें",
                "imageSrc": "assets/like_subscribe_bell_banner.png",
                "accentColor": "#EF4444",
            }
        ],
    }
    with open(props_path, "w", encoding="utf-8") as f:
        json.dump(fake_props, f)

    fake_video = tmp_path / f"{test_slug}.mp4"
    fake_video.write_bytes(b"dummy")
    fb_dest = tmp_path / f"{test_slug}_fb.mp4"

    def mock_subprocess_side_effect(*args, **kwargs):
        fb_dest.write_bytes(b"dummy fb video " * 5000)
        return MagicMock(returncode=0)

    with patch("subprocess.run", side_effect=mock_subprocess_side_effect):
        res = bridge.render_facebook_variant(slug=test_slug, original_video_path=fake_video)
        assert res == fb_dest

        fb_props_path = REMOTION_PUBLIC_DIR / "demo-props" / f"{test_slug}_fb.json"
        assert fb_props_path.exists()
        with open(fb_props_path, "r", encoding="utf-8") as f:
            fb_data = json.load(f)

        cta = next(o for o in fb_data["overlays"] if o["type"] == "subscribe_cta")
        assert cta["text"] == "लाइक और फॉलो करें"
        assert "फॉलो करें" in cta["subtitle"]
        assert "fb_follow_like_banner.png" in cta["imageSrc"]

    # Clean up
    try:
        props_path.unlink()
        (REMOTION_PUBLIC_DIR / "demo-props" / f"{test_slug}_fb.json").unlink()
    except Exception:
        pass


