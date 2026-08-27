# In-Page Cookie Authentication Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Restore a persistent in-page login without URL-based authentication.

**Architecture:** A focused authentication module reads server-only credentials, issues a signed 30-day cookie after valid login, and validates or clears it on each page load. `scraper_app.py` renders the login form or tracker based only on that module.

**Tech Stack:** Python, Streamlit, streamlit-cookies-controller, Python `unittest`.

---

### Task 1: Cookie authentication module

**Files:**
- Create: `auth.py`
- Create: `tests/test_auth.py`

- [ ] **Step 1: Write failing tests for valid and invalid signed sessions.**

```python
def test_valid_cookie_authenticates_admin(self):
    self.assertTrue(auth.is_authenticated({"username": "admin"}))

def test_invalid_cookie_is_rejected(self):
    self.assertFalse(auth.is_authenticated({"username": "other"}))
```

- [ ] **Step 2: Run the tests and confirm they fail because `auth` does not exist.**

Run: `python -m unittest tests.test_auth -v`

- [ ] **Step 3: Implement the minimal credential and session helpers.**

```python
def is_authenticated(session: dict[str, str] | None) -> bool:
    return session == {"username": configured_username()}
```

- [ ] **Step 4: Run the tests and confirm they pass.**

Run: `python -m unittest tests.test_auth -v`

### Task 2: Streamlit login and logout flow

**Files:**
- Modify: `scraper_app.py`
- Modify: `requirements.txt`
- Modify: `tests/test_auth_boundary.py`

- [ ] **Step 1: Write a failing source-boundary test requiring an in-page login and forbidding query-parameter authentication.**

```python
self.assertIn("def login", source)
self.assertNotIn("st.query_params", source)
```

- [ ] **Step 2: Run the test and confirm it fails because no login function exists.**

Run: `python -m unittest discover -s tests -v`

- [ ] **Step 3: Add the cookie component dependency and login/logout UI.**

```python
if not auth.is_authenticated(cookie.get(AUTH_COOKIE_NAME)):
    login(cookie)
else:
    main_app(cookie)
```

- [ ] **Step 4: Run all tests and syntax validation.**

Run: `python -m unittest discover -s tests -v && python -m py_compile auth.py scraper_app.py`

### Task 3: Deployment and verification

**Files:**
- Modify: `SERVER.md`

- [ ] **Step 1: Document the untracked server secrets and safe nginx removal sequence.**

```toml
[stock_tracker_auth]
username = "admin"
password = "server-only password"
cookie_key = "long random signing key"
```

- [ ] **Step 2: Review the final diff and run the complete verification suite.**

Run: `git diff --check && python -m unittest discover -s tests -v && python -m py_compile auth.py scraper_app.py`

- [ ] **Step 3: Commit the implementation.**

```bash
git add auth.py scraper_app.py requirements.txt tests SERVER.md
git commit -m "fix(auth): persist in-page login with signed cookie"
```
