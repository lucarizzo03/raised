"use client";

import { Fragment, useEffect, useMemo, useRef, useState } from "react";
import { ChevronDown, ChevronUp } from "lucide-react";

import type { Company, Round, Signal } from "@/lib/mock-data";
import CompanyLogo from "./CompanyLogo";

const ROUNDS: Round[] = ["Pre-seed", "Seed", "Series A", "Series B", "Later"];

const ACTION_LABELS: Record<string, string> = {
  check_careers: "checked careers page",
  search_news: "searched news",
  fetch_about: "fetched about page",
};

// Matches the disclosure transition below; the exiting row unmounts once the
// collapse has finished playing.
const COLLAPSE_MS = 320;

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

const fieldClass =
  "h-9 rounded-md border border-border bg-surface px-3 text-text shadow-sm transition-all duration-200 hover:border-text-secondary/40 focus:border-accent focus:outline-none focus:ring-2 focus:ring-accent/25";

export default function CompanyTable({ companies }: { companies: Company[] }) {
  const [roundFilter, setRoundFilter] = useState<Round | "">("");
  const [minScore, setMinScore] = useState<number>(0);
  const [needsReviewOnly, setNeedsReviewOnly] = useState(false);
  const [sortKey, setSortKey] = useState<SortKey>("score");
  const [sortDir, setSortDir] = useState<SortDir>("desc");
  const [expanded, setExpanded] = useState<string | null>(null);
  const [exiting, setExiting] = useState<string | null>(null);
  const exitTimer = useRef<number | null>(null);

  useEffect(() => {
    return () => {
      if (exitTimer.current) window.clearTimeout(exitTimer.current);
    };
  }, []);

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

  function toggleRow(id: string) {
    if (exitTimer.current) window.clearTimeout(exitTimer.current);

    if (expanded === id) {
      // Keep the panel mounted so the collapse can animate out.
      setExpanded(null);
      setExiting(id);
      exitTimer.current = window.setTimeout(() => setExiting(null), COLLAPSE_MS);
      return;
    }

    setExpanded(id);
    setExiting(null);
  }

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
      <th className={`py-3 pr-2 font-medium ${hideOnMobile ? "hidden md:table-cell" : ""}`}>
        <button
          type="button"
          onClick={() => toggleSort(sortKeyName)}
          className="-mx-1.5 flex items-center gap-1 rounded-sm px-1.5 py-1 text-left transition-all duration-200 hover:bg-hover hover:text-text active:scale-95 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/40"
        >
          {label}
          {active &&
            (sortDir === "asc" ? (
              <ChevronUp size={12} className="text-accent" />
            ) : (
              <ChevronDown size={12} className="text-accent" />
            ))}
        </button>
      </th>
    );
  }

  return (
    <div className="overflow-hidden rounded-lg border border-border bg-surface shadow-sm">
      <div className="flex flex-wrap items-center gap-3 border-b border-border px-5 py-4 text-sm">
        <select
          className={fieldClass}
          value={roundFilter}
          onChange={(e) => setRoundFilter(e.target.value as Round | "")}
        >
          <option value="">All rounds</option>
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
            className={`${fieldClass} w-20`}
          />
        </label>

        <label className="flex cursor-pointer items-center gap-2 text-text-secondary">
          <input
            type="checkbox"
            checked={needsReviewOnly}
            onChange={(e) => setNeedsReviewOnly(e.target.checked)}
            className="h-4 w-4 accent-accent"
          />
          Needs review only
        </label>

        <span className="ml-auto text-xs tabular-nums text-text-secondary">
          Showing {rows.length} of {companies.length}
        </span>
      </div>

      <div className="overflow-x-auto">
        <table className="w-full min-w-[680px] border-collapse text-sm">
          <thead>
            <tr className="border-b border-border text-left text-xs text-text-secondary">
              <th className="w-8 py-3 pl-5 pr-2 text-right font-medium">#</th>
              <th className="py-3 pr-2 font-medium">Company</th>
              <SortHeader label="Score" sortKeyName="score" />
              <th className="py-3 pr-2 font-medium">Round</th>
              <SortHeader label="Raised" sortKeyName="raised" hideOnMobile />
              <SortHeader label="Days ago" sortKeyName="days" hideOnMobile />
              <th className="py-3 pr-2 font-medium">Signals</th>
              <th className="w-9 py-3 pr-4" />
            </tr>
          </thead>
          <tbody>
            {rows.map((c, i) => {
              const isOpen = expanded === c.id;
              const isMounted = isOpen || exiting === c.id;
              const rank = i + 1;
              const days = daysAgo(c.raisedDate);

              return (
                <Fragment key={c.id}>
                  <tr
                    onClick={() => toggleRow(c.id)}
                    onKeyDown={(e) => {
                      if (e.key === "Enter" || e.key === " ") {
                        e.preventDefault();
                        toggleRow(c.id);
                      }
                    }}
                    tabIndex={0}
                    role="button"
                    aria-expanded={isOpen}
                    aria-label={`${c.name}, score ${c.score}`}
                    className={`group h-12 cursor-pointer border-b border-border transition-colors duration-200 hover:bg-hover focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-accent/50 ${
                      isOpen ? "bg-hover" : ""
                    }`}
                  >
                    <td
                      className={`py-2 pl-5 pr-2 text-right text-xs tabular-nums ${
                        isOpen ? "text-accent" : "text-text-secondary"
                      }`}
                    >
                      {rank}
                    </td>
                    <td className="py-2 pr-2">
                      <div className="flex items-center gap-2.5">
                        <CompanyLogo domain={c.domain} name={c.name} size={24} />
                        <div>
                          <div className="text-sm font-medium text-text">{c.name}</div>
                          <div className="text-xs text-text-secondary">{c.domain}</div>
                        </div>
                      </div>
                    </td>
                    <td className="py-2 pr-2">
                      <div className="text-base font-semibold tabular-nums text-text">
                        {c.score}
                      </div>
                      <div className="mt-1.5 h-1.5 w-16 overflow-hidden rounded-full bg-border">
                        <div
                          className="h-1.5 rounded-full bg-accent transition-[width] duration-500 ease-spring"
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
                    <td className="py-2 pr-2">
                      <RowSignals signals={c.signals} />
                    </td>
                    <td className="py-2 pr-4 text-right">
                      <ChevronDown
                        size={15}
                        className={`ml-auto text-text-secondary/60 transition-all duration-300 ease-spring group-hover:text-text-secondary ${
                          isOpen ? "rotate-180 text-accent" : ""
                        }`}
                      />
                    </td>
                  </tr>
                  {isMounted && (
                    <tr className="border-b border-border bg-canvas">
                      <td colSpan={8} className="p-0">
                        <Disclosure open={isOpen}>
                          <div className="px-6 py-6">
                            <ExpandedRow company={c} />
                          </div>
                        </Disclosure>
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
        <p className="animate-rise py-12 text-center text-sm text-text-secondary">
          No companies match these filters.
        </p>
      )}
    </div>
  );
}

/**
 * Height-animated disclosure. The 0fr -> 1fr grid row transition is the one
 * way to animate to an unknown content height without measuring it, so the
 * panel opens and closes on the same spring curve as the chevron.
 */
function Disclosure({ open, children }: { open: boolean; children: React.ReactNode }) {
  const [entered, setEntered] = useState(false);

  useEffect(() => {
    // One frame at 0fr before flipping, otherwise it mounts fully open and
    // there is nothing to transition from.
    const id = requestAnimationFrame(() => setEntered(true));
    return () => cancelAnimationFrame(id);
  }, []);

  const show = open && entered;

  return (
    <div
      className={`grid transition-all duration-[320ms] ease-spring ${
        show ? "grid-rows-[1fr] opacity-100" : "grid-rows-[0fr] opacity-0"
      }`}
    >
      <div className="overflow-hidden">{children}</div>
    </div>
  );
}

function RowSignals({ signals }: { signals: Signal[] }) {
  // Funding is already shown in the Round/Raised columns — repeating it as
  // a badge here is redundant. Only needsReview signals get the pill
  // treatment; everything else is plain text so the row reads instead of
  // turning into a wall of chips.
  const relevant = signals.filter((s) => s.type !== "funding");
  const shown = relevant.slice(0, 3);
  const hidden = relevant.length - shown.length;

  return (
    <div className="flex flex-wrap items-center gap-x-2.5 gap-y-1">
      {shown.map((s) =>
        s.needsReview ? (
          <span
            key={s.id}
            className="rounded-full bg-review-bg px-2 py-0.5 text-xs text-review-text"
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
    <div className="grid grid-cols-1 gap-8 md:grid-cols-2">
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
              className="text-xs text-accent transition-opacity hover:opacity-70"
            >
              {company.domain}
            </a>
          </div>
        </div>
        <p className="mt-3 text-sm leading-relaxed text-text">{company.explanation}</p>

        <h3 className="mb-1.5 mt-5 text-[11px] font-semibold uppercase tracking-wide text-text-secondary">
          Why this score
        </h3>
        <ul className="text-sm">
          {company.rulesFired.map((r) => (
            <li key={r.rule} className="flex justify-between py-1">
              <span className="text-text">{r.rule}</span>
              <span className="tabular-nums text-text">+{r.points}</span>
            </li>
          ))}
        </ul>
        <div className="mt-1 flex justify-between border-t border-border pt-2 text-sm font-semibold">
          <span className="text-text">Total</span>
          <span className="tabular-nums text-text">{total}</span>
        </div>

        <h3 className="mb-1.5 mt-5 text-[11px] font-semibold uppercase tracking-wide text-text-secondary">
          Signals
        </h3>
        <ul className="space-y-1.5 text-sm">
          {company.signals.map((s) => (
            <li key={s.id} className="flex flex-wrap items-baseline gap-2">
              <span className="text-text">{s.label}</span>
              <span className="text-xs tabular-nums text-text-secondary">
                {s.confidence.toFixed(2)}
              </span>
              {s.needsReview && (
                <span className="rounded-full bg-review-bg px-2 py-0.5 text-xs text-review-text">
                  review
                </span>
              )}
              <a
                href={s.sourceUrl}
                target="_blank"
                rel="noreferrer"
                onClick={(e) => e.stopPropagation()}
                className="text-xs text-accent transition-opacity hover:opacity-70"
              >
                source
              </a>
            </li>
          ))}
        </ul>
      </div>

      <div>
        <h3 className="mb-1.5 text-[11px] font-semibold uppercase tracking-wide text-text-secondary">
          Investigation
        </h3>
        {company.decisions.length === 0 ? (
          <p className="text-sm text-text-secondary">Scored on first pass</p>
        ) : (
          <ol className="space-y-1.5 text-sm text-text">
            {company.decisions.map((d) => (
              <li key={d.round}>
                Round {d.round} - {d.question} {d.answer} ({d.confidence.toFixed(2)}) -&gt;{" "}
                {d.actionChosen ? ACTION_LABELS[d.actionChosen] ?? d.actionChosen : "scored"}
              </li>
            ))}
          </ol>
        )}

        <h3 className="mb-1.5 mt-5 text-[11px] font-semibold uppercase tracking-wide text-text-secondary">
          Draft email
        </h3>
        <div className="relative rounded-md border border-border bg-surface p-4 pt-9 shadow-sm">
          <button
            type="button"
            onClick={(e) => {
              e.stopPropagation();
              copyEmail();
            }}
            className="absolute right-3 top-3 rounded-sm px-2 py-0.5 text-xs text-accent transition-all duration-200 hover:bg-hover active:scale-95 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/40"
          >
            {copied ? "Copied" : "Copy"}
          </button>
          <p className="whitespace-pre-wrap text-sm leading-relaxed text-text">
            {company.draftEmail}
          </p>
        </div>
      </div>
    </div>
  );
}
