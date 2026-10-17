-- Jobs are one shared pool; each user's profile filters and ranks it.
create extension if not exists vector;

create table jobs (
    id           text primary key,             -- source:company:external_id
    source       text not null,
    company      text not null,
    title        text not null,
    url          text not null,
    location_raw text not null default '',
    cities       text[] not null default '{}',
    remote       boolean not null default false,
    in_india     boolean not null default false,
    description  text not null default '',     -- plain text, HTML stripped at fetch
    posted_at    timestamptz,
    first_seen   timestamptz not null default now(),
    last_seen    timestamptz not null default now()
);
create index jobs_last_seen on jobs (last_seen);
create index jobs_in_india on jobs (in_india) where in_india;

create table users (
    id          bigserial primary key,
    name        text not null,
    telegram_id bigint unique,
    profile_url text,                           -- a profile.json in the portfolio's data format
    prefs       jsonb not null default '{}',
    created_at  timestamptz not null default now()
);
