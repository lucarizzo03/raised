import { createClient } from "@supabase/supabase-js";

import type { DecisionRow, RankedCompany, SignalRow } from "./types";
import { sampleCompanies, sampleDecisions, sampleSignals } from "./sample-data";

export type DashboardData = {
  companies: RankedCompany[];
  signals: SignalRow[];
  decisions: DecisionRow[];
  runDate: string | null;
  isSampleData: boolean;
};

export async function fetchDashboardData(): Promise<DashboardData> {
  const url = process.env.NEXT_PUBLIC_SUPABASE_URL;
  const key = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY;

  if (!url || !key) {
    return {
      companies: sampleCompanies,
      signals: sampleSignals,
      decisions: sampleDecisions,
      runDate: null,
      isSampleData: true,
    };
  }

  const supabase = createClient(url, key);
  const [companies, signals, decisions] = await Promise.all([
    supabase
      .from("ranked_companies")
      .select("*")
      .order("score", { ascending: false }),
    supabase.from("signals").select("*").order("detected_at", { ascending: false }),
    supabase.from("decisions").select("*").order("created_at"),
  ]);

  return {
    companies: (companies.data ?? []) as RankedCompany[],
    signals: (signals.data ?? []) as SignalRow[],
    decisions: (decisions.data ?? []) as DecisionRow[],
    runDate: companies.data?.[0]?.run_date ?? null,
    isSampleData: false,
  };
}
