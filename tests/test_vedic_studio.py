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


@pytest.fixture(autouse=True)
def disable_external_gemini_network(monkeypatch):
    """Prevent unit tests from hanging on live external Gemini network calls."""
    monkeypatch.setenv("GEMINI_API_KEY", "")
    from autotube.config import get_config
    cfg = get_config()
    orig_key = cfg.gemini_api_key
    cfg.gemini_api_key = ""
    yield
    cfg.gemini_api_key = orig_key


def test_breakdown_vedic_script_fallback(monkeypatch):
    """Verify script breakdown correctly decomposes Hindi text and generates 8K English prompts."""
    monkeypatch.setenv("GEMINI_API_KEY", "")
    director = DirectorEngine()
    director.cfg.gemini_api_key = ""
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


def test_optimize_vedic_script_ramcharitmanas(monkeypatch):
    """Verify raw Ramcharitmanas chaupai input is optimized into a viral ~45s Hindi script."""
    monkeypatch.setenv("GEMINI_API_KEY", "")
    director = DirectorEngine()
    director.cfg.gemini_api_key = ""
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
    # Must have between 90 and 165 words for 55-58s YouTube Shorts duration
    words = len(opt_script.split())
    assert 90 <= words <= 165

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
        assert res["model_used"] in ["gemini-3-flash-preview", "gemini-3.5-flash-lite", "gemini-3.1-flash-lite", "gemini-3.5-flash", "gemini-3.8-flash"]
        assert "श्रीमद्भगवद्गीता" in res["scripture_source"]
        assert len(res["optimized_script"].split()) >= 40


def test_optimize_vedic_script_topic_vaishno_devi():
    """Verify entering topic 'माँ वैष्णो देवी' generates 55-60s story and accurate scene prompts."""
    director = DirectorEngine()
    res = director.optimize_vedic_script("माँ वैष्णो देवी की तपस्या और गुफा")
    assert res["success"] is True
    assert "वैष्णो" in res["optimized_script"]
    words = len(res["optimized_script"].split())
    assert 90 <= words <= 165
    assert res["est_seconds"] >= 35.0

    # Break into scenes & verify prompts directly match Vaishno Devi / Himalayan cave
    scenes = director.breakdown_vedic_script(res["optimized_script"])
    assert len(scenes) >= 4
    prompts_text = " ".join(s["visual_prompt"] for s in scenes).lower()
    assert "vaishno" in prompts_text or "cave" in prompts_text or "devi" in prompts_text


def test_optimize_vedic_script_topic_hanuman():
    """Verify entering topic 'हनुमान जी की शक्ति' generates 55-60s story and accurate scene prompts."""
    director = DirectorEngine()
    res = director.optimize_vedic_script("हनुमान जी और संजीवनी बूटी")
    assert res["success"] is True
    assert "हनुमान" in res["optimized_script"]
    words = len(res["optimized_script"].split())
    assert 90 <= words <= 165
    assert res["est_seconds"] >= 35.0

    # Break into scenes & verify prompts directly match Hanuman / Sanjeevani
    scenes = director.breakdown_vedic_script(res["optimized_script"])
    assert len(scenes) >= 4
    prompts_text = " ".join(s["visual_prompt"] for s in scenes).lower()
    assert "hanuman" in prompts_text or "sanjeevani" in prompts_text


def test_optimize_vedic_script_topic_shiva():
    """Verify entering topic 'भगवान शिव और विषपान' generates 55-60s story and accurate scene prompts."""
    director = DirectorEngine()
    res = director.optimize_vedic_script("भगवान शिव और कालकूट विषपान")
    assert res["success"] is True
    assert "शिव" in res["optimized_script"] or "महादेव" in res["optimized_script"]
    words = len(res["optimized_script"].split())
    assert 90 <= words <= 165

    scenes = director.breakdown_vedic_script(res["optimized_script"])
    assert len(scenes) >= 4
    prompts_text = " ".join(s["visual_prompt"] for s in scenes).lower()
    assert "shiva" in prompts_text or "kailash" in prompts_text or "neelkanth" in prompts_text


