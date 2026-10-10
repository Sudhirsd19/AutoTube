"""Persistent, retryable scheduler for AutoTube's configured publishing slots."""

from __future__ import annotations

import datetime
import json
import threading
import time
from pathlib import Path
from typing import Any, Dict, Optional

from autotube.config import PROJECT_ROOT
from autotube.utils.console import print_info, print_warning, print_success, print_error

SLOTS_CONFIG_FILE = PROJECT_ROOT / "config" / "slots_config.json"
EXECUTION_TRACKER_FILE = PROJECT_ROOT / "config" / "slot_execution_tracker.json"
MAX_ATTEMPTS_PER_SLOT = 3
RETRY_DELAY_SECONDS = 10 * 60
STALE_RUNNING_SECONDS = 3 * 60 * 60
TRACKER_RETENTION_DAYS = 7
_TRACKER_LOCK = threading.RLock()


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
    if name in ("ist", "in", "india", "hi", "asia/kolkata"):
        try:
            from zoneinfo import ZoneInfo
            return ZoneInfo("Asia/Kolkata")
        except Exception:
            return datetime.timezone(datetime.timedelta(hours=5, minutes=30))
    return datetime.timezone.utc


def _read_tracker_unlocked() -> Dict[str, Any]:
    try:
        if not EXECUTION_TRACKER_FILE.exists():
            return {"version": 1, "jobs": {}}
        with EXECUTION_TRACKER_FILE.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
        if isinstance(payload, dict) and isinstance(payload.get("jobs"), dict):
            return {"version": 1, "jobs": payload["jobs"]}
        # Migrate an absent/older/invalid schema without treating it as completed work.
        return {"version": 1, "jobs": {}}
    except Exception as exc:
        print_warning(f"[AutopilotDaemon] Could not read execution tracker: {exc}")
        return {"version": 1, "jobs": {}}


def _write_tracker_unlocked(data: Dict[str, Any]) -> None:
    EXECUTION_TRACKER_FILE.parent.mkdir(parents=True, exist_ok=True)
    temp_path = EXECUTION_TRACKER_FILE.with_suffix(".json.tmp")
    with temp_path.open("w", encoding="utf-8") as handle:
        json.dump(data, handle, indent=2, ensure_ascii=False)
        handle.flush()
    temp_path.replace(EXECUTION_TRACKER_FILE)


