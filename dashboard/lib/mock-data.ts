export type Round = "Pre-seed" | "Seed" | "Series A" | "Series B" | "Later";

export type Signal = {
  id: string;
  type:
    | "funding"
    | "sales_role"
    | "first_sales_hire"
    | "technical_founder"
    | "icp_fit";
  label: string; // e.g. "Hiring: Founding AE"
  confidence: number; // 0 to 1
  needsReview: boolean; // true when confidence < 0.7
  sourceUrl: string;
  detectedAt: string; // ISO date
};

export type Decision = {
  round: number; // 1, 2, or 3
  question: string;
  answer: string;
  confidence: number;
  actionChosen: string | null; // null when it chose to stop
};

export type Company = {
  id: string;
  name: string;
  domain: string;
  round: Round;
  amountRaised: number; // USD
  raisedDate: string; // ISO date
  score: number;
  rulesFired: { rule: string; points: number }[];
  explanation: string;
  signals: Signal[];
  decisions: Decision[];
  draftEmail: string;
};

function isoDaysAgo(days: number): string {
  const d = new Date();
  d.setUTCDate(d.getUTCDate() - days);
  return d.toISOString().slice(0, 10);
}

let sigCounter = 0;
function mkSignal(
  type: Signal["type"],
  label: string,
  confidence: number,
  sourceUrl: string,
  detectedDaysAgo: number
): Signal {
  sigCounter += 1;
  return {
    id: `sig-${sigCounter}`,
    type,
    label,
    confidence,
    needsReview: confidence < 0.7,
    sourceUrl,
    detectedAt: isoDaysAgo(detectedDaysAgo),
  };
}

