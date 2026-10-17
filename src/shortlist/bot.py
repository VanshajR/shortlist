"""The Telegram bot: a webhook that Telegram calls with each message and button tap.

    python -m shortlist.bot link     # a one-time code; send "/start <code>" to the bot
    python -m shortlist.bot webhook  # point Telegram at the deployed app

Runs as a serverless function (index.py at the repo root), so every request
opens its own database connection.
"""
import argparse
import json
import os
import secrets

import psycopg
from fastapi import FastAPI, Header, HTTPException
from psycopg.types.json import Jsonb

from . import db, embeddings, env
from .digest import MATCH, buttons, card, skip_buttons
from .rank import prefs_for
from .telegram import Telegram, esc

app = FastAPI(title="shortlist bot")

HELP = """<b>shortlist</b> finds jobs worth applying to.

/today: your current matches
/search <i>words</i>: look for jobs, e.g. /search backend python pune
/prefs: what it filters on, and how to change it
/help: this message

The morning digest has buttons on each job: tap <i>I applied</i>, <i>Later</i> or <i>Skip</i>. A skip asks why, which keeps future matches closer to what you want."""

STRANGER = ("This is a personal bot. If you run shortlist yourself, link your chat with the code from "
            "<code>python -m shortlist.bot link</code>.")


@app.get("/health")
def health():
    return {"ok": True}


@app.post("/telegram")
def webhook(update: dict, x_telegram_bot_api_secret_token: str = Header(default="")):
    expected = os.environ.get("TELEGRAM_WEBHOOK_SECRET", "")
    if not expected or not secrets.compare_digest(x_telegram_bot_api_secret_token, expected):
        raise HTTPException(403)
    with db.connect() as conn:
        handle(conn, Telegram(), update)
    return {"ok": True}


def handle(conn: psycopg.Connection, tg: Telegram, update: dict) -> None:
    if "callback_query" in update:
        return on_button(conn, tg, update["callback_query"])
    message = update.get("message") or {}
    text = (message.get("text") or "").strip()
    chat = message.get("chat", {}).get("id")
    if not text or not chat:
        return
    command, _, rest = text.partition(" ")
    command = command.split("@")[0].lower()  # "/today@dailyaxiom_bot" in groups
    user = conn.execute("select * from users where telegram_id = %s", (message["from"]["id"],)).fetchone()

    if command == "/start" and rest.strip():
        return link(conn, tg, chat, message["from"]["id"], rest.strip())
    if not user:
        return tg.send(chat, STRANGER)
    if command in ("/start", "/help"):
        tg.send(chat, HELP)
    elif command == "/today":
        today(conn, tg, user)
    elif command == "/search":
        search(conn, tg, user, rest.strip())
    elif command == "/prefs":
        prefs(conn, tg, user, rest.strip())
    else:
        tg.send(chat, "I don't know that one. /help lists what I can do.")


def link(conn, tg, chat: int, telegram_id: int, code: str) -> None:
    user = conn.execute("update users set telegram_id = %s, link_code = null where link_code = %s returning name",
                        (telegram_id, code)).fetchone()
    if not user:
        return tg.send(chat, "That code didn't work. Codes work once; make a new one with "
                             "<code>python -m shortlist.bot link</code>.")
    tg.send(chat, f"Linked, {esc(user['name'].split()[0])}. Your digest arrives here each morning.\n\n" + HELP)


def today(conn, tg, user) -> None:
    rows = conn.execute(
        MATCH + """ where m.user_id = %s and m.status in ('new', 'sent', 'later') and m.verdict in ('apply', 'maybe')
                    order by m.status = 'later', m.fit desc, m.semantic desc limit 5""", (user["id"],)).fetchall()
    if not rows:
        return tg.send(user["telegram_id"], "Nothing waiting right now. New jobs are checked every six hours.")
    for m in rows:
        tg.send(user["telegram_id"], card(m), buttons(m["handle"]))


def search(conn, tg, user, query: str) -> None:
    if not query:
        return tg.send(user["telegram_id"], "Add some words: /search backend python pune")
    try:
        [vector] = embeddings.embed([query], task=embeddings.QUERY, patient=False)
    except embeddings.QuotaExhausted:
        # Telegram gives up on a webhook after about a minute, so no waiting it out here
        return tg.send(user["telegram_id"], "Search is out of free quota for today. Try again tomorrow, "
                                             "or use /today for your current matches.")
    rows = conn.execute(
        """select j.title, j.company, j.cities, j.remote_scope, j.url, m.fit
           from job_embeddings e join jobs j on j.id = e.job_id
           left join matches m on m.job_id = j.id and m.user_id = %s
           where j.last_seen > now() - interval '3 days'
           order by e.embedding <=> %s::vector limit 5""", (user["id"], vector)).fetchall()
    if not rows:
        return tg.send(user["telegram_id"], "Nothing matched.")
    lines = [f"Closest to <i>{esc(query)}</i>:"]
    for r in rows:
        where = ", ".join(r["cities"][:2]) or (r["remote_scope"] or "")
        fit = f" · fit {r['fit']}/10" if r["fit"] is not None else ""
        lines.append(f'\n<a href="{esc(r["url"])}">{esc(r["title"])}</a>\n{esc(r["company"].title())} · {esc(where)}{fit}')
    tg.send(user["telegram_id"], "\n".join(lines))


