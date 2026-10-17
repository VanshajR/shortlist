"""Rank the job pool for a user.

    python -m shortlist.rank                # rank, judge the best new ones, show the top
    python -m shortlist.rank --judge 0      # semantic scores only, no model calls
    python -m shortlist.rank --show 30

Stages, cheapest first:
  1. the database keeps jobs that are still listed, recent, and in the user's cities
     (or remote and open to India)
  2. filters rule out senior titles and posts asking for more years than the user has
  3. the same role posted for several cities counts once
  4. semantic score: how close the job is to the user's three closest highlights
  5. an LLM judges the best few: fit 0-10, a verdict, why, and the gaps
"""
import argparse
import datetime
import re
import sys

import psycopg
from psycopg.types.json import Jsonb

from . import db, env, filters, llm, retrieve
from .profile import fetch_profile

DEFAULT_PREFS = {
    "cities": ["Delhi", "Gurugram", "Noida", "Ghaziabad", "Faridabad", "Pune", "Hyderabad", "Bengaluru"],
    "remote": True,          # remote jobs open to India
    "max_years": 2,          # rule out posts asking for more
    "internships": False,
    "max_age_days": 45,
    "off_track": filters.OFF_TRACK,  # title words that mean a different kind of role
    "roles": "software engineering (backend or full stack) and AI engineering: building with LLMs, agents, RAG",
}


def prefs_for(user: dict) -> dict:
    return {**DEFAULT_PREFS, **(user.get("prefs") or {})}


POOL = """
select j.id, j.company, j.title, j.description, j.cities, j.remote_scope, j.url,
       (select avg(s) from (
            select 1 - (h.embedding <=> e.embedding) as s from highlights h
            where h.user_id = %(user)s and h.embedding is not null
            order by h.embedding <=> e.embedding limit 3) best) as semantic
from jobs j
join job_embeddings e on e.job_id = j.id
where j.last_seen > now() - interval '3 days'
  and coalesce(j.posted_at, j.first_seen) > now() - make_interval(days => %(max_age)s)
  and ((j.in_india and (j.cities = '{}' or j.cities && %(cities)s))
       or (%(remote)s and j.remote_scope in ('india', 'global', 'unclear')))
"""


def _title_key(title: str) -> str:
    """'Software Engineer (Bengaluru)' and 'Software Engineer - Pune' are the same role."""
    title = re.sub(r"\(.*?\)|[-–,|].*$", "", title.lower())
    return re.sub(r"\W+", " ", title).strip()


def shortlist_pool(conn: psycopg.Connection, user: dict) -> tuple[list[dict], dict]:
    prefs = prefs_for(user)
    rows = conn.execute(POOL, {"user": user["id"], "max_age": prefs["max_age_days"],
                               "cities": prefs["cities"], "remote": prefs["remote"]}).fetchall()
    out, kept = {}, {}
    for row in rows:
        reason = filters.rule_out(row["title"], row["description"], prefs["max_years"],
                                  prefs["internships"], prefs["off_track"])
        if reason:
            out[reason.split(" ")[0] if reason.startswith("asks") else reason] = out.get(reason, 0) + 1
            continue
        key = (row["company"], _title_key(row["title"]))
        if key not in kept or row["semantic"] > kept[key]["semantic"]:
            kept[key] = row
    ruled_out = {"seen": len(rows), **out, "duplicates": len(rows) - sum(out.values()) - len(kept)}
    return sorted(kept.values(), key=lambda r: r["semantic"], reverse=True), ruled_out


def save(conn: psycopg.Connection, user_id: int, pool: list[dict]) -> None:
    """Record semantic scores. Jobs that dropped out lose their unsent matches;
    anything already sent, applied to or skipped stays as history."""
    with conn.transaction():
        for row in pool:
            conn.execute(
                """insert into matches (user_id, job_id, semantic) values (%s, %s, %s)
                   on conflict (user_id, job_id) do update set semantic = excluded.semantic, ranked_at = now()""",
                (user_id, row["id"], row["semantic"]))
        conn.execute("delete from matches where user_id = %s and status = 'new' and not job_id = any(%s)",
                     (user_id, [r["id"] for r in pool]))


JUDGE = """You screen job posts for one candidate and decide whether they should apply.

The candidate:
{candidate}

They're looking for: {roles}.
They're based in India: on-site roles must be in India, and remote roles must accept people in India.

Score how well this job fits them, 0 to 10:
- 8-10: they meet the core requirements, the seniority suits someone early in their career, and they can take it from India.
- 5-7: a reasonable stretch; some requirements are missing but the core matches.
- 0-4: a poor match, too senior, a different field, or not open to someone in India.
Judge only from the post and the candidate's experience below; don't assume skills they haven't shown.

Reply with JSON: {{"fit": 0-10, "verdict": "apply" | "maybe" | "skip", "why": "one or two plain sentences", "gaps": ["at most three things they lack"], "years_required": number or null, "open_to_india": true | false | null}}"""


