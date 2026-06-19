import pytest
from datetime import datetime
from zoneinfo import ZoneInfo
from scraper import (
    normalize_country_name,
    sanitize_player_name,
    filter_matches_by_date
)

IL_TZ = ZoneInfo("Asia/Jerusalem")

# The exact 48 canonical Hebrew names from Sport5's database
SPORT5_CANONICAL_NATIONS = {
    "גרמניה", "אנגליה", "פורטוגל", "צ`כיה", "בלגיה", "הולנד", "קרואטיה", "שווייץ",
    "סקוטלנד", "ספרד", "צרפת", "טורקיה", "אוסטריה", "מקסיקו", "ברזיל", "פרגוואי",
    "שוודיה", "איראן", "ארגנטינה", "גאנה", "קולומביה", "נורווגיה", "ערב הסעודית",
    "אקוואדור", "ארה\"ב", "בוסניה והרצגובינה", "דרום קוריאה", "קנדה", "מרוקו",
    "חוף השנהב", "יפן", "ניו זילנד", "אורוגוואי", "סנגל", "אלג`יריה",
    "הרפובליקה הדמוקרטית של קונגו", "פנמה", "אוזבקיסטן", "ירדן", "עיראק",
    "כף ורדה", "מצרים", "תוניסיה", "קורוסאו", "אוסטרליה", "האיטי", "קטאר", "דרום אפריקה"
}

def test_country_name_normalization():
    # Ecuador checks
    assert normalize_country_name("אקוודור") == "אקוואדור"
    assert normalize_country_name("אקוואדור") == "אקוואדור"
    
    # Cape Verde checks
    assert normalize_country_name("כף ורדה") == "כף ורדה"
    assert normalize_country_name("קייפ ורדה") == "כף ורדה"
    assert normalize_country_name("Cape Verde") == "כף ורדה"
    assert normalize_country_name(" קייפ ורדה  ") == "כף ורדה"
    
    # USA checks
    assert normalize_country_name("ארצות הברית") == "ארה\"ב"
    assert normalize_country_name("ארה\"ב") == "ארה\"ב"
    assert normalize_country_name("USA") == "ארה\"ב"
    assert normalize_country_name("United States") == "ארה\"ב"
    
    # South Korea checks
    assert normalize_country_name("קוריאה הדרומית") == "דרום קוריאה"
    assert normalize_country_name("דרום קוריאה") == "דרום קוריאה"
    assert normalize_country_name("South Korea") == "דרום קוריאה"

