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
import shutil

from fastapi import FastAPI, BackgroundTasks, HTTPException, Request, UploadFile, File
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from googleapiclient.discovery import build

from autotube.config import get_config, PROJECT_ROOT
from autotube.uploader.auth import YouTubeAuth
from autotube.scripting.alien_tracker import AlienSeriesTracker, ALIEN_SERIES_CHAPTERS
from autotube.media.cloud_video_gen import CloudVideoGenerator, CANONICAL_VIDEOS_DIR
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


@app.on_event("startup")
async def on_startup():
    """Auto-start background services (Harvester + Scheduled Autopilot Daemon)."""
    try:
        from autotube.media.ai_video_harvester import harvester_instance
        harvester_instance.start_background_harvester()
        log_event("🚀 24/7 AI Video Harvester activated automatically on server startup!")
    except Exception as e:
        log_event(f"Failed to auto-start harvester: {e}")

    try:
        from autotube.scheduler.daemon import AutopilotDaemon
        global autopilot_daemon_instance
        autopilot_daemon_instance = AutopilotDaemon()
        autopilot_daemon_instance.start()
        log_event("⏰ Scheduled Autopilot Daemon watcher activated on server startup!")
    except Exception as e:
        log_event(f"Failed to auto-start autopilot daemon: {e}")


# -------------------------------------------------------------
# PYDANTIC SCHEMAS
# -------------------------------------------------------------
class RescheduleRequest(BaseModel):
    video_id: str
    publish_at: str  # ISO 8601 UTC or local format
    channel: Optional[str] = "english"


class PublishNowRequest(BaseModel):
    video_id: str
    channel: Optional[str] = "english"


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


class SaveSlotsRequest(BaseModel):
    slots: List[Dict[str, Any]]
    active_preset: Optional[str] = "custom"
    daily_target: Optional[int] = None
    autopilot_daemon: Optional[bool] = False
    review_before_upload: Optional[bool] = False
    upload_privacy: Optional[str] = "private"
    auto_upload: Optional[bool] = True


class CloudVideoConfigRequest(BaseModel):
    replicate_token: Optional[str] = None
    kling_access_key: Optional[str] = None
    kling_secret_key: Optional[str] = None


class MotionClipRequest(BaseModel):
    asset_name: str
    custom_prompt: Optional[str] = None


class PublishLocalVideoRequest(BaseModel):
    filename: str
    title: Optional[str] = None
    description: Optional[str] = None
    tags: Optional[List[str]] = None
    privacy: str = "public"
    channel: Optional[str] = "english"


class HarvestJobRequest(BaseModel):
    title: str
    prompt: str
    category: str = "custom"
    source_image: Optional[str] = None


class DirectorKeysRequest(BaseModel):
    nvidia_api_key: Optional[str] = None
    elevenlabs_api_key: Optional[str] = None


class ScriptEnhanceRequest(BaseModel):
    raw_script: str
    topic: Optional[str] = None
    language: str = "hi"
    video_format: Optional[str] = "short"


class VoiceAuditionRequest(BaseModel):
    voice_id: str
    sample_text: Optional[str] = None


class DirectorRenderRequest(BaseModel):
    script_text: str
    title: str
    voice: str = "auto"
    voice_speed: float = 0.92
    bgm_filename: Optional[str] = "auto"
    bgm_volume: float = 0.16
    subtitle_style: str = "hormozi"
    enable_classified_badge: bool = False
    visual_engine: str = "auto"
    video_format: Optional[str] = "short"
    language: Optional[str] = "hi"
    real_incident_mode: bool = False
    visual_mode: Optional[str] = "multi_cinematic"
    auto_viral_hook: bool = True
    scenes: Optional[List[Dict[str, Any]]] = None


class DirectorPublishRequest(BaseModel):
    filename: str
    title: str
    description: Optional[str] = None
    tags: Optional[List[str]] = None
    privacy: str = "public"
    pinned_comment: Optional[str] = None
    channel: Optional[str] = "english"


# State cache for last completed Director render
LAST_DIRECTOR_RESULT: Dict[str, Any] = {}


# Track which local files have been published to prevent duplicates
PUBLISH_TRACKER_FILE = PROJECT_ROOT / "config" / "local_publish_tracker.json"


