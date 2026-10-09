"""Pull event details (date, time, place) out of Instagram captions."""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta

MONTHS = {
    "jan": 1, "january": 1, "feb": 2, "february": 2, "mar": 3, "march": 3,
    "apr": 4, "april": 4, "may": 5, "jun": 6, "june": 6, "jul": 7, "july": 7,
    "aug": 8, "august": 8, "sep": 9, "sept": 9, "september": 9, "oct": 10,
    "october": 10, "nov": 11, "november": 11, "dec": 12, "december": 12,
}
WEEKDAYS = {
    "mon": 0, "monday": 0, "tue": 1, "tues": 1, "tuesday": 1, "wed": 2,
    "wednesday": 2, "thu": 3, "thur": 3, "thurs": 3, "thursday": 3,
    "fri": 4, "friday": 4, "sat": 5, "saturday": 5, "sun": 6, "sunday": 6,
}

KEYWORDS = re.compile(
    r"\b(join us|come (out|through|by)|rsvp|tickets?|free (food|pizza|boba|merch)|"
    r"info session|workshop|meeting|open mic|party|show|concert|game|tryouts?|"
    r"social|fair|panel|speaker|hosting|doors|kickoff|mixer|fundraiser|"
    r"general body|gbm|performance|screening|tonight|tomorrow|this (mon|tues|wednes|thurs|fri|satur|sun)day)\b",
    re.I,
)

_MONTH_RE = "|".join(sorted(MONTHS, key=len, reverse=True))
_DAY_RE = "|".join(sorted(WEEKDAYS, key=len, reverse=True))
MONTH_DAY = re.compile(rf"\b({_MONTH_RE})\.?\s+(\d{{1,2}})(?:st|nd|rd|th)?\b", re.I)
DAY_MONTH = re.compile(rf"\b(\d{{1,2}})(?:st|nd|rd|th)?\s+(?:of\s+)?({_MONTH_RE})\b", re.I)
NUMERIC = re.compile(r"(?<![\d/])(\d{1,2})/(\d{1,2})(?:/(\d{2,4}))?(?![\d/])")
WEEKDAY = re.compile(rf"\b({_DAY_RE})\b\.?", re.I)
TIME = re.compile(
    r"\b(\d{1,2})(?::(\d{2}))?\s*(am|pm|a\.m\.|p\.m\.)(?:\s*[-–to]+\s*(\d{1,2})(?::(\d{2}))?\s*(am|pm|a\.m\.|p\.m\.)?)?",
    re.I,
)
PLACE = re.compile(
    r"(?:📍|@|\blocation\s*[:\-]|\bwhere\s*[:\-]|\bat the\b|\bin\b(?=\s+[A-Z0-9]))\s*([^\n.!|•📅🕕⏰]{3,60})",
)


@dataclass
class Event:
    account: str
    post_url: str
    title: str
    start: datetime  # naive local time; all-day events use midnight + all_day
    all_day: bool = True
    location: str = ""

    def key(self) -> str:
        return f"{self.post_url}|{self.start.isoformat()}"


def _to_24h(hour: int, minute: int, meridiem: str) -> time | None:
    m = meridiem.lower().replace(".", "")
    if not 1 <= hour <= 12 or minute > 59:
        return None
    if m == "pm" and hour != 12:
        hour += 12
    elif m == "am" and hour == 12:
        hour = 0
    return time(hour, minute)


def find_time(text: str) -> time | None:
    m = TIME.search(text)
    if not m:
        return None
    hour, minute = int(m.group(1)), int(m.group(2) or 0)
    meridiem = m.group(3)
    return _to_24h(hour, minute, meridiem)


def _month_day(month: int, day: int, posted: date) -> date | None:
    try:
        d = date(posted.year, month, day)
    except ValueError:
        return None
    if d < posted - timedelta(days=30):  # "Jan 5" posted in December
        d = d.replace(year=posted.year + 1)
    return d


