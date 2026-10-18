"""The morning digest: each linked user's best new matches, one message per job.

    python -m shortlist.digest            # send to everyone linked
    python -m shortlist.digest --limit 3
"""
import argparse

import psycopg

from . import db, env
from .telegram import Telegram, esc

VERDICT = {"apply": "worth applying", "maybe": "a stretch worth a look", "skip": "probably not"}
SKIP_REASONS = [("Too senior", "senior"), ("Wrong stack", "stack"), ("Not this company", "company"),
                ("Not my kind of role", "role"), ("Location", "location"), ("Other", "other")]


def card(m: dict) -> str:
    """One job as a Telegram message. `m` is a match joined with its job."""
    where = ", ".join(m["cities"][:3]) or "Location not stated"
    if m.get("remote_scope"):
        where += " · remote" if m["remote_scope"] in ("india", "global") else " · remote (check it's open to India)"
    lines = [f"<b>{esc(m['title'])}</b>", f"{esc(m['company'].title())} · {esc(where)}"]
    reasons = m.get("reasons") or {}
    if m.get("fit") is not None:
        lines.append(f"Fit {m['fit']}/10, {VERDICT.get(m.get('verdict'), '')}")
    if reasons.get("why"):
        lines.append(f"\n{esc(reasons['why'])}")
    if reasons.get("gaps"):
        lines.append("Gaps: " + esc("; ".join(reasons["gaps"])))
    lines.append(f'\n<a href="{esc(m["url"])}">Open the posting</a>')
    return "\n".join(lines)


def buttons(handle: str):
    return [[("I applied", f"a:{handle}"), ("Later", f"l:{handle}"), ("Skip", f"s:{handle}")]]


def skip_buttons(handle: str):
    rows = [[(label, f"r:{handle}:{code}") for label, code in SKIP_REASONS[i:i + 2]] for i in range(0, 6, 2)]
    return rows + [[("Back", f"b:{handle}")]]


MATCH = """select m.*, j.title, j.company, j.cities, j.remote_scope, j.url
           from matches m join jobs j on j.id = m.job_id"""


def send_digest(conn: psycopg.Connection, tg: Telegram, user: dict, limit: int = 5) -> int:
    rows = conn.execute(
        MATCH + """ where m.user_id = %s and m.status = 'new' and m.verdict in ('apply', 'maybe')
                    order by m.fit desc, m.semantic desc limit %s""", (user["id"], limit)).fetchall()
    if not rows:
        # Never silent: a quiet morning and a broken pipeline look the same from the outside
        tg.send(user["telegram_id"], quiet_day(conn, user))
        return 0
    tg.send(user["telegram_id"], f"{len(rows)} new job{'s' if len(rows) > 1 else ''} worth a look.")
    for m in rows:
        tg.send(user["telegram_id"], card(m), buttons(m["handle"]))
        conn.execute("update matches set status = 'sent', sent_at = now() where user_id = %s and job_id = %s",
                     (user["id"], m["job_id"]))
    return len(rows)


def quiet_day(conn: psycopg.Connection, user: dict) -> str:
    """Why there's nothing to send: nothing new fitted, or the pipeline is behind."""
    s = conn.execute(
        """select (select count(*) from jobs where first_seen > now() - interval '1 day') as fetched,
                  (select max(last_seen) from jobs) as last_fetch,
                  (select max(embedded_at) from job_embeddings) as last_embed,
                  (select count(*) from matches where user_id = %s and ranked_at > now() - interval '1 day') as ranked,
                  (select count(*) from matches where user_id = %s and status = 'later') as later""",
        (user["id"], user["id"])).fetchone()
    lines = ["No new matches this morning."]
    if not s["last_fetch"] or s["last_fetch"] < _hours_ago(conn, 13):
        lines.append("Jobs haven't been fetched since " + _when(s["last_fetch"]) + ", so something is stuck. I'll look into it.")
    elif not s["last_embed"] or s["last_embed"] < _hours_ago(conn, 30):
        lines.append(f"{s['fetched']} new jobs came in, but matching has been held up since {_when(s['last_embed'])} "
                     "(the free embedding quota), so they haven't been scored yet.")
    else:
        lines.append(f"{s['fetched']} new jobs came in over the last day; none fitted well enough to send.")
    if s["later"]:
        lines.append(f"You have {s['later']} saved for later in /today.")
    return " ".join(lines)


def _hours_ago(conn, hours: int):
    return conn.execute("select now() - make_interval(hours => %s) as t", (hours,)).fetchone()["t"]


def _when(ts) -> str:
    return ts.strftime("%d %b, %H:%M UTC") if ts else "never"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=5)
    args = parser.parse_args()
    env.load()
    tg = Telegram()
    with db.connect() as conn:
        for user in conn.execute("select * from users where telegram_id is not null").fetchall():
            print(f"{user['name']}: sent {send_digest(conn, tg, user, args.limit)}")


if __name__ == "__main__":
    main()
