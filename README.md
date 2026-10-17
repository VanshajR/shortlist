# shortlist

Finds jobs worth applying to and helps you apply well. It's built for my own SDE / AI-engineer job hunt in India and works for anyone.

> Work in progress. Right now it pulls jobs from company job boards into a database. The Telegram bot, ranking and tailoring come next.

## Running it

```bash
python -m venv .venv
.venv/Scripts/activate        # Windows; use .venv/bin/activate elsewhere
pip install -e ".[dev]"

python -m shortlist.fetch     # pull jobs into data/shortlist.db
uvicorn shortlist.app:app     # API: GET /health, POST /fetch
pytest
```

Companies to watch are in [`data/companies.toml`](data/companies.toml). Add a company by putting its job-board slug under the right board.

Why it's built this way: [docs/decisions.md](docs/decisions.md).
