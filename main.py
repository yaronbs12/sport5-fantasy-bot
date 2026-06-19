"""
main.py
-------
Sport5 Fantasy Football CLI Tool

Interactive flow:
  1. Auth  → check/acquire Sport5 session (opens browser if needed)
  2. League → prompt for league name, search GetLeaguesSummary, fallback to manual ID
  3. N      → prompt for number of upcoming matches to analyze
  4. Report → fetch rosters + next N matches, print Hebrew match reports immediately
  5. Loop   → ask to repeat with different league / N
"""

import sys
import os
import re
from datetime import datetime

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

from playwright.sync_api import sync_playwright

from config           import SEASON_ID
from display          import format_bidi
from login            import ensure_authenticated
from schedule_fetcher import fetch_live_schedule
from scraper          import (
    create_browser_context,
    fetch_leagues_summary,
    fetch_all_squads,
)
from notifier         import build_match_report, now_il

DIVIDER_HEAVY = "═" * 58
DIVIDER_LIGHT = "─" * 58
OUTPUT_DIR    = os.getcwd()


# ─────────────────────────────────────────────────────────────────────────────
#  Helpers
# ─────────────────────────────────────────────────────────────────────────────

def hr(heavy: bool = False) -> None:
    print(DIVIDER_HEAVY if heavy else DIVIDER_LIGHT)


def section(title: str) -> None:
    print()
    hr(heavy=True)
    print(f"  {title}")
    hr(heavy=True)


def save_reports(reports: list[str], league_id: str) -> str:
    """Save reports (logical Hebrew, no bidi) to a timestamped text file."""
    ts       = now_il().strftime("%Y%m%d_%H%M%S")
    filename = os.path.join(OUTPUT_DIR, f"match_reports_{league_id}_{ts}.txt")
    try:
        with open(filename, "w", encoding="utf-8") as f:
            f.write("\n\n".join(reports))
        return filename
    except Exception as exc:
        print(f"  [save] Could not write file: {exc}")
        return ""


# ─────────────────────────────────────────────────────────────────────────────
#  Step 2 — League selection
# ─────────────────────────────────────────────────────────────────────────────

def normalize_league_name(s: str) -> str:
    """
    Normalizes a league name string for robust matching.
    Strips all spaces and removes/replaces quotes, gershayim, and apostrophes.
    """
    if not s:
        return ""
    # Strip all whitespace characters
    s = "".join(s.split())
    # Remove variations of quotes, gershayim, and apostrophes
    for char in ('"', "'", '״', '׳', '’'):
        s = s.replace(char, '')
    return s.lower()


def prompt_league_id(context) -> str:
    """
    Asks the user for a league name, searches GetLeaguesSummary, and
    returns the resolved league ID as a string.

    Fallback chain:
      name match (exact / partial / case-insensitive)
        → multiple matches → numbered selection
        → no match         → manual ID entry
        → API failure      → manual ID entry
    """
    section("LEAGUE SELECTION")

    print("  Enter your league name to search automatically,")
    print("  or press Enter to type the league ID directly.\n")
    league_name = input("  League name: ").strip()

    leagues = []
    league_id = ""
    resolved_name = ""

    if league_name:
        # ── Search via API ───────────────────────────────────────────────────────
        print(f"\n  Searching for \"{league_name}\"...")
        leagues = fetch_leagues_summary(context)

        if leagues:
            normalized_input = normalize_league_name(league_name)
            matches = []
            for lg in leagues:
                api_name = lg.get("leagueName") or lg.get("name") or ""
                normalized_api_name = normalize_league_name(api_name)
                if normalized_input and normalized_input in normalized_api_name:
                    matches.append(lg)

            if len(matches) == 1:
                m = matches[0]
                print(f"  ✓ Found: \"{m['leagueName']}\"  (ID: {m['id']})")
                league_id = str(m["id"])
                resolved_name = m.get("leagueName") or m.get("name") or ""

            elif len(matches) > 1:
                print(f"  Multiple matches ({len(matches)}) — choose one:\n")
                for i, m in enumerate(matches, 1):
                    print(f"    {i}. {m['leagueName']}  (ID: {m['id']})")
                while True:
                    raw = input("\n  Enter number: ").strip()
                    if raw.isdigit() and 1 <= int(raw) <= len(matches):
                        m = matches[int(raw) - 1]
                        print(f"  ✓ Selected: \"{m['leagueName']}\"  (ID: {m['id']})")
                        league_id = str(m["id"])
                        resolved_name = m.get("leagueName") or m.get("name") or ""
                        break
                    print("  Invalid choice, try again.")
            else:
                print(f"  No league named \"{league_name}\" found.")
        else:
            print("  Could not retrieve leagues list from API.")

    # ── Fallback: manual ID ──────────────────────────────────────────────────
    if not league_id:
        print("  Please enter the League ID manually.")
        league_id = input("  League ID: ").strip()

    if league_id:
        # Resolve league name from loaded list for blacklist verification
        if not leagues:
            leagues = fetch_leagues_summary(context)
        if leagues:
            matched_lg = next(
                (lg for lg in leagues if lg and (str(lg.get("id")) == league_id or str(lg.get("teamId")) == league_id)),
                None
            )
            if matched_lg:
                resolved_name = matched_lg.get("leagueName") or matched_lg.get("name") or ""

    # ── Guardrail / Blacklist Check ──────────────────────────────────────────
    LEAGUE_BLACKLIST = ["כף ורדה", "ליגת העל", "כללי", "הכללית", "עולמי"]

    # Check if attempts to load a known massive global league ID
    is_massive_id = False
    if not league_id or league_id.lower() in ("0", "null", "none"):
        is_massive_id = True

    # Check blacklist phrases in resolved name
    is_blacklisted = False
    if resolved_name:
        for phrase in LEAGUE_BLACKLIST:
            if phrase in resolved_name:
                is_blacklisted = True
                break

    # Also check if the user's input league_name itself contains a blacklist phrase
    if league_name:
        for phrase in LEAGUE_BLACKLIST:
            if phrase in league_name:
                is_blacklisted = True
                break

    if is_massive_id or is_blacklisted:
        msg = "🚨 חסם בטיחות: הליגה שנבחרה המונית מדי או חסומה (לדוגמה: ליגת כף ורדה או הליגה הכללית). הריצה הופסקה כדי למנוע קריסה וחסימת IP."
        print()
        print(format_bidi(msg))
        print()
        sys.exit(1)

    return league_id


