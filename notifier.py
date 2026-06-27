"""
notifier.py
-----------
Alert logic and Hebrew text generation.

New:  build_match_report()  — on-demand match summary for the CLI tool
      Generates the exact schema:
        ⚽ [Team A] נגד [Team B]!
        הנה השחקנים שלכם שעל המגרש:
        • [Member]: [Player A], [Player B]
        • [Member B]: [Player C] (C)
        * שחקנים על הספסל למשחק זה: [Member] ([Player] - ספסל)
        👑 קפטן פעיל במשחק זה: [Member] ([Player])

Kept:  build_substitution_alert()  — used by live-loop mode / test_run.py
       build_match_preview_alert() — used by live-loop mode / test_run.py
       evaluate_alerts()           — used by live-loop mode / test_run.py
"""

import json
import logging
import os
from datetime import datetime

import config
from config import (
    IL_TZ,
    ALERT_WINDOW_SECONDS,
    ALERT_STATE_FILE,
)
from display import format_bidi

logger = logging.getLogger(__name__)


# backward-compat alias
rtl = format_bidi

# Hebrew day names
_HE_DAYS = ["שני", "שלישי", "רביעי", "חמישי", "שישי", "שבת", "ראשון"]


# ─────────────────────────────────────────────────────────────────────────────
#  Persistent alert state
# ─────────────────────────────────────────────────────────────────────────────

def load_sent_alerts() -> set:
    if os.path.exists(ALERT_STATE_FILE):
        try:
            with open(ALERT_STATE_FILE, "r", encoding="utf-8") as f:
                return set(json.load(f))
        except Exception:
            pass
    return set()


