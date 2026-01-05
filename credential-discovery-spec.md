# Credential Discovery Specification

A comprehensive specification for discovering and loading Claude Code credentials across platforms.

---

## Overview

Claude Code supports multiple authentication methods with a defined priority order. This spec covers how to locate, read, and validate credentials on Linux, macOS, and Windows.

---

## Config Directory

The base configuration directory is determined by:

```
config_dir = CLAUDE_CONFIG_DIR env var ?? {homedir}/.claude
```

**Home directory by platform:**

| Platform | Resolution |
|----------|------------|
| Linux | `$HOME` or from `/etc/passwd` |
| macOS | `$HOME` or from `/etc/passwd` |
| Windows | `$USERPROFILE` or `$HOMEDRIVE` + `$HOMEPATH` |

In Python: `pathlib.Path.home()` or `os.path.expanduser("~")`

---

## Credential Storage Locations

### OAuth Credentials (Subscription)

**File path:** `{config_dir}/.credentials.json`

**File format:**
```json
{
  "claudeAiOauth": {
    "accessToken": "sk-ant-oat01-...",
    "refreshToken": "sk-ant-ort01-...",
    "expiresAt": 1735689600000,
    "scopes": ["user:inference", "user:profile", "user:sessions:claude_code"],
    "subscriptionType": "max",
    "rateLimitTier": "default_claude_max_5x"
  }
}
```

**Token prefixes:**

| Prefix | Type |
|--------|------|
| `sk-ant-oat01-` | OAuth Access Token |
| `sk-ant-ort01-` | OAuth Refresh Token |

### Device ID

**File path:** `{config_dir}/../.claude.json` (i.e., `~/.claude.json`, NOT inside `.claude/`)

**File format:**
```json
{
  "userID": "1f4e478d2c02333fe4cf2c851b507d4361f1f4d35d3c8ba9182ffc5e5404882f",
  ...
}
```

**Generation:** 32 random bytes as hex string (64 characters)

In Python: `secrets.token_hex(32)`

---

## Platform-Specific Storage

### macOS Keychain

On macOS, credentials are stored in the system Keychain with plaintext file as fallback.

**Service name:** `"Claude Code-credentials"` or `"Claude Code{suffix}-credentials"`

The suffix is added when `CLAUDE_CONFIG_DIR` is set:
```
suffix = "-" + sha256(config_dir).hex()[:8]
```

**Account name:** `$USER` env var or system username

**Reading from Keychain:**
```bash
security find-generic-password -a "$USER" -w -s "Claude Code-credentials"
```

Returns the JSON string of the credentials object.

**Writing to Keychain:**
```bash
# Data must be hex-encoded
hex_data=$(echo -n '{"claudeAiOauth":...}' | xxd -p | tr -d '\n')
security -i <<EOF
add-generic-password -U -a "$USER" -s "Claude Code-credentials" -X "$hex_data"
EOF
```

**Fallback:** If Keychain read fails, read from `{config_dir}/.credentials.json`

### Linux

Plaintext file only: `{config_dir}/.credentials.json`

**File permissions:** `0600` (read/write owner only)

### Windows

Plaintext file only: `{config_dir}/.credentials.json`

**Path example:** `C:\Users\{username}\.claude\.credentials.json`

---

## Environment Variables

### Authentication Sources

| Variable | Purpose | Format |
|----------|---------|--------|
| `CLAUDE_CODE_OAUTH_TOKEN` | Direct OAuth token | `sk-ant-oat01-...` |
| `CLAUDE_CODE_OAUTH_TOKEN_FILE_DESCRIPTOR` | FD number containing OAuth token | Integer |
| `ANTHROPIC_API_KEY` | Direct API key | `sk-ant-api03-...` |
| `CLAUDE_CODE_API_KEY_FILE_DESCRIPTOR` | FD number containing API key | Integer |
| `ANTHROPIC_AUTH_TOKEN` | Legacy auth token | String |

### Configuration

| Variable | Purpose | Default |
|----------|---------|---------|
| `CLAUDE_CONFIG_DIR` | Override config directory | `~/.claude` |
| `CLAUDE_CODE_USE_BEDROCK` | Use AWS Bedrock | `false` |
| `CLAUDE_CODE_USE_VERTEX` | Use Google Vertex | `false` |

### File Descriptor Reading

When reading from file descriptor (Linux/macOS):

```python
# macOS / FreeBSD
path = f"/dev/fd/{fd_number}"

# Linux
path = f"/proc/self/fd/{fd_number}"

token = open(path).read().strip()
```

---

## Authentication Priority

The authentication source is determined in this order:

### For OAuth Token (Subscription)

1. `CLAUDE_CODE_OAUTH_TOKEN` env var
2. `CLAUDE_CODE_OAUTH_TOKEN_FILE_DESCRIPTOR` env var (read from fd)
3. Credential store:
   - macOS: Keychain → plaintext fallback
   - Linux/Windows: plaintext file
4. Return `None` if not found

### For API Key

1. `ANTHROPIC_API_KEY` env var
2. `CLAUDE_CODE_API_KEY_FILE_DESCRIPTOR` env var (read from fd)
3. Return `None` if not found

### Overall Priority

```
1. If ANTHROPIC_AUTH_TOKEN set → use as token
2. If CLAUDE_CODE_OAUTH_TOKEN set → use OAuth
3. If CLAUDE_CODE_OAUTH_TOKEN_FILE_DESCRIPTOR set → read OAuth from fd
4. If credential store has claudeAiOauth with valid scopes → use OAuth
5. If ANTHROPIC_API_KEY set → use API key
6. If CLAUDE_CODE_API_KEY_FILE_DESCRIPTOR set → read API key from fd
7. Error: no credentials found
```

