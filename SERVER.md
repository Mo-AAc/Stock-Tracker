# Server setup — Stock Tracker

**Status:** deployed and running on the shared `python` host.
**Provenance:** sourced from `_platform/PLATFORM.md`, which was verified against the live host
on **2026-07-29**. Nothing here was re-checked against the host when this file was written —
in particular, the claims about *which* repo and branch the server tracks come from
`PLATFORM.md` §3 and §9, not from an inspection of `/opt/StockTracker`.

> ## ⚠ Before you commit anything in this repo
>
> This working tree has two remotes. `origin` is the **public upstream**
> `sara03alaraj/Stock-Tracker`; `fork` is `Mo-AAc/Stock-Tracker`, which is what the server
> actually deploys from. Local `main` currently **tracks `origin/main`** and is ahead by one
> commit.
>
> This file contains internal infrastructure detail (LAN address, service user, `/opt`
> paths). Commit it only on a branch tracking **`fork`**, and re-point `main` at `fork`
> before doing routine work here — otherwise a `git push` aims at a third party's public
> repository.

This file is the project-scoped extract. The authoritative cross-project reference is
`_platform/PLATFORM.md` — on the workstation at `C:\Dev\_platform\PLATFORM.md`, which is
outside this repo and therefore not present in the server checkout at `/opt/StockTracker`.
**If anything here conflicts with `PLATFORM.md`, `PLATFORM.md` wins.**

`deployment.md` in this repo describes a *generic* Ubuntu install (`streamlit run`, `screen`,
"consider systemd"). That is **not** how this app runs — see §5.

---

## 1. Where it runs

| Fact | Value |
|---|---|
| Host | `python` — Ubuntu 24.04.4 LTS, a **Hyper-V guest** on a Contabo dedicated server (not a VPS) |
| Reachable from | The office LAN only, at `192.168.4.9`. There is **no public URL** |
| URL | `http://192.168.4.9/stocks/` |
| App dir | `/opt/StockTracker` |
| venv | `/opt/StockTracker/.venv` |
| Service user | `stockapp` (system account, `nologin` shell) |
| systemd unit | `stock-tracker` |
| Internal bind | `127.0.0.1:8501` — Streamlit, localhost only |
| Persistence | `last_run.json` in the app dir — **tracked in git but rewritten by the app** |
| Repo deployed | `Mo-AAc/Stock-Tracker` (the **fork**), branch `main` |
| Extra deps file | `/opt/stocktracker-extra-requirements.txt` — on the server, not in git |
| nginx | `location /stocks/` inside `sites-available/gi-qa-tool` |
| Timezone | Host is **UTC**; workstations are UTC+3 — matters for schedule debugging |

**Never edit `sites-available/gi-qa-tool`.** It serves this app, the GI QA Tool (`/`) and
Excel Unprotect (`/unprotect/`). A mistake in it takes down three production tools at once.

---

## 2. The silent-outage trap — do not re-break this

`scrape_jordan_disclosures()` imports `selenium` and `webdriver-manager` **inside the
function**, wrapped in a broad `except Exception`. The server also needs a real
`google-chrome-stable` binary. When any of the three is missing, the `ModuleNotFoundError`
is swallowed, the function returns an empty list, and the app reports **`0 updates found`
instantly and successfully** — while `systemctl status` shows `active (running)`.

That hid **ten days** of missing ASE data.

Mitigations now in place — all three matter:

1. The server tracks the **fork** (per `PLATFORM.md` §3/§9), and this local checkout's
   `requirements.txt` does list `selenium` and `webdriver-manager` — verified by reading it.
   Upstream PR #1 has since been merged (`9663cf0`, verified 2026-08-27), so a fresh
   clone of `sara03alaraj/Stock-Tracker` no longer reproduces the outage from this
   cause alone. The host still needs `google-chrome-stable` either way.
