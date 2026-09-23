import { expect, test } from "@playwright/test";

import { toCompanies } from "../lib/map";
import type { RankedCompanyRow, SignalRow } from "../lib/types";

const row = (rules: string[]): RankedCompanyRow => ({
  company_id: 1, score: 0, explanation: "", rules_fired: rules, run_date: "2026-09-23",
  name: "Arcee AI", domain: null, domain_verified: false, round: "series_a",
  amount_raised: null, raised_date: "2026-09-22", first_seen: "2026-09-22",
});

test("reduced low-confidence rules show their confidence and full value", () => {
  const [company] = toCompanies(
    [row(["raise_recency (+28)", "first_sales_hire (+6, confidence 0.14, reduced from 30)", "technical_founders"])],
    [], []
  );
  expect(company.rulesFired).toEqual([
    { rule: "Raise recency", points: 28 },
    { rule: "First sales hire (confidence 0.14)", points: 6, note: "reduced from 30" },
    { rule: "Technical founders", points: 10 },
  ]);
});

test("unknown founders read as missing data", () => {
  const signal: SignalRow = {
    id: 1, company_id: 1, signal_type: "technical_founders", value: "unknown",
    confidence: 0.9, needs_review: false, source_url: null, detected_at: "2026-09-23",
  };
  const [company] = toCompanies([row([])], [signal], []);
  expect(company.signals[0].label).toBe("Founders: unknown");
  expect(company.badges).toEqual([]);
});

test("each question shows only its current answer, and jobs only real sales roles", () => {
  let id = 0;
  const s = (signal_type: string, value: string, source_url: string | null = null, confidence = 0.9): SignalRow => ({
    id: ++id, company_id: 1, signal_type, value, confidence, needs_review: confidence < 0.7, source_url, detected_at: "2026-09-23",
  });
  const rows = [
    s("icp_fit", "2.1", null, 0.5), s("round", "Seed"), s("new_round", "yes"),
    s("sales_role", "yes (Enterprise Account Executive)", "j1"), s("sales_role_type", "AE (Enterprise Account Executive)", "j1"),
    s("sales_role", "no (GTM Recruiter)", "j2"), s("sales_role_type", "Other (GTM Recruiter)", "j2"),
    s("icp_fit", "2.4", null, 0.6), s("round", "Series A"),
    s("icp_fit", "2.7", null, 0.8),  // the investigation's final answer
    s("sells_to", "B2B"),
    s("sales_role", "yes (Enterprise Account Executive)", "j3"),  // second posting, same title
  ];
  const [company] = toCompanies([row([])], rows, []);
  expect(company.signals.map((x) => x.label)).toEqual([
    "New round: yes", "Round: Series A", "Sells to: B2B", "ICP fit: 2.7", "Hiring: Enterprise Account Executive",
  ]);
  // Only the current ICP answer counts toward "needs review".
  expect(company.signals.some((x) => x.needsReview)).toBe(false);
});
