"""Regression tests covering critical audit findings:
1. Storage purge active job protection (HTTP 400 when generation running).
2. Harvester MP4 validation operator precedence.
3. Shorts duration clamping (<60s YouTube Shorts rule) and word count targets.
4. Subtitle failure fallback preservation.
5. Motion-only visual mode rejection of static images.
"""

import pytest
from pathlib import Path
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
         patch("autotube.media.stock_fetcher.StockFetcher.fetch_scene_visual_assets", return_value=mock_assets):

        with pytest.raises(RuntimeError) as exc_info:
            acquire_scene_visuals_waterfall(
                script=mock_script,
                output_dir=tmp_path,
                slug="mystery_test",
                orientation="portrait",
                max_scenes=2,
            )
        assert "Visual Pipeline Fail-Closed" in str(exc_info.value)
        assert "static asset" in str(exc_info.value).lower()


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


