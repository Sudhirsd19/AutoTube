import importlib


def test_structured_scene_plan_is_preserved_only_when_it_matches_script():
    director_module = importlib.import_module("autotube.media.director_engine")
    engine = director_module.DirectorEngine.__new__(director_module.DirectorEngine)

    script = "Earth moves toward the black hole. Gravity bends the light."
    scenes = [
        {"scene_number": 1, "narration": "Earth moves toward the black hole.", "visual_subject": "Earth black hole", "search_keywords": ["Earth black hole"]},
        {"scene_number": 2, "narration": "Gravity bends the light.", "visual_subject": "gravity lensing", "search_keywords": ["gravity lensing"]},
    ]

    prepared = engine._prepare_scene_specs(script, "Test", scenes, 25)
    assert [s["narration"] for s in prepared] == [s["narration"] for s in scenes]
    assert prepared[0]["visual_subject"] == "Earth black hole"


def test_mismatched_scene_plan_falls_back_without_losing_text():
    director_module = importlib.import_module("autotube.media.director_engine")
    engine = director_module.DirectorEngine.__new__(director_module.DirectorEngine)

    script = "First sentence has content. Second sentence has more content."
    stale_scenes = [{"scene_number": 1, "narration": "Completely different text.", "visual_subject": "wrong visual"}]

    prepared = engine._prepare_scene_specs(script, "Test", stale_scenes, 25)
    combined = " ".join(s["narration"] for s in prepared)
    assert engine._normalize_scene_text(combined) == engine._normalize_scene_text(script)
    assert len(prepared) == 2


def test_decimal_and_abbreviation_splitting_does_not_drop_narration():
    director_module = importlib.import_module("autotube.media.director_engine")
    engine = director_module.DirectorEngine.__new__(director_module.DirectorEngine)

    script = "The object is 3.8 billion years old. Dr. Rao studied it in the U.S. lab."
    scenes = engine._split_script_into_scenes(script, 25)
    combined = " ".join(s["narration"] for s in scenes)

    assert engine._normalize_scene_text(combined) == engine._normalize_scene_text(script)
    assert len(scenes) == 2
    assert "3.8" in combined
    assert "Dr. Rao" in combined
    assert "U.S." in combined
