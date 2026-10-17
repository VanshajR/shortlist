from datetime import datetime, timezone

import httpx

from ..models import Job

API = "https://api.lever.co/v0/postings/{slug}"


class LeverSource:
    def __init__(self, slug: str):
        self.slug = slug
        self.name = f"lever:{slug}"

    def fetch(self) -> list[Job]:
        r = httpx.get(API.format(slug=self.slug), params={"mode": "json"}, timeout=30)
        r.raise_for_status()
        return [self._to_job(p) for p in r.json()]

    def _to_job(self, p: dict) -> Job:
        cats = p.get("categories") or {}
        # Lever lists extra offices separately from the primary one
        locations = [cats.get("location") or "", *(cats.get("allLocations") or [])]
        location_raw = ", ".join(dict.fromkeys(l for l in locations if l))
        if p.get("workplaceType") == "remote":
            location_raw = f"{location_raw} (Remote)".strip()

        created = p.get("createdAt")  # epoch millis
        return Job(
            source="lever",
            external_id=p["id"],
            company=self.slug,
            title=p["text"].strip(),
            url=p["hostedUrl"],
            location_raw=location_raw,
            description=p.get("descriptionPlain") or p.get("description") or "",
            posted_at=datetime.fromtimestamp(created / 1000, timezone.utc) if created else None,
        )
