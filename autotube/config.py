"""Configuration management for AutoTube using Pydantic and PyYAML."""

import os
from pathlib import Path
from typing import Any, Dict, Optional
import yaml
from dotenv import load_dotenv
from pydantic import BaseModel, Field

# Root directory of AutoTube
PROJECT_ROOT = Path(__file__).resolve().parent.parent

# Load environment variables
load_dotenv(PROJECT_ROOT / ".env")


class ProjectConfig(BaseModel):
    name: str = "AutoTube"
    version: str = "1.0.0"
    description: str = "AI YouTube Video Generator & Auto-Uploader"


class PathsConfig(BaseModel):
    project_root: Path = Field(default_factory=lambda: PROJECT_ROOT)
    output_dir: Path = Field(default_factory=lambda: PROJECT_ROOT / "output")
    assets_dir: Path = Field(default_factory=lambda: PROJECT_ROOT / "assets")
    temp_dir: Path = Field(default_factory=lambda: PROJECT_ROOT / "output" / "temp")

    def ensure_directories(self) -> None:
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.assets_dir.mkdir(parents=True, exist_ok=True)
        self.temp_dir.mkdir(parents=True, exist_ok=True)
        (self.output_dir / "shorts").mkdir(parents=True, exist_ok=True)
        (self.output_dir / "videos").mkdir(parents=True, exist_ok=True)
        (self.assets_dir / "audio").mkdir(parents=True, exist_ok=True)
        (self.assets_dir / "video").mkdir(parents=True, exist_ok=True)
        (self.assets_dir / "fonts").mkdir(parents=True, exist_ok=True)


class SubtitleStyle(BaseModel):
    font: str = "Arial-Bold"
    fontsize: int = 58
    primary_color: str = "&H00FFFFFF"
    highlight_color: str = "&H0000FFFF"
    outline_color: str = "&H00000000"
    outline_width: int = 3
    shadow_width: int = 2
    position: str = "bottom"


class VideoSettings(BaseModel):
    width: int
    height: int
    fps: int = 30
    default_duration: Optional[int] = None
    subtitle_style: SubtitleStyle = Field(default_factory=SubtitleStyle)


class VideoConfig(BaseModel):
    shorts: VideoSettings = Field(
        default_factory=lambda: VideoSettings(
            width=1080, height=1920, fps=30, default_duration=50
        )
    )
    longform: VideoSettings = Field(
        default_factory=lambda: VideoSettings(
            width=1920, height=1080, fps=30, default_duration=300
        )
    )


class VoiceConfig(BaseModel):
    default_voice: str = "en-US-ChristopherNeural"
    hindi_voice: str = "hi-IN-MadhurNeural"
    rate: str = "-3%"
    pitch: str = "-4Hz"
    volume: str = "+0%"


class MediaConfig(BaseModel):
    stock_provider: str = "pexels"
    image_provider: str = "pollinations"
    background_music_volume: float = 0.24


class YouTubeConfig(BaseModel):
    client_secrets_file: Path = Field(
        default_factory=lambda: PROJECT_ROOT / "config" / "client_secrets.json"
    )
    token_file: Path = Field(
        default_factory=lambda: PROJECT_ROOT / "config" / "token.json"
    )
    default_privacy: str = "private"
    default_category: str = "28"


class AppConfig(BaseModel):
    project: ProjectConfig = Field(default_factory=ProjectConfig)
    paths: PathsConfig = Field(default_factory=PathsConfig)
    video: VideoConfig = Field(default_factory=VideoConfig)
    voice: VoiceConfig = Field(default_factory=VoiceConfig)
    media: MediaConfig = Field(default_factory=MediaConfig)
    youtube: YouTubeConfig = Field(default_factory=YouTubeConfig)

    # API Keys from environment
    gemini_api_key: Optional[str] = None
    pexels_api_key: Optional[str] = None
    pixabay_api_key: Optional[str] = None
    elevenlabs_api_key: Optional[str] = None


_config_instance: Optional[AppConfig] = None


def get_config(reload: bool = False) -> AppConfig:
    global _config_instance
    if _config_instance is not None and not reload:
        return _config_instance

    config_path = PROJECT_ROOT / "config" / "settings.yaml"
    data: Dict[str, Any] = {}
    if config_path.exists():
        with open(config_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}

    # Bind environment keys
    data["gemini_api_key"] = os.getenv("GEMINI_API_KEY")
    data["pexels_api_key"] = os.getenv("PEXELS_API_KEY")
    data["pixabay_api_key"] = os.getenv("PIXABAY_API_KEY")
    data["elevenlabs_api_key"] = os.getenv("ELEVENLABS_API_KEY")

    cfg = AppConfig(**data)
    cfg.paths.ensure_directories()
    _config_instance = cfg
    return cfg
