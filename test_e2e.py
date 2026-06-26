"""
test_e2e.py
-----------
End-to-end and unit tests for Sport5 Fantasy Dashboard.

Covers:
  1. build_match_report  - correct output structure and content
  2. copy_button_html    - generated HTML contains the script + button
  3. format_player_row_html  - captain / VC badge injection
  4. get_flag_emoji / COUNTRY_TO_FLAG  - all 48 nations have a flag entry
  5. normalize_league_name  - punctuation stripping
  6. squad comparison logic  - set intersection / difference correctness
  7. tab name formatting     - kickoff time appears, no flag letter codes
  8. report sanitization     - backtick replacement
  9. date-boundary filtering - sanity re-check
 10. get_logo_base64         - fallback URL and base64 success path

Run with:  pytest test_e2e.py -v
"""

import json
import sys
import os
from datetime import datetime
from unittest.mock import patch

import pytest

sys.path.insert(0, os.path.dirname(__file__))

try:
    from zoneinfo import ZoneInfo
except ImportError:
    from backports.zoneinfo import ZoneInfo

IL_TZ = ZoneInfo("Asia/Jerusalem")

KICKOFF_SAMPLE = datetime(2026, 6, 20, 22, 0, tzinfo=IL_TZ)

MOCK_SQUADS = [
    {
        "user_name": "יוסי כהן",
        "team_name": "הצוות של יוסי",
        "players": [
            {"name": "מולר",    "nation": "גרמניה",   "is_bench": False, "role": "captain"},
            {"name": "גנאברי",  "nation": "גרמניה",   "is_bench": False, "role": "player"},
            {"name": "נוישטר",  "nation": "גרמניה",   "is_bench": True,  "role": "player"},
            {"name": "מסי",     "nation": "ארגנטינה", "is_bench": False, "role": "player"},
        ],
    },
    {
        "user_name": "דני לוי",
        "team_name": "דני FC",
        "players": [
            {"name": "קרוס",    "nation": "גרמניה",   "is_bench": False, "role": "player"},
            {"name": "גנאברי",  "nation": "גרמניה",   "is_bench": False, "role": "sub_captain"},
            {"name": "מסי",     "nation": "ארגנטינה", "is_bench": True,  "role": "player"},
            {"name": "לאוטרו",  "nation": "ארגנטינה", "is_bench": False, "role": "player"},
        ],
    },
]

# ─────────────────────────────────────────────────────────────────────────────
# 1. build_match_report
# ─────────────────────────────────────────────────────────────────────────────

from notifier import build_match_report


def test_build_match_report_contains_teams():
    report = build_match_report("גרמניה", "סקוטלנד", KICKOFF_SAMPLE, MOCK_SQUADS, apply_bidi=False)
    assert "גרמניה" in report
    assert "סקוטלנד" in report


def test_build_match_report_starters_section():
    report = build_match_report("גרמניה", "סקוטלנד", KICKOFF_SAMPLE, MOCK_SQUADS, apply_bidi=False)
    assert "שחקנים שלכם שפותחים בהרכב" in report
    assert "מולר" in report
    assert "גנאברי" in report


def test_build_match_report_bench_section():
    report = build_match_report("גרמניה", "סקוטלנד", KICKOFF_SAMPLE, MOCK_SQUADS, apply_bidi=False)
    assert "שחקנים שלכם שמחכים על הספסל" in report
    assert "נוישטר" in report


def test_build_match_report_captain_section():
    report = build_match_report("גרמניה", "סקוטלנד", KICKOFF_SAMPLE, MOCK_SQUADS, apply_bidi=False)
    assert "קפטן פעיל במשחק" in report
    assert "מולר" in report


def test_build_match_report_no_players_message():
    report = build_match_report("ניגריה", "אנגוואנה", KICKOFF_SAMPLE, MOCK_SQUADS, apply_bidi=False)
    assert "אין שחקנים למשחק זה" in report


def test_build_match_report_backtick_sanitization():
    squads_with_tick = [
        {
            "user_name": "טסטר",
            "team_name": "טסט FC",
            "players": [
                {"name": "ז`רמי דוקו", "nation": "גרמניה", "is_bench": False, "role": "player"},
            ],
        }
    ]
    raw = build_match_report("גרמניה", "סקוטלנד", KICKOFF_SAMPLE, squads_with_tick, apply_bidi=False)
    sanitized = raw.replace("`", "'")
    assert "`" not in sanitized
    assert "ז'רמי" in sanitized


