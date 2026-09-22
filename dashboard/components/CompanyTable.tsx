"use client";

import { Fragment, useEffect, useMemo, useRef, useState } from "react";
import { ChevronDown, ChevronUp } from "lucide-react";

import type { Badge, Company, Round } from "@/lib/types";
import { daysAgo, fmtAmount } from "@/lib/format";
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

// Default list length; "Show all" lifts it.
const TOP_N = 25;

const fieldClass =
  "h-9 min-w-0 rounded-md border border-border bg-surface px-3 text-sm leading-5 text-text shadow-sm transition-all duration-200 hover:border-text-secondary/40 focus:border-accent focus:outline-none focus:ring-2 focus:ring-accent/25";

const actionButtonClass =
  "inline-flex h-9 shrink-0 items-center justify-center whitespace-nowrap rounded-sm border border-border bg-surface px-3 text-xs font-medium leading-none text-accent transition-all duration-200 hover:bg-hover active:scale-95 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/40";

export default function CompanyTable({ companies }: { companies: Company[] }) {
  const [roundFilter, setRoundFilter] = useState<Round | "">("");
  const [minScore, setMinScore] = useState<number>(0);
  const [needsReviewOnly, setNeedsReviewOnly] = useState(false);
  const [sortKey, setSortKey] = useState<SortKey>("score");
  const [sortDir, setSortDir] = useState<SortDir>("desc");
  const [expanded, setExpanded] = useState<string | null>(null);
  const [exiting, setExiting] = useState<string | null>(null);
  const [showAll, setShowAll] = useState(false);
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
        av = a.amountRaised ?? -1;
        bv = b.amountRaised ?? -1;
      } else {
        // Undated raises sort last in either direction.
        av = daysAgo(a.raisedDate) ?? Number.MAX_SAFE_INTEGER;
        bv = daysAgo(b.raisedDate) ?? Number.MAX_SAFE_INTEGER;
      }
      return (av - bv) * dir;
    });
  }, [companies, roundFilter, minScore, needsReviewOnly, sortKey, sortDir]);

  const visible = showAll ? rows : rows.slice(0, TOP_N);

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
      <th className={`w-24 py-3 pr-3 align-middle font-medium ${hideOnMobile ? "hidden md:table-cell" : ""}`}>
        <button
          type="button"
          onClick={() => toggleSort(sortKeyName)}
          className="-ml-1.5 flex h-8 items-center gap-1.5 whitespace-nowrap rounded-sm px-1.5 text-left leading-none transition-all duration-200 hover:bg-hover hover:text-text active:scale-95 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/40"
        >
          {label}
          <span aria-hidden="true" className="flex h-3 w-3 shrink-0 items-center justify-center">
            {active &&
              (sortDir === "asc" ? (
                <ChevronUp size={12} className="text-accent" />
              ) : (
                <ChevronDown size={12} className="text-accent" />
              ))}
          </span>
        </button>
      </th>
    );
  }

  return (
    <div className="overflow-hidden rounded-lg border border-border bg-surface shadow-sm">
      <div className="grid grid-cols-2 items-end gap-3 border-b border-border px-4 py-4 text-sm sm:px-5 md:flex md:flex-wrap md:gap-4">
        <label className="flex min-w-0 flex-col gap-1.5 text-xs text-text-secondary md:w-40">
          Round
          <select
            className={`${fieldClass} w-full`}
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
        </label>

        <label className="flex min-w-0 flex-col gap-1.5 text-xs text-text-secondary md:w-24">
          Min score
          <input
            type="number"
            min={0}
            max={100}
            value={minScore}
            onChange={(e) => setMinScore(Number(e.target.value) || 0)}
            className={`${fieldClass} w-full`}
          />
        </label>

        <div className="col-span-2 flex min-w-0 items-center justify-between gap-2 sm:gap-3 md:contents">
          <label className="flex h-9 shrink-0 cursor-pointer items-center gap-2 whitespace-nowrap text-xs text-text-secondary sm:text-sm">
            <input
              type="checkbox"
              checked={needsReviewOnly}
              onChange={(e) => setNeedsReviewOnly(e.target.checked)}
              className="h-4 w-4 shrink-0 accent-accent"
            />
            Needs review only
          </label>

          <span className="flex h-9 shrink-0 items-center whitespace-nowrap text-xs tabular-nums text-text-secondary md:ml-auto">
            Showing {visible.length} of {companies.length}
          </span>
        </div>
      </div>

      <div className="@container overflow-x-auto">
        <table className="w-full min-w-[680px] table-fixed border-collapse text-sm md:min-w-[960px]">
          <thead>
            <tr className="h-14 border-b border-border text-left text-xs leading-none text-text-secondary">
              <th className="w-12 py-3 pl-4 pr-2 text-right align-middle font-medium sm:pl-5">#</th>
              <th className="w-56 py-3 pr-3 align-middle font-medium lg:w-64">Company</th>
              <SortHeader label="Score" sortKeyName="score" />
              <th className="w-24 whitespace-nowrap py-3 pr-3 align-middle font-medium">Round</th>
              <SortHeader label="Raised" sortKeyName="raised" hideOnMobile />
              <SortHeader label="Days ago" sortKeyName="days" hideOnMobile />
              <th className="py-3 pr-3 align-middle font-medium">Signals</th>
              <th className="w-12 py-3" />
            </tr>
          </thead>
          <tbody>
            {visible.map((c, i) => {
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
                    className={`group h-14 cursor-pointer border-b border-border transition-colors duration-200 hover:bg-hover focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-accent/50 ${
                      isOpen ? "bg-hover" : ""
                    }`}
                  >
                    <td
                      className={`py-2 pl-4 pr-2 text-right align-middle text-xs tabular-nums sm:pl-5 ${
                        isOpen ? "text-accent" : "text-text-secondary"
                      }`}
                    >
                      {rank}
                    </td>
                    <td className="py-2 pr-3 align-middle">
                      <div className="flex items-center gap-2.5">
                        <CompanyLogo domain={c.domain} name={c.name} size={24} verified={c.domainVerified} />
                        <div className="min-w-0">
                          <div className="break-words text-sm font-medium leading-5 text-text">{c.name}</div>
                          <div className="truncate text-xs leading-4 text-text-secondary" title={c.domain ?? undefined}>{c.domain}</div>
                        </div>
                      </div>
                    </td>
                    <td className="py-2 pr-3 align-middle">
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
                    <td className="whitespace-nowrap py-2 pr-3 align-middle text-text">{c.round}</td>
                    <td className="hidden whitespace-nowrap py-2 pr-3 align-middle tabular-nums text-text md:table-cell">
                      {fmtAmount(c.amountRaised)}
                    </td>
                    <td className="hidden whitespace-nowrap py-2 pr-3 align-middle tabular-nums text-text md:table-cell">
                      {days ?? "—"}
                    </td>
                    <td className="py-2 pr-3 align-middle">
                      <RowBadges badges={c.badges} />
                    </td>
                    <td className="px-2 py-2 text-center align-middle">
                      <span className="inline-flex h-8 w-8 items-center justify-center rounded-sm">
                        <ChevronDown
                          size={15}
                          className={`text-text-secondary/60 transition-all duration-300 ease-spring group-hover:text-text-secondary ${
                            isOpen ? "rotate-180 text-accent" : ""
                          }`}
                        />
                      </span>
                    </td>
                  </tr>
                  {isMounted && (
                    <tr className="border-b border-border bg-canvas">
                      <td colSpan={8} className="p-0">
                        <Disclosure open={isOpen}>
                          <div className="w-full max-w-[100cqw] px-4 py-6 sm:px-5">
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

      {rows.length > TOP_N && (
        <div className="flex items-center justify-center border-t border-border px-4 py-3 sm:px-5">
          <button
            type="button"
            onClick={() => setShowAll((v) => !v)}
            className={`${actionButtonClass} min-w-36`}
          >
            {showAll ? `Show top ${TOP_N}` : `Show all (${rows.length})`}
          </button>
        </div>
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

function RowBadges({ badges }: { badges: Badge[] }) {
  // Findings only. Raise recency and round are deliberately absent - they
  // already have their own columns. Order is set in lib/map.ts.
  const shown = badges.slice(0, 3);
  const hidden = badges.length - shown.length;

  return (
    <div className="flex flex-wrap items-center gap-x-2.5 gap-y-1">
      {shown.map((b) =>
        b.needsReview ? (
          <span
            key={b.id}
            className="rounded-full bg-review-bg px-2 py-0.5 text-xs text-review-text"
          >
            {b.label} (review)
          </span>
        ) : (
          <span key={b.id} className="text-xs text-text-secondary">
            {b.label}
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
    <div className="grid min-w-0 grid-cols-1 gap-8 md:grid-cols-2">
      <div className="min-w-0">
        <div className="flex items-center gap-3">
          <CompanyLogo
            domain={company.domain}
            name={company.name}
            size={40}
            verified={company.domainVerified}
          />
          <div>
            <div className="text-sm font-medium text-text">{company.name}</div>
            {company.domain ? (
              <a
                href={`https://${company.domain}`}
                target="_blank"
                rel="noreferrer"
                onClick={(e) => e.stopPropagation()}
                className="text-xs text-accent transition-opacity hover:opacity-70"
              >
                {company.domain}
              </a>
            ) : (
              <span className="text-xs text-text-secondary">domain unverified</span>
            )}
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
            <li key={s.id} className="grid grid-cols-[minmax(0,1fr)_2rem_3rem_2.5rem] items-start gap-x-2">
              <span className="min-w-0 break-words py-0.5 text-text">{s.label}</span>
              <span className="text-right text-xs leading-6 tabular-nums text-text-secondary">
                {s.confidence.toFixed(2)}
              </span>
              <span className="flex h-6 items-center justify-center">
                {s.needsReview && (
                  <span className="rounded-full bg-review-bg px-2 py-0.5 text-xs text-review-text">
                    review
                  </span>
                )}
              </span>
              <span className="flex h-6 items-center justify-end">
                {s.sourceUrl && (
                  <a
                    href={s.sourceUrl}
                    target="_blank"
                    rel="noreferrer"
                    onClick={(e) => e.stopPropagation()}
                    className="inline-flex h-6 items-center text-xs text-accent transition-opacity hover:opacity-70"
                  >
                    source
                  </a>
                )}
              </span>
            </li>
          ))}
        </ul>
      </div>

      <div className="min-w-0">
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

        <div className="mt-5 overflow-hidden rounded-md border border-border bg-surface shadow-sm">
          <div className="flex min-h-14 items-center justify-between gap-3 border-b border-border px-4 py-2">
            <h3 className="text-[11px] font-semibold uppercase tracking-wide text-text-secondary">
              Draft email
            </h3>
            <button
              type="button"
              onClick={(e) => {
                e.stopPropagation();
                copyEmail();
              }}
              className={`${actionButtonClass} min-w-20`}
            >
              {copied ? "Copied" : "Copy"}
            </button>
          </div>
          <p className="whitespace-pre-wrap break-words p-4 text-sm leading-relaxed text-text">
            {company.draftEmail}
          </p>
        </div>
      </div>
    </div>
  );
}
