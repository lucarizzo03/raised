import type { Company } from "./types";

const today = new Date().toISOString().slice(0, 10);

/** Rendered only when SUPABASE_URL / SUPABASE_ANON_KEY are absent. */
export const sampleCompanies: Company[] = [
  {
    id: "1",
    name: "Acme Data",
    domain: "acme.com",
    domainVerified: true,
    round: "Seed",
    amountRaised: 8_000_000,
    raisedDate: today,
    score: 100,
    rulesFired: [
      { rule: "Raise recency", points: 30 },
      { rule: "Round Seed-B", points: 15 },
      { rule: "First sales hire", points: 30 },
      { rule: "Any sales role open", points: 15 },
      { rule: "ICP fit", points: 10 },
    ],
    explanation: "Raised seed 0d ago; making first sales hire (1 sales role open); sells B2B.",
    signals: [
      { id: "s-1", type: "genuine_raise", label: "Genuine raise: yes", confidence: 0.97, needsReview: false, sourceUrl: "https://example.com" },
      { id: "s-2", type: "sales_role", label: "Hiring: Account Executive", confidence: 0.91, needsReview: false, sourceUrl: "https://example.com/job" },
      { id: "s-3", type: "sells_to", label: "Sells to: B2B", confidence: 0.88, needsReview: false, sourceUrl: null },
    ],
    badges: [
      { id: "b-1", label: "First sales hire", needsReview: false },
      { id: "b-2", label: "Hiring: Account Executive", needsReview: false },
      { id: "b-3", label: "B2B", needsReview: false },
    ],
    decisions: [
      { round: 1, question: "score now or dig deeper?", answer: "check_careers", confidence: 0.81, actionChosen: "check_careers" },
      { round: 2, question: "score now or dig deeper?", answer: "score_now", confidence: 0.9, actionChosen: null },
    ],
    draftEmail: "Hi there,\n\nCongrats on the seed round.\n\nBest,\nJoe",
  },
];
