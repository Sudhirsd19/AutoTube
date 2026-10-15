"""Sample video frames and verify scene relevance with Gemini vision."""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
import shutil
import re
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

import imageio_ffmpeg


GEMINI_HTTP_TIMEOUT_MS = int(os.getenv("AUTOTUBE_GEMINI_HTTP_TIMEOUT_MS", "60000"))


class VisualQualityGate:
    """Final frame-level QA. Uses Gemini when GEMINI_API_KEY is present."""

    MODELS = (
        "gemini-3.5-flash-lite",
        "gemini-flash-lite-latest",
        "gemini-3.8-flash",
        "gemini-3.5-flash",
        "gemini-3-flash-preview",
    )

    def __init__(self, min_confidence: int = 75, min_coverage: int = 70) -> None:
        self.min_confidence = min_confidence
        self.min_coverage = min_coverage
        self.strict = os.getenv("AUTOTUBE_FRAME_QA_STRICT", "0").lower() in {"1", "true", "yes"}
        self._client = None

    def _get_client(self):
        if self._client is not None:
            return self._client
        key = os.getenv("GEMINI_API_KEY", "").strip()
        if not key:
            return None
        try:
            from google import genai
            from google.genai import types
            self._client = genai.Client(
                api_key=key,
                http_options=types.HttpOptions(
                    timeout=GEMINI_HTTP_TIMEOUT_MS,
                    retry_options=types.HttpRetryOptions(attempts=3),
                ),
            )
        except Exception as exc:
            print(f"[FrameQA] Gemini client initialization failed: {type(exc).__name__}: {exc}")
            self._client = None
        return self._client

    def verify(self, asset_path: Path, narration: str, scene_plan: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        path = Path(asset_path)
        if not path.exists() or path.stat().st_size < 5000:
            return {"accepted": False, "confidence": 0, "coverage": 0, "reason": "Invalid asset.", "mode": "local"}

        client = self._get_client()
        if client is None:
            return {
                "accepted": not self.strict,
                "confidence": None,
                "coverage": None,
                "reason": "Gemini vision unavailable.",
                "mode": "metadata_only",
            }

        image_mime_types = {
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".png": "image/png",
            ".webp": "image/webp",
        }
        is_still_image = path.suffix.lower() in image_mime_types
        frames = [path] if is_still_image else self._extract_frames(path)
        if not frames:
            return {
                "accepted": not self.strict,
                "confidence": 0,
                "coverage": 0,
                "reason": "No frames could be extracted.",
                "mode": "frame_qa",
            }

        plan = scene_plan or {}
        prompt = f"""You are visual QA for a YouTube video scene.
EXACT NARRATION: {narration}
TARGET SUBJECT: {plan.get("subject", "")}
MUST SHOW: {json.dumps(plan.get("must_show", []), ensure_ascii=False)}
MUST AVOID: {json.dumps(plan.get("avoid", []), ensure_ascii=False)}

Judge ONLY the supplied video frames or the supplied still image.
Guidelines:
- Visuals MUST genuinely depict or directly support the scene narration and TARGET SUBJECT.
- If narration is in Hindi or non-English, understand the spoken sentence in context with TARGET SUBJECT.
- Check MUST SHOW and MUST AVOID elements reasonably:
  * For astronomy, space, black hole, star, or cosmos topics: footage MUST show authentic cosmic phenomena (deep space, nebulae, stars, planets, galaxies, black hole simulations, celestial motion). DO NOT accept human faces, helmets, visors, modern offices, or terrestrial daytime scenes!
  * For history, mythology, temple, or archaeology topics: footage of ancient stone ruins, temple architecture, archaeological excavations, ancient artifacts, or historical landscapes ARE VALID ACCEPTABLE EVIDENCE for the subject.
  * For nature, geography, science, wildlife, rivers, or Amazon topics: footage of rainforest canopies, rivers, thermal steam, jungle wildlife, reptiles, or deep nature landscapes ARE VALID ACCEPTABLE EVIDENCE for the subject.
  * DO NOT accept modern gadgets, doorbells, modern yoga studios, modern city streets, or outer space footage for ancient history/temple/rainforest narration!
  * Do NOT fail footage if one optional secondary element from MUST SHOW is absent, as long as the core TARGET SUBJECT is visually represented.
- Check MUST AVOID items strictly: if modern offices, smartphones, irrelevant talking faces, helmets, doorbells, or modern cartoons appear, add them to 'violations'.
- DO NOT accept completely unrelated stock footage (e.g., modern cities/offices/talking faces when narration discusses space, biology, physics, or ancient temples).
- Set accepted to true when visuals have strong semantic bearing on the spoken words.
Return JSON only:
{{"confidence":0-100,"coverage":0-100,"accepted":true/false,"reason":"one sentence","violations":[]}}
Accept when confidence >= {self.min_confidence}, coverage >= {self.min_coverage}, and there are no violations.
"""

        try:
            from google.genai import types

            contents: List[Any] = [
                types.Part.from_bytes(
                    data=p.read_bytes(),
                    mime_type=(
                        image_mime_types.get(path.suffix.lower(), "image/jpeg")
                        if is_still_image
                        else "image/jpeg"
                    ),
                )
                for p in frames
            ]
            contents.append(prompt)

            last_err: Optional[Exception] = None
            is_transient_error = False
            for model in self.MODELS:
                try:
                    response = client.models.generate_content(
                        model=model,
                        contents=contents,
                        config={"response_mime_type": "application/json"},
                    )
                    raw = (response.text or "").strip()
                    fence = chr(96) * 3
                    if raw.startswith(fence + "json"):
                        raw = raw[len(fence) + 4:].split(fence, 1)[0].strip()
                    elif raw.startswith(fence):
                        raw = raw[len(fence):].split(fence, 1)[0].strip()
                    data = json.loads(raw)
                    confidence = int(data.get("confidence", 0))
                    coverage = int(data.get("coverage", 0))
                    violations = data.get("violations") or []
                    # Strictly require meeting thresholds and absence of violations
                    accepted = (
                        bool(data.get("accepted", False))
                        and confidence >= self.min_confidence
                        and coverage >= self.min_coverage
                        and not violations
                    )
                    return {
                        "accepted": accepted,
                        "confidence": confidence,
                        "coverage": coverage,
                        "reason": str(data.get("reason", "")),
                        "violations": violations,
                        "frame_count": len(frames),
                        "mode": "frame_qa",
                        "model": model,
                    }
                except Exception as exc:
                    last_err = exc
                    err_str = str(exc).lower()
                    if any(k in err_str for k in ("503", "unavailable", "timeout", "timed out", "429", "resource_exhausted", "quota")):
                        is_transient_error = True
                    print(f"[FrameQA] Gemini model {model} failed: {type(exc).__name__}: {exc}")
                    time.sleep(1.0)
                    continue
        finally:
            # A still image is an input asset and must never be removed by QA cleanup.
            if not is_still_image:
                for p in frames:
                    try:
                        p.unlink(missing_ok=True)
                    except Exception:
                        pass
                if frames:
                    try:
                        shutil.rmtree(frames[0].parent, ignore_errors=True)
                    except Exception:
                        pass

        if is_transient_error:
            return {
                "accepted": not self.strict,
                "confidence": None,
                "coverage": None,
                "reason": f"Gemini vision service transiently unavailable ({type(last_err).__name__ if last_err else '503/timeout'}).",
                "mode": "frame_qa_transient_error",
            }

        return {
            "accepted": not self.strict,
            "confidence": None,
            "coverage": None,
            "reason": f"Frame QA failed: {type(last_err).__name__ if last_err else 'unknown'}",
            "mode": "frame_qa_error",
        }

    @staticmethod
    def _probe_duration(asset_path: Path) -> float:
        """Read media duration from ffmpeg metadata without a separate ffprobe dependency."""
        ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
        try:
            proc = subprocess.run(
                [ffmpeg, "-hide_banner", "-i", str(asset_path)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                text=True,
                timeout=15,
            )
            text_out = proc.stderr or ""
            match = re.search(r"Duration: (\d+):(\d+):(\d+)(?:\.(\d+))?", text_out)
            if not match:
                return 0.0
            hours, minutes, seconds = (int(match.group(i)) for i in range(1, 4))
            fraction = match.group(4) or "0"
            return hours * 3600 + minutes * 60 + seconds + float("0." + fraction)
        except Exception:
            return 0.0

    @classmethod
    def _extract_frames(cls, asset_path: Path, count: int = 4) -> List[Path]:
        """Sample frames across the whole clip, not just the opening seconds."""
        ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
        temp_dir = Path(tempfile.mkdtemp(prefix="autotube_frameqa_"))
        duration = cls._probe_duration(asset_path)
        if duration <= 0:
            positions = [0.5 + i * 0.8 for i in range(count)]
        else:
            positions = [
                max(0.0, min(duration - 0.15, duration * fraction))
                for fraction in (0.10, 0.35, 0.65, 0.90)
            ][:count]

        outputs: List[Path] = []
        for index, position in enumerate(positions):
            output = temp_dir / f"frame_{index:02d}.jpg"
            cmd = [
                ffmpeg, "-hide_banner", "-loglevel", "error",
                "-ss", f"{position:.3f}", "-i", str(asset_path),
                "-frames:v", "1", "-vf", "scale=512:-1:force_original_aspect_ratio=decrease",
                "-q:v", "4", "-y", str(output)
            ]
            try:
                subprocess.run(
                    cmd,
                    check=True,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.PIPE,
                    timeout=15,
                )
            except Exception:
                continue
            if output.exists() and output.stat().st_size > 1000:
                outputs.append(output)

        return outputs
