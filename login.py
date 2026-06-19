"""
login.py
--------
Handles the Sport5 / Google SSO authentication flow.

Fast path  : Opens a headless context and makes a test API call.
             If the session cookies in USER_DATA_DIR are still valid → done.

Slow path  : Opens a VISIBLE Chromium window, navigates to Sport5, and
             calls page.wait_for_url("**/my-team", timeout=0) which blocks
             INDEFINITELY until the user completes Google login and the
             browser lands on the /my-team dashboard page.
             Only then are the session cookies flushed to disk and the
             headed context closed.
"""

import sys
import time

from playwright.sync_api import BrowserContext

from config import USER_DATA_DIR, SEASON_ID

# Sport5 home / login entry point
_LOGIN_URL = "https://dreamteam.sport5.co.il"

# API endpoint used to verify the session is authenticated
# (the same endpoint #1 used by the scraper)
_AUTH_TEST_URL = (
    f"https://dreamteam.sport5.co.il/api/Leagues/Get?seasonId={SEASON_ID}"
)


# ─────────────────────────────────────────────────────────────────────────────
#  Internal: test whether a context has a valid authenticated session
# ─────────────────────────────────────────────────────────────────────────────

def _is_authenticated(context: BrowserContext) -> bool:
    """
    Returns True when the context can successfully call the Sport5 API
    and receive a valid JSON response with data.

    Returns False if:
      - HTTP status != 200
      - Response body is HTML (JSON decode error → unauthenticated redirect)
      - Response data is empty / missing
    """
    try:
        resp = context.request.get(_AUTH_TEST_URL, timeout=10_000)
        if resp.status != 200:
            return False
        body = resp.json()                      # raises if HTML returned
        return bool(body.get("data"))           # empty data = not authed
    except Exception:
        return False                            # any failure = not authed


# ─────────────────────────────────────────────────────────────────────────────
#  Public entry point called by main.py
# ─────────────────────────────────────────────────────────────────────────────

def ensure_authenticated(playwright_instance) -> None:
    """
    Guarantees a valid Sport5 session exists in USER_DATA_DIR before
    the main monitoring loop starts.

    Raises RuntimeError only if an unexpected error occurs (not on timeout,
    since wait_for_url has timeout=0 i.e. waits forever).
    """

    # ── Fast path ────────────────────────────────────────────────────────────
    print("[login] בודק אם הסשן קיים ותקף...")
    ctx = playwright_instance.chromium.launch_persistent_context(
        user_data_dir = USER_DATA_DIR,
        headless      = True,
        args          = ["--no-sandbox"],
    )
    try:
        if _is_authenticated(ctx):
            print("[login] ✅ הסשן תקין – ממשיך במצב headless.\n")
            return
        print("[login] ⚠️  הסשן לא תקין – פותח דפדפן להתחברות...")
    finally:
        ctx.close()          # must close before opening another context on same dir

    # ── Slow path: headed browser, wait for /my-team ─────────────────────────
    print()
    print("=" * 60)
    print("  🔐 נדרשת התחברות ל-Sport5")
    print("  ייפתח חלון דפדפן — התחברו עם Google.")
    print("  הסקריפט יחכה עד שתגיעו לעמוד הקבוצה (/my-team).")
    print("=" * 60)
    print()

    ctx  = playwright_instance.chromium.launch_persistent_context(
        user_data_dir = USER_DATA_DIR,
        headless      = False,
        args          = ["--no-sandbox", "--start-maximized"],
        no_viewport   = True,
    )
    page = ctx.new_page()
    page.goto(_LOGIN_URL, wait_until="domcontentloaded")

    print("[login] ממתין לסיום ההתחברות... (הסקריפט יתקדם אוטומטית)")

    # ── BLOCKS HERE until the browser URL matches **/my-team ─────────────────
    # timeout=0 means wait forever — no timeout at all.
    page.wait_for_url("**/my-team", timeout=0)

    # Give Chromium 2 seconds to flush all session cookies to USER_DATA_DIR
    time.sleep(2)
    ctx.close()

    print()
    print("[login] ✅ התחברות הצליחה! הסשן נשמר.")
    print("[login] ממשיך במצב headless...\n")
