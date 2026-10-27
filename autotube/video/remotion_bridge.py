"""OpenMontage Remotion Bridge for AutoTube.

Orchestrates ultra-realistic video generation combining:
1. OpenMontage Gemini 3.8 Flash TTS for natural human voiceover.
2. AutoTube MultiStockAggregator for exact-matched video clips from Pexels, Pixabay, Mixkit.
3. OpenMontage Remotion Engine for high-end kinetic motion graphics & 9:16 vertical reels.
"""

import os
import re
import json
import time
import shutil
import subprocess
from pathlib import Path
from typing import Dict, Any, List, Optional, Callable

from autotube.config import PROJECT_ROOT, get_config
from autotube.utils.console import print_info, print_success, print_warning, print_error
from autotube.utils.file_utils import sanitize_filename
from autotube.utils.ffmpeg_helper import get_media_duration
from autotube.voice.gemini_tts import GeminiTTSEngine
from autotube.media.multi_stock_aggregator import MultiStockAggregator

OPENMONTAGE_DIR = Path(
    os.getenv("OPENMONTAGE_DIR", "")
) if os.getenv("OPENMONTAGE_DIR") else (
    Path("/home/opc/OpenMontage") if Path("/home/opc/OpenMontage").exists()
    else (PROJECT_ROOT.parent / "OpenMontage" if (PROJECT_ROOT.parent / "OpenMontage").exists()
    else (PROJECT_ROOT / "remotion-composer" if (PROJECT_ROOT / "remotion-composer").exists()
    else Path(r"D:\OpenMontage")))
)

def get_remotion_dir() -> Path:
    env_dir = os.getenv("OPENMONTAGE_DIR")
    if env_dir:
        p = Path(env_dir)
        if (p / "remotion-composer").exists():
            return p / "remotion-composer"
        if (p / "package.json").exists():
            return p

    candidates = [
        Path("/home/opc/OpenMontage/remotion-composer"),
        Path("/home/opc/AutoTube/remotion-composer"),
        PROJECT_ROOT.parent / "OpenMontage" / "remotion-composer",
        PROJECT_ROOT / "remotion-composer",
        Path(r"D:\OpenMontage\remotion-composer"),
    ]
    for c in candidates:
        if c.exists() and (c / "package.json").exists():
            return c
    return Path(r"D:\OpenMontage\remotion-composer")

REMOTION_DIR = get_remotion_dir()
REMOTION_PUBLIC_DIR = REMOTION_DIR / "public"


