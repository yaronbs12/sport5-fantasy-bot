import streamlit as st
import json
import sys
import os
import time
import requests
import urllib.parse
from datetime import datetime
from playwright.sync_api import sync_playwright

# Setup paths
sys.path.insert(0, os.getcwd())

from config import SEASON_ID, USER_DATA_DIR
from display import format_bidi
from login import ensure_authenticated
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

# Normalization helper (keeps league name string normalized for matching)
def normalize_league_name(s: str) -> str:
    if not s:
        return ""
    s = "".join(s.split())
    for char in ('"', "'", '״', '׳', '’'):
        s = s.replace(char, '')
    return s.lower()

# -------------------------------------------------------------
# High-Performance Caching
# -------------------------------------------------------------
@st.cache_data(ttl=600)
def fetch_metadata_cached():
    """Fetch user leagues list, teams mapping, and round dates, caching results for 10 minutes."""
    try:
        with sync_playwright() as pw:
            context = create_browser_context(pw)
            from login import _is_authenticated
            authed = _is_authenticated(context)
            if not authed:
                context.close()
                return False, [], {}, None
            
            leagues = fetch_leagues_summary(context)
            teams_map = get_teams_mapping(context)
            active_round_dates = fetch_active_round_dates(context)
            context.close()
            return True, leagues, teams_map, active_round_dates
    except Exception:
        return False, [], {}, None

@st.cache_data(ttl=600)
def fetch_live_schedule_cached():
    """Fetch live match schedule, caching results for 10 minutes."""
    return fetch_live_schedule(only_future=True)

@st.cache_data(ttl=600)
def fetch_all_squads_cached(league_id: str):
    """Fetch all rosters for the chosen league, caching results for 10 minutes."""
    with sync_playwright() as pw:
        context = create_browser_context(pw)
        squads = fetch_all_squads(context, league_id=league_id)
        context.close()
    return squads

