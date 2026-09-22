-- Schema for the signal-based account prioritizer.
-- Run once in the Supabase SQL editor (or via psql $DATABASE_URL).

create table if not exists companies (
    id            bigint generated always as identity primary key,
    name          text not null,
    domain        text unique,               -- normalized: lowercase, no www/path
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

-- Latest run's ranking, for the dashboard.
create or replace view ranked_companies as
select s.company_id, s.score, s.explanation, s.rules_fired, s.run_date,
       c.name, c.domain, c.round, c.amount_raised, c.raised_date, c.first_seen
from scores s
join companies c on c.id = s.company_id
where s.run_date = (select max(run_date) from scores);

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
