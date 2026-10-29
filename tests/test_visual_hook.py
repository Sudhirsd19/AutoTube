"""Unit tests for VisualHookManager (Top Video Hook Banner & Thumbnail Sync)."""

import pytest
from pathlib import Path
from PIL import Image

from autotube.media.visual_hook import VisualHookManager


def test_visual_hook_text_generation():
    """Verify explosive curiosity hook generation with fallbacks."""
    vm = VisualHookManager()
    
    # Vedic test
    v_hook = vm.generate_hook_text("यमराज और नचिकेता का रहस्य", topic_category="vedic", language="hi")
    assert isinstance(v_hook, str)
    assert len(v_hook.strip()) > 3
    assert any("\u0900" <= c <= "\u097F" for c in v_hook)

    # Alien test
    a_hook = vm.generate_hook_text("Roswell UFO Incident and Alien Secrets", topic_category="mystery", language="en")
    assert isinstance(a_hook, str)
    assert len(a_hook.strip()) > 3


def test_create_top_hook_banner_vertical(tmp_path):
    """Verify creating 9:16 vertical video header banner PNG with alpha channel."""
    vm = VisualHookManager()
    out_file = tmp_path / "test_banner_vertical.png"
    
    hook_str = "मरने के बाद आत्मा कहाँ जाती है?"
    banner_p = vm.create_top_hook_banner(
        hook_text=hook_str,
        video_width=1080,
        video_height=1920,
        topic_category="vedic",
        output_path=out_file,
    )
    
    assert banner_p.exists()
    assert banner_p.stat().st_size > 1000
    
    with Image.open(banner_p) as img:
        assert img.mode == "RGBA"
        # Width should be ~90% of 1080 = 972
        assert img.width == 972
        assert img.height == 150


def test_create_top_hook_banner_landscape(tmp_path):
    """Verify creating 16:9 landscape video header banner PNG."""
    vm = VisualHookManager()
    out_file = tmp_path / "test_banner_landscape.png"
    
    hook_str = "THE CLASSIFIED TRUTH IS OUT!"
    banner_p = vm.create_top_hook_banner(
        hook_text=hook_str,
        video_width=1920,
        video_height=1080,
        topic_category="mystery",
        output_path=out_file,
    )
    
    assert banner_p.exists()
    assert banner_p.stat().st_size > 1000
    
    with Image.open(banner_p) as img:
        assert img.mode == "RGBA"
        assert img.height == 115
