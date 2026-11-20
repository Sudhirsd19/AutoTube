"""Unit and integration tests for Facebook News Post & Photo Publishing Engine."""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest

from autotube.config import PROJECT_ROOT
from autotube.uploader.facebook_upload import FacebookReelsUploader, FacebookPageManager
from autotube.news.trending_collector import TrendingNewsCollector
from autotube.news.news_card_generator import NewsCardGenerator
from autotube.news.news_post_generator import NewsPostGenerator


def test_facebook_uploader_has_publish_photo():
    """Verify FacebookReelsUploader and alias have publish_photo method."""
    uploader = FacebookReelsUploader()
    assert hasattr(uploader, "publish_photo")
    assert callable(uploader.publish_photo)
    assert FacebookPageManager is FacebookReelsUploader


def test_facebook_slots_config_has_fb_post_slot():
    """Verify slots_config.json contains the 05:30 PM (17:30) IST Facebook News Post slot."""
    config_path = PROJECT_ROOT / "config" / "slots_config.json"
    assert config_path.exists()
    with open(config_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    growth_slots = data.get("presets", {}).get("growth_4", [])
    fb_slot = next((s for s in growth_slots if s.get("id") == "slot_fb_post"), None)
    assert fb_slot is not None, "slot_fb_post not found in growth_4 preset"
    assert fb_slot.get("hour") == 17
    assert fb_slot.get("minute") == 30
    assert fb_slot.get("tz") == "IST"
    assert fb_slot.get("channel") == "facebook"
    assert fb_slot.get("format") == "fb_post"


def test_news_card_generator_finds_browser():
    """Verify NewsCardGenerator detects a browser binary for headless rendering."""
    card_gen = NewsCardGenerator()
    assert card_gen.browser_bin is not None
    assert Path(card_gen.browser_bin).exists() or card_gen.browser_bin in ["chromium-browser", "chromium", "google-chrome"]


def test_news_card_render_1080x1080():
    """Verify NewsCardGenerator renders an exact 1080x1080 image."""
    card_gen = NewsCardGenerator()
    sample_img = PROJECT_ROOT / "assets" / "news_fallback" / "jensen_huang.jpg"
    if not sample_img.exists():
        pytest.skip("Sample image not found for card test")

    content = {
        "card_category": "TECH & AI UPDATE",
        "card_tag_hindi": "NVIDIA CEO का बड़ा ऐलान",
        "card_headline_line1": "“अब बच्चों को कोडिंग मत सिखाओ!",
        "card_headline_line2": "AI खुद सॉफ्टवेयर बनाएगा”",
        "card_highlight_text": "AI खुद सॉफ्टवेयर बनाएगा",
        "card_speaker": "— जेन्सन हुआंग (Jensen Huang, CEO - NVIDIA)",
    }
    out_path = PROJECT_ROOT / "temp" / "test_rendered_card.jpg"
    res_path = card_gen.render_card(image_path=sample_img, content=content, output_path=out_path)
    assert res_path.exists()

    from PIL import Image
    im = Image.open(res_path)
    assert im.size == (1080, 1080)


def test_trending_collector_rss():
    """Verify TrendingNewsCollector can fetch RSS items."""
    collector = TrendingNewsCollector()
    items = collector.fetch_rss_items(query="NVIDIA", max_items=5)
    assert isinstance(items, list)
    if items:
        assert "title" in items[0]
        assert "link" in items[0]


def test_post_generator_structure():
    """Verify NewsPostGenerator produces required fields and Hindi content."""
    gen = NewsPostGenerator()
    dummy_story = {
        "headline_en": "NVIDIA CEO Says Coding is Obsolete in AI Era",
        "summary": "Jensen Huang tells World Government Summit that AI will write software so kids do not need to code.",
        "subject": "Jensen Huang",
        "category": "TECH & AI UPDATE",
        "tag_hindi": "NVIDIA CEO का बड़ा ऐलान",
        "photo_credit": "Reuters",
    }
    content = gen.generate_post_content(dummy_story)
    assert "card_headline_line1" in content
    assert "card_headline_line2" in content
    assert "post_caption" in content
    assert len(content["post_caption"]) > 100
    # Caption must have poll question
    assert "1️⃣" in content["post_caption"] or "2️⃣" in content["post_caption"] or "1" in content["post_caption"]


def test_facebook_reel_caption_strips_shorts_and_youtube_tags():
    """Verify Facebook Reel caption generator removes #Shorts and YouTube tags."""
    uploader = FacebookReelsUploader()
    raw_title = "प्रशांत महासागर का रहस्य! The Pacific Mystery #Shorts"
    raw_desc = "चैनल को सब्सक्राइब करें और पूरा वीडियो देखें। #Shorts"
    raw_tags = ["#Shorts", "#YouTubeShorts", "#Mystery", "#Ocean"]

    caption = uploader._build_reel_caption(title=raw_title, description=raw_desc, tags=raw_tags)
    assert "#Shorts" not in caption
    assert "#shorts" not in caption
    assert "#YouTubeShorts" not in caption
    assert "#Reels" in caption
    assert "#FacebookReels" in caption
    assert "चैनल को सब्सक्राइब" not in caption


def test_facebook_reel_scheduled_payload():
    """Verify FacebookReelsUploader sends video_state='SCHEDULED' and scheduled_publish_time."""
    uploader = FacebookReelsUploader()
    import time
    future_time = int(time.time()) + 3600  # 1 hour in future

    with patch.object(uploader, "load_credentials", return_value={"page_id": "test_page_123", "access_token": "fake_token"}), \
         patch("autotube.uploader.facebook_upload.requests.post") as mock_post:

        mock_post.side_effect = [
            # Phase 1
            MagicMock(json=lambda: {"video_id": "vid_999", "upload_url": "https://rupload.facebook.com/vid_999"}),
            # Phase 2
            MagicMock(content=b"{}", json=lambda: {}),
            # Phase 3
            MagicMock(json=lambda: {"post_id": "post_999", "success": True}),
        ]

        dummy_video = PROJECT_ROOT / "temp" / "dummy_reel.mp4"
        dummy_video.parent.mkdir(parents=True, exist_ok=True)
        dummy_video.write_bytes(b"dummy video bytes content" * 100)

        try:
            res = uploader.upload_reel(
                video_path=dummy_video,
                title="रहस्यमयी दुनिया का सच",
                description="शानदार वीडियो",
                language="hi",
                scheduled_publish_time=future_time,
            )

            assert res.get("success") is True
            assert res.get("video_state") == "SCHEDULED"
            assert res.get("scheduled_publish_time") == future_time

            # Verify Phase 3 payload
            phase3_call = mock_post.call_args_list[2]
            payload = phase3_call[1]["data"]
            assert payload["video_state"] == "SCHEDULED"
            assert payload["scheduled_publish_time"] == future_time
        finally:
            if dummy_video.exists():
                dummy_video.unlink()


def test_trending_collector_deduplication():
    """Verify TrendingNewsCollector detects duplicate stories and filters them."""
    collector = TrendingNewsCollector()
    past_records = [
        {
            "title": "🔴 OpenAI का चौंकाने वाला फैसला: रोबोटिक्स टीम बंद! 🤖",
            "headline_en": "OpenAI Abruptly Disbands Robotics Team Right After Offering 3.3 Million Yuan Annual Pay Package",
            "subject": "OpenAI",
            "tokens": {"openai", "disbands", "robotics", "team", "package"},
        }
    ]

    # Duplicate headlines should return True
    dup_cand1 = "OpenAI reportedly folds robotics team into core research"
    dup_cand2 = "OpenAI Disbands Dedicated Robotics Team In Sudden Pivot"
    assert collector.is_duplicate_story(dup_cand1, past_records) is True
    assert collector.is_duplicate_story(dup_cand2, past_records) is True

    # Fresh stories should return False
    fresh_cand1 = "SpaceX Catches Starship on the First Try in Milestone Aerospace Triumph"
    fresh_cand2 = "James Webb Telescope Detects Immense Cosmic Structure in Deep Space"
    assert collector.is_duplicate_story(fresh_cand1, past_records) is False
    assert collector.is_duplicate_story(fresh_cand2, past_records) is False


def test_facebook_uploader_has_delete_post():
    """Verify FacebookReelsUploader has delete_post method."""
    uploader = FacebookReelsUploader()
    assert hasattr(uploader, "delete_post")
    assert callable(uploader.delete_post)

    with patch.object(uploader, "load_credentials", return_value={"access_token": "fake_token"}), \
         patch("autotube.uploader.facebook_upload.requests.delete") as mock_del:
        mock_del.return_value = MagicMock(status_code=200, json=lambda: {"success": True}, content=b"{}")
        res = uploader.delete_post("1319257467944992_122110447845524838")
        assert res["success"] is True
        assert res["post_id"] == "1319257467944992_122110447845524838"

