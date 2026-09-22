"use client";

import { Fragment, useMemo, useState } from "react";
import { ChevronDown, ChevronUp } from "lucide-react";

import type { Company, Round, Signal } from "@/lib/mock-data";
import CompanyLogo from "./CompanyLogo";

const ROUNDS: Round[] = ["Pre-seed", "Seed", "Series A", "Series B", "Later"];

const ACTION_LABELS: Record<string, string> = {
  check_careers: "checked careers page",
  search_news: "searched news",
  fetch_about: "fetched about page",
};

type SortKey = "score" | "raised" | "days";
type SortDir = "asc" | "desc";

function daysAgo(dateStr: string): number {
  return Math.floor((Date.now() - new Date(dateStr).getTime()) / 86_400_000);
}

function fmtAmount(v: number): string {
  const millions = v / 1_000_000;
  const rounded = Math.round(millions * 10) / 10;
  const text = rounded % 1 === 0 ? rounded.toFixed(0) : rounded.toFixed(1);
  return `$${text}M`;
}

export default function CompanyTable({ companies }: { companies: Company[] }) {
  const [roundFilter, setRoundFilter] = useState<Round | "">("");
  const [minScore, setMinScore] = useState<number>(0);
  const [needsReviewOnly, setNeedsReviewOnly] = useState(false);
  const [sortKey, setSortKey] = useState<SortKey>("score");
  const [sortDir, setSortDir] = useState<SortDir>("desc");
  const [expanded, setExpanded] = useState<string | null>(null);

  const rows = useMemo(() => {
    const filtered = companies.filter((c) => {
      if (roundFilter && c.round !== roundFilter) return false;
      if (c.score < minScore) return false;
      if (needsReviewOnly && !c.signals.some((s) => s.needsReview)) return false;
      return true;
    });

    const dir = sortDir === "asc" ? 1 : -1;
    return [...filtered].sort((a, b) => {
      let av: number;
      let bv: number;
      if (sortKey === "score") {
        av = a.score;
        bv = b.score;
      } else if (sortKey === "raised") {
        av = a.amountRaised;
        bv = b.amountRaised;
      } else {
        av = daysAgo(a.raisedDate);
        bv = daysAgo(b.raisedDate);
      }
      return (av - bv) * dir;
    });
  }, [companies, roundFilter, minScore, needsReviewOnly, sortKey, sortDir]);

  function toggleSort(key: SortKey) {
    if (sortKey === key) {
      setSortDir((d) => (d === "asc" ? "desc" : "asc"));
    } else {
      setSortKey(key);
      setSortDir("desc");
    }
  }

  function SortHeader({
    label,
    sortKeyName,
    hideOnMobile,
  }: {
    label: string;
    sortKeyName: SortKey;
    hideOnMobile?: boolean;
  }) {
    const active = sortKey === sortKeyName;
    return (
      <th className={`py-2 pr-2 font-medium ${hideOnMobile ? "hidden md:table-cell" : ""}`}>
        <button
          type="button"
          onClick={() => toggleSort(sortKeyName)}
          className="flex items-center gap-1 text-left transition-colors hover:text-text"
        >
          {label}
          {active &&
            (sortDir === "asc" ? (
              <ChevronUp size={12} className="text-text" />
            ) : (
              <ChevronDown size={12} className="text-text" />
            ))}
        </button>
      </th>
    );
  }

  return (
    <div>
      <div className="mb-3 flex flex-wrap items-center gap-3 text-xs">
        <select
          className="h-7 rounded border border-border bg-bg px-2 text-text"
          value={roundFilter}
          onChange={(e) => setRoundFilter(e.target.value as Round | "")}
        >
          <option value="">All</option>
          {ROUNDS.map((r) => (
            <option key={r} value={r}>
              {r}
            </option>
          ))}
        </select>

        <label className="flex items-center gap-2 text-text-secondary">
          Min score
          <input
            type="number"
            min={0}
            max={100}
            value={minScore}
            onChange={(e) => setMinScore(Number(e.target.value) || 0)}
            className="h-7 w-16 rounded border border-border bg-bg px-2 text-text"
          />
        </label>

        <label className="flex items-center gap-2 text-text-secondary">
          <input
            type="checkbox"
            checked={needsReviewOnly}
            onChange={(e) => setNeedsReviewOnly(e.target.checked)}
          />
          Needs review only
        </label>

        <span className="ml-auto text-text-secondary">
          Showing {rows.length} of {companies.length}
        </span>
      </div>

      <div className="overflow-x-auto">
        <table className="w-full min-w-[640px] border-collapse text-sm">
          <thead>
            <tr className="border-b border-border text-left text-xs text-text-secondary">
              <th className="w-8 py-2 pr-2 text-right font-medium">#</th>
              <th className="py-2 pr-2 font-medium">Company</th>
              <SortHeader label="Score" sortKeyName="score" />
              <th className="py-2 pr-2 font-medium">Round</th>
              <SortHeader label="Raised" sortKeyName="raised" hideOnMobile />
              <SortHeader label="Days ago" sortKeyName="days" hideOnMobile />
              <th className="py-2 font-medium">Signals</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((c, i) => {
              const isOpen = expanded === c.id;
              const rank = i + 1;
              const days = daysAgo(c.raisedDate);

              return (
                <Fragment key={c.id}>
                  <tr
                    onClick={() => setExpanded(isOpen ? null : c.id)}
                    className={`h-11 cursor-pointer border-b border-border hover:bg-surface ${
                      isOpen ? "border-l-2 border-l-accent" : ""
                    }`}
                  >
                    <td className="py-2 pr-2 text-right text-xs text-text-secondary tabular-nums">
                      {rank}
                    </td>
                    <td className="py-2 pr-2">
                      <div className="flex items-center gap-2">
                        <CompanyLogo domain={c.domain} name={c.name} size={24} />
                        <div>
                          <div className="text-sm font-medium text-text">{c.name}</div>
                          <div className="text-xs text-text-secondary">{c.domain}</div>
                        </div>
                      </div>
                    </td>
                    <td className="py-2 pr-2">
                      <div className="text-base font-semibold tabular-nums text-text">{c.score}</div>
                      <div className="mt-1.5 h-1.5 w-16 rounded bg-border">
                        <div
                          className="h-1.5 rounded bg-accent"
                          style={{ width: `${Math.min(100, Math.max(0, c.score))}%` }}
                        />
                      </div>
                    </td>
                    <td className="py-2 pr-2 text-text">{c.round}</td>
                    <td className="hidden py-2 pr-2 tabular-nums text-text md:table-cell">
                      {fmtAmount(c.amountRaised)}
                    </td>
                    <td className="hidden py-2 pr-2 tabular-nums text-text md:table-cell">
                      {days}
                    </td>
                    <td className="py-2">
                      <RowSignals signals={c.signals} />
                    </td>
                  </tr>
                  {isOpen && (
                    <tr className="border-b border-border border-l-2 border-l-accent bg-surface">
                      <td colSpan={7} className="p-6">
                        <ExpandedRow company={c} />
                      </td>
                    </tr>
                  )}
                </Fragment>
              );
            })}
          </tbody>
        </table>
      </div>

      {rows.length === 0 && (
        <p className="py-10 text-center text-sm text-text-secondary">
          No companies match these filters.
        </p>
      )}
    </div>
  );
}

