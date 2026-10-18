"""Job posts written for people, turned into jobs: a model reads free text (a Telegram
post, an HN comment) and pulls out what the pipeline needs, or says it isn't a job.

It only extracts. A field the text doesn't state comes back empty; nothing is filled in.
"""
import logging
import unicodedata

from . import llm

log = logging.getLogger(__name__)

PROMPT = """You read posts from job channels and pull out the job openings in them.

For each numbered post, return what it says, and nothing it doesn't:
- is_job: false for ads, courses, webinars, "join our group" and anything that isn't one specific opening
- title: as written
- company: the hiring organisation's name, as written; "" if the post doesn't name it (never an email address)
- location: city or cities, or "Remote", as written; "" if not stated
- experience: what it says about experience ("Freshers", "0-2 years", "5+ years"); "" if not stated
- apply_url: the link to apply, if there is one (not WhatsApp, Telegram or course links)
- apply_email: the address to send a resume to, if there is one

A post may list several openings; return one entry per opening, each with the post's number.

Reply with JSON: {"jobs": [{"post": 1, "is_job": true, "title": "", "company": "", "location": "", "experience": "", "apply_url": "", "apply_email": ""}]}"""

BATCH = 4  # posts per model call
# Extraction is simple, so a small model does it, on its own free-tier budget: Groq's Qwen
# caps output at 1000 tokens a minute, and gpt-oss-120b is what my site's chatbot answers with.
DEFAULT = "groq:openai/gpt-oss-20b,gemini:gemini-flash-latest"


def plain(text: str) -> str:
    """Channels write in Unicode "bold" (𝐂𝐚𝐩𝐠𝐞𝐦𝐢𝐧𝐢); NFKC turns that back into letters."""
    return unicodedata.normalize("NFKC", text or "")


def extract(posts: list[str]) -> list[dict]:
    """One dict per opening found, with `post` the index into `posts`."""
    found = []
    for start in range(0, len(posts), BATCH):
        found += _batch(posts, start, min(start + BATCH, len(posts)))
    return found


def _batch(posts: list[str], start: int, end: int) -> list[dict]:
    """Extract posts[start:end]. A reply cut off mid-JSON splits the batch in two; a single
    post that still fails is skipped and logged, rather than losing the whole run."""
    chunk = posts[start:end]
    numbered = "\n\n".join(f"--- post {i + 1} ---\n{plain(p)[:2500]}" for i, p in enumerate(chunk))
    try:
        reply = llm.parse_json(llm.answer(PROMPT, numbered, json_mode=True, max_tokens=2000, effort="low",
                                          setting="SHORTLIST_EXTRACT_LLM", default=DEFAULT)[0])
    except llm.ModelError as e:
        if end - start > 1:
            middle = (start + end) // 2
            return _batch(posts, start, middle) + _batch(posts, middle, end)
        log.warning("skipped a post the model couldn't read: %s", str(e)[:120])
        return []
    found = []
    for job in reply.get("jobs", []):
        try:
            index = int(job.get("post", 0)) - 1
        except (TypeError, ValueError):
            continue
        if 0 <= index < len(chunk) and job.get("is_job") and job.get("title"):
            found.append({**{k: str(job.get(k) or "").strip() for k in
                             ("title", "company", "location", "experience", "apply_url", "apply_email")},
                          "post": start + index})
    return found
