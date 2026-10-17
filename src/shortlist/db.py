"""Storage: Postgres with pgvector. Neon in production, a local container while
developing (see README). Schema changes are numbered SQL files in migrations/,
applied in order and recorded, so every database ends up the same."""
import os
from pathlib import Path

import psycopg
from pgvector.psycopg import register_vector
from psycopg.rows import dict_row

from .models import Job

MIGRATIONS = Path(__file__).parent / "migrations"


def connect(url: str | None = None) -> psycopg.Connection:
    url = url or os.environ.get("DATABASE_URL")
    if not url:
        raise SystemExit("DATABASE_URL isn't set; see .env.example")
    # Autocommit: reads don't hold a transaction open while a job waits minutes on an API,
    # which Neon's pooler doesn't survive; writes use explicit transaction blocks.
    # No server-side prepared statements, since the pooler can switch server connections.
    conn = psycopg.connect(url, row_factory=dict_row, autocommit=True, prepare_threshold=None)
    migrate(conn)
    register_vector(conn)  # after migrating: the first migration creates the extension
    return conn


def migrate(conn: psycopg.Connection) -> list[str]:
    """Apply any migrations this database hasn't seen. Returns their names."""
    with conn.transaction():
        # two cron runs starting together shouldn't both migrate
        conn.execute("select pg_advisory_xact_lock(7461)")
        conn.execute("create table if not exists schema_migrations "
                     "(version text primary key, applied_at timestamptz not null default now())")
        done = {r["version"] for r in conn.execute("select version from schema_migrations")}
        applied = []
        for path in sorted(MIGRATIONS.glob("*.sql")):
            if path.stem in done:
                continue
            conn.execute(path.read_text(encoding="utf-8"))
            conn.execute("insert into schema_migrations (version) values (%s)", (path.stem,))
            applied.append(path.stem)
    return applied


UPSERT = """
insert into jobs (id, source, company, title, url, location_raw, cities, remote, in_india, remote_scope,
                  description, posted_at)
values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
on conflict (id) do update set
    title = excluded.title,
    location_raw = excluded.location_raw,
    cities = excluded.cities,
    remote = excluded.remote,
    in_india = excluded.in_india,
    remote_scope = excluded.remote_scope,
    description = excluded.description,
    last_seen = now()
returning (xmax = 0) as inserted
"""


def upsert_jobs(conn: psycopg.Connection, jobs: list[Job]) -> int:
    """Insert new jobs and refresh the ones already known. Returns how many were new."""
    if not jobs:
        return 0
    rows = [
        (j.id, j.source, j.company, j.title, j.url, j.location_raw, j.cities, j.remote,
         j.in_india, j.remote_scope, j.description, j.posted_at)
        for j in jobs
    ]
    new = 0
    with conn.transaction(), conn.cursor() as cur:
        cur.executemany(UPSERT, rows, returning=True)
        while True:
            new += cur.fetchone()["inserted"]
            if not cur.nextset():
                break
    return new
