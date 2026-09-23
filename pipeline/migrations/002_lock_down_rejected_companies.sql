-- rejected_companies was created without row level security, so Supabase's
-- Data API let the anon key read, insert, update and delete it. The dashboard
-- never reads it; only the pipeline (table owner, bypasses RLS) writes it.
alter table rejected_companies enable row level security;

-- Dashboard tables are select-only for anon: reset whatever Supabase's
-- default "expose new tables" privileges granted, then grant select back.
-- The anon/authenticated roles only exist on Supabase, so plain Postgres
-- (tests) skips this.
do $$
declare r text;
begin
    foreach r in array array['anon', 'authenticated'] loop
        if exists (select 1 from pg_roles where rolname = r) then
            execute format('revoke all on rejected_companies, pipeline_settings from %I', r);
            execute format('revoke all on companies, signals, scores, decisions, ranked_companies from %I', r);
        end if;
    end loop;
    if exists (select 1 from pg_roles where rolname = 'anon') then
        grant select on companies, signals, scores, decisions, ranked_companies to anon;
    end if;
end $$;
