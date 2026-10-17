"""Hacker News "Ask HN: Who is hiring?", the monthly thread where companies post openings
as comments. Read through HN's public Algolia API.

Most posts are US-only, so only comments that mention India or worldwide remote work go to
the model (see extract.py). The cursor is the newest comment handled, so each run reads only
what's been added since; a new month's thread starts over on its own.
"""
import html
import re
from datetime import datetime, timezone

import httpx

from .. import extract
from ..models import Job

API = "https://hn.algolia.com/api/v1"
OPEN_TO_INDIA = re.compile(r"\b(india|bangalore|bengaluru|hyderabad|pune|gurgaon|gurugram|noida|delhi|mumbai|chennai"
                           r"|remote\s*\(?\s*(?:global|worldwide|anywhere)|worldwide|anywhere in the world|apac)\b", re.I)


class HackerNewsSource:
    name = "hn"
    stateful = True

    def fetch_since(self, cursor: str | None) -> tuple[list[Job], str | None]:
        with httpx.Client(timeout=30) as c:
            hits = c.get(f"{API}/search_by_date", params={"tags": "story,author_whoishiring",
                                                         "query": "who is hiring", "hitsPerPage": 5}).json()["hits"]
            thread = next((h for h in hits if h["title"].lower().startswith("ask hn: who is hiring")), None)
            if not thread:
                return [], cursor
            thread_id, last_seen = thread["objectID"], 0
            if cursor and cursor.startswith(f"{thread_id}:"):
                last_seen = int(cursor.split(":")[1])
            comments = c.get(f"{API}/items/{thread_id}").json().get("children", [])
        fresh = [k for k in comments if k.get("id", 0) > last_seen and k.get("text")]
        candidates = [k for k in fresh if OPEN_TO_INDIA.search(_text(k["text"]))]
        texts = [_text(k["text"]) for k in candidates]
        jobs = []
        for found in extract.extract(texts):
            k = candidates[found["post"]]
            jobs.append(Job(
                source="hn", external_id=f"{k['id']}:{re.sub(r'[^a-z0-9]+', '-', found['title'].lower())[:40]}",
                company=found["company"] if found["company"] and "@" not in found["company"] else "Unknown company",
                title=found["title"],
                url=found["apply_url"] or (f"mailto:{found['apply_email']}" if found["apply_email"]
                                           else f"https://news.ycombinator.com/item?id={k['id']}"),
                location_raw=found["location"],
                description="\n".join(filter(None, [f"Experience: {found['experience']}" if found["experience"] else "",
                                                    texts[found["post"]]])),
                posted_at=datetime.fromtimestamp(k["created_at_i"], timezone.utc) if k.get("created_at_i") else None,
            ))
        newest = max((k["id"] for k in fresh), default=last_seen)
        return jobs, f"{thread_id}:{newest}"

    def fetch(self) -> list[Job]:
        return self.fetch_since(None)[0]


def _text(raw: str) -> str:
    return html.unescape(re.sub(r"<[^>]+>", " ", re.sub(r"<p>", "\n", raw or ""))).strip()