def test_all_48_participating_nations_resolve():
    # Test inputs mapping various formats for all 48 tournament countries
    inputs_to_test = [
        # 1. Germany
        "Germany", "גרמניה",
        # 2. England
        "England", "אנגליה",
        # 3. Portugal
        "Portugal", "פורטוגל",
        # 4. Czech Republic
        "Czech Republic", "צ'כיה", "צ`כיה",
        # 5. Belgium
        "Belgium", "בלגיה",
        # 6. Netherlands
        "Netherlands", "הולנד",
        # 7. Croatia
        "Croatia", "קרואטיה",
        # 8. Switzerland
        "Switzerland", "שווייץ", "שוויץ",
        # 9. Scotland
        "Scotland", "סקוטלנד",
        # 10. Spain
        "Spain", "ספרד",
        # 11. France
        "France", "צרפת",
        # 12. Turkey
        "Turkey", "טורקיה",
        # 13. Austria
        "Austria", "אוסטריה",
        # 14. Mexico
        "Mexico", "מקסיקו",
        # 15. Brazil
        "Brazil", "ברזיל",
        # 16. Paraguay
        "Paraguay", "פרגוואי",
        # 17. Sweden
        "Sweden", "שוודיה",
        # 18. Iran
        "Iran", "איראן", "אירן",
        # 19. Argentina
        "Argentina", "ארגנטינה",
        # 20. Ghana
        "Ghana", "גאנה",
        # 21. Colombia
        "Colombia", "קולומביה",
        # 22. Norway
        "Norway", "נורווגיה",
        # 23. Saudi Arabia
        "Saudi Arabia", "ערב הסעודית",
        # 24. Ecuador
        "Ecuador", "אקוודור", "אקוואדור",
        # 25. USA
        "USA", "United States", "ארצות הברית", "ארה\"ב", "ארהב",
        # 26. Bosnia
        "Bosnia & Herzegovina", "בוסניה", "בוסניה והרצגובינה",
        # 27. South Korea
        "South Korea", "קוריאה הדרומית", "דרום קוריאה",
        # 28. Canada
        "Canada", "קנדה",
        # 29. Morocco
        "Morocco", "מרוקו",
        # 30. Ivory Coast
        "Ivory Coast", "חוף השנהב",
        # 31. Japan
        "Japan", "יפן",
        # 32. New Zealand
        "New Zealand", "ניו זילנד",
        # 33. Uruguay
        "Uruguay", "אורוגוואי",
        # 34. Senegal
        "Senegal", "סנגל",
        # 35. Algeria
        "Algeria", "אלג'יריה", "אלג`יריה",
        # 36. Congo DR
        "Congo DR", "קונגו", "הרפובליקה הדמוקרטית של קונגו",
        # 37. Panama
        "Panama", "פנמה",
        # 38. Uzbekistan
        "Uzbekistan", "אוזבקיסטן",
        # 39. Jordan
        "Jordan", "ירדן",
        # 40. Iraq
        "Iraq", "עיראק",
        # 41. Cape Verde
        "Cape Verde", "קייפ ורדה", "כף ורדה",
        # 42. Egypt
        "Egypt", "מצרים",
        # 43. Tunisia
        "Tunisia", "תוניסיה",
        # 44. Curacao
        "Curacao", "קורוסאו", "קיראסאו",
        # 45. Australia
        "Australia", "אוסטרליה",
        # 46. Haiti
        "Haiti", "האיטי", "הייטי",
        # 47. Qatar
        "Qatar", "קטאר",
        # 48. South Africa
        "South Africa", "דרום אפריקה"
    ]
    
    for nation_input in inputs_to_test:
        resolved = normalize_country_name(nation_input)
        assert resolved in SPORT5_CANONICAL_NATIONS, f"Failed to map '{nation_input}' -> got '{resolved}'"

def test_player_name_sanitization():
    assert sanitize_player_name("ז`רמי דוקו") == "ז'רמי דוקו"
    assert sanitize_player_name("ג`ק גריליש") == "ג'ק גריליש"
    assert sanitize_player_name("ליאו מסי") == "ליאו מסי"
    assert sanitize_player_name("") == ""
    assert sanitize_player_name(None) == ""

def test_matchday_date_boundaries_filter():
    start_str = "2026-06-18T19:00:00"
    end_str = "2026-06-24T05:00:00"
    
    k1 = datetime(2026, 6, 18, 18, 59, tzinfo=IL_TZ)
    k2 = datetime(2026, 6, 18, 19, 0, tzinfo=IL_TZ)
    k3 = datetime(2026, 6, 20, 12, 0, tzinfo=IL_TZ)
    k4 = datetime(2026, 6, 24, 5, 0, tzinfo=IL_TZ)
    k5 = datetime(2026, 6, 24, 5, 1, tzinfo=IL_TZ)
    
    mock_schedule = [
        {"match_id": "m1", "home_team": "Team A", "away_team": "Team B", "kickoff_time": k1},
        {"match_id": "m2", "home_team": "Team C", "away_team": "Team D", "kickoff_time": k2},
        {"match_id": "m3", "home_team": "Team E", "away_team": "Team F", "kickoff_time": k3},
        {"match_id": "m4", "home_team": "Team G", "away_team": "Team H", "kickoff_time": k4},
        {"match_id": "m5", "home_team": "Team I", "away_team": "Team J", "kickoff_time": k5},
    ]
    
    filtered = filter_matches_by_date(mock_schedule, start_str, end_str)
    
    kept_ids = [m["match_id"] for m in filtered]
    assert "m2" in kept_ids
    assert "m3" in kept_ids
    assert "m4" in kept_ids
    assert "m1" not in kept_ids
    assert "m5" not in kept_ids
    assert len(filtered) == 3