class AutopilotDaemon:
    """Runs due slots once at a time and retries failed/missed slots safely."""

    def __init__(self):
        self._running = False
        self._thread: Optional[threading.Thread] = None

    def start(self):
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(
            target=self._loop,
            name="AutoTubeAutopilotDaemon",
            daemon=True,
        )
        self._thread.start()
        print_info("⏰ Persistent Autopilot Daemon watcher initialized.")

    def stop(self):
        self._running = False

    def _load_config(self) -> dict:
        if not SLOTS_CONFIG_FILE.exists():
            return {}
        try:
            with SLOTS_CONFIG_FILE.open("r", encoding="utf-8") as handle:
                return json.load(handle)
        except Exception as exc:
            print_warning(f"[AutopilotDaemon] Error loading slots config: {exc}")
            return {}

    def _loop(self):
        while self._running:
            try:
                self._check_slots()
            except Exception as exc:
                print_error(f"[AutopilotDaemon] Unexpected loop error: {exc}")
            time.sleep(30)

    @staticmethod
    def _slot_is_due(slot: dict, now_local: datetime.datetime) -> bool:
        """A slot remains due after its publish time until it succeeds or exhausts retries."""
        try:
            hour = int(slot.get("hour", 8))
            minute = int(slot.get("minute", 0))
            if not (0 <= hour <= 23 and 0 <= minute <= 59):
                return False
            scheduled = now_local.replace(
                hour=hour, minute=minute, second=0, microsecond=0
            )
            return now_local >= scheduled
        except (TypeError, ValueError):
            return False

    @staticmethod
    def _parse_datetime(value: Any) -> Optional[datetime.datetime]:
        if not value:
            return None
        try:
            parsed = datetime.datetime.fromisoformat(str(value))
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=datetime.timezone.utc)
            return parsed.astimezone(datetime.timezone.utc)
        except (TypeError, ValueError):
            return None

    @classmethod
    def _retry_is_ready(cls, record: dict, now_utc: datetime.datetime) -> bool:
        retry_after = cls._parse_datetime(record.get("retry_after"))
        return retry_after is None or now_utc.astimezone(datetime.timezone.utc) >= retry_after

    @staticmethod
    def _job_key(local_date: str, slot_id: str) -> str:
        return f"{local_date}::{slot_id}"

    def _update_job(self, job_key: str, record: dict) -> None:
        with _TRACKER_LOCK:
            tracker = _read_tracker_unlocked()
            tracker["jobs"][job_key] = record
            _write_tracker_unlocked(tracker)

    def _complete_slot(self, slot_id: str, job_key: str, attempt: int) -> None:
        success = False
        try:
            from autotube.web.app import run_autopilot_task
            success = run_autopilot_task(slot_id) is True
        except Exception as exc:
            print_error(f"[AutopilotDaemon] Slot {slot_id} crashed: {exc}")

        now = datetime.datetime.now(datetime.timezone.utc)
        with _TRACKER_LOCK:
            tracker = _read_tracker_unlocked()
            record = tracker["jobs"].get(job_key, {})
            record.update({
                "slot_id": slot_id,
                "attempts": attempt,
                "finished_at": now.isoformat(),
                "status": "succeeded" if success else "failed",
                "last_error": None if success else "generation/upload did not complete successfully",
            })
            if success or attempt >= MAX_ATTEMPTS_PER_SLOT:
                record["retry_after"] = None
            else:
                record["retry_after"] = (
                    now + datetime.timedelta(seconds=RETRY_DELAY_SECONDS)
                ).isoformat()
            tracker["jobs"][job_key] = record
            _write_tracker_unlocked(tracker)

        if success:
            print_success(f"✅ Autopilot slot {slot_id} completed successfully.")
        else:
            print_warning(
                f"⚠️ Autopilot slot {slot_id} failed on attempt {attempt}/{MAX_ATTEMPTS_PER_SLOT}."
            )

    def _check_slots(self):
        config = self._load_config()
        if not config.get("autopilot_daemon", False):
            return

        slots = config.get("slots", [])
        if not isinstance(slots, list) or not slots:
            return

        try:
            from autotube.web.app import GENERATION_STATUS, log_event
            if GENERATION_STATUS.get("is_running", False):
                return
        except ImportError:
            return

        now_utc = datetime.datetime.now(datetime.timezone.utc)
        retention_date = (now_utc.date() - datetime.timedelta(days=TRACKER_RETENTION_DAYS)).isoformat()
        chosen = None

        with _TRACKER_LOCK:
            tracker = _read_tracker_unlocked()
            jobs = tracker["jobs"]

            # Drop old per-day records to keep the tracker bounded.
            for key in list(jobs):
                try:
                    job_date = key.split("::", 1)[0]
                    if job_date < retention_date:
                        del jobs[key]
                except Exception:
                    del jobs[key]

            # Never start another scheduled render while a tracked job is active.
            # A stale "running" state indicates a process/server crash; release it for retry.
            for key, record in list(jobs.items()):
                if record.get("status") != "running":
                    continue
                attempted = self._parse_datetime(record.get("started_at"))
                age = (now_utc - attempted).total_seconds() if attempted else STALE_RUNNING_SECONDS + 1
                if age <= STALE_RUNNING_SECONDS:
                    _write_tracker_unlocked(tracker)
                    return
                record["status"] = "failed"
                record["last_error"] = "stale running state recovered after process/server interruption"
                record["retry_after"] = (
                    now_utc + datetime.timedelta(seconds=RETRY_DELAY_SECONDS)
                ).isoformat()
                jobs[key] = record

            for slot in slots:
                if not isinstance(slot, dict):
                    continue
                slot_id = str(slot.get("id") or "").strip()
                if not slot_id:
                    continue
                if str(slot.get("status", "ready")).strip().lower() not in {"ready", "active", "enabled"}:
                    continue

                timezone = _get_tz(str(slot.get("tz", "IST")))
                local_now = datetime.datetime.now(timezone)
                if not self._slot_is_due(slot, local_now):
                    continue

                key = self._job_key(local_now.date().isoformat(), slot_id)
                record = jobs.get(key, {})
                status = record.get("status")
                if status == "succeeded":
                    continue
                if status == "running":
                    _write_tracker_unlocked(tracker)
                    return

                attempts = int(record.get("attempts", 0) or 0)
                if attempts >= MAX_ATTEMPTS_PER_SLOT:
                    continue
                if not self._retry_is_ready(record, now_utc):
                    continue

                attempt = attempts + 1
                jobs[key] = {
                    **record,
                    "slot_id": slot_id,
                    "status": "running",
                    "attempts": attempt,
                    "started_at": now_utc.isoformat(),
                    "retry_after": None,
                }
                _write_tracker_unlocked(tracker)
                chosen = (slot_id, key, attempt, local_now, slot)
                break

        if not chosen:
            return

        slot_id, job_key, attempt, local_now, slot = chosen
        message = (
            f"⏰ [AutopilotDaemon] Slot '{slot_id}' is due "
            f"({int(slot.get('hour', 8)):02d}:{int(slot.get('minute', 0)):02d} "
            f"{slot.get('tz', 'IST')}); starting attempt {attempt}/{MAX_ATTEMPTS_PER_SLOT}."
        )
        print_success(message)
        try:
            log_event(message)
        except Exception:
            pass

        # Reserving the status before starting the thread prevents dashboard/manual
        # requests from racing this scheduled job.
        GENERATION_STATUS["is_running"] = True
        GENERATION_STATUS["current_task"] = f"Autopilot Slot ({slot_id})"
        threading.Thread(
            target=self._complete_slot,
            args=(slot_id, job_key, attempt),
            name=f"AutopilotSlot_{slot_id}",
            daemon=True,
        ).start()
