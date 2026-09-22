import type {
  Badge,
  Company,
  Decision,
  DecisionRow,
  RankedCompanyRow,
  Round,
  Signal,
  SignalRow,
} from "./types";

const ROUND_LABELS: Record<string, Round> = {
  pre_seed: "Pre-seed",
  seed: "Seed",
  series_a: "Series A",
  series_b: "Series B",
  later: "Later",
};

// Weights for rules that do not carry their own "(+N)" suffix. Mirrors
// SCORING_WEIGHTS in pipeline/src/config.py.
const RULE_POINTS: Record<string, number> = {
  round_seed_to_b: 15,
  first_sales_hire: 30,
  any_sales_role_open: 15,
  technical_founders: 10,
};

const RULE_LABELS: Record<string, string> = {
  raise_recency: "Raise recency",
  round_seed_to_b: "Round Seed-B",
  first_sales_hire: "First sales hire",
  any_sales_role_open: "Any sales role open",
  technical_founders: "Technical founders",
  icp_fit: "ICP fit",
};

/** "raise_recency (+28)" -> { rule: "Raise recency", points: 28 } */
function parseRule(raw: string): { rule: string; points: number } {
  const match = raw.match(/^(\w+)\s*\(\+(\d+)\)$/);
  const key = match ? match[1] : raw;
  const points = match ? Number(match[2]) : (RULE_POINTS[key] ?? 0);
  return { rule: RULE_LABELS[key] ?? key, points };
}

/** "yes (Account Executive)" -> "Account Executive" */
function parenValue(value: string): string | null {
  const m = value.match(/\(([^)]+)\)\s*$/);
  return m ? m[1].trim() : null;
}

function isYes(s: SignalRow): boolean {
  return s.value.toLowerCase().startsWith("yes");
}

const SIGNAL_LABELS: Record<string, string> = {
  genuine_raise: "Genuine raise",
  is_startup: "Venture-backed startup",
  sells_to: "Sells to",
  icp_fit: "ICP fit",
  round: "Round",
  first_sales_hire: "First sales hire",
  technical_founders: "Technical founders",
  sales_role: "Sales role",
  sales_role_type: "Sales role type",
  domain_unverified: "Domain unverified",
};

function signalLabel(s: SignalRow): string {
  if (s.signal_type === "sales_role" && isYes(s)) {
    return `Hiring: ${parenValue(s.value) ?? "sales role"}`;
  }
  if (s.signal_type === "domain_unverified") return "Domain unverified";
  return `${SIGNAL_LABELS[s.signal_type] ?? s.signal_type}: ${s.value}`;
}

/**
 * Badges show findings, never rule names. Raise recency and round are
 * deliberately absent - they already have their own columns.
 * Order: first sales hire, sales roles, technical founders, B2B.
 */
function buildBadges(signals: SignalRow[]): Badge[] {
  const badges: Badge[] = [];
  const first = signals.find((s) => s.signal_type === "first_sales_hire" && isYes(s));
  if (first) {
    badges.push({ id: `b-${first.id}`, label: "First sales hire", needsReview: first.needs_review });
  }

  const seen = new Set<string>();
  for (const s of signals) {
    if (s.signal_type !== "sales_role" || !isYes(s)) continue;
    const title = parenValue(s.value);
    if (!title || seen.has(title)) continue;
    seen.add(title);
    badges.push({ id: `b-${s.id}`, label: `Hiring: ${title}`, needsReview: s.needs_review });
  }

  const tech = signals.find((s) => s.signal_type === "technical_founders" && isYes(s));
  if (tech) {
    badges.push({ id: `b-${tech.id}`, label: "Technical founders", needsReview: tech.needs_review });
  }

  const b2b = signals.find((s) => s.signal_type === "sells_to" && s.value === "B2B");
  if (b2b) {
    badges.push({ id: `b-${b2b.id}`, label: "B2B", needsReview: b2b.needs_review });
  }
  return badges;
}

function draftEmail(name: string, round: Round, roleLabel: string, hook: string): string {
  return (
    `Hi there,\n\n` +
    `Congrats on the ${round.toLowerCase()} round — saw the news and noticed ${name} is ` +
    `${hook}. That's usually the moment outbound infrastructure gets built from scratch, ` +
    `and I imagine whoever takes the ${roleLabel} role is going to need it working on day one.\n\n` +
    `Worth a 15 minute call this week to see if it's a fit?\n\n` +
    `Best,\nJoe`
  );
}

export function toCompanies(
  rows: RankedCompanyRow[],
  signalRows: SignalRow[],
  decisionRows: DecisionRow[]
): Company[] {
  const byCompany = new Map<number, SignalRow[]>();
  for (const s of signalRows) {
    const list = byCompany.get(s.company_id);
    if (list) list.push(s);
    else byCompany.set(s.company_id, [s]);
  }
  const decisionsBy = new Map<number, Decision[]>();
  for (const d of decisionRows) {
    const list = decisionsBy.get(d.company_id) ?? [];
    list.push({
      round: d.round,
      question: d.question,
      answer: d.answer,
      confidence: d.confidence,
      actionChosen: d.action_chosen,
    });
    decisionsBy.set(d.company_id, list);
  }

  return rows.map((r) => {
    const raw = byCompany.get(r.company_id) ?? [];
    const round = ROUND_LABELS[r.round ?? ""] ?? "Later";
    const salesTitles = raw
      .filter((s) => s.signal_type === "sales_role" && isYes(s))
      .map((s) => parenValue(s.value))
      .filter((t): t is string => Boolean(t));
    const firstHire = raw.some((s) => s.signal_type === "first_sales_hire" && isYes(s));

    const signals: Signal[] = raw.map((s) => ({
      id: `s-${s.id}`,
      type: s.signal_type,
      label: signalLabel(s),
      confidence: s.confidence,
      needsReview: s.needs_review,
      sourceUrl: s.source_url,
    }));

    return {
      id: String(r.company_id),
      name: r.name,
      domain: r.domain,
      domainVerified: r.domain_verified,
      round,
      amountRaised: r.amount_raised === null ? null : Number(r.amount_raised),
      raisedDate: r.raised_date,
      score: r.score,
      rulesFired: (r.rules_fired ?? []).map(parseRule),
      explanation: r.explanation ?? "",
      signals,
      badges: buildBadges(raw),
      decisions: decisionsBy.get(r.company_id) ?? [],
      draftEmail: draftEmail(
        r.name,
        round,
        salesTitles[0] ?? "sales",
        firstHire
          ? "making its first sales hire"
          : salesTitles.length > 0
            ? "opening up sales roles"
            : "growing fast post-raise"
      ),
    };
  });
}
