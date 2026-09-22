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
