import { createClient, type SupabaseClient } from "@supabase/supabase-js";

import { toCompanies } from "./map";
import { sampleCompanies } from "./sample-data";
import type { Company, DecisionRow, RankedCompanyRow, SignalRow } from "./types";

export type DashboardData = {
  companies: Company[];
  lastUpdated: string | null;
  isSampleData: boolean;
};

const PAGE = 1000;

/**
 * PostgREST caps a response at 1000 rows. signals is already well past that,
 * so anything unpaged silently loses most of the badges.
 */
async function fetchAll<T>(
  supabase: SupabaseClient,
  table: string,
  order: string
): Promise<T[]> {
  const out: T[] = [];
  for (let from = 0; ; from += PAGE) {
    const { data, error } = await supabase
      .from(table)
      .select("*")
      .order(order)
      .range(from, from + PAGE - 1);
    if (error) throw new Error(`${table}: ${error.message}`);
    const rows = (data ?? []) as T[];
    out.push(...rows);
    if (rows.length < PAGE) return out;
  }
}

export async function fetchDashboardData(): Promise<DashboardData> {
  // Server-only env vars (no NEXT_PUBLIC_ prefix): read in a server
  // component, so they are never bundled into client-side JS.
  const url = process.env.SUPABASE_URL;
  const key = process.env.SUPABASE_ANON_KEY;

  if (!url || !key) {
    return { companies: sampleCompanies, lastUpdated: null, isSampleData: true };
  }

  const supabase = createClient(url, key);
  try {
    const [companies, signals, decisions] = await Promise.all([
      fetchAll<RankedCompanyRow>(supabase, "ranked_companies", "score"),
      fetchAll<SignalRow>(supabase, "signals", "id"),
      fetchAll<DecisionRow>(supabase, "decisions", "id"),
    ]);

    const lastUpdated =
      signals
        .map((s) => s.detected_at)
        .filter(Boolean)
        .sort()
        .at(-1) ?? null;

    return {
      companies: toCompanies(companies, signals, decisions).sort(
        (a, b) => b.score - a.score
      ),
      lastUpdated,
      isSampleData: false,
    };
  } catch (err) {
    console.error("dashboard data fetch failed, falling back to sample:", err);
    return { companies: sampleCompanies, lastUpdated: null, isSampleData: true };
  }
}
