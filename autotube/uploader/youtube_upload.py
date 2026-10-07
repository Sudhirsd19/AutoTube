"""YouTube video upload manager using YouTube Data API v3."""

import json
from datetime import datetime
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
        self.last_error: Optional[str] = None

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
        chapters: Optional[List[tuple]] = None,
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

        is_short = "#Shorts" in title or (tags and "#Shorts" in tags)
        if is_short:
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
        else:
            base_viral_tags = [
                "Documentary",
                "Full Documentary",
                "Sci-Fi",
                "History",
                "Space Mysteries",
                "Science",
                "Cosmic",
                "Universe",
            ]
        clean_tags = list(dict.fromkeys((tags or []) + base_viral_tags))

        # Check latest longform documentary for Shorts-to-Long Funnel cross-promotion
        latest_long = None
        latest_long_file = Path("config/latest_longform_video.json")
        if latest_long_file.exists():
            try:
                latest_long = json.loads(latest_long_file.read_text(encoding="utf-8"))
            except Exception:
                pass

        funnel_desc = ""
        funnel_pin = ""
        if is_short and latest_long and latest_long.get("video_url"):
            l_url = latest_long["video_url"]
            l_title = latest_long.get("title", "Full Documentary")
            funnel_desc = (
                f"\n🎬 MUST WATCH FULL 16:9 DOCUMENTARY:\n"
                f"👉 {l_title}\n"
                f"🔗 {l_url}\n"
            )
            funnel_pin = f"\n\n🎬 Watch Full 16:9 Documentary: {l_url}"

        # Automatic Interactive YouTube Chapters for Long Videos
        chapters_block = ""
        if not is_short and chapters:
            chapter_lines = ["\n📌 CHAPTERS / TIMESTAMPS:"]
            for sec, ch_name in chapters:
                m, s = divmod(int(sec), 60)
                chapter_lines.append(f"{m:02d}:{s:02d} - {ch_name}")
            chapters_block = "\n".join(chapter_lines) + "\n"

        # Ensure 1-click subscription link and engagement CTA in description
        channel_handle = "@cosmochro"
        sub_link = f"https://www.youtube.com/{channel_handle}?sub_confirmation=1"
        sub_cta_block = (
            "\n\n"
            + chapters_block
            + funnel_desc
            + "🔔 SUBSCRIBE for Daily Cosmic Mysteries & Mind-Blowing Facts:\n"
            f"👉 {sub_link}\n\n"
            "💬 Which revelation shocked you the most? Drop your comment below!\n"
            "⚡ Share this video with a friend who loves science & mysteries!\n\n"
            f"{'#Shorts ' if is_short else ''}#AlienInterview #Documentary #SpaceMysteries #Trending #Viral"
        )
        if "sub_confirmation=1" not in description:
            full_description = (description.rstrip() + sub_cta_block)[:5000]
        else:
            full_description = description[:5000]

        # Optimize pinned comment with high-engagement question + funnel link + 1-click auto-subscribe link
        if pinned_comment:
            if "sub_confirmation=1" not in pinned_comment:
                effective_pinned_comment = f"{pinned_comment.strip()}{funnel_pin}\n\n👉 Subscribe to {channel_handle} for more:\n{sub_link}"
            else:
                effective_pinned_comment = f"{pinned_comment.strip()}{funnel_pin}"
        else:
            effective_pinned_comment = (
                "🔥 What do you think is the real truth? Type 1 or Type 2 below! 👇\n"
                f"{funnel_pin}\n"
                f"👉 Subscribe to {channel_handle} for more deep mysteries:\n{sub_link}"
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

            # Record latest longform video for future Shorts funnel cross-promotion
            if not is_short and video_id:
                try:
                    latest_long_file = Path("config/latest_longform_video.json")
                    latest_long_file.parent.mkdir(parents=True, exist_ok=True)
                    latest_long_file.write_text(
                        json.dumps(
                            {
                                "video_id": video_id,
                                "video_url": video_url,
                                "title": title,
                                "uploaded_at": datetime.now().isoformat(),
                            },
                            indent=2,
                            ensure_ascii=False,
                        ),
                        encoding="utf-8",
                    )
                    print_info(f"Recorded latest longform video for Shorts funnel: {video_id}")
                except Exception as se:
                    print_warning(f"Could not save latest longform video info: {se}")

            return video_url

        except HttpError as e:
            err_text = str(e)
            if "uploadLimitExceeded" in err_text:
                self.last_error = "YouTube Daily Upload Limit Exceeded! Your channel reached its daily limit of video uploads (~6-10 per day). YouTube will reset this limit in 24 hours."
            elif "quotaExceeded" in err_text:
                self.last_error = "YouTube API Quota Exceeded for today (10,000 units/day). Limit resets at midnight Pacific Time."
            else:
                self.last_error = f"YouTube API Error: {e}"
            print_error(f"YouTube API HTTP error: {e}")
            return None
        except Exception as e:
            self.last_error = f"Upload failed: {e}"
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
