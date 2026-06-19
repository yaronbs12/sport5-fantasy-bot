"""
test_run.py
-----------
Standalone integration test for the Sport5 Fantasy Bot.

► Does NOT require Playwright or a live Sport5 session.
► Injects mock squad data (10 league members, realistic German/Argentine players).
► Temporarily overrides alert_state.json and the match schedule so every
  alert type fires immediately.
► Prints the full expected terminal output so you can visually confirm that
  all Hebrew texts, captain labels, and timing logic are correct.

Run with:
    python test_run.py
"""

import os
import sys
import json
import shutil
from datetime import datetime, timedelta

# ── Make sure we import from our project directory ──────────────────────────
sys.path.insert(0, os.path.dirname(__file__))

# ── Patch the schedule BEFORE importing config so test timings are injected ─
import config as _cfg
try:
    from zoneinfo import ZoneInfo
except ImportError:
    from backports.zoneinfo import ZoneInfo

IL_TZ = ZoneInfo("Asia/Jerusalem")

def _now():
    return datetime.now(tz=IL_TZ)

# Create two test matches whose kickoff is exactly 1 hour from NOW
# → triggers both Alert 1 (1h deadline) and Alert 2 (match preview) for Round 1
# Also create a third match exactly 3 hours from NOW for Round 2
# → triggers Alert 1 (3h deadline)

_t1h = _now() + timedelta(seconds=3600)   # 1 hour from now
_t3h = _now() + timedelta(seconds=10800)  # 3 hours from now

PATCHED_SCHEDULE = [
    {
        "match_id":    "test_r1_m1",
        "round_id":    "test1",
        "home_team":   "גרמניה",
        "away_team":   "סקוטלנד",
        "kickoff_time": _t1h,
    },
    {
        "match_id":    "test_r1_m2",
        "round_id":    "test1",
        "home_team":   "ארגנטינה",
        "away_team":   "מקסיקו",
        "kickoff_time": _t1h + timedelta(hours=2),  # same round, 3h from now
    },
    {
        "match_id":    "test_r2_m1",
        "round_id":    "test2",
        "home_team":   "צרפת",
        "away_team":   "איטליה",
        "kickoff_time": _t3h,
    },
]

# Inject into config before notifier imports it
_cfg.MATCH_SCHEDULE = PATCHED_SCHEDULE
_cfg.FIRST_KICKOFF_PER_ROUND = _cfg.get_first_kickoff_per_round(PATCHED_SCHEDULE)
# Widen the window to 120s so minor timing offsets don't miss the trigger
_cfg.ALERT_WINDOW_SECONDS = 120

# Now import notifier (which reads config at import time via module-level vars)
from notifier import evaluate_alerts, build_match_preview_alert, build_substitution_alert, rtl

# Convenience: a kickoff time for tests (1h from now)
_KICKOFF_TEST = _now() + timedelta(seconds=3600)

# ─────────────────────────────────────────────────────────────────────────────
#  Mock squad data – 5 league members with German and Argentine players
# ─────────────────────────────────────────────────────────────────────────────

MOCK_SQUADS = [
    {
        "user_name": "יוסי כהן",
        "team_name": "הצוות של יוסי",
        "players": [
            {"name": "מולר",     "nation": "גרמניה",    "is_bench": False, "role": "captain"},
            {"name": "גנאברי",   "nation": "גרמניה",    "is_bench": False, "role": "player"},
            {"name": "נוישטר",   "nation": "גרמניה",    "is_bench": True,  "role": "player"},
            {"name": "מסי",      "nation": "ארגנטינה",  "is_bench": False, "role": "player"},
            {"name": "די מריה",  "nation": "ארגנטינה",  "is_bench": True,  "role": "player"},
        ],
    },
    {
        "user_name": "דני לוי",
        "team_name": "דני FC",
        "players": [
            {"name": "כימיך",    "nation": "גרמניה",    "is_bench": False, "role": "sub_captain"},
            {"name": "רויס",     "nation": "גרמניה",    "is_bench": True,  "role": "player"},
            {"name": "לאוטרו",   "nation": "ארגנטינה",  "is_bench": False, "role": "player"},
            {"name": "אלוורז",   "nation": "ארגנטינה",  "is_bench": False, "role": "captain"},
            {"name": "אוטמנדי",  "nation": "ארגנטינה",  "is_bench": True,  "role": "player"},
        ],
    },
    {
        "user_name": "רון אבידן",
        "team_name": "רון יוניטד",
        "players": [
            {"name": "זאנה",     "nation": "גרמניה",    "is_bench": False, "role": "player"},
            {"name": "הברץ",     "nation": "גרמניה",    "is_bench": True,  "role": "player"},
            {"name": "מבאפה",    "nation": "צרפת",      "is_bench": False, "role": "captain"},
            {"name": "בנזמה",    "nation": "צרפת",      "is_bench": False, "role": "player"},
        ],
    },
    {
        "user_name": "שירה מזרחי",
        "team_name": "שירה גולס",
        "players": [
            {"name": "רודריגז",  "nation": "ארגנטינה",  "is_bench": False, "role": "player"},
            {"name": "מרטינז",   "nation": "ארגנטינה",  "is_bench": False, "role": "player"},
            {"name": "סלאח",     "nation": "מצרים",     "is_bench": False, "role": "captain"},
        ],
    },
    {
        "user_name": "עמית שלום",
        "team_name": "עמית פאוור",
        "players": [
            {"name": "הוורץ",    "nation": "גרמניה",    "is_bench": False, "role": "player"},
            {"name": "פולקרוג",  "nation": "גרמניה",    "is_bench": True,  "role": "player"},
            {"name": "נויר",     "nation": "גרמניה",    "is_bench": False, "role": "player"},  # GK – starting
            {"name": "פורנלס",   "nation": "ספרד",      "is_bench": False, "role": "captain"},
        ],
    },
]

