"""
config.py
---------
Central configuration for the Sport5 Fantasy Football Automation Engine.
The match schedule is now fetched LIVE from openfootball (GitHub).
"""

import os
import logging
try:
    from zoneinfo import ZoneInfo
except ImportError:
    from backports.zoneinfo import ZoneInfo

# ─────────────────────────────────────────────────────────────────────────────
#  Playwright / Session
# ─────────────────────────────────────────────────────────────────────────────
USER_DATA_DIR = os.path.join(os.getcwd(), "sport5_user_data")
SEASON_ID     = 9       # Sport5 Dream Team season identifier — World Cup 2026
DEBUG         = os.environ.get("DEBUG", "false").lower() == "true"

# ─────────────────────────────────────────────────────────────────────────────
#  Sport5 API base URL  (single source of truth — do not repeat elsewhere)
# ─────────────────────────────────────────────────────────────────────────────
BASE_URL = "https://dreamteam.sport5.co.il"

# ─────────────────────────────────────────────────────────────────────────────
#  Loop & timing
# ─────────────────────────────────────────────────────────────────────────────
LOOP_INTERVAL_SECONDS  = 60     # Main loop tick (seconds)
ALERT_WINDOW_SECONDS   = 90     # ±90s window to "hit" an alert trigger
SCHEDULE_REFRESH_HOURS = 6      # Re-download match schedule every N hours

# ─────────────────────────────────────────────────────────────────────────────
#  Files
# ─────────────────────────────────────────────────────────────────────────────
LOG_FILE         = os.path.join(os.getcwd(), "fantasy_bot.log")
ALERT_STATE_FILE = os.path.join(os.getcwd(), "alert_state.json")

# ─────────────────────────────────────────────────────────────────────────────
#  Israel timezone
# ─────────────────────────────────────────────────────────────────────────────
IL_TZ = ZoneInfo("Asia/Jerusalem")

# ─────────────────────────────────────────────────────────────────────────────
#  Alert offsets (seconds before kickoff)
#  Substitution deadline → 3h and 1h before FIRST match of a round
#  Match preview         → 1h before EACH individual match
# ─────────────────────────────────────────────────────────────────────────────
ALERT_OFFSETS = {
    "3h": 3 * 3600,
    "1h": 1 * 3600,
}

# ─────────────────────────────────────────────────────────────────────────────
#  These are populated at runtime by main.py after fetching the live schedule.
#  Do NOT hard-code values here — they will be overwritten.
# ─────────────────────────────────────────────────────────────────────────────
MATCH_SCHEDULE: list = []
FIRST_KICKOFF_PER_ROUND: dict = {}

# Leagues blacklist to avoid pulling massive/global leagues which cause WAF blocks / timeouts
LEAGUE_BLACKLIST = ["כף ורדה", "ליגת העל", "כללי", "הכללית", "עולמי"]


# Runtime value — set via UI (Streamlit) or CLI prompt; never hard-code here.
LEAGUE_ID: str = ""


# ─────────────────────────────────────────────────────────────────────────────
#  Logging
# ─────────────────────────────────────────────────────────────────────────────

def setup_logging() -> None:
    """
    Configure logging for CLI (main.py) usage.
    Streamlit manages its own logging — do NOT call this from app.py.
    """
    logging.basicConfig(
        level=logging.DEBUG if DEBUG else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
        handlers=[
            logging.FileHandler(LOG_FILE, encoding="utf-8"),
            logging.StreamHandler(),
        ],
    )


def get_first_kickoff_per_round(schedule: list) -> dict:
    """Returns {round_id: earliest_kickoff_datetime} for each round."""
    rounds: dict = {}
    for match in schedule:
        rid = match["round_id"]
        kt  = match["kickoff_time"]
        if rid not in rounds or kt < rounds[rid]:
            rounds[rid] = kt
    return rounds
