from datetime import datetime, timedelta, timezone

from shortlist import extract
from shortlist.sources import telegram_channel as tc

PAGE = """
<div class="tgme_widget_message_wrap"><div data-post="getjobss/8274">
<div class="tgme_widget_message_text js-message_text">𝐂𝐚𝐩𝐠𝐞𝐦𝐢𝐧𝐢<br/>Position: Associate Software Engineer<br/>
Experience: Freshers<br/>Location: Bangalore, India<br/>Apply Link: <a href="https://www.capgemini.com/in-en/jobs/535235">https://www.capgemini.com/in-en/jobs/5...</a></div>
<time datetime="2026-10-17T01:24:35+00:00"></time></div></div>
<div class="tgme_widget_message_wrap"><div data-post="getjobss/8276">
<div class="tgme_widget_message_text js-message_text">IBM FREE COURSES 2026! <a href="https://pdlink.in/4zG">https://pdlink.in/4zG</a></div>
<time datetime="2026-10-17T06:03:48+00:00"></time></div></div>
"""


def test_posts_are_read_with_their_real_links_and_plain_letters():
    posts = tc._parse(PAGE, "getjobss")
    assert [p["id"] for p in posts] == [8274, 8276]
    assert "https://www.capgemini.com/in-en/jobs/535235" in posts[0]["text"]  # the full URL, not the shortened text
    assert extract.plain(posts[0]["text"]).startswith("Capgemini")


def test_posts_sent_seconds_apart_are_one_message():
    t = datetime(2026, 10, 17, tzinfo=timezone.utc)
    posts = [{"id": 1, "text": "HIRING QA ENGINEER", "at": t},
             {"id": 2, "text": "Key skills: Python", "at": t + timedelta(seconds=5)},
             {"id": 3, "text": "Hiring: Data Analyst", "at": t + timedelta(seconds=8)},   # close, but a new opening
             {"id": 4, "text": "Share your resume", "at": t + timedelta(minutes=30)}]
    assert [[p["id"] for p in g] for g in tc._group(posts)] == [[1, 2], [3], [4]]


def test_only_new_posts_are_read_and_ads_are_dropped(monkeypatch):
    class Page:
        text = PAGE
        def raise_for_status(self): pass

    monkeypatch.setattr(tc.httpx.Client, "get", lambda self, url, params=None: Page())
    seen = []

    def fake_extract(texts):
        seen.extend(texts)
        return [{"post": 0, "title": "Associate Software Engineer", "company": "Capgemini", "location": "Bangalore, India",
                 "experience": "Freshers", "apply_url": "https://www.capgemini.com/in-en/jobs/535235", "apply_email": ""}]

    monkeypatch.setattr(tc.extract, "extract", fake_extract)
    jobs, cursor = tc.TelegramChannelSource("getjobss").fetch_since("8275")
    assert len(seen) == 1 and "IBM" in seen[0]  # 8274 was already handled; only 8276 went to the model
    jobs, cursor = tc.TelegramChannelSource("getjobss").fetch_since(None)
    assert cursor == "8276" and jobs[0].company == "Capgemini"
    assert jobs[0].description.startswith("Experience: Freshers") and jobs[0].url.startswith("https://www.capgemini.com")


def test_extraction_keeps_only_jobs_and_maps_them_to_posts(monkeypatch):
    import json
    monkeypatch.setattr(extract.llm, "answer", lambda system, user, **kw: (json.dumps({"jobs": [
        {"post": 1, "is_job": True, "title": "SDE", "company": "Acme"},
        {"post": 2, "is_job": False, "title": "Free course"},
        {"post": 9, "is_job": True, "title": "Out of range"}]}), "test:model"))
    found = extract.extract(["post one", "post two"])
    assert [(f["post"], f["title"]) for f in found] == [(0, "SDE")]


def test_a_cut_off_reply_splits_the_batch_instead_of_failing(monkeypatch):
    import json
    calls = []

    def answer(system, user, **kw):
        calls.append(user.count("--- post"))
        if user.count("--- post") > 1:
            return '{"jobs": [{"post": 1, "is_j', "test:model"  # cut off mid-JSON
        return json.dumps({"jobs": [{"post": 1, "is_job": True, "title": "SDE", "company": "Acme"}]}), "test:model"

    monkeypatch.setattr(extract.llm, "answer", answer)
    found = extract.extract(["a", "b", "c"])
    assert [f["post"] for f in found] == [0, 1, 2] and calls[0] == 3
