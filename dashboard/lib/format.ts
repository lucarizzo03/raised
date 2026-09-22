/** $50M (not $50.0M), $4.5M, $3.9B, $310K. */
export function fmtAmount(v: number | null): string {
  if (v === null || Number.isNaN(v)) return "—";
  const [div, suffix] =
    Math.abs(v) >= 1_000_000_000
      ? [1_000_000_000, "B"]
      : Math.abs(v) >= 1_000_000
        ? [1_000_000, "M"]
        : Math.abs(v) >= 1_000
          ? [1_000, "K"]
          : [1, ""];
  const scaled = Math.round((v / div) * 10) / 10;
  const text = scaled % 1 === 0 ? scaled.toFixed(0) : scaled.toFixed(1);
  return `$${text}${suffix}`;
}

export function daysAgo(dateStr: string | null): number | null {
  if (!dateStr) return null;
  const ms = Date.now() - new Date(dateStr).getTime();
  if (Number.isNaN(ms)) return null;
  return Math.floor(ms / 86_400_000);
}

const UNITS: [number, Intl.RelativeTimeFormatUnit][] = [
  [60, "second"],
  [60, "minute"],
  [24, "hour"],
  [7, "day"],
  [4.348, "week"],
  [12, "month"],
];

/** "2 hours ago" */
export function relativeTime(iso: string | null): string | null {
  if (!iso) return null;
  const then = new Date(iso).getTime();
  if (Number.isNaN(then)) return null;
  let value = (then - Date.now()) / 1000;
  let unit: Intl.RelativeTimeFormatUnit = "second";
  for (const [step, next] of UNITS) {
    if (Math.abs(value) < step) break;
    value /= step;
    unit = next;
  }
  return new Intl.RelativeTimeFormat("en", { numeric: "auto" }).format(
    Math.round(value),
    unit
  );
}

/** Exact timestamp for the title attribute. */
export function exactTime(iso: string | null): string {
  if (!iso) return "";
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? "" : d.toUTCString();
}