def candidate_summary(profile: dict, today: str | None = None) -> str:
    """Spelled out, so the judge doesn't have to guess: a bare "until 2026-07" read as
    "still a student", and internships read as no experience at all."""
    today = today or datetime.date.today().isoformat()[:7]
    me = profile["profile"]
    lines = [me.get("headline", "")]
    for ed in profile.get("education", [])[:1]:
        end = ed.get("end") or ""
        when = f"graduated {_month(end)}" if end and end <= today else f"graduating {_month(end)}"
        lines.append(f"Education: {ed['degree']}, {ed['institution']}, {when}"
                     + (f", {ed['score']}" if ed.get("score") else "") + ".")
    roles = [f"{e.get('site_role') or e['role']} at {e['org']} ({_month(e['start'])} to {_month(e.get('end')) if e.get('end') else 'now'})"
             for e in profile.get("experience", []) if e.get("kind") == "work"]
    lines.append("Work so far: " + "; ".join(roles) + ".")
    if all("intern" in r.lower() for r in roles):
        lines.append("Career stage: a new graduate whose experience is internships; looking for "
                     "entry-level roles (0-2 years).")
    return "\n".join(lines)


def _month(yyyymm: str) -> str:
    try:
        return datetime.date.fromisoformat(f"{yyyymm}-01").strftime("%b %Y")
    except (TypeError, ValueError):
        return yyyymm or "?"


def judge(conn: psycopg.Connection, user: dict, profile: dict, limit: int) -> int:
    """Have the model judge the best unjudged matches. Returns how many it judged."""
    prefs = prefs_for(user)
    rows = conn.execute(
        """select m.job_id, j.title, j.company, j.cities, j.remote_scope, j.description
           from matches m join jobs j on j.id = m.job_id
           where m.user_id = %s and m.status = 'new' and m.fit is null
           -- entry-level titles first; remote jobs that may not take India after ones that surely do
           order by j.title ~* %s desc,
                    m.semantic - case when j.remote_scope = 'unclear' then 0.05 else 0 end desc
           limit %s""", (user["id"], filters.ENTRY_LEVEL, limit)).fetchall()
    system = JUDGE.format(candidate=candidate_summary(profile), roles=prefs["roles"])
    for row in rows:
        evidence = retrieve.for_job(conn, user["id"], row["job_id"], k=5)
        where = ", ".join(row["cities"]) or "not stated"
        if row["remote_scope"]:
            where += f" (remote: {row['remote_scope']})"
        post = (f"{row['title']} at {row['company']}\nLocation: {where}\n\n{row['description'][:5000]}\n\n"
                "The candidate's experience closest to this job:\n"
                + "\n".join(f"- {h['owner']}: {h['text']}" for h in evidence))
        reply, model = llm.answer(system, post, json_mode=True, max_tokens=500)
        verdict = _clean(llm.parse_json(reply))
        verdict["highlights"] = [h["id"] for h in evidence]
        conn.execute(
            """update matches set fit = %s, verdict = %s, reasons = %s, judged_by = %s
               where user_id = %s and job_id = %s""",
            (verdict.pop("fit"), verdict.pop("verdict"), Jsonb(verdict), model, user["id"], row["job_id"]))
    return len(rows)


def _clean(raw: dict) -> dict:
    """Models bend formats; keep the fields in range so a bad reply can't break the digest."""
    try:
        fit = max(0, min(10, round(float(raw.get("fit", 0)))))
    except (TypeError, ValueError):
        fit = 0
    verdict = raw.get("verdict")
    if verdict not in ("apply", "maybe", "skip"):
        verdict = "apply" if fit >= 8 else "maybe" if fit >= 5 else "skip"
    years = raw.get("years_required")
    return {
        "fit": fit,
        "verdict": verdict,
        "why": str(raw.get("why", ""))[:400],
        "gaps": [str(g)[:120] for g in (raw.get("gaps") or [])][:3],
        "years_required": years if isinstance(years, int) else None,
        "open_to_india": raw.get("open_to_india") if isinstance(raw.get("open_to_india"), bool) else None,
    }


def top(conn: psycopg.Connection, user_id: int, k: int) -> list[dict]:
    """Judged jobs by fit, then the rest by semantic score."""
    return conn.execute(
        """select m.*, j.title, j.company, j.cities, j.remote_scope, j.url
           from matches m join jobs j on j.id = m.job_id
           where m.user_id = %s and m.status in ('new', 'later')
           order by m.fit desc nulls last, m.semantic desc limit %s""", (user_id, k)).fetchall()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--judge", type=int, default=15, help="how many new matches the model judges (0: none)")
    parser.add_argument("--show", type=int, default=15)
    args = parser.parse_args()
    env.load()
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # models write curly quotes and odd dashes
    with db.connect() as conn:
        user = conn.execute("select * from users order by id limit 1").fetchone()
        pool, ruled_out = shortlist_pool(conn, user)
        save(conn, user["id"], pool)
        judged = judge(conn, user, fetch_profile(user["profile_url"]), args.judge) if args.judge else 0
        print(f"pool {ruled_out} -> {len(pool)} matches, {judged} judged\n")
        for m in top(conn, user["id"], args.show):
            fit = f"{m['fit']:>2}" if m["fit"] is not None else " ."
            where = ", ".join(m["cities"][:2]) or (m["remote_scope"] or "")
            print(f"{fit}  {m['semantic']:.3f}  {m['title'][:46]:<46}  {m['company']:<12.12}  {where[:22]}")
            if m["reasons"].get("why"):
                print(f"        {m['reasons']['why'][:150]}")


if __name__ == "__main__":
    main()
