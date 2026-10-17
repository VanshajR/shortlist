from datetime import datetime, timezone

from shortlist import db
from shortlist.models import Job
from shortlist.text import html_to_text


def job(external_id="1", title="Software Engineer", **kw):
    return Job(source="greenhouse", external_id=external_id, company="acme", title=title,
               url=f"https://example.com/{external_id}", **kw)


def test_new_jobs_are_counted_once_and_updates_refresh_them(conn):
    assert db.upsert_jobs(conn, [job("1"), job("2")]) == 2
    assert db.upsert_jobs(conn, [job("1", title="Software Engineer II"), job("3")]) == 1
    row = conn.execute("select title, first_seen < last_seen as refreshed from jobs where id = 'greenhouse:acme:1'").fetchone()
    assert row["title"] == "Software Engineer II" and row["refreshed"]


def test_cities_and_dates_round_trip(conn):
    posted = datetime(2026, 10, 1, tzinfo=timezone.utc)
    db.upsert_jobs(conn, [job(cities=["Gurugram", "Noida"], in_india=True, posted_at=posted)])
    row = conn.execute("select cities, in_india, posted_at from jobs").fetchone()
    assert row == {"cities": ["Gurugram", "Noida"], "in_india": True, "posted_at": posted}


def test_migrations_run_once(conn):
    assert db.migrate(conn) == []


def test_html_descriptions_become_readable_text():
    raw = ("<p>Build <strong>agents</strong>&nbsp;at scale.</p><h3>You have</h3>"
           "<ul><li><p>Python</p></li><li>2+ years</li></ul><script>track()</script>")
    assert html_to_text(raw) == "Build agents at scale.\nYou have\n- Python\n- 2+ years"


def test_plain_text_is_only_tidied():
    assert html_to_text("Python &amp; Go\n\n\n\nRemote") == "Python & Go\n\nRemote"
