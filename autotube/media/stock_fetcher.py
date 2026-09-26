"""Stock media fetcher supporting Pexels, Pixabay, and local assets."""

import os
from pathlib import Path
from typing import List, Optional
import requests
from autotube.config import get_config
from autotube.utils.console import print_error, print_info, print_success, print_warning
from autotube.utils.file_utils import sanitize_filename


class StockFetcher:
    """Fetches royalty-free stock videos and images for scenes."""

    def __init__(self, pexels_key: Optional[str] = None):
        cfg = get_config()
        self.pexels_key = pexels_key or cfg.pexels_api_key or os.getenv("PEXELS_API_KEY")

    def search_and_download_video(
        self,
        query: str,
        output_dir: Path,
        orientation: str = "portrait",  # portrait (9:16) or landscape (16:9)
        min_duration: int = 5,
    ) -> Optional[Path]:
        """Search Pexels for a video matching query and download it."""
        if not self.pexels_key:
            print_warning(
                "PEXELS_API_KEY not configured. Skipping stock video fetch."
            )
            return None

        headers = {"Authorization": self.pexels_key}
        url = f"https://api.pexels.com/videos/search?query={requests.utils.quote(query)}&orientation={orientation}&per_page=5"

        try:
            print_info(f"Searching stock footage on Pexels for: '{query}' ({orientation})...")
            resp = requests.get(url, headers=headers, timeout=15)
            if resp.status_code != 200:
                print_error(f"Pexels API error {resp.status_code}: {resp.text}")
                return None

            data = resp.json()
            videos = data.get("videos", [])
            if not videos:
                print_warning(f"No stock video found for query: '{query}'")
                return None

            # Pick first video with suitable duration and resolution
            video_files = videos[0].get("video_files", [])
            # Sort by width/height descending (HD preferably)
            sorted_files = sorted(
                video_files,
                key=lambda x: (x.get("width", 0) * x.get("height", 0)),
                reverse=True,
            )

            # Prefer 1080p / 720p
            target_file = None
            for vf in sorted_files:
                if vf.get("quality") in ["hd", "sd"] and vf.get("link"):
                    target_file = vf
                    break
            if not target_file and sorted_files:
                target_file = sorted_files[0]

            if not target_file:
                return None

            download_url = target_file["link"]
            file_name = f"stock_{sanitize_filename(query)}_{videos[0]['id']}.mp4"
            target_path = output_dir / file_name

            if target_path.exists() and target_path.stat().st_size > 0:
                return target_path

            print_info(f"Downloading video: {file_name}...")
            with requests.get(download_url, stream=True, timeout=30) as r:
                r.raise_for_status()
                with open(target_path, "wb") as f:
                    for chunk in r.iter_content(chunk_size=65536):
                        f.write(chunk)

            print_success(f"Stock video downloaded: {target_path.name}")
            return target_path

        except Exception as e:
            print_error(f"Failed to fetch stock video: {e}")
            return None
