import json

import httpx
import pytest

from shortlist import embeddings, llm, providers


@pytest.fixture(autouse=True)
def keys(monkeypatch):
    for name in ("OPENAI_API_KEY", "ANTHROPIC_API_KEY", "GROQ_API_KEY", "GEMINI_API_KEY"):
        monkeypatch.setenv(name, f"test-{name}")


def fake(handler):
    """An httpx client whose requests go to `handler` and get recorded."""
    seen = []

    def record(request):
        seen.append(request)
        return handler(request)

    return httpx.Client(transport=httpx.MockTransport(record)), seen


def openai_reply(text):
    return httpx.Response(200, json={"choices": [{"message": {"content": text}}]})


def test_specs_keep_model_names_that_contain_colons():
    [choice] = providers.parse("ollama:qwen3:8b")
    assert (choice.provider.name, choice.model) == ("ollama", "qwen3:8b")


@pytest.mark.parametrize("spec, problem", [
    ("gpt-4.1", "expected provider:model"),
    ("mystery:model", "unknown provider"),
])
def test_bad_specs_fail_with_a_clear_message(spec, problem):
    with pytest.raises(SystemExit, match=problem):
        providers.parse(spec)


def test_a_provider_without_its_key_is_reported(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY")
    with pytest.raises(SystemExit, match="OPENAI_API_KEY"):
        providers.parse("openai:gpt-4.1-mini")


def test_openai_compatible_providers_get_a_standard_request(monkeypatch):
    monkeypatch.setenv("SHORTLIST_LLM", "openai:gpt-4.1-mini")
    client, seen = fake(lambda r: openai_reply('{"score": 7}'))
    assert llm.ask_json("judge", "job text", http=client) == {"score": 7}
    request = seen[0]
    body = json.loads(request.content)
    assert str(request.url) == "https://api.openai.com/v1/chat/completions"
    assert request.headers["authorization"] == "Bearer test-OPENAI_API_KEY"
    assert body["response_format"] == {"type": "json_object"} and body["messages"][0]["role"] == "system"


def test_ollama_needs_no_key(monkeypatch):
    monkeypatch.setenv("SHORTLIST_LLM", "ollama:llama3.2")
    client, seen = fake(lambda r: openai_reply("hi"))
    assert llm.ask("s", "u", http=client) == "hi"
    assert str(seen[0].url) == "http://localhost:11434/v1/chat/completions"
    assert "authorization" not in seen[0].headers


def test_anthropic_uses_its_own_api(monkeypatch):
    monkeypatch.setenv("SHORTLIST_LLM", "anthropic:claude-sonnet-5-5")
    client, seen = fake(lambda r: httpx.Response(200, json={"content": [{"type": "text", "text": '```json\n{"ok": true}\n```'}]}))
    assert llm.ask_json("judge", "job", http=client) == {"ok": True}
    request = seen[0]
    body = json.loads(request.content)
    assert str(request.url) == "https://api.anthropic.com/v1/messages"
    assert request.headers["x-api-key"] == "test-ANTHROPIC_API_KEY" and "anthropic-version" in request.headers
    assert body["system"].startswith("judge") and "JSON" in body["system"]


def test_falls_back_to_the_next_model(monkeypatch):
    monkeypatch.setenv("SHORTLIST_LLM", "groq:openai/gpt-oss-120b,gemini:gemini-2.5-flash")
    client, seen = fake(lambda r: httpx.Response(503, text="busy") if "groq" in str(r.url) else openai_reply("from gemini"))
    assert llm.ask("s", "u", http=client) == "from gemini"
    assert [r.url.host for r in seen] == ["api.groq.com", "generativelanguage.googleapis.com"]


def test_every_model_failing_says_why(monkeypatch):
    monkeypatch.setenv("SHORTLIST_LLM", "groq:a,openai:b")
    client, _ = fake(lambda r: httpx.Response(500, text="down"))
    with pytest.raises(llm.ModelError, match="groq:a: 500"):
        llm.ask("s", "u", http=client)


def test_openai_embeddings_ask_for_768_numbers(monkeypatch):
    monkeypatch.setenv("SHORTLIST_EMBEDDINGS", "openai:text-embedding-3-small")
    client, seen = fake(lambda r: httpx.Response(200, json={"data": [
        {"index": 1, "embedding": [0.0, 2.0] + [0.0] * 766},
        {"index": 0, "embedding": [3.0] + [0.0] * 767},
    ]}))
    first, second = embeddings.embed(["a", "b"], http=client)
    assert json.loads(seen[0].content)["dimensions"] == 768
    assert first[0] == pytest.approx(1.0) and second[1] == pytest.approx(1.0)  # in order, normalised


def test_a_model_with_the_wrong_size_is_refused(monkeypatch):
    monkeypatch.setenv("SHORTLIST_EMBEDDINGS", "ollama:mxbai-embed-large")
    client, _ = fake(lambda r: httpx.Response(200, json={"data": [{"index": 0, "embedding": [0.1] * 1024}]}))
    with pytest.raises(SystemExit, match="1024"):
        embeddings.embed(["a"], http=client)


def test_switching_embedding_models_changes_every_hash(monkeypatch):
    monkeypatch.setenv("SHORTLIST_EMBEDDINGS", "gemini:gemini-embedding-001")
    before = embeddings.text_hash("same text")
    monkeypatch.setenv("SHORTLIST_EMBEDDINGS", "ollama:nomic-embed-text")
    assert embeddings.text_hash("same text") != before


def test_gemini_key_travels_in_a_header_not_the_url(monkeypatch):
    monkeypatch.setenv("SHORTLIST_EMBEDDINGS", "gemini:gemini-embedding-001")
    client, seen = fake(lambda r: httpx.Response(200, json={"embeddings": [{"values": [1.0] + [0.0] * 767}]}))
    embeddings.embed(["a"], http=client)
    assert "key=" not in str(seen[0].url) and seen[0].headers["x-goog-api-key"] == "test-GEMINI_API_KEY"


def test_an_impatient_caller_gets_the_rate_limit_at_once(monkeypatch):
    monkeypatch.setenv("SHORTLIST_EMBEDDINGS", "gemini:gemini-embedding-001")
    client, seen = fake(lambda r: httpx.Response(429, json={"error": {"details": [{"retryDelay": "30s"}]}}))
    with pytest.raises(embeddings.QuotaExhausted):
        embeddings.embed(["a"], http=client, patient=False)
    assert len(seen) == 1  # no retries, no 30-second sleep
