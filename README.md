# 🎬 AutoTube: Complete AI YouTube Video Generator & Auto-Uploader

**AutoTube** is a production-ready, fully-automated CLI pipeline for generating high-retention **YouTube Shorts (9:16)**, **Long-form Documentary Videos (16:9)**, **High-CTR Thumbnails**, and **Auto-Uploading to YouTube** via the YouTube Data API v3.

---

## ⚡ Key Capabilities

- 🤖 **AI Scriptwriting:** Generates structured, high-hook viral scripts using Google Gemini (with smart offline fallback templates).
- 🎙️ **Neural Voiceover (Edge-TTS):** Ultra high-quality Microsoft Neural voices (US, UK, Hindi/Indian, etc.) with zero API cost and millisecond word-level timestamps.
- 🎨 **Dynamic Animated Subtitles:** Word-by-word karaoke highlight animations (Alex Hormozi / MrBeast style) rendered directly via FFmpeg libass.
- 🎥 **Visual Asset Engine:** Multi-source footage from Pexels, Pixabay, Mixkit and Coverr, NASA public space/science video search, scene-specific archival media from Wikimedia/Wikipedia, plus AI visual fallback.
- 🔍 **Frame-Level Visual QA:** When `GEMINI_API_KEY` is configured, selected footage is sampled across the clip and checked against the exact scene narration before it is accepted; `AUTOTUBE_FRAME_QA_STRICT=1` makes QA fail-closed.
- 🖼️ **High-CTR Thumbnail Generator:** Automatically produces 1280x720 clickable thumbnails with bold typography, outlines, and lighting accents.
- 🚀 **YouTube Data API v3 Auto-Upload:** OAuth2 token management, video uploads, metadata injection (Title, Description, Tags, Category), scheduling, and custom thumbnail publishing.
- 🛠️ **Built-in Portable FFmpeg:** Uses bundled `imageio-ffmpeg` binary out-of-the-box (no manual FFmpeg installation required).

---

## 📂 Project Architecture

```
d:/AutoTube/
├── config/
│   ├── settings.yaml          # Global video dimensions, colors, subtitle styles
│   └── client_secrets.json    # Google OAuth2 client secrets (for YouTube upload)
├── autotube/
│   ├── config.py              # Strongly-typed configuration manager
│   ├── cli.py                 # Typer & Rich CLI application
│   ├── utils/                 # FFmpeg runner, console formatting, file helpers
│   ├── scripting/             # AI prompt templates & Gemini script generator
│   ├── voice/                 # Edge-TTS voice engine with word boundary extraction
│   ├── media/                 # Stock fetcher, AI visuals & background music mixer
│   ├── video/                 # Shorts builder, Longform builder, Subtitle burner & Thumbnail creator
│   └── uploader/              # YouTube Data API v3 OAuth2 uploader & scheduler
├── output/
│   ├── shorts/                # Generated 9:16 vertical Shorts (.mp4)
│   ├── videos/                # Generated 16:9 widescreen videos & thumbnails (.mp4, .jpg)
│   └── temp/                  # Cached audio, visuals, and subtitle files
├── assets/                    # Optional local music, gameplay clips, fonts
├── run.py                     # Root CLI entrypoint
└── requirements.txt
```

---

## 🚀 Quick Start Guide

### 1. Verify Environment & System Status
```powershell
python run.py init
```

### 2. View Available AI Voices
```powershell
python run.py voices
```
*Supports `christopher`, `guy`, `aria`, `andrew`, `madhur` (Hindi), `swara` (Hindi), `ryan` (UK), etc.*

---

## 🎬 Generating Content

### 📱 Generate a YouTube Short (9:16 Vertical)
```powershell
python run.py shorts --topic "The Deepest Hole on Earth" --voice guy --duration 45
```
Options:
- `--topic` / `-t`: Any topic, niche, or idea.
- `--voice` / `-v`: Voice name (e.g. `guy`, `christopher`, `madhur`).
- `--duration` / `-d`: Target duration in seconds (default: 45).
- `--upload`: Automatically upload to YouTube after generation.
- `--privacy`: `private`, `unlisted`, or `public`.

### 📺 Generate a Long-form Video & Thumbnail (16:9 Widescreen)
```powershell
python run.py video --topic "Mysteries of the Deep Sea" --scenes 5 --voice christopher
```
Options:
- `--topic` / `-t`: Topic for the documentary.
- `--scenes` / `-s`: Number of scenes (default: 5).
- `--voice` / `-v`: Narrator voice.
- `--upload`: Automatically upload to YouTube after generation.

### 📤 Direct Video Upload to YouTube
```powershell
python run.py upload output/shorts/my_video.mp4 --title "Shocking Space Fact! #Shorts" --desc "Full breakdown" --privacy private
```

---

## 🔑 API Keys Configuration (`.env`)

Edit `.env` at the root of the project to add your optional API keys:

```env
# Google Gemini API Key (for custom scriptwriting)
# Get your free key at: https://aistudio.google.com/
GEMINI_API_KEY=your_gemini_key_here

# Pexels API Key (for free vertical and landscape stock footage)
# Get your free key at: https://www.pexels.com/api/
PEXELS_API_KEY=your_pexels_key_here

# Pixabay API Key (optional alternative stock provider)
PIXABAY_API_KEY=your_pixabay_key_here
```

*(Note: AutoTube works even without API keys using smart built-in fallback scripts and zero-auth AI visuals!)*

---

## 🔐 Enabling YouTube Auto-Upload

1. Go to [Google Cloud Console](https://console.cloud.google.com/).
2. Create a project and enable **YouTube Data API v3**.
3. Create credentials: **OAuth 2.0 Client ID** -> Application Type: **Desktop Application**.
4. Download the JSON file and save it as:
   ```
   d:/AutoTube/config/client_secrets.json
   ```
5. Run any command with `--upload` or `python run.py upload ...`. A browser window will open once to authenticate your YouTube channel and save `config/token.json` for future automated uploads!
