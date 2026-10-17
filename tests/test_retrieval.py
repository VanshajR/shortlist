import hashlib

import pytest

from shortlist import embeddings, profile, retrieve

PROFILE = {
    "experience": [{
        "id": "dxfactor", "org": "DXFactor", "role": "SWE Intern", "start": "2026-02", "end": "2026-06",
        "summary": "Worked on AI agents and infrastructure.",
        "highlights": [{"id": "rag", "text": "Built a RAG platform over **5,000+ documents**.", "tags": ["rag"]}],
    }],
    "projects": [
        {"slug": "poll", "name": "Intervue Poll", "tier": "side", "summary": "A real time polling system.", "highlights": []},
        {"slug": "empty", "name": "Empty", "tier": "archive", "summary": "", "highlights": []},
    ],
}


def test_highlights_cover_bullets_and_summaries_without_markdown():
    found = {h["id"]: h for h in profile.highlights_from(PROFILE)}
    assert set(found) == {"experience:dxfactor:summary", "experience:dxfactor:rag", "project:poll:summary"}
    assert found["experience:dxfactor:rag"]["text"] == "Built a RAG platform over 5,000+ documents."


def fake_vector(text: str) -> list[float]:
    """Deterministic stand-in for a real embedding: texts sharing words point the same way."""
    vector = [0.0] * embeddings.DIMS
    for word in text.lower().replace(":", " ").replace(".", " ").split():
        vector[int(hashlib.md5(word.encode()).hexdigest(), 16) % embeddings.DIMS] += 1.0
    return vector


@pytest.fixture
def fake_embeddings(monkeypatch):
    calls = []

    def embed(texts, task=embeddings.DOCUMENT, http=None):
        calls.append(len(texts))
        return [fake_vector(t) for t in texts]

    monkeypatch.setattr(embeddings, "embed", embed)
    return calls


def test_sync_embeds_only_what_changed(conn, fake_embeddings):
    user = conn.execute("insert into users (name) values ('me') returning id").fetchone()["id"]
    assert profile.sync(conn, user, PROFILE) == {"highlights": 3, "embedded": 3, "removed": 0}
    assert profile.sync(conn, user, PROFILE) == {"highlights": 3, "embedded": 0, "removed": 0}

    edited = {**PROFILE, "projects": [{**PROFILE["projects"][0], "summary": "A live polling system."}]}
    assert profile.sync(conn, user, edited) == {"highlights": 3, "embedded": 1, "removed": 0}
    assert fake_embeddings == [3, 1]


def test_search_finds_the_closest_highlight(conn, fake_embeddings):
    user = conn.execute("insert into users (name) values ('me') returning id").fetchone()["id"]
    profile.sync(conn, user, PROFILE)
    [top, *_] = retrieve.search(conn, user, "real time polling")
    assert top["id"] == "project:poll:summary" and top["score"] > 0.3


def test_indexing_stops_cleanly_when_the_quota_runs_out(conn, monkeypatch):
    from shortlist import db
    from shortlist.models import Job
    jobs = [Job(source="greenhouse", external_id=str(i), company="acme", title="Backend Engineer",
                url=f"https://x/{i}", in_india=True, description="Python APIs") for i in range(120)]
    db.upsert_jobs(conn, jobs)
    calls = []

    def embed(texts, task=embeddings.DOCUMENT, http=None):
        calls.append(len(texts))
        if len(calls) > 1:
            raise embeddings.QuotaExhausted("EmbedContentRequestsPerDay")
        return [fake_vector(t) for t in texts]

    monkeypatch.setattr(embeddings, "embed", embed)
    result = retrieve.index_jobs(conn)
    assert result == {"candidates": 120, "embedded": 50, "left": 70, "stopped": "EmbedContentRequestsPerDay"}
    assert conn.execute("select count(*) as n from job_embeddings").fetchone()["n"] == 50
