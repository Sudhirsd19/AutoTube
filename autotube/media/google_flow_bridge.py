"""Google Flow Web Studio Automation Bridge.

Uses Playwright with a persistent Chrome user profile (config/chrome_flow_profile)
to generate high-fidelity 3D and cinematic video clips on https://flow.google.com/
using the user's active Google AI Pro plan (1,000 credits/month).
"""

import os
import time
from pathlib import Path
from typing import List, Optional
from autotube.utils.console import print_error, print_info, print_success, print_warning

PROFILE_DIR = Path("config/edge_flow_profile").resolve()
EDGE_PATH = "C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe"
CHROME_PATH = "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe"
FLOW_URL = "https://flow.google.com/"


class GoogleFlowBridge:
    """Automates video generation via Google Flow web studio using Edge/Chrome."""

    def __init__(self, profile_dir: Optional[Path] = None):
        if profile_dir:
            self.profile_dir = profile_dir
        elif Path("config/edge_flow_profile").exists():
            self.profile_dir = Path("config/edge_flow_profile").resolve()
        else:
            self.profile_dir = Path("config/chrome_flow_profile").resolve()

        if Path(EDGE_PATH).exists():
            self.browser_path = EDGE_PATH
            self.channel = "msedge"
        else:
            self.browser_path = CHROME_PATH
            self.channel = "chrome"

    def is_authenticated(self) -> bool:
        """Check if persistent Chrome profile exists and has Google cookies."""
        if not self.profile_dir.exists():
            return False
        # Profile directory will contain Default or Network directory
        net_dir = self.profile_dir / "Default" / "Network"
        cookies_db = self.profile_dir / "Default" / "Cookies"
        return cookies_db.exists() or net_dir.exists() or len(list(self.profile_dir.iterdir())) > 3

    def generate_scene_clip(
        self,
        prompt: str,
        output_path: Path,
        aspect_ratio: str = "9:16",
        timeout: int = 180,
        headless: bool = True,
    ) -> Optional[Path]:
        """Generate a single 3D or cinematic video clip via Google Flow web."""
        import urllib.request
        from playwright.sync_api import sync_playwright

        output_path.parent.mkdir(parents=True, exist_ok=True)
        print_info(f"Connecting to Google Flow (Google AI Pro Engine)...")
        print_info(f"Prompt: {prompt}")

        # Check if user has Desktop Bridge open on port 9222
        is_cdp_active = False
        try:
            with urllib.request.urlopen("http://localhost:9222/json/version", timeout=1) as resp:
                if resp.status == 200:
                    is_cdp_active = True
        except Exception:
            pass

        with sync_playwright() as p:
            should_close = True
            if is_cdp_active:
                print_info("Found active browser session on port 9222! Connecting over CDP...")
                try:
                    browser = p.chromium.connect_over_cdp("http://localhost:9222")
                    context = browser.contexts[0]
                    page = None
                    for pg in context.pages:
                        if "flow.google.com" in pg.url:
                            page = pg
                            break
                    if not page:
                        page = context.new_page()
                        page.goto(FLOW_URL, wait_until="domcontentloaded", timeout=45000)
                    should_close = False  # Keep user's browser open
                except Exception as ce:
                    print_warning(f"CDP connection notice: {ce}. Falling back to persistent launch.")
                    is_cdp_active = False

            if not is_cdp_active:
                if not self.is_authenticated():
                    print_warning("Google Flow profile not yet authenticated.")
                    print_info("TIP: Double-click 'Start_AutoTube_Google_Flow.bat' on your Desktop to connect Edge instantly!")
                    return None

                try:
                    context = p.chromium.launch_persistent_context(
                        user_data_dir=str(self.profile_dir),
                        executable_path=self.browser_path,
                        headless=headless,
                        viewport={"width": 1280, "height": 850},
                        args=[
                            "--disable-blink-features=AutomationControlled",
                            "--no-first-run",
                            "--no-default-browser-check",
                        ],
                    )
                    page = context.pages[0] if context.pages else context.new_page()
                    page.goto(FLOW_URL, wait_until="domcontentloaded", timeout=45000)
                except Exception as e:
                    print_error(f"Could not launch browser context: {e}")
                    return None

            # Ensure we are inside a project workspace
            if "project" not in page.url:
                new_proj_btn = page.locator("text=New project").first
                if new_proj_btn.is_visible():
                    print_info("Opening new Google Flow project workspace...")
                    new_proj_btn.click()
                    time.sleep(4)

            # Ensure Video mode is active
            try:
                model_btn = page.locator("button:has-text('Banana'), button:has-text('Nano')").first
                if model_btn.is_visible():
                    model_btn.click()
                    time.sleep(1)
                    video_opt = page.locator("button:has-text('Video'), [role='menuitem']:has-text('Video')").first
                    if video_opt.is_visible():
                        video_opt.click()
                        time.sleep(1)
            except Exception as me:
                print_warning(f"Model mode check notice: {me}")

            # Type prompt into ProseMirror editor
            try:
                typed = page.evaluate("""(text) => {
                    const el = document.querySelector('.ProseMirror');
                    if (!el) return false;
                    el.focus();
                    document.execCommand('selectAll', false, null);
                    document.execCommand('insertText', false, text);
                    return el.innerText;
                }""", prompt)

                if not typed:
                    print_warning("ProseMirror editor not found. Fallback typing...")
                    editor = page.locator(".ProseMirror, textarea").first
                    editor.click()
                    page.keyboard.type(prompt)

                print_success(f"Prompt successfully typed into Google Flow editor!")
                time.sleep(1)

                # Click Start generation button
                clicked = page.evaluate("""() => {
                    const btns = Array.from(document.querySelectorAll('button'));
                    const genBtn = btns.find(b => 
                        b.getAttribute('aria-label')?.includes('Start generation') ||
                        b.innerText.includes('arrow_forward') ||
                        (b.type === 'submit' && b.querySelector('[data-icon*=\"arrow\"], i, span'))
                    );
                    if (genBtn && !genBtn.disabled) {
                        genBtn.click();
                        return true;
                    }
                    return false;
                }""")

                if clicked:
                    print_success("🚀 Clicked 'Start generation' in Google Flow! Video is rendering...")
                else:
                    page.keyboard.press("Enter")
                    print_info("Submitted prompt via Enter key.")

                # Poll for rendering completion
                start_t = time.time()
                rendered_video_url = None
                print_info(f"Waiting for Google Flow AI rendering (up to {timeout}s)...")
                while time.time() - start_t < timeout:
                    time.sleep(6)
                    # Look for video elements or downloadable mp4 links
                    videos = page.query_selector_all("video")
                    for v in videos:
                        src = v.get_attribute("src")
                        if src and ("blob:" in src or "google" in src or ".mp4" in src):
                            rendered_video_url = src
                            break
                    if rendered_video_url:
                        break

                if rendered_video_url:
                    print_success(f"Google Flow video successfully rendered: {rendered_video_url[:60]}...")
                    # Download video blob/stream
                    page.evaluate("""async ([src, outName]) => {
                        const resp = await fetch(src);
                        const blob = await resp.blob();
                        const a = document.createElement('a');
                        a.href = URL.createObjectURL(blob);
                        a.download = outName;
                        document.body.appendChild(a);
                        a.click();
                        document.body.removeChild(a);
                    }""", [rendered_video_url, output_path.name])
                    time.sleep(3)
                    if should_close:
                        context.close()
                    return output_path
                else:
                    print_warning("Waiting for video completed without finding video tag.")
                    if should_close:
                        context.close()
                    return None

            except Exception as e:
                print_error(f"Error during Google Flow generation: {e}")
                if should_close:
                    context.close()
                return None
