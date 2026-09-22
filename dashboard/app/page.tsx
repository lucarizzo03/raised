import { fetchDashboardData } from "@/lib/data";
import CompanyTable from "@/components/CompanyTable";

export const dynamic = "force-dynamic";

export default async function Page() {
  const data = await fetchDashboardData();

  return (
    <main className="mx-auto max-w-6xl px-4 py-8">
      <header className="mb-6 flex items-baseline justify-between">
        <div>
          <h1 className="text-xl font-semibold">Raised</h1>
          <p className="text-sm text-neutral-500">
            Companies that just raised and are starting to hire sales.
          </p>
        </div>
        <p className="text-xs text-neutral-400">
          {data.isSampleData
            ? "Sample data — set SUPABASE_URL / SUPABASE_ANON_KEY"
            : `Last updated: ${data.runDate ?? "never"}`}
        </p>
      </header>
      <CompanyTable
        companies={data.companies}
        signals={data.signals}
        decisions={data.decisions}
      />
    </main>
  );
}
