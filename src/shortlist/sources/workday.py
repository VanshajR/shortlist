"""Workday career sites, which most large companies hiring freshers in India use.

Every site has an undocumented but public JSON API behind its careers page. A
watchlist entry is "tenant.wdN/site", read off the careers URL:
https://nvidia.wd5.myworkdayjobs.com/NVIDIAExternalCareerSite -> "nvidia.wd5/NVIDIAExternalCareerSite".

Sites list thousands of jobs worldwide, so this asks for India only (each site
names its location filter differently; it's found by looking for "India") and
fetches full descriptions only for engineering-type titles, one request each.
"""
import re
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

import httpx

from ..filters import ENGINEERING_TITLE
from ..models import Job

PAGE = 20          # the most Workday returns per request
MAX_POSTINGS = 400  # per site, per run: India listings on even the biggest sites fit


class WorkdaySource:
    def __init__(self, spec: str):
        host, _, self.site = spec.partition("/")
        self.tenant, _, wd = host.partition(".")
        self.base = f"https://{self.tenant}.{wd}.myworkdayjobs.com"
        self.api = f"{self.base}/wday/cxs/{self.tenant}/{self.site}"
        self.name = f"workday:{self.tenant}"

    def fetch(self) -> list[Job]:
        with httpx.Client(timeout=30, headers={"Accept": "application/json"}) as client:
            first = self._page(client, {}, "", 0)
            facet = _india_facet(first.get("facets", []))
            applied, search = ({facet[0]: [facet[1]]}, "") if facet else ({}, "India")
            postings, offset, total = [], 0, None
            while offset < MAX_POSTINGS:
                page = self._page(client, applied, search, offset)
                total = total or page.get("total")  # only the first page says; later ones report 0
                postings += page.get("jobPostings", [])
                offset += PAGE
                if not page.get("jobPostings") or offset >= (total or 0):
                    break
            wanted = [p for p in postings if ENGINEERING_TITLE.search(p.get("title", ""))]
            with ThreadPoolExecutor(4) as pool:
                jobs = list(pool.map(lambda p: self._job(client, p), wanted))
        return [j for j in jobs if j]

    def _page(self, client, facets, search, offset) -> dict:
        r = client.post(f"{self.api}/jobs", json={"appliedFacets": facets, "limit": PAGE,
                                                   "offset": offset, "searchText": search})
        r.raise_for_status()
        return r.json()

    def _job(self, client, posting: dict) -> Job | None:
        try:
            r = client.get(f"{self.api}{posting['externalPath']}")
            r.raise_for_status()
            info = r.json()["jobPostingInfo"]
        except (httpx.HTTPError, KeyError, ValueError):
            return None  # one broken posting shouldn't sink the site
        places = [info.get("location", "")] + list(info.get("additionalLocations") or [])
        return Job(
            source="workday",
            external_id=info.get("jobReqId") or posting["externalPath"].rsplit("_", 1)[-1],
            company=self.tenant,
            title=info.get("title") or posting["title"],
            url=info.get("externalUrl") or f"{self.base}/en-US/{self.site}{posting['externalPath']}",
            location_raw="; ".join(p for p in places if p),
            description=info.get("jobDescription", ""),
            posted_at=_posted(info.get("startDate"), posting.get("postedOn", "")),
        )


def _india_facet(facets: list[dict]) -> tuple[str, str] | None:
    """(facet parameter, value id) for India, wherever this site keeps it."""
    def walk(param, values):
        for v in values:
            if v.get("descriptor", "").strip().lower() == "india":
                return param, v["id"]
            found = walk(v.get("facetParameter", param), v.get("values", []))
            if found:
                return found
        return None

    for facet in facets:
        found = walk(facet.get("facetParameter"), facet.get("values", []))
        if found:
            return found
    return None


def _posted(start_date: str | None, posted_on: str) -> datetime | None:
    if start_date:
        try:
            return datetime.fromisoformat(start_date).replace(tzinfo=timezone.utc)
        except ValueError:
            pass
    # the list only says "Posted Today", "Posted 3 Days Ago", "Posted 30+ Days Ago"
    now = datetime.now(timezone.utc)
    if "today" in posted_on.lower():
        return now
    if "yesterday" in posted_on.lower():
        return now - timedelta(days=1)
    days = re.search(r"(\d+)\+?\s*days", posted_on, re.I)
    return now - timedelta(days=int(days.group(1))) if days else None
