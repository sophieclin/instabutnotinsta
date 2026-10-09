import sys
from datetime import date, datetime, time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from events import extract_events, find_dates, find_location, find_time  # noqa: E402

POSTED = datetime(2026, 10, 9, 12, 0)  # a Friday


def test_month_day():
    assert find_dates("Join us Oct 15th!", POSTED.date()) == [date(2026, 10, 15)]
    assert find_dates("see you 20 November", POSTED.date()) == [date(2026, 11, 20)]


def test_numeric_date():
    assert find_dates("GBM 10/21 in the union", POSTED.date()) == [date(2026, 10, 21)]


def test_relative():
    assert find_dates("Tomorrow at 7", POSTED.date()) == [date(2026, 10, 10)]
    assert find_dates("Tonight!", POSTED.date()) == [POSTED.date()]


def test_weekday_resolves_forward():
    assert find_dates("Come out this Thursday", POSTED.date()) == [date(2026, 10, 15)]


def test_year_rollover():
    assert find_dates("Jan 5 kickoff", datetime(2026, 12, 20).date()) == [date(2027, 1, 5)]


def test_time():
    assert find_time("doors at 7:30 pm") == time(19, 30)
    assert find_time("no time here") is None


def test_location():
    assert find_location("📍 Sarratt Cinema\nbring a friend") == "Sarratt Cinema"


def test_event_needs_keyword_and_date():
    assert extract_events("Cute pic of my dog Oct 15", "a", "u", POSTED) == []
    assert extract_events("Join us for a party!", "a", "u", POSTED) == []
    evs = extract_events("Join us for a party Oct 15 at 7pm 📍 Rand Hall", "a", "u", POSTED)
    assert len(evs) == 1
    assert evs[0].start == datetime(2026, 10, 15, 19, 0)
    assert not evs[0].all_day
    assert evs[0].location == "Rand Hall"