# ─────────────────────────────────────────────────────────────────────────────
#  Helpers
# ─────────────────────────────────────────────────────────────────────────────

DIVIDER = "─" * 60

def print_section(title: str) -> None:
    print(f"\n{'═' * 60}")
    print(f"  {title}")
    print('═' * 60)


def emit(text: str) -> None:
    print(DIVIDER)
    for line in text.splitlines():
        print(f"  {line}")
    print(DIVIDER)


# ─────────────────────────────────────────────────────────────────────────────
#  1. Timezone sanity check
# ─────────────────────────────────────────────────────────────────────────────

print_section("✔ PHASE 1 – Israel Timezone Sanity Check")

now    = _now()
offset = now.utcoffset()
print(f"  Current Israel time : {now.strftime('%Y-%m-%d %H:%M:%S %Z')}")
print(f"  UTC offset          : {offset}")
print(f"  Expected offset     : +02:00 (winter) or +03:00 (summer/DST)")

t1_delta = int((_t1h - now).total_seconds() / 60)
t3_delta = int((_t3h - now).total_seconds() / 60)
print(f"  Test match 1 in     : ~{t1_delta} minutes  → will trigger 1h alerts")
print(f"  Test match 3 in     : ~{t3_delta} minutes  → will trigger 3h deadline alert")

# ─────────────────────────────────────────────────────────────────────────────
#  2. Text builder unit tests (independent of timing)
# ─────────────────────────────────────────────────────────────────────────────

print_section("✔ PHASE 2 – Hebrew Text Builder Unit Tests")

print("\n[Alert 1 – 3h deadline]")
emit(build_substitution_alert(3))

print("\n[Alert 1 – 1h deadline]")
emit(build_substitution_alert(1))

print("\n[Alert 2 – גרמניה preview]")
emit(build_match_preview_alert("גרמניה", "סקוטלנד", _KICKOFF_TEST, MOCK_SQUADS))

print("\n[Alert 2 – ארגנטינה preview]")
emit(build_match_preview_alert("ארגנטינה", "מקסיקו", _KICKOFF_TEST, MOCK_SQUADS))

print("\n[Alert 2 – נבחרת ללא שחקנים בליגה (סקוטלנד)]")
emit(build_match_preview_alert("סקוטלנד", "גרמניה", _KICKOFF_TEST, MOCK_SQUADS))

# ─────────────────────────────────────────────────────────────────────────────
#  3. Full evaluate_alerts() integration test
# ─────────────────────────────────────────────────────────────────────────────

print_section("✔ PHASE 3 – Full evaluate_alerts() Integration Test")

# Clear alert state so nothing is "already sent"
state_file = _cfg.ALERT_STATE_FILE
if os.path.exists(state_file):
    backup = state_file + ".bak"
    shutil.copy(state_file, backup)
    os.remove(state_file)
    print(f"  (Backed up existing alert_state.json → {backup})")

sent = set()
alerts = evaluate_alerts(MOCK_SQUADS, sent)

print(f"\n  Alerts triggered    : {len(alerts)}")
print(f"  Alert keys in state : {sorted(sent)}\n")

if alerts:
    for i, a in enumerate(alerts, 1):
        print(f"  ── Alert #{i} ──")
        emit(a)
else:
    print("  ⚠️  No alerts fired. Check timing offsets or ALERT_WINDOW_SECONDS.")

# ─────────────────────────────────────────────────────────────────────────────
#  4. De-duplication test
# ─────────────────────────────────────────────────────────────────────────────

print_section("✔ PHASE 4 – De-duplication (no double alerts)")

alerts_again = evaluate_alerts(MOCK_SQUADS, sent)
if len(alerts_again) == 0:
    print("  ✅ PASS – evaluate_alerts() returned 0 alerts on second call (already sent).")
else:
    print(f"  ❌ FAIL – {len(alerts_again)} alert(s) fired again!")
    for a in alerts_again:
        print(a)

# ─────────────────────────────────────────────────────────────────────────────
#  Done
# ─────────────────────────────────────────────────────────────────────────────

print_section("✔ ALL TESTS COMPLETE")
print("  Run  python main.py  to start the live monitoring loop.\n")