def find_dates(text: str, posted: date) -> list[date]:
    """Dates mentioned in the caption, resolved against the post date."""
    found: list[date] = []
    for m in MONTH_DAY.finditer(text):
        d = _month_day(MONTHS[m.group(1).lower()], int(m.group(2)), posted)
        if d:
            found.append(d)
    for m in DAY_MONTH.finditer(text):
        d = _month_day(MONTHS[m.group(2).lower()], int(m.group(1)), posted)
        if d:
            found.append(d)
    for m in NUMERIC.finditer(text):
        month, day = int(m.group(1)), int(m.group(2))
        if 1 <= month <= 12 and 1 <= day <= 31:
            d = _month_day(month, day, posted)
            if d:
                found.append(d)
    lower = text.lower()
    if re.search(r"\b(tonight|today)\b", lower):
        found.append(posted)
    if re.search(r"\btomorrow\b", lower):
        found.append(posted + timedelta(days=1))
    # Weekday names only count if no explicit date was found (avoids "Fri Oct 17" dupes).
    if not found:
        for m in WEEKDAY.finditer(text):
            word = m.group(1)
            # "sat"/"sun"/"mon"/"wed" as lowercase words are usually not days
            if word.lower() in ("sat", "sun", "mon", "wed", "may") and not word[0].isupper():
                continue
            target = WEEKDAYS[word.lower()]
            ahead = (target - posted.weekday()) % 7
            found.append(posted + timedelta(days=ahead))
    return sorted(set(found))


def find_location(text: str) -> str:
    m = PLACE.search(text)
    if not m:
        return ""
    return re.sub(r"\s+", " ", m.group(1)).strip(" ,-")


def make_title(caption: str) -> str:
    for line in caption.splitlines():
        line = line.strip()
        if len(line) >= 4:
            return line[:90]
    return "(no caption)"


def extract_events(caption: str, account: str, post_url: str, posted: datetime) -> list[Event]:
    """Heuristic extraction. Needs an event-ish keyword AND a date."""
    if not caption or not KEYWORDS.search(caption):
        return []
    dates = find_dates(caption, posted.date())
    if not dates:
        return []
    t = find_time(caption)
    loc = find_location(caption)
    title = make_title(caption)
    return [
        Event(
            account=account,
            post_url=post_url,
            title=title,
            start=datetime.combine(d, t or time(0, 0)),
            all_day=t is None,
            location=loc,
        )
        for d in dates[:3]
    ]


LLM_PROMPT = """You read Instagram captions and extract upcoming events.
The post was published on {posted} (a {weekday}). Resolve relative dates ("this Friday", "tomorrow") from that.
Return ONLY a JSON array (possibly empty). Each item: {{"title": str, "date": "YYYY-MM-DD", "time": "HH:MM" or null, "location": str or ""}}.
Only include real events someone could attend, not past recaps or giveaways.

Caption:
{caption}"""


def extract_events_llm(caption: str, account: str, post_url: str, posted: datetime, client, model: str) -> list[Event]:
    """Same output as extract_events, but asks Claude. `client` is anthropic.Anthropic()."""
    if not caption.strip():
        return []
    resp = client.messages.create(
        model=model,
        max_tokens=600,
        messages=[{
            "role": "user",
            "content": LLM_PROMPT.format(
                posted=posted.date().isoformat(), weekday=posted.strftime("%A"), caption=caption[:3000]
            ),
        }],
    )
    raw = resp.content[0].text
    start, end = raw.find("["), raw.rfind("]")
    if start < 0 or end < 0:
        return []
    try:
        items = json.loads(raw[start:end + 1])
    except json.JSONDecodeError:
        return []
    out: list[Event] = []
    for it in items:
        try:
            d = date.fromisoformat(it["date"])
            t = datetime.strptime(it["time"], "%H:%M").time() if it.get("time") else None
        except (KeyError, ValueError, TypeError):
            continue
        out.append(Event(
            account=account, post_url=post_url, title=str(it.get("title", make_title(caption)))[:90],
            start=datetime.combine(d, t or time(0, 0)), all_day=t is None,
            location=str(it.get("location") or ""),
        ))
    return out
