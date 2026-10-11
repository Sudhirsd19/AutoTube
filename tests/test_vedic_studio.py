"""Unit and integration tests for Vedic & Granth Storyboard Studio."""

import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient

from autotube.media.director_engine import DirectorEngine
from autotube.web.app import app


@pytest.fixture
def client():
    return TestClient(app)


def test_breakdown_vedic_script_fallback():
    """Verify script breakdown correctly decomposes Hindi text and generates 8K English prompts."""
    director = DirectorEngine()
    script = (
        "क्या आप भी भविष्य की चिंता में अपना आज बर्बाद कर रहे हैं? "
        "कुरुक्षेत्र में अर्जुन के हाथ कांप रहे थे, क्योंकि उन्हें अपनी हार का डर था। "
        "तब भगवान कृष्ण ने कहा— पार्थ, तुम्हारा अधिकार केवल कर्म पर है, फल पर नहीं। "
        "हार केवल एक घटना है, आपकी पहचान नहीं।"
    )
    scenes = director.breakdown_vedic_script(script)
    assert isinstance(scenes, list)
    assert len(scenes) >= 3

    for s in scenes:
        assert "scene_number" in s
        assert "narration" in s
        assert "visual_prompt" in s
        assert len(s["visual_prompt"]) > 10
        # Prompts must be photorealistic 8k
        assert "8k" in s["visual_prompt"].lower() or "photorealistic" in s["visual_prompt"].lower()

    # Verify Arjuna scene gets Kurukshetra battlefield prompt
    arjuna_scene = next((s for s in scenes if "अर्जुन" in s["narration"]), None)
    assert arjuna_scene is not None
    assert "arjuna" in arjuna_scene["visual_prompt"].lower() or "kurukshetra" in arjuna_scene["visual_prompt"].lower()

    # Verify Krishna scene gets Lord Krishna on chariot prompt
    krishna_scene = next((s for s in scenes if "कृष्ण" in s["narration"] or "पार्थ" in s["narration"]), None)
    assert krishna_scene is not None
    assert "krishna" in krishna_scene["visual_prompt"].lower()


def test_prepare_scene_specs_preserves_custom_images():
    """Verify that user-uploaded custom_image_path is preserved in scene specs."""
    director = DirectorEngine()
    provided = [
        {
            "narration": "कुरुक्षेत्र में अर्जुन के हाथ कांप रहे थे।",
            "custom_image_path": "/tmp/custom_arjuna_4k.png",
            "visual_prompt": "Cinematic 8k shot of Arjuna",
        },
        {
            "narration": "तब भगवान कृष्ण ने कहा— पार्थ।",
            "custom_image_path": "/tmp/custom_krishna_4k.png",
            "visual_prompt": "Cinematic 8k shot of Krishna",
        }
    ]
    specs = director._prepare_scene_specs(
        script_text="कुरुक्षेत्र में अर्जुन। तब कृष्ण।",
        title="Gita Motivation",
        provided_scenes=provided,
        max_scenes=6,
    )
    assert len(specs) == 2
    assert specs[0]["custom_image_path"] == "/tmp/custom_arjuna_4k.png"
    assert specs[0]["visual_prompt"] == "Cinematic 8k shot of Arjuna"
    assert specs[1]["custom_image_path"] == "/tmp/custom_krishna_4k.png"


def test_api_vedic_breakdown(client):
    """Test POST /api/vedic/breakdown returns structured storyboard scenes."""
    payload = {
        "script_text": "क्या आप भी भविष्य की चिंता में अपना आज बर्बाद कर रहे हैं? कुरुक्षेत्र में अर्जुन के हाथ कांप रहे थे। तब भगवान कृष्ण ने कहा— पार्थ, तुम्हारा अधिकार केवल कर्म पर है।"
    }
    resp = client.post("/api/vedic/breakdown", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert isinstance(data["scenes"], list)
    assert len(data["scenes"]) >= 2
    assert "visual_prompt" in data["scenes"][0]


def test_api_vedic_upload_and_stream(client, tmp_path):
    """Test uploading an image and streaming it back."""
    # Create dummy image file bytes
    dummy_img = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15c4"
    files = {"file": ("test_scene_1.png", dummy_img, "image/png")}
    data = {"scene_index": "1"}

    upload_resp = client.post("/api/vedic/upload_image", data=data, files=files)
    assert upload_resp.status_code == 200
    res = upload_resp.json()
    assert res["success"] is True
    assert res["scene_index"] == 1
    assert "file_path" in res
    assert "stream_url" in res

    # Stream the file back
    stream_resp = client.get(res["stream_url"])
    assert stream_resp.status_code == 200
    assert stream_resp.headers["content-type"] in ("image/png", "application/octet-stream")


def test_api_stream_spiritual_bgm(client):
    """Test that /api/director/stream_bgm/spiritual resolves to an audio file without error."""
    resp = client.get("/api/director/stream_bgm/spiritual")
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "audio/mpeg"
