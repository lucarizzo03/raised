"use client";

import { Fragment, useMemo, useState } from "react";

import type { DecisionRow, RankedCompany, SignalRow } from "@/lib/types";
import Logo from "./Logo";

const ROUND_LABELS: Record<string, string> = {
  pre_seed: "Pre-seed",
  seed: "Seed",
  series_a: "Series A",
  series_b: "Series B",
  later: "Later",
  unknown: "?",
};

const RULE_BADGES: Record<string, string> = {
  raised_within_30d: "fresh raise",
  raised_31_90d: "recent raise",
  round_seed_to_b: "Seed–B",
  first_sales_hire: "first sales hire",
  any_sales_role_open: "sales roles",
  technical_founders: "technical founders",
};

function daysSince(dateStr: string | null): number | null {
  if (!dateStr) return null;
  return Math.floor((Date.now() - new Date(dateStr).getTime()) / 86400000);
}

function fmtAmount(v: number | null): string {
  if (v == null) return "—";
  if (v >= 1e9) return `$${(v / 1e9).toFixed(1)}B`;
  if (v >= 1e6) return `$${(v / 1e6).toFixed(1)}M`;
  if (v >= 1e3) return `$${(v / 1e3).toFixed(0)}K`;
  return `$${v}`;
}

export default function CompanyTable({
  companies,
  signals,
  decisions,
}: {
  companies: RankedCompany[];
  signals: SignalRow[];
  decisions: DecisionRow[];
}) {
  const [roundFilter, setRoundFilter] = useState("");
  const [minScore, setMinScore] = useState(0);
  const [open, setOpen] = useState<number | null>(null);

  const signalsByCompany = useMemo(() => {
    const m = new Map<number, SignalRow[]>();
    for (const s of signals) {
      m.set(s.company_id, [...(m.get(s.company_id) ?? []), s]);
    }
    return m;
  }, [signals]);

  const decisionsByCompany = useMemo(() => {
    const m = new Map<number, DecisionRow[]>();
    for (const d of decisions) {
      m.set(d.company_id, [...(m.get(d.company_id) ?? []), d]);
    }
    return m;
  }, [decisions]);

  const rounds = useMemo(
    () => [...new Set(companies.map((c) => c.round).filter(Boolean))] as string[],
    [companies]
  );

  const rows = companies.filter(
    (c) => (!roundFilter || c.round === roundFilter) && c.score >= minScore
  );

  return (
    <div>
      <div className="mb-3 flex gap-3 text-sm">
        <select
          className="rounded border border-neutral-300 px-2 py-1"
          value={roundFilter}
          onChange={(e) => setRoundFilter(e.target.value)}
        >
          <option value="">All rounds</option>
          {rounds.map((r) => (
            <option key={r} value={r}>
              {ROUND_LABELS[r] ?? r}
            </option>
          ))}
        </select>
        <label className="flex items-center gap-2 text-neutral-600">
          Min score
          <input
            type="number"
            min={0}
            step={10}
            className="w-20 rounded border border-neutral-300 px-2 py-1"
            value={minScore}
            onChange={(e) => setMinScore(Number(e.target.value) || 0)}
          />
        </label>
        <span className="ml-auto self-center text-neutral-400">{rows.length} companies</span>
      </div>

      <table className="w-full border-collapse text-sm">
        <thead>
          <tr className="border-b border-neutral-200 text-left text-xs uppercase text-neutral-400">
            <th className="py-2 pr-2 font-medium">#</th>
            <th className="py-2 pr-2 font-medium">Company</th>
            <th className="py-2 pr-2 font-medium">Score</th>
            <th className="py-2 pr-2 font-medium">Round</th>
            <th className="py-2 pr-2 font-medium">Raised</th>
            <th className="py-2 pr-2 font-medium">Days</th>
            <th className="py-2 font-medium">Signals</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((c, i) => {
            const days = daysSince(c.raised_date);
            const expanded = open === c.company_id;
            return (
              <Fragment key={c.company_id}>
                <tr
                  className="cursor-pointer border-b border-neutral-100 hover:bg-neutral-50"
                  onClick={() => setOpen(expanded ? null : c.company_id)}
                >
                  <td className="py-2 pr-2 text-neutral-400">{i + 1}</td>
                  <td className="py-2 pr-2">
                    <span className="flex items-center gap-2 font-medium">
                      <Logo domain={c.domain} name={c.name} />
                      {c.name}
                    </span>
                  </td>
                  <td className="py-2 pr-2 font-semibold tabular-nums">{c.score}</td>
                  <td className="py-2 pr-2">{ROUND_LABELS[c.round ?? "unknown"] ?? c.round}</td>
                  <td className="py-2 pr-2 tabular-nums">{fmtAmount(c.amount_raised)}</td>
                  <td className="py-2 pr-2 tabular-nums">{days ?? "—"}</td>
                  <td className="py-2">
                    <span className="flex flex-wrap gap-1">
                      {(c.rules_fired ?? []).map((r) => (
                        <span
                          key={r}
                          className="rounded bg-neutral-100 px-1.5 py-0.5 text-[11px] text-neutral-600"
                        >
                          {RULE_BADGES[r] ?? r}
                        </span>
                      ))}
                    </span>
                  </td>
                </tr>
                {expanded && (
                  <tr className="border-b border-neutral-200 bg-neutral-50">
                    <td colSpan={7} className="px-4 py-3">
                      <ExpandedRow
                        company={c}
                        signals={signalsByCompany.get(c.company_id) ?? []}
                        decisions={decisionsByCompany.get(c.company_id) ?? []}
                      />
                    </td>
                  </tr>
                )}
              </Fragment>
            );
          })}
        </tbody>
      </table>
      {rows.length === 0 && (
        <p className="py-10 text-center text-neutral-400">No companies match the filters.</p>
      )}
    </div>
  );
}

