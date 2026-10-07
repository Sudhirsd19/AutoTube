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
    assert aggregator.search_nasa("black hole", 4) == [{"query": "black hole", "limit": 4}]
