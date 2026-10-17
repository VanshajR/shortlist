# shortlist

Finds jobs worth applying to and helps you apply well. It's built for my own SDE / AI-engineer job hunt in India and is meant to work for anyone.

> Work in progress. Today it pulls jobs from company job boards into Postgres every six hours. Ranking against your experience, a Telegram bot with a daily digest, tailored resumes and a web dashboard come next.

## Running it

```bash
python -m venv .venv
.venv/Scripts/activate        # Windows; use .venv/bin/activate elsewhere
pip install -e ".[dev]"

# a local Postgres with pgvector (Neon runs the real one)
docker run -d --name shortlist-pg -e POSTGRES_PASSWORD=dev -p 5433:5432 pgvector/pgvector:pg16
docker exec shortlist-pg psql -U postgres -c "create database shortlist_dev" -c "create database shortlist_test"

cp .env.example .env          # DATABASE_URL=postgresql://postgres:dev@localhost:5433/shortlist_dev
python -m shortlist.fetch     # pull jobs into the database
pytest
```

Companies to watch are in [`data/companies.toml`](data/companies.toml). Add one by putting its job-board slug under the right board.

Why it's built this way: [docs/decisions.md](docs/decisions.md).
