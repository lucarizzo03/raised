export type RankedCompany = {
  company_id: number;
  score: number;
  explanation: string | null;
  rules_fired: string[];
  run_date: string;
  name: string;
  domain: string | null;
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
