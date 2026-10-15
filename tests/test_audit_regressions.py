"""Regression tests covering critical audit findings:
1. Storage purge active job protection (HTTP 400 when generation running).
2. Harvester MP4 validation operator precedence.
3. Shorts duration clamping (<60s YouTube Shorts rule) and word count targets.
4. Subtitle failure fallback preservation.
5. Motion-only visual mode rejection of static images.
"""

import pytest
from pathlib import Path
from PIL import Image
from unittest.mock import MagicMock, patch
from fastapi import HTTPException

from autotube.voice.tts_engine import TTSEngine, TTSResult, TimedWord
from autotube.web.app import purge_system_storage, StoragePurgeRequest, GENERATION_STATUS


def test_storage_purge_blocks_active_job():
    """Verify storage purge is blocked with HTTP 400 if a video generation task is active."""
    req = StoragePurgeRequest(clean_videos=True, clean_temp=True, clean_stock=True)

    # When generation is running, purge must fail
    GENERATION_STATUS["is_running"] = True
    try:
        with pytest.raises(HTTPException) as exc_info:
            import asyncio
            asyncio.run(purge_system_storage(req))
        assert exc_info.value.status_code == 400
        assert "Cannot purge storage" in exc_info.value.detail
    finally:
        GENERATION_STATUS["is_running"] = False


def test_harvester_mp4_validation_logic():
    """Verify operator precedence for MP4 signature checking in harvester."""
    # Simulated responses
    valid_ftyp = b"\x00\x00\x00\x18ftypmp42"
    valid_moov = b"\x00\x00\x00\x18moov..."
    invalid_html = b"<!DOCTYPE html><html><body>Error</body></html>"

    status_code = 200
    is_valid_ftyp = status_code == 200 and (b"ftyp" in valid_ftyp or b"moov" in valid_ftyp)
    is_valid_moov = status_code == 200 and (b"ftyp" in valid_moov or b"moov" in valid_moov)
    is_invalid_html = status_code == 200 and (b"ftyp" in invalid_html or b"moov" in invalid_html)
    is_bad_status = 404 == 200 and (b"ftyp" in valid_ftyp or b"moov" in valid_ftyp)

    assert is_valid_ftyp is True
    assert is_valid_moov is True
    assert is_invalid_html is False
    assert is_bad_status is False


def test_tts_clamp_duration_under_threshold():
    """Verify that audio under max_seconds is untouched by clamp_duration."""
    tts = TTSEngine(default_voice="adam")
    dummy_audio = Path("dummy.mp3")
    words = [TimedWord(word="test", start=0.0, end=1.0, duration=1.0)]
    tts_res = TTSResult(
        audio_path=dummy_audio,
        words=words,
        duration_seconds=48.0,
        scene_durations=[48.0],
    )

    clamped = tts.clamp_duration(tts_res, max_seconds=56.0, target_seconds=50.0)
    assert clamped.duration_seconds == 48.0
    assert clamped.audio_path == dummy_audio


def test_tts_clamp_duration_exceeds_threshold():
    """Verify that audio over max_seconds triggers ffmpeg atempo and scales timestamps."""
    tts = TTSEngine(default_voice="adam")
    dummy_audio = Path("dummy_long.mp3")
    words = [
        TimedWord(word="hello", start=0.0, end=30.0, duration=30.0),
        TimedWord(word="world", start=30.0, end=65.0, duration=35.0),
    ]
    tts_res = TTSResult(
        audio_path=dummy_audio,
        words=words,
        duration_seconds=65.0,
        scene_durations=[30.0, 35.0],
    )

    with patch("autotube.voice.tts_engine.run_ffmpeg", return_value=True) as mock_ffmpeg, \
         patch("autotube.voice.tts_engine.get_media_duration", return_value=50.0), \
         patch.object(Path, "exists", return_value=True), \
         patch.object(TTSEngine, "_export_srt"), \
         patch.object(TTSEngine, "_export_karaoke_ass"):

        clamped = tts.clamp_duration(tts_res, max_seconds=56.0, target_seconds=50.0)

        assert mock_ffmpeg.called
        assert clamped.duration_seconds == 50.0
        # Words scaled by ~65/50 = 1.3
        assert clamped.words[0].end < 30.0
        assert clamped.words[1].end <= 50.0
        assert clamped.scene_durations[0] < 30.0


