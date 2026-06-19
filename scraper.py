"""
scraper.py
----------
Playwright-based data extraction from Sport5 Fantasy API.

headless=False everywhere (off-screen window) → bypasses Sport5 WAF.

Validated endpoints:
  #0  GET /api/CustomLeagues/GetLeaguesSummary?seasonId=9
      Path: data (array) → each item: { id, leagueName, ... }

  #1  GET /api/Leagues/Get?seasonId=9
      Path: data.teams[] → { id, name }

  #2  GET /api/CustomLeagues/GetLeagueData
          ?seasonId=9&leagueId=<id>&teamId=null&isPerRound=false
          &pageIndex=0&searchText=
      Path: data.teams[] → { userId, userName, name }

  #3  GET /api/UserTeam/GetUserAndTeam?seasonId=9&userId=<uid>
      Path: data.userTeam.userTeamPlayers[]
            data.userTeam.captainId
            data.userTeam.subCaptainId
      Bench flag: item["isReserve"]  (True = bench, False = starting XI)
"""

import json
import os
from datetime import datetime
from playwright.sync_api import BrowserContext

from config import USER_DATA_DIR, SEASON_ID, LEAGUE_ID, DEBUG


# ─────────────────────────────────────────────────────────────────────────────
#  Playwright context factory
#  headless=False → bypasses Sport5 anti-bot WAF
#  Window is positioned far off-screen so it's invisible to the user
# ─────────────────────────────────────────────────────────────────────────────

def create_browser_context(playwright_instance, headless: bool = False):
    """
    Launch a persistent Chromium context reusing the saved user profile.

    headless=False (default) because Sport5's WAF blocks headless Chromium.
    The browser window is a tiny 100×100px window positioned at -32000,-32000
    so it is off-screen and invisible without triggering headless detection.
    """
    args = ["--no-sandbox", "--disable-dev-shm-usage"]
    if not headless:
        args += ["--window-position=-32000,-32000", "--window-size=100,100"]

    return playwright_instance.chromium.launch_persistent_context(
        user_data_dir = USER_DATA_DIR,
        headless      = headless,
        args          = args,
    )


# ─────────────────────────────────────────────────────────────────────────────
#  Low-level JSON helper
# ─────────────────────────────────────────────────────────────────────────────

def _get_json(context: BrowserContext, url: str) -> dict | list | None:
    """
    Authenticated GET → parsed JSON (dict or list), or None on failure.

    Distinguishes:
      HTTP != 200  → WAF / auth block
      ValueError   → server returned HTML (unauthenticated or WAF block)
      Exception    → network / Playwright error
    """
    try:
        response = context.request.get(url)
        if response.status != 200:
            print(f"  [scraper] HTTP {response.status} <- {url}")
            return None
        return response.json()
    except ValueError:
        print(f"  [scraper] ERROR: got HTML instead of JSON <- {url}")
        print("            → Session expired? Delete sport5_user_data/ and re-run.")
        print("            → WAF block? Ensure headless=False is used.")
        return None
    except Exception as exc:
        print(f"  [scraper] Network error: {exc}")
        return None


# ─────────────────────────────────────────────────────────────────────────────
#  Endpoint #0 — Leagues summary (for interactive league search)
# ─────────────────────────────────────────────────────────────────────────────

def fetch_leagues_summary(context: BrowserContext) -> list[dict]:
    """
    Returns a list of all custom leagues for the season.

    URL : GET /api/CustomLeagues/GetLeaguesSummary?seasonId=9
    Path: data (array) → each item contains at minimum { id, leagueName }

    Saves raw API response to leagues_debug.json for inspection.
    Returns [] on any failure so callers fall back to manual ID entry.
    """
    url = f"https://dreamteam.sport5.co.il/api/CustomLeagues/GetLeaguesSummary?seasonId={SEASON_ID}"
    raw = _get_json(context, url)

    if raw is None:
        print("  [scraper] GetLeaguesSummary: no response (HTML/error). Check session.")
        return []

    # ── Save raw response so the user can inspect the real field names ────────
    _dump_always("leagues_debug.json", raw)

    # ── Try different response shapes ─────────────────────────────────────────
    leagues: list = []
    if isinstance(raw, list):
        leagues = raw
    elif isinstance(raw, dict):
        data = raw.get("data", [])
        if isinstance(data, list):
            leagues = data
        elif isinstance(data, dict):
            leagues = (
                data.get("leagues")     or
                data.get("leaguesList") or
                data.get("items")       or
                []
            )

    print(f"  [scraper] GetLeaguesSummary: {len(leagues)} leagues found.")

    # ── Print first 10 names so the user can see what the API returned ────────
    if leagues:
        print("  [scraper] First 10 league names from API:")
        for lg in leagues[:10]:
            name = lg.get("leagueName") or lg.get("name") or repr(lg)
            lid  = lg.get("id") or lg.get("leagueId") or "?"
            print(f"    ID={lid}  name={name!r}")
    else:
        print("  [scraper] Response keys (top-level):", list(raw.keys()) if isinstance(raw, dict) else type(raw))

    return leagues