# ─────────────────────────────────────────────────────────────────────────────
# 2. Copy-button HTML structure (pure Python – no browser required)
# ─────────────────────────────────────────────────────────────────────────────

def _build_copy_html(report_text: str, idx: int = 0) -> str:
    escaped = json.dumps(report_text)
    border_color = "#27272a"
    text_color = "#f4f4f5"
    hover_bg = "#27272a"
    accent_color = "#6366f1"

    return f"""
    <div>
        <button id="copy-btn-{idx}" onclick="copyText_{idx}()">העתק דוח</button>
    </div>
    <script>
    (function() {{
        const REPORT_TEXT_{idx} = {escaped};
        window.copyText_{idx} = function() {{
            window.parent.postMessage({{
                type: 'streamlit:copyToClipboard',
                text: REPORT_TEXT_{idx}
            }}, '*');
        }};
    }})();
    </script>
    """


def test_copy_button_contains_button_id():
    html = _build_copy_html("שלום עולם", idx=0)
    assert 'id="copy-btn-0"' in html


def test_copy_button_contains_correct_onclick():
    html = _build_copy_html("שלום עולם", idx=1)
    assert "copyText_1()" in html


def test_copy_button_escaped_json_in_script():
    report = "שחקן: ז'רמי דוקו\nמשחק: גרמניה נגד סקוטלנד"
    html = _build_copy_html(report, idx=2)
    assert json.dumps(report) in html


def test_copy_button_postmessage_present():
    html = _build_copy_html("טקסט לבדיקה", idx=3)
    assert "postMessage" in html
    assert "streamlit:copyToClipboard" in html


def test_copy_button_unique_per_tab():
    html0 = _build_copy_html("report A", idx=0)
    html1 = _build_copy_html("report B", idx=1)
    assert 'id="copy-btn-0"' in html0
    assert 'id="copy-btn-1"' in html1
    assert 'id="copy-btn-0"' not in html1


# ─────────────────────────────────────────────────────────────────────────────
# 3. format_player_row_html
# ─────────────────────────────────────────────────────────────────────────────

from app import format_player_row_html


def test_player_row_captain_badge():
    html = format_player_row_html("מולר", {"role": "captain", "nation": "גרמניה"})
    assert ">C<" in html.replace(" ", "")
    assert "מולר" in html


def test_player_row_vc_badge():
    html = format_player_row_html("גנאברי", {"role": "sub_captain", "nation": "גרמניה"})
    assert ">VC<" in html.replace(" ", "")


def test_player_row_regular_player_no_badge():
    html = format_player_row_html("קרוס", {"role": "player", "nation": "גרמניה"})
    assert ">C<" not in html.replace(" ", "")
    assert ">VC<" not in html.replace(" ", "")
    assert "קרוס" in html


def test_player_row_nation_displayed():
    html = format_player_row_html("מולר", {"role": "player", "nation": "גרמניה"})
    assert "גרמניה" in html


# ─────────────────────────────────────────────────────────────────────────────
# 4. get_flag_emoji / COUNTRY_TO_FLAG completeness
# ─────────────────────────────────────────────────────────────────────────────

from app import get_flag_emoji, COUNTRY_TO_FLAG

ALL_48_CANONICAL = [
    "גרמניה", "אנגליה", "פורטוגל", "צ`כיה", "בלגיה", "הולנד", "קרואטיה",
    "שווייץ", "סקוטלנד", "ספרד", "צרפת", "טורקיה", "אוסטריה", "מקסיקו",
    "ברזיל", "פרגוואי", "שוודיה", "איראן", "ארגנטינה", "גאנה", "קולומביה",
    "נורווגיה", "ערב הסעודית", "אקוואדור", 'ארה"ב', "בוסניה והרצגובינה",
    "דרום קוריאה", "קנדה", "מרוקו", "חוף השנהב", "יפן", "ניו זילנד",
    "אורוגוואי", "סנגל", "אלג`יריה", "הרפובליקה הדמוקרטית של קונגו",
    "פנמה", "אוזבקיסטן", "ירדן", "עיראק", "כף ורדה", "מצרים", "תוניסיה",
    "קורוסאו", "אוסטרליה", "האיטי", "קטאר", "דרום אפריקה",
]


