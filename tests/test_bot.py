import pytest
from fastapi.testclient import TestClient

from shortlist import bot, db, digest, rank
from shortlist.models import Job

ME = 555


class FakeTelegram:
    """Records what the bot would have sent."""

    def __init__(self):
        self.sent, self.edits, self.answers = [], [], []

    def send(self, chat_id, text, buttons=None):
        self.sent.append({"chat": chat_id, "text": text, "buttons": buttons})
        return len(self.sent)

    def edit(self, chat_id, message_id, text, buttons=None):
        self.edits.append({"text": text, "buttons": buttons})

    def answer(self, callback_id, text=None):
        self.answers.append(text)


@pytest.fixture
def setup(conn):
    db.upsert_jobs(conn, [
        Job(source="workday", external_id="1", company="mastercard", title="Software Engineer I-1",
            url="https://x/1", cities=["Pune"], in_india=True),
        Job(source="workday", external_id="2", company="target", title="Engineer <Platform>",
            url="https://x/2", cities=["Bengaluru"], in_india=True),
    ])
    user = conn.execute("insert into users (name, telegram_id) values ('Vanshaj R', %s) returning *", (ME,)).fetchone()
    for job, fit, verdict in (("workday:mastercard:1", 8, "apply"), ("workday:target:2", 5, "maybe")):
        conn.execute("""insert into matches (user_id, job_id, semantic, fit, verdict, reasons)
                        values (%s, %s, 0.5, %s, %s, '{"why": "Fits.", "gaps": ["Go"]}')""", (user["id"], job, fit, verdict))
    return user, FakeTelegram()


def message(text, sender=ME):
    return {"message": {"text": text, "chat": {"id": sender}, "from": {"id": sender}}}


def tap(data, sender=ME):
    return {"callback_query": {"id": "q", "data": data, "from": {"id": sender},
                               "message": {"chat": {"id": sender}, "message_id": 1}}}


def handle_of(conn, job_id):
    return conn.execute("select handle from matches where job_id = %s", (job_id,)).fetchone()["handle"]


def test_digest_sends_the_best_first_and_marks_them_sent(conn, setup):
    user, tg = setup
    assert digest.send_digest(conn, tg, user) == 2
    assert tg.sent[0]["text"] == "2 new jobs worth a look."
    assert "Software Engineer I-1" in tg.sent[1]["text"] and "Fit 8/10" in tg.sent[1]["text"]
    assert "&lt;Platform&gt;" in tg.sent[2]["text"]  # titles are escaped for Telegram's HTML
    assert all(len(data.encode()) <= 64 for _, data in tg.sent[1]["buttons"][0])
    assert digest.send_digest(conn, tg, user) == 0  # nothing twice


def test_a_stranger_is_told_its_personal(conn, setup):
    _, tg = setup
    bot.handle(conn, tg, message("/today", sender=999))
    assert "personal bot" in tg.sent[0]["text"]


def test_linking_with_a_one_time_code(conn, setup):
    _, tg = setup
    conn.execute("insert into users (name, link_code) values ('Asha Rao', 'abc123')")
    bot.handle(conn, tg, message("/start abc123", sender=777))
    assert tg.sent[0]["text"].startswith("Linked, Asha.")
    bot.handle(conn, tg, message("/start abc123", sender=888))
    assert "didn't work" in tg.sent[1]["text"]


def test_skip_asks_why_and_not_this_company_blocks_it(conn, setup):
    user, tg = setup
    handle = handle_of(conn, "workday:mastercard:1")
    bot.handle(conn, tg, tap(f"s:{handle}"))
    assert "Why skip it?" in tg.edits[-1]["text"]
    bot.handle(conn, tg, tap(f"r:{handle}:company"))
    assert "won't see Mastercard again" in tg.edits[-1]["text"]
    row = conn.execute("select status from matches where job_id = 'workday:mastercard:1'").fetchone()
    feedback = conn.execute("select action, reason, fit, verdict from feedback").fetchone()
    prefs = conn.execute("select prefs from users where id = %s", (user["id"],)).fetchone()["prefs"]
    assert row["status"] == "skipped" and prefs["blocked"] == ["mastercard"]
    assert feedback == {"action": "skipped", "reason": "company", "fit": 8, "verdict": "apply"}