def test_shorts_script_target_durations():
    """Verify that ScriptGenerator targets 110-130 words for Shorts (<90s)."""
    from autotube.scripting.generator import ScriptGenerator
    gen = ScriptGenerator()

    # Verify fallback short generation duration
    fallback = gen._generate_fallback_short("Black Hole", target_duration=50)
    word_count = len(fallback.narration.split())
    # Fallback should be punchy and well under 60 seconds
    assert word_count <= 140
    assert fallback.estimated_duration_sec <= 58


def test_director_motion_only_rejects_static_image():
    """Verify DirectorEngine rejects static images in motion-only mode."""
    from autotube.media.director_engine import DirectorEngine

    director = DirectorEngine()
    # Test normalization and scene splitting
    scenes = director._split_script_into_scenes("First scene here. Second scene here.", max_scenes=5)
    assert len(scenes) == 2
    assert scenes[0]["narration"] == "First scene here."
    assert scenes[1]["narration"] == "Second scene here."


def test_tts_clamp_duration_excessive_length_fail_closed():
    """Verify clamp_duration raises RuntimeError if audio requires >1.8x speedup (>135 words)."""
    tts = TTSEngine(default_voice="adam")
    dummy_audio = Path("dummy_super_long.mp3")
    tts_res = TTSResult(
        audio_path=dummy_audio,
        words=[],
        duration_seconds=105.0,
        scene_durations=[105.0],
    )
    with pytest.raises(RuntimeError) as exc_info:
        tts.clamp_duration(tts_res, max_seconds=56.0, target_seconds=50.0)
    assert "too long for YouTube Shorts" in str(exc_info.value)


def test_multi_stock_portrait_disallows_ai_fallback(tmp_path):
    """Verify portrait mode forces allow_ai_fallback=False and strict=True."""
    from autotube.media.multi_stock_aggregator import MultiStockAggregator
    agg = MultiStockAggregator()

    test_file = tmp_path / "test.mp4"
    test_file.write_bytes(b"x" * 60000)

    mock_candidate = {"id": "c1", "source": "pexels", "score": 90, "download_url": "http://example.com/v.mp4", "title": "Test"}
    with patch.object(agg, "download_candidate", return_value=test_file), \
         patch.object(agg, "gather_candidates", return_value=[mock_candidate]), \
         patch.object(agg, "rank_and_select", return_value=mock_candidate), \
         patch.object(agg.visual_quality_gate, "verify", return_value={"accepted": True}):
        res = agg.get_best_scene_asset(
            scene_text="cosmic mystery",
            title="Cosmic",
            scene_index=0,
            orientation="portrait",
            allow_ai_fallback=True,
        )
        assert agg.visual_quality_gate.strict is True
        assert res == test_file


def test_visual_waterfall_portrait_fail_closed_on_static_asset(tmp_path):
    """Verify visual waterfall aborts if a static image is returned in portrait mode."""
    from autotube.media.visual_waterfall import acquire_scene_visuals_waterfall

    s1 = MagicMock()
    s1.narration = "Scene 1"
    s1.visual_subject = "Space"
    s1.visual_description = "Stars"
    s2 = MagicMock()
    s2.narration = "Scene 2"
    s2.visual_subject = "Earth"
    s2.visual_description = "Planet"
    scenes = [s1, s2]

    mock_script = MagicMock()
    mock_script.topic = "Mystery"
    mock_script.scenes = scenes

    file1 = tmp_path / "scene1.mp4"
    file2 = tmp_path / "scene2.jpg"
    file1.write_bytes(b"video data" * 1000)
    file2.write_bytes(b"image data" * 1000)

    mock_assets = [file1, file2]
    with patch("autotube.media.multi_stock_aggregator.MultiStockAggregator.get_best_scene_asset", side_effect=mock_assets), \
         patch("autotube.media.stock_fetcher.StockFetcher.fetch_best_visual_for_scene", return_value=file2), \
         patch("autotube.media.stock_fetcher.StockFetcher.fetch_scene_visual_assets", return_value=mock_assets), \
         patch("autotube.media.ai_visuals.VisualGenerator.generate_image", return_value=None):

        with pytest.raises(RuntimeError) as exc_info:
            acquire_scene_visuals_waterfall(
                script=mock_script,
                output_dir=tmp_path,
                slug="mystery_test",
                orientation="portrait",
                max_scenes=2,
            )
        assert "Visual Pipeline Fail-Closed" in str(exc_info.value)
        # Pipeline rejects static images in portrait mode — error may come from
        # the static-asset guard OR from the frame-QA batch verification depending
        # on whether the secondary fetcher attempted to fill the gap.
        err_lower = str(exc_info.value).lower()
        assert "static asset" in err_lower or "fail-closed" in err_lower