def _load_publish_tracker() -> Dict[str, Any]:
    if PUBLISH_TRACKER_FILE.exists():
        try:
            with open(PUBLISH_TRACKER_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def _save_publish_tracker(data: Dict[str, Any]):
    PUBLISH_TRACKER_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(PUBLISH_TRACKER_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


# -------------------------------------------------------------
# HELPER: GET YOUTUBE SERVICE & MULTI-CHANNEL CONFIG
# -------------------------------------------------------------
CHANNELS_CONFIG_FILE = PROJECT_ROOT / "config" / "channels_config.json"


def _load_channels_config() -> Dict[str, Any]:
    default_cfg = {
        "default_channel": "english",
        "channels": {
            "english": {
                "id": "english",
                "name": "English Shorts Channel",
                "language": "English",
                "token_file": "config/token_english.json",
                "default_privacy": "private",
                "default_category": "28",
            },
            "hindi": {
                "id": "hindi",
                "name": "Hindi Shorts Channel",
                "language": "Hindi",
                "token_file": "config/token_hindi.json",
                "default_privacy": "private",
                "default_category": "28",
            },
        },
    }
    if CHANNELS_CONFIG_FILE.exists():
        try:
            with open(CHANNELS_CONFIG_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return default_cfg


def get_youtube_service(channel: str = "english"):
    try:
        target_ch = (channel or "english").lower().strip()
        creds = YouTubeAuth(channel=target_ch).get_credentials(interactive=False)
        if not creds or not creds.valid:
            return None
        return build("youtube", "v3", credentials=creds)
    except Exception as e:
        print_warning(f"Failed to initialize YouTube service for channel '{channel}': {e}")
        return None


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

    # Check YouTube connections for all channels
    yt_en = get_youtube_service("english")
    yt_hi = get_youtube_service("hindi")
    ch_cfg = _load_channels_config().get("channels", {})
    en_info = YouTubeAuth(channel="english").get_channel_info() if yt_en else None
    hi_info = YouTubeAuth(channel="hindi").get_channel_info() if yt_hi else None

    # System disk usage
    try:
        tot_d, used_d, free_d = shutil.disk_usage(PROJECT_ROOT)
        free_gb = round(free_d / (1024**3), 2)
        used_pct = round((used_d / tot_d) * 100, 1) if tot_d > 0 else 0
    except Exception:
        free_gb = 0.0
        used_pct = 0.0

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
        "youtube_connected": bool(yt_en is not None or yt_hi is not None),
        "channels": {
            "english": {
                "id": "english",
                "name": ch_cfg.get("english", {}).get("name", "English Shorts Channel"),
                "connected": bool(yt_en is not None),
                "authenticated": bool(yt_en is not None),
                "is_authenticated": bool(yt_en is not None),
                "token_exists": YouTubeAuth(channel="english").token_file.exists(),
                "has_token_file": YouTubeAuth(channel="english").token_file.exists(),
                "info": en_info,
            },
            "hindi": {
                "id": "hindi",
                "name": ch_cfg.get("hindi", {}).get("name", "Hindi Shorts Channel"),
                "connected": bool(yt_hi is not None),
                "authenticated": bool(yt_hi is not None),
                "is_authenticated": bool(yt_hi is not None),
                "token_exists": YouTubeAuth(channel="hindi").token_file.exists(),
                "has_token_file": YouTubeAuth(channel="hindi").token_file.exists(),
                "info": hi_info,
            },
        },
        "disk_free_gb": free_gb,
        "disk_used_pct": used_pct,
    }


@app.get("/api/auth/status")
async def get_auth_status(channel: Optional[str] = None):
    ch_cfg = _load_channels_config().get("channels", {})
    res = {}
    for ch_key in ("english", "hindi"):
        auth_mgr = YouTubeAuth(channel=ch_key)
        creds = auth_mgr.get_credentials(interactive=False)
        has_token = auth_mgr.token_file.exists()
        is_valid = bool(creds and creds.valid)
        ch_info = auth_mgr.get_channel_info() if is_valid else None
        res[ch_key] = {
            "channel": ch_key,
            "name": ch_cfg.get(ch_key, {}).get("name", f"{ch_key.title()} Shorts Channel"),
            "has_token_file": has_token,
            "token_exists": has_token,
            "is_authenticated": is_valid,
            "authenticated": is_valid,
            "connected": is_valid,
            "token_expired": bool(creds and creds.expired) if creds else (True if has_token else False),
            "channel_info": ch_info,
        }
    if channel and channel.lower().strip() in res:
        return res[channel.lower().strip()]
    return res


@app.get("/api/auth/url")
async def get_oauth_url(channel: str = "english"):
    """Generate and return Google OAuth authorization URL for the requested channel."""
    try:
        from google_auth_oauthlib.flow import InstalledAppFlow
        from autotube.uploader.auth import YOUTUBE_SCOPES
        cfg = get_config()
        secrets_file = cfg.youtube.client_secrets_file
        if not secrets_file.exists():
            raise HTTPException(status_code=404, detail="client_secrets.json not found in config/")
        
        target_ch = (channel or "english").lower().strip()
        flow = InstalledAppFlow.from_client_secrets_file(str(secrets_file), YOUTUBE_SCOPES)
        flow.redirect_uri = "urn:ietf:wg:oauth:2.0:oob"
        auth_url, _ = flow.authorization_url(prompt="consent", access_type="offline")

        # Save verifier and redirect_uri so exchange_code can redeem this exact request
        if getattr(flow, "code_verifier", None):
            verifier_file = PROJECT_ROOT / "config" / f"oauth_verifier_{target_ch}.txt"
            verifier_file.write_text(flow.code_verifier, encoding="utf-8")

        redirect_file = PROJECT_ROOT / "config" / f"oauth_redirect_{target_ch}.txt"
        redirect_file.write_text(flow.redirect_uri, encoding="utf-8")

        return {"success": True, "auth_url": auth_url, "url": auth_url, "channel": target_ch}
    except Exception as e:
        auth_file = PROJECT_ROOT / "config" / "auth_url.txt"
        if auth_file.exists():
            val = auth_file.read_text(encoding="utf-8").strip()
            return {"success": True, "auth_url": val, "url": val, "channel": channel}
        raise HTTPException(status_code=500, detail=str(e))


class ExchangeCodeRequest(BaseModel):
    code: str
    channel: str = "english"


@app.post("/api/auth/exchange_code")
async def exchange_auth_code(req: ExchangeCodeRequest):
    """Exchange Google OAuth authorization code for credentials tokens and save."""
    try:
        import urllib.parse
        from google_auth_oauthlib.flow import InstalledAppFlow
        from autotube.uploader.auth import YOUTUBE_SCOPES

        raw_input = req.code.strip()
        code = raw_input
        # Support if user pasted the full redirected URL
        if "code=" in raw_input:
            parsed = urllib.parse.urlparse(raw_input)
            params = urllib.parse.parse_qs(parsed.query)
            if "code" in params:
                code = params["code"][0]
        elif "approvalCode=" in raw_input:
            parsed = urllib.parse.urlparse(raw_input)
            params = urllib.parse.parse_qs(parsed.query)
            if "approvalCode" in params:
                code = params["approvalCode"][0]

        # Unquote URL encoding if needed (e.g. 4%2F...)
        code = urllib.parse.unquote(code).strip()

        target_ch = (req.channel or "english").lower().strip()
        cfg = get_config()
        secrets_file = cfg.youtube.client_secrets_file
        flow = InstalledAppFlow.from_client_secrets_file(str(secrets_file), YOUTUBE_SCOPES)

        redirect_file = PROJECT_ROOT / "config" / f"oauth_redirect_{target_ch}.txt"
        if redirect_file.exists():
            flow.redirect_uri = redirect_file.read_text(encoding="utf-8").strip()
        else:
            flow.redirect_uri = "urn:ietf:wg:oauth:2.0:oob"

        verifier_file = PROJECT_ROOT / "config" / f"oauth_verifier_{target_ch}.txt"
        if verifier_file.exists():
            saved_verifier = verifier_file.read_text(encoding="utf-8").strip()
            if saved_verifier:
                flow.code_verifier = saved_verifier
        else:
            flow.autogenerate_code_verifier = False
            flow.code_verifier = None

        flow.fetch_token(code=code)
        creds = flow.credentials

        token_file = PROJECT_ROOT / "config" / f"token_{target_ch}.json"
        token_file.parent.mkdir(parents=True, exist_ok=True)
        with open(token_file, "w", encoding="utf-8") as f:
            f.write(creds.to_json())

        if target_ch == "english":
            try:
                with open(PROJECT_ROOT / "config" / "token.json", "w", encoding="utf-8") as f:
                    f.write(creds.to_json())
            except Exception:
                pass

        try:
            if verifier_file.exists():
                verifier_file.unlink()
            if redirect_file.exists():
                redirect_file.unlink()
        except Exception:
            pass

        log_event(f"Successfully authenticated '{target_ch}' channel via Google OAuth code.")
        return {"success": True, "message": f"Successfully authenticated {target_ch.title()} Channel!"}
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to exchange authorization code: {e}")


class SaveTokenRequest(BaseModel):
    token_json: str
    channel: str = "english"


@app.post("/api/auth/save_token")
async def save_token_payload(req: SaveTokenRequest):
    try:
        data = json.loads(req.token_json)
        target_ch = (req.channel or "english").lower().strip()
        token_file = PROJECT_ROOT / "config" / f"token_{target_ch}.json"
        token_file.parent.mkdir(parents=True, exist_ok=True)
        with open(token_file, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        if target_ch == "english":
            try:
                with open(PROJECT_ROOT / "config" / "token.json", "w", encoding="utf-8") as f:
                    json.dump(data, f, indent=2)
            except Exception:
                pass
        log_event(f"YouTube token_{target_ch}.json updated via Web Dashboard.")
        return {"success": True, "message": f"Token for {target_ch.title()} Channel saved successfully!"}
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid token JSON: {e}")


# -------------------------------------------------------------
# API ROUTES: YOUTUBE VIDEO & SCHEDULE MANAGER
# -------------------------------------------------------------
@app.get("/api/videos")
async def list_videos(channel: str = "english"):
    try:
        target_ch = (channel or "english").lower().strip()
        yt = get_youtube_service(target_ch)
        ch_cfg = _load_channels_config().get("channels", {})
        available_channels = [
            {"id": "english", "name": ch_cfg.get("english", {}).get("name", "English Shorts")},
            {"id": "hindi", "name": ch_cfg.get("hindi", {}).get("name", "Hindi Shorts")},
        ]
        if not yt:
            return {
                "videos": [],
                "channel": None,
                "current_channel": target_ch,
                "available_channels": available_channels,
                "auth_required": True,
                "error": f"YouTube OAuth token for {target_ch.title()} Channel has expired or is not configured. Please authenticate.",
            }

        # 1. Get uploads playlist ID of the authenticated channel
        channels_res = yt.channels().list(part="contentDetails,snippet,statistics", mine=True).execute()
        if not channels_res.get("items"):
            return {
                "videos": [],
                "channel": None,
                "current_channel": target_ch,
                "available_channels": available_channels,
                "auth_required": False,
            }

        ch_item = channels_res["items"][0]
        stats = ch_item.get("statistics", {})
        thumb_url = ch_item["snippet"]["thumbnails"].get("default", {}).get("url", "")
        channel_info = {
            "id": ch_item.get("id"),
            "channel_key": target_ch,
            "title": ch_item["snippet"]["title"],
            "custom_url": ch_item["snippet"].get("customUrl", ""),
            "thumbnail": thumb_url,
            "avatar": thumb_url,
            "subscribers": stats.get("subscriberCount", "0"),
            "subscriber_count": stats.get("subscriberCount", "0"),
            "total_views": stats.get("viewCount", "0"),
            "view_count": stats.get("viewCount", "0"),
            "total_videos": stats.get("videoCount", "0"),
            "video_count": stats.get("videoCount", "0"),
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
            return {
                "videos": [],
                "channel": channel_info,
                "current_channel": target_ch,
                "available_channels": available_channels,
            }

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

        return {
            "videos": video_list,
            "channel": channel_info,
            "current_channel": target_ch,
            "available_channels": available_channels,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/videos/reschedule")
async def reschedule_video(req: RescheduleRequest):
    """Update scheduled release date/time using YouTube Data API."""
    try:
        target_ch = (req.channel or "english").lower().strip()
        yt = get_youtube_service(target_ch)
        if not yt:
            raise HTTPException(status_code=400, detail=f"YouTube service not connected for {target_ch.title()} channel")

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

        log_event(f"Successfully rescheduled video {req.video_id} to {req_time} on {target_ch.title()} channel")
        return {"success": True, "message": f"Video {req.video_id} rescheduled to {req_time}"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/videos/make_public")
async def make_video_public(req: PublishNowRequest):
    """Instantly make any private or scheduled video PUBLIC on YouTube."""
    try:
        target_ch = (req.channel or "english").lower().strip()
        yt = get_youtube_service(target_ch)
        if not yt:
            raise HTTPException(status_code=400, detail=f"YouTube service not connected for {target_ch.title()} channel")
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
    GENERATION_STATUS["current_task"] = f"Master Full Documentary 16:9 ({lang.upper()})"
    log_event(f"Starting Master Full Documentary generation ({lang.upper()})...")

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
        log_event(f"Master Full Documentary generation completed with return code {proc.returncode}!")
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
    return {"success": True, "message": f"Master Full Documentary ({req.lang.upper()}) generation started!"}


SLOTS_CONFIG_FILE = PROJECT_ROOT / "config" / "slots_config.json"


def _load_slots_config() -> Dict[str, Any]:
    if SLOTS_CONFIG_FILE.exists():
        try:
            with open(SLOTS_CONFIG_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {"slots": [], "active_preset": "balanced_7", "daily_target": 7, "presets": {}}


def _save_slots_config(data: Dict[str, Any]):
    SLOTS_CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(SLOTS_CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def run_autopilot_task(slot_id: Optional[str] = None):
    import subprocess
    import sys

    config = _load_slots_config()
    slots = config.get("slots", [])
    count = 1 if slot_id else (len(slots) if slots else int(config.get("daily_target", 5)))
    auto_upload = config.get("auto_upload", True)
    privacy = config.get("upload_privacy", "private")

    task_desc = f"Autopilot Slot ({slot_id})" if slot_id else f"Autopilot Batch ({count} Slots)"
    GENERATION_STATUS["is_running"] = True
    GENERATION_STATUS["current_task"] = task_desc
    log_event(f"Starting {task_desc} generation...")

    try:
        python_bin = sys.executable
        if slot_id:
            this_slot = next((s for s in slots if s.get("id") == slot_id), None)
            active_niche = this_slot.get("niche", "mystery") if this_slot else "mixed"
            raw_lang = this_slot.get("language") or this_slot.get("lang") if this_slot else "mixed"
            active_lang = "hi" if str(raw_lang).lower().startswith("hi") else ("en" if str(raw_lang).lower().startswith("en") else "mixed")
        else:
            # Batch mode: Always mixed so each slot in the configured matrix uses its own unique niche and language
            active_niche = "mixed"
            active_lang = "mixed"

        cmd = [python_bin, "run.py", "autopilot", "--count", str(count), "--niche", active_niche, "--lang", active_lang]
        if auto_upload:
            cmd.append("--upload")
        else:
            cmd.append("--no-upload")

        if privacy == "public":
            cmd.append("--no-schedule")
        else:
            cmd.append("--schedule")

        if slot_id:
            cmd.extend(["--slot-id", slot_id])

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
        log_event(f"Autopilot task completed with return code {proc.returncode}!")
    except Exception as e:
        log_event(f"Autopilot error: {e}")
    finally:
        GENERATION_STATUS["is_running"] = False
        GENERATION_STATUS["current_task"] = "Idle"


@app.get("/api/autopilot/slots")
async def get_autopilot_slots():
    return _load_slots_config()


@app.post("/api/autopilot/slots/save")
async def save_autopilot_slots(req: SaveSlotsRequest):
    data = _load_slots_config()
    data["slots"] = req.slots
    if req.active_preset:
        data["active_preset"] = req.active_preset
    if req.daily_target is not None:
        data["daily_target"] = req.daily_target
    else:
        data["daily_target"] = len(req.slots)
    if req.autopilot_daemon is not None:
        data["autopilot_daemon"] = req.autopilot_daemon
    if req.review_before_upload is not None:
        data["review_before_upload"] = req.review_before_upload
    if req.upload_privacy is not None:
        data["upload_privacy"] = req.upload_privacy
    if req.auto_upload is not None:
        data["auto_upload"] = req.auto_upload
    _save_slots_config(data)
    log_event(f"Slot Matrix updated with {len(req.slots)} active slots.")
    return {"success": True, "message": "Slot matrix saved successfully!", "data": data}


@app.post("/api/autopilot/slots/preset/{preset_name}")
async def apply_autopilot_preset(preset_name: str):
    data = _load_slots_config()
    presets = data.get("presets", {})
    if preset_name in presets:
        data["slots"] = presets[preset_name]
        data["active_preset"] = preset_name
        data["daily_target"] = len(presets[preset_name])
        _save_slots_config(data)
        log_event(f"Applied preset '{preset_name}' ({len(data['slots'])} slots).")
        return {"success": True, "data": data}
    raise HTTPException(status_code=400, detail=f"Preset '{preset_name}' not found.")


@app.post("/api/autopilot/run_slot/{slot_id}")
async def trigger_autopilot_slot(slot_id: str, bg_tasks: BackgroundTasks):
    if GENERATION_STATUS["is_running"]:
        raise HTTPException(status_code=400, detail="Another video generation is already in progress!")

    bg_tasks.add_task(run_autopilot_task, slot_id)
    return {"success": True, "message": f"Autopilot for slot '{slot_id}' started in background!"}


@app.post("/api/autopilot/run")
async def trigger_autopilot(bg_tasks: BackgroundTasks):
    if GENERATION_STATUS["is_running"]:
        raise HTTPException(status_code=400, detail="Another video generation is already in progress!")

    bg_tasks.add_task(run_autopilot_task, None)
    return {"success": True, "message": "Autopilot daily batch started in background!"}


# -------------------------------------------------------------
# API ROUTES: MEDIA PREVIEW & HTML5 VIDEO STREAMING
# -------------------------------------------------------------
@app.get("/api/media/list")
async def list_media_files():
    video_dirs = [
        PROJECT_ROOT / "output" / "shorts",
        PROJECT_ROOT / "output" / "longform",
        PROJECT_ROOT / "output" / "videos",
    ]
    files = []
    seen = set()
    for v_dir in video_dirs:
        if v_dir.exists():
            for p in v_dir.glob("*.mp4"):
                if p.name in seen:
                    continue
                seen.add(p.name)
                stat = p.stat()
                size_mb = round(stat.st_size / (1024 * 1024), 2)
                mtime = datetime.datetime.fromtimestamp(stat.st_mtime).strftime("%d-%b %H:%M")
                files.append({
                    "filename": p.name,
                    "folder": v_dir.name,
                    "size_mb": size_mb,
                    "mtime_raw": stat.st_mtime,
                    "modified": mtime,
                    "stream_url": f"/api/media/stream/{p.name}",
                })
    files.sort(key=lambda x: x.get("mtime_raw", 0), reverse=True)
    return {"files": files}


@app.get("/api/media/stream/{filename}")
async def stream_media(filename: str):
    search_dirs = [
        PROJECT_ROOT / "output" / "shorts",
        PROJECT_ROOT / "output" / "longform",
        PROJECT_ROOT / "output" / "videos",
    ]
    for d in search_dirs:
        p = d / filename
        if p.exists():
            return FileResponse(p, media_type="video/mp4")
    raise HTTPException(status_code=404, detail="Video file not found")


@app.post("/api/media/delete/{filename}")
@app.delete("/api/media/{filename}")
async def delete_media_file(filename: str):
    """Delete a rendered video and associated subtitles/artifacts from disk, and remove from publish tracker."""
    safe_name = os.path.basename(filename.strip())
    if not safe_name or safe_name in (".", ".."):
        raise HTTPException(status_code=400, detail="Invalid filename")

    search_dirs = [
        PROJECT_ROOT / "output" / "shorts",
        PROJECT_ROOT / "output" / "longform",
        PROJECT_ROOT / "output" / "videos",
        PROJECT_ROOT / "output",
    ]
    deleted_paths = []
    for d in search_dirs:
        target = d / safe_name
        if target.exists() and target.is_file():
            try:
                target.unlink()
                deleted_paths.append(str(target))
                log_event(f"🗑️ Deleted video file: {target.name}")
            except Exception as e:
                log_event(f"Error deleting {target.name}: {e}")
                raise HTTPException(status_code=500, detail=f"Failed to delete file: {e}")

    # Also clean associated artifacts (srt, ass, json, preview jpg)
    stem = Path(safe_name).stem
    for ext in (".srt", ".ass", ".jpg", ".png", ".json"):
        for d in search_dirs:
            extra = d / f"{stem}{ext}"
            if extra.exists() and extra.is_file():
                try:
                    extra.unlink()
                except Exception:
                    pass

    # Clean from local publish tracker if present
    tracker = _load_publish_tracker()
    if safe_name in tracker:
        del tracker[safe_name]
        _save_publish_tracker(tracker)
        log_event(f"Removed {safe_name} from local publish tracker.")

    # Reset LAST_DIRECTOR_RESULT if matching
    global LAST_DIRECTOR_RESULT
    if LAST_DIRECTOR_RESULT.get("video_filename") == safe_name:
        LAST_DIRECTOR_RESULT = {}

    if not deleted_paths:
        raise HTTPException(status_code=404, detail=f"File '{safe_name}' not found on server")

    return {
        "success": True,
        "filename": safe_name,
        "message": f"Successfully deleted '{safe_name}'",
        "deleted_count": len(deleted_paths),
    }


@app.post("/api/media/delete_all")
async def delete_all_media_files():
    """Delete all rendered videos from disk and clean publish tracker."""
    search_dirs = [
        PROJECT_ROOT / "output" / "shorts",
        PROJECT_ROOT / "output" / "longform",
        PROJECT_ROOT / "output" / "videos",
    ]
    deleted_count = 0
    freed_bytes = 0
    for d in search_dirs:
        if d.exists():
            for p in list(d.glob("*")):
                if p.is_file():
                    try:
                        sz = p.stat().st_size
                        p.unlink()
                        deleted_count += 1
                        freed_bytes += sz
                    except Exception:
                        pass
        d.mkdir(parents=True, exist_ok=True)

    try:
        _save_publish_tracker({})
    except Exception:
        pass

    global LAST_DIRECTOR_RESULT
    LAST_DIRECTOR_RESULT = {}

    freed_mb = round(freed_bytes / (1024**2), 2)
    log_event(f"🗑️ Deleted all rendered videos: {deleted_count} files removed ({freed_mb} MB freed).")
    return {
        "success": True,
        "deleted_count": deleted_count,
        "freed_mb": freed_mb,
        "message": f"Successfully deleted all {deleted_count} videos ({freed_mb} MB freed)!",
    }


def _get_dir_size_bytes(path: Path) -> int:
    total = 0
    if not path.exists():
        return 0
    try:
        for entry in os.scandir(path):
            if entry.is_file(follow_symlinks=False):
                total += entry.stat().st_size
            elif entry.is_dir(follow_symlinks=False):
                total += _get_dir_size_bytes(Path(entry.path))
    except Exception:
        pass
    return total


def _get_storage_status_dict() -> Dict[str, Any]:
    try:
        tot, used, free = shutil.disk_usage(PROJECT_ROOT)
    except Exception:
        tot, used, free = 1, 0, 1

    videos_size = sum(_get_dir_size_bytes(d) for d in [
        PROJECT_ROOT / "output" / "shorts",
        PROJECT_ROOT / "output" / "longform",
        PROJECT_ROOT / "output" / "videos",
    ])
    temp_size = (
        _get_dir_size_bytes(PROJECT_ROOT / "output" / "temp")
        + _get_dir_size_bytes(PROJECT_ROOT / "temp")
    )
    stock_size = (
        _get_dir_size_bytes(PROJECT_ROOT / "assets" / "stock_cache")
        + _get_dir_size_bytes(PROJECT_ROOT / "assets" / "pexels_videos")
        + _get_dir_size_bytes(PROJECT_ROOT / "assets" / "ai_movie_clips")
    )
    total_cleanable = videos_size + temp_size + stock_size

    return {
        "disk_total_gb": round(tot / (1024**3), 2),
        "disk_used_gb": round(used / (1024**3), 2),
        "disk_free_gb": round(free / (1024**3), 2),
        "disk_used_pct": round((used / tot) * 100, 1) if tot > 0 else 0,
        "videos_size_mb": round(videos_size / (1024**2), 2),
        "temp_size_mb": round(temp_size / (1024**2), 2),
        "stock_size_mb": round(stock_size / (1024**2), 2),
        "total_cleanable_mb": round(total_cleanable / (1024**2), 2),
    }


class StoragePurgeRequest(BaseModel):
    clean_videos: bool = True
    clean_temp: bool = True
    clean_stock: bool = True


@app.get("/api/system/storage")
async def get_system_storage():
    return _get_storage_status_dict()


@app.post("/api/system/storage/purge")
async def purge_system_storage(req: StoragePurgeRequest):
    if GENERATION_STATUS.get("is_running"):
        raise HTTPException(
            status_code=400,
            detail="Cannot purge storage while video generation is currently in progress!"
        )

    freed_bytes = 0
    deleted_files = 0

    if req.clean_videos:
        for d in [
            PROJECT_ROOT / "output" / "shorts",
            PROJECT_ROOT / "output" / "longform",
            PROJECT_ROOT / "output" / "videos",
        ]:
            if d.exists():
                for f in list(d.glob("*")):
                    if f.is_file():
                        try:
                            sz = f.stat().st_size
                            f.unlink()
                            freed_bytes += sz
                            deleted_files += 1
                        except Exception:
                            pass
        try:
            _save_publish_tracker({})
        except Exception:
            pass

    if req.clean_temp:
        for t_dir in [
            PROJECT_ROOT / "output" / "temp",
            PROJECT_ROOT / "temp",
        ]:
            if t_dir.exists():
                for f in list(t_dir.rglob("*")):
                    if f.is_file():
                        try:
                            sz = f.stat().st_size
                            f.unlink()
                            freed_bytes += sz
                            deleted_files += 1
                        except Exception:
                            pass

    if req.clean_stock:
        for s_dir in [
            PROJECT_ROOT / "assets" / "stock_cache",
            PROJECT_ROOT / "assets" / "pexels_videos",
            PROJECT_ROOT / "assets" / "ai_movie_clips",
        ]:
            if s_dir.exists():
                for f in list(s_dir.rglob("*")):
                    if f.is_file():
                        try:
                            sz = f.stat().st_size
                            f.unlink()
                            freed_bytes += sz
                            deleted_files += 1
                        except Exception:
                            pass

    # Ensure critical directory paths remain intact
    for p in [
        PROJECT_ROOT / "output" / "shorts",
        PROJECT_ROOT / "output" / "longform",
        PROJECT_ROOT / "output" / "videos",
        PROJECT_ROOT / "output" / "temp",
        PROJECT_ROOT / "temp" / "archival",
        PROJECT_ROOT / "temp" / "director",
        PROJECT_ROOT / "assets" / "stock_cache",
        PROJECT_ROOT / "assets" / "pexels_videos",
    ]:
        p.mkdir(parents=True, exist_ok=True)

    freed_mb = round(freed_bytes / (1024**2), 2)
    log_event(f"🧹 Storage Purge: Freed {freed_mb} MB ({deleted_files} files deleted).")

    return {
        "success": True,
        "message": f"Successfully freed {freed_mb} MB ({deleted_files} files deleted)!",
        "freed_mb": freed_mb,
        "deleted_files": deleted_files,
        "storage": _get_storage_status_dict(),
    }



@app.get("/api/audio/preview/voice/{voice_name}")
async def preview_voice(voice_name: str):
    v = voice_name.lower().strip()
    preview_dir = PROJECT_ROOT / "assets" / "previews" / "voices"
    target = preview_dir / f"{v}.mp3"
    if target.exists():
        return FileResponse(target, media_type="audio/mpeg")

    # If not yet generated, attempt synthesis
    try:
        preview_dir.mkdir(parents=True, exist_ok=True)
        from autotube.voice.tts_engine import TTSEngine
        is_hi = v.startswith("hi") or "hindi" in v or v in ("akashvani", "akashwani", "madhur", "swara")
        sample_text = "ब्रह्मांड के अनंत रहस्यों में आपका स्वागत है। ब्लैक होल के अंदर वक्त ठहर जाता है।" if is_hi else "Welcome to the edge of the universe. Beyond the event horizon, time stands still."
        engine = TTSEngine(default_voice=v)
        engine.synthesize(text=sample_text, output_audio_path=target, voice=v)
        if target.exists():
            return FileResponse(target, media_type="audio/mpeg")
    except Exception as e:
        log_event(f"Error generating voice preview for {v}: {e}")

    raise HTTPException(status_code=404, detail="Voice preview not available")


@app.get("/api/audio/preview/bgm/{category}")
async def preview_bgm(category: str):
    cat = category.lower().strip()
    audio_dir = PROJECT_ROOT / "assets" / "audio"

    cat_map = {
        "psychology": audio_dir / "psychology" / "anxiety.mp3",
        "space": audio_dir / "space" / "lightless_dawn.mp3",
        "history": audio_dir / "history" / "heroic_age.mp3",
        "mystery": audio_dir / "mystery" / "curse_of_the_scarab.mp3",
        "alien": audio_dir / "alien" / "roswell_mystery_calm.mp3",
        "auto": audio_dir / "mystery" / "desert_city.mp3",
    }

    target = cat_map.get(cat)
    if not target or not target.exists():
        sub_dir = audio_dir / cat
        if sub_dir.exists():
            for f in sub_dir.glob("*.mp3"):
                return FileResponse(f, media_type="audio/mpeg")
        fallback = audio_dir / "mystery" / "desert_city.mp3"
        if fallback.exists():
            return FileResponse(fallback, media_type="audio/mpeg")
        raise HTTPException(status_code=404, detail="BGM preview not found")

    return FileResponse(target, media_type="audio/mpeg")


@app.get("/api/logs")
async def get_logs():
    logs = GENERATION_STATUS["logs"]
    if not logs and LOGS_FILE.exists():
        try:
            with open(LOGS_FILE, "r", encoding="utf-8", errors="ignore") as f:
                lines = f.readlines()
                logs = [line.strip() for line in lines[-50:] if line.strip()]
        except Exception:
            pass
    return {
        "is_running": GENERATION_STATUS["is_running"],
        "current_task": GENERATION_STATUS["current_task"],
        "logs": logs[-60:],
    }


# -------------------------------------------------------------
# API ROUTES: AI DIRECTOR STUDIO (NVIDIA + ELEVENLABS + BGM)
# -------------------------------------------------------------
@app.get("/api/director/options")
async def get_director_options():
    """Return available ElevenLabs voices, BGM audio tracks, and subtitle styles."""
    from autotube.media.director_engine import DirectorEngine
    director = DirectorEngine()
    return director.get_studio_options()


@app.post("/api/director/save_keys")
async def save_director_keys(req: DirectorKeysRequest):
    """Save NVIDIA and ElevenLabs API keys to .env."""
    env_file = PROJECT_ROOT / ".env"
    env_lines = []
    if env_file.exists():
        with open(env_file, "r", encoding="utf-8") as f:
            env_lines = f.readlines()

    keys_to_update = {}
    if req.nvidia_api_key is not None:
        keys_to_update["NVIDIA_API_KEY"] = req.nvidia_api_key.strip()
        os.environ["NVIDIA_API_KEY"] = req.nvidia_api_key.strip()
    if req.elevenlabs_api_key is not None:
        keys_to_update["ELEVENLABS_API_KEY"] = req.elevenlabs_api_key.strip()
        os.environ["ELEVENLABS_API_KEY"] = req.elevenlabs_api_key.strip()

    new_lines = []
    updated_keys = set()
    for line in env_lines:
        line_clean = line.strip()
        matched = False
        for k, v in keys_to_update.items():
            if line_clean.startswith(f"{k}="):
                new_lines.append(f"{k}={v}\n")
                updated_keys.add(k)
                matched = True
                break
        if not matched:
            new_lines.append(line)

    for k, v in keys_to_update.items():
        if k not in updated_keys and v:
            new_lines.append(f"{k}={v}\n")

    with open(env_file, "w", encoding="utf-8") as f:
        f.writelines(new_lines)

    log_event("Director Studio API keys (NVIDIA & ElevenLabs) saved successfully.")
    return {"success": True, "message": "API keys saved to .env"}


@app.post("/api/director/enhance_script")
async def enhance_script(req: ScriptEnhanceRequest):
    """Enhance raw script or topic into a 3-act viral high-retention Short or Long video script."""
    from autotube.media.director_engine import DirectorEngine
    director = DirectorEngine()
    res = director.enhance_script_with_ai(
        raw_input=req.raw_script,
        topic=req.topic,
        language=req.language,
        video_format=req.video_format or "short",
    )
    return res


@app.post("/api/director/test_voice")
async def test_voice_audition(req: VoiceAuditionRequest):
    """Generate a quick 3-second voice preview."""
    from autotube.media.director_engine import DirectorEngine
    director = DirectorEngine()
    try:
        sample_audio = director.generate_voice_audition(voice_id=req.voice_id, sample_text=req.sample_text)
        return {
            "success": True,
            "stream_url": f"/api/director/stream_temp/{sample_audio.name}",
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.api_route("/api/director/stream_temp/{filename}", methods=["GET", "HEAD"])
async def stream_director_temp_file(filename: str):
    """Stream temporary audio preview file."""
    temp_p = PROJECT_ROOT / "temp" / "director" / filename
    if not temp_p.exists():
        temp_p = PROJECT_ROOT / "temp" / filename
    if not temp_p.exists():
        raise HTTPException(status_code=404, detail="Audio preview not found")
    return FileResponse(temp_p, media_type="audio/mpeg")


@app.api_route("/api/director/stream_bgm/{filename}", methods=["GET", "HEAD"])
async def stream_director_bgm_file(filename: str):
    """Stream background music track for browser preview."""
    audio_dir = PROJECT_ROOT / "assets" / "audio"
    matches = list(audio_dir.rglob(filename))
    if not matches:
        raise HTTPException(status_code=404, detail="BGM track not found")
    return FileResponse(matches[0], media_type="audio/mpeg")


def run_director_render_task(req_data: dict):
    """Background task worker for rendering custom Director video."""
    global LAST_DIRECTOR_RESULT
    GENERATION_STATUS["is_running"] = True
    v_fmt = req_data.get("video_format", "short")
    fmt_tag = "16:9 Long Video" if v_fmt == "landscape_long" else "9:16 Short"
    GENERATION_STATUS["current_task"] = f"AI Studio ({fmt_tag}): {req_data.get('title', 'Custom Video')[:22]}"
    log_event(f"🎬 Starting AI Video Studio Render ({fmt_tag}): '{req_data.get('title')}'...")

    def update_progress(pct: int, msg: str):
        GENERATION_STATUS["progress"] = pct
        log_event(f"Studio: {msg}")

    try:
        from autotube.media.director_engine import DirectorEngine
        director = DirectorEngine()
        result = director.render_custom_video(
            script_text=req_data["script_text"],
            title=req_data["title"],
            voice=req_data.get("voice", "akashvani"),
            voice_speed=float(req_data.get("voice_speed", 1.05)),
            bgm_filename=req_data.get("bgm_filename", "auto"),
            bgm_volume=float(req_data.get("bgm_volume", 0.16)),
            subtitle_style_id=req_data.get("subtitle_style", "hormozi"),
            enable_classified_badge=bool(req_data.get("enable_classified_badge", False)),
            visual_engine=req_data.get("visual_engine", "auto"),
            video_format=v_fmt,
            language=req_data.get("language", "hi"),
            real_incident_mode=bool(req_data.get("real_incident_mode", False)),
            visual_mode=req_data.get("visual_mode", "multi_cinematic"),
            auto_viral_hook=bool(req_data.get("auto_viral_hook", True)),
            scenes=req_data.get("scenes"),
            progress_callback=update_progress,
        )

        LAST_DIRECTOR_RESULT = result
        log_event(f"✅ AI Video Studio successfully completed: {result['video_filename']} ({result.get('duration', 0):.1f}s)!")
    except Exception as e:
        log_event(f"❌ AI Video Studio Render failed: {e}")
        LAST_DIRECTOR_RESULT = {"success": False, "error": str(e)}
    finally:
        GENERATION_STATUS["is_running"] = False
        GENERATION_STATUS["current_task"] = "Idle"
        GENERATION_STATUS["progress"] = 0


@app.post("/api/director/render")
async def trigger_director_render(req: DirectorRenderRequest, bg_tasks: BackgroundTasks):
    """Trigger complete custom video render matching user script, voice, BGM, and styling."""
    if GENERATION_STATUS["is_running"]:
        raise HTTPException(status_code=400, detail="Another video generation task is currently running!")

    req_dict = req.dict()
    bg_tasks.add_task(run_director_render_task, req_dict)
    return {"success": True, "message": f"Started AI Director render for '{req.title}'!"}


@app.get("/api/director/last_result")
async def get_director_last_result():
    """Retrieve result of most recently rendered Director Short."""
    return LAST_DIRECTOR_RESULT


@app.post("/api/director/publish")
async def publish_director_video(req: DirectorPublishRequest):
    """Publish rendered director video to YouTube with 1-click."""
    from autotube.uploader.youtube_upload import YouTubeUploader
    video_path = PROJECT_ROOT / "output" / "shorts" / req.filename
    if not video_path.exists():
        video_path = PROJECT_ROOT / "output" / "longform" / req.filename
    if not video_path.exists():
        video_path = PROJECT_ROOT / "output" / req.filename
    if not video_path.exists():
        raise HTTPException(status_code=404, detail="Rendered video file not found")

    target_ch = (req.channel or "english").lower().strip()
    uploader = YouTubeUploader(channel=target_ch)
    desc = (req.description or req.title) + "\n\n" + (" ".join(req.tags or ["#Shorts", "#Viral"]))

    video_url = uploader.upload_video(
        video_path=video_path,
        title=req.title,
        description=desc,
        tags=req.tags or ["Shorts", "Viral"],
        privacy_status=req.privacy or "public",
        pinned_comment=req.pinned_comment,
        channel=target_ch,
    )

    if not video_url:
        raise HTTPException(status_code=500, detail="YouTube upload failed (API limit or credentials error)")

    # Record in publish tracker
    tracker = _load_publish_tracker()
    tracker[req.filename] = {
        "url": video_url,
        "date": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "title": req.title,
        "privacy": req.privacy,
    }
    _save_publish_tracker(tracker)

    log_event(f"Director Short successfully published to YouTube: {video_url}!")
    return {"success": True, "url": video_url}


# Backward compatibility aliases
@app.get("/api/settings/cloud_video")
async def get_cloud_video_settings():
    return await get_director_options()


@app.post("/api/settings/cloud_video")
async def save_cloud_video_settings(req: CloudVideoConfigRequest):
    return {"success": True, "message": "Updated"}


@app.get("/api/media/character_clips")
async def list_character_clips():
    clips = []
    if CANONICAL_VIDEOS_DIR.exists():
        for p in sorted(CANONICAL_VIDEOS_DIR.glob("*.mp4")):
            stat = p.stat()
            clips.append({
                "filename": p.name,
                "asset_stem": p.stem.replace("_motion", ""),
                "size_mb": round(stat.st_size / (1024 * 1024), 2),
                "stream_url": f"/api/media/stream_clip/{p.name}",
            })
    return {"clips": clips}


@app.get("/api/media/stream_clip/{filename}")
async def stream_character_clip(filename: str):
    p = CANONICAL_VIDEOS_DIR / filename
    if not p.exists():
        raise HTTPException(status_code=404, detail="Character motion clip not found")
    return FileResponse(p, media_type="video/mp4")


def run_motion_clip_task(asset_name: str, custom_prompt: Optional[str]):
    GENERATION_STATUS["is_running"] = True
    GENERATION_STATUS["current_task"] = f"AI Motion Video: {asset_name}"
    log_event(f"Starting Movie Motion Clip Generation for {asset_name}...")

    try:
        gen = CloudVideoGenerator()
        if not gen.is_configured():
            log_event("Error: No Cloud Video API Token configured (Replicate or Kling required).")
            return

        source_img = PROJECT_ROOT / "assets" / "alien_interview" / f"{asset_name}.jpg"
        if not source_img.exists():
            log_event(f"Error: Source image {source_img.name} does not exist.")
            return

        target_vid = CANONICAL_VIDEOS_DIR / f"{asset_name}_motion.mp4"
        prompt = custom_prompt or (
            f"Cinematic movie shot, 1947 Roswell interrogation room, {asset_name} subtle movement, "
            f"breathing, blinking eyes, moody atmospheric lighting, dark noir 4k"
        )

        if gen.replicate_token:
            res = gen.generate_i2v_replicate(
                image_path=source_img,
                prompt=prompt,
                output_path=target_vid,
            )
        elif gen.kling_access_key:
            res = gen.generate_i2v_kling(
                image_path=source_img,
                prompt=prompt,
                output_path=target_vid,
            )
        else:
            log_event("No paid token found. Using 100% FREE Wan2.1 ZeroGPU generator...")
            from autotube.media.free_video_gen import FreeVideoGenerator
            free_gen = FreeVideoGenerator()
            res = free_gen.generate_i2v(
                image_path=source_img,
                prompt=prompt,
                output_path=target_vid,
            )

        if res and res.exists():
            log_event(f"Success! Character Motion Clip saved to {res.name} ({round(res.stat().st_size / (1024*1024), 2)} MB)!")
        else:
            log_event(f"Motion clip generation for {asset_name} failed or timed out.")
    except Exception as e:
        log_event(f"Motion clip generation error: {e}")
    finally:
        GENERATION_STATUS["is_running"] = False
        GENERATION_STATUS["current_task"] = "Idle"


@app.post("/api/generate/motion_clip")
async def trigger_motion_clip_generation(req: MotionClipRequest, bg_tasks: BackgroundTasks):
    if GENERATION_STATUS["is_running"]:
        raise HTTPException(status_code=400, detail="Another video generation task is currently running!")

    bg_tasks.add_task(run_motion_clip_task, req.asset_name, req.custom_prompt)
    return {"success": True, "message": f"Started movie motion video generation for {req.asset_name}!"}


# -------------------------------------------------------------
# 24/7 AI VIDEO HARVESTER & VAULT API
# -------------------------------------------------------------
@app.get("/api/harvester/status")
async def get_harvester_status():
    """Return status of 24/7 background video harvester and vault clips."""
    from autotube.media.ai_video_harvester import harvester_instance
    jobs = harvester_instance.load_queue()
    pending = [j for j in jobs if j.get("status") != "completed"]
    completed = [j for j in jobs if j.get("status") == "completed"]
    clips = harvester_instance.get_vault_clips()
    return {
        "is_running": harvester_instance.is_running,
        "total_jobs": len(jobs),
        "pending_count": len(pending),
        "completed_count": len(completed),
        "jobs": jobs,
        "clips": clips,
    }


@app.post("/api/harvester/start")
async def start_harvester():
    """Start the 24/7 background harvester thread."""
    from autotube.media.ai_video_harvester import harvester_instance
    harvester_instance.start_background_harvester()
    log_event("Started 24/7 Background AI Video Harvester!")
    return {"success": True, "message": "24/7 Background Harvester is running!"}


@app.post("/api/harvester/stop")
async def stop_harvester():
    """Stop the background harvester thread."""
    from autotube.media.ai_video_harvester import harvester_instance
    harvester_instance.stop_background_harvester()
    log_event("Stopped 24/7 Background AI Video Harvester.")
    return {"success": True, "message": "Harvester stopped."}


@app.post("/api/harvester/add_job")
async def add_harvester_job(req: HarvestJobRequest):
    """Add a custom scene prompt to the 24/7 harvest queue."""
    from autotube.media.ai_video_harvester import harvester_instance
    job = harvester_instance.add_job(
        title=req.title,
        prompt=req.prompt,
        category=req.category,
        source_image=req.source_image,
    )
    log_event(f"Added custom job to Harvester queue: {req.title}")
    return {"success": True, "job": job}


@app.api_route("/api/harvester/stream/{filename}", methods=["GET", "HEAD"])
async def stream_vault_video(filename: str):
    """Stream harvested vault video with native byte-range support for HTML5 playback."""
    from autotube.media.ai_video_harvester import VAULT_DIR, CANONICAL_VIDEOS_DIR
    clean_name = Path(filename).name
    video_path = VAULT_DIR / clean_name
    if not video_path.exists():
        video_path = CANONICAL_VIDEOS_DIR / clean_name
    if not video_path.exists():
        raise HTTPException(status_code=404, detail="Clip not found in vault")

    return FileResponse(video_path, media_type="video/mp4")


@app.post("/api/harvester/upload")
async def upload_vault_clip(file: UploadFile = File(...)):
    """Upload a user video clip (e.g. from Google Flow, Sora, Luma, etc.) directly into the vault."""
    from autotube.media.ai_video_harvester import VAULT_DIR
    VAULT_DIR.mkdir(parents=True, exist_ok=True)

    clean_name = sanitize_filename(Path(file.filename).stem) + Path(file.filename).suffix.lower()
    if not clean_name.endswith((".mp4", ".mov", ".webm")):
        raise HTTPException(status_code=400, detail="Only video files (.mp4, .mov, .webm) are supported.")

    target_path = VAULT_DIR / clean_name
    content = await file.read()
    with open(target_path, "wb") as f:
        f.write(content)

    log_event(f"Uploaded custom video clip to Vault: {clean_name} ({round(len(content)/(1024*1024), 2)} MB)")
    return {"success": True, "filename": clean_name, "message": f"Successfully uploaded {clean_name} to Vault!"}


# Track the state and error of the most recent publish request
LAST_PUBLISH_RESULT: Dict[str, Any] = {
    "filename": None,
    "status": "idle",
    "error": None,
    "url": None,
}


# -------------------------------------------------------------
# API ROUTES: PUBLISH LOCAL VIDEO TO YOUTUBE (WITH DUPLICATE CHECK)
# -------------------------------------------------------------
@app.get("/api/media/publish_status")
async def get_publish_status():
    """Return which local files have already been published to YouTube and recent publish status."""
    tracker = _load_publish_tracker()
    return {
        "published": tracker,
        "last_publish": LAST_PUBLISH_RESULT,
    }


@app.post("/api/media/publish")
async def publish_local_video(req: PublishLocalVideoRequest, bg_tasks: BackgroundTasks):
    """Upload a local rendered video to YouTube. Prevents duplicate uploads."""
    video_path = PROJECT_ROOT / "output" / "shorts" / req.filename
    if not video_path.exists():
        raise HTTPException(status_code=404, detail=f"Video file '{req.filename}' not found in output/shorts/")

    # Duplicate check
    tracker = _load_publish_tracker()
    if req.filename in tracker:
        existing = tracker[req.filename]
        raise HTTPException(
            status_code=409,
            detail=f"Already published! YouTube URL: {existing.get('url', 'unknown')} (uploaded on {existing.get('date', 'unknown')})"
        )

    if GENERATION_STATUS["is_running"]:
        raise HTTPException(status_code=400, detail="Another task is in progress. Wait for it to complete.")

    LAST_PUBLISH_RESULT["filename"] = req.filename
    LAST_PUBLISH_RESULT["status"] = "publishing"
    LAST_PUBLISH_RESULT["error"] = None
    LAST_PUBLISH_RESULT["url"] = None

    bg_tasks.add_task(run_publish_task, req.filename, video_path, req.title, req.description, req.tags, req.privacy, req.channel or "english")
    return {"success": True, "message": f"Publishing '{req.filename}' to YouTube ({(req.channel or 'english').title()} Channel) in background..."}


def run_publish_task(
    filename: str,
    video_path: Path,
    title: Optional[str],
    description: Optional[str],
    tags: Optional[List[str]],
    privacy: str,
    channel: str = "english",
):
    """Background task to upload a local video to YouTube."""
    global LAST_PUBLISH_RESULT
    target_ch = (channel or "english").lower().strip()
    GENERATION_STATUS["is_running"] = True
    GENERATION_STATUS["current_task"] = f"Publishing ({target_ch.title()} Channel): {filename}"
    log_event(f"Starting YouTube upload for {filename} to {target_ch.title()} channel...")

    try:
        from autotube.uploader.youtube_upload import YouTubeUploader

        uploader = YouTubeUploader(channel=target_ch)

        # Auto-generate title from filename if not provided
        if not title:
            stem = video_path.stem
            title = stem.replace("_", " ").title()
            # Add series branding for alien interview videos
            if "alien_interview" in stem:
                part_num = ""
                for seg in stem.split("_"):
                    if seg.isdigit():
                        part_num = seg
                        break
                lang = "Hindi" if stem.endswith("_hi") else "English"
                title = f"78 Years Secret: Roswell Alien's First Words Shocked the US Military 😱 (Part {part_num or 1}) #Shorts" if lang == "English" else f"78 साल का राज: रोसवेल एलियन के पहले शब्दों ने सेना को हिला दिया 😱 (Part {part_num or 1}) #Shorts"

        if not description:
            description = (
                f"{title}\n\n"
                "Based on 'Alien Interview' by Lawrence Spencer - The classified transcripts "
                "of Nurse Matilda O'Donnell MacElroy's telepathic sessions with the alien being "
                "known as 'Airl' at Roswell, 1947.\n\n"
                "#AlienInterview #Roswell1947 #TopSecret #Shorts"
            )

        if not tags:
            tags = [
                "Alien Interview", "Roswell 1947", "Airl", "Top Secret",
                "UFO", "Extraterrestrial", "Mystery", "Shorts",
            ]

        video_url = uploader.upload_video(
            video_path=video_path,
            title=title,
            description=description,
            tags=tags,
            privacy_status=privacy,
            channel=target_ch,
        )

        if video_url:
            # Record in publish tracker to prevent duplicate uploads
            tracker = _load_publish_tracker()
            tracker[filename] = {
                "url": video_url,
                "title": title,
                "privacy": privacy,
                "date": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                "size_mb": round(video_path.stat().st_size / (1024 * 1024), 2),
            }
            _save_publish_tracker(tracker)
            LAST_PUBLISH_RESULT["status"] = "success"
            LAST_PUBLISH_RESULT["url"] = video_url
            LAST_PUBLISH_RESULT["error"] = None
            log_event(f"SUCCESS! {filename} published to YouTube: {video_url}")
        else:
            err_msg = uploader.last_error or "Upload failed: YouTube returned no URL."
            LAST_PUBLISH_RESULT["status"] = "error"
            LAST_PUBLISH_RESULT["error"] = err_msg
            LAST_PUBLISH_RESULT["url"] = None
            log_event(f"FAILED: {filename} upload failed: {err_msg}")

    except Exception as e:
        LAST_PUBLISH_RESULT["status"] = "error"
        LAST_PUBLISH_RESULT["error"] = str(e)
        LAST_PUBLISH_RESULT["url"] = None
        log_event(f"Publish error for {filename}: {e}")
    finally:
        GENERATION_STATUS["is_running"] = False
        GENERATION_STATUS["current_task"] = "Idle"


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
