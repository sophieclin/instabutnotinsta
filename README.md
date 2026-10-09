# instabutnotinsta

Check the Instagram accounts you follow for upcoming events, without opening Instagram.

It reads the recent posts of **public** accounts, finds captions that mention an event with a
date, and prints a digest. It also writes `events.ics`, which you can import into any calendar.

## Setup

```
pip install -r requirements.txt
```

Put usernames in `accounts.txt`, one per line.

## Use

```
python checker.py              # new events from the last 14 days of posts
python checker.py --days 30    # read further back
python checker.py --all        # include events you've already seen
python checker.py --llm        # have Claude read captions (set ANTHROPIC_API_KEY)
```

Events you've already been shown are remembered in `.seen.json`; later runs mark only new ones.

## Notes

- Default detection is keyword and date matching: free, but it can miss unusual phrasing
  (and ignores text inside images). `--llm` is more accurate and costs a few cents.
- Instagram rate-limits anonymous access and it is against their terms of service. The script
  waits between accounts; keep the list short and run it once a day, not in a loop. If you see
  "Instagram refused the request", wait a while and try again.
- Private accounts are skipped.

## Tests

```
python -m pytest tests
```