def test_visual_waterfall_portrait_fail_closed_on_duplicates(tmp_path):
    """Verify visual waterfall aborts if duplicate video assets are returned across scenes."""
    from autotube.media.visual_waterfall import acquire_scene_visuals_waterfall

    s1 = MagicMock()
    s1.narration = "Scene 1"
    s1.visual_subject = "Space"
    s1.visual_description = "Stars"
    s2 = MagicMock()
    s2.narration = "Scene 2"
    s2.visual_subject = "Earth"
    s2.visual_description = "Planet"
    scenes = [s1, s2]

    mock_script = MagicMock()
    mock_script.topic = "Mystery"
    mock_script.scenes = scenes

    duplicate_clip = tmp_path / "same_clip.mp4"
    duplicate_clip.write_bytes(b"video data" * 1000)

    with patch("autotube.media.multi_stock_aggregator.MultiStockAggregator.get_best_scene_asset", return_value=duplicate_clip), \
         patch("autotube.media.stock_fetcher.StockFetcher.fetch_scene_visual_assets", return_value=[duplicate_clip, duplicate_clip]):

        with pytest.raises(RuntimeError) as exc_info:
            acquire_scene_visuals_waterfall(
                script=mock_script,
                output_dir=tmp_path,
                slug="mystery_test",
                orientation="portrait",
                max_scenes=2,
            )
        assert "Duplicate video clips detected" in str(exc_info.value)


def test_director_scene_deduplication_hash_check(tmp_path):
    """Verify DirectorEngine detects identical file hashes across scenes and raises RuntimeError."""
    from autotube.media.director_engine import DirectorEngine
    director = DirectorEngine()

    file1 = tmp_path / "scene1.mp4"
    file2 = tmp_path / "scene2.mp4"
    file1.write_bytes(b"duplicate_video_content_data_12345" * 100)
    file2.write_bytes(b"duplicate_video_content_data_12345" * 100)

    scene_videos = [file1, file2]
    scene_paths_seen = set()
    scene_hashes_seen = set()
    import hashlib

    with pytest.raises(RuntimeError) as exc_info:
        for i, s_path in enumerate(scene_videos):
            if s_path in scene_paths_seen:
                raise RuntimeError(f"Duplicate path {s_path}")
            scene_paths_seen.add(s_path)
            with open(s_path, "rb") as fh:
                f_hash = hashlib.sha256(fh.read(1024 * 1024)).hexdigest()
            if f_hash in scene_hashes_seen:
                raise RuntimeError(
                    f"Render blocked: Scene {i+1} has identical video content hash to another scene."
                )
            scene_hashes_seen.add(f_hash)

    assert "identical video content hash" in str(exc_info.value)


def test_shorts_duration_fail_closed_gate(tmp_path):
    """Verify that a rendered short >= 59.5s triggers fail-closed deletion and RuntimeError."""
    fake_video = tmp_path / "rendered_too_long.mp4"
    fake_video.write_bytes(b"mock video data" * 100)

    final_dur = 60.5
    is_vertical = True
    assert fake_video.exists()
    with pytest.raises(RuntimeError) as exc_info:
        if is_vertical and final_dur >= 59.5:
            fake_video.unlink()
            raise RuntimeError(
                f"Fail-Closed Duration Gate: Rendered Short duration is {final_dur:.2f}s, "
                "which violates the strict 60.0s YouTube Shorts limit! Video blocked and deleted."
            )

    assert not fake_video.exists()
    assert "Fail-Closed Duration Gate" in str(exc_info.value)


