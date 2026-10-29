"""Facebook Reels Uploader using Meta Graph API.
Uploads vertical 9:16 videos directly to a Facebook Page as Facebook Reels.
"""

import json
import logging
import os
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional
import requests

from autotube.config import PROJECT_ROOT
from autotube.utils.console import print_error, print_info, print_success, print_warning

logger = logging.getLogger(__name__)

FACEBOOK_CONFIG_FILE = PROJECT_ROOT / "config" / "facebook_credentials.json"
FACEBOOK_HISTORY_FILE = PROJECT_ROOT / "config" / "facebook_published_history.json"
GRAPH_API_VERSION = "v19.0"
GRAPH_API_BASE = f"https://graph.facebook.com/{GRAPH_API_VERSION}"
RUP_API_BASE = f"https://rupload.facebook.com/video-upload/{GRAPH_API_VERSION}"


class FacebookReelsUploader:
    """Manages authentication and direct publishing of Facebook Reels to a Facebook Page."""

    def __init__(self, credentials_path: Optional[Path] = None):
        self.credentials_path = credentials_path or FACEBOOK_CONFIG_FILE
        self.history_path = FACEBOOK_HISTORY_FILE
        self._ensure_files()

    def _ensure_files(self) -> None:
        """Ensure config directory and history files exist."""
        self.credentials_path.parent.mkdir(parents=True, exist_ok=True)
        if not self.history_path.exists():
            try:
                with open(self.history_path, "w", encoding="utf-8") as f:
                    json.dump([], f, indent=2)
            except Exception as e:
                logger.warning(f"Could not initialize facebook history file: {e}")

    def load_credentials(self) -> Dict[str, Any]:
        """Load stored Facebook Page ID and Page Access Token."""
        if not self.credentials_path.exists():
            return {}
        try:
            with open(self.credentials_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Error reading Facebook credentials: {e}")
            return {}

    def is_configured(self) -> bool:
        """Check if Page ID and Access Token are configured."""
        creds = self.load_credentials()
        return bool(creds.get("page_id") and creds.get("access_token"))

    def save_credentials(self, page_id: str, access_token: str) -> Dict[str, Any]:
        """Save and verify Facebook Page ID and Access Token."""
        clean_page_id = str(page_id).strip()
        clean_token = str(access_token).strip()

        if not clean_page_id or not clean_token:
            return {"success": False, "error": "Both Page ID and Access Token are required."}

        # Verify credentials against Graph API
        verification = self.verify_credentials(clean_page_id, clean_token)
        if not verification.get("success"):
            return verification

        page_name = verification.get("page_name", "Facebook Page")
        page_picture = verification.get("page_picture", "")

        creds = {
            "page_id": clean_page_id,
            "access_token": clean_token,
            "page_name": page_name,
            "page_picture": page_picture,
            "updated_at": int(time.time()),
        }

        with open(self.credentials_path, "w", encoding="utf-8") as f:
            json.dump(creds, f, indent=2)

        print_success(f"Facebook Page credentials saved and verified for: '{page_name}' (ID: {clean_page_id})")
        return {"success": True, "page_name": page_name, "page_id": clean_page_id, "page_picture": page_picture}

    def verify_credentials(self, page_id: Optional[str] = None, access_token: Optional[str] = None) -> Dict[str, Any]:
        """Verify token validity and fetch Facebook Page details."""
        if not page_id or not access_token:
            creds = self.load_credentials()
            page_id = creds.get("page_id")
            access_token = creds.get("access_token")

        if not page_id or not access_token:
            return {"success": False, "error": "Facebook credentials not configured."}

        try:
            url = f"{GRAPH_API_BASE}/{page_id}"
            params = {
                "fields": "id,name,link,picture{url}",
                "access_token": access_token,
            }
            resp = requests.get(url, params=params, timeout=12)
            data = resp.json()

            if "error" in data:
                err_msg = data["error"].get("message", "Unknown Graph API error")
                err_code = data["error"].get("code", "")
                return {"success": False, "error": f"Facebook API Error ({err_code}): {err_msg}"}

            page_name = data.get("name", "Unknown Page")
            picture_url = ((data.get("picture") or {}).get("data") or {}).get("url", "")

            return {
                "success": True,
                "page_id": page_id,
                "page_name": page_name,
                "page_link": data.get("link", f"https://facebook.com/{page_id}"),
                "page_picture": picture_url,
            }
        except Exception as e:
            return {"success": False, "error": f"Connection error verifying Facebook Page: {e}"}

    def upload_reel(
        self,
        video_path: Path,
        title: str,
        description: Optional[str] = None,
        tags: Optional[List[str]] = None,
        progress_callback: Optional[Callable[[int, str], None]] = None,
        language: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Upload a vertical 9:16 video to the connected Facebook Page as a Reel.

        Follows Meta Graph API Reels 3-phase upload protocol:
        Phase 1: Initialize session on /{page_id}/video_reels?upload_phase=start
        Phase 2: Upload video binary to rupload.facebook.com
        Phase 3: Publish reel on /{page_id}/video_reels?upload_phase=finish
        """
        video_path = Path(video_path)
        if not video_path.exists():
            return {"success": False, "error": f"Video file not found: {video_path}"}

        file_size = video_path.stat().st_size
        if file_size == 0:
            return {"success": False, "error": "Video file is empty."}

        creds = self.load_credentials()
        page_id = creds.get("page_id")
        access_token = creds.get("access_token")

        if not page_id or not access_token:
            return {"success": False, "error": "Facebook Page credentials missing. Configure them in Settings."}

        # Strict Hindi Content Guard: Facebook Page is strictly reserved for Hindi Reels
        is_hindi = (
            (language and str(language).lower().startswith("hi"))
            or any("\u0900" <= c <= "\u097F" for c in (title or ""))
            or any("\u0900" <= c <= "\u097F" for c in (description or ""))
            or any("\u0900" <= c <= "\u097F" for c in video_path.name)
        )
        if not is_hindi:
            page_name = creds.get("page_name", "CosmoCronicle")
            msg = f"Facebook Page '{page_name}' is strictly reserved for Hindi Reels. Video '{video_path.name}' is English and was blocked from Facebook upload."
            print_warning(f"⛔ [Facebook Reels Guard] {msg}")
            return {"success": False, "skipped": True, "error": msg}

        # Build Reel Caption (Description + Viral Reel Hashtags)
        caption = self._build_reel_caption(title=title, description=description, tags=tags)

        if progress_callback:
            progress_callback(10, "Initializing Facebook Reels upload session...")

        print_info(f"🚀 [Facebook Reels] Starting Reel upload: '{video_path.name}' ({file_size / (1024*1024):.1f} MB)")

        # Phase 1: Initialize Upload Session
        try:
            init_url = f"{GRAPH_API_BASE}/{page_id}/video_reels"
            init_payload = {
                "upload_phase": "start",
                "access_token": access_token,
            }
            init_resp = requests.post(init_url, data=init_payload, timeout=20)
            init_data = init_resp.json()

            if "error" in init_data:
                err = init_data["error"].get("message", "Error in Phase 1 start")
                print_error(f"Facebook Reels Phase 1 failed: {err}")
                return {"success": False, "error": f"Facebook Reels Init Error: {err}"}

            video_id = init_data.get("video_id")
            upload_url = init_data.get("upload_url")

            if not video_id:
                return {"success": False, "error": "No video_id returned from Facebook Reels start phase."}

            # If upload_url is missing, construct the standard rupload URL
            if not upload_url:
                upload_url = f"{RUP_API_BASE}/{video_id}"

            print_info(f"   Reel session initiated: video_id={video_id}")
        except Exception as e:
            return {"success": False, "error": f"Failed during Phase 1 session init: {e}"}

        # Phase 2: Upload Video Binary
        if progress_callback:
            progress_callback(30, "Uploading video binary to Meta CDN...")

        try:
            headers = {
                "Authorization": f"OAuth {access_token}",
                "offset": "0",
                "file_size": str(file_size),
                "Content-Type": "application/octet-stream",
            }

            with open(video_path, "rb") as video_file:
                upload_resp = requests.post(
                    upload_url,
                    headers=headers,
                    data=video_file,
                    timeout=180,
                )

            upload_data = upload_resp.json() if upload_resp.content else {}
            if "error" in upload_data:
                err = upload_data["error"].get("message", "Binary upload failed")
                print_error(f"Facebook Reels binary upload failed: {err}")
                return {"success": False, "error": f"Upload Phase 2 Error: {err}"}

            print_info(f"   Binary uploaded successfully to Facebook.")
        except Exception as e:
            return {"success": False, "error": f"Failed during Phase 2 binary upload: {e}"}

        # Phase 3: Finish and Publish Reel
        if progress_callback:
            progress_callback(75, "Publishing Reel to Facebook Page...")

        try:
            finish_url = f"{GRAPH_API_BASE}/{page_id}/video_reels"
            finish_payload = {
                "upload_phase": "finish",
                "access_token": access_token,
                "video_id": video_id,
                "video_state": "PUBLISHED",
                "description": caption,
            }

            finish_resp = requests.post(finish_url, data=finish_payload, timeout=30)
            finish_data = finish_resp.json()

            if "error" in finish_data:
                err = finish_data["error"].get("message", "Error in Phase 3 finish")
                print_error(f"Facebook Reels Phase 3 failed: {err}")
                return {"success": False, "error": f"Publish Phase 3 Error: {err}"}

            post_id = finish_data.get("post_id") or video_id
            reel_url = f"https://www.facebook.com/reel/{video_id}"

            print_success(f"🎉 Facebook Reel Published Successfully! URL: {reel_url}")

            # Record in published history
            self._record_publish(
                video_id=video_id,
                post_id=post_id,
                title=title,
                caption=caption,
                reel_url=reel_url,
                video_filename=video_path.name,
            )

            if progress_callback:
                progress_callback(100, "Reel Published Successfully!")

            return {
                "success": True,
                "video_id": video_id,
                "post_id": post_id,
                "reel_url": reel_url,
                "title": title,
                "caption": caption,
            }
        except Exception as e:
            return {"success": False, "error": f"Failed during Phase 3 publishing: {e}"}

    def _build_reel_caption(
        self,
        title: str,
        description: Optional[str] = None,
        tags: Optional[List[str]] = None,
    ) -> str:
        """Construct an engaging Facebook Reel caption with hashtags."""
        clean_title = (title or "").strip()
        body_desc = (description or "").strip()

        # Clean tags
        clean_tags = []
        default_reel_tags = ["#Reels", "#FacebookReels", "#ViralReels", "#Trending", "#Facts", "#HindiReels"]

        if tags:
            for t in tags:
                t_str = str(t).strip()
                if not t_str.startswith("#"):
                    t_str = f"#{t_str}"
                if t_str.lower() not in [x.lower() for x in clean_tags]:
                    clean_tags.append(t_str)

        for d_tag in default_reel_tags:
            if d_tag.lower() not in [x.lower() for x in clean_tags]:
                clean_tags.append(d_tag)

        # Assemble caption
        parts = []
        if clean_title:
            parts.append(clean_title)

        import re
        if body_desc and body_desc != clean_title:
            # Strip YouTube-specific subscribe appeals from Facebook Reel body
            cleaned_desc = re.sub(
                r"(चैनल को सब्सक्राइब|चैनल को subscribe|subscribe to (the )?channel|subscribe करें)[^.!?\n]*[.!?]?",
                "",
                body_desc,
                flags=re.IGNORECASE,
            ).strip()
            # If description has multiple paragraphs, keep it concise for Reel
            short_desc = cleaned_desc[:350].strip()
            if short_desc:
                parts.append(f"\n{short_desc}")

        # Facebook follow CTA (Guaranteed Ending Follow Hook)
        p_name = self.load_credentials().get("page_name", "CosmoCronicle")
        follow_hook = f"👉 ऐसे ही रोंगटे खड़े कर देने वाले रहस्यों और अनसुने तथ्यों के लिए अभी @{p_name} पेज को FOLLOW करें! 🔔✨"
        if not any("FOLLOW" in p or "फॉलो करें" in p for p in parts):
            parts.append(f"\n{follow_hook}")

        # Tags line
        tags_line = " ".join(clean_tags[:10])
        parts.append(f"\n{tags_line}")

        return "\n".join(parts).strip()

    def _record_publish(
        self,
        video_id: str,
        post_id: str,
        title: str,
        caption: str,
        reel_url: str,
        video_filename: str,
    ) -> None:
        """Record published Reel details in history."""
        try:
            records = []
            if self.history_path.exists():
                with open(self.history_path, "r", encoding="utf-8") as f:
                    records = json.load(f)
                    if not isinstance(records, list):
                        records = []

            records.insert(
                0,
                {
                    "video_id": video_id,
                    "post_id": post_id,
                    "title": title,
                    "reel_url": reel_url,
                    "video_filename": video_filename,
                    "published_at": int(time.time()),
                    "published_date": time.strftime("%Y-%m-%d %H:%M:%S"),
                },
            )

            # Keep last 100 records
            records = records[:100]

            with open(self.history_path, "w", encoding="utf-8") as f:
                json.dump(records, f, indent=2)
        except Exception as e:
            logger.warning(f"Could not record Facebook publish history: {e}")

    def get_published_history(self) -> List[Dict[str, Any]]:
        """Retrieve history of Reels published through AutoTube."""
        if not self.history_path.exists():
            return []
        try:
            with open(self.history_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                return data if isinstance(data, list) else []
        except Exception:
            return []
