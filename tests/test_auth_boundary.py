"""Source-level guards on the Stock Tracker authentication boundary."""

from __future__ import annotations

import ast
from pathlib import Path
import unittest


APP_PATH = Path(__file__).resolve().parents[1] / "scraper_app.py"
AUTH_PATH = Path(__file__).resolve().parents[1] / "auth.py"


class AuthenticationBoundaryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.source = APP_PATH.read_text(encoding="utf-8")
        self.tree = ast.parse(self.source)

    def _function_names(self) -> set[str]:
        return {
            node.name
            for node in ast.walk(self.tree)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        }

    def test_app_renders_an_in_page_login(self) -> None:
        """Authentication is a page in the app, not a browser Basic Auth prompt."""
        self.assertIn("login", self._function_names())

    def test_app_delegates_credential_checks_to_the_auth_module(self) -> None:
        imported = {
            alias.name
            for node in ast.walk(self.tree)
            if isinstance(node, ast.Import)
            for alias in node.names
        }
        self.assertIn("auth", imported)

    def test_url_parameters_never_grant_access(self) -> None:
        """A copied URL must not carry a session to an unauthenticated browser."""
        self.assertNotIn("query_params", self.source)
        self.assertNotIn("?auth=", self.source)
        self.assertNotIn("?logout=", self.source)

    def test_no_credentials_are_hardcoded_in_the_app(self) -> None:
        names = {
            node.id for node in ast.walk(self.tree) if isinstance(node, ast.Name)
        }
        self.assertNotIn("CREDENTIALS", names)
        self.assertNotIn("AAC@2010", self.source)

    def test_no_credentials_are_hardcoded_in_the_auth_module(self) -> None:
        """Secrets come from the untracked secrets.toml, never from source."""
        auth_tree = ast.parse(AUTH_PATH.read_text(encoding="utf-8"))
        assignments = {
            target.id: node.value
            for node in ast.walk(auth_tree)
            if isinstance(node, ast.Assign)
            for target in node.targets
            if isinstance(target, ast.Name)
        }
        for secret_name in ("PASSWORD", "COOKIE_KEY", "SECRET_KEY", "CREDENTIALS"):
            self.assertNotIn(secret_name, assignments)


if __name__ == "__main__":
    unittest.main()
