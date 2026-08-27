"""Regression checks for the Stock Tracker authentication boundary."""

from __future__ import annotations

import ast
from pathlib import Path
import unittest


APP_PATH = Path(__file__).resolve().parents[1] / "scraper_app.py"


class AuthenticationBoundaryTests(unittest.TestCase):
    def test_application_does_not_implement_or_bypass_authentication(self) -> None:
        """nginx owns authentication, so URLs and app state cannot grant access."""
        source = APP_PATH.read_text(encoding="utf-8")
        tree = ast.parse(source)
        names = {
            node.id
            for node in ast.walk(tree)
            if isinstance(node, ast.Name)
        }
        string_literals = {
            node.value
            for node in ast.walk(tree)
            if isinstance(node, ast.Constant) and isinstance(node.value, str)
        }

        self.assertNotIn("CREDENTIALS", names)
        self.assertNotIn("logged_in", string_literals)
        self.assertNotIn("auth", string_literals)
        self.assertNotIn("logout", string_literals)
        self.assertNotIn("query_params", source)
        self.assertNotIn("?auth=", source)
        self.assertNotIn("?logout=", source)


if __name__ == "__main__":
    unittest.main()
