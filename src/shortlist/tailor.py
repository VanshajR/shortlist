"""A one-page resume tailored to a job, from the user's profile.

    python -m shortlist.tailor --job "workday:mastercard:R-293576"
    python -m shortlist.tailor --general          # no particular job
    python -m shortlist.tailor --job ... --out out/

The phone number comes from RESUME_PHONE in .env: profile.json is public, a phone isn't.
"""
import argparse
import os
import re
import sys
from pathlib import Path

import psycopg

from . import db, embeddings, env
from .profile import fetch_profile
from .resume.build import Result, build


def scores_for(conn: psycopg.Connection, user_id: int, job: dict) -> dict[str, float]:
    """How close each of the user's highlights is to the job."""
    rows = conn.execute(
        """select h.id, 1 - (h.embedding <=> e.embedding) as score from highlights h
           join job_embeddings e on e.job_id = %s where h.user_id = %s and h.embedding is not null""",
        (job["id"], user_id)).fetchall()
    if not rows:  # not embedded yet: embed the post now
        [vector] = embeddings.embed([f"{job['title']} at {job['company']}\n{job['description'][:3000]}"])
        rows = conn.execute(
            """select id, 1 - (embedding <=> %s::vector) as score from highlights
               where user_id = %s and embedding is not null""", (vector, user_id)).fetchall()
    return {r["id"]: r["score"] for r in rows}


def tailor(conn: psycopg.Connection, user: dict, job_id: str | None) -> tuple[Result, dict | None]:
    profile = fetch_profile(user["profile_url"])
    job = None
    if job_id:
        job = conn.execute("select * from jobs where id = %s", (job_id,)).fetchone()
        if not job:
            raise SystemExit(f"no job {job_id}")
    scores = scores_for(conn, user["id"], job) if job else None
    job_text = f"{job['title']}\n{job['description']}" if job else ""
    return build(profile, scores, job_text, phone=os.environ.get("RESUME_PHONE")), job


def filename(user: dict, job: dict | None) -> str:
    slug = lambda s: re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")[:40]
    who = slug(user["name"])
    return f"{who}-{slug(job['company'])}-{slug(job['title'])}" if job else f"{who}-resume"


def main():
    parser = argparse.ArgumentParser()
    which = parser.add_mutually_exclusive_group(required=True)
    which.add_argument("--job", help="a job id from the database")
    which.add_argument("--general", action="store_true", help="a resume for no particular job")
    parser.add_argument("--out", type=Path, default=Path("out"))
    args = parser.parse_args()
    env.load()
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    with db.connect() as conn:
        user = conn.execute("select * from users order by id limit 1").fetchone()
        result, job = tailor(conn, user, args.job)
    args.out.mkdir(parents=True, exist_ok=True)
    name = filename(user, job)
    (args.out / f"{name}.tex").write_text(result.tex, encoding="utf-8")
    (args.out / f"{name}.pdf").write_bytes(result.pdf)
    print(f"{args.out / name}.pdf: {result.pages} page(s), trimmed {result.trimmed} time(s)")
    for p in result.problems:
        print("  problem:", p)


if __name__ == "__main__":
    main()
