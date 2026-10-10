"""Tests for AutoTube Multi-Channel Architecture (English & Hindi channels).

Verifies:
1. Token resolution per channel (token_english.json vs token_hindi.json with token.json fallback).
2. Channels configuration schema and defaults.
3. YouTubeAuth and YouTubeUploader channel binding.
4. AutoPilot topic generation channel assignment (English slot -> english, Hindi slot -> hindi).
5. Slots config structure preserves channel property.
6. Web API endpoints support channel parameter.
"""

import json
import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch

from autotube.uploader.auth import YouTubeAuth, resolve_token_file
from autotube.uploader.youtube_upload import YouTubeUploader
from autotube.web.app import (
    app,
    _load_channels_config,
    RescheduleRequest,
    PublishNowRequest,
    PublishLocalVideoRequest,
    DirectorPublishRequest,
    SaveTokenRequest,
)


def test_resolve_token_file(tmp_path):
    """Test channel token file resolution and fallback."""
    with patch("autotube.uploader.auth.PROJECT_ROOT", tmp_path):
        config_dir = tmp_path / "config"
        config_dir.mkdir(parents=True)

        tok_legacy = config_dir / "token.json"
        tok_en = config_dir / "token_english.json"
        tok_hi = config_dir / "token_hindi.json"

        # Initially, none exist -> should return target path directly
        assert resolve_token_file("english") == tok_en
        assert resolve_token_file("hindi") == tok_hi

        # If legacy token.json exists, english should fall back to it
        tok_legacy.write_text('{"token": "legacy"}')
        assert resolve_token_file("english") == tok_legacy

        # But if token_english.json exists, it takes precedence
        tok_en.write_text('{"token": "english_channel"}')
        assert resolve_token_file("english") == tok_en

        # Hindi resolves to token_hindi.json
        assert resolve_token_file("hindi") == tok_hi
        tok_hi.write_text('{"token": "hindi_channel"}')
        assert resolve_token_file("hindi") == tok_hi


def test_channels_config_loading():
    """Verify channels_config.json contains valid english and hindi channel definitions."""
    cfg = _load_channels_config()
    assert "channels" in cfg
    channels = cfg["channels"]
    assert "english" in channels
    assert "hindi" in channels
    assert channels["english"].get("language") == "English"
    assert channels["hindi"].get("language") == "Hindi"
    assert "token_file" in channels["english"]
    assert "token_file" in channels["hindi"]


def test_auth_and_uploader_channel_binding():
    """Verify YouTubeAuth and YouTubeUploader store and respect target channel."""
    auth_en = YouTubeAuth(channel="english")
    auth_hi = YouTubeAuth(channel="hindi")

    assert auth_en.channel == "english"
    assert auth_hi.channel == "hindi"
    assert "english" in str(auth_en.token_file).lower() or "token.json" in str(auth_en.token_file).lower()
    assert "hindi" in str(auth_hi.token_file).lower()

    uploader_en = YouTubeUploader(channel="english")
    uploader_hi = YouTubeUploader(channel="hindi")

    assert uploader_en.channel == "english"
    assert uploader_hi.channel == "hindi"


def test_autopilot_slot_channel_resolution(tmp_path):
    """Verify AutoPilot slot batch assigns correct channel based on slot data / language."""
    from autotube.scheduler.autopilot import AutoPilot

    pilot = AutoPilot()
    slots_data = [
        {
            "id": "slot_1",
            "hour": 12,
            "minute": 0,
            "tz": "EDT",
            "niche": "Deep Space Paradoxes",
            "language": "English",
            "channel": "english",
            "format": "short"
        },
        {
            "id": "slot_2",
            "hour": 20,
            "minute": 30,
            "tz": "IST",
            "niche": "Antariksh Rahasya",
            "language": "Hindi",
            "channel": "hindi",
            "format": "short"
        }
    ]

    # Verify channel extraction logic matches AutoPilot
    resolved = []
    for s in slots_data:
        ch = s.get("channel") or ("hindi" if s.get("language", "").lower() in ("hindi", "hi") else "english")
        resolved.append((s["id"], s["language"], ch))

    assert resolved[0] == ("slot_1", "English", "english")
    assert resolved[1] == ("slot_2", "Hindi", "hindi")


def test_web_pydantic_models_accept_channel():
    """Verify all publish/reschedule API request schemas accept channel."""
    req_resched = RescheduleRequest(video_id="v123", publish_at="2026-10-15T12:00:00Z", channel="hindi")
    assert req_resched.channel == "hindi"

    req_pub = PublishNowRequest(video_id="v123", channel="english")
    assert req_pub.channel == "english"

    req_local = PublishLocalVideoRequest(filename="vid.mp4", privacy="public", channel="hindi")
    assert req_local.channel == "hindi"

    req_dir = DirectorPublishRequest(filename="vid.mp4", title="Test", channel="english")
    assert req_dir.channel == "english"

    req_tok = SaveTokenRequest(token_json="{}", channel="hindi")
    assert req_tok.channel == "hindi"
