-- Remote jobs: who they're open to (see locations.remote_scope). Filled by the next fetch.
alter table jobs add column remote_scope text
    check (remote_scope in ('india', 'global', 'foreign', 'unclear'));

-- A user's ranked jobs. The semantic score comes from embeddings; fit, verdict and
-- reasons come from the LLM judge, which only sees the best few each run.
create table matches (
    user_id   bigint not null references users(id) on delete cascade,
    job_id    text not null references jobs(id) on delete cascade,
    semantic  real not null,                  -- 0-1: how close the job is to their best highlights
    fit       smallint check (fit between 0 and 10),
    verdict   text check (verdict in ('apply', 'maybe', 'skip')),
    reasons   jsonb not null default '{}',    -- why, gaps, years asked for, highlights it matched
    judged_by text,                           -- provider:model
    status    text not null default 'new' check (status in ('new', 'sent', 'applied', 'skipped', 'later')),
    ranked_at timestamptz not null default now(),
    primary key (user_id, job_id)
);
create index matches_for_digest on matches (user_id, status, fit desc);