# ─────────────────────────────────────────────────────────────────────────────
#  Endpoint #1 — Nations / Teams mapping
# ─────────────────────────────────────────────────────────────────────────────

def get_teams_mapping(context: BrowserContext) -> dict:
    """
    Returns {team_id (int): team_name_hebrew (str)}.

    URL : GET /api/Leagues/Get?seasonId=9
    Path: data.teams[] → { id, name }
    """
    url  = f"https://dreamteam.sport5.co.il/api/Leagues/Get?seasonId={SEASON_ID}"
    data = _get_json(context, url)
    teams_map: dict = {}

    if data and isinstance(data, dict):
        for team in data.get("data", {}).get("teams", []):
            t_id   = team.get("id")
            t_name = (team.get("name") or "").strip()
            if t_id and t_name:
                teams_map[t_id] = t_name

    print(f"  [scraper] Loaded {len(teams_map)} national team mappings.")
    _dump_once("sport5_teams_debug.json", {str(k): v for k, v in teams_map.items()})
    return teams_map


def fetch_active_round_dates(context: BrowserContext) -> tuple[str, str]:
    """
    Returns (startDate, endDate) strings from Sport5 active round info.
    """
    url  = f"https://dreamteam.sport5.co.il/api/Leagues/Get?seasonId={SEASON_ID}"
    data = _get_json(context, url)
    if data and isinstance(data, dict):
        d_val = data.get("data", {})
        if isinstance(d_val, dict):
            start = d_val.get("startDate")
            end = d_val.get("endDate")
            if start and end:
                return start, end
    return "", ""


# ─────────────────────────────────────────────────────────────────────────────
#  Endpoint #2 — League members
# ─────────────────────────────────────────────────────────────────────────────

def fetch_league_users(context: BrowserContext, league_id: str) -> list[dict]:
    """
    Returns the 10 league member entries.

    URL : GET /api/CustomLeagues/GetLeagueData
              ?seasonId=9&leagueId=<id>&teamId=null&isPerRound=false
              &pageIndex=0&searchText=
    Path: data.teams[] → { userId, userName, name }
    """
    url = (
        f"https://dreamteam.sport5.co.il/api/CustomLeagues/GetLeagueData"
        f"?seasonId={SEASON_ID}"
        f"&leagueId={league_id}"
        f"&teamId=null"
        f"&isPerRound=false"
        f"&pageIndex=0"
        f"&searchText="
    )
    data    = _get_json(context, url)
    members: list[dict] = []

    if data and isinstance(data, dict):
        for item in data.get("data", {}).get("teams", []):
            user_id   = item.get("userId")
            user_name = (item.get("userName") or "").strip()
            team_name = (item.get("name")     or "").strip()
            if user_id:
                members.append({
                    "user_id":   str(user_id),
                    "user_name": user_name,
                    "team_name": team_name,
                })

    print(f"  [scraper] Found {len(members)} league members for league {league_id}.")
    return members


# ─────────────────────────────────────────────────────────────────────────────
#  Endpoint #3 — Individual squad
# ─────────────────────────────────────────────────────────────────────────────