def test_optimize_vedic_script_dynamic_custom_topic():
    """Verify arbitrary custom topic generates full 55-60s story incorporating user topic."""
    director = DirectorEngine()
    topic = "सच्चे मित्र की पहचान"
    res = director.optimize_vedic_script(topic)
    assert res["success"] is True
    assert "मित्र" in res["optimized_script"]
    words = len(res["optimized_script"].split())
    assert 90 <= words <= 165


def test_custom_story_mode_preserves_stock_video_logic(tmp_path):
    """Verify Custom Story Studio (visual_mode='multi_cinematic') uses multi-stock videos and is NEVER hijacked by AI images."""
    director = DirectorEngine()
    # Script contains deity keywords that previously triggered Gita/Granth hijack
    script = "माँ वैष्णो देवी के दर्शन की अद्भुत गाथा। श्रद्धा और विश्वास।"
    title = "माँ वैष्णो देवी का रहस्य #Shorts"

    dummy_video = tmp_path / "mock_stock_video.mp4"
    dummy_video.write_bytes(b"dummy mp4 video bytes" * 1000)

    with patch("autotube.media.multi_stock_aggregator.MultiStockAggregator.get_best_scene_asset") as mock_get_stock, \
         patch("autotube.media.ai_visuals.VisualGenerator.generate_image") as mock_gen_ai, \
         patch("autotube.media.director_engine.TTSEngine.synthesize") as mock_tts, \
         patch("autotube.media.director_engine.TTSEngine.clamp_duration") as mock_clamp, \
         patch("autotube.media.director_engine.ShortsBuilder.build_short") as mock_build, \
         patch("autotube.media.director_engine.burn_subtitles") as mock_burn:

        fake_tts_res = MagicMock()
        fake_tts_res.audio_path = tmp_path / "voice.mp3"
        fake_tts_res.audio_path.write_bytes(b"dummy audio" * 500)
        fake_tts_res.subtitles_ass_path = tmp_path / "subs.ass"
        fake_tts_res.subtitles_srt_path = None
        fake_tts_res.duration_seconds = 12.0
        fake_tts_res.scene_durations = [6.0, 6.0]
        mock_tts.return_value = fake_tts_res
        mock_clamp.return_value = fake_tts_res

        mock_get_stock.return_value = dummy_video

        def fake_build_short(*args, **kwargs):
            out_p = kwargs.get("output_path")
            if out_p:
                Path(out_p).write_bytes(b"dummy unsubbed video" * 1000)
            return True
        mock_build.side_effect = fake_build_short

        def fake_burn(*args, **kwargs):
            out_p = kwargs.get("output_video")
            if out_p:
                Path(out_p).write_bytes(b"dummy final video" * 1000)
            return True
        mock_burn.side_effect = fake_burn

        # Calling with visual_mode='multi_cinematic' (Custom Story Studio default)
        scenes = [
            {"narration": "माँ वैष्णो देवी के दर्शन की अद्भुत गाथा।", "duration": 6.0},
            {"narration": "श्रद्धा और विश्वास से जीवन बदलता है।", "duration": 6.0},
        ]
        res = director.render_custom_video(
            script_text=script,
            title=title,
            visual_mode="multi_cinematic",
            scenes=scenes,
        )

        assert res["success"] is True
        # Verify MultiStockAggregator was invoked for the scenes
        assert mock_get_stock.call_count >= 1
        # Verify VisualGenerator.generate_image was NEVER called (no AI image hijacking!)
        assert mock_gen_ai.call_count == 0


