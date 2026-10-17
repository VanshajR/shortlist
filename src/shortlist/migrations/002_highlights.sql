-- What a user has done, in pieces small enough to match against a job: every
-- highlight bullet from their profile, plus one summary per role and project
-- (plenty of side projects have a summary but no bullets).
create table highlights (
    user_id   bigint not null references users(id) on delete cascade,
    id        text not null,                -- "project:depthpad:analog", "experience:dxfactor:summary"
    kind      text not null check (kind in ('experience', 'project')),
    owner     text not null,                -- the org or project it belongs to
    text      text not null,
    tags      text[] not null default '{}',
    meta      jsonb not null default '{}',  -- tier, dates, tech, links
    text_hash text not null,                -- re-embed only when the text changes
    embedding vector(768),
    primary key (user_id, id)
);

-- Only plausible jobs get embedded (India or remote, engineering titles), to stay
-- inside the free embedding quota.
create table job_embeddings (
    job_id      text primary key references jobs(id) on delete cascade,
    text_hash   text not null,
    embedding   vector(768) not null,
    embedded_at timestamptz not null default now()
);
create index job_embeddings_hnsw on job_embeddings using hnsw (embedding vector_cosine_ops);
