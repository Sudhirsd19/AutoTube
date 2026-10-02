"""AutoTube Command Center - Modern FastAPI Web Dashboard.

Provides:
1. YouTube Schedule & Live Video Manager (View, Reschedule, 1-Click Publish Now)
2. Alien Series 16-Chapter Curriculum Tracker & 1-Click Generator
3. In-Browser HTML5 Video Player & Archive Preview
4. Live Generation Terminal & Background Job Runner
5. Quota & System Health Monitor
"""

import asyncio
import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional
import os
import json

from fastapi import FastAPI, BackgroundTasks, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from googleapiclient.discovery import build

from autotube.config import get_config, PROJECT_ROOT
from autotube.uploader.auth import YouTubeAuth
from autotube.scripting.alien_tracker import AlienSeriesTracker, ALIEN_SERIES_CHAPTERS
from autotube.utils.file_utils import sanitize_filename

app = FastAPI(title="AutoTube Command Center", version="2.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

TEMPLATES_DIR = Path(__file__).parent / "templates"
LOGS_FILE = PROJECT_ROOT / "output" / "cron.log"
GENERATION_STATUS = {
    "is_running": False,
    "current_task": "Idle",
    "progress": 0,
    "last_log": "",
    "logs": [],
}


def log_event(msg: str):
    timestamp = datetime.datetime.now().strftime("%H:%M:%S")
    formatted = f"[{timestamp}] {msg}"
    GENERATION_STATUS["last_log"] = formatted
    GENERATION_STATUS["logs"].append(formatted)
    if len(GENERATION_STATUS["logs"]) > 200:
        GENERATION_STATUS["logs"].pop(0)


# -------------------------------------------------------------
# PYDANTIC SCHEMAS
# -------------------------------------------------------------
class RescheduleRequest(BaseModel):
    video_id: str
    publish_at: str  # ISO 8601 UTC or local format


class PublishNowRequest(BaseModel):
    video_id: str


class AlienGenerateRequest(BaseModel):
    part: Optional[int] = None
    lang: str = "hi"
    upload: bool = True
    privacy: str = "public"


class CustomShortRequest(BaseModel):
    topic: str
    niche: str = "science"
    lang: str = "en"
    upload: bool = True
    privacy: str = "public"


# -------------------------------------------------------------
# HELPER: GET YOUTUBE SERVICE
# -------------------------------------------------------------
def get_youtube_service():
    creds = YouTubeAuth().get_credentials()
    if not creds:
        raise HTTPException(status_code=401, detail="YouTube credentials not found or expired.")
    return build("youtube", "v3", credentials=creds)


# -------------------------------------------------------------
# API ROUTES: SYSTEM STATUS & HEALTH
# -------------------------------------------------------------
@app.get("/api/status")
async def get_status():
    tracker = AlienSeriesTracker()
    now_utc = datetime.datetime.now(datetime.timezone.utc)
    now_ist = now_utc.astimezone(datetime.timezone(datetime.timedelta(hours=5, minutes=30)))
    now_edt = now_utc.astimezone(datetime.timezone(datetime.timedelta(hours=-4)))

    # Count today's uploads from published_history.json
    history_file = PROJECT_ROOT / "config" / "published_history.json"
    today_uploads_count = 0
    if history_file.exists():
        try:
            with open(history_file, "r", encoding="utf-8") as f:
                hist = json.load(f)
                today_str = now_utc.strftime("%Y-%m-%d")
                for item in hist:
                    if isinstance(item, dict) and item.get("date", "").startswith(today_str):
                        today_uploads_count += 1
        except Exception:
            pass

    return {
        "status": "online",
        "time_ist": now_ist.strftime("%d-%b-%Y %I:%M %p IST"),
        "time_edt": now_edt.strftime("%d-%b-%Y %I:%M %p EDT"),
        "current_alien_part": tracker.current_part,
        "total_chapters": tracker.total_chapters,
        "today_uploads_count": today_uploads_count,
        "daily_upload_limit": 10,
        "is_generating": GENERATION_STATUS["is_running"],
        "current_task": GENERATION_STATUS["current_task"],
    }


# -------------------------------------------------------------
# API ROUTES: YOUTUBE VIDEO & SCHEDULE MANAGER
# -------------------------------------------------------------
@app.get("/api/videos")
async def list_videos():
    try:
        yt = get_youtube_service()

        # 1. Get uploads playlist ID of the authenticated channel
        channels_res = yt.channels().list(part="contentDetails,snippet", mine=True).execute()
        if not channels_res.get("items"):
            return {"videos": [], "channel": None}

        ch_item = channels_res["items"][0]
        channel_info = {
            "title": ch_item["snippet"]["title"],
            "custom_url": ch_item["snippet"].get("customUrl", ""),
            "thumbnail": ch_item["snippet"]["thumbnails"].get("default", {}).get("url", ""),
        }
        uploads_playlist_id = ch_item["contentDetails"]["relatedPlaylists"]["uploads"]

        # 2. Fetch recent videos from uploads playlist
        playlist_res = yt.playlistItems().list(
            part="snippet,contentDetails",
            playlistId=uploads_playlist_id,
            maxResults=30,
        ).execute()

        video_ids = [item["contentDetails"]["videoId"] for item in playlist_res.get("items", [])]
        if not video_ids:
            return {"videos": [], "channel": channel_info}

        # 3. Fetch detailed video status, duration, publishAt, and metrics
        videos_res = yt.videos().list(
            part="snippet,status,contentDetails,statistics",
            id=",".join(video_ids),
        ).execute()

        video_list = []
        for v in videos_res.get("items", []):
            vid_id = v["id"]
            snippet = v["snippet"]
            status = v["status"]
            stats = v.get("statistics", {})
            content = v.get("contentDetails", {})

            privacy = status.get("privacyStatus", "unknown")
            publish_at = status.get("publishAt")  # Present if scheduled!
            is_scheduled = (privacy == "private" and publish_at is not None)

            # Format publishAt display
            publish_display_ist = None
            publish_display_edt = None
            if publish_at:
                try:
                    dt = datetime.datetime.fromisoformat(publish_at.replace("Z", "+00:00"))
                    ist_dt = dt.astimezone(datetime.timezone(datetime.timedelta(hours=5, minutes=30)))
                    edt_dt = dt.astimezone(datetime.timezone(datetime.timedelta(hours=-4)))
                    publish_display_ist = ist_dt.strftime("%d %b, %I:%M %p IST")
                    publish_display_edt = edt_dt.strftime("%d %b, %I:%M %p EDT")
                except Exception:
                    publish_display_ist = publish_at

            thumbs = snippet.get("thumbnails", {})
            best_thumb = (
                thumbs.get("maxres", {}).get("url")
                or thumbs.get("standard", {}).get("url")
                or thumbs.get("high", {}).get("url")
                or thumbs.get("medium", {}).get("url")
                or thumbs.get("default", {}).get("url", "")
            )

            video_list.append({
                "id": vid_id,
                "title": snippet.get("title", ""),
                "description": snippet.get("description", "")[:120] + "...",
                "published_at": snippet.get("publishedAt", ""),
                "thumbnail": best_thumb,
                "privacy": privacy,
                "is_scheduled": is_scheduled,
                "publish_at_iso": publish_at,
                "publish_display_ist": publish_display_ist,
                "publish_display_edt": publish_display_edt,
                "views": int(stats.get("viewCount", 0)),
                "likes": int(stats.get("likeCount", 0)),
                "comments": int(stats.get("commentCount", 0)),
                "duration": content.get("duration", ""),
                "url": f"https://youtu.be/{vid_id}",
            })

        return {"videos": video_list, "channel": channel_info}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/videos/reschedule")
async def reschedule_video(req: RescheduleRequest):
    """Update scheduled release date/time using YouTube Data API."""
    try:
        yt = get_youtube_service()

        # Parse requested publish date & time
        req_time = req.publish_at.strip()
        # Accept YYYY-MM-DDTHH:MM or ISO format
        if not req_time.endswith("Z") and not ("+" in req_time):
            # Assume local IST or convert to UTC
            dt = datetime.datetime.fromisoformat(req_time)
            # Default to UTC if naive
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=datetime.timezone.utc)
            req_time = dt.astimezone(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

        yt.videos().update(
            part="status",
            body={
                "id": req.video_id,
                "status": {
                    "privacyStatus": "private",
                    "publishAt": req_time,
                    "selfDeclaredMadeForKids": False,
                },
            },
        ).execute()

        log_event(f"Successfully rescheduled video {req.video_id} to {req_time}")
        return {"success": True, "message": f"Video {req.video_id} rescheduled to {req_time}"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/videos/make_public")
async def make_video_public(req: PublishNowRequest):
    """Instantly make any private or scheduled video PUBLIC on YouTube."""
    try:
        yt = get_youtube_service()
        yt.videos().update(
            part="status",
            body={
                "id": req.video_id,
                "status": {
                    "privacyStatus": "public",
                    "selfDeclaredMadeForKids": False,
                },
            },
        ).execute()

        log_event(f"Video {req.video_id} is now LIVE & PUBLIC!")
        return {"success": True, "message": f"Video {req.video_id} is now PUBLIC!"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# -------------------------------------------------------------
# API ROUTES: ALIEN INTERVIEW CHAPTERS & ROADMAP
# -------------------------------------------------------------
@app.get("/api/alien/chapters")
async def get_alien_chapters():
    tracker = AlienSeriesTracker()
    tracker_status = tracker.data.get("parts_status", {})
    chapters = []

    for ch in ALIEN_SERIES_CHAPTERS:
        p_num = ch["part"]
        p_str = str(p_num)
        st = tracker_status.get(p_str, {})

        en_done = st.get("en_done", False)
        hi_done = st.get("hi_done", False)
        en_vid = st.get("en_video_id")
        hi_vid = st.get("hi_video_id")

        chapters.append({
            "part": p_num,
            "title_en": ch["title_en"],
            "title_hi": ch["title_hi"],
            "book_chapter": ch["book_chapter"],
            "core_theme": ch["core_theme"],
            "evidence_proof": ch["evidence_proof"],
            "key_quote": ch["key_quote"],
            "en_done": en_done,
            "hi_done": hi_done,
            "en_video_url": f"https://youtu.be/{en_vid}" if en_vid and en_vid != "rendered_local" else None,
            "hi_video_url": f"https://youtu.be/{hi_vid}" if hi_vid and hi_vid != "rendered_local" else None,
            "is_current": (p_num == tracker.current_part),
        })

    return {
        "current_part": tracker.current_part,
        "total_chapters": tracker.total_chapters,
        "chapters": chapters,
    }


# -------------------------------------------------------------
# API ROUTES: BACKGROUND VIDEO GENERATOR
# -------------------------------------------------------------
def run_alien_task(part: Optional[int], lang: str, upload: bool, privacy: str):
    import subprocess
    import sys

    GENERATION_STATUS["is_running"] = True
    GENERATION_STATUS["current_task"] = f"Alien Interview Part {part or 'Next'} ({lang.upper()})"
    log_event(f"Starting Alien Interview generation (Part {part or 'Next'}, {lang.upper()})...")

    python_bin = sys.executable
    cmd = [python_bin, "run.py", "alien", "--lang", lang, "--privacy", privacy]
    if part is not None:
        cmd.extend(["--part", str(part)])
    if upload:
        cmd.append("--upload")

    try:
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            cwd=str(PROJECT_ROOT),
        )
        for line in proc.stdout:
            clean = line.strip()
            if clean:
                log_event(clean)
        proc.wait()
        log_event(f"Alien Interview generation completed with return code {proc.returncode}!")
    except Exception as e:
        log_event(f"Generation error: {e}")
    finally:
        GENERATION_STATUS["is_running"] = False
        GENERATION_STATUS["current_task"] = "Idle"


@app.post("/api/generate/alien")
async def trigger_alien_generation(req: AlienGenerateRequest, bg_tasks: BackgroundTasks):
    if GENERATION_STATUS["is_running"]:
        raise HTTPException(status_code=400, detail="Another video generation is already in progress!")

    bg_tasks.add_task(run_alien_task, req.part, req.lang, req.upload, req.privacy)
    return {"success": True, "message": f"Alien Interview Part {req.part or 'Next'} ({req.lang}) started!"}


def run_autopilot_task():
    import subprocess
    import sys

    GENERATION_STATUS["is_running"] = True
    GENERATION_STATUS["current_task"] = "Autopilot Daily Batch (7 Slots)"
    log_event("Starting full Autopilot 7-Slot batch generation...")

    python_bin = sys.executable
    cmd = [python_bin, "run.py", "autopilot", "--count", "7", "--niche", "mixed", "--lang", "mixed", "--upload", "--schedule"]

    try:
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            cwd=str(PROJECT_ROOT),
        )
        for line in proc.stdout:
            clean = line.strip()
            if clean:
                log_event(clean)
        proc.wait()
        log_event(f"Autopilot batch completed with return code {proc.returncode}!")
    except Exception as e:
        log_event(f"Autopilot error: {e}")
    finally:
        GENERATION_STATUS["is_running"] = False
        GENERATION_STATUS["current_task"] = "Idle"


@app.post("/api/autopilot/run")
async def trigger_autopilot(bg_tasks: BackgroundTasks):
    if GENERATION_STATUS["is_running"]:
        raise HTTPException(status_code=400, detail="Another video generation is already in progress!")

    bg_tasks.add_task(run_autopilot_task)
    return {"success": True, "message": "Autopilot daily batch started in background!"}


# -------------------------------------------------------------
# API ROUTES: MEDIA PREVIEW & HTML5 VIDEO STREAMING
# -------------------------------------------------------------
@app.get("/api/media/list")
async def list_media_files():
    shorts_dir = PROJECT_ROOT / "output" / "shorts"
    files = []
    if shorts_dir.exists():
        for p in sorted(shorts_dir.glob("*.mp4"), key=lambda x: x.stat().st_mtime, reverse=True):
            stat = p.stat()
            size_mb = round(stat.st_size / (1024 * 1024), 2)
            mtime = datetime.datetime.fromtimestamp(stat.st_mtime).strftime("%d-%b %H:%M")
            files.append({
                "filename": p.name,
                "size_mb": size_mb,
                "modified": mtime,
                "stream_url": f"/api/media/stream/{p.name}",
            })
    return {"files": files}


@app.get("/api/media/stream/{filename}")
async def stream_media(filename: str):
    p = PROJECT_ROOT / "output" / "shorts" / filename
    if not p.exists():
        raise HTTPException(status_code=404, detail="Video file not found")
    return FileResponse(p, media_type="video/mp4")


@app.get("/api/logs")
async def get_logs():
    return {
        "is_running": GENERATION_STATUS["is_running"],
        "current_task": GENERATION_STATUS["current_task"],
        "logs": GENERATION_STATUS["logs"][-60:],
    }


# -------------------------------------------------------------
# FRONTEND DASHBOARD
# -------------------------------------------------------------
@app.get("/", response_class=HTMLResponse)
async def serve_dashboard():
    index_file = TEMPLATES_DIR / "index.html"
    if not index_file.exists():
        return HTMLResponse("<h1>AutoTube Dashboard Template Not Found</h1>", status_code=500)
    with open(index_file, "r", encoding="utf-8") as f:
        return HTMLResponse(f.read())
