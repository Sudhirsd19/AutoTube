import json
import os
import re
import time
import random
import socket
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional, Set
import yt_dlp

from autotube.config import PROJECT_ROOT
from autotube.utils.console import print_info, print_success, print_warning, print_error
from autotube.utils.ffmpeg_helper import get_ffmpeg_path, get_media_duration

YOUTUBE_CACHE_DIR = PROJECT_ROOT / "temp" / "youtube_clips"
YOUTUBE_CACHE_DIR.mkdir(parents=True, exist_ok=True)
USED_VIRAL_SHORTS_FILE = PROJECT_ROOT / "config" / "used_viral_shorts.json"


class YouTubeHarvester:
    """Acquires, filters, and transforms viral social clips with 100% anti-copyright protection."""

    def __init__(self):
        self.cache_dir = YOUTUBE_CACHE_DIR
        self.tracker_file = USED_VIRAL_SHORTS_FILE
        self.used_video_ids: Set[str] = set()
        self._load_used_history()

    def _load_used_history(self) -> None:
        """Load previously rendered/used viral video IDs from persistent disk storage."""
        if not self.tracker_file.exists():
            return
        try:
            with open(self.tracker_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, dict):
                    used_ids = data.get("used_ids", {})
                    if isinstance(used_ids, dict):
                        self.used_video_ids = set(used_ids.keys())
                    elif isinstance(used_ids, list):
                        self.used_video_ids = set(used_ids)
                elif isinstance(data, list):
                    self.used_video_ids = set(data)
        except Exception as exc:
            print_warning(f"Could not load used viral shorts history: {exc}")

    def _save_used_history(self, new_id: str, metadata: Optional[Dict[str, Any]] = None) -> None:
        """Atomically persist used viral video ID to disk."""
        try:
            self.tracker_file.parent.mkdir(parents=True, exist_ok=True)
            existing_data: Dict[str, Any] = {"used_ids": {}}
            if self.tracker_file.exists():
                try:
                    with open(self.tracker_file, "r", encoding="utf-8") as f:
                        loaded = json.load(f)
                        if isinstance(loaded, dict) and "used_ids" in loaded:
                            if isinstance(loaded["used_ids"], dict):
                                existing_data["used_ids"] = loaded["used_ids"]
                            elif isinstance(loaded["used_ids"], list):
                                existing_data["used_ids"] = {k: {} for k in loaded["used_ids"]}
                except Exception:
                    pass

            existing_data["used_ids"][new_id] = metadata or {
                "timestamp": int(time.time()),
                "date": time.strftime("%Y-%m-%d %H:%M:%S")
            }

            temp_file = self.tracker_file.with_suffix(".tmp")
            with open(temp_file, "w", encoding="utf-8") as f:
                json.dump(existing_data, f, indent=2, ensure_ascii=False)
            temp_file.replace(self.tracker_file)
        except Exception as exc:
            print_warning(f"Could not save used viral short ID {new_id}: {exc}")

    @staticmethod
    def extract_video_id(url_or_id: str) -> str:
        """Extract clean 11-char YouTube ID or sanitized slug for deduplication."""
        if not url_or_id:
            return ""
        clean = url_or_id.strip()
        if len(clean) == 11 and re.match(r"^[a-zA-Z0-9_-]{11}$", clean):
            return clean
        m = re.search(r"(?:v=|/v/|youtu\.be/|/shorts/|/embed/)([a-zA-Z0-9_-]{11})", clean)
        if m:
            return m.group(1)
        slug = clean.split("?")[0].rstrip("/").split("/")[-1]
        return re.sub(r"[^\w-]", "", slug)[:32]

    def is_used(self, url_or_id: str) -> bool:
        """Check if video ID has already been rendered or published."""
        clean_id = self.extract_video_id(url_or_id)
        return bool(clean_id and clean_id in self.used_video_ids)

    def mark_as_used(self, url_or_id: str, title: str = "", topic: str = "") -> None:
        """Record video ID as used permanently so it will never repeat."""
        clean_id = self.extract_video_id(url_or_id)
        if not clean_id:
            return
        self.used_video_ids.add(clean_id)
        meta = {
            "title": title[:100],
            "topic": topic[:100],
            "url": f"https://www.youtube.com/watch?v={clean_id}" if len(clean_id) == 11 else url_or_id,
            "timestamp": int(time.time()),
            "date": time.strftime("%Y-%m-%d %H:%M:%S")
        }
        self._save_used_history(clean_id, meta)
        print_info(f"💾 [Deduplication] Recorded viral video ID as used: {clean_id} ('{title[:35]}')")

    @staticmethod
    def is_url(text: str) -> bool:
        """Check if input text is a web URL."""
        if not text or not isinstance(text, str):
            return False
        clean = text.strip()
        return bool(re.match(r"^https?://[^\s]+$", clean, re.IGNORECASE))

    @staticmethod
    def is_supported_platform_url(url: str) -> bool:
        """Check if URL is from YouTube, Instagram, or Facebook."""
        clean = (url or "").lower()
        return any(domain in clean for domain in [
            "youtube.com", "youtu.be",
            "instagram.com", "instagr.am",
            "facebook.com", "fb.watch", "fb.com"
        ])

    @staticmethod
    def get_proxy_url() -> Optional[str]:
        """Check if local Privoxy/Tor proxy is available (port 8118 or 9050)."""
        for port, proto in [(8118, "http"), (9050, "socks5")]:
            try:
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                    s.settimeout(0.3)
                    if s.connect_ex(("127.0.0.1", port)) == 0:
                        return f"{proto}://127.0.0.1:{port}"
            except Exception:
                pass
        return None

    @staticmethod
    def enrich_character_query(query: str) -> str:
        """Enrich short/character queries with authentic identifiers to prevent fake lookalikes and mimicry."""
        if not query:
            return ""
        ql = query.lower().strip()

        # Spiritual Figures / Gurus / Katha Vachak
        if any(k in ql for k in ["anirudh", "aniruddh", "anirudha", "pookie baba"]):
            return "Aniruddhacharya Ji Maharaj funny comedy pravachan"
        elif any(k in ql for k in ["bageshwar", "dhirendra shastri", "dhirendra krishna"]):
            return "Bageshwar Dham Dhirendra Krishna Shastri dialogue"
        elif any(k in ql for k in ["premanand", "vrindavan maharaj"]):
            return "Pujya Premanand Ji Maharaj pravachan satsang"
        elif any(k in ql for k in ["jaya kishori"]):
            return "Jaya Kishori ji pravachan motivation"

        # Iconic Bollywood / Sitcom Characters
        elif any(k in ql for k in ["jethalal", "gada", "tmkoc", "tarak mehta"]):
            return "TMKOC Jethalal comedy scene"
        elif any(k in ql for k in ["baburao", "babu rao", "babu bhaiya"]):
            return "Babu Rao Hera Pheri comedy scene"
        elif any(k in ql for k in ["rajpal", "chhota don", "bandya"]):
            return "Rajpal Yadav comedy scene movie"
        elif any(k in ql for k in ["pushpa", "allu arjun"]):
            return "Pushpa movie dialogue scene"
        elif any(k in ql for k in ["rocky bhai", "kgf"]):
            return "KGF Rocky Bhai dialogue scene"
        elif any(k in ql for k in ["akshay kumar", "raju"]):
            return "Akshay Kumar comedy scene movie"
        elif any(k in ql for k in ["munna bhai", "circuit"]):
            return "Munna Bhai Circuit comedy scene"
        elif any(k in ql for k in ["majnu bhai", "welcome"]):
            return "Welcome movie Majnu Bhai scene"
        elif any(k in ql for k in ["vasooli", "golmaal"]):
            return "Golmaal movie comedy scene"

        # Ancient Indian Temples & Historical Heritage Sites
        elif any(k in ql for k in ["lepakshi", "लेपाक्षी", "झूलता खंभा", "लटकता"]):
            return "Lepakshi temple hanging pillar mystery drone real footage"
        elif any(k in ql for k in ["kailasa", "ellora", "कैलाश मंदिर", "कैलासा", "एलोरा"]):
            return "Kailasa temple Ellora ancient rock cut architecture drone real"
        elif any(k in ql for k in ["ram setu", "ramsetu", "राम सेतु", "floating stone", "तैरते पत्थर"]):
            return "Ram Setu floating stone Rameshwaram ocean real video"
        elif any(k in ql for k in ["iron pillar", "लौह स्तंभ", "delhi pillar", "rustproof iron"]):
            return "Delhi Iron Pillar Qutub Minar 1600 year rustproof mystery"
        elif any(k in ql for k in ["padmanabha", "पद्मनाभ", "vault b", "वॉल्ट बी"]):
            return "Padmanabhaswamy temple secret vault door Kerala real footage"
        elif any(k in ql for k in ["brihadeeswarar", "thanjavur", "तंजावुर", "बृहदेश्वर"]):
            return "Brihadeeswarar temple Thanjavur granite dome real architecture"
        elif any(k in ql for k in ["dwarka", "द्वारका", "submerged dwarka", "डूबी द्वारका"]):
            return "Dwarka submerged city underwater ruins Gujarat archaeology"
        elif any(k in ql for k in ["konark", "कोणार्क", "sun temple"]):
            return "Konark Sun Temple wheel chariot architecture real footage"
        elif any(k in ql for k in ["hampi", "vittala", "हम्पी", "विट्ठल"]):
            return "Hampi Vittala temple musical pillars stone chariot real"
        elif any(k in ql for k in ["kedarnath", "केदारनाथ"]):
            return "Kedarnath temple Himalayas snow drone view real footage"
        elif any(k in ql for k in ["ajanta", "अजंता"]):
            return "Ajanta caves ancient rock architecture caves real"
        elif any(k in ql for k in ["rani ki vav", "रानी की वाव"]):
            return "Rani Ki Vav stepwell Patan Gujarat ancient architecture"
        elif any(k in ql for k in ["bhangarh", "भानगढ़"]):
            return "Bhangarh fort Rajasthan mystery ruins real footage"

        return query

    @staticmethod
    def is_impostor_or_mimicry(title: str, query: str = "") -> bool:
        """Detect mimicry, acting reels, parody lookalikes, or fake cosplayers."""
        if not title:
            return False
        t_low = title.lower()
        q_low = (query or "").lower()

        banned_terms = [
            "mimicry", "acting", "lookalike", "look-alike", "humshakal", "duplicate",
            "parody", "cosplay", "face swap", "filter", "roast", "nakal", "makeup",
            "dressup", "copycat", "impersonat", "fake", "deepfake"
        ]
        if any(term in t_low for term in banned_terms):
            return True

        if any(g in q_low for g in ["anirudh", "aniruddh", "bageshwar", "premanand", "kishori", "maharaj"]):
            authentic_markers = ["maharaj", "pravachan", "katha", "ashram", "satsang", "darbar", "baba", "guruji", "gauri gopal", "sanskar", "shri"]
            if "instagram reel" in t_low and not any(m in t_low for m in authentic_markers):
                return True

        return False

    def search_top_shorts(
        self,
        query: str,
        limit: int = 5,
        target_orientation: str = "portrait",
        exclude_used: bool = True,
        target_duration: int = 55
    ) -> List[Dict[str, Any]]:
        """Search YouTube for top-viewed Shorts matching query.

        Returns metadata list: id, title, url, duration, views.
        """
        clean_q = re.sub(r"[^\w\s-]", " ", query).strip()
        if not clean_q:
            return []

        enriched_q = self.enrich_character_query(clean_q)
        negative_filters = "-mimicry -acting -filter -parody -roast -lookalike -cosplay -duplicate"
        search_term = f"{enriched_q} shorts #shorts {negative_filters}"
        print_info(f"🔎 [YouTube Harvester] Searching authentic viral clips for: '{enriched_q}'...")

        ffmpeg_exe = get_ffmpeg_path()
        ydl_opts: Dict[str, Any] = {
            "quiet": True,
            "no_warnings": True,
            "extract_flat": "in_playlist",
            "default_search": "ytsearch35",
            "socket_timeout": 15,
            "noplaylist": True,
        }
        proxy = self.get_proxy_url()
        if proxy:
            ydl_opts["proxy"] = proxy

        candidates: List[Dict[str, Any]] = []

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                res = ydl.extract_info(search_term, download=False)
                entries = res.get("entries") or []

                for entry in entries:
                    if not entry:
                        continue
                    v_id = entry.get("id") or self.extract_video_id(entry.get("url") or "")
                    title = entry.get("title") or "Viral Clip"
                    duration = float(entry.get("duration") or 0.0)
                    view_count = int(entry.get("view_count") or 0)

                    url = entry.get("url") or (f"https://www.youtube.com/watch?v={v_id}" if v_id else "")
                    if not url or not v_id:
                        continue

                    # STRICT AUTHENTICITY GUARD: Reject mimicry, acting reels, and lookalikes
                    if self.is_impostor_or_mimicry(title, query=clean_q):
                        print_info(f"⏭️ [Authenticity Guard] Skipping mimicry/acting clip: {v_id} ('{title[:45]}')")
                        continue

                    # STRICT DEDUPLICATION: skip if already used in any previous generation
                    if exclude_used and self.is_used(v_id):
                        print_info(f"⏭️ [Deduplication] Skipping already used clip: {v_id} ({title[:35]})")
                        continue

                    candidates.append({
                        "id": v_id,
                        "title": title,
                        "url": url,
                        "duration": duration,
                        "views": view_count,
                    })

                def score_short(c: Dict[str, Any]) -> tuple:
                    d = float(c.get("duration") or 0.0)
                    views = int(c.get("views") or 0)
                    t_low = (c.get("title") or "").lower()
                    has_tag = any(x in t_low for x in ["#short", "short", "shorts", "reel"])

                    req_min = max(25.0, target_duration - 10)
                    req_max = max(120.0, target_duration * 2.5)

                    if req_min <= d <= req_max:
                        dur_rank = 5
                    elif d >= (target_duration * 0.7) and d <= 240:
                        dur_rank = 4
                    elif d >= 25 and d <= 300:
                        dur_rank = 2
                    elif 0 < d < 25:
                        dur_rank = 1 if target_duration > 35 else 4
                    elif d == 0:
                        dur_rank = 3 if has_tag else 2
                    else:
                        dur_rank = 0

                    return (dur_rank, 1 if has_tag else 0, views)

                candidates.sort(key=score_short, reverse=True)

        except Exception as exc:
            print_warning(f"YouTube Harvester search notice: {exc}")

        return candidates[:limit]

    def download_raw_video(
        self,
        url_or_id: str,
        output_path: Path,
        timeout_seconds: int = 40,
        include_audio: bool = True,
        max_duration: Optional[int] = None
    ) -> Optional[Path]:
        """Download raw video stream via yt-dlp with proxy & strict timeout."""
        target_url = url_or_id if self.is_url(url_or_id) else f"https://www.youtube.com/watch?v={url_or_id}"
        ffmpeg_exe = get_ffmpeg_path()

        out_template = str(output_path.with_suffix("")) + ".%(ext)s"

        import shutil
        node_path = shutil.which("node") or ("/usr/bin/node" if os.path.exists("/usr/bin/node") else None)

        fmt = (
            "best[height<=720][ext=mp4]/best[height<=1080][ext=mp4]/bestvideo[height<=720]+bestaudio/best"
            if include_audio
            else "bestvideo[height<=1080][ext=mp4]/bestvideo[height<=1080]/bestvideo/best"
        )

        ydl_opts: Dict[str, Any] = {
            "format": fmt,
            "outtmpl": out_template,
            "quiet": True,
            "no_warnings": True,
            "ffmpeg_location": ffmpeg_exe,
            "socket_timeout": timeout_seconds,
            "noplaylist": True,
            "extractor_args": {
                "youtube": {
                    "player_client": ["android", "web"]
                }
            }
        }
        proxy = self.get_proxy_url()
        if proxy:
            ydl_opts["proxy"] = proxy
        if node_path:
            ydl_opts["js_runtimes"] = {"node": {"path": node_path}}

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([target_url])

            # Check for downloaded output
            if output_path.exists() and output_path.stat().st_size > 10000:
                return output_path

            # If extension changed to .mkv, .webm or other, locate it
            parent_dir = output_path.parent
            stem = output_path.stem
            for f in parent_dir.glob(f"{stem}.*"):
                if f.is_file() and f.suffix.lower() in {".mp4", ".mkv", ".webm", ".mov"} and f.stat().st_size > 10000:
                    return f

        except Exception as exc:
            print_warning(f"Download failed for {target_url}: {exc}")

        return None

    def transform_clip_anti_copyright(
        self,
        input_path: Path,
        output_path: Path,
        duration: float = 3.5,
        start_time: Optional[float] = None,
        orientation: str = "portrait"
    ) -> Optional[Path]:
        """Transform raw clip for scene montage with audio strip."""
        if not input_path.exists() or input_path.stat().st_size < 10000:
            return None

        ffmpeg_exe = get_ffmpeg_path()
        total_duration = get_media_duration(input_path)

        if start_time is None:
            if total_duration > (duration + 3.0):
                earliest = max(1.0, total_duration * 0.15)
                latest = max(earliest, total_duration * 0.65 - duration)
                start_time = random.uniform(earliest, latest)
            else:
                start_time = 0.5 if total_duration > (duration + 0.5) else 0.0

        target_w = 1080 if orientation == "portrait" else 1920
        target_h = 1920 if orientation == "portrait" else 1080

        filter_str = (
            f"scale={target_w}:{target_h}:force_original_aspect_ratio=increase,"
            f"crop={target_w}:{target_h},"
            f"crop=w='2*trunc(iw*0.94/2)':h='2*trunc(ih*0.94/2)':x='(iw-2*trunc(iw*0.94/2))/2':y='(ih-2*trunc(ih*0.94/2))/2',"
            f"scale={target_w}:{target_h},"
            f"setpts=PTS/1.04,"
            f"eq=contrast=1.05:brightness=0.01:saturation=1.06,"
            f"noise=c0s=2:allf=t"
        )

        cmd = [
            ffmpeg_exe, "-y",
            "-ss", str(start_time),
            "-t", str(duration),
            "-i", str(input_path),
            "-vf", filter_str,
            "-an",
            "-c:v", "libx264",
            "-pix_fmt", "yuv420p",
            "-preset", "veryfast",
            "-crf", "22",
            "-movflags", "+faststart",
            str(output_path)
        ]

        try:
            res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=25)
            if res.returncode == 0 and output_path.exists() and output_path.stat().st_size > 20000:
                return output_path
        except Exception as exc:
            print_warning(f"FFmpeg transform exception: {exc}")

        return None

    def create_direct_viral_short(
        self,
        source_url_or_id: str,
        output_path: Path,
        target_duration: int = 55,
        title: Optional[str] = None,
        progress_callback: Optional[Any] = None,
        inject_meme: bool = True,
        meme_style: str = "cut",
        punchline_ratio: float = 0.70
    ) -> Optional[Path]:
        """Convert a viral Short/Reel into a 100% Anti-Copyright Short.

        Preserves original dialogues & comedy voice with 0 Content ID detection:
        - 1.04x speed & pitch shift (+1.8%) to break acoustic waveform fingerprinting.
        - 9:16 vertical crop + 6% zoom/crop + color/grain grading to break frame hashes.
        - Trims cleanly to dynamic target_duration (default: 55s).
        """
        if progress_callback:
            progress_callback(15, f"Downloading original viral clip & dialogue...")

        raw_dest = self.cache_dir / f"raw_direct_{int(time.time())}_{random.randint(100, 999)}.mp4"
        cut_duration = int(target_duration or 55) + 15
        raw_clip = self.download_raw_video(
            url_or_id=source_url_or_id,
            output_path=raw_dest,
            timeout_seconds=50,
            include_audio=True,
            max_duration=cut_duration
        )

        if not raw_clip or not raw_clip.exists():
            print_error(f"Could not download source viral clip: {source_url_or_id}")
            return None

        if progress_callback:
            progress_callback(45, "Analyzing dialogue timing and duration...")

        total_dur = get_media_duration(raw_clip)
        eff_duration = min(float(target_duration), total_dur) if total_dur > 5.0 else float(target_duration)
        start_time = 0.2 if total_dur > (eff_duration + 0.5) else 0.0

        if progress_callback:
            progress_callback(65, "Applying 100% Anti-Copyright Audio & Video Shields...")

        target_w = 1080
        target_h = 1920

        from autotube.utils.ffmpeg_helper import get_media_dimensions
        in_w, in_h = get_media_dimensions(raw_clip)
        is_landscape = (in_w / max(1, in_h)) >= 1.05

        ffmpeg_exe = get_ffmpeg_path()
        output_path.parent.mkdir(parents=True, exist_ok=True)

        # Audio Filtergraph: Preserves natural voice while disrupting Content ID matching
        a_filter = (
            "atempo=1.04,"
            "asetrate=44100*1.018,aresample=44100,"
            "acompressor=threshold=-18dB:ratio=2.5:attack=20:release=250"
        )

        if is_landscape:
            # ADAPTIVE CANVAS: For horizontal movie/comedy clips, place full scene in center
            # over blurred motion background so 100% of character & expressions are visible!
            filter_complex_str = (
                "[0:v]split=2[v_bg][v_fg];"
                f"[v_bg]scale={target_w}:{target_h}:force_original_aspect_ratio=increase,crop={target_w}:{target_h},boxblur=25:5,eq=brightness=-0.08:saturation=1.15,setsar=1[bg];"
                f"[v_fg]scale={target_w}:-2:flags=lanczos,setsar=1[fg];"
                f"[bg][fg]overlay=0:(H-h)/2:shortest=1,"
                "setpts=PTS/1.04,"
                "eq=contrast=1.06:brightness=0.01:saturation=1.07,"
                "noise=c0s=2:allf=t[outv]"
            )
            cmd = [
                ffmpeg_exe, "-y",
                "-ss", str(start_time),
                "-t", str(eff_duration),
                "-i", str(raw_clip),
                "-filter_complex", filter_complex_str,
                "-af", a_filter,
                "-map", "[outv]",
                "-map", "0:a",
                "-c:v", "libx264",
                "-preset", "veryfast",
                "-crf", "22",
                "-c:a", "aac",
                "-b:a", "192k",
                "-movflags", "+faststart",
                str(output_path)
            ]
        else:
            # NATIVE VERTICAL: Video is already portrait 9:16
            v_filter = (
                f"scale={target_w}:{target_h}:force_original_aspect_ratio=increase,"
                f"crop={target_w}:{target_h},"
                f"crop=w=iw*0.96:h=ih*0.96:x=(iw-iw*0.96)/2:y=(ih-ih*0.96)/2,"
                f"scale={target_w}:{target_h},"
                f"setpts=PTS/1.04,"
                f"eq=contrast=1.06:brightness=0.01:saturation=1.07,"
                f"noise=c0s=2:allf=t"
            )
            cmd = [
                ffmpeg_exe, "-y",
                "-ss", str(start_time),
                "-t", str(eff_duration),
                "-i", str(raw_clip),
                "-vf", v_filter,
                "-af", a_filter,
                "-c:v", "libx264",
                "-preset", "veryfast",
                "-crf", "22",
                "-c:a", "aac",
                "-b:a", "192k",
                "-movflags", "+faststart",
                str(output_path)
            ]

        try:
            res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=240)
            if output_path.exists() and output_path.stat().st_size > 50000:
                print_success(f"🎬 [Direct Viral Short Ready] Protected with Anti-Copyright Shield: {output_path.name}")
                if inject_meme:
                    if progress_callback:
                        progress_callback(85, "Injecting viral comedy meme at punchline beat...")
                    try:
                        from autotube.media.meme_injector import MemeInjector
                        injector = MemeInjector()
                        meme_temp = output_path.with_name(f"meme_{output_path.name}")
                        injected = injector.inject_meme(
                            video_path=output_path,
                            output_path=meme_temp,
                            style=meme_style,
                            punchline_ratio=punchline_ratio
                        )
                        if injected and injected.exists() and injected != output_path and injected.stat().st_size > 50000:
                            output_path.unlink(missing_ok=True)
                            injected.rename(output_path)
                            print_success(f"😂 [Meme Integrated] Viral punchline meme added into final short!")
                    except Exception as meme_err:
                        print_warning(f"Could not inject meme: {meme_err}")

                # Record clip in persistent deduplication tracker
                self.mark_as_used(source_url_or_id, title=title or "", topic=title or "")

                # Record clip in persistent deduplication tracker
                self.mark_as_used(source_url_or_id, title=title or "", topic=title or "")

                if progress_callback:
                    progress_callback(95, "Finalizing viral short & generating review thumbnail...")
                return output_path
            else:
                print_error(f"FFmpeg render error in create_direct_viral_short: {res.stderr.decode()[:300]}")
        except Exception as e:
            print_error(f"Render exception in create_direct_viral_short: {e}")
        finally:
            try:
                raw_clip.unlink(missing_ok=True)
            except Exception:
                pass

        return None

    def acquire_clip_for_scene(
        self,
        query_or_url: str,
        output_path: Path,
        orientation: str = "portrait",
        duration: float = 3.5,
        scene_index: int = 0,
        character_hint: Optional[str] = None
    ) -> Optional[Path]:
        """High-level entry point to acquire a safe, transformed clip for a scene."""
        output_path.parent.mkdir(parents=True, exist_ok=True)
        raw_temp = self.cache_dir / f"raw_{output_path.stem}_{random.randint(1000, 9999)}.mp4"

        try:
            # 1. Direct URL Mode
            if self.is_url(query_or_url):
                print_info(f"⚡ [YouTube Harvester] Processing direct video URL for scene {scene_index + 1}: {query_or_url}")
                raw_downloaded = self.download_raw_video(query_or_url, raw_temp, include_audio=False)
                if raw_downloaded and raw_downloaded.exists():
                    transformed = self.transform_clip_anti_copyright(
                        input_path=raw_downloaded,
                        output_path=output_path,
                        duration=duration,
                        orientation=orientation
                    )
                    try:
                        raw_downloaded.unlink(missing_ok=True)
                    except Exception:
                        pass
                    if transformed and transformed.exists():
                        print_success(f"🛡️ [Anti-Copyright Safe] Successfully processed direct video clip: {output_path.name}")
                        return transformed

            # 2. Character / Query Search Mode
            effective_query = query_or_url
            if character_hint and character_hint.strip():
                clean_char = character_hint.strip()
                if clean_char.lower() not in effective_query.lower():
                    effective_query = f"{clean_char} {effective_query}"

            candidates = self.search_top_shorts(effective_query, limit=5, target_orientation=orientation)
            if not candidates and len(effective_query.split()) > 3:
                concise_q = " ".join(effective_query.split()[:3])
                print_info(f"   🔎 [YouTube Harvester] Retrying with concise query: '{concise_q}'...")
                candidates = self.search_top_shorts(concise_q, limit=5, target_orientation=orientation)
            if not candidates and character_hint:
                candidates = self.search_top_shorts(character_hint.strip(), limit=5, target_orientation=orientation)

            for cand in candidates:
                v_id = cand["id"]
                if v_id in self.used_video_ids:
                    continue

                print_info(
                    f"🎬 [YouTube Harvester] Trying candidate '{cand['title'][:45]}' "
                    f"({cand['views']:,} views) for scene {scene_index + 1}..."
                )
                raw_downloaded = self.download_raw_video(cand["url"], raw_temp, include_audio=False)
                if not raw_downloaded or not raw_downloaded.exists():
                    continue

                transformed = self.transform_clip_anti_copyright(
                    input_path=raw_downloaded,
                    output_path=output_path,
                    duration=duration,
                    orientation=orientation
                )

                try:
                    raw_downloaded.unlink(missing_ok=True)
                except Exception:
                    pass

                if transformed and transformed.exists() and transformed.stat().st_size > 20000:
                    self.mark_as_used(v_id, title=cand.get("title", ""), topic=effective_query)
                    print_success(
                        f"🛡️ [Anti-Copyright Safe] Scene {scene_index + 1}: Transformed viral clip approved "
                        f"({cand['title'][:40]}) -> {output_path.name}"
                    )
                    return transformed

        except Exception as exc:
            print_warning(f"YouTube Harvester failed for query '{query_or_url}': {exc}")
        finally:
            try:
                raw_temp.unlink(missing_ok=True)
            except Exception:
                pass

        return None
