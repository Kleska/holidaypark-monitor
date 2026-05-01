"""
Monitor dostepnosci domkow Holiday Park & Resort.
Robi jedno sprawdzenie i konczy. Cron w GitHub Actions wywoluje cyklicznie.
"""

import json
import os
import sys
from datetime import datetime
from pathlib import Path

import requests


# ============================================================
# TUTAJ DODAJESZ SWOJE ZAPYTANIA
# ============================================================
# Kazde zapytanie to jeden blok { ... }. Mozesz miec ich dowolnie wiele.
# Zwroc uwage na przecinki miedzy blokami!
#
# resort: numer osrodka (z URL-a w DevTools)
# date_from / date_to: format RRRR-MM-DD
# accommodation_type: typ domku (1, 2, 3, 4, 5)

WATCHLIST = [
    {
        "name": "Ustronie 04-10.05.2026 typ 1",
        "params": {
            "resort": 2,
            "date_from": "2026-05-04",
            "date_to": "2026-05-10",
            "accommodation_type": 1,
        },
    },
    {
        "name": "Ustronie 04-10.05.2026 typ 4",
        "params": {
            "resort": 2,
            "date_from": "2026-05-04",
            "date_to": "2026-05-10",
            "accommodation_type": 4,
        },
    },
    # Skopiuj blok wyzej, zmien wartosci, dodaj przecinek po } i jedziesz dalej:
    # {
    #     "name": "Inny osrodek czerwiec",
    #     "params": {
    #         "resort": 3,
    #         "date_from": "2026-06-01",
    #         "date_to": "2026-06-07",
    #         "accommodation_type": 1,
    #     },
    # },
]

# ============================================================

API_URL = "https://rezerwuj.holidaypark.pl/api/reservation/available-apartments/"
STATE_FILE = Path("state.json")

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "pl-PL,pl;q=0.9,en;q=0.8",
    "Referer": "https://rezerwuj.holidaypark.pl/",
}


def log(msg):
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {msg}", flush=True)


def fetch_available(params):
    r = requests.get(API_URL, params=params, headers=HEADERS, timeout=20)
    r.raise_for_status()
    return [a for a in r.json() if a.get("is_available")]


def load_state():
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def save_state(state):
    STATE_FILE.write_text(
        json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def telegram_send(text):
    if not (TELEGRAM_TOKEN and TELEGRAM_CHAT_ID):
        log("Telegram nieskonfigurowany - pomijam.")
        return
    try:
        r = requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
            json={
                "chat_id": TELEGRAM_CHAT_ID,
                "text": text,
                "parse_mode": "Markdown",
                "disable_web_page_preview": True,
            },
            timeout=10,
        )
        r.raise_for_status()
        log("Telegram: wyslano powiadomienie.")
    except Exception as e:
        log(f"Telegram error: {e}")


def check_one(query, state):
    name = query["name"]
    params = query["params"]

    try:
        avail = fetch_available(params)
    except Exception as e:
        log(f"Blad pobierania '{name}': {e}")
        return

    avail_map = {a["apartment_id"]: a["display_name"] for a in avail}
    avail_ids = sorted(avail_map.keys())
    prev_ids = state.get(name, [])

    new_ids = sorted(set(avail_ids) - set(prev_ids))

    if new_ids:
        lines = [f"• {avail_map[i]} ({i})" for i in new_ids]
        msg = (
            f"🔔 *Wolny domek!*\n\n"
            f"_{name}_\n\n"
            + "\n".join(lines)
            + f"\n\n[Otworz strone rezerwacji](https://rezerwuj.holidaypark.pl/)"
        )
        telegram_send(msg)
        log(f"[{name}] NOWE: {new_ids}")
    else:
        log(f"[{name}] dostepnych: {len(avail_ids)} (bez zmian)")

    state[name] = avail_ids


def main():
    log(f"Start - {len(WATCHLIST)} zapytan do sprawdzenia")
    state = load_state()
    for query in WATCHLIST:
        check_one(query, state)
    save_state(state)
    log("Koniec.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