PREF_HELP = """Change one with:
/prefs years 1
/prefs cities Pune, Bengaluru, Gurugram
/prefs remote on (or off)
/prefs avoid SRE and DevOps roles, data engineering
/prefs block <company> (or unblock)"""


def prefs(conn, tg, user, args: str) -> None:
    current = prefs_for(user)
    key, _, value = args.partition(" ")
    key, value = key.lower(), value.strip()
    change = {}
    if key == "years" and value.isdigit():
        change["max_years"] = int(value)
    elif key == "cities" and value:
        change["cities"] = [c.strip() for c in value.split(",") if c.strip()]
    elif key == "remote" and value.lower() in ("on", "off"):
        change["remote"] = value.lower() == "on"
    elif key == "avoid" and value:
        change["avoid"] = value
    elif key in ("block", "unblock") and value:
        blocked = set(current.get("blocked", []))
        (blocked.add if key == "block" else blocked.discard)(value.lower())
        change["blocked"] = sorted(blocked)
    elif args:
        return tg.send(user["telegram_id"], "I didn't follow that.\n\n" + PREF_HELP)

    if change:
        conn.execute("update users set prefs = prefs || %s where id = %s", (Jsonb(change), user["id"]))
        current = {**current, **change}
    lines = [
        f"<b>Experience:</b> up to {current['max_years']} year{'s' if current['max_years'] != 1 else ''}",
        f"<b>Cities:</b> {esc(', '.join(current['cities']))}",
        f"<b>Remote:</b> {'yes, if open to India' if current['remote'] else 'no'}",
        f"<b>Looking for:</b> {esc(current['roles'])}",
        f"<b>Not interested in:</b> {esc(current['avoid'] or 'nothing set')}",
        f"<b>Blocked companies:</b> {esc(', '.join(current.get('blocked', [])) or 'none')}",
    ]
    note = "Saved. It applies from the next ranking.\n\n" if change else ""
    tg.send(user["telegram_id"], note + "\n".join(lines) + "\n\n" + PREF_HELP)


def on_button(conn, tg, query: dict) -> None:
    user = conn.execute("select * from users where telegram_id = %s", (query["from"]["id"],)).fetchone()
    message = query.get("message") or {}
    chat, message_id = message.get("chat", {}).get("id"), message.get("message_id")
    parts = (query.get("data") or "").split(":")
    if not user or len(parts) < 2:
        return tg.answer(query["id"])
    kind, handle = parts[0], parts[1]
    m = conn.execute(MATCH + " where m.user_id = %s and m.handle = %s", (user["id"], handle)).fetchone()
    if not m:
        return tg.answer(query["id"], "That job is no longer listed.")

    if kind == "s":
        tg.edit(chat, message_id, card(m) + "\n\n<i>Why skip it?</i>", skip_buttons(handle))
        return tg.answer(query["id"])
    if kind == "b":
        tg.edit(chat, message_id, card(m), buttons(handle))
        return tg.answer(query["id"])

    action, reason, note = {
        "a": ("applied", None, "Marked as applied. Good luck."),
        "l": ("later", None, "Saved for later. It'll be in /today."),
        "r": ("skipped", parts[2] if len(parts) > 2 else "other", "Skipped."),
    }.get(kind, (None, None, None))
    if not action:
        return tg.answer(query["id"])
    record(conn, user, m, action, reason)
    if reason == "company":
        blocked = sorted(set(prefs_for(user).get("blocked", [])) | {m["company"].lower()})
        conn.execute("update users set prefs = prefs || %s where id = %s", (Jsonb({"blocked": blocked}), user["id"]))
        note = f"Skipped. You won't see {m['company'].title()} again (undo: /prefs unblock {m['company']})."
    tg.edit(chat, message_id, card(m) + f"\n\n<i>{esc(note)}</i>", None if action != "later" else buttons(handle))
    tg.answer(query["id"])


def record(conn, user, m, action: str, reason: str | None) -> None:
    with conn.transaction():
        conn.execute("update matches set status = %s where user_id = %s and job_id = %s",
                     (action, user["id"], m["job_id"]))
        conn.execute("""insert into feedback (user_id, job_id, action, reason, fit, verdict)
                        values (%s, %s, %s, %s, %s, %s)""",
                     (user["id"], m["job_id"], action, reason, m["fit"], m["verdict"]))


def main():
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("link")
    hook = sub.add_parser("webhook")
    hook.add_argument("url", help="the deployed app, e.g. https://shortlist-xyz.vercel.app")
    args = parser.parse_args()
    env.load()
    if args.cmd == "link":
        with db.connect() as conn:
            code = secrets.token_urlsafe(6)
            user = conn.execute("update users set link_code = %s where id = (select min(id) from users) returning name",
                                (code,)).fetchone()
        print(f"Send this to the bot to link {user['name']}:  /start {code}")
    else:
        tg = Telegram()
        tg.call("setWebhook", url=f"{args.url.rstrip('/')}/telegram",
                secret_token=os.environ["TELEGRAM_WEBHOOK_SECRET"], allowed_updates=["message", "callback_query"])
        tg.call("setMyCommands", commands=[
            {"command": "today", "description": "Your current matches"},
            {"command": "search", "description": "Look for jobs"},
            {"command": "prefs", "description": "What it filters on"},
            {"command": "help", "description": "How it works"}])
        print("webhook set:", json.dumps(tg.call("getWebhookInfo"))[:200])


if __name__ == "__main__":
    main()