def fetch_structured_squad(
    context:   BrowserContext,
    user_id:   str | int,
    user_name: str,
    team_name: str,
    teams_map: dict,
) -> dict:
    """
    Fetches one league member's full squad.

    URL : GET /api/UserTeam/GetUserAndTeam?seasonId=9&userId=<uid>
    Path: data.userTeam.{userTeamPlayers[], captainId, subCaptainId}
    """
    url = (
        f"https://dreamteam.sport5.co.il/api/UserTeam/GetUserAndTeam"
        f"?seasonId={SEASON_ID}&userId={user_id}"
    )
    squad = {"user_name": user_name, "team_name": team_name, "players": []}
    data  = _get_json(context, url)

    if not data or not isinstance(data, dict):
        return squad

    user_team      = data.get("data", {}).get("userTeam", {})
    players_raw    = user_team.get("userTeamPlayers", [])

    # Normalize IDs to int to avoid int/str type-mismatch false negatives
    def _to_int(v) -> int | None:
        try:
            return int(v) if v is not None else None
        except (ValueError, TypeError):
            return None

    captain_id     = _to_int(user_team.get("captainId"))
    sub_captain_id = _to_int(user_team.get("subCaptainId"))

    for p in players_raw:
        # Skip only when isActive is EXPLICITLY False (missing field → keep player).
        # Do NOT use p.get("isActive", False) — that defaults to False when the
        # field is absent, which wrongly skips ALL players if the API omits it.
        if p.get("isActive") is False:
            continue
        # Skip only when isRemoved is explicitly True
        if p.get("isRemoved") is True:
            continue

        player_obj = p.get("player", {})

        # captainId may refer to either the wrapper's playerId OR the inner player's id
        # — check both so we never miss a match
        p_id_wrapper = _to_int(p.get("playerId"))
        p_id_inner   = _to_int(player_obj.get("id"))

        p_name     = sanitize_player_name((player_obj.get("name") or "").strip())
        t_id       = player_obj.get("teamId")
        nation     = teams_map.get(t_id, f"Team_{t_id}")
        is_reserve = bool(p.get("isReserve", False))

        role = "player"
        for pid in (p_id_wrapper, p_id_inner):
            if pid is None:
                continue
            if pid == captain_id:
                role = "captain"
                break
            if pid == sub_captain_id:
                role = "sub_captain"
                break

        squad["players"].append({
            "name":     p_name,
            "nation":   nation,
            "is_bench": is_reserve,
            "role":     role,
        })

    # Debug: show captain resolution for this squad
    captain_found  = next((p for p in squad["players"] if p["role"] == "captain"),     None)
    vc_found       = next((p for p in squad["players"] if p["role"] == "sub_captain"), None)
    cap_name  = captain_found["name"]  if captain_found else "NOT FOUND"
    vc_name   = vc_found["name"]       if vc_found      else "NOT FOUND"
    print(
        f"    [cap] {user_name}: "
        f"captainId={captain_id} → {cap_name} | "
        f"subCaptainId={sub_captain_id} → {vc_name}"
    )

    return squad


# ─────────────────────────────────────────────────────────────────────────────
#  Full snapshot
# ─────────────────────────────────────────────────────────────────────────────

def fetch_all_squads(
    context:   BrowserContext,
    league_id: str = LEAGUE_ID,
) -> list[dict]:
    """
    Runs endpoints #1 → #2 → #3 and returns a squad dict per member.

    Parameters
    ----------
    league_id : str
        The league to fetch. Defaults to config.LEAGUE_ID but can be
        overridden at call time (used by the interactive CLI).
    """
    print("  [scraper] Fetching team/nation mapping (endpoint #1)...")
    teams_map = get_teams_mapping(context)

    print(f"  [scraper] Fetching league members for {league_id} (endpoint #2)...")
    members = fetch_league_users(context, league_id)

    if not members:
        print("  [scraper] WARNING: no members found — check session & league ID.")
        return []

    squads: list = []
    print("  [scraper] Fetching individual rosters (endpoint #3)...")
    for member in members:
        squad = fetch_structured_squad(
            context,
            user_id   = member["user_id"],
            user_name = member["user_name"],
            team_name = member["team_name"],
            teams_map = teams_map,
        )
        starters = sum(1 for p in squad["players"] if not p["is_bench"])
        benched  = sum(1 for p in squad["players"] if p["is_bench"])
        print(f"    + {member['user_name']} — {starters} starters, {benched} bench")
        squads.append(squad)

    return squads


# ─────────────────────────────────────────────────────────────────────────────
#  Utility
# ─────────────────────────────────────────────────────────────────────────────

def _dump_once(filename: str, data) -> None:
    """Write data as JSON only if the file doesn't already exist."""
    if not DEBUG:
        return
    path = os.path.join(os.getcwd(), filename)
    if not os.path.exists(path) and data:
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            print(f"  [scraper] Saved dump -> {path}")
        except Exception:
            pass


def _dump_always(filename: str, data) -> None:
    """Write data as JSON unconditionally (overwrites existing file)."""
    if not DEBUG:
        return
    path = os.path.join(os.getcwd(), filename)
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        print(f"  [scraper] Debug dump -> {path}")
    except Exception:
        pass


# ─────────────────────────────────────────────────────────────────────────────
#  TDD Helper Functions
# ─────────────────────────────────────────────────────────────────────────────

