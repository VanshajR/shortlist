"""Text to vectors with whichever embedding model is configured (SHORTLIST_EMBEDDINGS).

    gemini:gemini-embedding-001   free tier, the default
    openai:text-embedding-3-small
    ollama:nomic-embed-text       local and free

Every vector is 768 numbers, which is what the database stores. Gemini and OpenAI
are asked for 768; with Ollama, pick a model that produces 768 (nomic-embed-text
does). The provider and model are part of each text's hash, so switching models
re-embeds everything instead of mixing vectors from two models.
"""
import hashlib
import math
import os
import re
import time

import httpx

from .providers import Choice, parse

DEFAULT = "gemini:gemini-embedding-001"
DIMS = 768
BATCH = 100
BATCH_CHARS = 40_000  # ~10k tokens per call
# Gemini's free tier allows about 30k tokens a minute. Sending more and backing off
# on 429 stalled for minutes at a time, so its requests are paced to stay under it.
GEMINI_TOKENS_PER_MINUTE = 25_000

# a stored thing (a job, a highlight) vs a question someone types; only Gemini uses this
DOCUMENT, QUERY = "RETRIEVAL_DOCUMENT", "RETRIEVAL_QUERY"


def model(require_key: bool = True) -> Choice:
    [choice] = parse(os.environ.get("SHORTLIST_EMBEDDINGS", DEFAULT), require_key)[:1]
    return choice


def text_hash(text: str) -> str:
    # only the model's name matters here, so no key is needed to check what's changed
    return hashlib.sha1(f"{model(require_key=False).label}:{DIMS}:{text}".encode()).hexdigest()


def embed(texts: list[str], task: str = DOCUMENT, http: httpx.Client | None = None) -> list[list[float]]:
    """One normalised vector per text, in order."""
    choice = model()
    client = http or httpx.Client(timeout=120)
    vectors: list[list[float]] = []
    try:
        for chunk in _batches([t[:8000] for t in texts]):
            if choice.provider.name == "gemini":
                _pace(sum(len(t) for t in chunk) // 4 + 1)  # ~4 characters a token
                got = _gemini(client, choice, chunk, task)
            elif choice.provider.openai_compatible:
                got = _openai(client, choice, chunk)
            else:
                raise SystemExit(f"{choice.provider.name} has no embedding API; use gemini, openai or ollama")
            for vector in got:
                if len(vector) != DIMS:
                    raise SystemExit(f"{choice.label} gives {len(vector)}-number vectors; the database stores "
                                     f"{DIMS}. Pick a {DIMS}-dimension model (e.g. ollama:nomic-embed-text).")
            vectors += [_normalise(v) for v in got]
    finally:
        if http is None:
            client.close()
    return vectors


def _gemini(client, choice, chunk, task):
    # the native API, for task types; the key goes in a header so it never shows up in errors or logs
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{choice.model}:batchEmbedContents"
    body = {"requests": [{"model": f"models/{choice.model}", "content": {"parts": [{"text": t}]},
                          "taskType": task, "outputDimensionality": DIMS} for t in chunk]}
    r = _post(client, url, {"x-goog-api-key": choice.provider.key}, body)
    return [e["values"] for e in r["embeddings"]]


def _openai(client, choice, chunk):
    headers = {"Authorization": f"Bearer {choice.provider.key}"} if choice.provider.key else {}
    body = {"model": choice.model, "input": chunk}
    if choice.provider.name == "openai":
        body["dimensions"] = DIMS
    r = _post(client, f"{choice.provider.base_url}/embeddings", headers, body)
    return [d["embedding"] for d in sorted(r["data"], key=lambda d: d["index"])]


def _post(client, url, headers, body) -> dict:
    for attempt in range(6):
        r = client.post(url, headers=headers, json=body)
        if r.status_code == 429 and attempt < 5:
            time.sleep(min(_retry_delay(r), 90))
            continue
        if r.status_code != 200:
            raise RuntimeError(f"embedding failed: {r.status_code} {r.text[:300]}")
        return r.json()
    raise RuntimeError("embedding rate limited")


def _retry_delay(response: httpx.Response) -> float:
    match = re.search(r'"retryDelay":\s*"([\d.]+)s"', response.text)
    if match:
        return float(match.group(1))
    return float(response.headers.get("retry-after", 20))


def _normalise(vector: list[float]) -> list[float]:
    norm = math.sqrt(sum(v * v for v in vector)) or 1.0
    return [v / norm for v in vector]


_sent: list[tuple[float, int]] = []  # (when, estimated tokens) over the last minute


def _pace(tokens: int) -> None:
    """Sleep until sending `tokens` more keeps the last minute under Gemini's budget."""
    while True:
        now = time.monotonic()
        _sent[:] = [(t, n) for t, n in _sent if now - t < 60]
        if not _sent or sum(n for _, n in _sent) + tokens <= GEMINI_TOKENS_PER_MINUTE:
            _sent.append((now, tokens))
            return
        time.sleep(60 - (now - _sent[0][0]) + 0.5)


def _batches(texts: list[str]):
    chunk, size = [], 0
    for text in texts:
        if chunk and (len(chunk) == BATCH or size + len(text) > BATCH_CHARS):
            yield chunk
            chunk, size = [], 0
        chunk.append(text)
        size += len(text)
    if chunk:
        yield chunk