2. `/opt/stocktracker-extra-requirements.txt` is a belt-and-braces backup install.
3. `Environment=PYTHONUNBUFFERED=1` in the systemd unit is **mandatory**. Without it,
   `print()` output sits in an 8 KB buffer for hours. *A burst of identical log lines all
   stamped to the same second means that variable is missing.*

**If you touch the scraper:** do not widen that `except`, and do not add a new optional
import behind a broad handler. An unavailable dependency must fail loudly. `0 updates found`
returning instantly is the signature of this bug, not of a quiet news day.

---

## 3. Constraints and runtime behaviour

**Streamlit needs WebSocket headers through nginx.** `/stocks/` requires
`proxy_set_header Upgrade $http_upgrade;` and `Connection "upgrade";`, a long
`proxy_read_timeout`, and a **separate `location /stocks/_stcore/stream` block**. Without
them the page loads but nothing is ever interactive — buttons do nothing, spinners never
resolve.

**`last_run.json` is tracked in git and rewritten by the app**, so it blocks every `git
pull`. Back it up and `git checkout --` it before pulling (§4). Do not add more
app-written files to git.

**A full Jordan run takes 15–25 minutes** — 17 symbols, a Chrome instance each. To tell
healthy from stuck:

```bash
ps -u stockapp -o pid,etime,comm | grep chromedriver     # run twice, 30s apart
```

A **changing PID** means progress. Process *count* is useless — every symbol's Chrome tree
has the same 12 processes.

---

## 4. Deploy

```bash
cd /opt/StockTracker
cp last_run.json /root/last_run_backup_$(date +%Y%m%d).json
sudo -u stockapp git checkout -- last_run.json   # tracked but app-rewritten; always blocks the pull
sudo -u stockapp git pull
sudo -u stockapp .venv/bin/pip install -r requirements.txt
sudo -u stockapp .venv/bin/pip install -r /opt/stocktracker-extra-requirements.txt
sudo -u stockapp test -f .streamlit/secrets.toml || echo 'MISSING: create it per section 6 before restarting'
sudo systemctl restart stock-tracker
```

**Do not skip the second `pip install`** — omitting it reproduces the outage in §2.

`stockapp`'s shell is `nologin`, so use `sudo -u stockapp <cmd>`; `sudo -iu` fails. Pulling
as `root` creates root-owned files that later block `stockapp` from writing.

**Rollback:** the folder snapshot `/opt/StockTracker_stable` is instant, offline, and
*includes* the venv — swap it in with `mv`. **Do not delete it**; it is the recovery path,
not clutter.

---

## 5. Health checks

```bash
systemctl is-active stock-tracker nginx
journalctl -u stock-tracker -n 50 --no-pager
ss -tlnp | grep ':8501 '
```

| Symptom | Cause | Fix |
|---|---|---|
| `0 updates found`, instantly | Swallowed `ModuleNotFoundError` (§2) | Install `selenium`, `webdriver-manager`, `google-chrome-stable` |
| Identical log lines all on the same second | `PYTHONUNBUFFERED=1` missing from the unit | Add it, `daemon-reload`, restart |
| `/stocks/` loads but nothing is interactive | Missing WebSocket headers | Add `Upgrade` / `Connection "upgrade"` + the `_stcore/stream` block |
| `/stocks/` returns another app's 404 | nginx not reloaded — `nginx -t` only validates the file on disk | `nginx -t && systemctl reload nginx` |
| `502 Bad Gateway` | Streamlit process down | `systemctl status stock-tracker`; `journalctl -u stock-tracker -n 50` |
| Login page 500s, or `KeyError: 'stock_tracker_auth'` in the log | `secrets.toml` missing or unreadable by `stockapp` | Recreate it per §6; `chown stockapp` and `chmod 600` |
| Login succeeds but every reload asks again | Cookie path mismatch, or the app is reached on a URL other than `/stocks/` | Cookie is scoped to `/stocks/`; confirm the URL and `auth.COOKIE_PATH` agree |
| `git pull` blocked | `last_run.json` | Back it up, `git checkout --` it, pull |
| `git pull` asks for a password | Remote reverted to HTTPS, or wrong user | `git remote -v`; always `sudo -u stockapp` |

