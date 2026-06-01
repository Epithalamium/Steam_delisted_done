import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import requests
from bs4 import BeautifulSoup

URL = "https://steam-tracker.com/apps/delisted"

# Mirrors the default checked state of the client-side filters on the page:
# 3 = Purchase disabled
# 6 = F2P (unavailable)
# 1 = Delisted
# 13 = Unreleased
# 2 = Test app
# 4 = Retail only
# 14 = Pre-order exclusive
ALLOWED_ITEMTYPES = {"1", "2", "3", "4", "6", "13", "14"}

ROOT = Path(__file__).parent.parent
LIST_FILE = ROOT / "games_list.txt"
README_FILE = ROOT / "README.md"

def fetch_games() -> dict[str, str]:
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
    }
    last_exc: Exception | None = None
    for attempt in range(3):
        if attempt:
            time.sleep(15 * attempt)
        try:
            resp = requests.get(URL, headers=headers, timeout=60)
            resp.raise_for_status()
            return parse_html(resp.text)
        except Exception as exc:
            print(f"Attempt {attempt + 1} failed: {exc}", file=sys.stderr)
            last_exc = exc
    raise last_exc  # type: ignore[misc]

def parse_html(html: str) -> dict[str, str]:
    soup = BeautifulSoup(html, "html.parser")
    games: dict[str, str] = {}

    for row in soup.find_all("tr", attrs={"data-appid": True}):
        itemtype = row.get("data-itemtype", "")
        if itemtype not in ALLOWED_ITEMTYPES:
            continue

        appid = row["data-appid"]
        tds = row.find_all("td", recursive=False)
        if len(tds) < 2:
            continue
        link = tds[1].find("a")
        if link:
            games[appid] = link.get_text(strip=True)

    return games

def load_previous() -> dict[str, str]:
    if not LIST_FILE.exists():
        return {}
    games: dict[str, str] = {}
    for line in LIST_FILE.read_text(encoding="utf-8").splitlines():
        if "\t" in line:
            appid, name = line.split("\t", 1)
            games[appid.strip()] = name.strip()
    return games

def save_games(games: dict[str, str]) -> None:
    lines = [
        f"{appid}\t{name}"
        for appid, name in sorted(games.items(), key=lambda x: int(x[0]))
    ]
    LIST_FILE.write_text("\n".join(lines) + "\n", encoding="utf-8")

def update_readme(current: dict[str, str], new_appids: set[str]) -> None:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    if new_appids:
        new_lines = [
            f"- [{current[a]}](https://store.steampowered.com/app/{a}/) (AppID: {a})"
            for a in sorted(new_appids, key=int)
        ]
        new_section = "## Newly Added Since Last Check\n\n" + "\n".join(new_lines)
    else:
        new_section = "## Newly Added Since Last Check\n\n_(No new entries this run)_"

    all_lines = [
        f"- [{name}](https://store.steampowered.com/app/{appid}/) (AppID: {appid})"
        for appid, name in sorted(current.items(), key=lambda x: int(x[0]))
    ]

    readme = f"""\
# Steam Delisted Games Tracker

Automatically tracks apps listed on [steam-tracker.com/apps/delisted](https://steam-tracker.com/apps/delisted).

Updated every 2 days via GitHub Actions. Last updated: **{now}**

**Filters applied:** All default item types

**Total tracked:** {len(current)} apps

---

{new_section}

---

## Full List

{chr(10).join(all_lines)}
"""
    README_FILE.write_text(readme, encoding="utf-8")

def main() -> None:
    previous = load_previous()
    try:
        current = fetch_games()
    except Exception as exc:
        print(f"ERROR fetching page after 3 attempts: {exc}", file=sys.stderr)
        print("Keeping existing data unchanged.", file=sys.stderr)
        sys.exit(0)

    if not current:
        print("ERROR: parsed 0 games — the page structure may have changed", file=sys.stderr)
        sys.exit(1)

    new_appids = set(current) - set(previous)

    save_games(current)
    update_readme(current, new_appids)

    print(f"Total: {len(current)}  |  New this run: {len(new_appids)}")
    for appid in sorted(new_appids, key=int):
        print(f"  + {current[appid]} (AppID {appid})")

if __name__ == "__main__":
    main()