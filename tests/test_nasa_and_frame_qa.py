from autotube.media.multi_stock_aggregator import MultiStockAggregator
from autotube.media.nasa_media import NasaMediaFetcher
from autotube.media.visual_quality_gate import VisualQualityGate


def test_nasa_video_url_prefers_preview_mp4():
    links = [
        {"rel": "canonical", "href": "https://images.nasa.gov/details/ABC"},
        {"rel": "preview", "href": "https://images-assets.nasa.gov/video/ABC/ABC-preview.mp4"},
        {"rel": "alternate", "href": "https://example.com/ABC.jpg"},
    ]
    assert NasaMediaFetcher._extract_video_url(links).endswith(".mp4")


def test_nasa_video_url_rejects_image_only_links():
    links = [
        {"rel": "canonical", "href": "https://images.nasa.gov/details/ABC"},
        {"href": "https://example.com/ABC.jpg"},
    ]
    assert NasaMediaFetcher._extract_video_url(links) == ""


def test_frame_gate_non_strict_without_api(tmp_path, monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("AUTOTUBE_FRAME_QA_STRICT", raising=False)
    asset = tmp_path / "clip.mp4"
    asset.write_bytes(b"x" * 6000)
    result = VisualQualityGate().verify(asset, "A black hole in deep space.")
    assert result["accepted"] is True
    assert result["mode"] == "metadata_only"


def test_frame_gate_strict_without_api(tmp_path, monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.setenv("AUTOTUBE_FRAME_QA_STRICT", "1")
    asset = tmp_path / "clip.mp4"
    asset.write_bytes(b"x" * 6000)
    result = VisualQualityGate().verify(asset, "A black hole in deep space.")
    assert result["accepted"] is False
    assert result["mode"] == "metadata_only"


class _StubNasa:
    def is_configured(self):
        return True

    def search_videos(self, query, limit=4):
        return [{"query": query, "limit": limit}]


def test_multi_stock_nasa_dispatcher_is_present():
    aggregator = object.__new__(MultiStockAggregator)
    aggregator.nasa_fetcher = _StubNasa()
    assert aggregator.search_nasa("black hole", 4) == [{"query": "black hole", "limit": 8}]


def test_multi_stock_strict_video_mode_returns_none_for_motion_fallback():
    aggregator = object.__new__(MultiStockAggregator)
    aggregator.gather_candidates = lambda **kwargs: []
    aggregator.rank_and_select = lambda *args, **kwargs: None
    aggregator.visual_quality_gate = None
    aggregator.pexels_fetcher = None
    scene_plan = {
        "subject": "black hole",
        "action": "swirling in deep space",
        "environment": "deep space",
        "must_show": ["black hole", "accretion disk"],
        "avoid": ["cartoon", "daylight"],
        "search_queries": ["black hole", "black hole space", "cosmic vortex"],
    }

    result = aggregator.get_best_scene_asset(
        scene_text="A black hole swallows matter.",
        title="Black Hole",
        scene_index=0,
        scene_plan=scene_plan,
        allow_ai_fallback=False,
    )

    assert result is None


def test_multi_stock_reuse_guard_checks_persistent_history():
    aggregator = object.__new__(MultiStockAggregator)
    aggregator.session_used_ids = set()
    aggregator.persistent_used_ids = {"pexels_12345"}
    aggregator.persistent_used_hashes = set()
    assert aggregator._is_used("pexels_12345") is True
    assert aggregator._is_used("pexels_99999") is False


def test_multi_stock_hash_guard_tracks_external_video(tmp_path):
    aggregator = object.__new__(MultiStockAggregator)
    aggregator.session_used_ids = set()
    aggregator.persistent_used_ids = set()
    aggregator.persistent_used_hashes = set()
    asset = tmp_path / "clip.mp4"
    asset.write_bytes(b"synthetic-video-content" * 500)

    assert aggregator._record_asset_fingerprint(asset, label="test") is True
    assert aggregator._record_asset_fingerprint(asset, label="test") is False


def test_frame_gate_transient_503_error(tmp_path, monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "fake_key_test")
    monkeypatch.setenv("AUTOTUBE_FRAME_QA_STRICT", "1")

    class _FailingModels:
        def generate_content(self, *args, **kwargs):
            raise RuntimeError("ServerError: 503 UNAVAILABLE. The service is currently unavailable.")

    class _FakeClient:
        models = _FailingModels()

    gate = VisualQualityGate()
    gate._client = _FakeClient()
    gate._extract_frames = lambda path, count=4: [tmp_path / "f1.jpg"]
    (tmp_path / "f1.jpg").write_bytes(b"frame-bytes-data")

    asset = tmp_path / "clip.mp4"
    asset.write_bytes(b"x" * 6000)

    result = gate.verify(asset, "A cheetah sprinting across the savanna.")
    assert result["accepted"] is False
    assert result["mode"] == "frame_qa_transient_error"
    assert "503" in result["reason"] or "transient" in result["reason"]


def test_multi_stock_transient_qa_fallback_accepts_high_confidence(tmp_path):
    aggregator = object.__new__(MultiStockAggregator)
    aggregator.session_used_ids = set()
    aggregator.persistent_used_ids = set()
    aggregator.persistent_used_hashes = set()
    aggregator._is_used = lambda cid: False
    aggregator.plan_visual_scene = lambda *args: {"search_queries": ["cheetah running"], "subject": "cheetah"}
    aggregator.generate_smart_queries = lambda *args: {"primary_query": "cheetah", "alternative_query": "", "mood_query": "", "scene_plan": {}}
    aggregator.gather_candidates = lambda *args, **kwargs: [{
        "id": "pixabay_307555",
        "title": "cheetah sprint running",
        "tags": ["cheetah", "sprint"],
        "score": 100.0,
        "ai_confidence": 95,
        "visual_coverage_pct": 100,
    }]
    aggregator.rank_and_select = lambda candidates, *args, **kwargs: candidates[0]

    test_clip = tmp_path / "cheetah.mp4"
    test_clip.write_bytes(b"x" * 60000)
    aggregator.download_candidate = lambda *args, **kwargs: test_clip

    class _MockGate:
        strict = True
        def verify(self, *args, **kwargs):
            return {
                "accepted": False,
                "confidence": None,
                "coverage": None,
                "reason": "Gemini vision service transiently unavailable (ServerError).",
                "mode": "frame_qa_transient_error",
            }

    aggregator.visual_quality_gate = _MockGate()

    result = aggregator.get_best_scene_asset(
        scene_text="Cheetah sprinting fast.",
        title="Cheetah Speed",
        scene_index=0,
        orientation="portrait",
    )
    assert result == test_clip

