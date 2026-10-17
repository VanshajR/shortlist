"""Y Combinator's job board: startups from YC batches, many hiring in India or remotely.

The board's pages carry their data as JSON (an Inertia "data-page" attribute). The
list gives location and minimum experience; descriptions come from each job's page,
fetched only for jobs that could be open to someone in India.
"""
import html
import json
import re

import httpx

from ..models import Job

BASE = "https://www.ycombinator.com"
ROLES = ["software-engineer", "machine-learning"]  # role pages on the board
OPEN_TO_INDIA = re.compile(r"\b(IN\b|india|bangalore|bengaluru|remote\s*$|remote \((global|anywhere|worldwide|in)\b)", re.I)


def _page_data(client: httpx.Client, path: str) -> dict:
    r = client.get(BASE + path)
    r.raise_for_status()
    found = re.search(r'data-page="([^"]+)"', r.text)
    return json.loads(html.unescape(found.group(1)))["props"] if found else {}


class YCombinatorSource:
    name = "ycombinator"

    def fetch(self) -> list[Job]:
        jobs, seen = [], set()
        with httpx.Client(timeout=30, follow_redirects=True, headers={"User-Agent": "Mozilla/5.0"}) as c:
            for role in ROLES:
                for post in _page_data(c, f"/jobs/role/{role}").get("jobPostings", []):
                    if post["id"] in seen or not OPEN_TO_INDIA.search(post.get("location") or ""):
                        continue
                    seen.add(post["id"])
                    detail = _page_data(c, post["url"]).get("job", {})
                    description = re.sub(r"<[^>]+>", "\n", detail.get("description") or "")
                    if post.get("minExperience"):
                        description = f"Experience: {post['minExperience']}\n\n{description}"
                    jobs.append(Job(
                        source="ycombinator", external_id=str(post["id"]),
                        company=post.get("companyName") or post.get("companySlug") or "YC startup",
                        title=post["title"], url=BASE + post["url"],
                        location_raw=post.get("location") or "", description=description,
                    ))
        return jobs
