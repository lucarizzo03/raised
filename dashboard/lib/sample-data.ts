import type { DecisionRow, RankedCompany, SignalRow } from "./types";

const today = new Date().toISOString().slice(0, 10);

export const sampleCompanies: RankedCompany[] = [
  {
    company_id: 1,
    score: 100,
    explanation:
      "Raised seed 12d ago; making first sales hire (2 sales roles open); technical founding team.",
    rules_fired: ["raised_within_30d", "round_seed_to_b", "first_sales_hire", "any_sales_role_open", "technical_founders"],
    run_date: today,
    name: "Acme Data",
    domain: "acme.com",
    round: "seed",
    amount_raised: 8000000,
    raised_date: today,
    first_seen: today,
  },
  {
    company_id: 2,
    score: 60,
    explanation: "Raised series_a 45d ago; has open sales roles.",
    rules_fired: ["raised_31_90d", "round_seed_to_b", "any_sales_role_open"],
    run_date: today,
    name: "Beta Cloud",
    domain: "vercel.com",
    round: "series_a",
    amount_raised: 20000000,
    raised_date: today,
    first_seen: today,
  },
];

export const sampleSignals: SignalRow[] = [
  { id: 1, company_id: 1, signal_type: "genuine_raise", value: "yes", confidence: 0.97, needs_review: false, source_url: "https://techcrunch.com/example", detected_at: today },
  { id: 2, company_id: 1, signal_type: "round", value: "Seed", confidence: 0.93, needs_review: false, source_url: "https://techcrunch.com/example", detected_at: today },
  { id: 3, company_id: 1, signal_type: "sales_role", value: "yes (Account Executive)", confidence: 0.91, needs_review: false, source_url: "https://jobs.ashbyhq.com/acme/1", detected_at: today },
  { id: 4, company_id: 1, signal_type: "icp_fit", value: "4.0", confidence: 0.66, needs_review: true, source_url: "https://techcrunch.com/example", detected_at: today },
  { id: 5, company_id: 1, signal_type: "technical_founders", value: "yes", confidence: 0.88, needs_review: false, source_url: null, detected_at: today },
];

export const sampleDecisions: DecisionRow[] = [
  { id: 1, company_id: 1, question: "score now or dig deeper?", answer: "check_careers", confidence: 0.81, action_chosen: "check_careers", round: 1, created_at: today },
  { id: 2, company_id: 1, question: "score now or dig deeper?", answer: "fetch_about", confidence: 0.77, action_chosen: "fetch_about", round: 2, created_at: today },
  { id: 3, company_id: 1, question: "score now or dig deeper?", answer: "score_now", confidence: 0.9, action_chosen: null, round: 3, created_at: today },
];
