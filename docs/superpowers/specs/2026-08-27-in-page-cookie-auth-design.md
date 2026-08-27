# In-Page Persistent Authentication Design

## Goal

Keep the Stock Tracker's in-page username/password screen while persisting a successful login
in the browser and never accepting authentication state from a URL.

## Chosen approach

The Streamlit app will use a cookie component to set and remove an encrypted, signed login
cookie. The app will validate the cookie before rendering the tracker and will only create it
after a successful username/password check.

The password and cookie-signing key will be read from the server's untracked
`.streamlit/secrets.toml`; neither will be committed. The cookie is scoped to `/stocks/`, has a
30-day expiry, and is cleared by the in-page Logout button.

## Request flow

1. A new browser session loads `/stocks/` with no login cookie and sees the in-page login form.
2. The form checks the configured username and password using constant-time comparison.
3. On success, the app sets the signed cookie and reruns without query parameters.
4. Later visits validate the cookie and load the tracker automatically.
5. Logout deletes the cookie and reruns to the login form.

## Deployment transition

nginx Basic Auth remains enabled until the cookie-auth version has been pulled, restarted, and
verified. It is then removed from both `/stocks/` and `/stocks/_stcore/stream` together, followed
by `nginx -t` and reload. This prevents an unauthenticated interval.

## Verification

Automated tests will cover login-cookie creation, cookie validation, rejection of invalid or
expired cookies, logout deletion, and the absence of query-parameter authentication. Manual
verification will use a fresh private browser session: login once, open a new tab successfully,
copy a URL into another unauthenticated browser, and confirm it still shows the login form.
