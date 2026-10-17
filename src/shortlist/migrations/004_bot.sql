-- Linking a Telegram chat to a user: the CLI makes a one-time code, /start <code> claims it.
alter table users add column link_code text unique;

-- Telegram buttons carry at most 64 bytes, and job ids run longer, so a match has a short handle.
alter table matches add column handle text generated always as (left(md5(job_id), 10)) stored;
create index matches_by_handle on matches (user_id, handle);
alter table matches add column sent_at timestamptz;

-- What the user did with a job, and what the judge had said: the raw material for
-- preferences ("not this company") and for growing the judge's eval set.
create table feedback (
    id      bigserial primary key,
    user_id bigint not null references users(id) on delete cascade,
    job_id  text not null references jobs(id) on delete cascade,
    action  text not null check (action in ('applied', 'later', 'skipped')),
    reason  text check (reason in ('senior', 'stack', 'company', 'role', 'location', 'other')),
    fit     smallint,
    verdict text,
    at      timestamptz not null default now()
);
create index feedback_by_user on feedback (user_id, at desc);
