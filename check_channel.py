from autotube.uploader.auth import YouTubeAuth
from googleapiclient.discovery import build

creds = YouTubeAuth().get_credentials()
yt = build("youtube", "v3", credentials=creds)

res = yt.channels().list(part="snippet,contentDetails", mine=True).execute()
for item in res.get("items", []):
    print("Channel Title:", item["snippet"]["title"])
    print("Channel ID:", item["id"])
    print("Custom URL:", item["snippet"].get("customUrl", "N/A"))

# Check recent uploaded videos
print("\n--- Recent Uploaded Videos ---")
v_res = yt.search().list(part="snippet", forMine=True, type="video", maxResults=10).execute()
for v in v_res.get("items", []):
    vid = v["id"]["videoId"]
    title = v["snippet"]["title"]
    published = v["snippet"]["publishedAt"]
    
    # Get privacy status
    status_res = yt.videos().list(part="status,snippet", id=vid).execute()
    status = "unknown"
    if status_res.get("items"):
        status = status_res["items"][0]["status"]["privacyStatus"]
    
    print(f"- [{status.upper()}] https://youtu.be/{vid} -> '{title}' ({published})")
