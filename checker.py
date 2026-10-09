#!/usr/bin/env python3
"""Check public Instagram accounts for upcoming events, without opening Instagram.

    python checker.py                 # digest of upcoming events from accounts.txt
    python checker.py --days 30       # look further back through each feed
    python checker.py --llm           # use Claude to read captions (needs ANTHROPIC_API_KEY)
    python checker.py --all           # also show events you've already seen
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

from events import Event, extract_events, extract_events_llm

HERE = Path(__file__).parent
ACCOUNTS_FILE = HERE / "accounts.txt"
STATE_FILE = HERE / ".seen.json"
ICS_FILE = HERE / "events.ics"


def load_accounts(path: Path) -> list[str]:
    names = []
    for line in path.read_text().splitlines():
        line = line.split("#", 1)[0].strip().lstrip("@")
        if line:
            names.append(line)
    return names


def load_seen() -> set[str]:
    try:
        return set(json.loads(STATE_FILE.read_text()))
    except (OSError, json.JSONDecodeError):
        return set()


def fetch_posts(username: str, since: datetime, loader):
    """Yield (caption, url, posted_at) for recent posts, newest first."""
    import instaloader

    profile = instaloader.Profile.from_username(loader.context, username)
    for post in profile.get_posts():
        posted = post.date_local.replace(tzinfo=None)
        # Pinned posts can be old and out of order, so skip rather than stop.
        if posted < since:
            if post.is_pinned:
                continue
            break
        yield post.caption or "", f"https://www.instagram.com/p/{post.shortcode}/", posted


def collect(accounts: list[str], days: int, use_llm: bool, model: str) -> list[Event]:
    import instaloader

    loader = instaloader.Instaloader(
        download_pictures=False, download_videos=False, download_video_thumbnails=False,
        download_geotags=False, download_comments=False, save_metadata=False,
        compress_json=False, quiet=True,
    )
    client = None
    if use_llm:
        import anthropic
        client = anthropic.Anthropic()

    since = datetime.now() - timedelta(days=days)
    found: list[Event] = []
    for i, name in enumerate(accounts):
        if i:
            time.sleep(3)  # be gentle; Instagram throttles quick repeated requests
        try:
            for caption, url, posted in fetch_posts(name, since, loader):
                if client:
                    found += extract_events_llm(caption, name, url, posted, client, model)
                else:
                    found += extract_events(caption, name, url, posted)
        except instaloader.exceptions.ProfileNotExistsException:
            print(f"! @{name}: account not found", file=sys.stderr)
        except instaloader.exceptions.PrivateProfileNotFollowedException:
            print(f"! @{name}: account is private, skipping", file=sys.stderr)
        except instaloader.exceptions.ConnectionException as e:
            print(f"! @{name}: Instagram refused the request ({e}). Try again later.", file=sys.stderr)
    return found


def write_ics(events: list[Event], path: Path) -> None:
    def esc(s: str) -> str:
        return s.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\n", "\\n")

    lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//instabutnotinsta//EN"]
    for n, e in enumerate(events):
        lines += ["BEGIN:VEVENT", f"UID:{abs(hash(e.key()))}-{n}@instabutnotinsta",
                  f"DTSTAMP:{datetime.utcnow():%Y%m%dT%H%M%SZ}"]
        if e.all_day:
            lines += [f"DTSTART;VALUE=DATE:{e.start:%Y%m%d}",
                      f"DTEND;VALUE=DATE:{e.start + timedelta(days=1):%Y%m%d}"]
        else:
            lines += [f"DTSTART:{e.start:%Y%m%dT%H%M%S}",
                      f"DTEND:{e.start + timedelta(hours=1):%Y%m%dT%H%M%S}"]
        lines.append(f"SUMMARY:{esc(f'{e.title} (@{e.account})')}")
        if e.location:
            lines.append(f"LOCATION:{esc(e.location)}")
        lines += [f"URL:{e.post_url}", "END:VEVENT"]
    lines.append("END:VCALENDAR")
    path.write_text("\r\n".join(lines) + "\r\n")


def print_digest(events: list[Event], seen: set[str]) -> None:
    if not events:
        print("No upcoming events found.")
        return
    day = None
    for e in events:
        if e.start.date() != day:
            day = e.start.date()
            print(f"\n{day:%A, %B %-d}")
        when = "all day" if e.all_day else f"{e.start:%-I:%M %p}"
        new = "" if e.key() in seen else "  [new]"
        print(f"  {when:>8}  @{e.account}: {e.title}{new}")
        if e.location:
            print(f"            at {e.location}")
        print(f"            {e.post_url}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--accounts", type=Path, default=ACCOUNTS_FILE)
    ap.add_argument("--days", type=int, default=14, help="how far back to read each feed (default 14)")
    ap.add_argument("--llm", action="store_true", help="use Claude to extract events")
    ap.add_argument("--model", default="claude-haiku-5-5")
    ap.add_argument("--all", action="store_true", help="include events already shown before")
    args = ap.parse_args()

    if not args.accounts.exists():
        print(f"Create {args.accounts.name} with one username per line.", file=sys.stderr)
        return 1
    accounts = load_accounts(args.accounts)
    if not accounts:
        print(f"{args.accounts.name} has no usernames yet.", file=sys.stderr)
        return 1

    today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    events = collect(accounts, args.days, args.llm, args.model)
    unique = {e.key(): e for e in events if e.start >= today}
    upcoming = sorted(unique.values(), key=lambda e: e.start)

    seen = load_seen()
    shown = upcoming if args.all else [e for e in upcoming if e.key() not in seen]
    print_digest(shown, seen)

    write_ics(upcoming, ICS_FILE)
    print(f"\n{len(upcoming)} upcoming event(s) saved to {ICS_FILE.name}")
    STATE_FILE.write_text(json.dumps(sorted(seen | {e.key() for e in upcoming})))
    return 0


if __name__ == "__main__":
    sys.exit(main())
