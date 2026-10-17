"""Semantic search between jobs and a user's highlights.

    python -m shortlist.retrieve index                 # embed jobs worth matching
    python -m shortlist.retrieve search "real-time systems"
    python -m shortlist.retrieve job <job id>          # my highlights that fit this job
"""
import argparse

import psycopg

from . import db, embeddings, env

# Only these get embedded: in India or remote and open to India, and an engineering-type
# title. Seniority and the rest are ranking's job; this keeps the free quota for jobs that could matter.
CANDIDATES = r"""
    (j.in_india or j.remote_scope in ('global', 'unclear'))
    and j.title ~* '(engineer|developer|sde|software|backend|front.?end|full.?stack|machine learning|\mml\M|\mai\M|data scien|platform|devops|\msre\M|infra)'
    and j.title !~* '(sales|account exec|recruit|marketing|legal|finance|counsel|\mhr\M)'
"""


def job_text(job: dict) -> str:
    where = ", ".join(job["cities"]) + (" (remote)" if job["remote"] else "")
    return f"{job['title']} at {job['company']}\n{where}\n{job['description'][:3000]}"


def index_jobs(conn: psycopg.Connection, limit: int | None = None) -> dict:
    """Embed candidate jobs that are new or whose text changed."""
    rows = conn.execute(
        f"""select j.id, j.title, j.company, j.cities, j.remote, j.description, e.text_hash
            from jobs j left join job_embeddings e on e.job_id = j.id
            where {CANDIDATES}
            order by j.in_india desc, j.first_seen desc""").fetchall()  # India first: the free quota is daily
    todo = []
    for row in rows:
        text = job_text(row)
        digest = embeddings.text_hash(text)
        if row["text_hash"] != digest:
            todo.append((row["id"], text, digest))
    todo = todo[:limit] if limit else todo
    # commit in slices, so a quota stop partway keeps what's done
    done = 0
    for start in range(0, len(todo), 50):
        chunk = todo[start:start + 50]
        try:
            vectors = embeddings.embed([text for _, text, _ in chunk])
        except embeddings.QuotaExhausted as e:
            # a free quota running out isn't a failure: the next scheduled run carries on
            return {"candidates": len(rows), "embedded": done, "left": len(todo) - done, "stopped": str(e)}
        done += len(chunk)
        with conn.transaction():
            for (job_id, _, digest), vector in zip(chunk, vectors):
                conn.execute(
                    """insert into job_embeddings (job_id, text_hash, embedding) values (%s, %s, %s)
                       on conflict (job_id) do update set text_hash = excluded.text_hash,
                           embedding = excluded.embedding, embedded_at = now()""",
                    (job_id, digest, vector))
    return {"candidates": len(rows), "embedded": done, "left": 0}


def search(conn: psycopg.Connection, user_id: int, query: str, k: int = 8) -> list[dict]:
    """The user's highlights closest to a question or a pasted job description."""
    [vector] = embeddings.embed([query], task=embeddings.QUERY)
    return _closest(conn, user_id, vector, k)


def for_job(conn: psycopg.Connection, user_id: int, job_id: str, k: int = 8) -> list[dict]:
    """The user's highlights that fit a job best; what a tailored resume should lead with."""
    row = conn.execute("select embedding from job_embeddings where job_id = %s", (job_id,)).fetchone()
    if not row:
        raise LookupError(f"{job_id} isn't embedded (not a candidate, or index hasn't run)")
    return _closest(conn, user_id, row["embedding"], k)


def _closest(conn, user_id, vector, k):
    return conn.execute(
        """select id, kind, owner, text, tags, meta, 1 - (embedding <=> %s::vector) as score
           from highlights where user_id = %s and embedding is not null
           order by embedding <=> %s::vector limit %s""",
        (vector, user_id, vector, k)).fetchall()


def main():
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("index").add_argument("--limit", type=int)
    sub.add_parser("search").add_argument("query")
    sub.add_parser("job").add_argument("job_id")
    args = parser.parse_args()
    env.load()
    with db.connect() as conn:
        if args.cmd == "index":
            print(index_jobs(conn, args.limit))
            return
        user = conn.execute("select id from users order by id limit 1").fetchone()
        hits = search(conn, user["id"], args.query) if args.cmd == "search" else for_job(conn, user["id"], args.job_id)
        for h in hits:
            print(f"{h['score']:.3f}  {h['owner']:<28.28}  {h['text'][:110]}")


if __name__ == "__main__":
    main()
