"""Autonomous Background Daemon for scheduled Daily AutoPilot video generation."""

import datetime
import json
import threading
import time
from pathlib import Path
from typing import Dict, Optional, Set
from autotube.utils.console import print_info, print_warning, print_success, print_error

SLOTS_CONFIG_FILE = Path("config/slots_config.json")
EXECUTION_TRACKER_FILE = Path("config/local_publish_tracker.json")


def _get_tz(tz_name: str) -> datetime.tzinfo:
    name = (tz_name or "").strip().lower()
    if name in ("us", "usa", "edt", "est", "en", "america/new_york"):
        try:
            from zoneinfo import ZoneInfo
            return ZoneInfo("America/New_York")
        except Exception:
            month = datetime.datetime.now(datetime.timezone.utc).month
            offset = -4 if 3 <= month <= 11 else -5
            return datetime.timezone(datetime.timedelta(hours=offset))
    elif name in ("ist", "in", "india", "hi", "asia/kolkata"):
        try:
            from zoneinfo import ZoneInfo
            return ZoneInfo("Asia/Kolkata")
        except Exception:
            return datetime.timezone(datetime.timedelta(hours=5, minutes=30))
    return datetime.timezone.utc


class AutopilotDaemon:
    """Monitors scheduled time slots in the background and triggers video generation."""

    def __init__(self):
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._executed_today: Set[str] = set()
        self._last_date_str = ""

    def start(self):
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._loop, name="AutoTubeAutopilotDaemon", daemon=True)
        self._thread.start()
        print_info("⏰ Autopilot Daemon background watcher initialized.")

    def stop(self):
        self._running = False

    def _load_config(self) -> dict:
        if not SLOTS_CONFIG_FILE.exists():
            return {}
        try:
            with open(SLOTS_CONFIG_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            print_warning(f"[AutopilotDaemon] Error loading slots config: {e}")
            return {}

    def _loop(self):
        while self._running:
            try:
                self._check_slots()
            except Exception as e:
                print_error(f"[AutopilotDaemon] Unexpected loop error: {e}")
            # Sleep 30 seconds between checks
            time.sleep(30)

    def _check_slots(self):
        config = self._load_config()
        if not config.get("autopilot_daemon", False):
            return

        slots = config.get("slots", [])
        if not slots:
            return

        today_utc = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d")
        if today_utc != self._last_date_str:
            self._executed_today.clear()
            self._last_date_str = today_utc

        # Check if web generation is already running
        try:
            from autotube.web.app import GENERATION_STATUS, run_autopilot_task, log_event
            if GENERATION_STATUS.get("is_running", False):
                return
        except ImportError:
            return

        for slot in slots:
            slot_id = slot.get("id")
            if not slot_id:
                continue

            tz = _get_tz(slot.get("tz", "IST"))
            now_tz = datetime.datetime.now(tz)
            date_key = f"{now_tz.strftime('%Y-%m-%d')}_{slot_id}"

            if date_key in self._executed_today:
                continue

            target_h = int(slot.get("hour", 8))
            target_m = int(slot.get("minute", 0))

            # Match within 2-minute window
            if now_tz.hour == target_h and 0 <= (now_tz.minute - target_m) <= 2:
                self._executed_today.add(date_key)
                log_msg = f"⏰ [Autopilot Daemon] Time slot '{slot_id}' triggered ({target_h:02d}:{target_m:02d} {slot.get('tz')})! Starting generation..."
                print_success(log_msg)
                try:
                    log_event(log_msg)
                except Exception:
                    pass

                # Launch slot generation in background
                threading.Thread(
                    target=run_autopilot_task,
                    args=(slot_id,),
                    name=f"AutopilotBatch_{slot_id}",
                    daemon=True,
                ).start()
                break  # Process one slot at a time
