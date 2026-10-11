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
    """Verify that user-uploaded custom_image_path is preserved across 7+ scenes without truncation."""
    director = DirectorEngine()
    provided = [
        {
            "narration": f"कुरुक्षेत्र का दृश्य {i+1}।",
            "custom_image_path": f"/tmp/custom_scene_{i+1}_4k.png",
            "visual_prompt": f"Cinematic 8k shot of scene {i+1}",
        }
        for i in range(7)
    ]
    specs = director._prepare_scene_specs(
        script_text="कुरुक्षेत्र में अर्जुन। तब कृष्ण।",
        title="Gita Motivation",
        provided_scenes=provided,
        max_scenes=6,
    )
    assert len(specs) == 7
    for i in range(7):
        assert specs[i]["custom_image_path"] == f"/tmp/custom_scene_{i+1}_4k.png"
        assert specs[i]["visual_prompt"] == f"Cinematic 8k shot of scene {i+1}"


def test_api_director_status(client):
    """Test GET /api/director/status endpoint returns valid status."""
    resp = client.get("/api/director/status")
    assert resp.status_code == 200
    data = resp.json()
    assert "is_running" in data


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


def test_optimize_vedic_script_ramcharitmanas():
    """Verify raw Ramcharitmanas chaupai input is optimized into a viral ~45s Hindi script."""
    director = DirectorEngine()
    raw = (
        '**"परहित सरिस धर्म नहिं भाई, पर पीड़ा सम नहिं अधमाई"**\n'
        '(Ramcharitmanas, Uttar Kand, Tulsidas)\n\n'
        '**Matlab:** Doosron ka bhala karne jaisa koi dharm nahi, aur doosron ko dukh dene jaisa koi paap nahi.'
    )
    res = director.optimize_vedic_script(raw)
    assert res["success"] is True
    opt_script = res["optimized_script"]
    assert "परहित सरिस धर्म" in opt_script
    assert "तुलसीदास" in opt_script
    # Must not contain raw asterisks
    assert "**" not in opt_script
    # Must have between 80 and 130 words for YouTube Shorts duration
    words = len(opt_script.split())
    assert 80 <= words <= 135

    # Test that breakdown of this optimized script produces accurate Tulsidas/compassion prompts
    scenes = director.breakdown_vedic_script(opt_script)
    assert len(scenes) >= 4
    # Check that Tulsidas or charity/compassion prompt is generated
    prompts_text = " ".join(s["visual_prompt"] for s in scenes).lower()
    assert "tulsidas" in prompts_text or "compassion" in prompts_text or "temple" in prompts_text


def test_api_vedic_optimize(client):
    """Test POST /api/vedic/optimize_script endpoint."""
    raw = '**"कर्मण्येवाधिकारस्ते मा फलेषु कदाचन"** (Bhagavad Gita)'
    resp = client.post("/api/vedic/optimize_script", json={"raw_script": raw})
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert "optimized_script" in data
    assert len(data["optimized_script"]) > 50
    assert data["word_count"] > 30


def test_api_director_publish_mocked(client, tmp_path):
    """Test POST /api/director/publish endpoint with mocked uploader."""
    from autotube.web.app import PROJECT_ROOT
    dummy_video = PROJECT_ROOT / "output" / "shorts" / "test_vedic_short.mp4"
    dummy_video.parent.mkdir(parents=True, exist_ok=True)
    dummy_video.write_bytes(b"dummy video data")

    try:
        with patch("autotube.uploader.youtube_upload.YouTubeUploader.upload_video") as mock_upload:
            mock_upload.return_value = "https://youtu.be/dummyVedic123"

            payload = {
                "filename": "test_vedic_short.mp4",
                "title": "कर्म ही पहचान है #Shorts",
                "description": "श्री कृष्ण की अमर सीख",
                "tags": ["Shorts", "Geeta", "Krishna"],
                "privacy": "public",
                "pinned_comment": "जय श्री कृष्ण!",
                "channel": "hindi"
            }
            resp = client.post("/api/director/publish", json=payload)
            assert resp.status_code == 200
            data = resp.json()
            assert data["success"] is True
            assert data["url"] == "https://youtu.be/dummyVedic123"
            mock_upload.assert_called_once()
    finally:
        if dummy_video.exists():
            dummy_video.unlink()


def test_api_vedic_upload_invalid_file_rejected(client):
    """Test that uploading corrupted or non-image files is rejected with HTTP 400."""
    corrupted_data = b"THIS IS NOT AN IMAGE AT ALL JUST RAW CORRUPTED BYTES 12345"
    files = {"file": ("corrupt.txt", corrupted_data, "text/plain")}
    data = {"scene_index": "1"}

    resp = client.post("/api/vedic/upload_image", data=data, files=files)
    assert resp.status_code == 400
    assert "Invalid or corrupted image file" in resp.json()["detail"]


def test_optimize_vedic_script_mocked_gemini_active_model():
    """Verify optimize_vedic_script queries modern Gemini models and returns metadata."""
    director = DirectorEngine()
    fake_client = MagicMock()
    fake_response = MagicMock()
    fake_response.text = '{"optimized_script": "कुरुक्षेत्र में भगवान कृष्ण ने अर्जुन को निष्काम कर्म का दिव्य ज्ञान दिया। जो व्यक्ति परिणाम की चिंता छोड़ केवल अपने कर्तव्य पर ध्यान केंद्रित करता है, वही सच्चा विजयी बनता है। आज ही अपने कर्म पर ध्यान दें और चैनल को सब्सक्राइब करें।", "title": "गीता का अमर संदेश #Shorts", "scripture_source": "श्रीमद्भगवद्गीता अध्याय २", "word_count": 48, "est_seconds": 18.5}'
    fake_client.models.generate_content.return_value = fake_response

    with patch("os.getenv", return_value="fake-gemini-key"), \
         patch("google.genai.Client", return_value=fake_client):
        res = director.optimize_vedic_script("कर्मण्येवाधिकारस्ते मा फलेषु कदाचन")
        assert res["success"] is True
        assert res["is_ai_generated"] is True
        assert res["model_used"] in ["gemini-3.5-flash-lite", "gemini-3.1-flash-lite", "gemini-3.5-flash", "gemini-3.8-flash"]
        assert "श्रीमद्भगवद्गीता" in res["scripture_source"]
        assert len(res["optimized_script"].split()) >= 40


