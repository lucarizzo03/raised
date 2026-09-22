import CompanyTable from "@/components/CompanyTable";
import { companies } from "@/lib/mock-data";

export default function Page() {
  return (
    <div className="min-h-screen">
      <header className="sticky top-0 z-30 border-b border-border/70 bg-canvas/70 backdrop-blur-xl">
        <div className="mx-auto flex max-w-[1240px] items-center justify-between gap-4 px-6 py-3.5">
          <div className="flex items-center gap-3">
            <span className="flex h-7 w-7 items-center justify-center rounded-md bg-accent text-[13px] font-bold text-white">
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
          <span className="text-xs text-text-secondary">Updated 3h ago</span>
        </div>
      </header>

      <main className="mx-auto max-w-[1240px] px-6 py-8">
        <CompanyTable companies={companies} />
      </main>
    </div>
  );
}
