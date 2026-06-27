"""
schedule_fetcher.py
-------------------
Fetches the LIVE 2026 World Cup match schedule from the
openfootball open-data GitHub repository and converts it
into the internal format used by config.py / notifier.py.

Source:
  https://raw.githubusercontent.com/openfootball/worldcup.json/master/2026/worldcup.json

Format returned by openfootball per match:
  {
    "round": "Matchday 8",
    "date":  "2026-06-18",
    "time":  "12:00 UTC-4",
    "team1": "Czech Republic",
    "team2": "South Africa",
    "group": "Group A",
    "ground": "Atlanta"
  }

We convert each match to:
  {
    "match_id":    "matchday8_CZE_RSA",
    "round_id":    8,
    "home_team":   "צ'כיה",
    "away_team":   "דרום אפריקה",
    "kickoff_time": datetime(..., tzinfo=IL_TZ)
  }

Team names are translated to the canonical Hebrew names used by Sport5,
as defined in TEAM_NAME_MAP below. All values MUST match the output of
normalize_country_name() in scraper.py exactly.
"""

import re
import json
import logging
import requests
from datetime import datetime, timezone, timedelta

from config import IL_TZ

logger = logging.getLogger(__name__)

OPENFOOTBALL_URL = (
    "https://raw.githubusercontent.com/openfootball/"
    "worldcup.json/master/2026/worldcup.json"
)

# ─────────────────────────────────────────────────────────────────────────────
#  English → Hebrew team name map
#  All values MUST match the canonical outputs of normalize_country_name()
#  in scraper.py (i.e., what Sport5 returns after normalization).
#  Add / fix any entries that don't match your Sport5 roster data.
# ─────────────────────────────────────────────────────────────────────────────
TEAM_NAME_MAP = {
    "Mexico":               "מקסיקו",
    "South Africa":         "דרום אפריקה",
    "South Korea":          "דרום קוריאה",
    "Czech Republic":       "צ'כיה",
    "Canada":               "קנדה",
    "Bosnia & Herzegovina": "בוסניה והרצגובינה",
    "Qatar":                "קטאר",
    "Switzerland":          "שווייץ",
    "Brazil":               "ברזיל",
    "Morocco":              "מרוקו",
    "Argentina":            "ארגנטינה",
    "Saudi Arabia":         "ערב הסעודית",
    "France":               "צרפת",
    "Nigeria":              "ניגריה",
    "England":              "אנגליה",
    "USA":                  "ארה\"ב",
    "United States":        "ארה\"ב",
    "Portugal":             "פורטוגל",
    "Spain":                "ספרד",
    "Germany":              "גרמניה",
    "Japan":                "יפן",
    "Australia":            "אוסטרליה",
    "Netherlands":          "הולנד",
    "Colombia":             "קולומביה",
    "Uzbekistan":           "אוזבקיסטן",
    "Ecuador":              "אקוואדור",
    "Uruguay":              "אורוגוואי",
    "Italy":                "איטליה",
    "Belgium":              "בלגיה",
    "Croatia":              "קרואטיה",
    "Serbia":               "סרביה",
    "Denmark":              "דנמרק",
    "Poland":               "פולין",
    "Cameroon":             "קמרון",
    "Senegal":              "סנגל",
    "Egypt":                "מצרים",
    "Ghana":                "גאנה",
    "Tunisia":              "תוניסיה",
    "Iran":                 "איראן",
    "Albania":              "אלבניה",
    "Austria":              "אוסטריה",
    "Hungary":              "הונגריה",
    "Romania":              "רומניה",
    "Scotland":             "סקוטלנד",
    "Turkey":               "טורקיה",
    "Wales":                "ויילס",
    "Chile":                "צ'ילה",
    "Venezuela":            "ונצואלה",
    "Peru":                 "פרו",
    "Paraguay":             "פרגוואי",
    "Bolivia":              "בוליביה",
    "Honduras":             "הונדורס",
    "Panama":               "פנמה",
    "Costa Rica":           "קוסטה ריקה",
    "Jamaica":              "ג'מייקה",
    "New Zealand":          "ניו זילנד",
    "Indonesia":            "אינדונזיה",
    "China":                "סין",
    "Thailand":             "תאילנד",
    "Iraq":                 "עיראק",
    "Syria":                "סוריה",
    "Jordan":               "ירדן",
    "Ukraine":              "אוקראינה",
    "Slovakia":             "סלובקיה",
    "Slovenia":             "סלובניה",
    "Greece":               "יוון",
    "Finland":              "פינלנד",
    "Norway":               "נורווגיה",
    "Sweden":               "שוודיה",
    "Ivory Coast":          "חוף השנהב",
    "Mali":                 "מאלי",
    "Congo DR":             "הרפובליקה הדמוקרטית של קונגו",
    "Angola":               "אנגולה",
    "Tanzania":             "טנזניה",
}


