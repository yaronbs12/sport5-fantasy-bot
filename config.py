"""
config.py
---------
Central configuration for the Sport5 Fantasy Football Automation Engine.
The match schedule is now fetched LIVE from openfootball (GitHub).
"""

import os
try:
    from zoneinfo import ZoneInfo
except ImportError:
    from backports.zoneinfo import ZoneInfo

# ─────────────────────────────────────────────────────────────────────────────
#  Playwright / Session
# ─────────────────────────────────────────────────────────────────────────────
USER_DATA_DIR = os.path.join(os.getcwd(), "sport5_user_data")
LEAGUE_ID     = ""
SEASON_ID     = 9
DEBUG         = False

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


def get_first_kickoff_per_round(schedule: list) -> dict:
    """Returns {round_id: earliest_kickoff_datetime} for each round."""
    rounds: dict = {}
    for match in schedule:
        rid = match["round_id"]
        kt  = match["kickoff_time"]
        if rid not in rounds or kt < rounds[rid]:
            rounds[rid] = kt
    return rounds
