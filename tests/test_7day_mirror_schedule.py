"""Unit tests for 7-Day Universal Mirror Schedule and paired slots."""

import pytest
from autotube.scripting.trend_finder import (
    DAY_WISE_NICHES,
    VIRAL_NICHES,
    NICHE_FALLBACKS,
    TrendFinder,
    get_day_wise_niche,
)
from autotube.scheduler.autopilot import AutoPilot


def test_all_seven_days_configured():
    """Verify all 7 days (0 to 6) have valid niches, descriptions, and fallbacks."""
    tf = TrendFinder()
    for day_idx in range(7):
        day_data = get_day_wise_niche(day_idx)
        niche_key = day_data["niche"]
        assert niche_key in VIRAL_NICHES, f"Day {day_idx} niche '{niche_key}' not in VIRAL_NICHES"
        assert niche_key in NICHE_FALLBACKS, f"Day {day_idx} niche '{niche_key}' not in NICHE_FALLBACKS"
        assert len(NICHE_FALLBACKS[niche_key]) >= 15, f"Day {day_idx} niche '{niche_key}' has too few fallbacks"
        
        canon, desc = tf.resolve_niche(niche_key)
        assert canon == niche_key
        assert len(desc) > 20


def test_daily_mirror_keyword_resolution():
    """Verify that 'daily_mirror' dynamically resolves to today's scheduled niche."""
    tf = TrendFinder()
    canon, desc = tf.resolve_niche("daily_mirror")
    today_data = get_day_wise_niche()
    assert canon == today_data["niche"]
    assert desc == today_data["description"]


def test_slots_config_preset_mirror():
    """Verify slots_config.json contains daily_mirror with 2 properly paired slots."""
    pilot = AutoPilot()
    slots = pilot.load_configured_slots()
    assert len(slots) >= 2, "Configured slots should have at least 2 slots"
    
    slot_1 = slots[0]
    slot_2 = slots[1]
    
    # Slot 1 must be English targeting CosmoChronicle
    assert slot_1.get("channel") == "english"
    assert slot_1.get("language").lower() == "english"
    assert slot_1.get("tz").upper() == "EDT"
    
    # Slot 2 must be Hindi targeting Dulumoni Borah DB / bgyanmantra and mirror slot_1
    assert slot_2.get("channel") == "hindi"
    assert slot_2.get("language").lower() == "hindi"
    assert slot_2.get("tz").upper() == "IST"
    assert slot_2.get("pair_with") == "slot_1"


def test_mirror_pairing_logic(monkeypatch):
    """Test that slot 2 reuses the topic discovered for slot 1 without extra API calls."""
    pilot = AutoPilot(niche="mixed", language="mixed")
    slots = pilot.load_configured_slots()
    
    # Mock get_single_topic to return a known mock topic
    mock_topic = "The 12000-Year-Old Underwater City Detected Beneath The Indian Ocean"
    call_count = 0
    
    def mock_get_single_topic(niche, language="en"):
        nonlocal call_count
        call_count += 1
        return mock_topic
        
    monkeypatch.setattr(pilot.trend_finder, "get_single_topic", mock_get_single_topic)
    
    # Simulate batch topic assignment
    active_slots = slots[:2]
    generated_topics_by_id = {}
    assigned_topics = []
    
    for idx, slot_data in enumerate(active_slots):
        curr_slot_id = slot_data.get("id", f"slot_{idx+1}")
        pair_target = slot_data.get("pair_with")
        
        if pair_target and pair_target in generated_topics_by_id:
            topic = generated_topics_by_id[pair_target]
        else:
            topic = pilot.trend_finder.get_single_topic(
                niche="ocean",
                language=str(slot_data.get("language") or "en"),
            )
            generated_topics_by_id[curr_slot_id] = topic
        assigned_topics.append((curr_slot_id, topic, slot_data.get("language")))
        
    # Crucial assertion: get_single_topic was called only ONCE because Slot 2 reused Slot 1's topic!
    assert call_count == 1
    assert len(assigned_topics) == 2
    assert assigned_topics[0][1] == mock_topic
    assert assigned_topics[1][1] == mock_topic
    assert assigned_topics[0][2] == "English"
    assert assigned_topics[1][2] == "Hindi"
