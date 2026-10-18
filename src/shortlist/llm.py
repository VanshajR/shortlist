"""Chat with whichever model is configured (SHORTLIST_LLM), falling back down the
list when one is rate limited or down. Ranking and tailoring want JSON back,
so `ask_json` asks for it and parses it, whatever the provider.
"""
import json
import os
import re
import time

import httpx

from .providers import Choice, parse

# Qwen first, not gpt-oss-120b: free tiers limit each model separately, and my site's chatbot
# (Axiom) answers with gpt-oss-120b on the same key, so batch judging stays off its budget.
DEFAULT = "groq:qwen/qwen3.8-27b,gemini:gemini-flash-latest"  # the alias never retires, unlike 2.5-flash did


class ModelError(RuntimeError):
    pass


def models(setting: str = "SHORTLIST_LLM", default: str = DEFAULT) -> list[Choice]:
    return parse(os.environ.get(setting, default))


def ask(system: str, user: str, **kw) -> str:
    return answer(system, user, **kw)[0]


def ask_json(system: str, user: str, **kw) -> dict:
    return parse_json(ask(system, user, json_mode=True, **kw))


def answer(system: str, user: str, *, json_mode: bool = False, max_tokens: int = 1500,
           http: httpx.Client | None = None, setting: str = "SHORTLIST_LLM", default: str = DEFAULT,
           effort: str | None = None) -> tuple[str, str]:
    """(reply, which model gave it). The first model in `setting` that answers wins."""
    chain = models(setting, default)
    client = http or httpx.Client(timeout=90)
    errors = []
    try:
        for choice in chain:
            try:
                if choice.provider.openai_compatible:
                    return _openai(client, choice, system, user, json_mode, max_tokens, effort), choice.label
                return _anthropic(client, choice, system, user, json_mode, max_tokens), choice.label
            except (httpx.HTTPError, ModelError) as e:
                errors.append(f"{choice.label}: {e}")
    finally:
        if http is None:
            client.close()
    raise ModelError("no model answered:\n  " + "\n  ".join(errors))


def parse_json(text: str) -> dict:
    """Models wrap JSON in code fences or a sentence now and then; take the object."""
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip())
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, re.S)
        if not match:
            raise ModelError(f"expected JSON, got: {text[:200]}") from None
        return json.loads(match.group(0))


def _post(client: httpx.Client, url: str, headers: dict, body: dict) -> dict:
    for attempt in range(3):
        r = client.post(url, headers=headers, json=body)
        if r.status_code == 429 and attempt < 2:
            time.sleep(min(float(r.headers.get("retry-after", 5)), 20))
            continue
        if r.status_code != 200:
            raise ModelError(f"{r.status_code} {r.text[:200]}")
        return r.json()
    raise ModelError("rate limited")


def _openai(client, choice: Choice, system, user, json_mode, max_tokens, effort=None) -> str:
    headers = {"Authorization": f"Bearer {choice.provider.key}"} if choice.provider.key else {}
    body = {"model": choice.model, "max_tokens": max_tokens, "temperature": 0.2,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]}
    if effort and choice.provider.name in ("openai", "groq", "gemini"):
        # reasoning models spend max_tokens on thinking first; a simple task needs little
        body["reasoning_effort"] = effort
    if json_mode:
        body["response_format"] = {"type": "json_object"}
    data = _post(client, f"{choice.provider.base_url}/chat/completions", headers, body)
    content = data["choices"][0]["message"].get("content")
    if not content:
        raise ModelError("empty reply")
    return content


def _anthropic(client, choice: Choice, system, user, json_mode, max_tokens) -> str:
    if json_mode:
        system += "\n\nReply with a single JSON object and nothing else."
    headers = {"x-api-key": choice.provider.key, "anthropic-version": "2023-06-01"}
    body = {"model": choice.model, "max_tokens": max_tokens, "temperature": 0.2, "system": system,
            "messages": [{"role": "user", "content": user}]}
    data = _post(client, f"{choice.provider.base_url}/messages", headers, body)
    text = "".join(block.get("text", "") for block in data.get("content", []) if block.get("type") == "text")
    if not text:
        raise ModelError("empty reply")
    return text
