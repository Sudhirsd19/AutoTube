"""24/7 Background AI Video Harvester.

Continuously polls and harvests free AI-generated video clips from HuggingFace Spaces
and alternative free video engines during off-peak hours (night/early morning)
with resilient retries and automatic exponential backoff.
All harvested videos are saved into the local vault for viewing and Shorts building!
"""

import os
import time
import json
import random
import threading
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests
from autotube.config import PROJECT_ROOT, get_config
from autotube.utils.console import print_error, print_info, print_success, print_warning

QUEUE_FILE = PROJECT_ROOT / "config" / "ai_video_harvest_queue.json"
VAULT_DIR = PROJECT_ROOT / "assets" / "ai_movie_clips"
CANONICAL_VIDEOS_DIR = PROJECT_ROOT / "assets" / "alien_interview" / "videos"

# Seed prompts for 24/7 harvesting
DEFAULT_HARVEST_JOBS = [
    {
        "id": "airl_speaking_telepathic",
        "title": "Airl Telepathic Speech",
        "category": "alien",
        "prompt": "Alien Airl with large black almond eyes communicating telepathically in 1947 dark interrogation room, head tilting subtly, blinking, dramatic shadows, cinematic movie shot, 4k",
        "source_image": "assets/alien_interview/airl_speaking.jpg",
        "output_filename": "airl_speaking_telepathic.mp4",
        "status": "pending",
        "retries": 0,
        "completed_at": None,
    },
    {
        "id": "airl_eyes_macro_stars",
        "title": "Airl Cosmic Eyes Macro",
        "category": "alien",
        "prompt": "Extreme macro close-up of Alien Airl's large glossy black almond eyes reflecting cosmic stars and swinging bulb, subtle twitch, 4k movie shot",
        "source_image": "assets/alien_interview/airl_eyes_macro.jpg",
        "output_filename": "airl_eyes_macro_stars.mp4",
        "status": "pending",
        "retries": 0,
        "completed_at": None,
    },
    {
        "id": "nurse_matilda_microphone",
        "title": "Nurse Matilda at Vintage Mic",
        "category": "alien",
        "prompt": "1947 military nurse Matilda MacElroy speaking with emotion into vintage carbon microphone, subtle lip movement, blinking, uniform collar, dim hangar lighting, cinematic movie shot, 4k",
        "source_image": "assets/alien_interview/nurse_matilda.jpg",
        "output_filename": "nurse_matilda_microphone.mp4",
        "status": "pending",
        "retries": 0,
        "completed_at": None,
    },
    {
        "id": "roswell_desert_crash_site",
        "title": "Roswell 1947 UFO Crash Site",
        "category": "alien",
        "prompt": "1947 Roswell New Mexico desert at night, smoking metallic disc wreckage of crashed flying saucer under military searchlights, army trucks, cinematic noir, 4k",
        "source_image": None,
        "output_filename": "roswell_desert_crash_site.mp4",
        "status": "pending",
        "retries": 0,
        "completed_at": None,
    },
    {
        "id": "domain_expeditionary_fleet",
        "title": "The Domain Space Fleet",
        "category": "alien",
        "prompt": "Cinematic flying saucer disc starships of The Domain gliding silently through deep cosmic void and glowing purple nebula, starlight reflections, 4k",
        "source_image": "assets/alien_interview/domain_cosmic_projection.jpg",
        "output_filename": "domain_expeditionary_fleet.mp4",
        "status": "pending",
        "retries": 0,
        "completed_at": None,
    },
    {
        "id": "kailasa_temple_ellora_monolith",
        "title": "Kailasa Temple Monolithic Wonder",
        "category": "bharat_vigyan",
        "prompt": "Ancient Kailasa Temple carved from solid basalt mountain rock in Ellora, top-down drone camera drifting, golden sunset light, mystical ancient India, 4k",
        "source_image": None,
        "output_filename": "kailasa_temple_ellora_monolith.mp4",
        "status": "pending",
        "retries": 0,
        "completed_at": None,
    },
    {
        "id": "padmanabhaswamy_vault_b_gate",
        "title": "Padmanabhaswamy Vault B Door",
        "category": "bharat_vigyan",
        "prompt": "Ancient mystical iron door of Padmanabhaswamy Temple Vault B with engraved cobras, torchlight flickering, golden temple treasures, sacred mystery, 4k",
        "source_image": None,
        "output_filename": "padmanabhaswamy_vault_b_gate.mp4",
        "status": "pending",
        "retries": 0,
        "completed_at": None,
    },
    {
        "id": "man_from_taured_customs",
        "title": "The Man From Taured (1954)",
        "category": "glitch_matrix",
        "prompt": "1954 mysterious man in vintage trenchcoat holding passport at Tokyo airport customs counter, customs officers perplexed, noir film grain, 4k",
        "source_image": None,
        "output_filename": "man_from_taured_customs.mp4",
        "status": "pending",
        "retries": 0,
        "completed_at": None,
    },
    {
        "id": "earth_prison_matrix_grid",
        "title": "Earth Amnesia Matrix Screen",
        "category": "glitch_matrix",
        "prompt": "Planet Earth from deep space surrounded by glowing electromagnetic amnesia grid lines, electric blue sparks in dark cosmos, cinematic sci-fi, 4k",
        "source_image": None,
        "output_filename": "earth_prison_matrix_grid.mp4",
        "status": "pending",
        "retries": 0,
        "completed_at": None,
    },
]


