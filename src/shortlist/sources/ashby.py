from datetime import datetime

import httpx

from ..models import Job

API = "https://api.ashbyhq.com/posting-api/job-board/{slug}"


class AshbySource:
    def __init__(self, slug: str):
        self.slug = slug
        self.name = f"ashby:{slug}"

    def fetch(self) -> list[Job]:
        r = httpx.get(API.format(slug=self.slug), timeout=30)
        r.raise_for_status()
        return [self._to_job(j) for j in r.json().get("jobs", []) if j.get("isListed", True)]

    def _to_job(self, j: dict) -> Job:
        locations = [j.get("location") or ""]
        locations += [s.get("location", "") for s in j.get("secondaryLocations") or []]
        location_raw = ", ".join(dict.fromkeys(l for l in locations if l))
        if j.get("isRemote") or j.get("workplaceType") == "Remote":
            location_raw = f"{location_raw} (Remote)".strip()

        posted = j.get("publishedAt")
        return Job(
            source="ashby",
            external_id=j["id"],
            company=self.slug,
            title=j["title"].strip(),
            url=j["jobUrl"],
            location_raw=location_raw,
            description=j.get("descriptionPlain") or j.get("descriptionHtml") or "",
            posted_at=datetime.fromisoformat(posted) if posted else None,
        )
