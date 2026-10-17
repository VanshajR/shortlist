# shortlist

Finds jobs worth applying to and helps you apply well. It's built for my own SDE / AI-engineer job hunt in India and is meant to work for anyone.

> Work in progress. Today it pulls jobs from company job boards every six hours and matches them against your experience with semantic search. Ranking, a Telegram bot with a daily digest, tailored resumes and a web dashboard come next.

## Running it

```bash
python -m venv .venv
.venv/Scripts/activate        # Windows; use .venv/bin/activate elsewhere
pip install -e ".[dev]"

# a local Postgres with pgvector (Neon runs the real one)
docker run -d --name shortlist-pg -e POSTGRES_PASSWORD=dev -p 5433:5432 pgvector/pgvector:pg16
docker exec shortlist-pg psql -U postgres -c "create database shortlist_dev" -c "create database shortlist_test"

cp .env.example .env          # DATABASE_URL=postgresql://postgres:dev@localhost:5433/shortlist_dev
python -m shortlist.fetch                                         # pull jobs
python -m shortlist.profile --name "You" --url https://you.dev/profile.json
python -m shortlist.retrieve index                                # embed jobs worth matching
python -m shortlist.retrieve search "real-time systems"           # your closest experience
pytest
```

## Bring your own model

Pick models in `.env` as `provider:model`: OpenAI, Anthropic, Groq, Gemini, OpenRouter, a local Ollama, or any OpenAI-compatible endpoint. List several chat models and they're tried in order. The defaults run on free tiers; `ollama:nomic-embed-text` runs fully offline.

```bash
SHORTLIST_LLM=anthropic:claude-sonnet-5-5,ollama:llama3.2
SHORTLIST_EMBEDDINGS=ollama:nomic-embed-text
```

`python evals/retrieval.py` scores how well search finds the right experience for job-style queries, so you can compare embedding models before switching.

Companies to watch are in [`data/companies.toml`](data/companies.toml). Add one by putting its job-board slug under the right board. Profiles use the format of my [portfolio's data](https://vanshajraghuvanshi.dev/llms.txt): roles and projects with highlight bullets.

Why it's built this way: [docs/decisions.md](docs/decisions.md).
