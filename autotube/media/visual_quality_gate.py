"""Sample video frames and verify scene relevance with Gemini vision."""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
import shutil
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

import imageio_ffmpeg


class VisualQualityGate:
    """Final frame-level QA. Uses Gemini when GEMINI_API_KEY is present."""

    MODELS = ("gemini-3.8-flash", "gemini-3.5-flash", "gemini-3.1-flash-lite")

    def __init__(self, min_confidence: int = 82, min_coverage: int = 80) -> None:
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
            self._client = genai.Client(api_key=key)
        except Exception:
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

        frames = self._extract_frames(path)
        if not frames:
            return {
                "accepted": not self.strict,
                "confidence": 0,
                "coverage": 0,
                "reason": "No frames could be extracted.",
                "mode": "frame_qa",
            }

        plan = scene_plan or {}
        prompt = f"""You are final visual QA for a YouTube scene.
EXACT NARRATION: {narration}
TARGET SUBJECT: {plan.get("subject", "")}
MUST SHOW: {json.dumps(plan.get("must_show", []), ensure_ascii=False)}
MUST AVOID: {json.dumps(plan.get("avoid", []), ensure_ascii=False)}

Judge ONLY the supplied video frames. Do not trust titles or tags.
Return JSON only:
{{"confidence":0-100,"coverage":0-100,"accepted":true/false,"reason":"one sentence","violations":[]}}
Accept only when confidence >= {self.min_confidence}, coverage >= {self.min_coverage}, and there is no major visual mismatch.
"""

        try:
            from google.genai import types

            contents: List[Any] = [
                types.Part.from_bytes(data=p.read_bytes(), mime_type="image/jpeg")
                for p in frames
            ]
            contents.append(prompt)

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
                except Exception:
                    continue
        finally:
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

        return {
            "accepted": not self.strict,
            "confidence": None,
            "coverage": None,
            "reason": "Frame QA failed.",
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
            match = re.search(r"Duration: (\\d+):(\\d+):(\\d+)(?:\\.(\\d+))?", text_out)
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
