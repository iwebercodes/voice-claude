"""Claude API client with cross-platform credential discovery."""

import getpass
import hashlib
import json
import os
import secrets
import subprocess
import sys
import uuid
from pathlib import Path
from typing import Any

import httpx

ANTHROPIC_API_URL = "https://api.anthropic.com"
DEFAULT_MODEL = "claude-haiku-4-5-20251001"  # Fast model for agent decisions

# OAuth constants
CLIENT_ID = "9d1c250a-e61b-44d9-88ed-5944d1962f5e"
TOKEN_URL = "https://console.anthropic.com/v1/oauth/token"
PROFILE_URL = "https://api.anthropic.com/api/oauth/profile"


class ClaudeAPIClient:
    """Client for Claude API with cross-platform credential discovery."""

    def __init__(self) -> None:
        self.access_token: str | None = None
        self.api_key: str | None = None
        self.device_id: str | None = None
        self.account_uuid: str | None = None
        self.org_uuid: str | None = None
        self.session_id = str(uuid.uuid4())
        self._http_client: httpx.Client | None = None
        self._is_oauth = False

    def _get_config_dir(self) -> Path:
        """Get Claude config directory."""
        if config_dir := os.environ.get("CLAUDE_CONFIG_DIR"):
            return Path(config_dir)
        return Path.home() / ".claude"

    def _get_keychain_service_name(self) -> str:
        """Get macOS Keychain service name."""
        base = "Claude Code-credentials"
        if os.environ.get("CLAUDE_CONFIG_DIR"):
            config_dir = self._get_config_dir()
            suffix = hashlib.sha256(str(config_dir).encode()).hexdigest()[:8]
            return f"Claude Code-{suffix}-credentials"
        return base

    def _read_from_fd(self, fd: int) -> str | None:
        """Read token from file descriptor."""
        try:
            if sys.platform in ("darwin", "freebsd"):
                path = f"/dev/fd/{fd}"
            else:
                path = f"/proc/self/fd/{fd}"
            return Path(path).read_text().strip()
        except Exception:
            return None

    def _read_macos_keychain(self) -> dict[str, Any] | None:
        """Read credentials from macOS Keychain."""
        try:
            user = os.environ.get("USER") or getpass.getuser()
            service = self._get_keychain_service_name()
            result = subprocess.run(
                ["security", "find-generic-password", "-a", user, "-w", "-s", service],
                capture_output=True,
                text=True,
            )
            if result.returncode == 0:
                creds: dict[str, Any] = json.loads(result.stdout.strip())
                return creds
        except Exception:
            pass
        return None

    def _read_credential_file(self) -> dict[str, Any] | None:
        """Read credentials from plaintext file."""
        creds_path = self._get_config_dir() / ".credentials.json"
        try:
            if creds_path.exists():
                creds: dict[str, Any] = json.loads(creds_path.read_text())
                return creds
        except Exception:
            pass
        return None

    def _read_credential_store(self) -> dict[str, Any] | None:
        """Read credentials from platform-appropriate store."""
        # macOS: try Keychain first
        if sys.platform == "darwin":
            if creds := self._read_macos_keychain():
                return creds

        # Fallback: plaintext file (all platforms)
        return self._read_credential_file()

    def _load_oauth_token(self) -> str | None:
        """Load OAuth token following priority order."""
        # 1. CLAUDE_CODE_OAUTH_TOKEN env var
        if token := os.environ.get("CLAUDE_CODE_OAUTH_TOKEN"):
            return token

        # 2. CLAUDE_CODE_OAUTH_TOKEN_FILE_DESCRIPTOR env var
        if fd_str := os.environ.get("CLAUDE_CODE_OAUTH_TOKEN_FILE_DESCRIPTOR"):
            try:
                if token := self._read_from_fd(int(fd_str)):
                    return token
            except ValueError:
                pass

        # 3. Credential store
        if creds := self._read_credential_store():
            if oauth := creds.get("claudeAiOauth"):
                if token := oauth.get("accessToken"):
                    return str(token)

        return None

    def _load_api_key(self) -> str | None:
        """Load API key following priority order."""
        # 1. ANTHROPIC_API_KEY env var
        if key := os.environ.get("ANTHROPIC_API_KEY"):
            return key

        # 2. CLAUDE_CODE_API_KEY_FILE_DESCRIPTOR env var
        if fd_str := os.environ.get("CLAUDE_CODE_API_KEY_FILE_DESCRIPTOR"):
            try:
                if key := self._read_from_fd(int(fd_str)):
                    return key
            except ValueError:
                pass

        return None

    def load_credentials(self) -> None:
        """Load credentials using cross-platform discovery."""
        # Check for legacy auth token first
        if token := os.environ.get("ANTHROPIC_AUTH_TOKEN"):
            self.access_token = token
            self._is_oauth = True
            return

        # Try OAuth token
        if token := self._load_oauth_token():
            self.access_token = token
            self._is_oauth = True
            return

        # Try API key
        if key := self._load_api_key():
            self.api_key = key
            self._is_oauth = False
            return

        raise FileNotFoundError("No credentials found")

    def _load_device_id(self) -> None:
        """Load or generate device ID."""
        config_file = Path.home() / ".claude.json"
        try:
            if config_file.exists():
                data = json.loads(config_file.read_text())
                if user_id := data.get("userID"):
                    self.device_id = user_id
                    return
        except Exception:
            pass

        # Generate new device ID
        self.device_id = secrets.token_hex(32)

    def _get_http_client(self) -> httpx.Client:
        """Get or create HTTP client."""
        if self._http_client is None:
            self._http_client = httpx.Client(timeout=60.0)
        return self._http_client

    def fetch_profile(self) -> None:
        """Fetch account and org UUIDs from API (OAuth only)."""
        if not self._is_oauth:
            # API key doesn't need profile fetch
            return

        client = self._get_http_client()
        resp = client.get(
            PROFILE_URL,
            headers={
                "Authorization": f"Bearer {self.access_token}",
                "Content-Type": "application/json",
            },
        )
        resp.raise_for_status()
        data = resp.json()
        self.account_uuid = data["account"]["uuid"]
        self.org_uuid = data["organization"]["uuid"]

    def initialize(self) -> None:
        """Load credentials and fetch profile."""
        try:
            self.load_credentials()
            self._load_device_id()
            self.fetch_profile()
        except FileNotFoundError:
            print(
                "Error: No credentials found.\n"
                "Run 'claude' to authenticate, or set ANTHROPIC_API_KEY.",
                file=sys.stderr,
            )
            sys.exit(1)
        except (KeyError, json.JSONDecodeError):
            print(
                "Error: Invalid credentials. Run 'claude' to re-authenticate.",
                file=sys.stderr,
            )
            sys.exit(1)
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 401:
                print(
                    "Error: Token expired. Run 'claude' to re-authenticate.",
                    file=sys.stderr,
                )
            else:
                print(
                    f"Error: API error ({e.response.status_code}). Try again later.",
                    file=sys.stderr,
                )
            sys.exit(1)
        except httpx.ConnectError:
            print(
                "Error: Cannot connect to API. Check internet connection.",
                file=sys.stderr,
            )
            sys.exit(1)

    def _build_headers(self) -> dict[str, str]:
        """Build request headers."""
        headers = {
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json",
            "User-Agent": "voice-claude/1.0",
        }

        if self._is_oauth:
            headers["Authorization"] = f"Bearer {self.access_token}"
            headers["anthropic-beta"] = (
                "oauth-2025-04-20,interleaved-thinking-2025-05-14"
            )
            headers["anthropic-dangerous-direct-browser-access"] = "true"
            headers["x-app"] = "cli"
        else:
            headers["x-api-key"] = self.api_key or ""

        return headers

    def _build_user_id(self) -> str:
        """Build metadata user_id string."""
        if self._is_oauth:
            return (
                f"user_{self.device_id}_account_{self.account_uuid}"
                f"_session_{self.session_id}"
            )
        return f"user_{self.device_id}_session_{self.session_id}"

    def send_message(
        self,
        messages: list[dict[str, Any]],
        system: str | list[dict[str, Any]] | None = None,
        tools: list[dict[str, Any]] | None = None,
        model: str = DEFAULT_MODEL,
        max_tokens: int = 1024,
    ) -> dict[str, Any]:
        """Send a message to Claude API."""
        client = self._get_http_client()

        body: dict[str, Any] = {
            "model": model,
            "max_tokens": max_tokens,
            "messages": messages,
            "metadata": {"user_id": self._build_user_id()},
        }

        if system:
            if isinstance(system, str):
                body["system"] = [{"type": "text", "text": system}]
            else:
                body["system"] = system

        if tools:
            body["tools"] = tools

        url = f"{ANTHROPIC_API_URL}/v1/messages"
        if self._is_oauth:
            url += "?beta=true"

        resp = client.post(url, headers=self._build_headers(), json=body)
        resp.raise_for_status()
        result: dict[str, Any] = resp.json()
        return result

    def cancel_request(self) -> None:
        """Cancel any in-flight request."""
        pass

    def close(self) -> None:
        """Close the HTTP client."""
        if self._http_client:
            self._http_client.close()
            self._http_client = None
