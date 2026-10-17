from shortlist.sources.bigtech import _google_job
from shortlist.sources.hn import OPEN_TO_INDIA
from shortlist.sources.ycombinator import OPEN_TO_INDIA as YC_OPEN


def test_a_google_results_row_becomes_a_job():
    row = ["123", "Software Engineer II, AI/ML", "https://x", [None, "<ul><li>Build models</li></ul>"],
           [None, "<p>Bachelor's degree or equivalent practical experience.</p>"], "tenant", None, "Google", "en-US",
           [["Hyderabad, Telangana, India", ["addr"], "Hyderabad"]], [None, "<p>About the team</p>"], [2],
           [1791821336, 0], None, None, None, None, None, None, [None, "<p>1 year of experience with Python</p>"], 1]
    job = _google_job(row)
    assert job.external_id == "123" and job.location_raw == "Hyderabad, Telangana, India"
    assert job.url.endswith("/jobs/results/123")
    assert "1 year of experience" in job.description and "About the team" in job.description
    assert job.posted_at.year == 2026


def test_hn_and_yc_only_send_india_or_worldwide_posts_onwards():
    assert OPEN_TO_INDIA.search("Acme | Backend | REMOTE (Worldwide)")
    assert OPEN_TO_INDIA.search("Acme | SDE | Bengaluru, India | Full-time")
    assert not OPEN_TO_INDIA.search("Acme | SWE | San Francisco | ONSITE")
    assert YC_OPEN.search("IN / Remote (IN)") and YC_OPEN.search("Remote")
    assert not YC_OPEN.search("New York, NY, US / Remote (US)")
