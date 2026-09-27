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
        pinned_comment: Optional[str] = None,
    ) -> Optional[str]:
        """Upload video file to YouTube with metadata, optional thumbnail and auto engagement comment."""
        if not video_path.exists():
            print_error(f"Video file not found: {video_path}")
            return None

        creds = self.auth.get_credentials()
        if not creds:
            print_error("Cannot upload: YouTube authentication credentials missing.")
            return None

        privacy = privacy_status or self.cfg.youtube.default_privacy
        category = category_id or self.cfg.youtube.default_category

        # Ensure high-traffic SEO tags
        base_viral_tags = [
            "Shorts",
            "YouTube Shorts",
            "Viral",
            "Trending",
            "Space",
            "Science Facts",
            "Mind Blowing",
            "Mysteries",
            "Universe",
        ]
        clean_tags = list(dict.fromkeys((tags or []) + base_viral_tags))

        # Ensure 1-click subscription link and engagement CTA in description
        sub_cta_block = (
            "\n\n"
            "🔔 SUBSCRIBE for Daily Cosmic Mysteries & Mind-Blowing Facts:\n"
            "👉 https://www.youtube.com/@skd_animate?sub_confirmation=1\n\n"
            "💬 Which theory shocked you the most? Drop your comment below!\n"
            "⚡ Share this with a friend who loves science & mysteries!\n\n"
            "#Shorts #SpaceFacts #Mystery #Trending #Viral"
        )
        if "sub_confirmation=1" not in description:
            full_description = (description.rstrip() + sub_cta_block)[:5000]
        else:
            full_description = description[:5000]

        # Optimize pinned comment with high-engagement question + 1-click auto-subscribe link
        sub_link = "https://www.youtube.com/@skd_animate?sub_confirmation=1"
        if pinned_comment:
            if "sub_confirmation=1" not in pinned_comment:
                effective_pinned_comment = f"{pinned_comment.strip()}\n\n👉 Subscribe to @skd_animate for Part 2:\n{sub_link}"
            else:
                effective_pinned_comment = pinned_comment
        else:
            effective_pinned_comment = (
                "🔥 Which mystery shocked you the most? Comment below! 👇\n"
                f"👉 Subscribe to @skd_animate for Part 2 releasing today:\n{sub_link}"
            )

        # If scheduling release, privacy status must be 'private'
        if publish_at:
            privacy = "private"

        body = {
            "snippet": {
                "title": title[:100],  # YouTube title limit is 100 chars
                "description": full_description,
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

            # Auto-post engagement comment
            if effective_pinned_comment:
                self.post_comment(video_id=video_id, comment_text=effective_pinned_comment)

            return video_url

        except HttpError as e:
            print_error(f"YouTube API HTTP error: {e}")
            return None
        except Exception as e:
            print_error(f"Upload failed: {e}")
            return None

    def post_comment(self, video_id: str, comment_text: str) -> bool:
        """Post a top-level creator comment to maximize user engagement and comments signal."""
        creds = self.auth.get_credentials()
        if not creds:
            return False

        try:
            youtube = build("youtube", "v3", credentials=creds)
            print_info(f"Posting engagement question on video {video_id}...")
            youtube.commentThreads().insert(
                part="snippet",
                body={
                    "snippet": {
                        "videoId": video_id,
                        "topLevelComment": {
                            "snippet": {
                                "textOriginal": comment_text,
                            }
                        },
                    }
                },
            ).execute()
            print_success("Creator engagement comment posted successfully!")
            return True
        except Exception as e:
            print_warning(f"Could not post creator comment: {e}")
            return False
