-- Schema for the signal-based account prioritizer.
-- Run once in the Supabase SQL editor (or via psql $DATABASE_URL).

create table if not exists companies (
    id            bigint generated always as identity primary key,
    name          text not null,
    domain        text unique,               -- normalized: lowercase, no www/path
    domain_verified boolean not null default false,  -- homepage fetched, name confirmed
    excluded        boolean not null default false,  -- kept on record, hidden from the dashboard
    excluded_reason text,
    dedupe_key    text not null unique,      -- domain, or normalized name fallback
    round         text,
    amount_raised numeric,
    raised_date   date,
    first_seen    timestamptz not null default now()
);

create table if not exists signals (
    id           bigint generated always as identity primary key,
    company_id   bigint not null references companies(id) on delete cascade,
    signal_type  text not null,
    value        text not null,
    confidence   double precision not null,
    needs_review boolean not null default false,
    source_url   text,
    detected_at  timestamptz not null default now()
);
create index if not exists signals_company_idx on signals(company_id);

create table if not exists scores (
    id          bigint generated always as identity primary key,
    company_id  bigint not null references companies(id) on delete cascade,
    score       integer not null,
    explanation text,
    rules_fired jsonb not null default '[]',
    run_date    date not null,
    unique (company_id, run_date)          -- one row per company per run
);
create index if not exists scores_run_idx on scores(run_date);

create table if not exists decisions (
    id            bigint generated always as identity primary key,
    company_id    bigint not null references companies(id) on delete cascade,
    question      text not null,
    answer        text not null,
    confidence    double precision not null,
    action_chosen text,
    round         integer not null,
    created_at    timestamptz not null default now()
);
create index if not exists decisions_company_idx on decisions(company_id);

create table if not exists rejected_companies (
    id         bigint generated always as identity primary key,
    name       text not null,
    reason     text not null,
    confidence double precision not null,
    source_url text,
    run_date   date not null,
    rejected_at timestamptz not null default now()
);
create index if not exists rejected_run_idx on rejected_companies(run_date);

-- Added after the first run; safe to re-run.
alter table companies add column if not exists domain_verified boolean not null default false;
alter table companies add column if not exists excluded boolean not null default false;
alter table companies add column if not exists excluded_reason text;
alter table companies add column if not exists article_published_at date;
alter table companies add column if not exists source_url text;
alter table companies add column if not exists article_title text;
alter table companies add column if not exists funding_evidence text;

alter table rejected_companies add column if not exists company_id bigint;
alter table rejected_companies add column if not exists raised_date date;
alter table rejected_companies add column if not exists article_published_at date;
alter table rejected_companies add column if not exists details text;
alter table rejected_companies add column if not exists snapshot jsonb;
create unique index if not exists rejected_company_reason_run_idx
    on rejected_companies(company_id, reason, run_date);

create table if not exists pipeline_settings (
    singleton boolean primary key default true check (singleton),
    display_window_days integer not null check (display_window_days > 0),
    backfill_completed_at timestamptz,
    backfill_added_count integer
);
alter table pipeline_settings enable row level security;

-- Dashboard ranking: each company's most recent score. Companies are only
-- judged once (dedupe skips known ones on later runs), so filtering to the
-- latest run_date would drop everything from earlier days.
create or replace view ranked_companies as
select distinct on (s.company_id)
       s.company_id, s.score, s.explanation, s.rules_fired, s.run_date,
       c.name, c.domain, c.domain_verified, c.round, c.amount_raised,
       c.raised_date, c.first_seen
from scores s
join companies c on c.id = s.company_id
join pipeline_settings p on p.singleton
where c.raised_date >= current_date - p.display_window_days
  and c.raised_date <= current_date
  and c.article_published_at <= current_date
  and not c.excluded
order by s.company_id, s.run_date desc;

-- Read-only access for the dashboard via the anon key.
alter table companies enable row level security;
alter table signals enable row level security;
alter table scores enable row level security;
alter table decisions enable row level security;

drop policy if exists anon_read_companies on companies;
drop policy if exists anon_read_signals on signals;
drop policy if exists anon_read_scores on scores;
drop policy if exists anon_read_decisions on decisions;

create policy anon_read_companies on companies for select to anon using (true);
create policy anon_read_signals on signals for select to anon using (true);
create policy anon_read_scores on scores for select to anon using (true);
create policy anon_read_decisions on decisions for select to anon using (true);

-- Table privileges for the anon role (needed if "automatically expose new
-- tables" is disabled in Data API settings).
grant select on companies, signals, scores, decisions to anon;
grant select on ranked_companies to anon;

-- Anon lockdown for pipeline-only tables lives in migrations/002; run
-- `run_pipeline migrate` after this file.