### Corrections to `deployment.md`

| Says | Reality |
|---|---|
| "ready to deploy … after installing the required Python dependencies" | Also needs `google-chrome-stable` on the host. `pip install` alone is not enough — §2 |
| Python packages list (8 entries, no selenium) | `requirements.txt` in this checkout now also lists `selenium` and `webdriver-manager` |
| "Run the Streamlit app: `streamlit run scraper_app.py`" | Production runs under the systemd unit `stock-tracker`, as `stockapp`, bound to `127.0.0.1:8501` |
| "consider using a process manager such as `systemd`, `tmux`, or `screen`" | Settled: systemd, with `Environment=PYTHONUNBUFFERED=1` as a hard requirement |
| "Do not deploy … `last_run.json`" | It **is** on the server and is the app's state file. Back it up before every pull |
| Nothing about nginx | Served at `/stocks/` behind nginx, which needs WebSocket headers — §3 |

---

## 6. Authentication and the login secret

The app authenticates **in the page**, not at the proxy. `auth.py` checks the submitted
username and password against `[stock_tracker_auth]` in `/opt/StockTracker/.streamlit/secrets.toml`
and, on success, issues an HMAC-signed token stored as the `stock_tracker_session` cookie
(path `/stocks/`, 30-day expiry, expiry inside the signed payload). No URL ever carries
authentication state, so a copied link grants nothing.

**`secrets.toml` is gitignored and exists only on the server.** It is not in any repo, not in
`/opt/StockTracker_stable`, and is **not restored by a rollback** — keep an offline copy.
`.streamlit/secrets.toml.example` in the repo is a template with placeholder values only.

### Creating or rotating the credential

Run on the host, as `stockapp`. Type the password directly; do not paste it into a shell
history file or a ticket.

```bash
cd /opt/StockTracker
sudo -u stockapp .venv/bin/python -c "import secrets; print(secrets.token_hex(32))"   # cookie_key
sudo -u stockapp nano .streamlit/secrets.toml
sudo chmod 600 .streamlit/secrets.toml
sudo systemctl restart stock-tracker
```

```toml
[stock_tracker_auth]
username = "admin"
password = "server-only password"
cookie_key = "the 64-char hex string generated above"
```

Changing `cookie_key` invalidates every existing session and forces all browsers to log in
again — that is the correct move whenever the password is rotated for a suspected leak, since
the password alone does not invalidate cookies already issued.

### Removing nginx Basic Auth (after cookie login is verified)

Basic Auth is the current gate and **stays up until the new login is confirmed working**, so
there is never an unauthenticated interval. Once `/stocks/` shows the in-page login, accepts
the new password, and still shows the tracker after a browser restart:

1. In `sites-available/gi-qa-tool`, remove `auth_basic` and `auth_basic_user_file` from
   **both** `location /stocks/` and `location /stocks/_stcore/stream` — together, in one edit.
   Leaving it on the `_stcore/stream` block alone breaks the WebSocket with a silent 401 and
   the page loads but never becomes interactive (§3).
2. `sudo nginx -t && sudo systemctl reload nginx`.

**That file also serves the GI QA Tool (`/`) and Excel Unprotect (`/unprotect/`)** — back it
up first and change nothing else in it. This is a hand edit for an operator, not an automated
step.

---

## 7. Security posture

The old credential `admin` / the password committed in `scraper_app.py` before 2026-08-27 is
**permanently compromised** — it is in the public upstream repo's history and cannot be
unpublished. It must never be reused anywhere. The replacement lives only in the server's
untracked `secrets.toml` (§6).

There is still **no TLS anywhere on this host**, so the password and the session cookie both
cross the LAN in plaintext. The login is a soft lock against casual access, not a security
boundary.

This is tolerable only because the host is not internet-reachable (proven 2026-07-29, not
assumed). TLS remains an open platform workstream. Do not hardcode a secret in source again,
and do not treat the login as protection when deciding what this app may access.
