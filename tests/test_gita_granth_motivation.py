"""Regression tests for Gita/Granth motivation voices and native-4K visual requirements."""

from io import BytesIO
from pathlib import Path
from types import SimpleNamespace

from PIL import Image

from autotube.media.ai_visuals import VisualGenerator
from autotube.media import visual_waterfall
from autotube.scripting.generator import (
    ScriptGenerator,
    is_bhagavad_gita_topic,
    is_gita_granth_motivation_topic,
)
from autotube.scripting.trend_finder import TrendFinder, _ensure_scripture_topic_identity
from autotube.voice.voice_director import choose_subject_voice


def _jpeg_bytes(size: tuple[int, int]) -> bytes:
    stream = BytesIO()
    Image.new("RGB", size, color=(30, 80, 120)).save(
        stream, format="JPEG", quality=75, optimize=True
    )
    return stream.getvalue()


def test_spiritual_topics_select_a_dedicated_voice_by_language():
    assert choose_subject_voice(
        "Bhagavad Gita: Krishna's Wisdom",
        "The Gita teaches selfless action and steady awareness.",
        "en",
    ) == "en_deep_warm_male"
    assert choose_subject_voice(
        "गीता से जीवन की सीख",
        "श्रीकृष्ण अर्जुन को निष्काम कर्म का संदेश देते हैं।",
        "hi",
    ) == "akashvani"


def test_spiritual_voice_takes_priority_over_space_and_history_keywords():
    assert choose_subject_voice(
        "Bhagavad Gita Cosmic Wisdom",
        "Krishna explains karma yoga to Arjuna on the battlefield.",
        "en",
    ) == "en_deep_warm_male"


def test_generic_motivation_and_digital_topics_are_not_misclassified():
    assert is_gita_granth_motivation_topic("Daily motivation to stay focused") is False
    assert is_gita_granth_motivation_topic("The digital future of education") is False
    assert is_gita_granth_motivation_topic("Granth se motivation") is True
    assert is_bhagavad_gita_topic("Geeta motivation for difficult times") is True


def test_trend_finder_routes_gita_granth_to_its_own_niche_without_false_digital_match():
    finder = TrendFinder.__new__(TrendFinder)
    niche, focus = finder.resolve_niche("गीता मोटिवेशन")
    assert niche == "gita_motivation"
    assert "Bhagavad Gita" in focus
    niche, _ = finder.resolve_niche("digital transformation")
    assert niche != "gita_motivation"


def test_gita_niche_adds_scripture_marker_when_generated_topic_is_generic():
    assert _ensure_scripture_topic_identity(
        "gita_motivation",
        ["How to stop comparing yourself with others"],
    ) == ["Ancient Scripture Wisdom: How to stop comparing yourself with others"]
    assert _ensure_scripture_topic_identity(
        "space",
        ["How to stop comparing yourself with others"],
    ) == ["How to stop comparing yourself with others"]


def test_no_api_key_uses_topic_specific_spiritual_script():
    generator = ScriptGenerator.__new__(ScriptGenerator)
    generator.client = None

    script = generator.generate_short_script(
        "Bhagavad Gita motivation for fear of failure",
        target_duration=45,
        language="hi",
    )

    assert len(script.scenes) == 6
    assert "गीता" in script.narration
    assert all(scene.visual_subject for scene in script.scenes)
    assert "सब्सक्राइब" in script.scenes[-1].narration


def test_english_spiritual_fallback_respects_short_word_budget():
    generator = ScriptGenerator.__new__(ScriptGenerator)
    generator.client = None

    script = generator.generate_short_script(
        "Bhagavad Gita motivation for fear of failure",
        target_duration=45,
        language="en",
    )

    assert 90 <= len(script.narration.split()) <= 110
    assert len(script.scenes) == 6
    assert "Bhagavad Gita" in script.narration