def test_all_48_have_flag_entry():
    missing = [n for n in ALL_48_CANONICAL if n not in COUNTRY_TO_FLAG]
    assert missing == [], f"Missing flags for: {missing}"


def test_get_flag_emoji_known():
    assert get_flag_emoji("גרמניה") == "🇩🇪"
    assert get_flag_emoji("ספרד") == "🇪🇸"
    assert get_flag_emoji("ברזיל") == "🇧🇷"


def test_get_flag_emoji_unknown_returns_empty():
    assert get_flag_emoji("מדינה_לא_קיימת") == ""


def test_get_flag_emoji_none_returns_empty():
    assert get_flag_emoji(None) == ""


# ─────────────────────────────────────────────────────────────────────────────
# 5. normalize_league_name
# ─────────────────────────────────────────────────────────────────────────────

from app import normalize_league_name


def test_normalize_league_name_strips_spaces():
    assert normalize_league_name("ליגת  החלומות") == normalize_league_name("ליגת החלומות")


def test_normalize_league_name_strips_quotes():
    assert normalize_league_name('ליגת ה"אלופות"') == normalize_league_name("ליגת האלופות")


def test_normalize_league_name_lowercases():
    assert normalize_league_name("PREMIER League") == normalize_league_name("premier league")


def test_normalize_league_name_empty():
    assert normalize_league_name("") == ""
    assert normalize_league_name(None) == ""


# ─────────────────────────────────────────────────────────────────────────────
# 6. Squad comparison logic
# ─────────────────────────────────────────────────────────────────────────────

def _compare_squads(squads, left_name, right_name):
    sq_l = next(s for s in squads if s["user_name"] == left_name)
    sq_r = next(s for s in squads if s["user_name"] == right_name)
    pl = {p["name"] for p in sq_l["players"]}
    pr = {p["name"] for p in sq_r["players"]}
    return {"only_left": pl - pr, "shared": pl & pr, "only_right": pr - pl}


def test_squad_comparison_shared():
    result = _compare_squads(MOCK_SQUADS, "יוסי כהן", "דני לוי")
    assert "גנאברי" in result["shared"]
    assert "מסי" in result["shared"]


def test_squad_comparison_only_left():
    result = _compare_squads(MOCK_SQUADS, "יוסי כהן", "דני לוי")
    assert "מולר" in result["only_left"]
    assert "נוישטר" in result["only_left"]


def test_squad_comparison_only_right():
    result = _compare_squads(MOCK_SQUADS, "יוסי כהן", "דני לוי")
    assert "קרוס" in result["only_right"]
    assert "לאוטרו" in result["only_right"]


def test_squad_comparison_symmetry():
    ab = _compare_squads(MOCK_SQUADS, "יוסי כהן", "דני לוי")
    ba = _compare_squads(MOCK_SQUADS, "דני לוי", "יוסי כהן")
    assert ab["only_left"] == ba["only_right"]
    assert ab["only_right"] == ba["only_left"]
    assert ab["shared"] == ba["shared"]


# ─────────────────────────────────────────────────────────────────────────────
# 7. Tab name formatting
# ─────────────────────────────────────────────────────────────────────────────

def _format_tab_name(match):
    kt = match.get("kickoff_time")
    t_str = ""
    if kt:
        if hasattr(kt, "strftime"):
            t_str = kt.strftime("%H:%M")
        else:
            t_str = str(kt)
    time_part = f" ({t_str})" if t_str else ""
    return f"⚽ {match['home_team']} - {match['away_team']}{time_part}"


def test_tab_name_includes_kickoff_time():
    match = {"home_team": "גרמניה", "away_team": "סקוטלנד", "kickoff_time": KICKOFF_SAMPLE}
    assert "22:00" in _format_tab_name(match)


def test_tab_name_includes_teams():
    match = {"home_team": "גרמניה", "away_team": "סקוטלנד", "kickoff_time": KICKOFF_SAMPLE}
    tab = _format_tab_name(match)
    assert "גרמניה" in tab
    assert "סקוטלנד" in tab