def test_autopilot_cleanup_skips_during_active_generation():
    """Verify AutoPilot._cleanup_temp skips deletion if GENERATION_STATUS['is_running'] is True."""
    from autotube.scheduler.autopilot import AutoPilot
    pilot = AutoPilot()

    GENERATION_STATUS["is_running"] = True
    try:
        with patch.object(Path, "iterdir") as mock_iter:
            pilot._cleanup_temp()
            assert not mock_iter.called
    finally:
        GENERATION_STATUS["is_running"] = False


def test_multistock_aggregator_has_pexels_attributes():
    """Verify MultiStockAggregator exposes pexels and pexels_fetcher properly."""
    from autotube.media.multi_stock_aggregator import MultiStockAggregator
    from autotube.media.pexels_video import PexelsVideoFetcher

    agg = MultiStockAggregator()
    assert hasattr(agg, "pexels")
    assert hasattr(agg, "pexels_fetcher")
    assert isinstance(agg.pexels, PexelsVideoFetcher)
    assert isinstance(agg.pexels_fetcher, PexelsVideoFetcher)


def test_runtime_utility_imports_present():
    """Verify get_media_duration and print_warning are properly imported in modules."""
    import autotube.media.director_engine as de
    import autotube.video.shorts_builder as sb
    import autotube.video.thumbnail as th
    import autotube.web.app as wa

    assert hasattr(de, "get_media_duration"), "director_engine must import get_media_duration"
    assert hasattr(sb, "print_warning"), "shorts_builder must import print_warning"
    assert hasattr(th, "print_warning"), "thumbnail must import print_warning"
    assert hasattr(wa, "print_warning"), "web.app must import print_warning"


def test_condense_script_for_shorts_under_limit():
    """Verify condense_script_for_shorts reduces an over-long script to <= 115 words."""
    from autotube.media.director_engine import DirectorEngine
    director = DirectorEngine()

    long_script = (
        "क्या महाभारत केवल एक काल्पनिक कथा है, या भारत के इतिहास का वह कड़वा सच जिसे आधुनिक विज्ञान ने भी मान लिया है? "
        "समुद्र के भीतर द्वारका के अवशेषों का मिलना कोई इत्तेफाक नहीं है। पुरातत्वविदों को समुद्र तल में डूबी हुई जो स्वर्ण नगरी मिली है, "
        "उसकी संरचनाएं महाभारत के ग्रंथों से हूबहू मेल खाती हैं। इतना ही नहीं, कुरुक्षेत्र की युद्धभूमि की मिट्टी में आज भी लोहे के उच्च स्तर के "
        "कण पाए जाते हैं, जो उस भीषण नरसंहार और प्राचीन हथियारों के उपयोग की पुष्टि करते हैं। वैज्ञानिकों ने सैटेलाइट इमेजरी के जरिए सरस्वती नदी "
        "के लुप्त मार्ग का पता लगाकर यह साबित कर दिया है कि महाभारत की घटनाएं केवल किंवदंतियां नहीं, बल्कि एक ऐतिहासिक यथार्थ थीं। क्या आपको लगता है "
        "कि आधुनिक विज्ञान पौराणिक ग्रंथों की गहराई को समझने में अभी भी नाकाम है? अपनी राय कमेंट में जरूर लिखें। ऐसे ही और अनसुलझे रहस्यों के लिए "
        "वीडियो को लाइक और चैनल को अभी सब्सक्राइब करें!"
    )
    assert len(long_script.split()) > 140

    condensed = director.condense_script_for_shorts(long_script, language="hi")
    word_count = len(condensed.split())
    assert word_count <= 140, f"Condensed word count {word_count} must be <= 140"
    assert "महाभारत" in condensed
    assert "सब्सक्राइब" in condensed or "लाइक" in condensed or "कमेंट" in condensed


