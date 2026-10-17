"""Which model provider to use, chosen in .env as "provider:model".

    SHORTLIST_LLM=groq:qwen/qwen3.8-27b,gemini:gemini-flash-latest    # tried in order
    SHORTLIST_EMBEDDINGS=ollama:nomic-embed-text

Everything except Anthropic speaks the OpenAI API, so one client covers them;
Anthropic gets its own. Anything else OpenAI-compatible works through
"custom:<model>" with CUSTOM_BASE_URL (and CUSTOM_API_KEY if it needs one).
"""
import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Provider:
    name: str
    base_url: str
    key_env: str | None        # None: no key needed (a local Ollama)
    openai_compatible: bool = True

    @property
    def key(self) -> str | None:
        return os.environ.get(self.key_env) if self.key_env else None


def _ollama_url() -> str:
    host = os.environ.get("OLLAMA_HOST", "http://localhost:11434").rstrip("/")
    return host if host.startswith("http") else f"http://{host}"


def registry() -> dict[str, Provider]:
    return {
        "openai": Provider("openai", "https://api.openai.com/v1", "OPENAI_API_KEY"),
        "anthropic": Provider("anthropic", "https://api.anthropic.com/v1", "ANTHROPIC_API_KEY", openai_compatible=False),
        "groq": Provider("groq", "https://api.groq.com/openai/v1", "GROQ_API_KEY"),
        "gemini": Provider("gemini", "https://generativelanguage.googleapis.com/v1beta/openai", "GEMINI_API_KEY"),
        "openrouter": Provider("openrouter", "https://openrouter.ai/api/v1", "OPENROUTER_API_KEY"),
        "ollama": Provider("ollama", f"{_ollama_url()}/v1", None),
        "custom": Provider("custom", os.environ.get("CUSTOM_BASE_URL", "").rstrip("/"), "CUSTOM_API_KEY"),
    }


@dataclass(frozen=True)
class Choice:
    provider: Provider
    model: str

    @property
    def label(self) -> str:
        return f"{self.provider.name}:{self.model}"


def parse(spec: str, require_keys: bool = True) -> list[Choice]:
    """'groq:openai/gpt-oss-120b, ollama:llama3.2' -> choices, checked up front so a
    typo fails at startup instead of halfway through a run."""
    known = registry()
    choices = []
    for part in filter(None, (p.strip() for p in spec.split(","))):
        name, sep, model = part.partition(":")   # model names can contain ':' (ollama tags)
        if not sep or not model:
            raise SystemExit(f"{part!r}: expected provider:model, e.g. openai:gpt-4.1-mini")
        provider = known.get(name)
        if provider is None:
            raise SystemExit(f"{part!r}: unknown provider {name!r}; use one of {', '.join(known)}")
        if provider.name == "custom" and not provider.base_url:
            raise SystemExit("custom provider needs CUSTOM_BASE_URL")
        if require_keys and provider.key_env and not provider.key and provider.name != "custom":
            raise SystemExit(f"{part!r} needs {provider.key_env} in .env")
        choices.append(Choice(provider, model))
    if not choices:
        raise SystemExit("no model configured")
    return choices
