"""
login.py
--------
Handles the Sport5 / Google SSO authentication flow.

Fast path  : Opens a headless context and makes a test API call.
             If the session cookies in USER_DATA_DIR are still valid → done.

Slow path  : Opens a VISIBLE Chromium window, navigates to Sport5, and
             calls page.wait_for_url("**/my-team", timeout=0) which blocks
             INDEFINITELY until the user completes login and the browser
             lands on the /my-team dashboard page.
             Only then are the session cookies flushed to disk and the
             headed context closed.
"""

import sys
import time
import logging

from playwright.sync_api import BrowserContext

from config import USER_DATA_DIR, SEASON_ID, BASE_URL

logger = logging.getLogger(__name__)

# API endpoint used to verify the session is authenticated
_AUTH_TEST_URL = f"{BASE_URL}/api/Leagues/Get?seasonId={SEASON_ID}"

# Time (seconds) for Chromium to flush session cookies to disk after login
_SESSION_FLUSH_SECONDS = 2


# ─────────────────────────────────────────────────────────────────────────────
#  Session validation
# ─────────────────────────────────────────────────────────────────────────────

def is_authenticated(context: BrowserContext) -> bool:
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
#  Public entry point called by main.py and app.py
# ─────────────────────────────────────────────────────────────────────────────

def ensure_authenticated(playwright_instance) -> None:
    """
    Guarantees a valid Sport5 session exists in USER_DATA_DIR before
    the main monitoring loop starts.

    Raises SystemExit if a headed browser cannot be opened.
    """

    # ── Fast path ────────────────────────────────────────────────────────────
    logger.info("בודק אם הסשן קיים ותקף...")
    ctx = playwright_instance.chromium.launch_persistent_context(
        user_data_dir = USER_DATA_DIR,
        headless      = True,
        args          = ["--no-sandbox"],
    )
    try:
        if is_authenticated(ctx):
            logger.info("✅ הסשן תקין – ממשיך במצב headless.")
            return
        logger.warning("⚠️  הסשן לא תקין – פותח דפדפן להתחברות...")
    finally:
        ctx.close()          # must close before opening another context on same dir

    # ── Slow path: headed browser, wait for /my-team ─────────────────────────
    print()
    print("=" * 60)
    print("  🔐 נדרשת התחברות ל-Sport5")
    print("  ייפתח חלון דפדפן — עליכם להתחבר עם אימייל וסיסמה בלבד!")
    print("  ⚠️ שימו לב: התחברות באמצעות Google חסומה בדפדפנים אוטומטיים.")
    print("  הסקריפט יחכה עד שתגיעו לעמוד הקבוצה (/my-team).")
    print("=" * 60)
    print()

    try:
        ctx  = playwright_instance.chromium.launch_persistent_context(
            user_data_dir = USER_DATA_DIR,
            headless      = False,
            args          = ["--no-sandbox", "--start-maximized"],
            no_viewport   = True,
        )
    except Exception as exc:
        logger.error("לא ניתן לפתוח את חלון הדפדפן: %s", exc)
        print()
        print("❌ שגיאה: לא ניתן לפתוח את חלון הדפדפן.")
        print(f"   Details: {exc}")
        print("💡 טיפים לפתרון:")
        print("   1. אם אתה מריץ בסביבה ללא תצוגה גרפית (שרת לינוקס / Docker), בצע התחברות במחשבך האישי והעתק את תיקיית 'sport5_user_data' לכאן.")
        print("   2. ודא שתיקיית 'sport5_user_data' אינה נעולה על ידי תהליך כרום אחר שרץ ברקע.")
        print()
        sys.exit(1)

    try:
        page = ctx.new_page()
        page.goto(BASE_URL, wait_until="domcontentloaded")

        print("[login] ממתין לסיום ההתחברות... (הסקריפט יתקדם אוטומטית)")
        logger.info("ממתין לסיום ההתחברות...")

        # ── BLOCKS HERE until the browser URL matches **/my-team ─────────────
        # timeout=0 means wait forever — no timeout at all.
        page.wait_for_url("**/my-team", timeout=0)

        # Give Chromium time to flush all session cookies to USER_DATA_DIR
        time.sleep(_SESSION_FLUSH_SECONDS)
    finally:
        ctx.close()

    logger.info("✅ התחברות הצליחה! הסשן נשמר.")
    print()
    print("[login] ✅ התחברות הצליחה! הסשן נשמר.")
    print("[login] ממשיך במצב headless...\n")
