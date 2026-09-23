-- Articles whose outcome is final (became a company, not a funding story,
-- duplicate, out of window). The daily run skips these before fetching or
-- extracting, so an article in the 3-day lookback is paid for once, not three
-- times. Pipeline-only: closed to the anon role.
create table if not exists processed_articles (
    url        text primary key,           -- normalized, see fetch.normalize_url
    outcome    text not null,
    first_seen timestamptz not null default now()
);
alter table processed_articles enable row level security;

do $$
declare r text;
begin
    foreach r in array array['anon', 'authenticated'] loop
        if exists (select 1 from pg_roles where rolname = r) then
            execute format('revoke all on processed_articles from %I', r);
        end if;
    end loop;
end $$;
