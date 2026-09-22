import CompanyTable from "@/components/CompanyTable";
import { fetchDashboardData } from "@/lib/data";
import { exactTime, relativeTime } from "@/lib/format";

// Always re-read Postgres so "last updated" and the ranking stay current.
export const dynamic = "force-dynamic";

export default async function Page() {
  const { companies, lastUpdated, isSampleData } = await fetchDashboardData();
  const relative = relativeTime(lastUpdated);

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
            className="w-full whitespace-nowrap pl-10 text-xs text-text-secondary sm:w-auto sm:shrink-0 sm:pl-0"
            title={exactTime(lastUpdated)}
          >
            {isSampleData
              ? "Sample data"
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
