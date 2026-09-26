"""YouTube OAuth2 Authentication Manager."""

import os
from pathlib import Path
from typing import Optional
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from autotube.config import get_config
from autotube.utils.console import print_error, print_info, print_success, print_warning

YOUTUBE_SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube",
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

        # If there are no valid credentials, let user log in
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
                        f"To enable YouTube uploads:\n"
                        f"1. Create a project in Google Cloud Console\n"
                        f"2. Enable YouTube Data API v3\n"
                        f"3. Create OAuth 2.0 Client ID (Desktop Application)\n"
                        f"4. Download JSON and save as '{self.client_secrets_file}'"
                    )
                    return None

                print_info(
                    "Launching browser for YouTube account authentication..."
                )
                flow = InstalledAppFlow.from_client_secrets_file(
                    str(self.client_secrets_file), YOUTUBE_SCOPES
                )
                creds = flow.run_local_server(port=0)

            # Save token for future runs
            self.token_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self.token_file, "w", encoding="utf-8") as token:
                token.write(creds.to_json())
            print_success(f"YouTube credentials saved to {self.token_file}")

        return creds
