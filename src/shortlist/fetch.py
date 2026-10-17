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

COMPANIES = Path(__file__).resolve().parents[2] / "data" / "companies.toml"


def _run(source: Source):
    try:
        return source.name, source.fetch(), None
    except Exception as e:  # one dead board shouldn't sink the run
        return source.name, [], e


def fetch_all(include_private: bool = False) -> dict:
    sources = load_sources(COMPANIES, include_private)
    jobs, failed = [], []

    with ThreadPoolExecutor(max_workers=8) as pool:
        for name, found, err in pool.map(_run, sources):
            if err:
                log.warning("%s failed: %s", name, err)
                failed.append(name)
            else:
                log.info("%s: %d jobs", name, len(found))
                jobs += found

    jobs = [normalize(j) for j in jobs]
    for job in jobs:
        job.description = html_to_text(job.description)
    with db.connect() as conn:
        new = db.upsert_jobs(conn, jobs)

    india = sum(j.in_india for j in jobs)
    summary = {"sources": len(sources), "failed": failed, "jobs": len(jobs), "india": india, "new": new}
    log.info("done: %s", summary)
    return summary


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--private", action="store_true", help="include private_sources")
    args = parser.parse_args()
    env.load()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    fetch_all(include_private=args.private)


if __name__ == "__main__":
    main()
