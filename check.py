"""
Monitor dostepnosci domkow Holiday Park & Resort.
Robi jedno sprawdzenie i konczy. Cron w GitHub Actions wywoluje cyklicznie.

Powiadomienia: Telegram + email (oba opcjonalne, dziala kazde z osobna).
"""

import json
import os
import smtplib
import ssl
import sys
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

import requests


# ============================================================
# ZAPYTANIA DO MONITOROWANIA
# ============================================================

WATCHLIST = [
    {
        "name": "Mielno - typ 1 (04-10.05.2026)",
        "params": {
            "resort": 8,
            "date_from": "2026-05-04",
            "date_to": "2026-05-10",
            "accommodation_type": 1,
        },
    },
    {
        "name": "Mielno - typ 4 (04-10.05.2026)",
        "params": {
            "resort": 8,
            "date_from": "2026-05-04",
            "date_to": "2026-05-10",
            "accommodation_type": 4,
        },
    },
    {
        "name": "Pobierowo - typ 1 (04-10.05.2026)",
        "params": {
            "resort": 1,
            "date_from": "2026-05-04",
            "date_to": "2026-05-10",
            "accommodation_type": 1,
        },
    },
    {
        "name": "Pobierowo - typ 4 (04-10.05.2026)",
        "params": {
            "resort": 1,
            "date_from": "2026-05-04",
            "date_to": "2026-05-10",
            "accommodation_type": 4,
        },
    },
]

# ============================================================

API_URL = "https://rezerwuj.holidaypark.pl/api/reservation/available-apartments/"
STATE_FILE = Path("state.json")
BOOKING_URL = "https://rezerwuj.holidaypark.pl/"

# Telegram (opcjonalny)
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")

# Email (opcjonalny). Domyslnie SMTP Gmaila.
EMAIL_FROM = os.environ.get("EMAIL_FROM", "")
EMAIL_PASSWORD = os.environ.get("EMAIL_PASSWORD", "")
EMAIL_TO = os.environ.get("EMAIL_TO", "")
SMTP_HOST = os.environ.get("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.environ.get("SMTP_PORT", "465"))

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
    target_type = params.get("accommodation_type")
    return [
        a for a in r.json()
        if a.get("is_available") and a.get("accommodation_type_id") == target_type
    ]


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


def telegram_send(text_md):
    if not (TELEGRAM_TOKEN and TELEGRAM_CHAT_ID):
        return
    try:
        r = requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
            json={
                "chat_id": TELEGRAM_CHAT_ID,
                "text": text_md,
                "parse_mode": "Markdown",
                "disable_web_page_preview": True,
            },
            timeout=10,
        )
        r.raise_for_status()
        log("Telegram: wyslano.")
    except Exception as e:
        log(f"Telegram error: {e}")


def email_send(subject, plain_text, html_text):
    if not (EMAIL_FROM and EMAIL_PASSWORD and EMAIL_TO):
        return
    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = EMAIL_FROM
        msg["To"] = EMAIL_TO
        msg.attach(MIMEText(plain_text, "plain", "utf-8"))
        msg.attach(MIMEText(html_text, "html", "utf-8"))

        ctx = ssl.create_default_context()
        with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, context=ctx, timeout=20) as s:
            s.login(EMAIL_FROM, EMAIL_PASSWORD)
            s.sendmail(EMAIL_FROM, [EMAIL_TO], msg.as_string())
        log("Email: wyslano.")
    except Exception as e:
        log(f"Email error: {e}")


def notify(query_name, items):
    """items: lista par (apartment_id, display_name)."""
    bullets_plain = "\n".join(f"- {dn} ({aid})" for aid, dn in items)
    bullets_html = "".join(f"<li>{dn} ({aid})</li>" for aid, dn in items)

    # Telegram (Markdown)
    md = (
        f"🔔 *Wolny domek!*\n\n"
        f"_{query_name}_\n\n"
        + "\n".join(f"• {dn} ({aid})" for aid, dn in items)
        + f"\n\n[Otworz strone rezerwacji]({BOOKING_URL})"
    )
    telegram_send(md)

    # Email
    subject = f"🔔 Wolny domek - {query_name}"
    plain = (
        f"Pojawil sie wolny domek!\n\n"
        f"Zapytanie: {query_name}\n\n"
        f"{bullets_plain}\n\n"
        f"Strona rezerwacji: {BOOKING_URL}\n"
    )
    html = f"""<!DOCTYPE html>
<html><body style="font-family: Arial, sans-serif; max-width: 600px;">
  <h2 style="color:#2a7;">🔔 Wolny domek!</h2>
  <p><strong>{query_name}</strong></p>
  <ul>{bullets_html}</ul>
  <p><a href="{BOOKING_URL}" style="display:inline-block;padding:10px 16px;
     background:#2a7;color:#fff;text-decoration:none;border-radius:6px;">
     Otworz strone rezerwacji</a></p>
  <p style="color:#888;font-size:12px;">Holiday Park Monitor</p>
</body></html>"""
    email_send(subject, plain, html)


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
        items = [(i, avail_map[i]) for i in new_ids]
        notify(name, items)
        log(f"[{name}] NOWE: {new_ids}")
    else:
        log(f"[{name}] dostepnych: {len(avail_ids)} (bez zmian)")

    state[name] = avail_ids


def main():
    log(f"Start - {len(WATCHLIST)} zapytan do sprawdzenia")
    log(f"Telegram: {'TAK' if TELEGRAM_TOKEN and TELEGRAM_CHAT_ID else 'NIE'}, "
        f"Email: {'TAK' if EMAIL_FROM and EMAIL_PASSWORD and EMAIL_TO else 'NIE'}")
    state = load_state()
    for query in WATCHLIST:
        check_one(query, state)
    save_state(state)
    log("Koniec.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