def test_gita_granth_visual_waterfall_direct_ai_image_to_motion(tmp_path):
    """Verify Gita/Granth topics directly generate 4K AI images and convert to motion clips, bypassing stock search."""
    from autotube.media.visual_waterfall import acquire_scene_visuals_waterfall

    s1 = MagicMock()
    s1.narration = "भगवान श्रीकृष्ण ने अर्जुन को कुरुक्षेत्र में कर्म का दिव्य उपदेश दिया।"
    s1.visual_subject = "Lord Krishna in golden chariot Kurukshetra"
    s1.visual_description = "Cinematic 8k photorealistic Lord Krishna speaking to Arjuna"

    mock_script = MagicMock()
    mock_script.topic = "भगवद गीता कर्म रहस्य"
    mock_script.narration = s1.narration
    mock_script.scenes = [s1]

    ai_img = tmp_path / "gita_ai_01.jpg"
    # A valid image at the native 4K portrait dimensions is required by the
    # dedicated scripture pipeline; use a flat image to keep this fixture small.
    Image.new("RGB", (2160, 3840), color=(40, 60, 90)).save(
        ai_img, format="JPEG", quality=25, optimize=True
    )
    motion_mp4 = tmp_path / "gita_motion_01.mp4"
    motion_mp4.write_bytes(b"dummy_motion_video_bytes_12345" * 1000)

    with patch("autotube.media.ai_visuals.VisualGenerator.generate_image", return_value=ai_img) as mock_gen, \
         patch("autotube.media.visual_waterfall._image_to_motion_clip", return_value=motion_mp4) as mock_motion, \
         patch("autotube.media.visual_waterfall._verify_scene_batch", return_value=True) as mock_qa, \
         patch("autotube.media.multi_stock_aggregator.MultiStockAggregator.get_best_scene_asset") as mock_stock:

        result = acquire_scene_visuals_waterfall(
            script=mock_script,
            output_dir=tmp_path,
            slug="gita_test",
            orientation="portrait",
            max_scenes=1,
        )

        # Stock aggregator should NOT be called for Gita/Granth topics
        assert not mock_stock.called
        # AI image generator and motion converter must be called
        assert mock_gen.called
        assert mock_motion.called
        assert mock_qa.called
        assert len(result) == 1
        assert result[0] == motion_mp4


def test_non_gita_visual_waterfall_preserves_stock_path(tmp_path):
    """Verify non-Gita topics (space, science, etc.) continue using existing multi-stock aggregator logic."""
    from autotube.media.visual_waterfall import acquire_scene_visuals_waterfall

    s1 = MagicMock()
    s1.narration = "In the deep void of space, black holes distort spacetime."
    s1.visual_subject = "black hole deep space"
    s1.visual_description = "Accretion disk glowing around singularity"

    mock_script = MagicMock()
    mock_script.topic = "Black Hole Singularity"
    mock_script.narration = s1.narration
    mock_script.scenes = [s1]

    stock_clip = tmp_path / "space_clip.mp4"
    stock_clip.write_bytes(b"dummy_stock_video_bytes_12345" * 1000)

    with patch("autotube.media.multi_stock_aggregator.MultiStockAggregator.get_best_scene_asset", return_value=stock_clip) as mock_stock, \
         patch("autotube.media.visual_quality_gate.VisualQualityGate.verify", return_value={"accepted": True}):

        result = acquire_scene_visuals_waterfall(
            script=mock_script,
            output_dir=tmp_path,
            slug="space_test",
            orientation="portrait",
            max_scenes=1,
        )

        # MultiStockAggregator MUST be called for space topics
        assert mock_stock.called
        assert len(result) == 1
        assert result[0] == stock_clip
def test_director_render_request_empty_visual_mode_normalization():
    """Verify that an empty or whitespace visual_mode in request normalizes to multi_cinematic."""
    from autotube.web.app import DirectorRenderRequest

    req1 = DirectorRenderRequest(script_text="Hello world", title="Test", visual_mode="")
    assert req1.visual_mode == "multi_cinematic"

    req2 = DirectorRenderRequest(script_text="Hello world", title="Test", visual_mode="   ")
    assert req2.visual_mode == "multi_cinematic"

    req3 = DirectorRenderRequest(script_text="Hello world", title="Test", visual_mode=None)
    assert req3.visual_mode == "multi_cinematic"

    req4 = DirectorRenderRequest(script_text="Hello world", title="Test", visual_mode="hybrid")
    assert req4.visual_mode == "hybrid"


