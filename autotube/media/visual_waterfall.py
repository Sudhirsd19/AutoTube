"""High-Performance Visual Acquisition Engine (HuggingFace Removed).

Order of Execution:
Tier 1: Gemini AI Video (Veo Engine) - attempted if configured, fails over instantly if quota/error.
Tier 2: Vocal-Aligned Real Motion Stock Video Footage (Pexels HD) + Photorealistic AI (Pollinations).
        100% reliable, fast, zero timeouts, cinematic high retention.
"""

from pathlib import Path
from typing import Any, List, Optional

from autotube.config import get_config
from autotube.media.stock_fetcher import StockFetcher
from autotube.media.veo_generator import VeoQuotaExceededError, VeoVideoGenerator
from autotube.utils.console import (
    print_error,
    print_info,
    print_step,
    print_success,
    print_warning,
)


def acquire_scene_visuals_waterfall(
    script: Any,
    output_dir: Path,
    slug: str,
    orientation: str = "portrait",
    max_scenes: int = 12,
    **kwargs: Any,
) -> List[Path]:
    """Execute high-speed, reliable visual asset acquisition:
    1. Gemini (Veo) if available and quota allows (instant failover on error)
    2. Vocal-Aligned Real Motion Stock Video (Pexels HD) + Photorealistic AI (Pollinations)
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    scenes = getattr(script, "scenes", []) or []

    # -------------------------------------------------------------
    # TIER 1: Google Flow Bridge (Google AI Pro Studio Engine)
    # -------------------------------------------------------------
    try:
        import urllib.request
        is_flow_connected = False
        try:
            with urllib.request.urlopen("http://localhost:9222/json/version", timeout=1) as resp:
                if resp.status == 200:
                    is_flow_connected = True
        except Exception:
            pass

        if is_flow_connected:
            from autotube.media.google_flow_bridge import GoogleFlowBridge
            flow_bridge = GoogleFlowBridge()
            print_info("🎬 [Tier 1] Generating native 3D AI video clips via Google Flow (Google AI Pro Engine)...")
            flow_scenes = []
            queries = [
                f"{getattr(s, 'visual_subject', '')}, {getattr(s, 'visual_description', '')}"
                for s in scenes[:max_scenes]
            ]
            for i, q in enumerate(queries):
                out_clip = output_dir / f"{slug}_flow_scene_{i+1}.mp4"
                res_clip = flow_bridge.generate_scene_clip(
                    prompt=q,
                    output_path=out_clip,
                    aspect_ratio="9:16" if orientation == "portrait" else "16:9",
                )
                if res_clip and res_clip.exists():
                    flow_scenes.append(res_clip)
                else:
                    break
            if flow_scenes and len(flow_scenes) >= 1:
                print_success(f"🎬 [Tier 1 Succeeded] Generated {len(flow_scenes)} scenes via Google Flow!")
                return flow_scenes
    except Exception as fe:
        print_warning(f"Google Flow Bridge notice: {fe}")

    # -------------------------------------------------------------
    # TIER 2: Gemini (Veo Video Generation - API Fallback)
    # -------------------------------------------------------------
    cfg = get_config()
    if cfg.gemini_api_key:
        try:
            print_info("🤖 Checking Gemini (Veo Engine) AI Video Generation...")
            veo_gen = VeoVideoGenerator()
            queries = [
                f"{getattr(s, 'visual_subject', '')}, {getattr(s, 'visual_description', '')}"
                for s in scenes[:max_scenes]
            ]
            if not queries:
                queries = [getattr(script, "topic", "cinematic scene")]

            veo_scenes = veo_gen.generate_scenes(
                prompts=queries,
                output_dir=output_dir,
                slug=slug,
                aspect_ratio="9:16" if orientation == "portrait" else "16:9",
                max_scenes=max_scenes,
            )
            if veo_scenes and len(veo_scenes) >= 1:
                print_success(f"🎬 [Tier 1 Succeeded] Generated {len(veo_scenes)} scenes with Gemini Veo!")
                return veo_scenes
        except (VeoQuotaExceededError, Exception) as gemini_err:
            err_msg = getattr(gemini_err, "message", str(gemini_err))
            print_warning(f"⚠️ Gemini (Veo) skipped or quota exceeded: {err_msg}")
            print_info("🔄 Moving directly to Real Motion Stock & AI Engine...")

    # -------------------------------------------------------------
    # TIER 2: Multi-Source AI Best Match Stock & Visuals (Mixkit + Coverr + Pexels + Pixabay + AI)
    # -------------------------------------------------------------
    print_info("🎬 [Primary Engine] Acquiring Multi-Source AI Best Match Visual Assets (Mixkit, Coverr, Pexels, AI)...")
    try:
        from autotube.media.multi_stock_aggregator import MultiStockAggregator
        multi_agg = MultiStockAggregator()
        scene_assets = []
        topic = getattr(script, "topic", "scene")

        target_scenes = scenes[:max_scenes] if scenes else []
        if target_scenes:
            for idx, s in enumerate(target_scenes):
                sentence = f"{getattr(s, 'narration', '')} {getattr(s, 'visual_subject', '')}".strip()
                asset = multi_agg.get_best_scene_asset(
                    scene_text=sentence or topic,
                    title=topic,
                    scene_index=idx,
                    orientation=orientation,
                )
                scene_assets.append(asset)
        else:
            queries = getattr(script, "visual_keywords", []) or [topic]
            for idx, q in enumerate(queries[:max_scenes]):
                asset = multi_agg.get_best_scene_asset(
                    scene_text=q,
                    title=topic,
                    scene_index=idx,
                    orientation=orientation,
                )
                scene_assets.append(asset)

        if scene_assets:
            print_success(f"🎬 Acquired {len(scene_assets)} synchronized Multi-Source AI scene visual assets!")
            return scene_assets
    except Exception as multi_err:
        print_warning(f"MultiStockAggregator fallback notice: {multi_err}")

    # Fallback to StockFetcher if needed
    stock_fetcher = StockFetcher()
    if scenes:
        scene_assets = stock_fetcher.fetch_scene_visual_assets(
            scenes=scenes[:max_scenes],
            output_dir=output_dir,
            orientation=orientation,
            require_video=False,
        )
    else:
        queries = getattr(script, "visual_keywords", []) or [getattr(script, "topic", "scene")]
        scene_assets = [
            stock_fetcher.fetch_best_visual_for_scene(
                subject=q,
                narration=getattr(script, "narration", None),
                output_dir=output_dir,
                orientation=orientation,
                require_video=False,
            )
            for q in queries[:max_scenes]
        ]

    print_success(f"🎬 Acquired {len(scene_assets)} synchronized scene visual assets!")
    return scene_assets
