"""Regression tests for visual fail-closed behavior, slot recovery and preset state."""

import datetime
from pathlib import Path

from autotube.media.visual_quality_gate import VisualQualityGate
from autotube.media.visual_waterfall import _verify_scene_batch
from autotube.scheduler.daemon import AutopilotDaemon
from autotube.web.app import _resolve_saved_preset


def test_provider_visual_batch_requires_every_clip_to_pass_qa(monkeypatch, tmp_path):
    first = tmp_path / "scene_1.mp4"
    second = tmp_path / "scene_2.mp4"
    first.write_bytes(b"x" * 6000)
    second.write_bytes(b"x" * 6000)
    seen = []

    def fake_verify(self, asset_path, narration, scene_plan=None):
        seen.append((Path(asset_path).name, narration, scene_plan["subject"]))
        return {"accepted": Path(asset_path).name == "scene_1.mp4", "reason": "test decision"}

    monkeypatch.setattr(VisualQualityGate, "verify", fake_verify)
    scenes = [
        {"narration": "A black hole bends light.", "visual_subject": "black hole"},
        {"narration": "The event horizon traps light.", "visual_subject": "event horizon"},
    ]

    assert _verify_scene_batch([first, second], scenes, "Space mystery", "Test provider") is False
    assert len(seen) == 2
    assert seen[0][2] == "black hole"
    assert seen[1][1] == "The event horizon traps light."


def test_provider_visual_batch_rejects_missing_scene_clip(monkeypatch, tmp_path):
    clip = tmp_path / "only_scene.mp4"
    clip.write_bytes(b"x" * 6000)
    monkeypatch.setattr(
        VisualQualityGate,
        "verify",
        lambda self, asset_path, narration, scene_plan=None: {"accepted": True},
    )
    scenes = [
        {"narration": "Scene one", "visual_subject": "one"},
        {"narration": "Scene two", "visual_subject": "two"},
    ]

    assert _verify_scene_batch([clip], scenes, "Test topic", "Test provider") is False


def test_scheduler_catches_up_slots_that_are_past_due():
    tz = datetime.timezone.utc
    slot = {"hour": 12, "minute": 0}
    before = datetime.datetime(2026, 10, 11, 11, 59, tzinfo=tz)
    after = datetime.datetime(2026, 10, 11, 18, 30, tzinfo=tz)

    assert AutopilotDaemon._slot_is_due(slot, before) is False
    assert AutopilotDaemon._slot_is_due(slot, after) is True


def test_scheduler_retry_waits_until_backoff_expires():
    tz = datetime.timezone.utc
    now = datetime.datetime(2026, 10, 11, 12, 0, tzinfo=tz)
    record = {"retry_after": "2026-10-11T12:10:00+00:00"}

    assert AutopilotDaemon._retry_is_ready(record, now) is False
    assert AutopilotDaemon._retry_is_ready(
        record, now + datetime.timedelta(minutes=10)
    ) is True


def test_saved_named_preset_becomes_custom_if_slots_were_edited():
    original = [{"id": "slot_1", "hour": 12, "minute": 0, "channel": "english"}]
    edited = [{"id": "slot_1", "hour": 13, "minute": 0, "channel": "english"}]
    presets = {"growth_1": original}

    assert _resolve_saved_preset(original, "growth_1", presets) == "growth_1"
    assert _resolve_saved_preset(edited, "growth_1", presets) == "custom"
    assert _resolve_saved_preset(edited, "custom", presets) == "custom"
