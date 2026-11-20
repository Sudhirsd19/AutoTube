"""Unit tests for 7-Day Day-Wise Schedule and 4-Slot Automation."""

import pytest
from autotube.scripting.trend_finder import (
    DAY_WISE_NICHES_HI,
    DAY_WISE_NICHES_EN,
    VIRAL_NICHES,
    NICHE_FALLBACKS,
    TrendFinder,
    get_day_wise_niche,
)
from autotube.scheduler.autopilot import AutoPilot


def test_all_seven_days_configured():
    """Verify all 7 days (0 to 6) have valid niches in both Hindi and English."""
    tf = TrendFinder()
    for day_idx in range(7):
        hi_data = get_day_wise_niche(day_idx, language="hi")
        en_data = get_day_wise_niche(day_idx, language="en")
        
        hi_niche = hi_data["niche"]
        en_niche = en_data["niche"]
        
        assert hi_niche in VIRAL_NICHES, f"Hindi Day {day_idx} niche '{hi_niche}' not in VIRAL_NICHES"
        assert en_niche in VIRAL_NICHES, f"English Day {day_idx} niche '{en_niche}' not in VIRAL_NICHES"
        
        canon_hi, _ = tf.resolve_niche(hi_niche, language="hi")
        canon_en, _ = tf.resolve_niche(en_niche, language="en")
        assert canon_hi == hi_niche
        assert canon_en == en_niche


def test_saturday_niche_differentiation():
    """Verify Saturday (weekday 5) is Animal Secrets for Hindi and US Secrets/Conspiracy for English."""
    hi_sat = get_day_wise_niche(5, language="hi")["niche"]
    en_sat = get_day_wise_niche(5, language="en")["niche"]
    assert hi_sat == "animal_secrets"
    assert en_sat == "conspiracy"


def test_slots_config_4_slots():
    """Verify slots_config.json contains 4 active slots (2 English + 2 Hindi)."""
    pilot = AutoPilot()
    slots = pilot.load_configured_slots()
    video_slots = [s for s in slots if s.get("format") != "fb_post"]
    assert len(video_slots) == 4, f"Expected 4 active video slots, got {len(video_slots)}"
    
    en_slots = [s for s in video_slots if (s.get("channel") == "english" or (s.get("language") or "").lower() == "english")]
    hi_slots = [s for s in video_slots if (s.get("channel") == "hindi" or (s.get("language") or "").lower() == "hindi")]
    
    assert len(en_slots) == 2, f"Expected 2 English slots, got {len(en_slots)}"
    assert len(hi_slots) == 2, f"Expected 2 Hindi slots, got {len(hi_slots)}"

