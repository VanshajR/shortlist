"""Career sites of large employers with their own job systems: Google, Microsoft, Amazon.

None of them document these endpoints; each is the JSON its own careers page loads.
They're asked for India only, and full descriptions are fetched only for
engineering-type titles, so a run stays to a few dozen requests per company.
"""
import json
import re
import time
from datetime import datetime, timezone

import httpx

from ..filters import ENGINEERING_TITLE
from ..models import Job

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126 Safari/537.36"}


def _client() -> httpx.Client:
    return httpx.Client(timeout=30, follow_redirects=True, headers=UA)


def _polite_get(c: httpx.Client, url: str, params: dict, pause: float = 0.4) -> httpx.Response:
    """A pause between requests, and when told to slow down (429), wait and retry."""
    for attempt in range(4):
        time.sleep(pause)
        r = c.get(url, params=params)
        if r.status_code != 429:
            return r
        time.sleep(float(r.headers.get("retry-after") or 10 * (attempt + 1)))
    return r


class AmazonSource:
    """amazon.jobs: one search API that returns descriptions too."""
    name = "amazon"
    API = "https://www.amazon.jobs/en/search.json"
    CATEGORIES = ["software-development", "machine-learning-science", "data-science"]

    def fetch(self) -> list[Job]:
        jobs, seen = [], set()
        with _client() as c:
            for category in self.CATEGORIES:
                offset = 0
                while offset < 1000:
                    r = c.get(self.API, params={"normalized_country_code[]": "IND", "category[]": category,
                                                "result_limit": 100, "offset": offset, "sort": "recent"})
                    r.raise_for_status()
                    page = r.json().get("jobs", [])
                    for j in page:
                        if j["id_icims"] in seen:
                            continue
                        seen.add(j["id_icims"])
                        jobs.append(Job(
                            source="amazon", external_id=str(j["id_icims"]), company=j.get("company_name") or "Amazon",
                            title=j["title"], url="https://www.amazon.jobs" + j["job_path"],
                            location_raw=f"{j.get('city', '')}, India",
                            description="\n\n".join(filter(None, [j.get("description"),
                                                                  "Basic qualifications:\n" + (j.get("basic_qualifications") or ""),
                                                                  "Preferred qualifications:\n" + (j.get("preferred_qualifications") or "")])),
                            posted_at=_parse_date(j.get("posted_date"), "%B %d, %Y"),
                        ))
                    offset += 100
                    if len(page) < 100:
                        break
        return jobs


class MicrosoftSource:
    """Microsoft's careers site (Eightfold): a search API, then one request per job for its description."""
    name = "microsoft"
    API = "https://apply.careers.microsoft.com/api/pcsx"

    def fetch(self) -> list[Job]:
        with _client() as c:
            positions, start = [], 0
            while start < 1500:
                r = _polite_get(c, f"{self.API}/search", {"domain": "microsoft.com", "location": "India", "start": start})
                r.raise_for_status()
                page = r.json()["data"]["positions"]
                positions += page
                start += len(page)
                if not page or start >= r.json()["data"].get("count", 0):
                    break
            jobs = []
            for p in positions:
                if not ENGINEERING_TITLE.search(p["name"]):
                    continue
                d = _polite_get(c, f"{self.API}/position_details", {"position_id": p["id"], "domain": "microsoft.com", "hl": "en"})
                info = d.json().get("data", {}) if d.status_code == 200 else {}
                jobs.append(Job(
                    source="microsoft", external_id=str(p.get("displayJobId") or p["id"]), company="Microsoft",
                    title=p["name"],
                    url=f"https://apply.careers.microsoft.com/careers?pid={p['id']}&domain=microsoft.com",
                    location_raw="; ".join(p.get("locations") or []),
                    description=info.get("jobDescription", ""),
                    posted_at=datetime.fromtimestamp(p["postedTs"], timezone.utc) if p.get("postedTs") else None,
                ))
        return jobs


class GoogleSource:
    """Google's careers results page embeds its jobs as a data blob. Asking for early-career
    and mid levels keeps out the senior roles before anything else does."""
    name = "google"
    PAGE = "https://www.google.com/about/careers/applications/jobs/results"
    LEVELS = ["EARLY", "MID"]

    def fetch(self) -> list[Job]:
        jobs, seen = [], set()
        with _client() as c:
            for level in self.LEVELS:
                for page in range(1, 30):
                    r = c.get(self.PAGE, params={"location": "India", "target_level": level, "page": page})
                    r.raise_for_status()
                    blob = re.search(r"AF_initDataCallback\(\{key: 'ds:1'.*?data:(\[.*?\]), sideChannel", r.text, re.S)
                    rows = (json.loads(blob.group(1))[0] or []) if blob else []
                    for row in rows:
                        if row[0] in seen:
                            continue
                        seen.add(row[0])
                        jobs.append(_google_job(row))
                    if len(rows) < 20:
                        break
        return jobs


def _google_job(row: list) -> Job:
    text = lambda cell: (cell[1] if isinstance(cell, list) and len(cell) > 1 else "") or ""
    places = [loc[0] for loc in (row[9] or []) if loc]
    created = row[12][0] if isinstance(row[12], list) and row[12] else None
    return Job(
        source="google", external_id=str(row[0]), company="Google", title=row[1],
        url=f"https://www.google.com/about/careers/applications/jobs/results/{row[0]}",
        location_raw="; ".join(places),
        description="\n\n".join(filter(None, [text(row[10]), text(row[3]), text(row[4]), text(row[19])])),
        posted_at=datetime.fromtimestamp(created, timezone.utc) if created else None,
    )


def _parse_date(value: str | None, fmt: str) -> datetime | None:
    try:
        return datetime.strptime(value, fmt).replace(tzinfo=timezone.utc) if value else None
    except ValueError:
        return None