# ─────────────────────────────────────────────────────────────────────────────
#  UTC offset parser  e.g. "12:00 UTC-6"  →  UTC-06:00
# ─────────────────────────────────────────────────────────────────────────────

def _parse_kickoff_utc(date_str: str, time_str: str) -> datetime | None:
    """
    Parse a date ('2026-06-18') + time ('12:00 UTC-6') into a UTC-aware datetime.
    Returns None on failure.
    """
    try:
        m = re.match(r"(\d{1,2}):(\d{2})\s+UTC([+-]\d+)", time_str)
        if not m:
            return None
        hour   = int(m.group(1))
        minute = int(m.group(2))
        offset = int(m.group(3))

        local_tz = timezone(timedelta(hours=offset))
        local_dt = datetime(
            *[int(x) for x in date_str.split("-")],
            hour, minute,
            tzinfo=local_tz,
        )
        return local_dt.astimezone(timezone.utc)
    except Exception:
        return None


def _to_il(utc_dt: datetime) -> datetime:
    """Convert a UTC datetime to Israel time."""
    return utc_dt.astimezone(IL_TZ)


def _round_number(round_str: str) -> int:
    """Extract numeric round id from e.g. 'Matchday 8'."""
    m = re.search(r"\d+", round_str)
    return int(m.group()) if m else 0


def _match_id(match: dict) -> str:
    t1 = re.sub(r"\W+", "", match["team1"])[:4].upper()
    t2 = re.sub(r"\W+", "", match["team2"])[:4].upper()
    return f"md{_round_number(match['round'])}_{t1}_{t2}"


# ─────────────────────────────────────────────────────────────────────────────
#  Main fetch function
# ─────────────────────────────────────────────────────────────────────────────

def fetch_live_schedule(only_future: bool = True) -> list[dict]:
    """
    Download and parse the openfootball World Cup 2026 JSON.
    Returns a list of match dicts in the format expected by notifier.py.

    Parameters
    ----------
    only_future : if True, skips matches whose kickoff is already in the past.
    """
    logger.info("Fetching live World Cup schedule from openfootball...")

    try:
        response = requests.get(OPENFOOTBALL_URL, timeout=15)
        response.raise_for_status()
        data = response.json()
    except requests.RequestException as exc:
        logger.error("Failed to fetch schedule: %s", exc)
        return []
    except ValueError as exc:
        logger.error("Failed to parse schedule JSON: %s", exc)
        return []

    matches_raw = data.get("matches", [])
    schedule    = []
    now_utc     = datetime.now(tz=timezone.utc)

    for match in matches_raw:
        date_str  = match.get("date", "")
        time_str  = match.get("time", "")
        team1_en  = match.get("team1", "").strip()
        team2_en  = match.get("team2", "").strip()
        round_str = match.get("round", "Matchday 0")

        utc_kickoff = _parse_kickoff_utc(date_str, time_str)
        if utc_kickoff is None:
            continue

        if only_future and utc_kickoff <= now_utc:
            continue

        il_kickoff = _to_il(utc_kickoff)

        # Translate to canonical Hebrew names (must match Sport5 / normalize_country_name output)
        home_heb = TEAM_NAME_MAP.get(team1_en, team1_en)
        away_heb = TEAM_NAME_MAP.get(team2_en, team2_en)

        schedule.append({
            "match_id":    _match_id(match),
            "round_id":    _round_number(round_str),
            "home_team":   home_heb,
            "away_team":   away_heb,
            "kickoff_time": il_kickoff,
            "kickoff_utc":  utc_kickoff,
            "ground":       match.get("ground", ""),
        })

    schedule.sort(key=lambda x: x["kickoff_time"])
    logger.info("Loaded %d upcoming matches.", len(schedule))
    return schedule


def print_upcoming(schedule: list[dict], n: int = 10) -> None:
    """Pretty-print the next N matches (for debugging / self-test)."""
    print(f"\n{'─'*60}")
    print(f"  Next {min(n, len(schedule))} upcoming World Cup matches (Israel time):")
    print(f"{'─'*60}")
    for m in schedule[:n]:
        kt = m["kickoff_time"].strftime("%a %d/%m  %H:%M %Z")
        print(f"  [{kt}]  {m['home_team']} vs {m['away_team']}   (Matchday {m['round_id']})")
    print(f"{'─'*60}\n")


# ─────────────────────────────────────────────────────────────────────────────
#  Quick self-test when run directly
# ─────────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import logging as _logging
    _logging.basicConfig(level=_logging.INFO, format="%(levelname)s: %(message)s")
    sched = fetch_live_schedule(only_future=False)
    print_upcoming(sched, n=20)
