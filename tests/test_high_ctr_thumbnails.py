"""Unit tests for High-CTR YouTube Thumbnail Generator and Web Endpoints."""

import pytest
from pathlib import Path
from PIL import Image
from fastapi.testclient import TestClient

from autotube.video.thumbnail import ThumbnailGenerator
from autotube.media.director_engine import DirectorEngine
from autotube.web.app import app
from autotube.config import PROJECT_ROOT


@pytest.fixture(autouse=True)
def disable_external_gemini_network(monkeypatch):
    """Prevent tests from hanging on live external Gemini network calls."""
    monkeypatch.setenv("GEMINI_API_KEY", "")


def test_thumbnail_generator_heuristic_hooks():
    """Verify heuristic 2-4 word hook extractor for Hindi and English."""
    tg = ThumbnailGenerator()

    # Hindi tests
    h1 = tg.extract_punchy_hook_text("हनुमान जी ने सूर्य को क्यों निगला था? जानिए रामायण का सच", language="hi")
    assert "हनुमान" in h1 or "रहस्य" in h1
    assert len(h1.split()) <= 5

    h2 = tg.extract_punchy_hook_text("भगवान शिव के तीसरे नेत्र का भयानक श्राप", language="hi")
    assert "श्राप" in h2 or "महादेव" in h2 or "शिव" in h2
    assert len(h2.split()) <= 5

    # English tests
    e1 = tg.extract_punchy_hook_text("The secret military files from Roswell 1947 alien interview", language="en")
    assert "ALIEN" in e1 or "SECRET" in e1 or "TRUTH" in e1
    assert len(e1.split()) <= 5


def test_generate_high_ctr_thumbnail_hindi_vedic(tmp_path):
    """Verify generating a 1280x720 High-CTR thumbnail in Devanagari Hindi."""
    tg = ThumbnailGenerator(width=1280, height=720)
    out_path = tmp_path / "test_vedic_thumb.jpg"

    res = tg.generate_high_ctr_thumbnail(
        title="हनुमान जी का महा-रहस्य",
        output_path=out_path,
        language="hi",
        topic_category="vedic",
        custom_hook_text="महा-विनाशकारी सच!",
    )

    assert res.exists()
    assert res.stat().st_size > 5000

    # Verify dimensions
    with Image.open(res) as img:
        assert img.size == (1280, 720)
        assert img.format == "JPEG"


def test_generate_high_ctr_thumbnail_english_mystery(tmp_path):
    """Verify generating a 1280x720 High-CTR thumbnail in English."""
    tg = ThumbnailGenerator(width=1280, height=720)
    out_path = tmp_path / "test_mystery_thumb.jpg"

    res = tg.generate_high_ctr_thumbnail(
        title="The Classified Project Stargate",
        output_path=out_path,
        language="en",
        topic_category="mystery",
        custom_hook_text="FORBIDDEN TRUTH!",
    )

    assert res.exists()
    assert res.stat().st_size > 5000

    with Image.open(res) as img:
        assert img.size == (1280, 720)


def test_api_director_thumbnail_generate_endpoint(tmp_path, monkeypatch):
    """Verify FastAPI /api/director/thumbnail/generate endpoint."""
    client = TestClient(app)

    # Create dummy video file
    dummy_dir = PROJECT_ROOT / "output" / "director"
    dummy_dir.mkdir(parents=True, exist_ok=True)
    dummy_video = dummy_dir / "test_api_thumb_video.mp4"
    dummy_video.write_bytes(b"dummy_video_bytes_for_testing")

    try:
        response = client.post("/api/director/thumbnail/generate", json={
            "filename": "test_api_thumb_video.mp4",
            "custom_hook_text": "1000 साल पुराना रहस्य!",
            "language": "hi",
            "topic_category": "vedic"
        })

        assert response.status_code == 200
        data = response.json()
        assert data.get("success") is True
        assert "thumbnail_filename" in data
        assert "thumbnail_url" in data

        expected_thumb = dummy_dir / "test_api_thumb_video_thumb.jpg"
        assert expected_thumb.exists()
        assert expected_thumb.stat().st_size > 5000
    finally:
        if dummy_video.exists():
            dummy_video.unlink()
        thumb_f = dummy_dir / "test_api_thumb_video_thumb.jpg"
        if thumb_f.exists():
            thumb_f.unlink()