type SourceGroup = { label: string; sources: { url: string; signalTypes: string[] }[] };

function sourceCategory(url: string): string {
  const host = (() => {
    try {
      return new URL(url).hostname.replace(/^www\./, "");
    } catch {
      return url;
    }
  })();
  if (host.includes("sec.gov")) return "SEC filings";
  if (
    host.includes("ashbyhq.com") ||
    host.includes("greenhouse.io") ||
    host.includes("lever.co")
  )
    return "Job postings";
  return "Funding news";
}

function groupSources(signals: SignalRow[]): SourceGroup[] {
  const byUrl = new Map<string, Set<string>>();
  for (const s of signals) {
    if (!s.source_url) continue;
    if (!byUrl.has(s.source_url)) byUrl.set(s.source_url, new Set());
    byUrl.get(s.source_url)!.add(s.signal_type);
  }
  const groups = new Map<string, { url: string; signalTypes: string[] }[]>();
  for (const [url, types] of byUrl) {
    const cat = sourceCategory(url);
    if (!groups.has(cat)) groups.set(cat, []);
    groups.get(cat)!.push({ url, signalTypes: [...types].sort() });
  }
  const order = ["Funding news", "SEC filings", "Job postings"];
  return order
    .filter((label) => groups.has(label))
    .map((label) => ({ label, sources: groups.get(label)! }));
}

function sourceHost(url: string): string {
  try {
    return new URL(url).hostname.replace(/^www\./, "");
  } catch {
    return url;
  }
}

function ExpandedRow({
  company,
  signals,
  decisions,
}: {
  company: RankedCompany;
  signals: SignalRow[];
  decisions: DecisionRow[];
}) {
  return (
    <div className="grid gap-4 md:grid-cols-2">
      <div>
        <h3 className="mb-1 text-xs font-semibold uppercase text-neutral-400">Why</h3>
        <p className="mb-3 text-sm">{company.explanation}</p>

        <h3 className="mb-1 text-xs font-semibold uppercase text-neutral-400">Signals</h3>
        <ul className="space-y-1 text-sm">
          {signals.map((s) => (
            <li key={s.id} className="flex items-baseline gap-2">
              <span className="text-neutral-500">{s.signal_type}:</span>
              <span>{s.value}</span>
              <span className="text-xs text-neutral-400">conf {s.confidence.toFixed(2)}</span>
              {s.needs_review && (
                <span className="rounded bg-amber-100 px-1 text-[11px] text-amber-800">
                  needs review
                </span>
              )}
              {s.source_url && (
                <a
                  href={s.source_url}
                  target="_blank"
                  rel="noreferrer"
                  className="text-xs text-blue-600 underline"
                  onClick={(e) => e.stopPropagation()}
                >
                  source
                </a>
              )}
            </li>
          ))}
          {signals.length === 0 && <li className="text-neutral-400">No signals recorded.</li>}
        </ul>

        <h3 className="mb-1 mt-3 text-xs font-semibold uppercase text-neutral-400">Sources</h3>
        {groupSources(signals).map((group) => (
          <div key={group.label} className="mb-2">
            <p className="text-xs font-medium text-neutral-500">{group.label}</p>
            <ul className="space-y-0.5 text-sm">
              {group.sources.map((s) => (
                <li key={s.url} className="flex items-baseline gap-2">
                  <a
                    href={s.url}
                    target="_blank"
                    rel="noreferrer"
                    className="text-blue-600 underline"
                    onClick={(e) => e.stopPropagation()}
                  >
                    {sourceHost(s.url)}
                  </a>
                  <span className="truncate text-xs text-neutral-400">
                    {s.signalTypes.join(", ")}
                  </span>
                </li>
              ))}
            </ul>
          </div>
        ))}
        {groupSources(signals).length === 0 && (
          <p className="text-sm text-neutral-400">No sources recorded.</p>
        )}
      </div>
      <div>
        <h3 className="mb-1 text-xs font-semibold uppercase text-neutral-400">Rules fired</h3>
        <ul className="mb-3 space-y-0.5 text-sm text-neutral-600">
          {(company.rules_fired ?? []).map((r) => (
            <li key={r}>+ {r}</li>
          ))}
        </ul>

        <h3 className="mb-1 text-xs font-semibold uppercase text-neutral-400">Decision trail</h3>
        <ul className="space-y-1 text-sm">
          {decisions.map((d) => (
            <li key={d.id} className="text-neutral-600">
              <span className="text-neutral-400">r{d.round}</span> {d.question}{" "}
              <span className="font-medium text-neutral-800">{d.answer}</span>{" "}
              <span className="text-xs text-neutral-400">conf {d.confidence.toFixed(2)}</span>
            </li>
          ))}
          {decisions.length === 0 && <li className="text-neutral-400">No decisions logged.</li>}
        </ul>
      </div>
    </div>
  );
}
