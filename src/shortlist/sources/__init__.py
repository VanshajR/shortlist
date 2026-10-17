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
from .bigtech import AmazonSource, GoogleSource, MicrosoftSource
from .hn import HackerNewsSource
from .workday import WorkdaySource
from .telegram_channel import TelegramChannelSource
from .ycombinator import YCombinatorSource

log = logging.getLogger(__name__)


class Source(Protocol):
    name: str

    def fetch(self) -> list[Job]: ...


BOARD_SOURCES = {
    "greenhouse": GreenhouseSource,
    "lever": LeverSource,
    "ashby": AshbySource,
    "workday": WorkdaySource,
    "telegram": TelegramChannelSource,  # public channels that post openings
}

# whole career sites with their own job systems, listed by name under `sites`
SITE_SOURCES = {
    "amazon": AmazonSource,
    "google": GoogleSource,
    "microsoft": MicrosoftSource,
    "ycombinator": YCombinatorSource,
    "hn": HackerNewsSource,
}


def load_sources(companies_file: Path, include_private: bool = False) -> list[Source]:
    watchlist = tomllib.loads(companies_file.read_text())
    sources: list[Source] = []
    for board, slugs in watchlist.items():
        if board == "sites":
            for site in slugs:
                if site in SITE_SOURCES:
                    sources.append(SITE_SOURCES[site]())
                else:
                    log.warning("no source for site %r", site)
            continue
        if board == "reputable":  # not a source: names the ranking trusts (see rank.REPUTABLE)
            continue
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
