"""NASA Image and Video Library integration.

Uses NASA's public Images API without requiring an API key. Search results are
restricted to video media and only direct playable video assets are returned.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List

import requests

NASA_SEARCH_URL = "https://images-api.nasa.gov/search"
HTTP_HEADERS = {
    "User-Agent": "AutoTube/1.0 (educational media pipeline; +https://github.com/Sudhirsd19/AutoTube)",
}


class NasaMediaFetcher:
    """Fetch free-to-access NASA video assets from the public Images API."""

    def __init__(self, timeout: int = 12) -> None:
        self.timeout = timeout
        self.enabled = True

    def is_configured(self) -> bool:
        """NASA's public Images API does not require an API key."""
        return self.enabled

    def search_videos(self, query: str, limit: int = 4) -> List[Dict[str, Any]]:
        clean_q = re.sub(r"[^a-zA-Z0-9\s]", " ", query).strip()
        if not clean_q:
            return []

        results: List[Dict[str, Any]] = []
        seen: set[str] = set()

        try:
            response = requests.get(
                NASA_SEARCH_URL,
                params={
                    "q": clean_q,
                    "media_type": "video",
                    "page": 1,
                    "page_size": max(1, min(limit, 10)),
                },
                headers=HTTP_HEADERS,
                timeout=self.timeout,
            )
            response.raise_for_status()
            payload = response.json()
        except Exception:
            return []

        for item in payload.get("collection", {}).get("items", []):
            data_rows = item.get("data") or []
            if not data_rows:
                continue
            meta = data_rows[0] or {}
            nasa_id = str(meta.get("nasa_id") or "").strip()
            if not nasa_id or nasa_id in seen:
                continue

            media_url = self._extract_video_url(item.get("links") or [])
            if not media_url:
                continue

            seen.add(nasa_id)
            title = str(meta.get("title") or nasa_id).strip()
            description = str(meta.get("description") or "").strip()
            tags = [
                token.lower()
                for token in re.findall(r"[A-Za-z0-9]{3,}", f"{title} {description}")[:40]
            ]

            results.append(
                {
                    "id": f"nasa_{nasa_id}",
                    "source": "NASA",
                    "title": title,
                    "tags": tags + ["nasa", "space", "science"],
                    "description": description[:500],
                    "download_url": media_url,
                    "is_vertical": False,
                    "aspect_ratio": "16:9",
                    "license_source": "NASA Images and Media",
                    "source_url": f"https://images.nasa.gov/details/{nasa_id}",
                }
            )
            if len(results) >= limit:
                break

        return results

    @staticmethod
    def _extract_video_url(links: List[Dict[str, Any]]) -> str:
        preferred: List[str] = []
        fallback: List[str] = []

        for link in links:
            href = str(link.get("href") or "").strip()
            if not href or not href.startswith(("http://", "https://")):
                continue
            rel = str(link.get("rel") or "").lower()
            render = str(link.get("render") or "").lower()
            mime = str(link.get("mime_type") or link.get("mimeType") or "").lower()
            lowered = href.lower()

            is_video = (
                "video/" in mime
                or lowered.endswith((".mp4", ".m4v", ".webm", ".mov"))
                or render == "video"
            )
            if not is_video:
                continue

            if rel == "preview" or "preview" in lowered:
                preferred.append(href)
            else:
                fallback.append(href)

        return (preferred or fallback or [""])[0]
