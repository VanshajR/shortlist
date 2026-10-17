"""Storage. Plain sqlite3 for now; Turso's client speaks the same API,
so moving the deployed copy there is a connection-string change."""
import json
import os
import sqlite3
from pathlib import Path

from .models import Job, utcnow

SCHEMA = """
create table if not exists jobs (
    id           text primary key,
    source       text not null,
    company      text not null,
    title        text not null,
    url          text not null,
    location_raw text,
    cities       text,            -- json list
    remote       integer not null default 0,
    in_india     integer not null default 0,
    description  text,
    posted_at    text,
    first_seen   text not null,
    last_seen    text not null
);
create index if not exists jobs_last_seen on jobs(last_seen);
"""


def connect(path: str | None = None) -> sqlite3.Connection:
    path = path or os.environ.get("SHORTLIST_DB", "data/shortlist.db")
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    return conn


def upsert_jobs(conn: sqlite3.Connection, jobs: list[Job]) -> int:
    """Insert new jobs, refresh existing ones. Returns how many were new."""
    now = utcnow().isoformat()
    new = 0
    for job in jobs:
        cur = conn.execute(
            """
            insert into jobs (id, source, company, title, url, location_raw, cities,
                              remote, in_india, description, posted_at, first_seen, last_seen)
            values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            on conflict(id) do update set
                title = excluded.title,
                location_raw = excluded.location_raw,
                cities = excluded.cities,
                remote = excluded.remote,
                in_india = excluded.in_india,
                description = excluded.description,
                last_seen = excluded.last_seen
            returning first_seen = last_seen
            """,
            (
                job.id, job.source, job.company, job.title, job.url, job.location_raw,
                json.dumps(job.cities), job.remote, job.in_india, job.description,
                job.posted_at.isoformat() if job.posted_at else None, now, now,
            ),
        )
        new += cur.fetchone()[0]
    conn.commit()
    return new