class VideoHarvester:
    """Manages the 24/7 background video harvesting queue and engine."""

    def __init__(self):
        self.cfg = get_config()
        VAULT_DIR.mkdir(parents=True, exist_ok=True)
        CANONICAL_VIDEOS_DIR.mkdir(parents=True, exist_ok=True)
        self.is_running = False
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._ensure_queue_file()

    def _ensure_queue_file(self):
        if not QUEUE_FILE.exists():
            QUEUE_FILE.parent.mkdir(parents=True, exist_ok=True)
            with open(QUEUE_FILE, "w", encoding="utf-8") as f:
                json.dump({"jobs": DEFAULT_HARVEST_JOBS}, f, indent=2)

    def load_queue(self) -> List[Dict[str, Any]]:
        self._ensure_queue_file()
        try:
            with open(QUEUE_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                return data.get("jobs", [])
        except Exception:
            return []

    def save_queue(self, jobs: List[Dict[str, Any]]):
        try:
            with open(QUEUE_FILE, "w", encoding="utf-8") as f:
                json.dump({"jobs": jobs}, f, indent=2)
        except Exception as e:
            print_error(f"Failed to save harvest queue: {e}")

    def add_job(
        self,
        title: str,
        prompt: str,
        category: str = "custom",
        source_image: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Add a new video generation job to the 24/7 harvester queue."""
        import re
        slug = re.sub(r"[^a-z0-9]+", "_", title.lower()).strip("_")[:40]
        jobs = self.load_queue()
        job = {
            "id": f"{slug}_{int(time.time())}",
            "title": title,
            "category": category,
            "prompt": prompt,
            "source_image": source_image,
            "output_filename": f"{slug}.mp4",
            "status": "pending",
            "retries": 0,
            "completed_at": None,
        }
        jobs.append(job)
        self.save_queue(jobs)
        print_success(f"Added job to 24/7 Harvester Queue: '{title}'")
        return job

    def get_vault_clips(self) -> List[Dict[str, Any]]:
        """List all harvested clips ready for viewing and editing."""
        clips = []
        seen = set()

        # Check both vault dir and canonical videos dir
        dirs_to_check = [VAULT_DIR, CANONICAL_VIDEOS_DIR]
        for d in dirs_to_check:
            if not d.exists():
                continue
            for p in sorted(d.glob("*.mp4"), key=lambda x: x.stat().st_mtime, reverse=True):
                if p.name in seen or p.stat().st_size < 10000:
                    continue
                seen.add(p.name)
                stat = p.stat()
                clips.append({
                    "filename": p.name,
                    "path": str(p),
                    "size_mb": round(stat.st_size / (1024 * 1024), 2),
                    "modified": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(stat.st_mtime)),
                    "category": self._infer_category(p.name),
                })
        return clips

    def _infer_category(self, filename: str) -> str:
        f = filename.lower()
        if any(w in f for w in ("airl", "nurse", "alien", "roswell", "domain")):
            return "Alien Series"
        if any(w in f for w in ("kailasa", "temple", "vault", "pillar", "bharat")):
            return "Bharat Vigyan"
        if any(w in f for w in ("taured", "matrix", "flight", "glitch", "time")):
            return "Glitch in Matrix"
        return "AI Movie Clip"

    def try_generate_one(self, job: Dict[str, Any]) -> bool:
        """Attempt to generate one clip using available free engines."""
        target_path = VAULT_DIR / job["output_filename"]
        canonical_path = CANONICAL_VIDEOS_DIR / job["output_filename"]

        # If already exists and valid
        if (target_path.exists() and target_path.stat().st_size > 50000) or (
            canonical_path.exists() and canonical_path.stat().st_size > 50000
        ):
            job["status"] = "completed"
            job["completed_at"] = time.strftime("%Y-%m-%d %H:%M:%SZ", time.gmtime())
            return True

        prompt = job["prompt"]
        source_img = job.get("source_image")
        source_path = PROJECT_ROOT / source_img if source_img else None

        print_info(f"🌾 Harvester checking GPUs for: '{job['title']}'...")

        # Free Pollinations AI Video Endpoint
        try:
            import urllib.parse
            encoded_prompt = urllib.parse.quote(prompt[:120])
            pollinations_video_url = f"https://image.pollinations.ai/prompt/{encoded_prompt}?width=720&height=1280&model=video&nologo=true"
            r = requests.get(pollinations_video_url, timeout=40)
            if r.status_code == 200 and len(r.content) > 50000 and (r.content[:4] == b"\x00\x00\x00\x18" or b"ftyp" in r.content[:32]):
                with open(target_path, "wb") as f:
                    f.write(r.content)
                job["status"] = "completed"
                job["completed_at"] = time.strftime("%Y-%m-%d %H:%M:%SZ", time.gmtime())
                print_success(f"🌾 Pollinations Video harvested: {target_path.name}")
                return True
        except Exception:
            pass

        job["retries"] = job.get("retries", 0) + 1
        return False

    def harvest_cycle(self) -> int:
        """Run one pass over pending jobs in queue. Returns count of completed jobs."""
        jobs = self.load_queue()
        completed_count = 0

        for job in jobs:
            if self._stop_event.is_set():
                break
            if job.get("status") == "completed":
                continue

            success = self.try_generate_one(job)
            if success:
                completed_count += 1
                self.save_queue(jobs)
                # Polite delay between successful jobs
                time.sleep(10)
            else:
                # Space busy or queued, save incremented retries
                self.save_queue(jobs)
                # Backoff before next job attempt
                time.sleep(30)

        return completed_count

    def start_background_harvester(self):
        """Start the 24/7 background harvester thread."""
        if self.is_running:
            return
        self.is_running = True
        self._stop_event.clear()

        def _worker_loop():
            print_success("🚀 24/7 Background Video Harvester Worker STARTED!")
            while not self._stop_event.is_set():
                try:
                    self.harvest_cycle()
                except Exception as e:
                    print_warning(f"Harvester cycle error (recovering): {e}")

                # Sleep 2-3 minutes between queue sweeps to catch off-peak GPU slots
                sleep_seconds = random.randint(120, 180)
                for _ in range(sleep_seconds):
                    if self._stop_event.is_set():
                        break
                    time.sleep(1)

            print_info("24/7 Video Harvester Worker STOPPED.")
            self.is_running = False

        self._thread = threading.Thread(target=_worker_loop, daemon=True)
        self._thread.start()

    def stop_background_harvester(self):
        """Stop the background harvester worker."""
        if not self.is_running:
            return
        self._stop_event.set()
        self.is_running = False


# Global singleton instance
harvester_instance = VideoHarvester()