WORLD_CUP_COUNTRY_MAP = {
    # 1. Germany
    "germany": "גרמניה",
    "גרמניה": "גרמניה",
    
    # 2. England
    "england": "אנגליה",
    "אנגליה": "אנגליה",
    
    # 3. Portugal
    "portugal": "פורטוגל",
    "פורטוגל": "פורטוגל",
    
    # 4. Czech Republic
    "czechrepublic": "צ`כיה",
    "czechia": "צ`כיה",
    "צכיה": "צ`כיה",
    
    # 5. Belgium
    "belgium": "בלגיה",
    "בלגיה": "בלגיה",
    
    # 6. Netherlands
    "netherlands": "הולנד",
    "הולנד": "הולנד",
    
    # 7. Croatia
    "croatia": "קרואטיה",
    "קרואטיה": "קרואטיה",
    
    # 8. Switzerland
    "switzerland": "שווייץ",
    "שווייץ": "שווייץ",
    "שוויץ": "שווייץ",
    
    # 9. Scotland
    "scotland": "סקוטלנד",
    "סקוטלנד": "סקוטלנד",
    
    # 10. Spain
    "spain": "ספרד",
    "ספרד": "ספרד",
    
    # 11. France
    "france": "צרפת",
    "צרפת": "צרפת",
    
    # 12. Turkey
    "turkey": "טורקיה",
    "türkiye": "טורקיה",
    "טורקיה": "טורקיה",
    
    # 13. Austria
    "austria": "אוסטריה",
    "אוסטריה": "אוסטריה",
    
    # 14. Mexico
    "mexico": "מקסיקו",
    "מקסיקו": "מקסיקו",
    
    # 15. Brazil
    "brazil": "ברזיל",
    "ברזיל": "ברזיל",
    
    # 16. Paraguay
    "paraguay": "פרגוואי",
    "פרגוואי": "פרגוואי",
    
    # 17. Sweden
    "sweden": "שוודיה",
    "שוודיה": "שוודיה",
    
    # 18. Iran
    "iran": "איראן",
    "איראן": "איראן",
    "אירן": "איראן",
    
    # 19. Argentina
    "argentina": "ארגנטינה",
    "ארגנטינה": "ארגנטינה",
    
    # 20. Ghana
    "ghana": "גאנה",
    "גאנה": "גאנה",
    
    # 21. Colombia
    "colombia": "קולומביה",
    "קולומביה": "קולומביה",
    
    # 22. Norway
    "norway": "נורווגיה",
    "נורווגיה": "נורווגיה",
    
    # 23. Saudi Arabia
    "saudiarabia": "ערב הסעודית",
    "ערבהסעודית": "ערב הסעודית",
    
    # 24. Ecuador
    "ecuador": "אקוואדור",
    "אקוודור": "אקוואדור",
    "אקוואדור": "אקוואדור",
    
    # 25. USA
    "usa": "ארה\"ב",
    "unitedstates": "ארה\"ב",
    "unitedstatesofamerica": "ארה\"ב",
    "ארצותהברית": "ארה\"ב",
    "ארהב": "ארה\"ב",
    
    # 26. Bosnia
    "bosnia": "בוסניה והרצגובינה",
    "bosniaherzegovina": "בוסניה והרצגובינה",
    "bosniaandherzegovina": "בוסניה והרצגובינה",
    "בוסניה": "בוסניה והרצגובינה",
    "בוסניהוהרצגובינה": "בוסניה והרצגובינה",
    
    # 27. South Korea
    "southkorea": "דרום קוריאה",
    "korearepublic": "דרום קוריאה",
    "korea": "דרום קוריאה",
    "קוריאההדרומית": "דרום קוריאה",
    "דרוםקוריאה": "דרום קוריאה",
    
    # 28. Canada
    "canada": "קנדה",
    "קנדה": "קנדה",
    
    # 29. Morocco
    "morocco": "מרוקו",
    "מרוקו": "מרוקו",
    
    # 30. Ivory Coast
    "ivorycoast": "חוף השנהב",
    "côtédivoire": "חוף השנהב",
    "חוףהשנהב": "חוף השנהב",
    
    # 31. Japan
    "japan": "יפן",
    "יפן": "יפן",
    
    # 32. New Zealand
    "newzealand": "ניו זילנד",
    "ניוזילנד": "ניו זילנד",
    
    # 33. Uruguay
    "uruguay": "אורוגוואי",
    "אורוגוואי": "אורוגוואי",
    
    # 34. Senegal
    "senegal": "סנגל",
    "סנגל": "סנגל",
    
    # 35. Algeria
    "algeria": "אלג`יריה",
    "אלגיריה": "אלג`יריה",
    "אלגריה": "אלג`יריה",
    
    # 36. Congo DR
    "congodr": "הרפובליקה הדמוקרטית של קונגו",
    "drcongo": "הרפובליקה הדמוקרטית של קונגו",
    "democraticrepublicofthecongo": "הרפובליקה הדמוקרטית של קונגו",
    "קונגו": "הרפובליקה הדמוקרטית של קונגו",
    "הרפובליקההדמוקרטיתשלקונגו": "הרפובליקה הדמוקרטית של קונגו",
    
    # 37. Panama
    "panama": "פנמה",
    "פנמה": "פנמה",
    
    # 38. Uzbekistan
    "uzbekistan": "אוזבקיסטן",
    "אוזבקיסטן": "אוזבקיסטן",
    
    # 39. Jordan
    "jordan": "ירדן",
    "ירדן": "ירדן",
    
    # 40. Iraq
    "iraq": "עיראק",
    "עיראק": "עיראק",
    
    # 41. Cape Verde
    "capeverde": "כף ורדה",
    "קייפורדה": "כף ורדה",
    "כףורדה": "כף ורדה",
    
    # 42. Egypt
    "egypt": "מצרים",
    "מצרים": "מצרים",
    
    # 43. Tunisia
    "tunisia": "תוניסיה",
    "תוניסיה": "תוניסיה",
    
    # 44. Curacao
    "curacao": "קורוסאו",
    "curaçao": "קורוסאו",
    "קיראסאו": "קורוסאו",
    "קורוסאו": "קורוסאו",
    
    # 45. Australia
    "australia": "אוסטרליה",
    "אוסטרליה": "אוסטרליה",
    
    # 46. Haiti
    "haiti": "האיטי",
    "האיטי": "האיטי",
    "הייטי": "האיטי",
    
    # 47. Qatar
    "qatar": "קטאר",
    "קטאר": "קטאר",
    
    # 48. South Africa
    "southafrica": "דרום אפריקה",
    "דרוםאפריקה": "דרום אפריקה"
}