def test_native_4k_mode_rejects_a_smaller_image_and_never_uses_stock_fallback(
    monkeypatch, tmp_path
):
    urls = []
    pexels_calls = []

    class FakeResponse:
        status_code = 200
        headers = {"content-type": "image/jpeg"}

        def __init__(self):
            self.content = _jpeg_bytes((1024, 1024))

    monkeypatch.setenv("POLLINATIONS_API_KEY", "test-key")
    monkeypatch.setattr(
        "autotube.media.ai_visuals.requests.get",
        lambda url, **kwargs: (urls.append(url) or FakeResponse()),
    )
    generator = VisualGenerator()

    result = generator._fetch_pollinations_image(
        prompt="photorealistic ancient Indian sacred manuscript",
        output_path=tmp_path / "scene.jpg",
        width=2160,
        height=3840,
        style="spiritual_photorealistic",
        require_native_resolution=True,
        allow_photo_fallback=False,
    )

    assert result is False
    assert not (tmp_path / "scene.jpg").exists()
    assert len(urls) == 3
    assert all("gen.pollinations.ai/image/" in url for url in urls)
    assert all("width=2160&height=3840" in url for url in urls)
    assert pexels_calls == []


def test_native_4k_mode_accepts_only_matching_real_pixel_dimensions(monkeypatch, tmp_path):
    class FakeResponse:
        status_code = 200
        headers = {"content-type": "image/jpeg"}
        content = _jpeg_bytes((2160, 3840))

    monkeypatch.setenv("POLLINATIONS_API_KEY", "test-key")
    monkeypatch.setattr(
        "autotube.media.ai_visuals.requests.get",
        lambda url, **kwargs: FakeResponse(),
    )
    output = tmp_path / "scene.jpg"
    generator = VisualGenerator()

    ok = generator._fetch_pollinations_image(
        prompt="photorealistic ancient Indian sacred manuscript",
        output_path=output,
        width=2160,
        height=3840,
        style="spiritual_photorealistic",
        require_native_resolution=True,
        allow_photo_fallback=False,
    )

    assert ok is True
    with Image.open(output) as image:
        assert image.size == (2160, 3840)


def test_scripture_video_path_requests_native_4k_ai_images_and_qas_every_scene(
    monkeypatch, tmp_path
):
    script = SimpleNamespace(
        topic="Bhagavad Gita motivation",
        title="Gita wisdom for difficult times",
        narration="One scene per spoken line.",
        scenes=[
            SimpleNamespace(
                narration="Krishna guides Arjuna toward steady action.",
                visual_subject="Krishna guiding Arjuna",
                visual_description="Respectful depiction on a Kurukshetra chariot at sunrise.",
            ),
            SimpleNamespace(
                narration="A steady mind helps us act with care.",
                visual_subject="meditating person sunrise",
                visual_description="A person reflecting peacefully at sunrise in an Indian ashram.",
            ),
        ],
    )
    requested = []
    qa_calls = []

    class FakeGenerator:
        def generate_image(self, **kwargs):
            requested.append(kwargs)
            path = Path(kwargs["output_path"])
            path.write_bytes(b"x" * 6000)
            return path

    class FakeImageContext:
        size = (2160, 3840)

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    def fake_motion_clip(image_path, output_path, **kwargs):
        output_path = Path(output_path)
        output_path.write_bytes(b"x" * 20000)
        return output_path

    monkeypatch.setattr("autotube.media.ai_visuals.VisualGenerator", FakeGenerator)
    monkeypatch.setattr("PIL.Image.open", lambda *args, **kwargs: FakeImageContext())
    monkeypatch.setattr(visual_waterfall, "_image_to_motion_clip", fake_motion_clip)
    monkeypatch.setattr(
        visual_waterfall,
        "_verify_scene_batch",
        lambda clips, scenes, topic, provider, script=None: (
            qa_calls.append((list(clips), list(scenes), topic, provider)) or True
        ),
    )

    clips = visual_waterfall.acquire_scene_visuals_waterfall(
        script=script,
        output_dir=tmp_path,
        slug="gita-test",
        orientation="portrait",
        max_scenes=6,
    )

    assert len(clips) == 2
    assert len(requested) == 2
    assert all(call["width"] == 2160 and call["height"] == 3840 for call in requested)
    assert all(call["require_native_resolution"] is True for call in requested)
    assert all(call["allow_photo_fallback"] is False for call in requested)
    assert len(qa_calls) == 1
    assert len(qa_calls[0][0]) == len(script.scenes)
