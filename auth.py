"""Signed-cookie authentication for the Stock Tracker.

The username, password and cookie signing key live in the server's untracked
`.streamlit/secrets.toml` under `[stock_tracker_auth]`; nothing secret is ever
committed. A successful login issues an HMAC-signed token whose expiry is part
of the signed payload, so a browser cannot extend its own session.

Secrets are read inside the accessor functions rather than at import time: a
missing `secrets.toml` must raise where it can be diagnosed, and must never be
silently downgraded into "no authentication".
"""

from __future__ import annotations

import base64
import binascii
import hmac
import json
from hashlib import sha256
from typing import Any

import streamlit as st

COOKIE_NAME = "stock_tracker_session"
COOKIE_PATH = "/stocks/"
SESSION_MAX_AGE_SECONDS = 30 * 24 * 60 * 60  # 30 days
SESSION_STATE_KEY = "stock_tracker_authenticated"
SECRETS_SECTION = "stock_tracker_auth"

_CLAIM_USERNAME = "u"
_CLAIM_EXPIRES_AT = "exp"


def _secret(key: str) -> str:
    """Read one server-only secret. Raises loudly when it is not configured."""
    return str(st.secrets[SECRETS_SECTION][key])


def configured_username() -> str:
    return _secret("username")


def configured_password() -> str:
    return _secret("password")


def _signing_key() -> bytes:
    return _secret("cookie_key").encode("utf-8")


def check_credentials(username: str, password: str) -> bool:
    """Validate a login attempt in constant time."""
    if not username or not password:
        return False
    username_ok = hmac.compare_digest(username, configured_username())
    password_ok = hmac.compare_digest(password, configured_password())
    return username_ok and password_ok


def _encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _decode(encoded: str) -> bytes:
    padding = "=" * (-len(encoded) % 4)
    return base64.urlsafe_b64decode(encoded + padding)


def _sign(payload: str) -> str:
    return hmac.new(_signing_key(), payload.encode("ascii"), sha256).hexdigest()


def issue_session(now: float) -> str:
    """Create a signed session token for the configured user."""
    claims: dict[str, Any] = {
        _CLAIM_USERNAME: configured_username(),
        _CLAIM_EXPIRES_AT: now + SESSION_MAX_AGE_SECONDS,
    }
    payload = _encode(json.dumps(claims, separators=(",", ":")).encode("utf-8"))
    return f"{payload}.{_sign(payload)}"


def is_authenticated(token: str | None, now: float) -> bool:
    """Return True only for an unexpired token signed with the server's key."""
    if not token or "." not in token:
        return False

    payload, _, signature = token.partition(".")
    if not hmac.compare_digest(signature, _sign(payload)):
        return False

    try:
        claims = json.loads(_decode(payload))
    except (binascii.Error, ValueError):
        # A malformed payload is an invalid session, not a server fault.
        return False

    if not isinstance(claims, dict):
        return False

    expires_at = claims.get(_CLAIM_EXPIRES_AT)
    if not isinstance(expires_at, (int, float)) or now >= expires_at:
        return False

    username = claims.get(_CLAIM_USERNAME)
    return isinstance(username, str) and hmac.compare_digest(
        username, configured_username()
    )