class RemotionBridge:
    """Bridges AutoTube's scripting, assets, and scheduling with OpenMontage's Remotion engine."""

    def __init__(self):
        self.cfg = get_config()
        self.tts = GeminiTTSEngine()
        self.multi_stock = MultiStockAggregator()
        self._ensure_environment()

    def _ensure_environment(self) -> None:
        """Verify Node.js and Remotion workspace are ready."""
        if not REMOTION_DIR.exists():
            raise RuntimeError(f"OpenMontage remotion-composer not found at: {REMOTION_DIR}")

        node_cmd = shutil.which("node") or shutil.which("node.exe")
        npx_cmd = shutil.which("npx.cmd") or shutil.which("npx") or shutil.which("npx.exe")

        if not node_cmd or not npx_cmd:
            raise RuntimeError("Node.js and npx are required for OpenMontage Remotion rendering.")

    def render_reel(
        self,
        title: str,
        script_text: str,
        voice: str = "Charon",
        scenes: Optional[List[Dict[str, Any]]] = None,
        bgm_path: Optional[Path] = None,
        bgm_volume: float = 0.14,
        output_format: str = "vertical_9x16",
        theme: str = "flat-motion-graphics",
        hook_text: Optional[str] = None,
        enable_subscribe_cta: bool = True,
        target_platform: str = "youtube",
        output_dir: Optional[Path] = None,
        progress_callback: Optional[Callable[[int, str], None]] = None,
    ) -> Path:
        """Render a complete viral Short or Reel using Multi-Stock clips + Remotion motion graphics."""
        slug = sanitize_filename(title or "hybrid_reel")
        is_vertical = output_format in ("vertical_9x16", "portrait", "short", "reel")
        target_comp = "ExplainerVertical" if is_vertical else "Explainer"
        orientation = "portrait" if is_vertical else "landscape"

        raw_out_dir = output_dir or (PROJECT_ROOT / "output" / ("shorts" if is_vertical else "longform"))
        out_directory = (PROJECT_ROOT / raw_out_dir).resolve() if not Path(raw_out_dir).is_absolute() else Path(raw_out_dir).resolve()
        out_directory.mkdir(parents=True, exist_ok=True)
        final_video_path = (out_directory / f"{slug}_{int(time.time())}.mp4").resolve()

        # Clean up old staging folders in public assets to keep Remotion bundle ultra-fast
        try:
            parent_remotion_assets = REMOTION_PUBLIC_DIR / "assets" / "autotube_remotion"
            if parent_remotion_assets.exists():
                for sub in parent_remotion_assets.iterdir():
                    if sub.is_dir() and sub.name != slug:
                        import shutil
                        shutil.rmtree(sub, ignore_errors=True)
        except Exception:
            pass

        # Unique staging folder inside Remotion public/assets
        staging_dir = REMOTION_PUBLIC_DIR / "assets" / "autotube_remotion" / slug
        staging_dir.mkdir(parents=True, exist_ok=True)

        if progress_callback:
            progress_callback(10, f"Synthesizing voice with Gemini 3.8 Flash TTS ({voice})...")

        # 1. Prepare Storyboard Scene Specs if not explicitly provided
        active_script = script_text.strip()
        if not scenes:
            raw_sentences = [
                s.strip() for s in re.split(r"[।\.\!\?]+", active_script) if len(s.strip()) > 8
            ]
            if not raw_sentences:
                raw_sentences = [active_script]
            scenes = [
                {"scene_number": i + 1, "narration": sent}
                for i, sent in enumerate(raw_sentences[:8])
            ]

        # 2. Synthesize Ultra-Realistic Voice with Gemini 3.8 Flash TTS
        local_voice_path = staging_dir / "narration.wav"
        tts_res = self.tts.synthesize(
            text=active_script,
            output_audio_path=local_voice_path,
            voice=voice,
            scenes=scenes,
        )

        total_duration = tts_res.duration_seconds
        scene_durations = list(tts_res.scene_durations or [])
        if len(scene_durations) != len(scenes):
            avg_dur = round(total_duration / len(scenes), 2)
            scene_durations = [avg_dur] * len(scenes)

        if progress_callback:
            progress_callback(35, f"Acquiring exact-matched stock videos across Pexels, Pixabay, Mixkit...")

        # 3. Multi-Stock Video Acquisition (Pexels + Pixabay + Mixkit)
        scene_video_assets: List[Path] = []
        for idx, sc in enumerate(scenes):
            sentence = str(sc.get("narration") or sc.get("text") or "").strip()
            print_info(f"   🎬 [Scene {idx+1}/{len(scenes)}] Searching multi-stock footage for: '{sentence[:45]}...'")

            # Query multi-stock aggregator
            candidate = self.multi_stock.get_best_scene_asset(
                scene_text=sentence,
                title=title,
                scene_index=idx,
                orientation=orientation,
                scene_plan={"narration": sentence, "scene_number": idx + 1},
                allow_archival_fallback=False,
                allow_ai_fallback=False,
            )

            # Fallback to direct Pexels query if aggregator returned None
            if not candidate or not Path(candidate).exists():
                print_warning(f"   ⚠️ MultiStock fallback triggered for Scene {idx+1}...")
                pexels_cand = self.multi_stock.pexels_fetcher.get_scene_video(
                    search_query=sentence[:40],
                    orientation=orientation,
                    scene_index=idx,
                )
                if pexels_cand and pexels_cand.exists():
                    candidate = pexels_cand

            # Fail-safe 1: Scan local stock & project video assets
            if not candidate or not Path(candidate).exists():
                local_candidates = (
                    list((PROJECT_ROOT / "assets" / "stock_cache").glob("*.mp4"))
                    + list((PROJECT_ROOT / "assets" / "pexels_videos").glob("*.mp4"))
                    + list((PROJECT_ROOT / "assets" / "nvidia_videos").glob("*.mp4"))
                    + list((PROJECT_ROOT / "assets" / "real_kailash").glob("*.mp4"))
                    + list(PROJECT_ROOT.glob("pexels_video_*.mp4"))
                    + list((PROJECT_ROOT / "temp").glob("**/*.mp4"))
                )
                valid_locals = [p for p in local_candidates if p.exists() and p.stat().st_size > 100_000]
                if valid_locals:
                    candidate = valid_locals[idx % len(valid_locals)]
                    print_info(f"   🛡️ Using local verified stock asset: {candidate.name}")

            # Fail-safe 2: Reuse previously acquired scene clip
            if (not candidate or not Path(candidate).exists()) and scene_video_assets:
                candidate = scene_video_assets[-1]
                print_info(f"   🛡️ Reusing active scene footage: {Path(candidate).name}")

            # Fail-safe 3: Generate emergency high-res cinematic motion clip using ffmpeg lavfi
            if not candidate or not Path(candidate).exists():
                em_clip = staging_dir / f"emergency_scene_{idx+1}.mp4"
                dur_s = max(4.0, scene_durations[idx] if idx < len(scene_durations) else 5.0)
                from autotube.utils.ffmpeg_helper import run_ffmpeg
                ok_em = run_ffmpeg([
                    "-f", "lavfi",
                    "-i", f"color=c=0x0f172a:s={'1080x1920' if is_vertical else '1920x1080'}:d={dur_s}:r=30",
                    "-c:v", "libx264", "-pix_fmt", "yuv420p", "-y", str(em_clip)
                ], desc="Generating emergency scene visual clip")
                if ok_em and em_clip.exists():
                    candidate = em_clip

            if not candidate or not Path(candidate).exists():
                raise RuntimeError(f"Could not acquire any stock video asset for Scene {idx+1}")

            # Stage clip inside Remotion public directory
            staged_clip = staging_dir / f"scene_{idx+1}.mp4"
            shutil.copy2(Path(candidate), staged_clip)
            scene_video_assets.append(staged_clip)

        # 4. Handle Background Music
        staged_bgm_rel: Optional[str] = None
        if bgm_path and Path(bgm_path).exists():
            staged_bgm = staging_dir / "bgm.mp3"
            shutil.copy2(Path(bgm_path), staged_bgm)
            staged_bgm_rel = f"assets/autotube_remotion/{slug}/bgm.mp3"
        else:
            # Auto-pick ambient meditation or calm music from AutoTube library
            avail_bgm = list((PROJECT_ROOT / "assets" / "audio").glob("**/*.mp3"))
            if avail_bgm:
                staged_bgm = staging_dir / "bgm.mp3"
                shutil.copy2(avail_bgm[0], staged_bgm)
                staged_bgm_rel = f"assets/autotube_remotion/{slug}/bgm.mp3"

        # 5. Build Remotion Cuts & Dynamic Overlays
        cuts: List[Dict[str, Any]] = []
        elapsed = 0.0
        for idx, (v_path, dur) in enumerate(zip(scene_video_assets, scene_durations)):
            in_s = round(elapsed, 2)
            out_s = round(elapsed + dur, 2)
            cuts.append({
                "id": f"scene-{idx+1}",
                "source": f"assets/autotube_remotion/{slug}/{v_path.name}",
                "in_seconds": in_s,
                "out_seconds": out_s,
                "transition_in": "cut" if idx == 0 else "fade",
                "transition_out": "fade",
                "transition_duration": 0.45,
            })
            elapsed += dur

        # Resolve Viral Hook & Typography
        display_hook = (hook_text or "").strip() or title.strip()
        is_hindi = any("\u0900" <= c <= "\u097F" for c in display_hook)
        hook_subtitle = "सच जानकर होश उड़ जाएंगे • पूरा देखें" if is_hindi else "Watch Till The End • Truth Revealed"

        # Dynamic Overlays:
        # A. Hero Title (opening kinetic burst)
        hero_duration = min(5.5, max(3.0, scene_durations[0] if scene_durations else 4.0))
        overlays: List[Dict[str, Any]] = [
            {
                "type": "hero_title",
                "in_seconds": 0.3,
                "out_seconds": hero_duration,
                "text": display_hook,
                "subtitle": hook_subtitle,
                "accentColor": "#F59E0B",
            }
        ]

        # B. Persistent Top Curiosity Header Banner (Classic AutoTube Hook Banner)
        if is_vertical and display_hook:
            overlays.append({
                "type": "top_hook_banner",
                "in_seconds": 0.0,
                "out_seconds": min(round(total_duration, 2), 8.5),
                "text": display_hook,
                "badge": "🚨 पूरा देखें" if is_hindi else "🚨 WATCH TILL END",
                "bgColor": "#FACC15",
                "textColor": "#000000",
            })

        # C. Mid-Video Shocking Fact Card
        if len(scene_durations) >= 3:
            mid_start = scene_durations[0] + 0.5
            mid_end = scene_durations[0] + scene_durations[1] - 0.2
            overlays.append({
                "type": "section_title",
                "in_seconds": round(mid_start, 2),
                "out_seconds": round(mid_end, 2),
                "text": "चौंकाने वाला सच" if is_hindi else "SHOCKING FACT",
                "subtitle": "रहस्य का खुलासा" if is_hindi else "Truth Revealed",
                "accentColor": "#22D3EE",
                "position": "bottom-left",
            })

        # D. Outro Channel Subscribe / Like / Bell Icon CTA (AutoTube Signature Feature)
        if enable_subscribe_cta and total_duration > 5.0:
            sub_start = max(1.0, round(total_duration - 5.5, 2))
            sub_end = max(2.0, round(total_duration - 0.2, 2))

            is_fb = (target_platform or "").lower() == "facebook"
            banner_name = "fb_follow_like_banner.png" if is_fb else "like_subscribe_bell_banner.png"
            banner_rel = f"assets/{banner_name}"
            local_banner = PROJECT_ROOT / "assets" / banner_name
            target_public_banner = REMOTION_PUBLIC_DIR / "assets" / banner_name
            if local_banner.exists() and not target_public_banner.exists():
                target_public_banner.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(local_banner, target_public_banner)
            cta_title = ("लाइक और फॉलो करें" if is_hindi else "LIKE & FOLLOW PAGE") if is_fb else ("लाइक और सब्सक्राइब करें" if is_hindi else "SUBSCRIBE FOR MORE")
            cta_sub = ("🔔 CosmoChronicle पेज को अभी फॉलो करें" if is_hindi else "🔔 Follow CosmoChronicle") if is_fb else ("🔔 नए वीडियो के लिए सब्सक्राइब करें" if is_hindi else "🔔 Daily Facts & Viral Stories")

            overlays.append({
                "type": "subscribe_cta",
                "in_seconds": sub_start,
                "out_seconds": sub_end,
                "text": cta_title,
                "subtitle": cta_sub,
                "imageSrc": banner_rel if target_public_banner.exists() else None,
                "accentColor": "#EF4444",
            })

        # Build kinetic word-level captions for Remotion
        captions: List[Dict[str, Any]] = []
        if hasattr(tts_res, "words") and tts_res.words:
            for w in tts_res.words:
                captions.append({
                    "word": w.word,
                    "startMs": int(round(w.start * 1000)),
                    "endMs": int(round(w.end * 1000)),
                })

        remotion_props = {
            "theme": theme,
            "audio": {
                "narration": {
                    "src": f"assets/autotube_remotion/{slug}/narration.wav",
                    "volume": 1.0,
                },
                **(
                    {"music": {"src": staged_bgm_rel, "volume": bgm_volume}}
                    if staged_bgm_rel
                    else {}
                ),
            },
            "cuts": cuts,
            "overlays": overlays,
            "captions": captions,
        }

        props_path = REMOTION_PUBLIC_DIR / "demo-props" / f"{slug}.json"
        props_path.parent.mkdir(parents=True, exist_ok=True)
        with open(props_path, "w", encoding="utf-8") as fh:
            json.dump(remotion_props, fh, indent=2, ensure_ascii=False)

        if progress_callback:
            progress_callback(75, f"Rendering {output_format} video timeline via OpenMontage Remotion Engine...")

        # 6. Run Remotion Render (Headless & Autonomous)
        import sys
        if sys.platform.startswith("win"):
            npx_cmd = shutil.which("npx.cmd") or shutil.which("npx") or "npx.cmd"
        else:
            npx_cmd = shutil.which("npx") or "npx"
        render_cmd = [
            npx_cmd,
            "remotion",
            "render",
            "src/index.tsx",
            target_comp,
            str(final_video_path),
            "--props",
            str(props_path),
            "--codec",
            "h264",
        ]

        # Headless Linux server optimizations & Chromium binding
        import sys
        if sys.platform.startswith("linux"):
            for chrom_bin in ["/usr/bin/chromium-browser", "/usr/bin/chromium", "/usr/bin/google-chrome"]:
                if os.path.exists(chrom_bin):
                    render_cmd.extend(["--browser-executable", chrom_bin])
                    break
            render_cmd.extend(["--gl", "angle", "--enable-multiprocess-on-linux"])

        # Cloud Server Speed Optimizations:
        # 1. Scale: 0.75 canvas scale reduces rasterization pixel workload by 44% with crisp 810x1440 quality
        # 2. Quality: 80% JPEG intermediate frames for optimal encode throughput
        scale_val = str(os.getenv("REMOTION_SCALE", "0.75"))
        render_cmd.extend([
            "--scale", scale_val,
            "--jpeg-quality", "80",
        ])
        if os.getenv("REMOTION_CONCURRENCY"):
            render_cmd.extend(["--concurrency", str(os.getenv("REMOTION_CONCURRENCY"))])

        print_info(f"🚀 Executing Remotion headless render: {target_comp} -> {final_video_path.name}")
        process = subprocess.Popen(
            render_cmd,
            cwd=str(REMOTION_DIR),
            shell=sys.platform.startswith("win"),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
        )

        last_progress_log = 0.0
        output_lines = []
        if process.stdout:
            for line in iter(process.stdout.readline, ""):
                output_lines.append(line)
                clean_line = line.strip()
                if clean_line:
                    now = time.time()
                    if "Rendered" in clean_line or "Encoded" in clean_line:
                        if now - last_progress_log >= 5.0:
                            print_info(f"   ⏳ [Remotion Progress] {clean_line}")
                            last_progress_log = now
                    elif any(k in clean_line for k in ("Bundled", "Finished", "Error", "Warning")):
                        print_info(f"   ℹ️ {clean_line}")

        process.wait()
        returncode = process.returncode

        # Safety Fallback: Check if Remotion saved relative to its own cwd
        if not final_video_path.exists():
            rel_remotion_target = REMOTION_DIR / "output" / ("shorts" if is_vertical else "longform") / final_video_path.name
            if rel_remotion_target.exists():
                shutil.move(str(rel_remotion_target), str(final_video_path))
            elif (REMOTION_DIR / final_video_path.name).exists():
                shutil.move(str(REMOTION_DIR / final_video_path.name), str(final_video_path))

        if returncode != 0 or not final_video_path.exists():
            tail_err = "".join(output_lines[-20:])
            print_error(f"Remotion render failed with code {returncode}:\n{tail_err}")
            raise RuntimeError(f"Remotion render failed. Check stdout logs above.")

        final_size_mb = final_video_path.stat().st_size / (1024 * 1024)
        print_success(f"🎉 OpenMontage Reel rendered successfully! File: {final_video_path.name} ({final_size_mb:.1f} MB)")

        if progress_callback:
            progress_callback(100, f"Render complete: {final_video_path.name} ({final_size_mb:.1f} MB)")

        return final_video_path