---

## OAuth Scope Validation

To determine if credentials are for subscription (vs API key), check scopes.

**Required scope for subscription:** `"user:inference"`

```python
def is_subscription_auth(credentials):
    scopes = credentials.get("scopes", [])
    return "user:inference" in scopes
```

**All Claude.ai OAuth scopes:**
- `user:inference` - Can make inference requests
- `user:profile` - Can read profile info
- `user:sessions:claude_code` - Claude Code session access

---

## Token Refresh

OAuth tokens expire. The `expiresAt` field is a Unix timestamp in milliseconds.

**Check expiration:**
```python
import time

def is_expired(credentials):
    expires_at = credentials.get("expiresAt")
    if not expires_at:
        return False
    # Add 5 minute buffer
    return (time.time() * 1000) >= (expires_at - 300000)
```

**Refresh endpoint:**
```
POST https://console.anthropic.com/v1/oauth/token
Content-Type: application/x-www-form-urlencoded

grant_type=refresh_token
refresh_token={refresh_token}
client_id=9d1c250a-e61b-44d9-88ed-5944d1962f5e
```

**Response:**
```json
{
  "access_token": "sk-ant-oat01-...",
  "refresh_token": "sk-ant-ort01-...",
  "expires_in": 3600,
  "token_type": "Bearer"
}
```

---

## Profile Endpoint

To get account and organization UUIDs (needed for API requests):

```
GET https://api.anthropic.com/api/oauth/profile
Authorization: Bearer {access_token}
Content-Type: application/json
```

**Response:**
```json
{
  "account": {
    "uuid": "152384b9-6910-418c-bf4e-6000e30eb7da",
    "email": "user@example.com",
    "display_name": "User Name",
    "has_claude_max": true
  },
  "organization": {
    "uuid": "0eb4a023-24ee-4dc6-ac7e-84aca01fe723",
    "name": "Organization Name",
    "organization_type": "claude_max",
    "rate_limit_tier": "default_claude_max_5x"
  }
}
```

---

## Implementation Pseudocode

```python
class CredentialLoader:
    def __init__(self):
        self.config_dir = os.environ.get("CLAUDE_CONFIG_DIR") or Path.home() / ".claude"

    def load_oauth_credentials(self) -> Optional[OAuthCredentials]:
        # 1. Check env var
        if token := os.environ.get("CLAUDE_CODE_OAUTH_TOKEN"):
            return OAuthCredentials(access_token=token, scopes=["user:inference"])

        # 2. Check file descriptor
        if fd := os.environ.get("CLAUDE_CODE_OAUTH_TOKEN_FILE_DESCRIPTOR"):
            token = self._read_from_fd(int(fd))
            if token:
                return OAuthCredentials(access_token=token, scopes=["user:inference"])

        # 3. Read from credential store
        creds = self._read_credential_store()
        if creds and "claudeAiOauth" in creds:
            oauth = creds["claudeAiOauth"]
            if oauth.get("accessToken"):
                return OAuthCredentials(**oauth)

        return None

    def _read_credential_store(self) -> Optional[dict]:
        # macOS: try keychain first
        if sys.platform == "darwin":
            try:
                result = subprocess.run(
                    ["security", "find-generic-password",
                     "-a", os.environ.get("USER", getpass.getuser()),
                     "-w", "-s", self._get_keychain_service_name()],
                    capture_output=True, text=True
                )
                if result.returncode == 0:
                    return json.loads(result.stdout.strip())
            except:
                pass

        # Fallback: plaintext file
        creds_file = self.config_dir / ".credentials.json"
        if creds_file.exists():
            return json.loads(creds_file.read_text())

        return None

    def _get_keychain_service_name(self) -> str:
        base = "Claude Code-credentials"
        if os.environ.get("CLAUDE_CONFIG_DIR"):
            suffix = hashlib.sha256(str(self.config_dir).encode()).hexdigest()[:8]
            return f"Claude Code-{suffix}-credentials"
        return base

    def _read_from_fd(self, fd: int) -> Optional[str]:
        if sys.platform in ("darwin", "freebsd"):
            path = f"/dev/fd/{fd}"
        else:
            path = f"/proc/self/fd/{fd}"
        try:
            return Path(path).read_text().strip()
        except:
            return None

    def load_device_id(self) -> str:
        config_file = Path.home() / ".claude.json"
        if config_file.exists():
            data = json.loads(config_file.read_text())
            if "userID" in data:
                return data["userID"]
        # Generate new device ID
        return secrets.token_hex(32)
```

---

## Error Cases

| Scenario | Behavior |
|----------|----------|
| No credentials found | Raise error or prompt login |
| Keychain access denied (macOS) | Fall back to plaintext file |
| Token expired | Attempt refresh, re-authenticate if refresh fails |
| Invalid scopes | Treat as no subscription, fall back to API key |
| Malformed JSON | Treat as no credentials |
| File permissions error | Raise error |

---

## Constants Reference

```python
# OAuth
CLIENT_ID = "9d1c250a-e61b-44d9-88ed-5944d1962f5e"
TOKEN_URL = "https://console.anthropic.com/v1/oauth/token"
PROFILE_URL = "https://api.anthropic.com/api/oauth/profile"

# Scopes
SCOPE_INFERENCE = "user:inference"
SCOPE_PROFILE = "user:profile"
SCOPE_SESSIONS = "user:sessions:claude_code"

# Token prefixes
PREFIX_OAUTH_ACCESS = "sk-ant-oat01-"
PREFIX_OAUTH_REFRESH = "sk-ant-ort01-"
PREFIX_API_KEY = "sk-ant-api03-"
```
