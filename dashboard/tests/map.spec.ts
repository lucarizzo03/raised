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