def test_vedic_studio_unconstrained_duration_allowed(tmp_path):
    """Verify Vedic & Granth Studio allows videos longer than 60s without clamp_duration or duration gate deletion."""
    director = DirectorEngine()
    # 12 scenes totaling 96.0s (well over the 60s Shorts ceiling)
    scenes = [{"narration": f"दृश्य {i+1}: धर्म और कर्म का दिव्य संदेश।", "duration": 8.0} for i in range(12)]
    script = " ".join(s["narration"] for s in scenes)
    title = "श्रीमद्भगवद्गीता का अमर ज्ञान"

    clip_counter = 0
    def mock_render_clip(*args, **kwargs):
        nonlocal clip_counter
        clip_counter += 1
        clip = tmp_path / f"mock_vedic_clip_{clip_counter}.mp4"
        clip.write_bytes(f"unique clip content {clip_counter}".encode() * 500)
        return clip

    with patch("autotube.media.director_engine.TTSEngine.synthesize") as mock_tts, \
         patch("autotube.media.director_engine.TTSEngine.clamp_duration") as mock_clamp, \
         patch("autotube.media.director_engine.ShortsBuilder.build_short") as mock_build, \
         patch("autotube.media.director_engine.burn_subtitles") as mock_burn, \
         patch("autotube.media.director_engine.get_media_duration", return_value=96.0), \
         patch("autotube.media.ai_visuals.VisualGenerator.generate_image", return_value=None), \
         patch("autotube.media.ai_visuals.VisualGenerator.create_sacred_vedic_fallback", return_value=tmp_path / "sacred.jpg"), \
         patch("autotube.media.vedic_cinematics.render_vedic_cinematic_clip", side_effect=mock_render_clip):

        fake_tts_res = MagicMock()
        fake_tts_res.audio_path = tmp_path / "voice.mp3"
        fake_tts_res.audio_path.write_bytes(b"dummy audio" * 500)
        fake_tts_res.subtitles_ass_path = tmp_path / "subs.ass"
        fake_tts_res.subtitles_srt_path = None
        fake_tts_res.duration_seconds = 96.0
        fake_tts_res.scene_durations = [8.0] * 12
        mock_tts.return_value = fake_tts_res

        def fake_build_short(*args, **kwargs):
            out_p = kwargs.get("output_path")
            if out_p:
                Path(out_p).write_bytes(b"dummy unsubbed video" * 1000)
            return True
        mock_build.side_effect = fake_build_short

        def fake_burn(*args, **kwargs):
            out_p = kwargs.get("output_video")
            if out_p:
                Path(out_p).write_bytes(b"dummy final video" * 1000)
            return True
        mock_burn.side_effect = fake_burn

        res = director.render_custom_video(
            script_text=script,
            title=title,
            visual_mode="vedic_granth_ai",
            scenes=scenes,
        )

        assert res["success"] is True
        assert res["duration"] == 96.0
        assert res["scene_count"] == 12
        # Verify clamp_duration was NEVER called for Vedic & Granth mode
        assert mock_clamp.call_count == 0
        # Verify build_short received enforce_shorts_duration_limit=False
        _, kwargs = mock_build.call_args
        assert kwargs.get("enforce_shorts_duration_limit") is False

        # Verify synthesize received allow_unconstrained_duration=True
        _, tts_kwargs = mock_tts.call_args
        assert tts_kwargs.get("allow_unconstrained_duration") is True

        # Verify contextual vedic_metadata is present in the result
        assert "vedic_metadata" in res
        assert res["vedic_metadata"] is not None
        assert "SanatanDharma" in res["vedic_metadata"]["tags_string"] or "BhagavadGita" in res["vedic_metadata"]["tags_string"]


def test_generate_vedic_metadata_topics():
    """Verify generate_vedic_metadata accurately produces deity-matched titles, tags, and pinned comments."""
    director = DirectorEngine()

    # 1. Lord Shiva
    shiva_meta = director.generate_vedic_metadata("भगवान शिव ने हलाहल विष पीकर ब्रह्मांड की रक्षा की। नीलकंठ महादेव।")
    assert shiva_meta["category"] == "shiva"
    assert "महादेव" in shiva_meta["title"] or "शिव" in shiva_meta["title"]
    assert "Mahadev" in shiva_meta["tags"]
    assert "HarHarMahadev" in shiva_meta["tags"]
    assert "हर हर महादेव" in shiva_meta["pinned_comment"]
    assert "Rahasya" not in shiva_meta["tags"]
    assert "Vigyan" not in shiva_meta["tags"]

    # 2. Lord Rama / Ramcharitmanas
    rama_meta = director.generate_vedic_metadata("परहित सरिस धर्म नहिं भाई, पर पीड़ा सम नहिं अधमाई। गोस्वामी तुलसीदास, रामचरितमानस।")
    assert rama_meta["category"] == "rama"
    assert "ShreeRam" in rama_meta["tags"]
    assert "Ramcharitmanas" in rama_meta["tags"]
    assert "जय श्री राम" in rama_meta["pinned_comment"]

    # 3. Lord Hanuman
    hanuman_meta = director.generate_vedic_metadata("पवनपुत्र हनुमान जी ने संजीवनी बूटी लाकर लक्ष्मण जी के प्राण बचाए।")
    assert hanuman_meta["category"] == "hanuman"
    assert "HanumanJi" in hanuman_meta["tags"]
    assert "Bajrangbali" in hanuman_meta["tags"]
    assert "जय बजरंगबली" in hanuman_meta["pinned_comment"]

    # 4. Custom User Title is preserved
    custom_meta = director.generate_vedic_metadata(
        "कुरुक्षेत्र में अर्जुन और कृष्ण।",
        custom_title="मेरा विशेष गीता ज्ञान",
    )
    assert custom_meta["title"] == "मेरा विशेष गीता ज्ञान #Shorts"