function mkDecision(
  round: number,
  question: string,
  answer: string,
  confidence: number,
  actionChosen: string | null
): Decision {
  return { round, question, answer, confidence, actionChosen };
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

type Spec = {
  name: string;
  domain: string;
  round: Round;
  amountM: number; // millions
  raisedDaysAgo: number;
  score: number;
  technicalFounders: boolean;
  firstSalesHire: boolean;
  salesRoles: string[];
  icpConfidence: number;
  icpLabel: string;
  decisions?: Decision[];
  lowConfidenceFirstHire?: boolean;
};

const SPECS: Spec[] = [
  {
    name: "Linear",
    domain: "linear.app",
    round: "Series B",
    amountM: 50,
    raisedDaysAgo: 18,
    score: 55,
    technicalFounders: true,
    firstSalesHire: false,
    salesRoles: ["Account Executive"],
    icpConfidence: 0.88,
    icpLabel: "strong",
    decisions: [mkDecision(1, "Evidence sufficient?", "Yes", 0.9, null)],
  },
  {
    name: "Vercel",
    domain: "vercel.com",
    round: "Series B",
    amountM: 40,
    raisedDaysAgo: 65,
    score: 45,
    technicalFounders: true,
    firstSalesHire: false,
    salesRoles: ["Enterprise Account Executive"],
    icpConfidence: 0.79,
    icpLabel: "good",
  },
  {
    name: "Supabase",
    domain: "supabase.com",
    round: "Series A",
    amountM: 30,
    raisedDaysAgo: 9,
    score: 80,
    technicalFounders: true,
    firstSalesHire: true,
    salesRoles: ["Founding Account Executive", "SDR"],
    icpConfidence: 0.91,
    icpLabel: "strong",
    decisions: [
      mkDecision(1, "Evidence sufficient?", "No", 0.58, "check_careers"),
      mkDecision(2, "Evidence sufficient?", "Yes", 0.86, null),
    ],
  },
  {
    name: "Resend",
    domain: "resend.com",
    round: "Seed",
    amountM: 8,
    raisedDaysAgo: 5,
    score: 85,
    technicalFounders: true,
    firstSalesHire: true,
    salesRoles: ["Founding AE"],
    icpConfidence: 0.93,
    icpLabel: "strong",
  },
  {
    name: "Clerk",
    domain: "clerk.com",
    round: "Series A",
    amountM: 15,
    raisedDaysAgo: 22,
    score: 75,
    technicalFounders: true,
    firstSalesHire: true,
    salesRoles: ["Account Executive"],
    icpConfidence: 0.84,
    icpLabel: "strong",
  },
  {
    name: "PostHog",
    domain: "posthog.com",
    round: "Series B",
    amountM: 25,
    raisedDaysAgo: 40,
    score: 50,
    technicalFounders: true,
    firstSalesHire: false,
    salesRoles: ["SDR"],
    icpConfidence: 0.62,
    icpLabel: "unclear",
  },
  {
    name: "Retool",
    domain: "retool.com",
    round: "Series A",
    amountM: 45,
    raisedDaysAgo: 70,
    score: 40,
    technicalFounders: true,
    firstSalesHire: false,
    salesRoles: [],
    icpConfidence: 0.71,
    icpLabel: "good",
  },
  {
    name: "Raycast",
    domain: "raycast.com",
    round: "Series A",
    amountM: 20,
    raisedDaysAgo: 14,
    score: 78,
    technicalFounders: true,
    firstSalesHire: true,
    salesRoles: ["Founding AE"],
    icpConfidence: 0.87,
    icpLabel: "strong",
    decisions: [
      mkDecision(1, "Evidence sufficient?", "No", 0.55, "check_careers"),
      mkDecision(2, "Evidence sufficient?", "No", 0.63, "fetch_about"),
      mkDecision(3, "Evidence sufficient?", "Yes", 0.82, null),
    ],
  },
  {
    name: "Cal.com",
    domain: "cal.com",
    round: "Seed",
    amountM: 6,
    raisedDaysAgo: 3,
    score: 88,
    technicalFounders: true,
    firstSalesHire: true,
    salesRoles: ["Founding AE", "SDR"],
    icpConfidence: 0.95,
    icpLabel: "strong",
  },
  {
    name: "Loops",
    domain: "loops.so",
    round: "Pre-seed",
    amountM: 2,
    raisedDaysAgo: 8,
    score: 65,
    technicalFounders: true,
    firstSalesHire: true,
    salesRoles: ["Founding AE"],
    icpConfidence: 0.74,
    icpLabel: "good",
  },
  {
    name: "Framer",
    domain: "framer.com",
    round: "Series B",
    amountM: 35,
    raisedDaysAgo: 55,
    score: 42,
    technicalFounders: false,
    firstSalesHire: false,
    salesRoles: ["Account Executive"],
    icpConfidence: 0.68,
    icpLabel: "unclear",
  },
  {
    name: "Airtable",
    domain: "airtable.com",
    round: "Later",
    amountM: 80,
    raisedDaysAgo: 100,
    score: 25,
    technicalFounders: true,
    firstSalesHire: false,
    salesRoles: [],
    icpConfidence: 0.4,
    icpLabel: "weak",
  },
  {
    name: "Webflow",
    domain: "webflow.com",
    round: "Later",
    amountM: 60,
    raisedDaysAgo: 120,
    score: 25,
    technicalFounders: false,
    firstSalesHire: false,
    salesRoles: [],
    icpConfidence: 0.35,
    icpLabel: "weak",
  },
  {
    name: "Ramp",
    domain: "ramp.com",
    round: "Series B",
    amountM: 150,
    raisedDaysAgo: 28,
    score: 60,
    technicalFounders: true,
    firstSalesHire: false,
    salesRoles: ["Account Executive", "SDR"],
    icpConfidence: 0.77,
    icpLabel: "good",
  },
  {
    name: "Mercury",
    domain: "mercury.com",
    round: "Series B",
    amountM: 90,
    raisedDaysAgo: 45,
    score: 48,
    technicalFounders: true,
    firstSalesHire: true,
    salesRoles: ["Account Executive"],
    icpConfidence: 0.72,
    icpLabel: "good",
    lowConfidenceFirstHire: true,
  },
  {
    name: "Deel",
    domain: "deel.com",
    round: "Later",
    amountM: 50,
    raisedDaysAgo: 80,
    score: 30,
    technicalFounders: false,
    firstSalesHire: false,
    salesRoles: ["SDR"],
    icpConfidence: 0.55,
    icpLabel: "unclear",
  },
  {
    name: "Gusto",
    domain: "gusto.com",
    round: "Later",
    amountM: 100,
    raisedDaysAgo: 200,
    score: 25,
    technicalFounders: false,
    firstSalesHire: false,
    salesRoles: [],
    icpConfidence: 0.3,
    icpLabel: "weak",
  },
  {
    name: "Plaid",
    domain: "plaid.com",
    round: "Series A",
    amountM: 34,
    raisedDaysAgo: 12,
    score: 76,
    technicalFounders: true,
    firstSalesHire: true,
    salesRoles: ["Founding AE"],
    icpConfidence: 0.89,
    icpLabel: "strong",
    decisions: [
      mkDecision(1, "Evidence sufficient?", "No", 0.61, "search_news"),
      mkDecision(2, "Evidence sufficient?", "Yes", 0.83, null),
    ],
  },
  {
    name: "Amplitude",
    domain: "amplitude.com",
    round: "Series B",
    amountM: 40,
    raisedDaysAgo: 33,
    score: 52,
    technicalFounders: true,
    firstSalesHire: false,
    salesRoles: ["Account Executive"],
    icpConfidence: 0.7,
    icpLabel: "good",
  },
  {
    name: "Intercom",
    domain: "intercom.com",
    round: "Later",
    amountM: 55,
    raisedDaysAgo: 90,
    score: 28,
    technicalFounders: false,
    firstSalesHire: false,
    salesRoles: [],
    icpConfidence: 0.65,
    icpLabel: "unclear",
  },
  {
    name: "Attio",
    domain: "attio.com",
    round: "Seed",
    amountM: 6.5,
    raisedDaysAgo: 6,
    score: 90,
    technicalFounders: true,
    firstSalesHire: true,
    salesRoles: ["Founding AE", "SDR"],
    icpConfidence: 0.96,
    icpLabel: "strong",
  },
  {
    name: "Modal",
    domain: "modal.com",
    round: "Seed",
    amountM: 16,
    raisedDaysAgo: 2,
    score: 90,
    technicalFounders: true,
    firstSalesHire: true,
    salesRoles: ["Founding AE"],
    icpConfidence: 0.92,
    icpLabel: "strong",
  },
  {
    name: "Temporal",
    domain: "temporal.io",
    round: "Series A",
    amountM: 25,
    raisedDaysAgo: 19,
    score: 68,
    technicalFounders: true,
    firstSalesHire: false,
    salesRoles: ["Account Executive"],
    icpConfidence: 0.75,
    icpLabel: "good",
  },
  {
    name: "Notarealco",
    domain: "notarealco-xyz.com",
    round: "Pre-seed",
    amountM: 1.2,
    raisedDaysAgo: 4,
    score: 58,
    technicalFounders: true,
    firstSalesHire: true,
    salesRoles: ["Founding AE"],
    icpConfidence: 0.66,
    icpLabel: "unclear",
  },
  {
    name: "Ghostworks",
    domain: "ghostworks-fake.io",
    round: "Seed",
    amountM: 4,
    raisedDaysAgo: 11,
    score: 62,
    technicalFounders: false,
    firstSalesHire: true,
    salesRoles: ["SDR"],
    icpConfidence: 0.69,
    icpLabel: "unclear",
  },
];

function buildCompany(spec: Spec, index: number): Company {
  const {
    name,
    domain,
    round,
    amountM,
    raisedDaysAgo,
    score,
    technicalFounders,
    firstSalesHire,
    salesRoles,
    icpConfidence,
    icpLabel,
    decisions,
    lowConfidenceFirstHire,
  } = spec;

  const sourceUrl = `https://techcrunch.com/${raisedDaysAgo}d/${domain.split(".")[0]}-raises`;
  const signals: Signal[] = [];

  signals.push(
    mkSignal(
      "funding",
      `Raised ${round} — $${amountM}M`,
      0.97,
      sourceUrl,
      raisedDaysAgo
    )
  );

  for (const role of salesRoles) {
    const board = index % 2 === 0 ? "ashbyhq.com" : "greenhouse.io";
    signals.push(
      mkSignal(
        "sales_role",
        `Hiring: ${role}`,
        0.85 + (index % 5) / 100,
        `https://jobs.${board}/${domain.split(".")[0]}/${index}`,
        Math.max(0, raisedDaysAgo - 1)
      )
    );
  }

  if (firstSalesHire) {
    signals.push(
      mkSignal(
        "first_sales_hire",
        "First sales hire",
        lowConfidenceFirstHire ? 0.58 : 0.81,
        `${domain ? `https://${domain}/careers` : sourceUrl}`,
        Math.max(0, raisedDaysAgo - 1)
      )
    );
  }

  signals.push(
    mkSignal(
      "technical_founder",
      technicalFounders ? "Technical founding team" : "Non-technical founding team",
      technicalFounders ? 0.86 : 0.8,
      `https://${domain}/about`,
      raisedDaysAgo + 2
    )
  );

  signals.push(
    mkSignal("icp_fit", `ICP fit: ${icpLabel}`, icpConfidence, sourceUrl, raisedDaysAgo)
  );

  const rulesFired: { rule: string; points: number }[] = [];
  if (raisedDaysAgo <= 30) rulesFired.push({ rule: "Raised within 30 days", points: 30 });
  else if (raisedDaysAgo <= 90) rulesFired.push({ rule: "Raised 31-90 days ago", points: 15 });
  if (round !== "Later") rulesFired.push({ rule: "Round Seed-B", points: 15 });
  if (firstSalesHire && salesRoles.length > 0)
    rulesFired.push({ rule: "First sales hire", points: 30 });
  if (salesRoles.length > 0) rulesFired.push({ rule: "Any sales role open", points: 15 });
  if (technicalFounders) rulesFired.push({ rule: "Technical founders", points: 10 });

  const roleLabel = salesRoles[0] ?? "sales";
  const hook = firstSalesHire
    ? "making its first sales hire"
    : salesRoles.length > 0
      ? "opening up sales roles"
      : "growing fast post-raise";

  const explanationParts: string[] = [`Raised ${round.toLowerCase()} ${raisedDaysAgo}d ago`];
  if (firstSalesHire && salesRoles.length > 0)
    explanationParts.push(
      `making first sales hire (${salesRoles.length} sales role${salesRoles.length !== 1 ? "s" : ""} open)`
    );
  else if (salesRoles.length > 0) explanationParts.push("has open sales roles");
  if (technicalFounders) explanationParts.push("technical founding team");

  return {
    id: `co-${index + 1}`,
    name,
    domain,
    round,
    amountRaised: Math.round(amountM * 1_000_000),
    raisedDate: isoDaysAgo(raisedDaysAgo),
    score,
    rulesFired,
    explanation: explanationParts.join("; ") + ".",
    signals,
    decisions: decisions ?? [],
    draftEmail: draftEmail(name, round, roleLabel, hook),
  };
}

export const companies: Company[] = SPECS.map(buildCompany);
