import CompanyTable from "@/components/CompanyTable";
import { companies } from "@/lib/mock-data";

export default function Page() {
  return (
    <main className="mx-auto max-w-[1200px] px-6 py-8">
      <header className="mb-6 flex items-baseline justify-between border-b border-border pb-4">
        <h1 className="text-xl font-semibold text-text">Raised</h1>
        <p className="text-xs text-text-secondary">Last updated: 3h ago</p>
      </header>
      <CompanyTable companies={companies} />
    </main>
  );
}
