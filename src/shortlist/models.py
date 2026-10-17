from dataclasses import dataclass, field
from datetime import datetime, timezone


@dataclass
class Job:
    source: str          # "greenhouse", "lever", "linkedin", ...
    external_id: str     # the id the source uses
    company: str
    title: str
    url: str
    location_raw: str = ""
    description: str = ""
    posted_at: datetime | None = None
    # filled in by normalize(), not by sources
    cities: list[str] = field(default_factory=list)
    remote: bool = False
    in_india: bool = False

    @property
    def id(self) -> str:
        return f"{self.source}:{self.company}:{self.external_id}"


def utcnow() -> datetime:
    return datetime.now(timezone.utc)