# Blocking login runner
def run_blocking_login():
    with st.spinner("ממתין לסיום ההתחברות... אנא בצע כניסה בחלון הדפדפן שנפתח."):
        try:
            with sync_playwright() as pw:
                ctx = pw.chromium.launch_persistent_context(
                    user_data_dir=USER_DATA_DIR,
                    headless=False,
                    args=["--no-sandbox", "--start-maximized"],
                    no_viewport=True,
                )
                page = ctx.new_page()
                page.goto("https://dreamteam.sport5.co.il", wait_until="domcontentloaded")
                page.wait_for_url("**/my-team", timeout=0)
                time.sleep(2.5)
                ctx.close()
            st.session_state.authenticated = True
            return True
        except Exception as exc:
            st.error(f"שגיאה בהתחברות: {exc}")
            return False

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
            --card-bg: #f4f5f7;
            --border-color: #e4e4e7;
            --text-color: #09090b;
            --accent-color: #6366f1;
            --muted-text: #64748b;
            --hover-bg: #e2e8f0;
        }
        """
    else:
        theme_css = """
        :root {
            --bg-color: #09090b;
            --card-bg: #18181b;
            --border-color: #27272a;
            --text-color: #f4f4f5;
            --accent-color: #6366f1;
            --muted-text: #a1a1aa;
            --hover-bg: #27272a;
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
            border-radius: 12px !important;
            padding: 24px !important;
            margin-bottom: 20px !important;
            box-shadow: 0 1px 3px 0 rgba(0, 0, 0, 0.1), 0 1px 2px -1px rgba(0, 0, 0, 0.1) !important;
        }}
        
        /* Input Form Polishing */
        .stTextInput input, .stNumberInput input, .stTextArea textarea {{
            background-color: var(--bg-color) !important;
            border: 1px solid var(--border-color) !important;
            color: var(--text-color) !important;
            border-radius: 8px !important;
            padding: 10px !important;
        }}
        .stTextInput input:focus, .stTextArea textarea:focus {{
            border-color: var(--accent-color) !important;
            box-shadow: 0 0 0 1px var(--accent-color) !important;
        }}
        
        /* Slider Styling */
        div[data-testid="stSlider"] [data-testid="stThumb"] {{
            background-color: var(--accent-color) !important;
            border: 2px solid var(--card-bg) !important;
            box-shadow: 0 0 10px rgba(99, 102, 241, 0.5) !important;
        }}
        
        /* Tabs Styling */
        div[data-baseweb="tab-list"] button[data-baseweb="tab"],
        button[data-baseweb="tab"] {{
            background: transparent !important;
            color: var(--muted-text) !important;
            font-size: 15px !important;
            font-weight: 600 !important;
            border: 1px solid transparent !important;
            padding: 10px 20px !important;
            border-radius: 6px !important;
            margin-right: 6px !important;
        }}
        button[aria-selected="true"] {{
            color: var(--accent-color) !important;
            background-color: var(--card-bg) !important;
            border: 1px solid var(--border-color) !important;
            border-bottom: 2px solid var(--accent-color) !important;
        }}
        
        /* Headings */
        h1, h2, h3, p, span {{
            color: var(--text-color);
        }}
        h1, h2, h3 {{
            font-weight: 700 !important;
            text-align: right;
            direction: rtl;
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
        }}
        .status-badge.disconnected {{
            background-color: rgba(239, 68, 68, 0.1) !important;
            color: #ef4444 !important;
            border: 1px solid rgba(239, 68, 68, 0.2) !important;
        }}
        
        /* RTL Text Direction overrides for Alerts */
        .stAlert {{
            direction: rtl;
            text-align: right;
            background-color: var(--card-bg) !important;
            border: 1px solid var(--border-color) !important;
            color: var(--text-color) !important;
            border-radius: 12px !important;
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
        
        /* Hide Sidebar UI Completely */
        [data-testid="collapsedControl"] {{
            display: none !important;
        }}
        [data-testid="stSidebar"] {{
            display: none !important;
        }}
    </style>
    """, unsafe_allow_html=True)

    # -------------------------------------------------------------
    # Header & Theme Switcher (No Sidebar)
    # -------------------------------------------------------------
    col_btn, col_title = st.columns([1.5, 8.5])
    with col_btn:
        st.markdown("<div style='margin-top: 15px;'></div>", unsafe_allow_html=True)
        if st.session_state.theme == "dark":
            if st.button("🌙 Dark Mode", use_container_width=True):
                st.session_state.theme = "light"
                st.rerun()
        else:
            if st.button("☀️ Light Mode", use_container_width=True):
                st.session_state.theme = "dark"
                st.rerun()

    with col_title:
        st.markdown("<h1 style='text-align: right; direction: rtl;'>🏆 Sport5 Fantasy Analytics</h1>", unsafe_allow_html=True)
        st.markdown("<p style='text-align: right; direction: rtl; font-size: 1.05rem; margin-bottom: 2.5rem; color: var(--muted-text);'>מערכת ניתוח וניהול משחקי מחזור ליגת החלומות</p>", unsafe_allow_html=True)
    
    if "authenticated" not in st.session_state:
        st.session_state.authenticated = False
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
        
    if not st.session_state.authenticated and "auth_checked" not in st.session_state:
        st.session_state.auth_checked = True
        authed, leagues, teams_map, active_round = fetch_metadata_cached()
        if authed:
            st.session_state.leagues = leagues
            st.session_state.teams_map = teams_map
            st.session_state.active_round_dates = active_round
            st.session_state.authenticated = True
            st.session_state.schedule = fetch_live_schedule_cached()
 
    if st.session_state.authenticated:
        # Keep local session state updated from the cache
        authed, leagues, teams_map, active_round = fetch_metadata_cached()
        st.session_state.leagues = leagues
        st.session_state.teams_map = teams_map
        st.session_state.active_round_dates = active_round
        st.session_state.schedule = fetch_live_schedule_cached()
        
        st.markdown("""
            <div style="text-align: right; margin-bottom: 20px;">
                <div class="status-badge">
                    <span style="display:inline-block; width:6px; height:6px; border-radius:50%; background-color:#10b981; margin-left: 6px;"></span>
                    סשן מחובר לשרת
                </div>
            </div>
        """, unsafe_allow_html=True)
    else:
        st.markdown("""
            <div style="text-align: right; margin-bottom: 20px;">
                <div class="status-badge disconnected">
                    <span style="display:inline-block; width:6px; height:6px; border-radius:50%; background-color:#ef4444; margin-left: 6px;"></span>
                    נדרש חיבור
                </div>
            </div>
        """, unsafe_allow_html=True)
        st.info("לא נמצא סשן מחובר. אנא לחץ על הכפתור כדי לפתוח חלון דפדפן מאובטח ולהתחבר עם חשבון Google.")
        if st.button("🔐 התחברות לחשבון", type="primary"):
            success = run_blocking_login()
            if success:
                st.cache_data.clear()  # Clear cache to immediately fetch fresh authenticated data
                st.session_state.authenticated = True
                st.rerun()
        return

    # -------------------------------------------------------------
    # Main Configuration Columns (Layout is clean with no empty boxes)
    # -------------------------------------------------------------
    col1, col2 = st.columns(2)
    selected_league_id = None
    resolved_league_name = ""
    
    with col1:
        st.markdown("<h3 style='direction:rtl; text-align:right;'>🔍 בחירת ליגה</h3>", unsafe_allow_html=True)
        league_search_query = st.text_input("🔍 הכנס את שם הליגה שלך (לדוגמה: ליגת האלופות)", value="").strip()
        manual_league_id = st.text_input(
            "🆔 מזהה ליגה (ID) — לגיבוי בלבד (אם החיפוש נכשל)", 
            value="",
            help="💡 איך מוצאים את ה-ID? נכנסים למסך הליגה המלא באתר ספורט 5, ומעתיקים את מספר ה-ID שמופיע בסוף כתובת ה-URL בחלון הדפדפן."
        ).strip()
        
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
                
        LEAGUE_BLACKLIST = ["כף ורדה", "ליגת העל", "כללי", "הכללית", "עולמי"]
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
            from zoneinfo import ZoneInfo
            IL_TZ = ZoneInfo("Asia/Jerusalem")
            
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
<div style="display: flex; flex-direction: column; align-items: center; justify-content: center; padding: 30px; background: var(--card-bg, #18181b); border: 1px solid var(--border-color, #27272a); rounded-lg: 12px; border-radius: 12px; margin-bottom: 20px;">
    <div class="football-loader" style="font-size: 60px; line-height: 1; user-select: none;">⚽</div>
    <div style="margin-top: 20px; font-size: 18px; font-weight: 600; text-align: center; color: var(--text-color, #f4f4f5);">
        🏃♂️💨 מכינים את המגרש ומנתחים סגלים... אנא המתן
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
                    st.error("לא נמצאו סגלים או חברי ליגה. אנא ודא שהסשן תקין ומזהה הליגה נכון.")
                else:
                    # Normalize player nations inside squads
                    for squad in squads:
                        for p in squad.get("players", []):
                            p["nation"] = normalize_country_name(p["nation"])
                    st.session_state.squads = squads
                    st.session_state.reports_generated = True
            except Exception as e:
                if "got HTML instead of JSON" in str(e) or "unauthenticated" in str(e).lower():
                    st.session_state.authenticated = False
                    st.cache_data.clear() # clear cached data if auth expired
                    st.error("הסשן שלך פג תוקף. אנא התחבר מחדש.")
                    st.rerun()
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
            from collections import Counter
            counter = Counter(all_players)
            most_common = counter.most_common()
            if most_common:
                max_count = most_common[0][1]
                popular_players = [name for name, count in most_common if count == max_count]
                popular_names = ", ".join(popular_players)
                
                total_league_teams = st.session_state.squads
                true_total_teams = len(total_league_teams)
                player_count = max_count
                
                st.markdown(
                    f'<div class="fantasy-card" style="direction: rtl; text-align: right;">'
                    f'<p style="margin: 0; font-size: 1.05rem; color: var(--text-color);">'
                    f'🏆 <b>השחקן הפופולרי בליגה:</b> {popular_names} (נמצא ב-{player_count} מתוך {true_total_teams} קבוצות בליגה שלך)'
                    f'</p>'
                    f'</div>',
                    unsafe_allow_html=True
                )
        
        st.markdown("<h3 style='direction: rtl; text-align: right;'>📝 דוחות משחק מוכנים</h3>", unsafe_allow_html=True)
        
        tab_names = [f"⚽ {m['home_team']} - {m['away_team']}" for m in selected_matches]
        tabs = st.tabs(tab_names)
        
        # Color variables passed directly to the iframe
        bg_color = "#ffffff" if st.session_state.theme == "light" else "#09090b"
        card_bg = "#f4f5f7" if st.session_state.theme == "light" else "#18181b"
        border_color = "#e4e4e7" if st.session_state.theme == "light" else "#27272a"
        text_color = "#09090b" if st.session_state.theme == "light" else "#f4f4f5"
        accent_color = "#6366f1"
        hover_bg = "#e2e8f0" if st.session_state.theme == "light" else "#27272a"
        
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
                
                st.markdown(f'<div class="fantasy-card" style="direction: rtl; text-align: right; color: var(--text-color);">\n\n{report_markdown}\n\n</div>', unsafe_allow_html=True)
                
                escaped_report = json.dumps(report_markdown)
                copy_button_html = f"""
                <div style="display: flex; justify-content: flex-end; margin-top: 15px;">
                    <button id="copy-btn-{i}" style="
                        background-color: transparent;
                        color: {text_color};
                        padding: 8px 18px;
                        border: 1px solid {border_color};
                        border-radius: 6px;
                        cursor: pointer;
                        font-size: 13.5px;
                        font-weight: 600;
                        display: inline-flex;
                        align-items: center;
                        gap: 8px;
                        font-family: 'Inter', system-ui, sans-serif;
                        transition: all 0.2s ease;
                    " onmouseover="this.style.backgroundColor='{hover_bg}';" onmouseout="this.style.backgroundColor='transparent';">
                        <span>📋</span> העתק דוח
                    </button>
                </div>
                <script>
                document.getElementById("copy-btn-{i}").addEventListener("click", () => {{
                    navigator.clipboard.writeText({escaped_report}).then(() => {{
                        const btn = document.getElementById("copy-btn-{i}");
                        const originalText = btn.innerHTML;
                        btn.innerHTML = "<span>✓</span> הועתק!";
                        btn.style.backgroundColor = "{accent_color}";
                        btn.style.borderColor = "{accent_color}";
                        btn.style.color = "#ffffff";
                        setTimeout(() => {{
                            btn.innerHTML = originalText;
                            btn.style.backgroundColor = "transparent";
                            btn.style.borderColor = "{border_color}";
                            btn.style.color = "{text_color}";
                        }}, 2000);
                    }});
                }});
                </script>
                """
                st.markdown(copy_button_html, unsafe_allow_html=True)
                
                # Live WhatsApp Direct Share Button
                encoded_report = urllib.parse.quote(report_markdown)
                whatsapp_url = f"https://api.whatsapp.com/send?text={encoded_report}"
                st.link_button("💬 שתף קבוצה בוואטסאפ", url=whatsapp_url, use_container_width=True)
                
                with st.expander("📋 העתק טקסט גולמי (לגיבוי)"):
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
                        # Local log for fallback gracefully
                        print(f"Bug Report Fallback Log: Email={user_email}, Desc={bug_desc}")

if __name__ == "__main__":
    main()
