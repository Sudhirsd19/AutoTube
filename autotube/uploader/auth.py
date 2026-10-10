"""YouTube OAuth2 Authentication Manager with robust Windows browser launching."""

import os
import sys
import webbrowser
import wsgiref.simple_server
from pathlib import Path
from typing import Optional, Dict, Any
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import (
    InstalledAppFlow,
    _ExclusiveWSGIServer,
    _RedirectWSGIApp,
    _WSGIRequestHandler,
)
from autotube.config import PROJECT_ROOT, get_config
from autotube.utils.console import (
    console,
    print_error,
    print_info,
    print_panel,
    print_success,
    print_warning,
)

YOUTUBE_SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube",
]


class YouTubeAuth:
    """Manages YouTube OAuth 2.0 Credentials with multi-channel support."""

    def __init__(
        self,
        channel: str = "english",
        client_secrets_file: Optional[Path] = None,
        token_file: Optional[Path] = None,
    ):
        cfg = get_config()
        self.channel = (channel or "english").lower().strip()
        self.client_secrets_file = (
            client_secrets_file or cfg.youtube.client_secrets_file
        )
        self.token_file = token_file or self.resolve_token_file(self.channel)

    @classmethod
    def resolve_token_file(cls, channel: str) -> Path:
        """Resolve the appropriate token file for a channel with legacy fallback."""
        ch = (channel or "english").lower().strip()
        ch_token = PROJECT_ROOT / "config" / f"token_{ch}.json"
        if ch_token.exists():
            return ch_token
        legacy_token = PROJECT_ROOT / "config" / "token.json"
        if ch == "english" and legacy_token.exists():
            return legacy_token
        return ch_token

    def get_credentials(self, interactive: bool = True) -> Optional[Credentials]:
        """Obtain valid user credentials from storage or run OAuth flow."""
        creds = None
        if self.token_file.exists():
            try:
                creds = Credentials.from_authorized_user_file(
                    str(self.token_file), YOUTUBE_SCOPES
                )
            except Exception as e:
                print_warning(f"Existing token for '{self.channel}' could not be loaded: {e}")

        # If credentials exist and are valid, return them immediately
        if creds and creds.valid:
            return creds

        # If expired, attempt refresh using refresh_token
        if creds and creds.expired and creds.refresh_token:
            try:
                print_info(f"Refreshing expired YouTube OAuth token for '{self.channel}' channel...")
                creds.refresh(Request())
                self.token_file.parent.mkdir(parents=True, exist_ok=True)
                with open(self.token_file, "w", encoding="utf-8") as token:
                    token.write(creds.to_json())
                if self.channel == "english":
                    try:
                        with open(PROJECT_ROOT / "config" / "token.json", "w", encoding="utf-8") as token:
                            token.write(creds.to_json())
                    except Exception:
                        pass
                print_success(f"YouTube credentials refreshed and saved to {self.token_file}")
                return creds
            except Exception as e:
                print_warning(f"Token refresh for '{self.channel}' failed: {e}. Re-authenticating...")
                creds = None

        # If non-interactive mode (e.g. background web request), do NOT block on local server
        if not interactive:
            return None

        if not self.client_secrets_file.exists():
            print_error(
                f"Client secrets file not found at: '{self.client_secrets_file}'\n"
                f"Please place client_secrets.json in config/ directory."
            )
            return None

        print_info("Starting OAuth2 local authentication server...")
        flow = InstalledAppFlow.from_client_secrets_file(
            str(self.client_secrets_file), YOUTUBE_SCOPES
        )

        # Bind local server on available port
        wsgi_app = _RedirectWSGIApp(
            "AutoTube Authentication Successful! You can close this browser tab."
        )
        local_server = wsgiref.simple_server.make_server(
            "localhost",
            0,
            wsgi_app,
            server_class=_ExclusiveWSGIServer,
            handler_class=_WSGIRequestHandler,
        )

        flow.redirect_uri = f"http://localhost:{local_server.server_port}/"
        auth_url, _ = flow.authorization_url(
            prompt="consent", access_type="offline"
        )

        # Save auth URL to file for easy access
        auth_file = PROJECT_ROOT / "config" / "auth_url.txt"
        auth_file.write_text(auth_url, encoding="utf-8")

        print_panel(
            f"[bold yellow]Google Login URL Ready:[/bold yellow]\n\n"
            f"[bold cyan]{auth_url}[/bold cyan]\n\n"
            f"[dim]URL has also been saved to config/auth_url.txt[/dim]",
            title="YouTube Login Authorization",
        )

        # Launch default browser in foreground on Windows
        if sys.platform == "win32":
            try:
                os.startfile(auth_url)
            except Exception:
                webbrowser.open(auth_url)
        else:
            webbrowser.open(auth_url)

        print_info("Waiting for authorization approval in browser...")
        local_server.timeout = 180  # 3 minutes timeout
        local_server.handle_request()

        try:
            if wsgi_app.last_request_uri:
                auth_response = wsgi_app.last_request_uri.replace(
                    "http:", "https:"
                )
                flow.fetch_token(authorization_response=auth_response)
                creds = flow.credentials
            else:
                print_warning("No authorization response received within timeout.")
                return None
        except Exception as fe:
            print_error(f"Failed to fetch token from response: {fe}")
            return None
        finally:
            local_server.server_close()

            # Save token for all future runs
            if creds:
                self.token_file.parent.mkdir(parents=True, exist_ok=True)
                with open(self.token_file, "w", encoding="utf-8") as token:
                    token.write(creds.to_json())
                if self.channel == "english":
                    try:
                        with open(PROJECT_ROOT / "config" / "token.json", "w", encoding="utf-8") as token:
                            token.write(creds.to_json())
                    except Exception:
                        pass
                print_success(f"YouTube credentials saved to {self.token_file}")

        return creds

    def get_channel_info(self) -> Optional[Dict[str, Any]]:
        """Fetch title, customUrl, thumbnail, and stats for this channel."""
        creds = self.get_credentials(interactive=False)
        if not creds:
            return None
        try:
            from googleapiclient.discovery import build
            yt = build("youtube", "v3", credentials=creds)
            resp = yt.channels().list(part="snippet,contentDetails,statistics", mine=True).execute()
            items = resp.get("items", [])
            if items:
                item = items[0]
                snippet = item.get("snippet", {})
                stats = item.get("statistics", {})
                return {
                    "channel": self.channel,
                    "channel_id": item.get("id"),
                    "title": snippet.get("title", ""),
                    "custom_url": snippet.get("customUrl", ""),
                    "thumbnail": snippet.get("thumbnails", {}).get("default", {}).get("url", ""),
                    "subscriber_count": stats.get("subscriberCount", "0"),
                    "video_count": stats.get("videoCount", "0"),
                    "view_count": stats.get("viewCount", "0"),
                }
        except Exception as e:
            print_warning(f"Could not fetch channel info for {self.channel}: {e}")
        return None


resolve_token_file = YouTubeAuth.resolve_token_file

