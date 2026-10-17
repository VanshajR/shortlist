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

## Bring your own model
Anyone running this should be able to use the keys they already have, so models are picked in `.env` as `provider:model`. OpenAI, Groq, Gemini, OpenRouter and Ollama all speak the OpenAI API, so one small client covers them; Anthropic has a second one. Chat models are tried in order, which also makes a free-tier rate limit a non-event. Embeddings are fixed at 768 numbers, which every supported embedding model can produce, and the model's name is part of each text's hash, so switching models re-embeds rather than comparing vectors from two different models.

## Search over highlights, not whole resumes
A resume is many claims, and a job cares about a few of them. Each highlight bullet (plus a summary per role and project, since many side projects have no bullets) is embedded on its own, so a job can be matched to the specific things that fit it. Tailoring reuses this: the bullets that rank highest for a job are the ones a tailored resume leads with. On 16 job-style queries Gemini's embeddings put an expected highlight in the top five every time (MRR 0.97); a local nomic-embed-text got 14 of 16.

## Gemini embeddings are paced, not retried
The free tier allows about 30k tokens a minute. Sending big batches and backing off on errors stalled for minutes, so requests are sized and spaced to stay under the limit.

## The judge is checked against a person, not just tested
`evals/judge_labels.json` holds 20 jobs that passed the filters, rated by me (would apply, maybe, no) before seeing the model's scores, with the posting text kept so the set outlives the postings. `evals/judge.py` runs them through the real filters and judge. The first version agreed with me on 15 of 20 and never said "maybe": every job it liked I'd have considered, but it hid three I'd have applied to or considered. My notes on the "no"s were mostly the same few reasons (wanted 2+ years; SRE, DevOps or data engineering; ML research), so those became preferences (`max_years`, `also_off_track`, `avoid`) rather than prompt tweaks, and "a stretch worth trying" became a 5-6 maybe. After that: 16 of 20, 5 of the 7 I'd consider shown, nothing shown I'd skip. Those numbers are on the same 20 jobs the changes came from, so they're optimistic; ratings from the bot's buttons will grow the set.
