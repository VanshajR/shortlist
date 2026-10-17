"""Public Telegram channels that post openings, read through Telegram's public web
preview (t.me/s/<channel>): no account, no API key, the same page anyone can open.

Posts are free text, so a model extracts the jobs (see extract.py). Each run reads only
posts newer than the last one handled (the cursor in source_state). Posts sent seconds
apart are one message split up, so they're read together. A Google Form link has its
title and description fetched, since the post itself often says little more than "apply".
"""
import html
import re
from datetime import datetime

import httpx

from .. import extract
from ..models import Job

PAGE = "https://t.me/s/{channel}"
MAX_PAGES = 5          # a first run reads the latest ~100 posts
SAME_MESSAGE_S = 15    # a message split in parts arrives within seconds
# ...but channels also post several different openings back to back, so a post that
# opens like an opening starts a new one however close it is
NEW_OPENING = re.compile(r"^\W*(?:we.?re\s+)?(?:hiring|position|role|opening|job title|urgent)\b", re.I)


class TelegramChannelSource:
    stateful = True

    def __init__(self, channel: str):
        self.channel = channel.lstrip("@")
        self.name = f"telegram:{self.channel}"

    def fetch_since(self, cursor: str | None) -> tuple[list[Job], str | None]:
        last_seen = int(cursor) if cursor else 0
        with httpx.Client(timeout=30, follow_redirects=True, headers={"User-Agent": "Mozilla/5.0"}) as c:
            posts = self._new_posts(c, last_seen)
            if not posts:
                return [], cursor
            groups = _group(posts)
            texts = [_with_forms(c, "\n\n".join(p["text"] for p in g)) for g in groups]
        jobs = []
        for found in extract.extract(texts):
            group = groups[found["post"]]
            first = group[0]
            details = [f"Experience: {found['experience']}" if found["experience"] else "",
                       f"Apply by email: {found['apply_email']}" if found["apply_email"] else "",
                       texts[found["post"]]]
            jobs.append(Job(
                source="telegram", external_id=f"{self.channel}:{first['id']}:{_slug(found['title'])}",
                # a recruiter's address is not a company name
                company=found["company"] if found["company"] and "@" not in found["company"] else "Unknown company",
                title=found["title"],
                url=found["apply_url"] or (f"mailto:{found['apply_email']}" if found["apply_email"]
                                           else f"https://t.me/{self.channel}/{first['id']}"),
                location_raw=found["location"], description="\n".join(filter(None, details)),
                posted_at=first["at"],
            ))
        return jobs, str(max(p["id"] for p in posts))

    def fetch(self) -> list[Job]:
        return self.fetch_since(None)[0]

    def _new_posts(self, c: httpx.Client, last_seen: int) -> list[dict]:
        posts, before = [], None
        for _ in range(MAX_PAGES):
            r = c.get(PAGE.format(channel=self.channel), params={"before": before} if before else None)
            r.raise_for_status()
            page = _parse(r.text, self.channel)
            fresh = [p for p in page if p["id"] > last_seen]
            posts += fresh
            if not page or len(fresh) < len(page):
                break
            before = min(p["id"] for p in page)
        return sorted({p["id"]: p for p in posts}.values(), key=lambda p: p["id"])


def _parse(page: str, channel: str) -> list[dict]:
    out = []
    for block in page.split('class="tgme_widget_message_wrap')[1:]:
        post = re.search(rf'data-post="{re.escape(channel)}/(\d+)"', block, re.I)
        body = re.search(r'<div class="tgme_widget_message_text[^"]*"[^>]*>(.*?)</div>', block, re.S)
        when = re.search(r'datetime="([^"]+)"', block)
        if not (post and body and when):
            continue
        raw = body.group(1)
        links = re.findall(r'href="(https?://[^"]+)"', raw)
        text = html.unescape(re.sub(r"<[^>]+>", "", re.sub(r"<br\s*/?>", "\n", raw)))
        # the visible text can shorten a URL; keep the real ones
        text += "".join(f"\n{u}" for u in links if u not in text)
        out.append({"id": int(post.group(1)), "text": text.strip(), "at": datetime.fromisoformat(when.group(1))})
    return out


def _group(posts: list[dict]) -> list[list[dict]]:
    groups = []
    for p in posts:
        if groups and (p["at"] - groups[-1][-1]["at"]).total_seconds() <= SAME_MESSAGE_S \
                and not NEW_OPENING.search(extract.plain(p["text"])):
            groups[-1].append(p)
        else:
            groups.append([p])
    return groups


def _with_forms(c: httpx.Client, text: str) -> str:
    """Add a linked Google Form's own title and description to the post's text."""
    for url in re.findall(r"https://(?:docs\.google\.com/forms|forms\.gle)/\S+", text)[:2]:
        try:
            page = c.get(url).text
        except httpx.HTTPError:
            continue
        meta = dict(re.findall(r'<meta property="og:(title|description)" content="([^"]*)"', page))
        if meta:
            text += f"\n\n[Form: {html.unescape(meta.get('title', ''))}] {html.unescape(meta.get('description', ''))[:1200]}"
    return text


def _slug(title: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")[:40]
