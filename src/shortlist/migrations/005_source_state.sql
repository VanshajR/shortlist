-- Sources that read a stream (a Telegram channel, a monthly HN thread) remember how far
-- they got, so each run only reads, and pays a model to understand, what's new.
create table source_state (
    source     text primary key,      -- "telegram:getjobss"
    cursor     text not null,         -- the last post or comment handled
    updated_at timestamptz not null default now()
);
