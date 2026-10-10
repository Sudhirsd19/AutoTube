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

from autotube.media.visual_quality_gate import VisualQualityGate


def _scene_value(scene: Any, key: str, default: Any = None) -> Any:
    if isinstance(scene, dict):
        return scene.get(key, default)
    return getattr(scene, key, default)


def _as_text_list(value: Any) -> List[str]:
    if isinstance(value, str):
        return [value.strip()] if value.strip() else []
    if isinstance(value, (list, tuple, set)):
        return [str(item).strip() for item in value if str(item).strip()]
    return []


def _remove_assets(paths: List[Path]) -> None:
    for raw_path in paths:
        try:
            Path(raw_path).unlink(missing_ok=True)
        except Exception:
            pass


def _verify_scene_batch(
    clips: List[Path],
    scenes: List[Any],
    topic: str,
    provider: str,
    script: Any = None,
) -> bool:
    """Fail closed unless every returned clip passes frame QA for its own narration."""
    video_exts = {".mp4", ".mov", ".webm", ".mkv"}
    target_scenes = list(scenes or [])
    if not target_scenes and clips:
        narration = str(_scene_value(script, "narration", "") or topic)
        target_scenes = [{"narration": narration, "visual_subject": topic} for _ in clips]

    if len(clips) != len(target_scenes):
        print_warning(
            f"⚠️ {provider} QA blocked: got {len(clips)} clips for "
            f"{len(target_scenes)} scene(s)."
        )
        return False

    gate = VisualQualityGate()
    gate.strict = True
    for index, (raw_clip, scene) in enumerate(zip(clips, target_scenes)):
        clip = Path(raw_clip)
        if (
            not clip.exists()
            or clip.stat().st_size < 5000
            or clip.suffix.lower() not in video_exts
        ):
            print_warning(f"⚠️ {provider} QA blocked invalid motion clip for Scene {index + 1}: {clip}")
            return False

        subject = str(
            _scene_value(scene, "visual_subject", "")
            or _scene_value(scene, "subject", "")
            or topic
        ).strip()
        narration = str(
            _scene_value(scene, "narration", "")
            or _scene_value(scene, "text", "")
            or subject
            or topic
        ).strip()
        visual_description = str(
            _scene_value(scene, "visual_description", "")
            or _scene_value(scene, "description", "")
            or ""
        ).strip()
        must_show = _as_text_list(_scene_value(scene, "must_show", []))
        if subject and subject not in must_show:
            must_show.insert(0, subject)
        if visual_description and visual_description not in must_show:
            must_show.append(visual_description)

        plan = {
            "subject": subject,
            "action": str(_scene_value(scene, "visual_action", "") or _scene_value(scene, "action", "") or ""),
            "environment": str(_scene_value(scene, "visual_environment", "") or _scene_value(scene, "environment", "") or ""),
            "must_show": must_show,
            "avoid": _as_text_list(_scene_value(scene, "avoid", _scene_value(scene, "visual_avoid", []))),
        }
        result = gate.verify(clip, narration, plan)
        if not result.get("accepted"):
            print_warning(
                f"⚠️ {provider} QA rejected Scene {index + 1}: "
                f"{result.get('reason', 'frame QA did not approve this clip')}."
            )
            return False

    print_success(f"✅ {provider} strict frame QA passed for all {len(clips)} scene(s).")
    return True
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
            expected_count = len(scenes[:max_scenes]) if scenes else len(queries)
            if flow_scenes and len(flow_scenes) == expected_count:
                if _verify_scene_batch(flow_scenes, scenes[:max_scenes], getattr(script, "topic", "scene"), "Google Flow", script):
                    print_success(f"🎬 [Tier 1 Succeeded] Generated and QA-approved all {len(flow_scenes)}/{expected_count} scenes via Google Flow!")
                    return flow_scenes
                print_warning("⚠️ Google Flow clips failed strict frame QA; trying the next visual provider.")
            elif flow_scenes:
                print_warning(f"⚠️ Google Flow generated partial scenes ({len(flow_scenes)}/{expected_count}). Falling over to complete tier.")
            _remove_assets(flow_scenes)
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

            expected_count = len(queries)
            veo_scenes = veo_gen.generate_scenes(
                prompts=queries,
                output_dir=output_dir,
                slug=slug,
                aspect_ratio="9:16" if orientation == "portrait" else "16:9",
                max_scenes=max_scenes,
            )
            if veo_scenes and len(veo_scenes) == expected_count:
                if _verify_scene_batch(veo_scenes, scenes[:max_scenes], getattr(script, "topic", "scene"), "Gemini Veo", script):
                    print_success(f"🎬 [Tier 2 Succeeded] Generated and QA-approved all {len(veo_scenes)}/{expected_count} scenes with Gemini Veo!")
                    return veo_scenes
                print_warning("⚠️ Gemini Veo clips failed strict frame QA; trying the stock-video providers.")
            elif veo_scenes:
                print_warning(f"⚠️ Gemini Veo generated partial scenes ({len(veo_scenes)}/{expected_count}). Falling over to complete tier.")
            _remove_assets(veo_scenes)
        except (VeoQuotaExceededError, Exception) as gemini_err:
            err_msg = getattr(gemini_err, "message", str(gemini_err))
            print_warning(f"⚠️ Gemini (Veo) skipped or quota exceeded: {err_msg}")
            print_info("🔄 Moving directly to Real Motion Stock & AI Engine...")

    # -------------------------------------------------------------
    # TIER 2: Multi-Source AI Best Match Stock & Visuals (Mixkit + Coverr + Pexels + Pixabay)
    # -------------------------------------------------------------
    print_info("🎬 [Primary Engine] Acquiring Multi-Source AI Best Match Visual Assets (Mixkit, Coverr, Pexels, Pixabay)...")
    is_portrait = (orientation == "portrait")
    try:
        from autotube.media.multi_stock_aggregator import MultiStockAggregator
        multi_agg = MultiStockAggregator()
        if getattr(multi_agg, "visual_quality_gate", None):
            # QA must be fail-closed for both Shorts and landscape output.
            multi_agg.visual_quality_gate.strict = True

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
                    allow_ai_fallback=False,
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
                    allow_ai_fallback=False,
                )
                scene_assets.append(asset)

        expected_count = len(target_scenes) if target_scenes else len(queries[:max_scenes])
        valid_assets = [
            a for a in scene_assets
            if a is not None and a.exists() and a.stat().st_size > 5000 and (
                not is_portrait or a.suffix.lower() in {".mp4", ".mov", ".webm", ".mkv"}
            )
        ]
        has_duplicates = len(set(valid_assets)) != len(valid_assets)
        if len(valid_assets) == expected_count and not has_duplicates:
            print_success(f"🎬 Acquired all {len(valid_assets)} synchronized Multi-Source AI scene visual assets (100% unique motion footage)!")
            return valid_assets
        else:
            reason = "duplicate footage detected" if has_duplicates else f"partial motion assets ({len(valid_assets)}/{expected_count})"
            print_warning(f"⚠️ MultiStockAggregator: {reason}. Falling back to secondary motion fetcher...")
    except Exception as multi_err:
        print_warning(f"MultiStockAggregator fallback notice: {multi_err}")

    # Fallback to StockFetcher (Motion footage required for portrait Shorts)
    stock_fetcher = StockFetcher()
    is_motion_preferred = is_portrait
    if scenes:
        scene_assets = stock_fetcher.fetch_scene_visual_assets(
            scenes=scenes[:max_scenes],
            output_dir=output_dir,
            orientation=orientation,
            require_video=is_motion_preferred,
        )
    else:
        queries = getattr(script, "visual_keywords", []) or [getattr(script, "topic", "scene")]
        scene_assets = [
            stock_fetcher.fetch_best_visual_for_scene(
                subject=q,
                narration=getattr(script, "narration", None),
                output_dir=output_dir,
                orientation=orientation,
                require_video=is_motion_preferred,
            )
            for q in queries[:max_scenes]
        ]

    # Final strict checks also cover the secondary StockFetcher fallback.
    fallback_queries = getattr(script, "visual_keywords", []) or [getattr(script, "topic", "scene")]
    expected_count = len(scenes[:max_scenes]) if scenes else len(fallback_queries[:max_scenes])
    if len(scene_assets) != expected_count:
        _remove_assets([a for a in scene_assets if a])
        raise RuntimeError(
            f"Visual Pipeline Fail-Closed: received {len(scene_assets)} fallback asset(s) "
            f"for {expected_count} expected scene(s)."
        )

    if is_motion_preferred:
        for idx, a in enumerate(scene_assets):
            if not a or not a.exists() or a.suffix.lower() not in {".mp4", ".mov", ".webm", ".mkv"}:
                raise RuntimeError(
                    f"Visual Pipeline Fail-Closed: Scene {idx+1} received invalid or static asset: {a}. "
                    "Shorts requires 100% verified motion video footage for every scene."
                )
        if len(set(scene_assets)) != len(scene_assets):
            raise RuntimeError(
                f"Visual Pipeline Fail-Closed: Duplicate video clips detected across scenes: {[a.name for a in scene_assets]}. "
                "Scene footage repetition is strictly disallowed."
            )

    if not _verify_scene_batch(
        [Path(a) for a in scene_assets],
        scenes[:max_scenes],
        getattr(script, "topic", "scene"),
        "StockFetcher fallback",
        script,
    ):
        raise RuntimeError(
            "Visual Pipeline Fail-Closed: one or more fallback scenes failed strict narration-to-frame QA. "
            "Unsafe visual assets will not be rendered or uploaded."
        )

    print_success(f"🎬 Acquired {len(scene_assets)} synchronized, frame-QA-approved visual assets!")
    return scene_assets
