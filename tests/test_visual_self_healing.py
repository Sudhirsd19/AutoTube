"""Unit tests for visual pipeline self-healing, food-keyword filtering, and per-scene frame QA."""

from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest

from autotube.media.stock_fetcher import StockFetcher, FOOD_COOKING_TAGS
from autotube.media.visual_waterfall import (
    _find_unapproved_scene_indices,
    _verify_scene_batch,
)


def test_food_cooking_tags_filter_pixabay(tmp_path):
    """Verify that Pixabay search filters out food/cooking clips for nature/wildlife queries."""
    fetcher = StockFetcher()
    fetcher.pixabay_key = "fake_key"
    fetcher._session_used_ids = set()
    fetcher._persistent_used_ids = set()

    fake_hits = [
        {
            "id": 11702,
            "tags": "squid, grilled, street food, barbecue, skewer, cook",
            "videos": {"medium": {"url": "https://example.com/grilled_squid.mp4", "width": 1080, "height": 1920}},
        },
        {
            "id": 888888,
            "tags": "colossal squid, deep sea, underwater, marine biology, ocean",
            "videos": {"medium": {"url": "https://example.com/deep_squid.mp4", "width": 1080, "height": 1920}},
        },
    ]

    # Verify unit-level negative tag filtering
    clean_q = "colossal squid"
    is_food_query = any(k in clean_q.lower() for k in ("food", "recipe", "cook", "kitchen", "restaurant", "dish", "meal", "eat", "culinary", "bbq", "grill"))
    assert not is_food_query

    # Verify hit 11702 is rejected because it contains food tags
    tokens_11702 = {t.strip() for t in fake_hits[0]["tags"].replace(",", " ").split() if t.strip()}
    assert bool(tokens_11702 & FOOD_COOKING_TAGS) is True

    # Verify hit 888888 is accepted
    tokens_888888 = {t.strip() for t in fake_hits[1]["tags"].replace(",", " ").split() if t.strip()}
    assert bool(tokens_888888 & FOOD_COOKING_TAGS) is False

    # End-to-end test of search_pixabay_video selecting only the non-food hit 99999
    def fake_get(url, *args, **kwargs):
        resp = MagicMock()
        resp.status_code = 200
        if "pixabay.com/api/videos" in url:
            resp.json.return_value = {"hits": fake_hits}
        else:
            resp.iter_content.return_value = [b"x" * 60000]
        return resp

    with patch("requests.get", side_effect=fake_get):
        result = fetcher.search_pixabay_video("colossal squid", output_dir=tmp_path)
        assert result is not None
        assert "888888" in result.name
        assert "11702" not in result.name


def test_find_unapproved_scene_indices(tmp_path):
    """Verify _find_unapproved_scene_indices identifies scenes rejected by VisualQualityGate."""
    clip1 = tmp_path / "clip1.mp4"
    clip2 = tmp_path / "clip2.mp4"
    clip1.write_bytes(b"x" * 6000)
    clip2.write_bytes(b"x" * 6000)

    scenes = [
        {"narration": "A colossal squid swimming in the deep abyss.", "visual_subject": "colossal squid"},
        {"narration": "Grilled squid skewers on charcoal.", "visual_subject": "grilled squid"},
    ]

    class _MockGate:
        strict = True
        def verify(self, clip_path, narration, plan):
            # Reject clip1 (e.g. food footage in deep sea scene)
            if "abyss" in narration:
                return {"accepted": False, "reason": "Shows food instead of abyss"}
            return {"accepted": True}

    with patch("autotube.media.visual_waterfall.VisualQualityGate", return_value=_MockGate()):
        unapproved = _find_unapproved_scene_indices(
            clips=[clip1, clip2],
            scenes=scenes,
            topic="Colossal Squid",
            provider="TestProvider",
            require_video=True,
        )
        assert unapproved == [0]
        # _verify_scene_batch should return False since scene 0 was rejected
        assert _verify_scene_batch(
            clips=[clip1, clip2],
            scenes=scenes,
            topic="Colossal Squid",
            provider="TestProvider",
            require_video=True,
        ) is False


def test_outro_cta_frame_qa_and_self_healing_acceptance(tmp_path):
    """Verify that Outro / CTA scenes are not rejected for missing subscribe buttons,
    and that ensure_subject_outro_cta always populates a grand finale visual subject."""
    from autotube.media.visual_quality_gate import VisualQualityGate
    from autotube.scripting.generator import ensure_subject_outro_cta
    from autotube.scripting.models import ShortScript, ShortScene

    # 1. Test ensure_subject_outro_cta always sets a valid visual_subject
    dummy_script = ShortScript(
        title="Wootz Steel Nanotechnology",
        hook="Did you know ancient Indian Wootz steel had carbon nanotubes?",
        topic="Ancient India Wootz Steel Nanotechnology",
        narration="Test narration",
        scenes=[
            ShortScene(scene_number=1, narration="Scene 1", visual_subject="ancient forge"),
            ShortScene(
                scene_number=2,
                narration="Hamare channel ko subscribe aur like zaroor karein!",
                visual_subject="",  # empty subject returned by model
            ),
        ],
        scenes_count=2,
        duration_seconds=55,
    )
    processed = ensure_subject_outro_cta(dummy_script, "Ancient India Wootz Steel Nanotechnology", "hi")
    last_sc = processed.scenes[-1]
    assert last_sc.visual_subject != ""
    assert "subscribe" not in last_sc.visual_subject.lower()
    assert "ancient" in last_sc.visual_subject.lower() or "temple" in last_sc.visual_subject.lower() or "finale" in last_sc.visual_subject.lower()

    # 2. Test VisualQualityGate outro CTA tolerance
    gate = VisualQualityGate()
    gate.strict = True
    test_clip = tmp_path / "temple_sunset.mp4"
    test_clip.write_bytes(b"dummy video data" * 1000)

    # Mock Gemini client returning a response that complains about missing subscribe button
    mock_client = MagicMock()
    mock_response = MagicMock()
    mock_response.text = '{"confidence": 85, "coverage": 80, "accepted": false, "reason": "The frames show a historical fort at sunset, but completely lacks the required animated subscribe bell button", "violations": ["missing animated subscribe bell button"]}'
    mock_client.models.generate_content.return_value = mock_response

    gate._client = mock_client
    with patch.object(gate, "_extract_frames", return_value=[tmp_path / "frame.jpg"]):
        (tmp_path / "frame.jpg").write_bytes(b"frame data" * 500)
        res = gate.verify(
            test_clip,
            narration="Aise hi rochak tathyo ke liye channel ko subscribe karein aur video ko like karein!",
            scene_plan={"subject": "ancient Indian stone temple sunset grand finale", "is_outro": True},
        )
        assert res.get("accepted") is True
