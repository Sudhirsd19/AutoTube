import sys
from autotube.uploader.auth import YouTubeAuth
from googleapiclient.discovery import build

video_id = sys.argv[1] if len(sys.argv) > 1 else "v1Lebapgzdg"
creds = YouTubeAuth().get_credentials()
yt = build("youtube", "v3", credentials=creds)

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
