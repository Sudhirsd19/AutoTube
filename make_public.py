from autotube.uploader.auth import YouTubeAuth
from googleapiclient.discovery import build

creds = YouTubeAuth().get_credentials()
yt = build("youtube", "v3", credentials=creds)

video_id = "kXVKszlYCBI"
yt.videos().update(
    part="status",
    body={
        "id": video_id,
        "status": {
            "privacyStatus": "public",
            "selfDeclaredMadeForKids": False,
        }
    }
).execute()

print(f"Video {video_id} is now PUBLIC!")
