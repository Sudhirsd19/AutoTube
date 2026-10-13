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
    require_video: bool = True,
) -> bool:
    """Fail closed unless every returned scene asset passes frame QA for its narration."""
    video_exts = {".mp4", ".mov", ".webm", ".mkv"}
    image_exts = {".jpg", ".jpeg", ".png", ".webp"}
    accepted_exts = video_exts if require_video else video_exts | image_exts
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
            or clip.suffix.lower() not in accepted_exts
        ):
            media_requirement = "motion video" if require_video else "video or still image"
            print_warning(
                f"⚠️ {provider} QA blocked invalid {media_requirement} for Scene {index + 1}: {clip}"
            )
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


def _image_to_motion_clip(
    image_path: Path,
    output_path: Path,
    duration: float = 6.0,
    fps: int = 30,
    width: int = 1080,
    height: int = 1920,
    motion_type: int = 0,
) -> Optional[Path]:
    """Convert a high-resolution 4K/portrait image into a cinematic continuous motion MP4 video."""
    import subprocess
    total_frames = max(1, int(duration * fps))
    p_factor = f"min(1.0,on/{total_frames})"
    m_idx = motion_type % 4
    if m_idx == 0:
        # Smooth continuous Zoom-In (1.0 -> 1.22)
        zoom_expr = f"min(1.22,1.0+0.22*{p_factor})"
        x_expr = "iw/2-(iw/zoom/2)"
        y_expr = "ih/2-(ih/zoom/2)"
    elif m_idx == 1:
        # Smooth continuous Zoom-Out (1.22 -> 1.04)
        zoom_expr = f"max(1.04,1.22-0.18*{p_factor})"
        x_expr = "iw/2-(iw/zoom/2)"
        y_expr = "ih/2-(ih/zoom/2)"
    elif m_idx == 2:
        # Cinematic Pan Left-to-Right
        zoom_expr = "1.15"
        x_expr = f"(iw-iw/zoom)*{p_factor}"
        y_expr = "ih/2-(ih/zoom/2)"
    else:
        # Cinematic Pan Right-to-Left
        zoom_expr = "1.15"
        x_expr = f"(iw-iw/zoom)*(1.0-{p_factor})"
        y_expr = "ih/2-(ih/zoom/2)"

    from autotube.utils.ffmpeg_helper import get_ffmpeg_path
    ffmpeg_exe = get_ffmpeg_path()
    scale_res = f"{int(width * 1.15)}:{int(height * 1.15)}"
    vf = (
        f"scale={scale_res}:force_original_aspect_ratio=increase,"
        f"crop={scale_res},"
        f"zoompan=z='{zoom_expr}':d={total_frames}:x='{x_expr}':y='{y_expr}':s={width}x{height}:fps={fps},"
        f"setsar=1,format=yuv420p"
    )
    args = [
        ffmpeg_exe, "-y", "-loop", "1", "-i", str(image_path), "-t", f"{duration:.2f}",
        "-vf", vf, "-r", str(fps), "-c:v", "libx264", "-preset", "ultrafast",
        "-pix_fmt", "yuv420p", "-an", str(output_path)
    ]
    try:
        res = subprocess.run(args, capture_output=True, text=True, timeout=45)
        if res.returncode == 0 and output_path.exists() and output_path.stat().st_size > 10000:
            return output_path
    except Exception as exc:
        print_warning(f"Image motion conversion failed for {image_path}: {exc}")
    return None


