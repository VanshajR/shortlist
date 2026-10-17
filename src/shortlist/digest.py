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
        return 0  # no "nothing today" message: silence is the digest when there's nothing new
    tg.send(user["telegram_id"], f"{len(rows)} new job{'s' if len(rows) > 1 else ''} worth a look.")
    for m in rows:
        tg.send(user["telegram_id"], card(m), buttons(m["handle"]))
        conn.execute("update matches set status = 'sent', sent_at = now() where user_id = %s and job_id = %s",
                     (user["id"], m["job_id"]))
    return len(rows)


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