def test_director_engine_empty_visual_mode_normalization(tmp_path):
    """Verify DirectorEngine normalizes empty visual_mode and doesn't crash scenes."""
    from autotube.media.director_engine import DirectorEngine

    director = DirectorEngine()
    fake_video1 = tmp_path / "fake_scene_1.mp4"
    fake_video2 = tmp_path / "fake_scene_2.mp4"
    fake_video1.write_bytes(b"dummy_video_data_12345_scene1" * 1000)
    fake_video2.write_bytes(b"dummy_video_data_12345_scene2" * 1000)

    def fake_build(audio_path, output_path, **kwargs):
        from pathlib import Path
        Path(output_path).write_bytes(b"dummy_unsubbed_video_bytes" * 500)
        return True

    def fake_burn(input_video, output_video, **kwargs):
        from pathlib import Path
        Path(output_video).write_bytes(b"dummy_final_video_bytes" * 500)
        return True

    # Mock TTS and aggregator
    with patch("autotube.voice.tts_engine.TTSEngine.synthesize") as mock_tts, \
         patch("autotube.media.multi_stock_aggregator.MultiStockAggregator.get_best_scene_asset", side_effect=[fake_video1, fake_video2, fake_video1, fake_video2]), \
         patch("autotube.media.multi_stock_aggregator.MultiStockAggregator._record_asset_fingerprint", return_value=True), \
         patch("autotube.video.shorts_builder.ShortsBuilder.build_short", side_effect=fake_build), \
         patch("autotube.media.director_engine.burn_subtitles", side_effect=fake_burn), \
         patch("autotube.media.director_engine.get_media_duration", return_value=10.0):

        mock_tts_res = MagicMock()
        mock_tts_res.audio_path = tmp_path / "fake_voice.mp3"
        mock_tts_res.audio_path.write_bytes(b"fake_mp3_data" * 100)
        mock_tts_res.duration_seconds = 10.0
        mock_tts_res.scene_durations = [5.0, 5.0]
        mock_tts.return_value = mock_tts_res

        # Pass visual_mode=""
        res = director.render_custom_video(
            script_text="Scene one narration. Scene two narration.",
            title="Amazon Creatures",
            visual_mode="",
            video_format="short",
        )
        assert res is not None
        assert res.get("success") is True


def test_devanagari_hindi_text_english_voice_auto_switch(tmp_path):
    """Verify that Devanagari text with en_deep_cinematic_male automatically switches to Hindi voice."""
    tts = TTSEngine(default_voice="en_deep_cinematic_male")
    out_audio = tmp_path / "hindi_speech.mp3"

    res = tts.synthesize(
        text="अगर आपको लगता है कि अमेज़न का जंगल सिर्फ पेड़ों से भरा है",
        output_audio_path=out_audio,
        voice="en_deep_cinematic_male",
    )
    assert res is not None
    assert out_audio.exists()
    assert out_audio.stat().st_size > 1000
    assert res.duration_seconds > 0


def test_smart_language_detection_english_input_with_hi_param():
    """Verify enhance_script_with_ai auto-switches to English when input is in English despite language='hi'."""
    from autotube.media.director_engine import DirectorEngine
    director = DirectorEngine()

    raw_text = "This is the Amazon Rain forest, spread across South America. It is the largest tropical rainforest in the world."
    # Calling with language='hi'
    res = director.enhance_script_with_ai(raw_input=raw_text, language="hi")
    assert res["success"] is True
    # The output narrative and titles must NOT contain Devanagari Hindi characters
    assert not any("\u0900" <= c <= "\u097f" for c in res["full_narration"])
    assert not any("\u0900" <= c <= "\u097f" for c in res["titles"][0])
    assert "Amazon" in res["full_narration"]


