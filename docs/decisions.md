# Decisions

Short notes on why things are the way they are.

## Telegram for the daily loop, a web page for the rest
I check my phone more than any dashboard, so the daily part lives in Telegram: a morning message with Apply, Skip and Later on each job. Some things are clumsy in a chat, though: browsing every match, changing preferences, previewing a tailored resume. Those go on a small web dashboard that logs in with Telegram, so there's one identity and no passwords.

## Board APIs over scraping for the public version
Greenhouse, Lever and Ashby expose public JSON for every company that uses them. That's stable, legal and needs no keys. Scrapers for LinkedIn, Indeed and Naukri exist only in a gitignored `private_sources/` folder that I run from my own machine. They're never deployed, and anyone self-hosting this gets only the clean version.

## No auto-apply
Mass-applying gets accounts flagged and sends weak applications. The tool finds the jobs and drafts the material; I press the button.

## GitHub Actions as the scheduler, nothing kept awake
Fetching and ranking are batch jobs, so a scheduled workflow runs them directly every six hours and exits. The bot and dashboard are a serverless function that wakes per request. Nothing needs a keep-alive ping, and every piece uses its free tier the way it's meant to be used.

## Postgres with pgvector, on Neon
Jobs, users, feedback and embeddings live in one database, so "jobs in NCR, posted this week, closest to my experience" is a single query instead of a join across two services. Locally and in CI it's the same image in a container, and the tests run against a real database rather than a mock.

## Fetch once, rank per user
Jobs go into one shared pool, and each user's profile filters and ranks that pool. This keeps the free API limits workable as users grow.

## Location normalisation is its own module
"Gurgaon" vs "Gurugram", "Bangalore" vs "Bengaluru", "Delhi NCR" meaning five cities. Getting this wrong silently drops good jobs, so it has tests.

## Descriptions are stored as plain text
Boards send HTML. Filters, embeddings, the LLM and Telegram all want text, so it's converted once at fetch time, keeping bullet points as "- " lines.
