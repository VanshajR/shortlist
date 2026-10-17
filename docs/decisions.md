# Decisions

Short notes on why things are the way they are.

## Telegram first, not a web app
I check my phone more than any dashboard. A daily message with three buttons per job is the smallest interface that's actually usable. A web dashboard can come later for stats.

## Board APIs over scraping for the public version
Greenhouse, Lever and Ashby expose public JSON for every company that uses them. That's stable, legal and needs no keys. Scrapers for LinkedIn, Indeed and Naukri exist only in a gitignored `private_sources/` folder that I run from my own machine. They're never deployed, and anyone self-hosting this gets only the clean version.

## No auto-apply
Mass-applying gets accounts flagged and sends weak applications. The tool finds the jobs and drafts the material; I press the button.

## HF Space + a cron ping
A free Space sleeps when idle. A GitHub Actions job pings it every 3 hours, which keeps it awake, and the same ping triggers the fetch, so the cron doubles as the scheduler. The Space's disk is wiped on restart, so the database has to live outside it (Turso).

## Fetch once, rank per user
Jobs go into one shared pool, and each user's profile filters and ranks that pool. This keeps the free API limits workable as users grow.

## Location normalisation is its own module
"Gurgaon" vs "Gurugram", "Bangalore" vs "Bengaluru", "Delhi NCR" meaning five cities. Getting this wrong silently drops good jobs, so it has tests.