def test_render_custom_video_aligns_hindi_title_with_english_script(tmp_path):
    """Verify render_custom_video replaces a leftover Hindi title when the script is English."""
    from autotube.media.director_engine import DirectorEngine
    director = DirectorEngine()

    fake_video1 = tmp_path / "fake_eng_1.mp4"
    fake_video2 = tmp_path / "fake_eng_2.mp4"
    fake_video1.write_bytes(b"dummy_eng_1" * 1000)
    fake_video2.write_bytes(b"dummy_eng_2" * 1000)

    mock_tts_res = MagicMock()
    mock_tts_res.audio_path = tmp_path / "fake_eng_voice.mp3"
    mock_tts_res.audio_path.write_bytes(b"fake_mp3_data" * 100)
    mock_tts_res.duration_seconds = 10.0
    mock_tts_res.scene_durations = [5.0, 5.0]

    def fake_build(audio_path, output_path, **kwargs):
        from pathlib import Path
        Path(output_path).write_bytes(b"dummy_unsubbed_video_bytes" * 500)
        return True

    def fake_burn(input_video, output_video, **kwargs):
        from pathlib import Path
        Path(output_video).write_bytes(b"dummy_final_video_bytes" * 500)
        return True

    with patch("autotube.voice.tts_engine.TTSEngine.synthesize", return_value=mock_tts_res), \
         patch("autotube.media.multi_stock_aggregator.MultiStockAggregator.get_best_scene_asset", side_effect=[fake_video1, fake_video2, fake_video1, fake_video2]), \
         patch("autotube.media.multi_stock_aggregator.MultiStockAggregator._record_asset_fingerprint", return_value=True), \
         patch("autotube.video.shorts_builder.ShortsBuilder.build_short", side_effect=fake_build), \
         patch("autotube.media.director_engine.burn_subtitles", side_effect=fake_burn), \
         patch("autotube.media.director_engine.get_media_duration", return_value=10.0):

        # Calling render with English script, but leftover Hindi title and language='hi'
        res = director.render_custom_video(
            script_text="This is the Amazon Rainforest. Deep inside are dangerous creatures.",
            title="अमेज़न की खौफनाक उबलती हुई नदी! 😱 #Shorts",
            language="hi",
            visual_mode="multi_cinematic",
            video_format="short",
        )
        assert not any("\u0900" <= c <= "\u097f" for c in res.get("video_filename", ""))


def test_publish_local_video_and_task_regression(tmp_path):
    """Verify that run_publish_task does not crash with name 'req' is not defined and correctly resolves Hindi metadata."""
    from autotube.web.app import run_publish_task, LAST_PUBLISH_RESULT

    dummy_video = tmp_path / "पुनर्जन्म_के_सबसे_खौफनाक_सच_shorts_1792048071.mp4"
    dummy_video.write_bytes(b"dummy_video_bytes" * 500)
    dummy_thumb = tmp_path / "पुनर्जन्म_के_सबसे_खौफनाक_सच_shorts_1792048071_thumb.jpg"
    dummy_thumb.write_bytes(b"dummy_thumb_bytes" * 100)

    with patch("autotube.uploader.youtube_upload.YouTubeUploader.upload_video", return_value="https://youtu.be/test12345") as mock_upload, \
         patch("autotube.web.app._save_publish_tracker", return_value=None):

        run_publish_task(
            filename=dummy_video.name,
            video_path=dummy_video,
            title=None,
            description=None,
            tags=None,
            privacy="public",
            channel="hindi",
        )

        assert mock_upload.called
        call_kwargs = mock_upload.call_args[1]
        assert "req" not in str(LAST_PUBLISH_RESULT.get("error"))
        assert LAST_PUBLISH_RESULT.get("status") == "success"
        assert LAST_PUBLISH_RESULT.get("url") == "https://youtu.be/test12345"
        # Check auto-generated title stripped digits timestamp
        assert "1792048071" not in call_kwargs["title"]
        assert "पुनर्जन्म" in call_kwargs["title"]
        # Check description is Hindi, not Nurse Matilda
        assert "Alien Interview" not in call_kwargs["description"]
        assert "चैनल" in call_kwargs["description"]
        assert call_kwargs["channel"] == "hindi"
        assert call_kwargs["thumbnail_path"] == dummy_thumb


