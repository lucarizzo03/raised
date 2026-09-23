-- Heartbeat: when the last successful daily run finished. pipeline_settings
-- stays closed to anon; this view exposes only the timestamp so the dashboard
-- can tell "no new companies" apart from "the pipeline stopped running".
alter table pipeline_settings add column if not exists last_run_completed_at timestamptz;

create or replace view pipeline_status as
select last_run_completed_at from pipeline_settings where singleton;

-- Supabase's default privileges grant anon ALL on new views, and this view
-- is auto-updatable (writes run as the owner, bypassing RLS). Select only.
do $$
begin
    if exists (select 1 from pg_roles where rolname = 'anon') then
        revoke all on pipeline_status from anon;
        grant select on pipeline_status to anon;
    end if;
    if exists (select 1 from pg_roles where rolname = 'authenticated') then
        revoke all on pipeline_status from authenticated;
    end if;
end $$;
