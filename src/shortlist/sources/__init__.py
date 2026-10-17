"""Job sources.

A source is anything with a `name` and a `fetch()` that returns Jobs.
Public sources live here; personal scrapers live in the gitignored
`private_sources` package at the repo root and are picked up if present.
"""
import logging
import tomllib
from pathlib import Path
from typing import Protocol

from ..models import Job
from .ashby import AshbySource
from .greenhouse import GreenhouseSource
from .lever import LeverSource

log = logging.getLogger(__name__)


class Source(Protocol):
    name: str

    def fetch(self) -> list[Job]: ...


BOARD_SOURCES = {
    "greenhouse": GreenhouseSource,
    "lever": LeverSource,
    "ashby": AshbySource,
}


def load_sources(companies_file: Path, include_private: bool = False) -> list[Source]:
    watchlist = tomllib.loads(companies_file.read_text())
    sources: list[Source] = []
    for board, slugs in watchlist.items():
        cls = BOARD_SOURCES.get(board)
        if cls is None:
            log.warning("no source for board %r, skipping %d companies", board, len(slugs))
            continue
        sources += [cls(slug) for slug in slugs]

    if include_private:
        try:
            import private_sources
        except ImportError:
            log.warning("include_private set but no private_sources package found")
        else:
            sources += private_sources.sources()

    return sources
