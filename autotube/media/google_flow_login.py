"""Google Flow Persistent Session Setup & Login Manager.

Launches visible Chrome window using a dedicated profile to allow the user
to log into their Google AI Pro account on https://flow.google.com/.
Automatically detects successful login when the PRO dashboard appears.
"""

import sys
import time
from pathlib import Path
from playwright.sync_api import sync_playwright
from autotube.utils.console import print_error, print_info, print_success, print_warning

PROFILE_DIR = Path("config/chrome_flow_profile").resolve()
CHROME_PATH = "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe"
FLOW_URL = "https://flow.google.com/"


def setup_google_flow_session(timeout_sec: int = 300):
    """Launch visible Chrome and automatically detect when user logs into Google Flow."""
    # Ensure fresh clean profile directory
    PROFILE_DIR.mkdir(parents=True, exist_ok=True)

    print_info(f"Opening Chrome for Google Flow authentication...")
    print_info(f"Target URL: {FLOW_URL}")
    print_info(f"Profile: {PROFILE_DIR}")

    with sync_playwright() as p:
        try:
            context = p.chromium.launch_persistent_context(
                user_data_dir=str(PROFILE_DIR),
                executable_path=CHROME_PATH,
                headless=False,
                viewport={"width": 1280, "height": 850},
                args=[
                    "--disable-blink-features=AutomationControlled",
                    "--no-first-run",
                    "--no-default-browser-check",
                ],
            )
        except Exception as e:
            print_error(f"Failed to launch Chrome: {e}")
            return False

        page = context.pages[0] if context.pages else context.new_page()
        try:
            page.goto(FLOW_URL, wait_until="domcontentloaded", timeout=45000)
        except Exception as e:
            print_warning(f"Initial navigation notice: {e}")

        print_success("=" * 60)
        print_success("👉 CHROME IS OPEN ON YOUR SCREEN!")
        print_success("1. Click 'Sign In' or 'Create with Google Flow'")
        print_success("2. Log into your Google Account with Google AI Pro (dulumoni2468@gmail.com)")
        print_success("3. The script will AUTOMATICALLY detect when you are logged in!")
        print_success("=" * 60)

        # Auto-detect login loop (up to timeout_sec)
        start_time = time.time()
        logged_in = False
        while time.time() - start_time < timeout_sec:
            try:
                curr_url = page.url
                if "accounts.google.com" not in curr_url and "/about" not in curr_url:
                    content = page.content()
                    if (
                        "PRO" in content
                        or "Create a character" in content
                        or "New project" in content
                        or "Flow Music" in content
                    ):
                        logged_in = True
                        break
            except Exception:
                pass
            time.sleep(2)

        if logged_in:
            print_success("🎉 SUCCESS! Google Flow PRO dashboard detected!")
            time.sleep(3)  # Let cookies fully persist
            context.close()
            print_success("Session permanently saved to config/chrome_flow_profile/!")
            print_success("AutoTube can now generate 3D & realistic videos automatically!")
            return True
        else:
            print_warning("Login timed out or window was closed.")
            try:
                context.close()
            except Exception:
                pass
            return False


if __name__ == "__main__":
    setup_google_flow_session()