# ─────────────────────────────────────────────────────────────────────────────
#  Step 3 — Match count prompt
# ─────────────────────────────────────────────────────────────────────────────

def prompt_match_count(total_available: int) -> int:
    """Ask how many upcoming matches to analyze."""
    print()
    print(format_bidi(f"  כמה משחקים קרובים ברצונך לבדוק? (1–{total_available} זמינים)"))
    print(f"  How many upcoming matches to analyze? (1–{total_available} available)")
    while True:
        raw = input("  N = ").strip()
        if raw.isdigit() and 1 <= int(raw) <= total_available:
            return int(raw)
        print(f"  Please enter a number between 1 and {total_available}.")


# ─────────────────────────────────────────────────────────────────────────────
#  Step 4 — Match report printer
# ─────────────────────────────────────────────────────────────────────────────

def print_report(report_text: str, match_index: int, total: int) -> None:
    """Print a single match report with index header."""
    print()
    hr(heavy=True)
    print(f"  Match {match_index}/{total}")
    hr(heavy=True)
    for line in report_text.splitlines():
        print(f"  {line}")
    hr()


# ─────────────────────────────────────────────────────────────────────────────
#  Main
# ─────────────────────────────────────────────────────────────────────────────

def main() -> None:
    print()
    print(DIVIDER_HEAVY)
    print("  Sport5 Fantasy Bot — Interactive CLI")
    print("  World Cup 2026 Match Report Generator")
    print(DIVIDER_HEAVY)

    with sync_playwright() as pw:

        # ── Auth ─────────────────────────────────────────────────────────────
        ensure_authenticated(pw)

        # ── Open persistent context (headless=False → WAF bypass) ────────────
        print("  Opening Sport5 session (non-headless, off-screen)...")
        context = create_browser_context(pw)

        # ── Fetch live schedule once ─────────────────────────────────────────
        print("  Fetching World Cup 2026 schedule...")
        schedule = fetch_live_schedule(only_future=True)
        if not schedule:
            print("  ERROR: could not fetch match schedule. Check internet.")
            context.close()
            return
        print(f"  Schedule loaded — {len(schedule)} upcoming matches.\n")

        # ── Interactive loop ─────────────────────────────────────────────────
        while True:

            # 2. League selection
            league_id = prompt_league_id(context)
            if not league_id:
                print("  No league ID provided — exiting.")
                break

            # 3. How many matches?
            n = prompt_match_count(len(schedule))
            selected_matches = schedule[:n]

            # 4. Fetch rosters for this league
            section(f"FETCHING ROSTERS — League {league_id}")
            squads = fetch_all_squads(context, league_id=league_id)

            if not squads:
                print(f"  ERROR: no members found for league {league_id}.")
                print("  Check that the league ID is correct and the session is valid.")
            else:
                # 5. Generate and print reports
                section(f"MATCH REPORTS — Next {n} matches")
                saved_reports = []   # logical Hebrew text (for file save)

                for i, match in enumerate(selected_matches, 1):
                    home    = match["home_team"]
                    away    = match["away_team"]
                    kickoff = match["kickoff_time"]

                    # Build report (logical Hebrew — no bidi yet)
                    logical_text  = build_match_report(home, away, kickoff, squads, apply_bidi=False)
                    # Build report (bidi-formatted for terminal)
                    terminal_text = build_match_report(home, away, kickoff, squads, apply_bidi=True)

                    print_report(terminal_text, i, n)
                    saved_reports.append(logical_text)

                # Save to file (logical Hebrew — renders correctly in any RTL app)
                if saved_reports:
                    saved_path = save_reports(saved_reports, league_id)
                    if saved_path:
                        print(f"\n  Reports saved to: {saved_path}")

            # 6. Continue?
            print()
            again = input("  Analyze another league or different N? (y / n): ").strip().lower()
            if again not in ("y", "yes"):
                break

        context.close()
        print("\n  Done. Goodbye!\n")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n  Stopped by user.")
        sys.exit(0)
    except RuntimeError as e:
        print(str(e))
        sys.exit(1)
