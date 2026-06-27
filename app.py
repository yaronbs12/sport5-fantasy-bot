import streamlit as st
import json
import sys
import html
import os
import time
import requests
import urllib.parse
import base64
import shutil
import subprocess
import logging
from datetime import datetime
from collections import Counter
from playwright.sync_api import sync_playwright

from config import SEASON_ID, USER_DATA_DIR, LEAGUE_BLACKLIST, IL_TZ, BASE_URL
from display import format_bidi, normalize_league_name
from login import is_authenticated
from schedule_fetcher import fetch_live_schedule
from scraper import (
    create_browser_context,
    fetch_leagues_summary,
    fetch_all_squads,
    get_teams_mapping,
    fetch_active_round_dates,
    normalize_country_name,
    sanitize_player_name,
    filter_matches_by_date
)
from notifier import build_match_report

logger = logging.getLogger(__name__)


# Page configuration
st.set_page_config(
    page_title="Sport5 Fantasy Analytics Dashboard",
    page_icon="🏆",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# Configuration persistence helpers
CONFIG_PATH = os.path.join(os.getcwd(), "config.json")

def load_saved_league_id() -> str:
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
                return str(data.get("last_league_id", ""))
        except Exception:
            pass
    return ""

def save_league_id(league_id: str):
    try:
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump({"last_league_id": league_id}, f, ensure_ascii=False, indent=2)
    except Exception:
        pass

@st.cache_data(ttl=86400)
def get_logo_base64() -> str:
    """Fetch the Sport5 logo and encode it to Base64 to bypass client hotlink blocks."""
    try:
        r = requests.get(
            f"{BASE_URL}/assets/images/sport-5-logo.png",
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=5
        )
        if r.status_code == 200:
            encoded = base64.b64encode(r.content).decode("utf-8")
            return f"data:image/png;base64,{encoded}"
    except Exception:
        pass
    return f"{BASE_URL}/assets/images/sport-5-logo.png"

COUNTRY_TO_FLAG = {
    "גרמניה": "🇩🇪",
    "אנגליה": "🏴󠁧󠁢󠁥󠁮󠁧󠁿",
    "פורטוגל": "🇵🇹",
    "צ`כיה": "🇨🇿",
    "צ'כיה": "🇨🇿",
    "בלגיה": "🇧🇪",
    "הולנד": "🇳🇱",
    "קרואטיה": "🇭🇷",
    "שווייץ": "🇨🇭",
    "שוויץ": "🇨🇭",
    "סקוטלנד": "🏴󠁧󠁢󠁳󠁣󠁴󠁿",
    "ספרד": "🇪🇸",
    "צרפת": "🇫🇷",
    "טורקיה": "🇹🇷",
    "אוסטריה": "🇦🇹",
    "מקסיקו": "🇲🇽",
    "ברזיל": "🇧🇷",
    "פרגוואי": "🇵🇾",
    "שוודיה": "🇸🇪",
    "איראן": "🇮🇷",
    "אירן": "🇮🇷",
    "ארגנטינה": "🇦🇷",
    "גאנה": "🇬🇭",
    "קולומביה": "🇨🇴",
    "נורווגיה": "🇳🇴",
    "ערב הסעודית": "🇸🇦",
    "אקוואדור": "🇪🇨",
    "אקוודור": "🇪🇨",
    "ארה\"ב": "🇺🇸",
    "ארהב": "🇺🇸",
    "בוסניה והרצגובינה": "🇧🇦",
    "בוסניה": "🇧🇦",
    "דרום קוריאה": "🇰🇷",
    "קנדה": "🇨🇦",
    "מרוקו": "🇲🇦",
    "חוף השנהב": "🇨🇮",
    "יפן": "🇯🇵",
    "ניו זילנד": "🇳🇿",
    "אורוגוואי": "🇺🇾",
    "סנגל": "🇸🇳",
    "אלג`יריה": "🇩🇿",
    "אלג'יריה": "🇩🇿",
    "הרפובליקה הדמוקרטית של קונגו": "🇨🇩",
    "פנמה": "🇵🇦",
    "אוזבקיסטן": "🇺🇿",
    "ירדן": "🇯🇴",
    "עיראק": "🇮🇶",
    "כף ורדה": "🇨🇻",
    "מצרים": "🇪🇬",
    "תוניסיה": "🇹🇳",
    "קורוסאו": "🇨🇼",
    "אוסטרליה": "🇦🇺",
    "האיטי": "🇭🇹",
    "קטאר": "🇶🇦",
    "דרום אפריקה": "🇿🇦"
}

def get_flag_emoji(country_name: str) -> str:
    if not country_name:
        return ""
    cleaned = country_name.replace("`", "'").strip()
    return COUNTRY_TO_FLAG.get(cleaned, "")

def emoji_to_flagcdn_img(emoji_str: str) -> str:
    """Converts a flag emoji to a flagcdn.com HTML image tag for reliable Windows rendering."""
    iso_code = ""
    if emoji_str == "🏴󠁧󠁢󠁥󠁮󠁧󠁿":
        iso_code = "gb-eng"
    elif emoji_str == "🏴󠁧󠁢󠁳󠁣󠁴󠁿":
        iso_code = "gb-sct"
    elif emoji_str == "🏴󠁧󠁢󠁷󠁬󠁳󠁿":
        iso_code = "gb-wls"
    elif len(emoji_str) == 2 and 0x1F1E6 <= ord(emoji_str[0]) <= 0x1F1FF:
        iso_code = "".join(chr(ord(c) - 0x1F1E6 + ord('a')) for c in emoji_str)
        
    if iso_code:
        return f'<img src="https://flagcdn.com/w20/{iso_code}.png" height="12" alt="{emoji_str}" style="vertical-align: middle; margin-left: 3px; border-radius: 2px; display: inline-block;">'
    return emoji_str

def format_player_row_html(p_name: str, p_dict: dict) -> str:
    role = p_dict.get("role", "")
    nation = p_dict.get("nation", "")
    flag = get_flag_emoji(nation)
    
    badge_html = ""
    if role == "captain":
        badge_html = '<span style="background: linear-gradient(135deg, #ffd700 0%, #ffa500 100%); color: #000; font-size: 10px; font-weight: 800; padding: 2px 6px; border-radius: 4px; margin-right: 6px; display: inline-block;">C</span>'
    elif role == "sub_captain":
        badge_html = '<span style="background: linear-gradient(135deg, #c0c0c0 0%, #808080 100%); color: #fff; font-size: 10px; font-weight: 800; padding: 2px 6px; border-radius: 4px; margin-right: 6px; display: inline-block;">VC</span>'
        
    return f"""<div style="display: flex; align-items: center; justify-content: space-between; padding: 6px 10px; border-bottom: 1px solid var(--border-color); background-color: rgba(255,255,255,0.02); border-radius: 6px; margin-bottom: 4px; direction: rtl; text-align: right;">
<div style="display: flex; align-items: center; gap: 6px;">
<span style="font-size: 13px; font-weight: 500; color: var(--text-color);">{p_name}</span>
{badge_html}
</div>
<span style="color: var(--muted-text); font-size: 11px; display: flex; align-items: center;">{emoji_to_flagcdn_img(flag)} {nation}</span>
</div>"""

# -------------------------------------------------------------

# High-Performance Caching
# -------------------------------------------------------------
@st.cache_data(ttl=600, show_spinner="טוען נתוני ליגות ומחזורים...")
def fetch_metadata_cached():
    """Fetch user leagues list, teams mapping, and round dates, caching results for 10 minutes."""
    try:
        with sync_playwright() as pw:
            context = create_browser_context(pw)
            try:
                authed = is_authenticated(context)
                if not authed:
                    raise PermissionError("Session is not authenticated.")
                
                leagues = fetch_leagues_summary(context)
                teams_map = get_teams_mapping(context)
                active_round_dates = fetch_active_round_dates(context)
                if not leagues:
                    raise ValueError("Leagues list is empty.")
                return leagues, teams_map, active_round_dates
            finally:
                context.close()
    except Exception as exc:
        if isinstance(exc, PermissionError) or isinstance(exc, ValueError):
            raise exc
        raise RuntimeError(f"שגיאה בטעינת נתונים: {exc}")

@st.cache_data(ttl=600, show_spinner="טוען לוח משחקים של מונדיאל 2026...")
def fetch_live_schedule_cached():
    """Fetch live match schedule, caching results for 10 minutes."""
    return fetch_live_schedule(only_future=True)

@st.cache_data(ttl=600, show_spinner="מושך סגלים והרכבים מ-Sport5...")
def fetch_all_squads_cached(league_id: str):
    """Fetch all rosters for the chosen league, caching results for 10 minutes."""
    try:
        with sync_playwright() as pw:
            context = create_browser_context(pw)
            try:
                if not is_authenticated(context):
                    raise PermissionError("Session is not authenticated.")
                squads = fetch_all_squads(context, league_id=league_id)
                if not squads:
                    raise ValueError("No squads could be retrieved.")
                return squads
            finally:
                context.close()
    except Exception as exc:
        if isinstance(exc, PermissionError) or isinstance(exc, ValueError):
            raise exc
        raise RuntimeError(f"שגיאה במשיכת סגלים: {exc}")

# ─────────────────────────────────────────────────────────────────────────────
# Authentication Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _check_session_alive() -> tuple[bool, str]:
    """
    Directly verifies whether the saved Playwright session in USER_DATA_DIR
    is still authenticated with Sport5.

    Returns (True, "") on success.
    Returns (False, reason_str) on failure – reason_str is shown to the user.
    Never uses @st.cache_data – result must always be live.
    """
    if not os.path.exists(USER_DATA_DIR):
        return False, "no_session_dir"
    try:
        with sync_playwright() as pw:
            context = create_browser_context(pw)
            try:
                authed = is_authenticated(context)
            finally:
                context.close()
        if authed:
            return True, ""
        return False, "session_expired"
    except Exception as exc:
        err = str(exc).lower()
        if "permission" in err or "access" in err or "lock" in err:
            return False, "locked"
        return False, f"error:{exc}"


def _do_logout():
    """Fully clears session cookies, Streamlit cache, and all session_state."""
    # 1. Delete Playwright session files
    if os.path.exists(USER_DATA_DIR):
        try:
            shutil.rmtree(USER_DATA_DIR)
        except Exception:
            pass
    # 2. Clear all cached data
    st.cache_data.clear()
    # 3. Wipe entire session_state (not just auth_checked – prevents stale data)
    for key in list(st.session_state.keys()):
        del st.session_state[key]
    # 4. Rerun → session_state is empty → auth flow starts fresh
    st.rerun()


def _show_login_ui(reason: str = ""):
    """
    Renders the full-page login prompt.
    """

    # ── Login card ────────────────────────────────────────────────────────
    st.markdown("""<div style="max-width: 520px; margin: 40px auto; background: var(--card-bg); border: 1px solid var(--border-color); border-radius: 16px; padding: 40px; text-align: center; box-shadow: 0 8px 32px rgba(0,0,0,0.35);">
<div style="font-size: 3.5rem; margin-bottom: 16px;">🔐</div>
<h2 style="margin: 0 0 10px 0; font-size: 1.5rem; font-weight: 700; color: var(--text-color); direction: rtl;">נדרשת התחברות ל-Sport5</h2>

<div style="background: rgba(59, 130, 246, 0.12); border: 1px solid rgba(59, 130, 246, 0.4); border-radius: 10px; padding: 15px; margin: 20px 0; direction: rtl; text-align: right;">
<strong style="color: #3b82f6; font-size: 0.95rem; display: block; margin-bottom: 6px;">ℹ️ מידע חשוב לגבי ההתחברות:</strong>
<span style="color: var(--text-color); font-size: 0.88rem; line-height: 1.4;">
לא ניתן להתחבר עם חשבון Google או פייסבוק.<br>
הדרך היחידה להתחבר למערכת היא באמצעות <b>אימייל וסיסמה בלבד</b> של חשבון Sport5.
</span>
</div>

<p style="color: var(--muted-text); font-size: 0.92rem; margin: 0 0 20px 0; direction: rtl; text-align: right; line-height: 1.4;">
לחיצה על הכפתור מטה תפתח חלון דפדפן.<br>
הזינו את האימייל והסיסמה שלכם בטופס ההתחברות של Sport5, והמערכת תתחבר אוטומטית.
</p>
</div>""", unsafe_allow_html=True)

    col_l, col_c, col_r = st.columns([2, 2, 2])
    with col_c:
        if st.button("🚀 התחבר ל-Sport5", type="primary", use_container_width=True, key="login_btn"):
            with st.spinner("ממתין לסיום ההתחברות... התחבר עם אימייל וסיסמה בלבד בחלון שנפתח (Google חסום)."):
                login_ok = False
                login_err_msg = ""

                def run_playwright_login():
                    with sync_playwright() as pw:
                        ctx = pw.chromium.launch_persistent_context(
                            user_data_dir=USER_DATA_DIR,
                            headless=False,
                            args=["--no-sandbox", "--start-maximized"],
                            no_viewport=True,
                        )
                        try:
                            page = ctx.new_page()
                            page.goto("https://dreamteam.sport5.co.il", wait_until="domcontentloaded")
                            page.wait_for_url("**/my-team", timeout=0)
                            time.sleep(2.5)
                        finally:
                            ctx.close()

                try:
                    run_playwright_login()
                    login_ok = True
                except Exception as exc:
                    exc_str = str(exc).lower()
                    if "executable" in exc_str or "playwright" in exc_str:
                        # Auto-install Playwright's chromium
                        try:
                            subprocess.run(["python", "-m", "playwright", "install", "chromium"], check=True)
                            # Retry after auto-install
                            run_playwright_login()
                            login_ok = True
                        except Exception as retry_exc:
                            login_err_msg = "❌ שגיאה: לא ניתן להפעיל את רכיב הדפדפן. אנא פנה לתמיכה."
                    elif "permission" in exc_str or "access" in exc_str or "lock" in exc_str:
                        login_err_msg = "🔒 שגיאה: דפדפן ההתחברות כבר פתוח ברקע. אנא סגור כל חלון דפדפן אחר ונסה שוב."
                    else:
                        login_err_msg = "❌ ההתחברות נכשלה. אנא נסה שוב."

            if login_ok:
                st.cache_data.clear()
                st.rerun()
            else:
                st.error(login_err_msg)

def main():
    # Initialize Theme State
    if "theme" not in st.session_state:
        st.session_state.theme = "dark"

    # -------------------------------------------------------------
    # Theme CSS Configuration
    # -------------------------------------------------------------
    if st.session_state.theme == "light":
        theme_css = """
        :root {
            --bg-color: #ffffff;
            --card-bg: #f9fafb;
            --border-color: #e5e7eb;
            --text-color: #09090b;
            --accent-color: #ef4444;
            --muted-text: #64748b;
            --hover-bg: #f3f4f6;
        }
        """
    else:
        theme_css = """
        :root {
            --bg-color: #09090b;
            --card-bg: #121216;
            --border-color: #1f1f27;
            --text-color: #f4f4f5;
            --accent-color: #ef4444;
            --muted-text: #8e8e9f;
            --hover-bg: #1c1c24;
        }
        """

    # Injecting Dynamic CSS
    st.markdown(f"""
    <style>
        @import url('https://fonts.googleapis.com/css2?family=Rubik:wght@300;400;500;600;700&display=swap');
        
        {theme_css}
        
        /* Apply fonts to standard text elements excluding icons */
        html, body, p, h1, h2, h3, h4, h5, h6, label, input, textarea, button, select {{
            font-family: 'Rubik', sans-serif;
        }}
        
        .stApp {{
            background-color: var(--bg-color) !important;
            color: var(--text-color) !important;
        }}
        
        /* Explicit Custom HTML Div Cards */
        .fantasy-card {{
            background-color: var(--card-bg) !important;
            border: 1px solid var(--border-color) !important;
            border-radius: 14px !important;
            padding: 24px !important;
            margin-bottom: 20px !important;
            box-shadow: 0 4px 20px rgba(0, 0, 0, 0.2) !important;
            transition: border-color 0.2s ease, box-shadow 0.2s ease !important;
        }}
        .fantasy-card:hover {{
            border-color: rgba(239, 68, 68, 0.3) !important;
            box-shadow: 0 4px 25px rgba(239, 68, 68, 0.05) !important;
        }}
        
        /* Force global Right-to-Left (RTL) and right-alignment for Hebrew text and widgets */
        p, span, label, li, ul, ol, h1, h2, h3, h4, h5, h6 {{
            direction: rtl !important;
            text-align: right !important;
        }}
        
        /* Widget Labels RTL */
        div[data-testid="stWidgetLabel"], 
        div[data-testid="stWidgetLabel"] p, 
        div[data-testid="stWidgetLabel"] label, 
        .stSlider label, 
        .stTextInput label, 
        .stSelectbox label {{
            direction: rtl !important;
            text-align: right !important;
            display: block !important;
            width: 100% !important;
        }}

        /* Input Form Polishing & RTL Alignment */
        .stTextInput input, .stNumberInput input, .stTextArea textarea {{
            background-color: var(--bg-color) !important;
            border: 1px solid var(--border-color) !important;
            color: var(--text-color) !important;
            border-radius: 8px !important;
            padding: 10px !important;
            direction: rtl !important;
            text-align: right !important;
        }}
        .stTextInput input:focus, .stTextArea textarea:focus {{
            border-color: var(--accent-color) !important;
            box-shadow: 0 0 0 1px var(--accent-color) !important;
        }}

        /* Keep button text centered, despite global RTL overrides */
        button, button div, button span, div.stButton > button, div.stButton > button * {{
            text-align: center !important;
        }}

        /* Tooltip and Help Icons RTL */
        div[data-testid="stTooltipHoverTarget"],
        div[data-testid="stTooltipHoverTarget"] div,
        div[data-testid="stTooltipIcon"],
        div[role="tooltip"],
        div[role="tooltip"] div,
        div[role="tooltip"] p {{
            direction: rtl !important;
            text-align: right !important;
        }}

        /* Expanders RTL */
        div[data-testid="stExpander"] details summary, 
        div[data-testid="stExpander"] details summary p,
        div[data-testid="stExpander"] details summary div,
        div[data-testid="stExpander"] p {{
            direction: rtl !important;
            text-align: right !important;
        }}

        /* Slider Styling */
        div[data-testid="stSlider"] [data-testid="stThumb"] {{
            background-color: var(--accent-color) !important;
            border: 2px solid var(--card-bg) !important;
            box-shadow: 0 0 10px rgba(239, 68, 68, 0.5) !important;
        }}
        
        /* Tabs Styling */
        div[data-baseweb="tab-list"] {{
            gap: 8px !important;
        }}
        div[data-baseweb="tab-list"] button[data-baseweb="tab"],
        button[data-baseweb="tab"] {{
            background: transparent !important;
            color: var(--muted-text) !important;
            font-size: 15px !important;
            font-weight: 600 !important;
            border: 1px solid transparent !important;
            padding: 12px 24px !important;
            border-radius: 8px !important;
            margin-right: 6px !important;
            transition: all 0.25s ease !important;
        }}
        div[data-baseweb="tab-list"] button[data-baseweb="tab"]:hover,
        button[data-baseweb="tab"]:hover {{
            color: var(--text-color) !important;
            background-color: var(--hover-bg) !important;
        }}
        button[aria-selected="true"] {{
            color: #ffffff !important;
            background-color: var(--accent-color) !important;
            border: 1px solid var(--accent-color) !important;
            box-shadow: 0 4px 14px rgba(239, 68, 68, 0.4) !important;
        }}
        
        /* Headings */
        h1, h2, h3, p, span {{
            color: var(--text-color);
        }}
        h1, h2, h3 {{
            font-weight: 700 !important;
        }}
        
        /* Primary Buttons */
        div.stButton > button[kind="primary"], div.stButton > button[kind="secondary"] {{
            border: none !important;
            border-radius: 6px !important;
            font-size: 15px !important;
            padding: 8px 20px !important;
            transition: all 0.2s ease !important;
        }}
        div.stButton > button[kind="primary"] {{
            background-color: var(--accent-color) !important;
            color: #ffffff !important;
            font-weight: 600 !important;
        }}
        div.stButton > button[kind="secondary"] {{
            background-color: var(--card-bg) !important;
            border: 1px solid var(--border-color) !important;
            color: var(--text-color) !important;
            font-weight: 500 !important;
        }}
        div.stButton > button[kind="primary"]:hover, div.stButton > button[kind="secondary"]:hover {{
            opacity: 0.9 !important;
        }}
        
        /* Status Badges */
        .status-badge {{
            display: inline-block;
            background-color: rgba(16, 185, 129, 0.1) !important;
            color: #10b981 !important;
            border: 1px solid rgba(16, 185, 129, 0.2) !important;
            padding: 4px 12px !important;
            border-radius: 20px !important;
            font-size: 13px !important;
            font-weight: 500 !important;
            direction: rtl !important;
            text-align: right !important;
        }}
        .status-badge.disconnected {{
            background-color: rgba(239, 68, 68, 0.1) !important;
            color: #ef4444 !important;
            border: 1px solid rgba(239, 68, 68, 0.2) !important;
        }}
        
        /* Alerts, Notification, Info, Warning, Error cards */
        .stAlert,
        div[data-testid="stNotification"] {{
            direction: rtl !important;
            text-align: right !important;
            background-color: var(--card-bg) !important;
            border: 1px solid var(--border-color) !important;
            border-radius: 12px !important;
        }}
        
        .stAlert div, .stAlert p,
        div[data-testid="stNotification"] p, 
        div[data-testid="stNotification"] div {{
            direction: rtl !important;
            text-align: right !important;
            color: var(--text-color) !important;
        }}
        
        /* Make st.popover dropdown modal wider to fit 3-column comparisons */
        div[data-testid="stPopoverBody"] {{
            min-width: 650px !important;
            max-width: 95vw !important;
            direction: rtl !important;
        }}
        
        /* Eradicate the Scrollbar via CSS */
        textarea, .fantasy-card textarea, div[data-testid="stTextArea"] textarea {{
            overflow-y: hidden !important;
            resize: none !important;
            scrollbar-width: none !important; /* Firefox */
        }}
        textarea::-webkit-scrollbar, div[data-testid="stTextArea"] textarea::-webkit-scrollbar {{
            display: none !important; /* Chrome, Safari, Edge */
        }}
        iframe {{
            scrollbar-width: none !important;
        }}
        iframe::-webkit-scrollbar {{
            display: none !important;
        }}
        
        .logout-container {{
            text-align: center !important;
            display: flex !important;
            justify-content: center !important;
        }}
        .logout-container div.stButton {{
            text-align: center !important;
            display: flex !important;
            justify-content: center !important;
        }}
        .logout-container div.stButton > button {{
            background-color: rgba(239, 68, 68, 0.15) !important;
            color: #ef4444 !important;
            border: 1px solid rgba(239, 68, 68, 0.3) !important;
            font-size: 13.5px !important;
            font-weight: 600 !important;
            padding: 6px 16px !important;
            border-radius: 6px !important;
            transition: all 0.2s ease !important;
        }}
        .logout-container div.stButton > button:hover {{
            background-color: #ef4444 !important;
            color: #ffffff !important;
            border-color: #ef4444 !important;
            box-shadow: 0 0 12px rgba(239, 68, 68, 0.4) !important;
        }}
        
        /* Hide Sidebar UI Completely */
        [data-testid="collapsedControl"] {{
            display: none !important;
        }}
        [data-testid="stSidebar"] {{
            display: none !important;
        }}

        /* Hide Streamlit top bar, main menu, and watermark footer */
        #MainMenu {{
            visibility: hidden !important;
            display: none !important;
        }}
        footer {{
            visibility: hidden !important;
            display: none !important;
        }}
        [data-testid="stToolbar"] {{
            display: none !important;
        }}
        [data-testid="stDecoration"] {{
            display: none !important;
        }}

        /* Hide heading anchor links next to titles */
        a.header-anchor {{
            display: none !important;
        }}

        /* Smooth tab transition animation */
        @keyframes tabFadeIn {{
            from {{
                opacity: 0;
                transform: translateY(8px);
            }}
            to {{
                opacity: 1;
                transform: translateY(0);
            }}
        }}
        div[data-testid="stTabPanel"] [role="tabpanel"] {{
            animation: tabFadeIn 0.4s cubic-bezier(0.16, 1, 0.3, 1);
        }}

        /* Pulsing Live indicator */
        @keyframes pulseRed {{
            0% {{
                transform: scale(0.95);
                box-shadow: 0 0 0 0 rgba(239, 68, 68, 0.7);
            }}
            70% {{
                transform: scale(1);
                box-shadow: 0 0 0 6px rgba(239, 68, 68, 0);
            }}
            100% {{
                transform: scale(0.95);
                box-shadow: 0 0 0 0 rgba(239, 68, 68, 0);
            }}
        }}
        .live-dot {{
            display: inline-block;
            width: 8px;
            height: 8px;
            background-color: #ef4444;
            border-radius: 50%;
            animation: pulseRed 1.8s infinite;
        }}
    </style>
    """, unsafe_allow_html=True)

    # -------------------------------------------------------------
    # Header & Theme Switcher (No Sidebar)
    # -------------------------------------------------------------
    logo_src = get_logo_base64()
    st.markdown(f"""
        <div class="fantasy-card" style="
            display: flex; 
            align-items: center; 
            justify-content: space-between; 
            direction: rtl; 
            padding: 20px 25px; 
            background: linear-gradient(135deg, #09090b 0%, #1c0609 50%, #2e080e 100%); 
            border-right: 5px solid #ef4444 !important;
            border-top: 1px solid rgba(239, 68, 68, 0.2) !important;
            border-bottom: 1px solid rgba(239, 68, 68, 0.2) !important;
            border-left: 1px solid rgba(239, 68, 68, 0.2) !important;
            border-radius: 12px;
            margin-bottom: 25px;
            box-shadow: 0 10px 30px rgba(0, 0, 0, 0.35);
        ">
            <div style="text-align: right;">
                <div style="display: flex; align-items: center; gap: 8px; margin-bottom: 5px;">
                    <span class="live-dot"></span>
                    <span style="font-size: 0.75rem; color: #ef4444; font-weight: 700; letter-spacing: 1px; direction: rtl;">STUDIO LIVE</span>
                </div>
                <h1 style="margin: 0; font-size: 1.9rem; font-weight: 800; color: #ffffff; text-shadow: 0 2px 4px rgba(0,0,0,0.5);">Sport5 Fantasy Analytics</h1>
                <p style="margin: 5px 0 0 0; font-size: 0.95rem; color: #a1a1aa;">מערכת ניתוח וניהול משחקי מחזור ליגת החלומות - מונדיאל 2026</p>
            </div>
            <div style="display: flex; flex-direction: column; align-items: center; gap: 10px;">
                <img src="{logo_src}" style="height: 65px; filter: drop-shadow(0 0 10px rgba(239, 68, 68, 0.55));" />
                <div style="display: flex; gap: 8px; align-items: center; justify-content: center; flex-wrap: wrap;">
                    <span style="background: rgba(239,68,68,0.15); border: 1px solid rgba(239,68,68,0.35); color: #ef4444; font-size: 10px; font-weight: 700; padding: 2px 8px; border-radius: 4px; letter-spacing: 0.5px; font-family: monospace;">v1.0.0</span>
                    <a href="https://github.com/yaronbs12/sport5-fantasy-bot" target="_blank" style="color: #a1a1aa; text-decoration: none; font-size: 11px; font-weight: 500; display: inline-flex; align-items: center; gap: 3px;">⭐ GitHub</a>
                </div>
            </div>
        </div>
    """, unsafe_allow_html=True)
    
    # ── Session-state defaults (theme survives logout, rest is reset) ─────
    if "leagues" not in st.session_state:
        st.session_state.leagues = []
    if "teams_map" not in st.session_state:
        st.session_state.teams_map = {}
    if "schedule" not in st.session_state:
        st.session_state.schedule = []
    if "squads" not in st.session_state:
        st.session_state.squads = None
    if "reports_generated" not in st.session_state:
        st.session_state.reports_generated = False
    if "active_round_dates" not in st.session_state:
        st.session_state.active_round_dates = None
    if "show_compare_modal" not in st.session_state:
        st.session_state.show_compare_modal = False
    if "authenticated" not in st.session_state:
        st.session_state.authenticated = False

    # ── Fast guard: session directory missing → instant logout ───────────
    # This runs on EVERY rerun (cost: one os.path.exists call).
    # Catches: manual deletion of sport5_user_data, external logout, etc.
    if st.session_state.authenticated and not os.path.exists(USER_DATA_DIR):
        st.session_state.authenticated = False
        st.cache_data.clear()
        # Don't call _do_logout() here — session_state is already partly initialized
        # above. Just reset the flag and re-flow into the check below.
        st.rerun()

    # ── Authentication gate ───────────────────────────────────────────────
    # Run a LIVE session check on every cold start (no cache involved).
    # Once authenticated==True it is only unset by _do_logout().
    if not st.session_state.authenticated:
        with st.spinner("🔄 בודק סשן קיים..."):
            session_ok, fail_reason = _check_session_alive()

        if session_ok:
            # Session is valid → pull data from cache (fast path)
            try:
                leagues, teams_map, active_round = fetch_metadata_cached()
                st.session_state.leagues = leagues
                st.session_state.teams_map = teams_map
                st.session_state.active_round_dates = active_round
                st.session_state.schedule = fetch_live_schedule_cached()
                st.session_state.authenticated = True
                st.rerun()  # rerun so the main UI renders in authenticated mode
            except PermissionError:
                # Double-validation: if unauthenticated, reset state and cache, show login UI
                st.cache_data.clear()
                st.session_state.authenticated = False
                _show_login_ui()
                st.stop()
            except Exception as meta_exc:
                st.cache_data.clear()
                st.session_state.authenticated = False
                _show_login_ui()
                st.stop()
        else:
            # No valid session → show login screen quietly, stop rendering anything else
            _show_login_ui()
            st.stop()  # ← critical: nothing below this line runs

    # ── Status bar (shown only when authenticated == True) ────────────────
    st.markdown("""
        <div class="status-badge" style="margin-top: 5px; margin-bottom: 20px;">
            <span style="display:inline-block; width:6px; height:6px; border-radius:50%;
                         background-color:#10b981; margin-left: 6px;"></span>
            סשן מחובר לשרת
        </div>
    """, unsafe_allow_html=True)

    # -------------------------------------------------------------
    # Main Configuration Panel (Collapsible Settings)
    # -------------------------------------------------------------
    is_expanded = not st.session_state.get("reports_generated", False)

    with st.expander("⚙️ פאנל הגדרות ליגה ומחזור", expanded=is_expanded):
        col1, col2 = st.columns(2)
        
        with col1:
            st.markdown("<h3 style='direction:rtl; text-align:right;'>🔍 בחירת ליגה</h3>", unsafe_allow_html=True)
            league_search_query = st.text_input("🔍 הכנס את שם הליגה שלך (לדוגמה: ליגת האלופות)", value="").strip()
            manual_league_id = st.text_input(
                "🆔 מזהה ליגה (ID) — לגיבוי בלבד (אם החיפוש נכשל)", 
                value="",
                help="💡 איך מוצאים את ה-ID? נכנסים למסך הליגה המלא באתר ספורט 5, ומעתיקים את מספר ה-ID שמופיע בסוף כתובת ה-URL בחלון הדפדפן."
            ).strip()

            # Ensure these are always defined even when no search is performed
            selected_league_id = None
            resolved_league_name = ""
            
            if league_search_query:
                normalized_query = normalize_league_name(league_search_query)
                matches = []
                for lg in st.session_state.leagues:
                    api_name = lg.get("leagueName") or lg.get("name") or ""
                    if normalized_query in normalize_league_name(api_name):
                        matches.append(lg)
                        
                if len(matches) == 1:
                    m = matches[0]
                    st.success(f"✓ נמצאה ליגה: {m['leagueName']}")
                    selected_league_id = str(m["id"])
                    resolved_league_name = m.get("leagueName") or m.get("name") or ""
                elif len(matches) > 1:
                    options = {f"{m['leagueName']} (ID: {m['id']})": str(m["id"]) for m in matches}
                    selected_option = st.selectbox("בחר ליגה מהרשימה:", list(options.keys()))
                    selected_league_id = options[selected_option]
                    for m in matches:
                        if str(m["id"]) == selected_league_id:
                            resolved_league_name = m.get("leagueName") or m.get("name") or ""
                            break
                else:
                    st.warning("לא נמצאו ליגות תואמות. אנא נסה מזהה ידני.")
                    
            if not selected_league_id and manual_league_id:
                selected_league_id = manual_league_id
                matched_lg = next(
                    (lg for lg in st.session_state.leagues if lg and (str(lg.get("id")) == selected_league_id or str(lg.get("teamId")) == selected_league_id)),
                    None
                )
                if matched_lg:
                    resolved_league_name = matched_lg.get("leagueName") or matched_lg.get("name") or ""

            if selected_league_id:
                is_massive = False
                if selected_league_id.lower() in ("0", "null", "none"):
                    is_massive = True
                    
                is_blacklisted = False
                if resolved_league_name:
                    for phrase in LEAGUE_BLACKLIST:
                        if phrase in resolved_league_name:
                            is_blacklisted = True
                            break
                if league_search_query:
                    for phrase in LEAGUE_BLACKLIST:
                        if phrase in league_search_query:
                            is_blacklisted = True
                            break
                            
                if is_massive or is_blacklisted:
                    st.error("🚨 חסם בטיחות: הליגה שנבחרה המונית מדי או חסומה. הריצה הופסקה כדי למנוע קריסה וחסימת IP.")
                    selected_league_id = None
    
            if selected_league_id:
                save_league_id(selected_league_id)
                if resolved_league_name:
                    st.markdown(f"<div style='text-align: right; color: var(--muted-text); direction: rtl;'>ליגה פעילה: <b>{resolved_league_name}</b></div>", unsafe_allow_html=True)
    
        with col2:
            st.markdown("<h3 style='direction:rtl; text-align:right;'>📅 הגדרת מחזור</h3>", unsafe_allow_html=True)
            schedule = st.session_state.schedule
            
            # Apply early country mapping normalization
            for m in schedule:
                m["home_team"] = normalize_country_name(m["home_team"])
                m["away_team"] = normalize_country_name(m["away_team"])
            
            if schedule:
                sport5_start, sport5_end = None, None
                if st.session_state.active_round_dates:
                    s_str, e_str = st.session_state.active_round_dates
                    if s_str and e_str:
                        try:
                            sport5_start = datetime.fromisoformat(s_str).replace(tzinfo=IL_TZ)
                            sport5_end = datetime.fromisoformat(e_str).replace(tzinfo=IL_TZ)
                        except Exception:
                            pass
                
                if sport5_start and sport5_end:
                    filtered_schedule = filter_matches_by_date(schedule, sport5_start, sport5_end)
                    st.markdown(
                        f"<div style='text-align: right; font-size: 14px; direction: rtl; color: var(--muted-text);'>טווח זמני מחזור: <br><b>{sport5_start.strftime('%d/%m %H:%M')}</b> עד <b>{sport5_end.strftime('%d/%m %H:%M')}</b></div>",
                        unsafe_allow_html=True
                    )
                else:
                    first_match = schedule[0]
                    active_round_id = first_match["round_id"]
                    filtered_schedule = [m for m in schedule if m["round_id"] == active_round_id]
                    st.markdown(f"<div style='text-align: right; direction: rtl; color: var(--muted-text);'>מחזור: <b>{active_round_id}</b></div>", unsafe_allow_html=True)
                    
                max_matches_in_round = len(filtered_schedule)
                st.markdown(f"<div style='text-align: right; margin-bottom: 15px; direction: rtl; color: var(--text-color);'>סה״כ משחקים במחזור זה: <b>{max_matches_in_round}</b></div>", unsafe_allow_html=True)
                
                if max_matches_in_round > 0:
                    n_input = st.slider(
                        "מספר משחקים לניתוח (N):",
                        min_value=1,
                        max_value=max_matches_in_round,
                        value=min(3, max_matches_in_round)
                    )
                    selected_matches = filtered_schedule[:n_input]
                else:
                    st.warning("לא נמצאו משחקים בטווח הזמנים של מחזור זה.")
                    n_input = 0
                    selected_matches = []
            else:
                st.error("שגיאה בטעינת לוח המשחקים.")
                n_input = 0
                selected_matches = []
    
        # Reset state if selections changed
        if "last_league_id" not in st.session_state or st.session_state.last_league_id != selected_league_id:
            st.session_state.last_league_id = selected_league_id
            st.session_state.squads = None
            st.session_state.reports_generated = False
            
        if "last_n_input" not in st.session_state or st.session_state.last_n_input != n_input:
            st.session_state.last_n_input = n_input
            st.session_state.reports_generated = False
        
        # Generate action button
        if selected_league_id and selected_matches:
            if st.button("🏆 הפק דוחות למחזור הנוכחי", type="primary", use_container_width=True):
                status_placeholder = st.empty()
                status_placeholder.markdown("""
    <div style="position: fixed; top: 0; left: 0; width: 100vw; height: 100vh; background: rgba(9, 9, 11, 0.7); display: flex; flex-direction: column; align-items: center; justify-content: center; z-index: 999999; backdrop-filter: blur(4px);">
        <div style="display: flex; flex-direction: column; align-items: center; justify-content: center; padding: 40px 60px; background: var(--card-bg, #18181b); border: 1px solid var(--border-color, #27272a); border-radius: 16px; box-shadow: 0 10px 25px rgba(0,0,0,0.5);">
            <div class="football-loader" style="font-size: 70px; line-height: 1; user-select: none;">⚽</div>
            <div style="margin-top: 25px; font-size: 19px; font-weight: 600; text-align: center; color: var(--text-color, #f4f4f5);">
                🏃‍♂️💨 מכינים את המגרש ומנתחים סגלים... אנא המתן
            </div>
        </div>
    </div>
    
    <style>
    @keyframes football-bounce-spin {
        0%, 100% {
            transform: translateY(0) rotate(0deg) scale(1);
        }
        50% {
            transform: translateY(-25px) rotate(180deg) scale(1.1);
        }
    }
    .football-loader {
        animation: football-bounce-spin 1.2s infinite ease-in-out;
        display: inline-block;
    }
    </style>
    """, unsafe_allow_html=True)
                try:
                    squads = fetch_all_squads_cached(selected_league_id)
                    
                    if not squads:
                        st.error("🚨 לא נמצאו קבוצות בליגה זו. אנא ודא שחשבונך מחובר ורשום לליגה המבוקשת, או שה-ID שהזנת נכון.")
                    else:
                        # Normalize player nations inside squads
                        for squad in squads:
                            for p in squad.get("players", []):
                                p["nation"] = normalize_country_name(p["nation"])
                        st.session_state.squads = squads
                        st.session_state.reports_generated = True
                        st.rerun()
                except PermissionError:
                    # Session expired mid-session → full logout + show login screen
                    st.error("⏰ הסשן שלך פג תוקף תוך כדי הפעלה. מנתק ומנקה...")
                    time.sleep(1.5)
                    _do_logout()  # wipes everything and reruns to show login
                except Exception as e:
                    err_str = str(e)
                    if "got HTML instead of JSON" in err_str or "unauthenticated" in err_str.lower() or "401" in err_str:
                        # Session expired mid-session → full logout + show login screen
                        st.error("⏰ הסשן שלך פג תוקף תוך כדי הפעלה. מנתק ומנקה...")
                        time.sleep(1.5)
                        _do_logout()  # wipes everything and reruns to show login
                    else:
                        st.error(f"שגיאה בהפקת הדוחות: {e}")
                        st.session_state.reports_generated = False
                finally:
                    status_placeholder.empty()

    # -------------------------------------------------------------
    # Match Reports & League Analytics
    # -------------------------------------------------------------
    if st.session_state.reports_generated and st.session_state.squads and selected_matches:
        st.markdown("<br><hr style='border-color: var(--border-color);'><br>", unsafe_allow_html=True)
        
        # League Analytics Dashboard: "Most Popular Player" Component
        all_players = []
        for squad in st.session_state.squads:
            for p in squad.get("players", []):
                all_players.append(p["name"])
                
        if all_players:
            counter = Counter(all_players)
            most_common = counter.most_common()
            if most_common:
                true_total_teams = len(st.session_state.squads)
                top5 = most_common[:5]

                col_popular, col_compare_btn = st.columns([7.5, 2.5])
                with col_popular:
                    bars_html = ""
                    medals = ["🥇", "🥈", "🥉", "4️⃣", "5️⃣"]
                    for rank, (pname, pcount) in enumerate(top5):
                        pct = round(pcount / true_total_teams * 100) if true_total_teams > 0 else 0
                        medal = medals[rank]
                        bars_html += (
                            f'<div style="margin-bottom: 10px;">'
                            f'<div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 4px; direction: rtl;">'
                            f'<span style="font-size: 13px; font-weight: 600; color: var(--text-color);">{medal} {pname}</span>'
                            f'<span style="font-size: 12px; color: var(--muted-text);">{pcount}/{true_total_teams} ({pct}%)</span>'
                            f'</div>'
                            f'<div style="background: var(--border-color); border-radius: 4px; height: 6px; overflow: hidden;">'
                            f'<div style="width: {pct}%; height: 100%; background: linear-gradient(90deg, #ef4444, #f97316); border-radius: 4px;"></div>'
                            f'</div>'
                            f'</div>'
                        )
                    st.markdown(
                        f'<div class="fantasy-card" style="direction: rtl; text-align: right; margin-bottom: 0; padding: 18px 20px;">'
                        f'<p style="margin: 0 0 12px 0; font-size: 0.95rem; font-weight: 700; color: var(--text-color);">📊 שחקנים פופולריים בליגה (Top 5)</p>'
                        f'{bars_html}'
                        f'</div>',
                        unsafe_allow_html=True
                    )
                with col_compare_btn:
                    # Wrapped in div for vertical centering
                    st.markdown('<div style="height: 100%; display: flex; align-items: center; justify-content: center; padding-top: 10px;">', unsafe_allow_html=True)
                    with st.popover("👥 השוואת סגלים", use_container_width=True, key="squad_compare_popover"):
                        st.markdown("<h3 style='margin:0; font-size: 1.3rem; font-weight: 700; color: var(--text-color); text-align: center;'>👥 השוואת סגלים מהירה</h3>", unsafe_allow_html=True)
                        st.markdown("<hr style='border-color: var(--border-color); margin: 10px 0;'>", unsafe_allow_html=True)
                        
                        member_names = sorted([squad["user_name"] for squad in st.session_state.squads])
                        
                        col_sel_left, col_sel_right = st.columns(2)
                        with col_sel_left:
                            left_user = st.selectbox(
                                "בחר חבר ליגה א':", 
                                options=member_names,
                                index=None,
                                placeholder="בחר משתמש...",
                                key="compare_select_left"
                            )
                        with col_sel_right:
                            right_user = st.selectbox(
                                "בחר חבר ליגה ב':", 
                                options=member_names,
                                index=None,
                                placeholder="בחר משתמש...",
                                key="compare_select_right"
                            )
                            
                        if left_user and right_user:
                            if left_user == right_user:
                                st.warning("⚠️ אנא בחר שני משתמשים שונים להשוואה.")
                            else:
                                # Perform comparison logic
                                sq_left = next(s for s in st.session_state.squads if s["user_name"] == left_user)
                                sq_right = next(s for s in st.session_state.squads if s["user_name"] == right_user)
                                
                                players_l = {p["name"]: p for p in sq_left["players"]}
                                players_r = {p["name"]: p for p in sq_right["players"]}
                                
                                names_l = set(players_l.keys())
                                names_r = set(players_r.keys())
                                
                                shared_names = names_l.intersection(names_r)
                                only_l_names = names_l - names_r
                                only_r_names = names_r - names_l
                                
                                st.markdown("<br>", unsafe_allow_html=True)
                                col_res_l, col_res_shared, col_res_r = st.columns(3)
                                
                                with col_res_l:
                                    st.markdown(f"<h4 style='font-size:0.95rem; border-bottom: 2px solid #ef4444; padding-bottom:5px; color:#ef4444; font-weight:700;'>👈 רק ל-{left_user} ({len(only_l_names)})</h4>", unsafe_allow_html=True)
                                    if only_l_names:
                                        for p_name in sorted(only_l_names):
                                            p = players_l[p_name]
                                            p_row_html = format_player_row_html(p_name, p)
                                            st.markdown(p_row_html, unsafe_allow_html=True)
                                    else:
                                        st.markdown("<p style='color: var(--muted-text); font-style: italic; font-size:13px; text-align:center;'>אין שחקנים ייחודיים</p>", unsafe_allow_html=True)
                                        
                                with col_res_shared:
                                    st.markdown(f"<h4 style='font-size:0.95rem; border-bottom: 2px solid #94a3b8; padding-bottom:5px; color:#94a3b8; font-weight:700;'>🤝 משותפים ({len(shared_names)})</h4>", unsafe_allow_html=True)
                                    if shared_names:
                                        for p_name in sorted(shared_names):
                                            p = players_l[p_name]
                                            role_l = players_l[p_name]["role"]
                                            role_r = players_r[p_name]["role"]
                                            
                                            resolved_role = ""
                                            if role_l == "captain" or role_r == "captain":
                                                resolved_role = "captain"
                                            elif role_l == "sub_captain" or role_r == "sub_captain":
                                                resolved_role = "sub_captain"
                                            
                                            p_copy = dict(p, role=resolved_role)
                                            p_row_html = format_player_row_html(p_name, p_copy)
                                            st.markdown(p_row_html, unsafe_allow_html=True)
                                    else:
                                        st.markdown("<p style='color: var(--muted-text); font-style: italic; font-size:13px; text-align:center;'>אין שחקנים משותפים</p>", unsafe_allow_html=True)
                                        
                                with col_res_r:
                                    st.markdown(f"<h4 style='font-size:0.95rem; border-bottom: 2px solid #3b82f6; padding-bottom:5px; color:#3b82f6; font-weight:700;'>👉 רק ל-{right_user} ({len(only_r_names)})</h4>", unsafe_allow_html=True)
                                    if only_r_names:
                                        for p_name in sorted(only_r_names):
                                            p = players_r[p_name]
                                            p_row_html = format_player_row_html(p_name, p)
                                            st.markdown(p_row_html, unsafe_allow_html=True)
                                    else:
                                        st.markdown("<p style='color: var(--muted-text); font-style: italic; font-size:13px; text-align:center;'>אין שחקנים ייחודיים</p>", unsafe_allow_html=True)
                    st.markdown('</div>', unsafe_allow_html=True)

        st.markdown("<h3 style='direction: rtl; text-align: right;'>📝 דוחות משחק מוכנים</h3>", unsafe_allow_html=True)
        
        tab_names = [f"⚽ {m['home_team']} - {m['away_team']}" for m in selected_matches]
        tabs = st.tabs(tab_names)
        
        for i, tab in enumerate(tabs):
            match = selected_matches[i]
            with tab:
                raw_report = build_match_report(
                    match["home_team"],
                    match["away_team"],
                    match["kickoff_time"],
                    st.session_state.squads,
                    apply_bidi=False
                )
                
                # Player Name Sanitization: Replace backticks globally with standard apostrophes
                report_markdown = raw_report.replace('`', "'")
                
                st.markdown('<div class="fantasy-card" style="direction: rtl; text-align: right; color: var(--text-color);">\n\n' + report_markdown + '\n\n</div>', unsafe_allow_html=True)
                
                safe_report_text = json.dumps(report_markdown)
                encoded_report = urllib.parse.quote(report_markdown)
                whatsapp_url = f"https://api.whatsapp.com/send?text={encoded_report}"
                
                action_buttons_html = f"""<div style="display: flex; gap: 12px; width: 100%; direction: rtl; margin-top: 10px;">
    <a href="{whatsapp_url}" target="_blank" style="flex: 1; height: 42px; background-color: #25D366; color: white; border-radius: 8px; display: inline-flex; align-items: center; justify-content: center; text-decoration: none; font-weight: 600; box-shadow: 0 4px 10px rgba(37, 211, 102, 0.25); font-size: 14.5px; font-family: 'Rubik', sans-serif;">💬 שתף בוואטסאפ</a>
    <button id="copy-btn-{i}" onclick="copyToClipboard_{i}(this)" style="flex: 1; height: 42px; background-color: #ef4444; color: white; border: none; border-radius: 8px; cursor: pointer; font-weight: 600; box-shadow: 0 4px 10px rgba(239, 68, 68, 0.25); display: inline-flex; align-items: center; justify-content: center; font-size: 14.5px; font-family: 'Rubik', sans-serif;">📋 העתק דוח ללוח</button>
</div>
<script>
function copyToClipboard_{i}(btn) {{
    const textToCopy = {safe_report_text};
    if (navigator.clipboard && window.isSecureContext) {{
        navigator.clipboard.writeText(textToCopy).then(() => {{
            updateButtonSuccess_{i}(btn);
        }}).catch(err => {{
            fallbackCopy_{i}(textToCopy, btn);
        }});
    }} else {{
        fallbackCopy_{i}(textToCopy, btn);
    }}
}}
function fallbackCopy_{i}(text, btn) {{
    const textArea = document.createElement("textarea");
    textArea.value = text;
    textArea.style.position = "fixed";
    textArea.style.left = "-9999px";
    document.body.appendChild(textArea);
    textArea.select();
    try {{
        document.execCommand('copy');
        updateButtonSuccess_{i}(btn);
    }} catch (err) {{
        console.error('Fallback copy failed', err);
    }}
    document.body.removeChild(textArea);
}}
function updateButtonSuccess_{i}(btn) {{
    const orig = btn.innerHTML;
    btn.innerHTML = '<span>✓</span> הועתק!';
    btn.style.backgroundColor = '#10b981';
    setTimeout(() => {{
        btn.innerHTML = orig;
        btn.style.backgroundColor = '#ef4444';
    }}, 2000);
}}
</script>"""
                st.markdown(action_buttons_html, unsafe_allow_html=True)
                
                st.markdown("<br>", unsafe_allow_html=True)
                with st.expander("📋 הצג טקסט גולמי (לגיבוי)"):
                    st.code(report_markdown, language="markdown")

    # -------------------------------------------------------------
    # Secure Production Bug Reporting Form (Webhook)
    # -------------------------------------------------------------
    st.markdown("<br><br><br>", unsafe_allow_html=True)
    with st.expander("🐛 דיווח על באג או פידבק"):
        with st.form("bug_report_form"):
            st.markdown("<p style='direction: rtl; text-align: right; color: var(--text-color);'>נתקלת בבעיה? יש לך רעיון לשיפור? נשמח לשמוע!</p>", unsafe_allow_html=True)
            bug_desc = st.text_area("תיאור הבאג או ההצעה:", placeholder="פרט כאן את התקלה או ההצעה שלך...", height=120)
            user_email = st.text_input("אימייל ליצירת קשר (אופציונלי):", placeholder="example@gmail.com")
            
            submit_bug = st.form_submit_button("שלח דיווח 🚀")
            
            if submit_bug:
                if not bug_desc.strip():
                    st.error("נא למלא את שדה התיאור.")
                else:
                    webhook_url = None
                    try:
                        webhook_url = st.secrets["BUG_WEBHOOK_URL"]
                    except Exception:
                        pass
                        
                    if webhook_url:
                        payload = {
                            "content": f"**New Report (Sport5 Fantasy)**\n**Email:** {user_email or 'N/A'}\n**Description:**\n{bug_desc}"
                        }
                        try:
                            resp = requests.post(webhook_url, json=payload, timeout=10)
                            if resp.status_code in (200, 204):
                                st.success("✅ הדיווח נשלח בהצלחה! תודה רבה.")
                            else:
                                st.error(f"שגיאה בשליחה לשרת ({resp.status_code}).")
                        except Exception as e:
                            st.error(f"שגיאה בתקשורת: {e}")
                    else:
                        st.warning("⚠️ מערכת הדיווח כרגע מנותקת עקב היעדר הגדרת Webhook (חסר BUG_WEBHOOK_URL ב-st.secrets).")
                        logger.warning("Bug Report Webhook missing.")
    # ── Footer ──────────────────────────────────────────────────────────────────
    st.markdown("""
        <div style="text-align: center; padding: 28px 0 8px 0; border-top: 1px solid var(--border-color); margin-top: 10px;">
            <p style="color: var(--muted-text); font-size: 12.5px; direction: ltr; text-align: center; margin: 0;">
                Built with ❤️ using <strong style="color: var(--text-color);">Streamlit</strong> &nbsp;·&nbsp;
                <strong style="color: var(--text-color);">Python</strong> &nbsp;·&nbsp;
                <strong style="color: var(--text-color);">Playwright</strong>
                &nbsp;&nbsp;|&nbsp;&nbsp;
                <a href="https://github.com/yaronbs12/sport5-fantasy-bot" target="_blank"
                   style="color: var(--muted-text); text-decoration: none; font-weight: 600;">
                    ⭐ GitHub
                </a>
                &nbsp;&nbsp;|&nbsp;&nbsp; © 2026
            </p>
        </div>
    """, unsafe_allow_html=True)
    st.markdown("<br><br>", unsafe_allow_html=True)
    col_empty1, col_logout_bottom, col_empty2 = st.columns([4, 2, 4])
    with col_logout_bottom:
        st.markdown("<div style='text-align: center;'>", unsafe_allow_html=True)
        if st.button("🚪 התנתק מהמערכת", key="logout_bottom_btn", use_container_width=True):
            _do_logout()
        st.markdown("</div>", unsafe_allow_html=True)


if __name__ == "__main__":
    main()

