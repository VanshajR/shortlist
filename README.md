# shortlist

Finds jobs worth applying to and helps you apply well. It's built for my own SDE / AI-engineer job hunt in India and is meant to work for anyone.

> Work in progress. Every six hours it pulls jobs from company job boards and Workday career sites, filters them, matches them to your experience and has a model judge the best ones. Each morning a Telegram bot sends the top few, with Applied / Later / Skip buttons. Tailored resumes and a web dashboard come next.

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
python -m shortlist.rank                                         # filter, score and judge
python -m shortlist.tailor --job <job id>                        # a one-page resume for that job (needs docker or pdflatex)
pytest
```

The Telegram bot: put `TELEGRAM_BOT_TOKEN` (from @BotFather) and a random `TELEGRAM_WEBHOOK_SECRET` in `.env`, deploy with `python scripts/deploy.py`, then run `python -m shortlist.bot link` and send the code it prints to your bot.

## Bring your own model

Pick models in `.env` as `provider:model`: OpenAI, Anthropic, Groq, Gemini, OpenRouter, a local Ollama, or any OpenAI-compatible endpoint. List several chat models and they're tried in order. The defaults run on free tiers; `ollama:nomic-embed-text` runs fully offline.

```bash
SHORTLIST_LLM=anthropic:claude-sonnet-5-5,ollama:llama3.2
SHORTLIST_EMBEDDINGS=ollama:nomic-embed-text
```

`python evals/retrieval.py` scores how well search finds the right experience for job-style queries, so you can compare embedding models before switching.

Companies to watch are in [`data/companies.toml`](data/companies.toml). Add one by putting its job-board slug under the right board. Profiles use the format of my [portfolio's data](https://vanshajraghuvanshi.dev/llms.txt): roles and projects with highlight bullets.

## Applying on Workday

[`extension/`](extension) is a Chrome extension that fills Workday applications from your saved details: personal and contact details, every work experience and education entry, websites, skills, your resume, and the questions every company asks in its own words (work authorisation, sponsorship, notice period, relocation and the rest). It points out what's left. When you answer a question it didn't know, it remembers that answer for the next company. It never submits; you look over each page and press Save and Continue yourself. See [extension/README.md](extension/README.md).

Why it's built this way: [docs/decisions.md](docs/decisions.md).