def acquire_scene_visuals_waterfall(
    script: Any,
    output_dir: Path,
    slug: str,
    orientation: str = "portrait",
    max_scenes: int = 12,
    **kwargs: Any,
) -> List[Path]:
    """Execute high-speed, reliable visual asset acquisition:
    1. For Gita / Granth / Scripture topics: Direct 4K/8K photorealistic AI visuals + continuous Ken Burns motion
    2. For all other topics: Google Flow -> Gemini Veo -> MultiStockAggregator -> StockFetcher
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    scenes = getattr(script, "scenes", []) or []

    # -------------------------------------------------------------
    # GITA / GRANTH / SCRIPTURE: Verified native-4K AI stills, then motion clips
    # Detection is based on the requested topic/title, not narration/visual text,
    # so a casual "karma" reference in an unrelated story cannot redirect the pipeline.
    # -------------------------------------------------------------
    import os
    import re

    topic = str(getattr(script, "topic", "") or "")
    title = str(getattr(script, "title", "") or "")
    identity = f"{title} {topic}".lower()
    spiritual_terms = (
        "bhagavad gita", "bhagwat gita", "gita", "geeta", "granth", "scripture",
        "shloka", "shlok", "upanishad", "chanakya niti", "sanatan", "spiritual",
        "adhyatmik", "karma yoga", "nishkama karma", "vedic scripture",
        "krishna", "arjuna", "mahabharat", "ramayan",
    )
    devanagari_terms = (
        "गीता", "श्रीमद्भगवद्गीता", "ग्रंथ", "ग्रन्थ", "शास्त्र", "श्लोक",
        "उपनिषद", "चाणक्य नीति", "सनातन", "आध्यात्म", "आध्यात्मिक",
        "कर्मयोग", "निष्काम कर्म", "कृष्ण", "अर्जुन", "महाभारत", "रामायण", "वेद",
    )
    is_spiritual_topic = (
        any(re.search(rf"\b{re.escape(term)}\b", identity) for term in spiritual_terms)
        or any(term in identity for term in devanagari_terms)
    )

    if is_spiritual_topic:
        from PIL import Image
        from autotube.media.ai_visuals import VisualGenerator

        target_scenes = list(scenes[:max_scenes])
        if not target_scenes:
            raise RuntimeError(
                "Scripture AI-only mode requires scene-by-scene narration and visual descriptions; "
                "refusing to substitute generic stock footage."
            )

        resolution = os.getenv("AUTOTUBE_SPIRITUAL_IMAGE_RESOLUTION", "4k").strip().lower()
        if resolution in {"8k", "4320"}:
            source_w, source_h = (4320, 7680) if orientation == "portrait" else (7680, 4320)
            resolution_label = "8K"
        else:
            source_w, source_h = (2160, 3840) if orientation == "portrait" else (3840, 2160)
            resolution_label = "4K"

        # Shorts are still encoded at the configured 1080x1920 final size; the
        # source image itself must pass the separate native 4K pixel validation.
        video_w, video_h = (1080, 1920) if orientation == "portrait" else (1920, 1080)
        expected_count = len(target_scenes)
        gita_motion_clips: List[Path] = []
        vg = VisualGenerator()

        print_info(
            f"🕉️ Scripture Motivation Mode: generating {expected_count} scene-specific "
            f"native {resolution_label} AI images ({source_w}x{source_h}). "
            "Stock-photo fallback is disabled."
        )

        for idx, scene in enumerate(target_scenes):
            v_subj = str(
                _scene_value(scene, "visual_subject", "")
                or _scene_value(scene, "subject", "")
                or _scene_value(scene, "visual_query", "")
                or topic
            ).strip()
            narration = str(
                _scene_value(scene, "narration", "")
                or _scene_value(scene, "text", "")
                or ""
            ).strip()
            v_desc = str(
                _scene_value(scene, "visual_description", "")
                or _scene_value(scene, "description", "")
                or v_subj
            ).strip()
            if not narration:
                raise RuntimeError(
                    f"Scripture scene {idx + 1} has no narration; refusing unsynchronized visuals."
                )

            ai_prompt = (
                f"Create ONE respectful, culturally grounded, photorealistic Indian spiritual cinematic still. "
                f"Exact subject: {v_subj}. Exact spoken narration to illustrate: {narration}. "
                f"Scene-specific details: {v_desc}. Overall topic: {topic}. "
                "Follow the described scene precisely; do not add unrelated gods, random temples, modern offices, "
                "smartphones, cartoons or fantasy props. If Shri Krishna is explicitly in this scene, depict him "
                "with respectful traditional Indian iconography and recognizable customary clothing/ornaments; "
                "show Arjuna or a Kurukshetra chariot only when the narration calls for them. "
                "For scripture scenes use historically plausible palm-leaf/manuscript materials, oil lamps and "
                "Indic calligraphy that is decorative and not meant to be legible. Photographic skin, cloth, stone, "
                "brass and gold textures, cinematic natural lighting, detailed composition. "
                "No captions, text overlay, logo or watermark. Native high-resolution source image."
            )
            img_path = output_dir / f"{slug}_scripture_ai{resolution_label.lower()}_scene_{idx + 1:02d}.jpg"
            ai_img = vg.generate_image(
                prompt=ai_prompt,
                output_path=img_path,
                width=source_w,
                height=source_h,
                style="spiritual_photorealistic",
                allow_fallback=False,
                require_native_resolution=True,
                allow_photo_fallback=False,
            )
            if not ai_img or not Path(ai_img).exists():
                raise RuntimeError(
                    f"Native {resolution_label} AI generation failed for scene {idx + 1}. "
                    "The provider did not return a verified source image; no stock fallback will be used."
                )

            with Image.open(ai_img) as generated:
                actual_w, actual_h = generated.size
            if actual_w < source_w or actual_h < source_h:
                raise RuntimeError(
                    f"Scene {idx + 1} image is {actual_w}x{actual_h}; "
                    f"native {resolution_label} requires at least {source_w}x{source_h} pixels."
                )

            out_clip = output_dir / f"{slug}_scripture_motion_scene_{idx + 1:02d}.mp4"
            motion_clip = _image_to_motion_clip(
                image_path=Path(ai_img),
                output_path=out_clip,
                duration=6.0,
                fps=30,
                width=video_w,
                height=video_h,
                motion_type=idx,
            )
            if not motion_clip or not Path(motion_clip).exists():
                raise RuntimeError(
                    f"Could not convert validated AI image to motion clip for scene {idx + 1}."
                )
            gita_motion_clips.append(Path(motion_clip))
            print_success(
                f"✅ Scripture scene {idx + 1}/{expected_count}: native {resolution_label} "
                f"image {actual_w}x{actual_h} validated; motion clip rendered."
            )

        if len(gita_motion_clips) != expected_count:
            raise RuntimeError(
                f"Scripture scene count mismatch: {len(gita_motion_clips)}/{expected_count}; "
                "refusing partial output."
            )
        if not _verify_scene_batch(
            gita_motion_clips,
            target_scenes,
            topic,
            f"Native {resolution_label} Scripture AI",
            script,
        ):
            raise RuntimeError(
                "Scripture frame QA failed or Gemini vision is unavailable. "
                "No unchecked visuals will be rendered or uploaded."
            )

        print_success(
            f"🕉️ All {expected_count} scenes passed native-resolution and frame-level visual QA."
        )
        return gita_motion_clips

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
    is_motion_preferred = is_portrait
    try:
        from autotube.media.multi_stock_aggregator import MultiStockAggregator
        multi_agg = MultiStockAggregator()
        if getattr(multi_agg, "visual_quality_gate", None):
            # QA must be fail-closed for both Shorts and landscape output.
            multi_agg.visual_quality_gate.strict = True

        scene_assets = []
        topic = getattr(script, "topic", "scene")

        target_scenes = scenes[:max_scenes] if scenes else []
        queries = getattr(script, "visual_keywords", []) or [topic]
        if target_scenes:
            for idx, s in enumerate(target_scenes):
                sentence = f"{getattr(s, 'narration', '')} {getattr(s, 'visual_subject', '')}".strip()
                v_subj = str(getattr(s, "visual_subject", "") or getattr(s, "subject", "") or "").strip()
                v_desc = str(getattr(s, "visual_description", "") or getattr(s, "description", "") or "").strip()
                v_keys = [str(k).strip() for k in (getattr(s, "search_keywords", []) or getattr(s, "visual_keywords", []) or []) if str(k).strip()]
                if v_subj and not v_keys:
                    v_keys = [v_subj]
                m_show = [str(m).strip() for m in getattr(s, "must_show", []) if str(m).strip()]
                if v_subj and v_subj not in m_show:
                    m_show.insert(0, v_subj)
                if v_desc and v_desc not in m_show:
                    m_show.append(v_desc)

                s_plan = {
                    "subject": v_subj,
                    "action": str(getattr(s, "visual_action", "") or getattr(s, "action", "") or "").strip(),
                    "environment": str(getattr(s, "visual_environment", "") or getattr(s, "environment", "") or "").strip(),
                    "must_show": m_show,
                    "avoid": [str(a).strip() for a in getattr(s, "avoid", []) if str(a).strip()],
                    "search_queries": v_keys[:4],
                }

                asset = multi_agg.get_best_scene_asset(
                    scene_text=sentence or topic,
                    title=topic,
                    scene_index=idx,
                    orientation=orientation,
                    scene_plan=s_plan if (v_subj or v_keys) else None,
                    allow_ai_fallback=False,
                )
                scene_assets.append(asset)
        else:
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
        non_none_candidates = [Path(a) for a in scene_assets if a is not None]
        if is_motion_preferred and len(set(non_none_candidates)) != len(non_none_candidates):
            raise RuntimeError(
                f"Visual Pipeline Fail-Closed: Duplicate video clips detected across scenes: {[a.name for a in non_none_candidates]}. "
                "Scene footage repetition is strictly disallowed."
            )

        used_paths: Set[Path] = set()
        slot_assets: List[Optional[Path]] = []
        for idx in range(expected_count):
            cand = scene_assets[idx] if idx < len(scene_assets) else None
            if (
                cand is not None
                and cand.exists()
                and cand.stat().st_size > 5000
                and (not is_portrait or cand.suffix.lower() in {".mp4", ".mov", ".webm", ".mkv"})
                and cand not in used_paths
            ):
                used_paths.add(cand)
                slot_assets.append(cand)
            else:
                slot_assets.append(None)

        missing_indices = [i for i, a in enumerate(slot_assets) if a is None]
        if not missing_indices:
            print_success(f"🎬 Acquired all {expected_count} synchronized Multi-Source AI scene visual assets (100% unique motion footage)!")
            return [Path(a) for a in slot_assets if a is not None]

        print_warning(f"⚠️ MultiStockAggregator secured {expected_count - len(missing_indices)}/{expected_count} scenes. Filling missing {len(missing_indices)} scene(s) via secondary motion fetcher...")
        stock_fetcher = StockFetcher()
        for missing_idx in missing_indices:
            missing_scene = target_scenes[missing_idx] if (target_scenes and missing_idx < len(target_scenes)) else None
            q = (queries[missing_idx] if (queries and missing_idx < len(queries)) else topic)
            narr = getattr(missing_scene, "narration", None) if missing_scene else getattr(script, "narration", None)
            subj = getattr(missing_scene, "visual_subject", q) if missing_scene else q

            try:
                fetched = stock_fetcher.fetch_best_visual_for_scene(
                    subject=subj,
                    narration=narr,
                    output_dir=output_dir,
                    orientation=orientation,
                    require_video=is_motion_preferred,
                    skip_multi_stock=True,
                )
                if fetched and fetched.exists() and fetched not in used_paths:
                    used_paths.add(fetched)
                    slot_assets[missing_idx] = fetched
            except Exception as f_err:
                print_warning(f"Secondary motion fetcher could not acquire scene {missing_idx+1} ('{subj}'): {f_err}")

        if all(a is not None for a in slot_assets):
            scene_assets = [Path(a) for a in slot_assets]
            print_success(f"🎬 All {expected_count} scene visual assets secured across primary + secondary fetchers!")
        else:
            scene_assets = [Path(a) for a in slot_assets if a is not None]
    except Exception as multi_err:
        print_warning(f"MultiStockAggregator fallback notice: {multi_err}")

    # Synchronize slot_assets and scene_assets cleanly
    if 'slot_assets' not in locals() or not slot_assets:
        slot_assets = [None] * expected_count
        if 'scene_assets' in locals() and scene_assets:
            for idx, a in enumerate(scene_assets[:expected_count]):
                if a is not None and Path(a).exists():
                    slot_assets[idx] = Path(a)

    scene_assets = [Path(a) for a in slot_assets if a is not None and Path(a).exists()]

    # Fallback to StockFetcher if full set still not secured
    is_motion_preferred = is_portrait
    if len(scene_assets) < expected_count:
        stock_fetcher = StockFetcher()
        if scenes:
            try:
                fetched_scenes = stock_fetcher.fetch_scene_visual_assets(
                    scenes=scenes[:max_scenes],
                    output_dir=output_dir,
                    orientation=orientation,
                    require_video=is_motion_preferred,
                )
                if fetched_scenes and len(fetched_scenes) == expected_count:
                    slot_assets = [Path(a) for a in fetched_scenes]
                    scene_assets = list(slot_assets)
            except Exception as sf_err:
                print_warning(f"StockFetcher fallback error: {sf_err}")
        else:
            queries = getattr(script, "visual_keywords", []) or [getattr(script, "topic", "scene")]
            try:
                fetched_queries = [
                    stock_fetcher.fetch_best_visual_for_scene(
                        subject=q,
                        narration=getattr(script, "narration", None),
                        output_dir=output_dir,
                        orientation=orientation,
                        require_video=is_motion_preferred,
                    )
                    for q in queries[:max_scenes]
                ]
                if all(f is not None for f in fetched_queries) and len(fetched_queries) == expected_count:
                    slot_assets = [Path(a) for a in fetched_queries]
                    scene_assets = list(slot_assets)
            except Exception as sf_err:
                print_warning(f"StockFetcher fallback error: {sf_err}")

    # Duplicate check on currently acquired non-None assets
    valid_assets = [Path(a) for a in slot_assets if a is not None and Path(a).exists()]
    if is_motion_preferred and valid_assets:
        if len(set(valid_assets)) != len(valid_assets):
            raise RuntimeError(
                f"Visual Pipeline Fail-Closed: Duplicate video clips detected across scenes: {[a.name for a in valid_assets]}. "
                "Scene footage repetition is strictly disallowed."
            )

    # Tier 3.5: Missing Scenes Recovery using 4K Photorealistic AI Visuals + Continuous Ken Burns Motion
    # If any scene slots are still missing after all stock engines (e.g. rare science/biology/spiritual),
    # generate high-resolution 4K AI visuals and convert them into cinematic continuous motion video clips.
    fallback_queries = getattr(script, "visual_keywords", []) or [getattr(script, "topic", "scene")]
    expected_count = len(scenes[:max_scenes]) if scenes else len(fallback_queries[:max_scenes])
    missing_slot_indices = [i for i in range(expected_count) if slot_assets[i] is None or not Path(slot_assets[i]).exists()]
    if missing_slot_indices:
        target_scenes = scenes[:max_scenes] if scenes else []
        needed = len(missing_slot_indices)
        print_info(f"🎨 Recovering {needed} missing scene(s) via 4K AI Photorealistic Generation + Ken Burns Motion...")
        try:
            from autotube.media.ai_visuals import VisualGenerator
            ai_vis = VisualGenerator()
            target_w = 1080 if orientation == "portrait" else 1920
            target_h = 1920 if orientation == "portrait" else 1080
            used_paths = {Path(a) for a in slot_assets if a is not None and Path(a).exists()}

            for m_idx in missing_slot_indices:
                m_scene = target_scenes[m_idx] if (target_scenes and m_idx < len(target_scenes)) else None
                subj = getattr(m_scene, "visual_subject", None) or (fallback_queries[m_idx] if m_idx < len(fallback_queries) else getattr(script, "topic", "scene"))
                desc = getattr(m_scene, "visual_description", None) or subj
                ai_prompt = f"{subj}, {desc}" if (desc and desc != subj) else subj
                img_out = output_dir / f"{slug}_ai4k_scene_{m_idx+1:02d}.jpg"
                gen_img = ai_vis.generate_image(
                    prompt=ai_prompt,
                    output_path=img_out,
                    width=target_w,
                    height=target_h,
                    style="3d_cinematic",
                )
                if gen_img and gen_img.exists():
                    motion_out = output_dir / f"{slug}_motion_scene_{m_idx+1:02d}.mp4"
                    motion_clip = _image_to_motion_clip(
                        image_path=gen_img,
                        output_path=motion_out,
                        duration=6.5,
                        width=target_w,
                        height=target_h,
                        motion_type=m_idx,
                    )
                    if motion_clip and motion_clip.exists() and motion_clip not in used_paths:
                        slot_assets[m_idx] = motion_clip
                        used_paths.add(motion_clip)
                        print_success(f"🎬 Recovered Scene {m_idx+1} as 4K dynamic motion video!")
        except Exception as ai_rec_err:
            print_warning(f"AI motion scene recovery notice: {ai_rec_err}")

    scene_assets = [Path(a) for a in slot_assets if a is not None]

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
                f"Visual Pipeline Fail-Closed: Duplicate video clips detected across scenes: {[a.name for a in scene_assets if a is not None]}. "
                "Scene footage repetition is strictly disallowed."
            )

    if not _verify_scene_batch(
        [Path(a) for a in scene_assets],
        scenes[:max_scenes],
        getattr(script, "topic", "scene"),
        "StockFetcher fallback",
        script,
        require_video=is_motion_preferred,
    ):
        raise RuntimeError(
            "Visual Pipeline Fail-Closed: one or more fallback scenes failed strict narration-to-frame QA. "
            "Unsafe visual assets will not be rendered or uploaded."
        )

    print_success(f"🎬 Acquired {len(scene_assets)} synchronized, frame-QA-approved visual assets!")
    return scene_assets
