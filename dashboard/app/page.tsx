import CompanyTable from "@/components/CompanyTable";
import { fetchDashboardData } from "@/lib/data";
import { exactTime, relativeTime } from "@/lib/format";

// Always re-read Postgres so "last updated" and the ranking stay current.
export const dynamic = "force-dynamic";

// The pipeline runs daily; past this, say so instead of looking current.
const STALE_AFTER_MS = 36 * 60 * 60 * 1000;

export default async function Page() {
  const { companies, lastUpdated, lastRunAt, isSampleData } = await fetchDashboardData();
  // Prefer the pipeline's heartbeat; fall back to the newest signal.
  const updatedAt = lastRunAt ?? lastUpdated;
  const relative = relativeTime(updatedAt);
  const stale =
    !isSampleData && lastRunAt !== null && Date.now() - new Date(lastRunAt).getTime() > STALE_AFTER_MS;

  return (
    <div className="min-h-screen">
      <header className="sticky top-0 z-30 border-b border-border/70 bg-canvas/70 backdrop-blur-xl">
        <div className="mx-auto flex max-w-[1240px] flex-wrap items-center justify-between gap-x-4 gap-y-2 px-4 py-3.5 sm:px-6">
          <div className="flex min-w-0 items-center gap-3">
            <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-md bg-accent text-[13px] font-bold text-white">
              R
            </span>
            <div>
              <h1 className="text-[15px] font-semibold leading-tight tracking-tight text-text">
                Raised
              </h1>
              <p className="text-xs leading-tight text-text-secondary">
                Companies worth reaching out to this week
              </p>
            </div>
          </div>
          <span
            className={`w-full whitespace-nowrap pl-10 text-xs sm:w-auto sm:shrink-0 sm:pl-0 ${
              stale ? "text-review-text" : "text-text-secondary"
            }`}
            title={exactTime(updatedAt)}
            data-stale={stale || undefined}
          >
            {isSampleData
              ? "Sample data"
              : stale
                ? `Last run ${relative} · pipeline may be stalled`
                : relative
                  ? `Updated ${relative}`
                  : "Never updated"}
          </span>
        </div>
      </header>

      <main className="mx-auto max-w-[1240px] px-4 py-6 sm:px-6 sm:py-8">
        <CompanyTable companies={companies} />
      </main>
    </div>
  );
}