def normalize_country_name(name: str) -> str:
    """Normalize country names from API to match strictly what Sport5 returns."""
    if not name:
        return ""
    
    # Sanitize lookup key: strip spaces, quotes, ampersands, dashes, and convert to lowercase
    key = "".join(name.split())
    for char in ('"', "'", '״', '׳', '’', '`', '&', '-', ',', '.', '(', ')'):
        key = key.replace(char, '')
    key = key.lower()
    
    return WORLD_CUP_COUNTRY_MAP.get(key, name)


def sanitize_player_name(name: str) -> str:
    """Replace backticks with standard single quotes to prevent Markdown parsing issues."""
    if not name:
        return ""
    return name.replace("`", "'")


def filter_matches_by_date(schedule: list[dict], start_date_str: str, end_date_str: str) -> list[dict]:
    """Filter upcoming matches strictly using the active round's start and end date boundaries."""
    if not schedule:
        return []
    if not start_date_str or not end_date_str:
        return schedule
        
    try:
        from zoneinfo import ZoneInfo
    except ImportError:
        from backports.zoneinfo import ZoneInfo
        
    IL_TZ = ZoneInfo("Asia/Jerusalem")
    
    try:
        start_dt = datetime.fromisoformat(start_date_str).replace(tzinfo=IL_TZ)
        end_dt = datetime.fromisoformat(end_date_str).replace(tzinfo=IL_TZ)
    except Exception:
        try:
            start_dt = start_date_str.replace(tzinfo=IL_TZ) if hasattr(start_date_str, "replace") else start_date_str
            end_dt = end_date_str.replace(tzinfo=IL_TZ) if hasattr(end_date_str, "replace") else end_date_str
        except Exception:
            return schedule

    filtered = []
    for m in schedule:
        kickoff = m.get("kickoff_time")
        if not kickoff:
            continue
            
        if isinstance(kickoff, str):
            try:
                kickoff_dt = datetime.fromisoformat(kickoff).replace(tzinfo=IL_TZ)
            except Exception:
                continue
        else:
            kickoff_dt = kickoff
            
        try:
            if start_dt <= kickoff_dt <= end_dt:
                filtered.append(m)
        except Exception:
            filtered.append(m)
            
    return filtered
