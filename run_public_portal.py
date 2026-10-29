"""Run AutoTube Public Guest Portal with 1-click Cloudflare Tunnel & 2-Video Daily Limiter."""

import os
import re
import sys
import time
import signal
import subprocess
import threading
from pathlib import Path

# Ensure UTF-8 output on Windows terminal
if sys.stdout.encoding != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except Exception:
        pass

PROJECT_ROOT = Path(__file__).resolve().parent
PYTHON_EXE = PROJECT_ROOT / ".venv" / "Scripts" / "python.exe"
CLOUDFLARED_EXE = PROJECT_ROOT / "tools" / "cloudflared.exe"

stop_event = threading.Event()


def stream_cloudflared_logs(proc):
    """Monitor cloudflared output to detect and display the public HTTPS link."""
    found_url = False
    pattern = re.compile(r"https://[a-zA-Z0-9-]+\.trycloudflare\.com")
    
    while True:
        line = proc.stderr.readline()
        if not line:
            break
        match = pattern.search(line)
        if match and not found_url:
            found_url = True
            base_url = match.group(0)
            portal_url = f"{base_url}/portal"
            print("\n" + "=" * 65, flush=True)
            print("🚀 AutoTube Public Guest Portal is LIVE!", flush=True)
            print("=" * 65, flush=True)
            print(f"\n👉 Share this Link with your 10-15 Followers:\n", flush=True)
            print(f"   {portal_url}\n", flush=True)
            print("=" * 65, flush=True)
            print("🛡️ Safety Controls Active:", flush=True)
            print(" • Daily Limit: 2 free videos per user/day (Locked on 3rd attempt)", flush=True)
            print(" • Paywall: Asks user to Subscribe (₹399/mo) or wait until midnight", flush=True)
            print(" • Protection: Videos are Download-Only (Your YouTube channel is untouched)", flush=True)
            print("=" * 65, flush=True)
            print("Press Ctrl+C anytime to close the public link.\n", flush=True)


def main():
    if not CLOUDFLARED_EXE.exists():
        print(f"[Error] cloudflared.exe not found at {CLOUDFLARED_EXE}", flush=True)
        sys.exit(1)

    print("\n[*] Starting AutoTube Web Server (port 8000)...", flush=True)
    web_proc = subprocess.Popen(
        [
            str(PYTHON_EXE),
            "-m",
            "uvicorn",
            "autotube.web.app:app",
            "--host",
            "127.0.0.1",
            "--port",
            "8000",
            "--log-level",
            "warning",
        ],
        cwd=str(PROJECT_ROOT),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    time.sleep(2)

    print("[*] Launching Secure Cloudflare Tunnel...", flush=True)
    cf_proc = subprocess.Popen(
        [
            str(CLOUDFLARED_EXE),
            "tunnel",
            "--url",
            "http://127.0.0.1:8000",
        ],
        cwd=str(PROJECT_ROOT),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
    )

    t = threading.Thread(target=stream_cloudflared_logs, args=(cf_proc,), daemon=True)
    t.start()

    def handle_sig(sig, frame):
        print("\n\n[*] Shutting down Public Portal and Tunnel cleanly...")
        try:
            cf_proc.terminate()
            web_proc.terminate()
        except Exception:
            pass
        sys.exit(0)

    signal.signal(signal.SIGINT, handle_sig)
    signal.signal(signal.SIGTERM, handle_sig)

    try:
        while True:
            time.sleep(1)
            if web_proc.poll() is not None or cf_proc.poll() is not None:
                break
    except KeyboardInterrupt:
        handle_sig(None, None)


if __name__ == "__main__":
    main()
