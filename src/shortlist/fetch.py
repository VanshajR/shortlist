"""Pull jobs from every source into the database.

    python -m shortlist.fetch              # public boards only
    python -m shortlist.fetch --private    # plus local-only scrapers
"""
import argparse
import logging
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from . import db, env
from .locations import normalize
from .text import html_to_text
from .sources import Source, load_sources

log = logging.getLogger("shortlist.fetch")

# relative to where it runs (the repo root), not to the installed package
COMPANIES = Path("data/companies.toml")


def _run(source: Source, cursors: dict[str, str]):
    """(name, jobs, error, new cursor). Stream sources (stateful) read from their cursor."""
    try:
        if getattr(source, "stateful", False):
            jobs, cursor = source.fetch_since(cursors.get(source.name))
            return source.name, jobs, None, cursor
        return source.name, source.fetch(), None, None
    except Exception as e:  # one dead board shouldn't sink the run
        return source.name, [], e, None


def fetch_all(include_private: bool = False, companies: Path = COMPANIES) -> dict:
    sources = load_sources(companies, include_private)
    jobs, failed, moved = [], [], {}

    with db.connect() as conn:
        cursors = {r["source"]: r["cursor"] for r in conn.execute("select source, cursor from source_state")}
    with ThreadPoolExecutor(max_workers=8) as pool:
        for name, found, err, cursor in pool.map(lambda s: _run(s, cursors), sources):
            if err:
                log.warning("%s failed: %s", name, err)
                failed.append(name)
            else:
                log.info("%s: %d jobs", name, len(found))
                jobs += found
                if cursor and cursor != cursors.get(name):
                    moved[name] = cursor

    jobs = [normalize(j) for j in jobs]
    for job in jobs:
        job.description = html_to_text(job.description)
    with db.connect() as conn:
        new = db.upsert_jobs(conn, jobs)
        # only after the jobs are stored: a run that dies first re-reads those posts next time
        for name, cursor in moved.items():
            conn.execute("""insert into source_state (source, cursor) values (%s, %s)
                            on conflict (source) do update set cursor = excluded.cursor, updated_at = now()""",
                         (name, cursor))

    india = sum(j.in_india for j in jobs)
    summary = {"sources": len(sources), "failed": failed, "jobs": len(jobs), "india": india, "new": new}
    log.info("done: %s", summary)
    return summary


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--private", action="store_true", help="include private_sources")
    parser.add_argument("--companies", type=Path, default=COMPANIES, help="watchlist (default: data/companies.toml)")
    args = parser.parse_args()
    env.load()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    fetch_all(include_private=args.private, companies=args.companies)


if __name__ == "__main__":
    main()