def save_sent_alerts(sent: set) -> None:
    try:
        with open(ALERT_STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(list(sent), f, ensure_ascii=False, indent=2)
    except Exception as exc:
        logger.error("Failed to save alert state: %s", exc)


# ─────────────────────────────────────────────────────────────────────────────
#  Time utilities
# ─────────────────────────────────────────────────────────────────────────────

def now_il() -> datetime:
    return datetime.now(tz=IL_TZ)


def seconds_until(target: datetime) -> float:
    return (target - now_il()).total_seconds()


def _within_window(delta: float, offset: int) -> bool:
    return abs(delta - offset) <= ALERT_WINDOW_SECONDS


def _fmt_time(dt: datetime) -> str:
    return dt.strftime("%H:%M")


def _fmt_date_he(dt: datetime) -> str:
    """Format kickoff date/time in Hebrew: 'יום שישי 20/06 | 22:00'."""
    day_he = _HE_DAYS[dt.weekday()]
    return f"יום {day_he} {dt.day:02d}/{dt.month:02d} | {dt.strftime('%H:%M')}"


# ─────────────────────────────────────────────────────────────────────────────
#  Player label helper
# ─────────────────────────────────────────────────────────────────────────────

def _label(p: dict) -> str:
    """Player name + role suffix (C) / (VC)."""
    suffix = " (C)" if p["role"] == "captain" else " (VC)" if p["role"] == "sub_captain" else ""
    return p["name"] + suffix


def _label_with_nation(p: dict) -> str:
    """
    Player name + role suffix + nation in parentheses.
    Example: 'מולר (C) (גרמניה)'
    """
    role_suffix = " (C)" if p["role"] == "captain" else " (VC)" if p["role"] == "sub_captain" else ""
    return f"{p['name']}{role_suffix} ({p['nation']})"


# ─────────────────────────────────────────────────────────────────────────────
#  Cross-reference helper
# ─────────────────────────────────────────────────────────────────────────────

def _players_for_nation(nation: str, squads: list[dict]) -> list[dict]:
    """
    Returns entries for members with ≥1 STARTER from *nation*.
    [{member_name, starters:[], bench:[]}, ...]
    """
    results = []
    for squad in squads:
        starters, bench = [], []
        for p in squad["players"]:
            if p["nation"] != nation:
                continue
            entry = {"name": p["name"], "role": p["role"]}
            (bench if p["is_bench"] else starters).append(entry)
        if starters:
            results.append({
                "member_name": squad["user_name"],
                "starters":    starters,
                "bench":       bench,
            })
    return results


# ─────────────────────────────────────────────────────────────────────────────
#  ★  NEW: on-demand match report  (CLI tool)
# ─────────────────────────────────────────────────────────────────────────────

def build_match_report(
    home_team:  str,
    away_team:  str,
    kickoff:    datetime,
    squads:     list[dict],
    apply_bidi: bool = True,
) -> str:
    """
    Generates a complete Hebrew match report for ONE match.

    Layout:
        ⚽ [home] נגד [away]!
        📅 יום [day] DD/MM | HH:MM

        🟢 שחקנים שלכם שפותחים בהרכב:
        • [Member]: [Player (C)] ([Nation])
        • [Member]: [Player] ([Nation]), [Player2] ([Nation])

        🛑 שחקנים שלכם שמחכים על הספסל:
        • [Member]: [Player] ([Nation])
        (or: • אין שחקנים למשחק זה)

        👑 קפטן פעיל במשחק: [Member] ([Player])

    Parameters
    ----------
    apply_bidi : bool
        True  → apply format_bidi() for terminal display.
        False → raw logical Hebrew (for file save / Telegram / WhatsApp).
    """
    # ── Collect per-member starters and bench for BOTH teams ─────────────────
    # Ordered dicts preserve insertion order (member with first player encountered first)
    starters_by_member: dict[str, list[dict]] = {}
    bench_by_member:    dict[str, list[dict]] = {}
    captain_member: str | None = None
    captain_player: str | None = None

    for squad in squads:
        m_name = squad["user_name"]
        for p in squad["players"]:
            if p["nation"] not in (home_team, away_team):
                continue
            if p["is_bench"]:
                bench_by_member.setdefault(m_name, []).append(p)
            else:
                starters_by_member.setdefault(m_name, []).append(p)
                if p["role"] == "captain" and captain_member is None:
                    captain_member = m_name
                    captain_player = p["name"]

    # ── Build raw lines (logical Hebrew order) ────────────────────────────────
    raw_lines: list[str] = [
        f"⚽ {home_team} נגד {away_team}!",
        f"📅 {_fmt_date_he(kickoff)}",
        "",
        "🟢 שחקנים שלכם שפותחים בהרכב:",
    ]

    if starters_by_member:
        starter_items = list(starters_by_member.items())
        for i, (m_name, players) in enumerate(starter_items):
            labels = ", ".join(_label_with_nation(p) for p in players)
            raw_lines.append(f"• {m_name}: {labels}")
            if i < len(starter_items) - 1:
                raw_lines.append("")
    else:
        raw_lines.append("• אין שחקנים למשחק זה")

    raw_lines.extend(["", "🛑 שחקנים שלכם שמחכים על הספסל:"])

    if bench_by_member:
        bench_items = list(bench_by_member.items())
        for i, (m_name, players) in enumerate(bench_items):
            labels = ", ".join(_label_with_nation(p) for p in players)
            raw_lines.append(f"• {m_name}: {labels}")
            if i < len(bench_items) - 1:
                raw_lines.append("")
    else:
        raw_lines.append("• אין שחקנים למשחק זה")

    if captain_member and captain_player:
        raw_lines.extend(["", f"👑 קפטן פעיל במשחק: {captain_member} ({captain_player})"])

    # ── Apply bidi per-line ───────────────────────────────────────────────────
    if apply_bidi:
        return "\n".join(format_bidi(ln) for ln in raw_lines)
    return "\n".join(raw_lines)


# ─────────────────────────────────────────────────────────────────────────────
#  Legacy builders (kept for test_run.py / future live-loop mode)
# ─────────────────────────────────────────────────────────────────────────────

def build_substitution_alert(hours: int) -> str:
    time_str = "שעה" if hours == 1 else f"{hours} שעות"
    lines = [
        f"🚨 חלון החילופים נסגר בעוד {time_str}!",
        "אל תשכחו לעדכן ולהחליף הרכבים!",
    ]
    return "\n".join(format_bidi(ln) for ln in lines)


def build_match_preview_alert(
    nation:   str,
    opponent: str,
    kickoff:  datetime,
    squads:   list[dict],
) -> str:
    time_str = _fmt_time(kickoff)
    members  = _players_for_nation(nation, squads)

    raw_lines = [
        f"⚽ בעוד שעה ({time_str}): {nation} נגד {opponent}",
        "השחקנים שלכם שמתחילים:",
    ]

    captain_member = captain_player = None
    if members:
        for entry in members:
            sl = [_label(p) for p in entry["starters"]]
            bl = [_label(p) for p in entry["bench"]]
            line = f"• {entry['member_name']}: {', '.join(sl)}"
            if bl:
                line += f"  |  ספסל: {', '.join(bl)}"
            raw_lines.append(line)
            for p in entry["starters"]:
                if p["role"] == "captain" and captain_member is None:
                    captain_member = entry["member_name"]
                    captain_player = p["name"]
    else:
        raw_lines.append(f"• אין שחקנים מתחילים מ{nation} בהרכבי הליגה")

    if captain_member:
        raw_lines.append(f"👑 קפטן פעיל: {captain_member} ({captain_player})")

    return "\n".join(format_bidi(ln) for ln in raw_lines)


# ─────────────────────────────────────────────────────────────────────────────
#  evaluate_alerts — for live-loop mode (kept, not used by CLI)
# ─────────────────────────────────────────────────────────────────────────────

def evaluate_alerts(squads: list[dict], sent_alerts: set) -> list[str]:
    alerts: list[str] = []
    schedule = config.MATCH_SCHEDULE
    first_ko = config.FIRST_KICKOFF_PER_ROUND

    for label, offset in sorted(config.ALERT_OFFSETS.items(), key=lambda x: -x[1]):
        hours = offset // 3600
        for round_id, first_kickoff in first_ko.items():
            secs = seconds_until(first_kickoff)
            key = f"deadline_r{round_id}_{label}"
            if key not in sent_alerts and _within_window(secs, offset):
                alerts.append(build_substitution_alert(hours))
                sent_alerts.add(key)

    for match in schedule:
        secs = seconds_until(match["kickoff_time"])
        for side in ("home", "away"):
            nation   = match[f"{side}_team"]
            opponent = match["away_team"] if side == "home" else match["home_team"]
            key      = f"preview_{match['match_id']}_{side}"
            if key not in sent_alerts and _within_window(secs, 3600):
                alerts.append(
                    build_match_preview_alert(nation, opponent, match["kickoff_time"], squads)
                )
                sent_alerts.add(key)

    return alerts