def test_applied_and_later(conn, setup):
    _, tg = setup
    bot.handle(conn, tg, tap(f"a:{handle_of(conn, 'workday:mastercard:1')}"))
    bot.handle(conn, tg, tap(f"l:{handle_of(conn, 'workday:target:2')}"))
    statuses = {r["job_id"]: r["status"] for r in conn.execute("select job_id, status from matches")}
    assert statuses == {"workday:mastercard:1": "applied", "workday:target:2": "later"}
    assert "Marked as applied" in tg.edits[0]["text"] and tg.edits[0]["buttons"] is None
    bot.handle(conn, tg, message("/today"))
    assert len(tg.sent) == 1 and "Engineer &lt;Platform&gt;" in tg.sent[0]["text"]  # later comes back, applied doesn't


def test_prefs_change_and_show(conn, setup):
    user, tg = setup
    bot.handle(conn, tg, message("/prefs years 1"))
    bot.handle(conn, tg, message("/prefs cities Pune, Noida"))
    assert "up to 1 year" in tg.sent[-1]["text"] and "Pune, Noida" in tg.sent[-1]["text"]
    bot.handle(conn, tg, message("/prefs anywhere Acme Labs"))
    assert "acme labs" in tg.sent[-1]["text"]
    bot.handle(conn, tg, message("/prefs volume 11"))
    assert "didn't follow" in tg.sent[-1]["text"]


def test_blocked_companies_leave_the_ranking(conn, setup):
    user, _ = setup
    conn.execute("update users set prefs = '{\"blocked\": [\"mastercard\"]}' where id = %s", (user["id"],))
    user = conn.execute("select * from users where id = %s", (user["id"],)).fetchone()
    conn.execute("insert into job_embeddings (job_id, text_hash, embedding) select id, 'x', array_fill(0.1, array[768])::vector from jobs")
    conn.execute("insert into highlights (user_id, id, kind, owner, text, text_hash, embedding) values (%s, 'h', 'project', 'p', 't', 'x', array_fill(0.1, array[768])::vector)", (user["id"],))
    pool, out = rank.shortlist_pool(conn, user)
    assert [r["company"] for r in pool] == ["target"] and out["blocked company"] == 1


def test_the_webhook_refuses_calls_without_telegrams_secret(monkeypatch):
    monkeypatch.setenv("TELEGRAM_WEBHOOK_SECRET", "s3cret")
    client = TestClient(bot.app)
    assert client.post("/telegram", json={}, headers={"X-Telegram-Bot-Api-Secret-Token": "wrong"}).status_code == 403
    assert client.post("/telegram", json={}).status_code == 403


def test_ranking_keeps_matches_whose_jobs_are_waiting_to_be_embedded(conn, setup):
    user, _ = setup  # two judged matches, and no job embeddings at all (the quota ran out)
    rank.save(conn, user["id"], [])
    assert conn.execute("select count(*) as n from matches").fetchone()["n"] == 2


def test_search_says_so_when_the_free_quota_is_out(conn, setup, monkeypatch):
    from shortlist import embeddings
    _, tg = setup
    calls = []

    def embed(texts, task=None, http=None, patient=True):
        calls.append(patient)
        raise embeddings.QuotaExhausted("per day")

    monkeypatch.setattr(embeddings, "embed", embed)
    bot.handle(conn, tg, message("/search backend pune"))
    assert calls == [False] and "out of free quota" in tg.sent[-1]["text"]


def test_reputable_companies_count_anywhere_in_india_unknown_ones_only_in_preferred_cities(conn, setup):
    user, _ = setup
    conn.execute("update users set prefs = '{\"cities\": [\"Pune\"]}' where id = %s", (user["id"],))
    user = conn.execute("select * from users where id = %s", (user["id"],)).fetchone()
    db.upsert_jobs(conn, [
        Job(source="telegram", external_id="a", company="Capgemini", title="Associate Software Engineer",
            url="https://x/a", cities=["Bengaluru"], in_india=True),
        Job(source="telegram", external_id="b", company="Tiny Startup", title="Software Engineer",
            url="https://x/b", cities=["Bengaluru"], in_india=True),
    ])
    conn.execute("insert into job_embeddings (job_id, text_hash, embedding) select id, 'x', array_fill(0.1, array[768])::vector from jobs")
    conn.execute("insert into highlights (user_id, id, kind, owner, text, text_hash, embedding) values (%s, 'h', 'project', 'p', 't', 'x', array_fill(0.1, array[768])::vector)", (user["id"],))
    pool, _ = rank.shortlist_pool(conn, user)
    companies = sorted(r["company"] for r in pool)
    # target is watched (workday) so Bengaluru is fine; Capgemini is reputable; the unknown startup isn't in Pune
    assert companies == ["Capgemini", "mastercard", "target"]
