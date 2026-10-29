"""Guest rate limiter and 2-videos/day quota tracker for public portal."""

import datetime
import hashlib
import json
import threading
from pathlib import Path
from typing import Any, Dict, Optional
from fastapi import Request

from autotube.config import PROJECT_ROOT

USAGE_FILE = PROJECT_ROOT / "output" / "guest_usage.json"
MAX_DAILY_FREE_VIDEOS = 2
_LOCK = threading.Lock()


def get_client_fingerprint(request: Request) -> str:
    """Extract a privacy-safe unique client fingerprint from IP and headers."""
    # Check for forwarded headers if behind Cloudflare Tunnel or reverse proxy
    client_ip = (
        request.headers.get("CF-Connecting-IP")
        or request.headers.get("X-Forwarded-For")
        or (request.client.host if request.client else "127.0.0.1")
    )
    # Split multiple IPs if present
    if "," in client_ip:
        client_ip = client_ip.split(",")[0].strip()

    user_agent = request.headers.get("User-Agent", "unknown-ua")
    client_cookie = request.cookies.get("autotube_guest_id", "")

    # Combine into a deterministic SHA256 identifier
    raw_str = f"{client_ip}::{client_cookie}::{user_agent[:40]}"
    return hashlib.sha256(raw_str.encode("utf-8")).hexdigest()[:16]


def _get_today_str() -> str:
    """Current date string (YYYY-MM-DD)."""
    return datetime.datetime.now().strftime("%Y-%m-%d")


def _seconds_until_midnight() -> int:
    """Calculate remaining seconds until local midnight."""
    now = datetime.datetime.now()
    tomorrow = (now + datetime.timedelta(days=1)).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    return max(0, int((tomorrow - now).total_seconds()))


def _format_time_remaining(seconds: int) -> str:
    """Format seconds into HH:MM:SS."""
    h = seconds // 3600
    m = (seconds % 3600) // 60
    s = seconds % 60
    return f"{h}h {m}m {s}s"


def _load_usage() -> Dict[str, Any]:
    if not USAGE_FILE.exists():
        return {}
    try:
        with open(USAGE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _save_usage(data: Dict[str, Any]):
    USAGE_FILE.parent.mkdir(parents=True, exist_ok=True)
    try:
        with open(USAGE_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
    except Exception as e:
        print(f"[GuestLimiter] Warning: Failed to save usage: {e}")


def get_guest_quota(client_id: str) -> Dict[str, Any]:
    """Retrieve the current daily quota status for this guest."""
    today = _get_today_str()
    secs_left = _seconds_until_midnight()
    time_str = _format_time_remaining(secs_left)

    with _LOCK:
        data = _load_usage()
        today_data = data.get(today, {})
        client_data = today_data.get(client_id, {"count": 0, "videos": []})
        used = client_data.get("count", 0)

        remaining = max(0, MAX_DAILY_FREE_VIDEOS - used)
        can_generate = used < MAX_DAILY_FREE_VIDEOS

        return {
            "client_id": client_id,
            "date": today,
            "max_daily_limit": MAX_DAILY_FREE_VIDEOS,
            "used_today": used,
            "remaining_today": remaining,
            "can_generate": can_generate,
            "seconds_until_reset": secs_left,
            "resets_in": time_str,
            "upgrade_message": (
                "You have used your 2 free AI videos for today! "
                "Upgrade to AutoTube Pro for unlimited videos, or wait until tomorrow."
            ),
        }


def record_guest_generation(client_id: str, video_filename: str):
    """Record a successfully rendered video against the guest's daily quota."""
    today = _get_today_str()
    with _LOCK:
        data = _load_usage()
        if today not in data:
            data[today] = {}
        if client_id not in data[today]:
            data[today][client_id] = {"count": 0, "videos": []}

        data[today][client_id]["count"] += 1
        data[today][client_id]["videos"].append(
            {
                "filename": video_filename,
                "timestamp": datetime.datetime.now().isoformat(),
            }
        )

        # Cleanup old days (> 30 days) to keep file small
        keys_to_delete = []
        for d_str in data.keys():
            try:
                d_date = datetime.datetime.strptime(d_str, "%Y-%m-%d").date()
                if (datetime.date.today() - d_date).days > 30:
                    keys_to_delete.append(d_str)
            except Exception:
                pass
        for k in keys_to_delete:
            del data[k]

        _save_usage(data)
