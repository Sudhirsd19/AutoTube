"""YouTube video upload manager using YouTube Data API v3."""

from pathlib import Path
from typing import List, Optional
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaFileUpload
from autotube.config import get_config
from autotube.uploader.auth import YouTubeAuth
from autotube.utils.console import print_error, print_info, print_success, print_warning


class YouTubeUploader:
    """Uploads videos and sets thumbnails and metadata on YouTube."""

    def __init__(self, auth: Optional[YouTubeAuth] = None):
        self.auth = auth or YouTubeAuth()
        self.cfg = get_config()

    def upload_video(
        self,
        video_path: Path,
        title: str,
        description: str,
        tags: Optional[List[str]] = None,
        privacy_status: Optional[str] = None,
        category_id: Optional[str] = None,
        publish_at: Optional[str] = None,
        thumbnail_path: Optional[Path] = None,
    ) -> Optional[str]:
        """Upload video file to YouTube with metadata and optional thumbnail."""
        if not video_path.exists():
            print_error(f"Video file not found: {video_path}")
            return None

        creds = self.auth.get_credentials()
        if not creds:
            print_error("Cannot upload: YouTube authentication credentials missing.")
            return None

        privacy = privacy_status or self.cfg.youtube.default_privacy
        category = category_id or self.cfg.youtube.default_category
        clean_tags = tags or ["AutoTube", "AI"]

        # If scheduling release, privacy status must be 'private'
        if publish_at:
            privacy = "private"

        body = {
            "snippet": {
                "title": title[:100],  # YouTube title limit is 100 chars
                "description": description[:5000],
                "tags": clean_tags[:500],
                "categoryId": str(category),
            },
            "status": {
                "privacyStatus": privacy,
                "selfDeclaredMadeForKids": False,
            },
        }

        if publish_at:
            body["status"]["publishAt"] = publish_at

        try:
            youtube = build("youtube", "v3", credentials=creds)
            print_info(f"Starting upload for '{video_path.name}' ({privacy} mode)...")

            media = MediaFileUpload(
                str(video_path),
                chunksize=1024 * 1024 * 4,  # 4MB chunks
                resumable=True,
            )

            insert_request = youtube.videos().insert(
                part=",".join(body.keys()),
                body=body,
                media_body=media,
            )

            response = None
            while response is None:
                status, response = insert_request.next_chunk()
                if status:
                    percent = int(status.progress() * 100)
                    print_info(f"Upload progress: {percent}%")

            video_id = response.get("id")
            video_url = f"https://youtu.be/{video_id}"
            print_success(f"Video successfully uploaded! URL: {video_url}")

            # Upload custom thumbnail if provided
            if thumbnail_path and thumbnail_path.exists():
                print_info(f"Uploading custom thumbnail: {thumbnail_path.name}...")
                try:
                    thumb_media = MediaFileUpload(str(thumbnail_path))
                    youtube.thumbnails().set(
                        videoId=video_id,
                        media_body=thumb_media,
                    ).execute()
                    print_success("Thumbnail uploaded successfully!")
                except Exception as te:
                    print_warning(f"Could not set custom thumbnail: {te}")

            return video_url

        except HttpError as e:
            print_error(f"YouTube API HTTP error: {e}")
            return None
        except Exception as e:
            print_error(f"Upload failed: {e}")
            return None
