import CompanyTable from "@/components/CompanyTable";
import { companies } from "@/lib/mock-data";

export default function Page() {
  return (
    <main className="mx-auto max-w-[1240px] px-6 py-10 md:py-14">
      <header className="mb-6 flex items-end justify-between gap-4">
        <div>
          <h1 className="text-[28px] font-semibold tracking-tight text-text">Raised</h1>
          <p className="mt-1 text-sm text-text-secondary">
            Companies worth reaching out to this week.
          </p>
        </div>
        <p className="whitespace-nowrap pb-1 text-xs text-text-secondary">Last updated: 3h ago</p>
      </header>
      <CompanyTable companies={companies} />
    </main>
  );
}