function RowSignals({ signals }: { signals: Signal[] }) {
  // Funding is already shown in the Round/Raised columns — repeating it as
  // a badge here is redundant. Only needsReview signals get the bordered
  // pill treatment; everything else is plain text so the row reads instead
  // of turning into a wall of chips.
  const relevant = signals.filter((s) => s.type !== "funding");
  const shown = relevant.slice(0, 3);
  const hidden = relevant.length - shown.length;

  return (
    <div className="flex flex-wrap items-center gap-x-2.5 gap-y-1">
      {shown.map((s) =>
        s.needsReview ? (
          <span
            key={s.id}
            className="rounded border border-border bg-review-bg px-1.5 py-0.5 text-xs text-review-text"
          >
            {s.label} (review)
          </span>
        ) : (
          <span key={s.id} className="text-xs text-text-secondary">
            {s.label}
          </span>
        )
      )}
      {hidden > 0 && <span className="text-xs text-text-secondary">+{hidden}</span>}
    </div>
  );
}

function ExpandedRow({ company }: { company: Company }) {
  const [copied, setCopied] = useState(false);
  const total = company.rulesFired.reduce((sum, r) => sum + r.points, 0);

  async function copyEmail() {
    try {
      await navigator.clipboard.writeText(company.draftEmail);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      // clipboard unavailable — nothing to do
    }
  }

  return (
    <div className="grid grid-cols-1 gap-6 md:grid-cols-2">
      <div>
        <div className="flex items-center gap-3">
          <CompanyLogo domain={company.domain} name={company.name} size={40} />
          <div>
            <div className="text-sm font-medium text-text">{company.name}</div>
            <a
              href={`https://${company.domain}`}
              target="_blank"
              rel="noreferrer"
              onClick={(e) => e.stopPropagation()}
              className="text-xs text-accent"
            >
              {company.domain}
            </a>
          </div>
        </div>
        <p className="mt-3 text-sm text-text">{company.explanation}</p>

        <h3 className="mb-1 mt-4 text-[11px] font-semibold uppercase tracking-wide text-text-secondary">Why this score</h3>
        <ul className="text-sm">
          {company.rulesFired.map((r) => (
            <li key={r.rule} className="flex justify-between py-0.5">
              <span className="text-text">{r.rule}</span>
              <span className="tabular-nums text-text">+{r.points}</span>
            </li>
          ))}
        </ul>
        <div className="mt-1 flex justify-between border-t border-border pt-1 text-sm font-semibold">
          <span className="text-text">Total</span>
          <span className="tabular-nums text-text">{total}</span>
        </div>

        <h3 className="mb-1 mt-4 text-[11px] font-semibold uppercase tracking-wide text-text-secondary">Signals</h3>
        <ul className="space-y-1 text-sm">
          {company.signals.map((s) => (
            <li key={s.id} className="flex flex-wrap items-baseline gap-2">
              <span className="text-text">{s.label}</span>
              <span className="text-xs tabular-nums text-text-secondary">
                {s.confidence.toFixed(2)}
              </span>
              {s.needsReview && (
                <span className="rounded border border-border bg-review-bg px-1.5 py-0.5 text-xs text-review-text">
                  review
                </span>
              )}
              <a
                href={s.sourceUrl}
                target="_blank"
                rel="noreferrer"
                onClick={(e) => e.stopPropagation()}
                className="text-xs text-accent"
              >
                source
              </a>
            </li>
          ))}
        </ul>
      </div>

      <div>
        <h3 className="mb-1 text-[11px] font-semibold uppercase tracking-wide text-text-secondary">Investigation</h3>
        {company.decisions.length === 0 ? (
          <p className="text-sm text-text-secondary">Scored on first pass</p>
        ) : (
          <ol className="space-y-1 text-sm text-text">
            {company.decisions.map((d) => (
              <li key={d.round}>
                Round {d.round} - {d.question} {d.answer} ({d.confidence.toFixed(2)}) -&gt;{" "}
                {d.actionChosen ? ACTION_LABELS[d.actionChosen] ?? d.actionChosen : "scored"}
              </li>
            ))}
          </ol>
        )}

        <h3 className="mb-1 mt-4 text-[11px] font-semibold uppercase tracking-wide text-text-secondary">Draft email</h3>
        <div className="relative rounded border border-border bg-bg p-3 pt-8">
          <button
            type="button"
            onClick={(e) => {
              e.stopPropagation();
              copyEmail();
            }}
            className="absolute right-2 top-2 text-xs text-accent"
          >
            {copied ? "Copied" : "Copy"}
          </button>
          <p className="whitespace-pre-wrap text-sm text-text">{company.draftEmail}</p>
        </div>
      </div>
    </div>
  );
}
