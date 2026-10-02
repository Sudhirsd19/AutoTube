"""YouTube OAuth2 Authentication Manager with robust Windows browser launching."""

import os
import sys
import webbrowser
import wsgiref.simple_server
from pathlib import Path
from typing import Optional
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
    "https://www.googleapis.com/auth/youtube.force-ssl",
]


class YouTubeAuth:
    """Manages YouTube OAuth 2.0 Credentials."""

    def __init__(
        self,
        client_secrets_file: Optional[Path] = None,
        token_file: Optional[Path] = None,
    ):
        cfg = get_config()
        self.client_secrets_file = (
            client_secrets_file or cfg.youtube.client_secrets_file
        )
        self.token_file = token_file or cfg.youtube.token_file

    def get_credentials(self) -> Optional[Credentials]:
        """Obtain valid user credentials from storage or run OAuth flow."""
        creds = None
        if self.token_file.exists():
            try:
                creds = Credentials.from_authorized_user_file(
                    str(self.token_file), YOUTUBE_SCOPES
                )
            except Exception as e:
                print_warning(f"Existing token could not be loaded: {e}")

        # If there are no valid credentials, run login flow
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                try:
                    print_info("Refreshing expired YouTube OAuth token...")
                    creds.refresh(Request())
                except Exception as e:
                    print_warning(f"Token refresh failed: {e}. Re-authenticating...")
                    creds = None

            if not creds:
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
                local_server.timeout = 300  # 5 minutes timeout
                local_server.handle_request()

                try:
                    auth_response = wsgi_app.last_request_uri.replace(
                        "http:", "https:"
                    )
                    flow.fetch_token(authorization_response=auth_response)
                    creds = flow.credentials
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
                print_success(f"YouTube credentials saved to {self.token_file}")

        return creds