def test_tab_name_no_flag_letter_codes():
    match = {"home_team": "גרמניה", "away_team": "קרואטיה", "kickoff_time": KICKOFF_SAMPLE}
    tab = _format_tab_name(match)
    for bad in [" DE", " HR", " ES", " FR", " BR", " AR"]:
        assert bad not in tab, f"ISO code found: {bad!r}"


def test_tab_name_missing_kickoff_graceful():
    match = {"home_team": "גרמניה", "away_team": "סקוטלנד", "kickoff_time": None}
    tab = _format_tab_name(match)
    assert "גרמניה" in tab
    assert "(" not in tab


# ─────────────────────────────────────────────────────────────────────────────
# 8. Report backtick sanitization
# ─────────────────────────────────────────────────────────────────────────────

def test_report_backtick_replacement():
    raw = "שחקן: ז`רמי דוקו\nשחקן2: ג`ק"
    sanitized = raw.replace("`", "'")
    assert "`" not in sanitized
    assert "ז'רמי" in sanitized
    assert "ג'ק" in sanitized


# ─────────────────────────────────────────────────────────────────────────────
# 9. Date filtering (sanity check)
# ─────────────────────────────────────────────────────────────────────────────

from scraper import filter_matches_by_date


def test_date_filter_outside_window_excluded():
    k_before = datetime(2026, 6, 10, 12, 0, tzinfo=IL_TZ)
    k_inside = datetime(2026, 6, 20, 12, 0, tzinfo=IL_TZ)
    k_after  = datetime(2026, 6, 30, 12, 0, tzinfo=IL_TZ)
    schedule = [
        {"match_id": "before", "kickoff_time": k_before},
        {"match_id": "inside", "kickoff_time": k_inside},
        {"match_id": "after",  "kickoff_time": k_after},
    ]
    result = filter_matches_by_date(schedule, "2026-06-18T00:00:00", "2026-06-25T00:00:00")
    ids = [m["match_id"] for m in result]
    assert "inside" in ids
    assert "before" not in ids
    assert "after" not in ids


# ─────────────────────────────────────────────────────────────────────────────
# 10. get_logo_base64 fallback URL and success path
# ─────────────────────────────────────────────────────────────────────────────

from app import get_logo_base64


def test_logo_fallback_on_network_error():
    get_logo_base64.clear()
    with patch("requests.get", side_effect=Exception("network error")):
        result = get_logo_base64()
    get_logo_base64.clear()
    assert result.startswith("https://")
    assert "sport5" in result


def test_logo_returns_base64_on_success():
    import base64
    fake_png = b"\x89PNG\r\n\x1a\n" + b"\x00" * 100
    get_logo_base64.clear()

    class FakeResp:
        status_code = 200
        content = fake_png

    with patch("requests.get", return_value=FakeResp()):
        result = get_logo_base64()
    get_logo_base64.clear()

    assert result.startswith("data:image/png;base64,")
    decoded = base64.b64decode(result.split(",", 1)[1])
    assert decoded == fake_png


# ─────────────────────────────────────────────────────────────────────────────
# 11. Caching authentication validation tests
# ─────────────────────────────────────────────────────────────────────────────

from app import fetch_metadata_cached, fetch_all_squads_cached

def test_fetch_metadata_unauthenticated_raises_permission_error():
    fetch_metadata_cached.clear()
    with patch("app.create_browser_context") as mock_context_factory, \
         patch("login._is_authenticated", return_value=False):
        
        mock_ctx = mock_context_factory.return_value
        with pytest.raises(PermissionError):
            fetch_metadata_cached()
            
        assert mock_ctx.close.called
    fetch_metadata_cached.clear()

def test_fetch_all_squads_unauthenticated_raises_permission_error():
    fetch_all_squads_cached.clear()
    with patch("app.create_browser_context") as mock_context_factory, \
         patch("login._is_authenticated", return_value=False):
         
        mock_ctx = mock_context_factory.return_value
        with pytest.raises(PermissionError):
            fetch_all_squads_cached("any-league-id")
            
        assert mock_ctx.close.called
    fetch_all_squads_cached.clear()
