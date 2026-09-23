// --- Rows as they come back from Postgres -----------------------------------

export type RankedCompanyRow = {
  company_id: number;
  score: number;
  explanation: string | null;
  rules_fired: string[];
  run_date: string;
  name: string;
  domain: string | null;
  domain_verified: boolean;
  round: string | null;
  amount_raised: number | null;
  raised_date: string | null;
  first_seen: string;
};

export type SignalRow = {
  id: number;
  company_id: number;
  signal_type: string;
  value: string;
  confidence: number;
  needs_review: boolean;
  source_url: string | null;
  detected_at: string;
};

export type DecisionRow = {
  id: number;
  company_id: number;
  question: string;
  answer: string;
  confidence: number;
  action_chosen: string | null;
  round: number;
  created_at: string;
};

// --- Shapes the table renders ------------------------------------------------

export type Round = "Pre-seed" | "Seed" | "Series A" | "Series B" | "Later";

export type Signal = {
  id: string;
  type: string;
  label: string;
  confidence: number;
  needsReview: boolean;
  sourceUrl: string | null;
};

/** A finding shown on the row itself. Never a rule name. */
export type Badge = {
  id: string;
  label: string;
  needsReview: boolean;
};

export type Decision = {
  round: number;
  question: string;
  answer: string;
  confidence: number;
  actionChosen: string | null;
};

export type Company = {
  id: string;
  name: string;
  domain: string | null;
  domainVerified: boolean;
  round: Round;
  amountRaised: number | null;
  raisedDate: string | null;
  score: number;
  /** note: e.g. "reduced from 30" when a low-confidence answer earned partial points */
  rulesFired: { rule: string; points: number; note?: string }[];
  explanation: string;
  signals: Signal[];
  badges: Badge[];
  decisions: Decision[];
  draftEmail: string;
};
