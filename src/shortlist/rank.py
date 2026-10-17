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
import tomllib
from pathlib import Path

import psycopg
from psycopg.types.json import Jsonb

from . import db, env, filters, llm, retrieve
from .profile import fetch_profile

def _watchlist() -> dict:
    path = Path("data/companies.toml")
    return tomllib.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


# Sources where anyone can post a job. Everything else is a company we chose to watch.
OPEN_FEEDS = ["telegram", "hn", "ycombinator", "linkedin", "indeed", "naukri", "glassdoor"]
REPUTABLE = _watchlist().get("reputable", [])

DEFAULT_PREFS = {
    "cities": ["Delhi", "Gurugram", "Noida", "Ghaziabad", "Faridabad", "Pune", "Hyderabad", "Bengaluru"],
    "remote": True,          # remote jobs open to India
    "max_years": 2,          # rule out posts asking for more
    "internships": False,
    "max_age_days": 45,
    "off_track": filters.OFF_TRACK,  # title words that mean a different kind of role
    "also_off_track": "",            # the user's own additions, e.g. "sre|devops"
    "roles": "software engineering (backend or full stack) and AI engineering: building with LLMs, agents, RAG",
    "avoid": "",                     # in their words: kinds of role they don't want
    "blocked": [],                   # companies they never want to see (Skip -> "Not this company")
    "any_city_at": [],               # their own additions to the reputable list (anywhere in India is fine)
}


def prefs_for(user: dict) -> dict:
    return {**DEFAULT_PREFS, **(user.get("prefs") or {})}


def reputable_pattern(prefs: dict) -> str:
    """One case-insensitive Postgres regex: any listed name as a whole word."""
    names = [re.escape(n) for n in REPUTABLE + list(prefs.get("any_city_at") or []) if n]
    return r"\m(" + "|".join(names) + r")\M" if names else r"^$\b"


def off_track_for(prefs: dict) -> str:
    return "|".join(p for p in (prefs["off_track"], prefs.get("also_off_track", "")) if p)


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
  -- a reputable company (every watched one, or a known name from an open feed) counts anywhere
  -- in India; an unknown one only in the preferred cities
  and ((j.in_india and (j.cities = '{}' or j.cities && %(cities)s
                        or j.source <> all(%(feeds)s) or j.company ~* %(reputable)s))
       or (%(remote)s and j.remote_scope in ('india', 'global', 'unclear')))
"""


def _title_key(title: str) -> str:
    """'Software Engineer (Bengaluru)' and 'Software Engineer - Pune' are the same role."""
    title = re.sub(r"\(.*?\)|[-–,|].*$", "", title.lower())
    return re.sub(r"\W+", " ", title).strip()


def shortlist_pool(conn: psycopg.Connection, user: dict) -> tuple[list[dict], dict]:
    prefs = prefs_for(user)
    rows = conn.execute(POOL, {"user": user["id"], "max_age": prefs["max_age_days"],
                               "cities": prefs["cities"], "remote": prefs["remote"],
                               "feeds": OPEN_FEEDS, "reputable": reputable_pattern(prefs)}).fetchall()
    out, kept = {}, {}
    blocked = {c.lower() for c in prefs["blocked"]}
    for row in rows:
        if row["company"].lower() in blocked:
            out["blocked company"] = out.get("blocked company", 0) + 1
            continue
        reason = filters.rule_out(row["title"], row["description"], prefs["max_years"],
                                  prefs["internships"], off_track_for(prefs))
        if reason:
            key = "too many years" if reason.startswith("asks") else reason  # "asks for 3+ years" -> one bucket
            out[key] = out.get(key, 0) + 1
            continue
        key = (row["company"].lower(), _title_key(row["title"]))  # "Adobe" from a channel, "adobe" from Workday
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
        # Only jobs the pool actually considered and left out: a job still waiting to be
        # embedded (the free quota is daily) isn't ruled out, just not scored yet.
        conn.execute("""delete from matches where user_id = %s and status = 'new' and not job_id = any(%s)
                        and job_id in (select job_id from job_embeddings)""",
                     (user_id, [r["id"] for r in pool]))


JUDGE = """You screen job posts for one candidate and decide whether they should apply.

The candidate:
{candidate}

They're looking for: {roles}.
They don't want: {avoid}.
They're based in India: on-site roles must be in India, and remote roles must accept people in India.

Score how well this job fits them, 0 to 10:
- 7-10: they meet the core requirements and the seniority suits them. They should apply.
- 5-6: a stretch worth trying. The kind of role is right and the core matches what they've done,
  even if some named tools or a little experience are missing. Early-career people are often
  hired for these, so when the role type is right, prefer this over a lower score.
- 0-4: a different kind of role from the one they want, clearly too senior (more years than they
  have, or a postgraduate degree required), or not open to someone in India.
Judge only from the post and the candidate's experience below; don't assume skills they haven't shown.

Reply with JSON: {{"fit": 0-10, "why": "one or two plain sentences", "gaps": ["at most three things they lack"], "years_required": number or null, "open_to_india": true | false | null}}"""


def candidate_summary(profile: dict, today: str | None = None, max_years: int = 2) -> str:
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
                     f"entry-level roles (0-{max_years} years).")
    return "\n".join(lines)


def _month(yyyymm: str) -> str:
    try:
        return datetime.date.fromisoformat(f"{yyyymm}-01").strftime("%b %Y")
    except (TypeError, ValueError):
        return yyyymm or "?"


def judge_prompt(profile: dict, prefs: dict) -> str:
    return JUDGE.format(candidate=candidate_summary(profile, max_years=prefs["max_years"]),
                        roles=prefs["roles"], avoid=prefs["avoid"] or "nothing in particular")


def judge_post(system: str, job: dict, evidence: list[dict]) -> tuple[dict, str]:
    """One job through the judge: (verdict, the model that gave it). `job` needs title,
    company, cities, remote_scope and description; evidence is the closest highlights."""
    where = ", ".join(job["cities"]) or "not stated"
    if job.get("remote_scope"):
        where += f" (remote: {job['remote_scope']})"
    post = (f"{job['title']} at {job['company']}\nLocation: {where}\n\n{job['description'][:5000]}\n\n"
            "The candidate's experience closest to this job:\n"
            + "\n".join(f"- {h['owner']}: {h['text']}" for h in evidence))
    reply, model = llm.answer(system, post, json_mode=True, max_tokens=500)
    verdict = _clean(llm.parse_json(reply))
    verdict["highlights"] = [h["id"] for h in evidence]
    return verdict, model


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
    system = judge_prompt(profile, prefs)
    for row in rows:
        evidence = retrieve.for_job(conn, user["id"], row["job_id"], k=5)
        verdict, model = judge_post(system, row, evidence)
        conn.execute(
            """update matches set fit = %s, verdict = %s, reasons = %s, judged_by = %s
               where user_id = %s and job_id = %s""",
            (verdict.pop("fit"), verdict.pop("verdict"), Jsonb(verdict), model, user["id"], row["job_id"]))
    return len(rows)


def verdict_for(fit: int) -> str:
    return "apply" if fit >= 7 else "maybe" if fit >= 5 else "skip"


def _clean(raw: dict) -> dict:
    """Models bend formats; keep the fields in range so a bad reply can't break the digest."""
    try:
        fit = max(0, min(10, round(float(raw.get("fit", 0)))))
    except (TypeError, ValueError):
        fit = 0
    # the verdict follows the score, so a reply can't say 6 and "skip"
    verdict = verdict_for(fit)
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