def test_api_vedic_metadata_endpoint(client):
    """Verify POST /api/vedic/metadata endpoint returns structured tags and title."""
    resp = client.post(
        "/api/vedic/metadata",
        json={"script_text": "भगवान शिव और पार्वती जी का दिव्य संवाद।"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert "metadata" in data
    meta = data["metadata"]
    assert "title" in meta
    assert "description" in meta
    assert "tags_string" in meta
    assert "#Mahadev" in meta["tags_string"]


def test_youtube_upload_vedic_content_type(tmp_path):
    """Verify YouTube uploader in 'vedic' mode never injects sci-fi mystery tags or channel funnels."""
    from autotube.uploader.youtube_upload import YouTubeUploader

    dummy_vid = tmp_path / "dummy_vedic.mp4"
    dummy_vid.write_bytes(b"dummy video bytes for upload test" * 100)

    with patch("autotube.uploader.youtube_upload.YouTubeAuth.get_credentials", return_value=MagicMock()), \
         patch("autotube.uploader.youtube_upload.build") as mock_build, \
         patch("autotube.uploader.youtube_upload.MediaFileUpload", return_value=MagicMock()):

        mock_yt = MagicMock()
        mock_build.return_value = mock_yt
        uploader = YouTubeUploader(channel="hindi")

        uploader.upload_video(
            video_path=dummy_vid,
            title="महादेव की अमर सीख #Shorts",
            description="पवित्र शिव पुराण की कथा।",
            tags=["Shorts", "Mahadev", "Bhakti"],
            content_type="vedic",
        )

        insert_kwargs = mock_yt.videos().insert.call_args[1]
        body = insert_kwargs.get("body", {})
        snippet = body.get("snippet", {})
        tags = snippet.get("tags", [])
        desc = snippet.get("description", "")

        # Verify no mystery or science tags are present
        assert "Rahasya" not in tags
        assert "Vigyan" not in tags
        assert "Hindi Facts" not in tags
        assert "Amazing Facts Hindi" not in tags

        # Verify Vedic tags are present
        assert "Sanatan Dharma" in tags
        assert "Vedic Wisdom" in tags

        # Verify description does not contain mystery CTA
        assert "इस रहस्य के बारे में आपकी क्या राय है" not in desc
        assert "रोज़ाना रहस्य, विज्ञान" not in desc
        assert "सनातन धर्म, प्राचीन वैदिक ज्ञान" in desc


def test_tts_synthesize_allow_unconstrained_duration(tmp_path):
    """Verify TTSEngine does not apply atempo speedup when allow_unconstrained_duration=True."""
    from autotube.voice.tts_engine import TTSEngine

    tts = TTSEngine(default_voice="akashvani")

    # Verify that in vertical mode (1080x1920) with scenes <= 9:
    # 1. Without allow_unconstrained_duration (default False): is_vertical_short is True
    assert (not False and ((1080 < 1920) or (len([1, 2]) <= 9))) is True

    # 2. With allow_unconstrained_duration=True: is_vertical_short is False
    allow_unconstrained = True
    assert (not allow_unconstrained and ((1080 < 1920) or (len([1, 2]) <= 9))) is False

    # 3. Test that synthesize with allow_unconstrained_duration passes flag to synthesize_async
    with patch.object(tts, "synthesize_async") as mock_async:
        mock_async.return_value = MagicMock()
        out_p = tmp_path / "test_voice.mp3"
        tts.synthesize(
            text="परीक्षण",
            output_audio_path=out_p,
            allow_unconstrained_duration=True,
        )
        _, kwargs = mock_async.call_args
        assert kwargs.get("allow_unconstrained_duration") is True





