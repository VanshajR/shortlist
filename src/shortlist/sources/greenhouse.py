import html
from datetime import datetime

import httpx

from ..models import Job

API = "https://boards-api.greenhouse.io/v1/boards/{slug}/jobs"


class GreenhouseSource:
    def __init__(self, slug: str):
        self.slug = slug
        self.name = f"greenhouse:{slug}"

    def fetch(self) -> list[Job]:
        r = httpx.get(API.format(slug=self.slug), params={"content": "true"}, timeout=30)
        r.raise_for_status()
        return [self._to_job(j) for j in r.json().get("jobs", [])]

    def _to_job(self, j: dict) -> Job:
        posted = j.get("first_published") or j.get("updated_at")
        return Job(
            source="greenhouse",
            external_id=str(j["id"]),
            company=self.slug,
            title=j["title"].strip(),
            url=j["absolute_url"],
            location_raw=(j.get("location") or {}).get("name", ""),
            # Greenhouse double-escapes the HTML body
            description=html.unescape(j.get("content") or ""),
            posted_at=datetime.fromisoformat(posted) if posted else None,
        )
