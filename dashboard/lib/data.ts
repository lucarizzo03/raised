import { createClient, type SupabaseClient } from "@supabase/supabase-js";

import { toCompanies } from "./map";
import { sampleCompanies } from "./sample-data";
import type { Company, DecisionRow, RankedCompanyRow, SignalRow } from "./types";

export type DashboardData = {
  companies: Company[];
  lastUpdated: string | null;
  /** When the last daily run finished; null if unknown. */
  lastRunAt: string | null;
  isSampleData: boolean;
};

const PAGE = 1000;
// Company ids per `in (...)` filter; keeps the request URL well under limits.
const ID_CHUNK = 150;

type Filter = { column: string; ids: number[] };

/**
 * PostgREST caps a response at 1000 rows, so every read is paged. signals and
 * decisions only ever grow, so they are filtered to the displayed companies
 * instead of being read in full on every request.
 */
async function fetchAll<T>(
  supabase: SupabaseClient,
  table: string,
  order: string,
  filter?: Filter
): Promise<T[]> {
  const out: T[] = [];
  for (let from = 0; ; from += PAGE) {
    let query = supabase.from(table).select("*");
    if (filter) query = query.in(filter.column, filter.ids);
    const { data, error } = await query
      .order(order)
      .range(from, from + PAGE - 1);
    if (error) throw new Error(`${table}: ${error.message}`);
    const rows = (data ?? []) as T[];
    out.push(...rows);
    if (rows.length < PAGE) return out;
  }
}

async function fetchForCompanies<T>(
  supabase: SupabaseClient,
  table: string,
  ids: number[]
): Promise<T[]> {
  const chunks: number[][] = [];
  for (let i = 0; i < ids.length; i += ID_CHUNK) chunks.push(ids.slice(i, i + ID_CHUNK));
  const pages = await Promise.all(
    chunks.map((chunk) =>
      fetchAll<T>(supabase, table, "id", { column: "company_id", ids: chunk })
    )
  );
  return pages.flat();
}

async function latestSignalTime(supabase: SupabaseClient): Promise<string | null> {
  const { data, error } = await supabase
    .from("signals")
    .select("detected_at")
    .order("detected_at", { ascending: false })
    .limit(1);
  if (error) throw new Error(`signals: ${error.message}`);
  return (data?.[0]?.detected_at as string | undefined) ?? null;
}

/** Heartbeat from the pipeline. Optional: a missing view never breaks the page. */
async function lastRunTime(supabase: SupabaseClient): Promise<string | null> {
  const { data, error } = await supabase.from("pipeline_status").select("last_run_completed_at").limit(1);
  if (error) {
    console.warn("pipeline_status unavailable:", error.message);
    return null;
  }
  return (data?.[0]?.last_run_completed_at as string | null | undefined) ?? null;
}

export async function fetchDashboardData(): Promise<DashboardData> {
  // Server-only env vars (no NEXT_PUBLIC_ prefix): read in a server
  // component, so they are never bundled into client-side JS.
  const url = process.env.SUPABASE_URL;
  const key = process.env.SUPABASE_ANON_KEY;

  if (!url || !key) {
    return { companies: sampleCompanies, lastUpdated: null, lastRunAt: null, isSampleData: true };
  }

  const supabase = createClient(url, key, { auth: { persistSession: false } });
  try {
    const [companies, lastUpdated, lastRunAt] = await Promise.all([
      fetchAll<RankedCompanyRow>(supabase, "ranked_companies", "score"),
      latestSignalTime(supabase),
      lastRunTime(supabase),
    ]);
    const ids = companies.map((c) => c.company_id);
    const [signals, decisions] = await Promise.all([
      fetchForCompanies<SignalRow>(supabase, "signals", ids),
      fetchForCompanies<DecisionRow>(supabase, "decisions", ids),
    ]);

    return {
      companies: toCompanies(companies, signals, decisions).sort(
        (a, b) => b.score - a.score
      ),
      lastUpdated,
      lastRunAt,
      isSampleData: false,
    };
  } catch (err) {
    console.error("dashboard data fetch failed, falling back to sample:", err);
    return { companies: sampleCompanies, lastUpdated: null, lastRunAt: null, isSampleData: true };
  }
}
