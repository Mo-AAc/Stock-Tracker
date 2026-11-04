"""Unit tests for the signed-cookie session helpers."""

from __future__ import annotations

import sys
from pathlib import Path
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import auth


TEST_USERNAME = "admin"
TEST_PASSWORD = "correct horse battery staple"
TEST_KEY = "0123456789abcdef0123456789abcdef"
NOW = 1_700_000_000.0


def _patched_config():
    """Patch the secret readers so tests never need a secrets.toml."""
    return mock.patch.multiple(
        auth,
        configured_username=lambda: TEST_USERNAME,
        configured_password=lambda: TEST_PASSWORD,
        _signing_key=lambda: TEST_KEY.encode("utf-8"),
    )


class CredentialTests(unittest.TestCase):
    def setUp(self) -> None:
        patcher = _patched_config()
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_correct_credentials_are_accepted(self) -> None:
        self.assertTrue(auth.check_credentials(TEST_USERNAME, TEST_PASSWORD))

    def test_wrong_password_is_rejected(self) -> None:
        self.assertFalse(auth.check_credentials(TEST_USERNAME, "wrong"))

    def test_wrong_username_is_rejected(self) -> None:
        self.assertFalse(auth.check_credentials("other", TEST_PASSWORD))

    def test_empty_credentials_are_rejected(self) -> None:
        self.assertFalse(auth.check_credentials("", ""))


class SessionTokenTests(unittest.TestCase):
    def setUp(self) -> None:
        patcher = _patched_config()
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_issued_token_authenticates(self) -> None:
        token = auth.issue_session(now=NOW)
        self.assertTrue(auth.is_authenticated(token, now=NOW))

    def test_token_is_still_valid_just_before_expiry(self) -> None:
        token = auth.issue_session(now=NOW)
        self.assertTrue(
            auth.is_authenticated(token, now=NOW + auth.SESSION_MAX_AGE_SECONDS - 1)
        )

    def test_expired_token_is_rejected(self) -> None:
        token = auth.issue_session(now=NOW)
        self.assertFalse(
            auth.is_authenticated(token, now=NOW + auth.SESSION_MAX_AGE_SECONDS + 1)
        )

    def test_missing_token_is_rejected(self) -> None:
        self.assertFalse(auth.is_authenticated(None, now=NOW))
        self.assertFalse(auth.is_authenticated("", now=NOW))

    def test_forged_unsigned_payload_is_rejected(self) -> None:
        """A hand-crafted payload with no valid signature must not authenticate."""
        import base64
        import json

        payload = base64.urlsafe_b64encode(
            json.dumps({"u": TEST_USERNAME, "exp": NOW + 3600}).encode("utf-8")
        ).decode("ascii")
        self.assertFalse(auth.is_authenticated(payload, now=NOW))
        self.assertFalse(auth.is_authenticated(f"{payload}.deadbeef", now=NOW))

    def test_tampered_payload_is_rejected(self) -> None:
        """Editing the payload of a genuine token invalidates its signature."""
        import base64
        import json

        token = auth.issue_session(now=NOW)
        payload_b64, signature = token.split(".", 1)
        claims = json.loads(base64.urlsafe_b64decode(payload_b64 + "=="))
        claims["exp"] = NOW + 10 * auth.SESSION_MAX_AGE_SECONDS
        forged = base64.urlsafe_b64encode(
            json.dumps(claims).encode("utf-8")
        ).decode("ascii").rstrip("=")
        self.assertFalse(auth.is_authenticated(f"{forged}.{signature}", now=NOW))

    def test_token_signed_with_another_key_is_rejected(self) -> None:
        with mock.patch.object(auth, "_signing_key", lambda: b"a different key"):
            foreign_token = auth.issue_session(now=NOW)
        self.assertFalse(auth.is_authenticated(foreign_token, now=NOW))

    def test_token_for_another_username_is_rejected(self) -> None:
        with mock.patch.object(auth, "configured_username", lambda: "someone_else"):
            foreign_token = auth.issue_session(now=NOW)
        self.assertFalse(auth.is_authenticated(foreign_token, now=NOW))

    def test_malformed_tokens_are_rejected_without_raising(self) -> None:
        for junk in ("not-a-token", "...", "!!!.!!!", "a.b.c"):
            with self.subTest(junk=junk):
                self.assertFalse(auth.is_authenticated(junk, now=NOW))


if __name__ == "__main__":
    unittest.main()
