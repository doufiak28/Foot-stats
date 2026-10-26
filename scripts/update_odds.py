#!/usr/bin/env python3
"""Generate a small public, key-free pre-match odds snapshot for GitHub Pages.
Provider: https://the-odds-api.com/ (The Odds API v4).
The API key is read ONLY from GitHub Actions Secrets; do not check it into Git.
"""
import json
import math
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

LEAGUES = {
    "Ligue 1": "soccer_france_ligue_one",
    "Ligue 2": "soccer_france_ligue_two",
    "Serie A": "soccer_italy_serie_a",
    "Serie B": "soccer_italy_serie_b",
    "Bundesliga": "soccer_germany_bundesliga",
    "Bundesliga 2": "soccer_germany_bundesliga2",
    "La Liga": "soccer_spain_la_liga",
    "La Liga 2": "soccer_spain_segunda_division",
    "Premier League": "soccer_epl",
    "Championship": "soccer_efl_champ",
    "MLS": "soccer_usa_mls",
}
# French licensed operators preferred; one three-way market from one bookmaker.
BOOK_ORDER = ["betclic_fr", "winamax_fr", "unibet_fr", "pmu_fr", "netbet_fr"]
OUT = Path(__file__).resolve().parent.parent / "data" / "live_odds.json"
API_KEY = os.environ.get("ODDS_API_KEY", "").strip()


def valid_price(value):
    return isinstance(value, (float, int)) and not isinstance(value, bool) and math.isfinite(value) and 1.01 <= value <= 100


def extract_book(event):
    home, away = event.get("home_team"), event.get("away_team")
    if not (isinstance(home, str) and isinstance(away, str) and home != away):
        return None
    for book in sorted(event.get("bookmakers", []), key=lambda x: (BOOK_ORDER.index(x.get("key")) if x.get("key") in BOOK_ORDER else len(BOOK_ORDER))):
        for market in book.get("markets", []):
            if market.get("key") != "h2h":
                continue
            outs = market.get("outcomes", [])
            homeprice = next((p.get("price") for p in outs if p.get("name") == home), None)
            awayprice = next((p.get("price") for p in outs if p.get("name") == away), None)
            drawprice = next((p.get("price") for p in outs if str(p.get("name", "")).casefold() in ("draw", "tie", "x")), None)
            if not all(valid_price(v) for v in (homeprice, drawprice, awayprice)):
                continue
            margin = 1 / homeprice + 1 / drawprice + 1 / awayprice - 1
            if not -0.03 <= margin <= 0.20:
                continue
            return {
                "event_id": str(event.get("id", "")),
                "commence_time": event.get("commence_time"),
                "home": home,
                "away": away,
                "bookmaker": book.get("title", book.get("key", "Bookmaker")),
                "bookmaker_key": book.get("key", ""),
                "updated_at": market.get("last_update") or book.get("last_update") or None,
                "odds": {"p1": homeprice, "px": drawprice, "p2": awayprice},
            }
    return None


def fetch_league(sport, api_key):
    params = urlencode({"apiKey": api_key, "regions": "fr", "markets": "h2h", "oddsFormat": "decimal", "dateFormat": "iso"})
    url = f"https://api.the-odds-api.com/v4/sports/{sport}/odds/?{params}"
    response = urlopen(Request(url, headers={"Accept": "application/json", "User-Agent": "Foot-stats/1.0"}), timeout=25)
    with response as res:
        data = json.load(res)
        remaining = res.headers.get("x-requests-remaining")
    if not isinstance(data, list):
        raise ValueError("Provider payload is not a list")
    return data, int(remaining) if remaining and remaining.isdecimal() else None


def main():
    if not API_KEY:
        print("ERROR: Missing GitHub Secret ODDS_API_KEY (never paste the key in index.html).", file=sys.stderr)
        return 2
    now = datetime.now(timezone.utc)
    all_matches = []
    problems = []
    remaining = None
    for league, sport in LEAGUES.items():
        if remaining is not None and remaining < 15:
            problems.append("Quota trop faible : arrêt prudent avant épuisement.")
            break
        try:
            results, remaining = fetch_league(sport, API_KEY)
            for item in results:
                row = extract_book(item)
                if row:
                    row["league"] = league
                    all_matches.append(row)
            print(f"{league}: {len(results)} fixtures; valid odds: {sum(x['league'] == league for x in all_matches)}; remaining credits: {remaining}")
        except HTTPError as e:
            body = e.read(400).decode("utf-8", errors="replace")
            print(f"Provider error ({league}): {e.code} - {body[:100]}", file=sys.stderr)
            problems.append(f"{league}: HTTP {e.code}")
            if e.code in (401, 403, 429):
                break
        except (URLError, TimeoutError, ValueError, OSError, json.JSONDecodeError) as e:
            problems.append(f"{league}: {type(e).__name__}")
            print(f"Fetch failed ({league}): {e}", file=sys.stderr)
        time.sleep(0.15)
    if problems and not all_matches:
        print("No usable snapshot; keeping prior file untouched.", file=sys.stderr)
        return 1
    payload = {
        "provider": "The Odds API", "market": "1X2 (h2h)", "region": "fr",
        "generated_at": now.isoformat(timespec="seconds").replace("+00:00", "Z"),
        "matches": all_matches,
        "warnings": problems,
    }
    OUT.parent.mkdir(exist_ok=True, parents=True)
    tmp = OUT.with_suffix(".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(OUT)
    print(f"Saved {len(all_matches)} matches into {OUT}; warnings={len(problems)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
