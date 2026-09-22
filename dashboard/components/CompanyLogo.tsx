"use client";

import { useState } from "react";

function initials(name: string): string {
  return name
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((w) => w[0])
    .join("")
    .toUpperCase();
}

export default function CompanyLogo({
  domain,
  name,
  size,
  verified,
}: {
  domain: string | null;
  name: string;
  size: number;
  verified: boolean;
}) {
  // 0 = Clearbit, 1 = Google favicons, 2 = initials fallback
  const [step, setStep] = useState(0);
  // Radius scales with the box so the 24px and 40px marks share one
  // app-icon geometry instead of one reading as a circle.
  const boxStyle = { width: size, height: size, borderRadius: Math.round(size * 0.24) };

  // An unverified domain may belong to a different company entirely, so we
  // never request a logo for one - that is how other companies' marks ended
  // up on these rows. Straight to initials.
  if (!verified || !domain || step >= 2) {
    return (
      <span
        style={boxStyle}
        className="flex shrink-0 items-center justify-center border border-border bg-initials-bg text-[11px] font-semibold text-text-secondary"
      >
        {initials(name)}
      </span>
    );
  }

  const src =
    step === 0
      ? `https://logo.clearbit.com/${domain}`
      : `https://www.google.com/s2/favicons?domain=${domain}&sz=128`;

  // Advance past a failed load or Google's generic 16x16 globe icon (it
  // returns 200 with that placeholder — ignoring sz=128 — instead of
  // erroring for domains it has no favicon for). Checked on load/error AND
  // via ref: a browser that already has the URL cached (failed or not)
  // resolves it before React attaches the listener, so onLoad/onError never
  // fire for it — the ref catches that by checking img.complete on mount.
  function evaluate(img: HTMLImageElement, atStep: number) {
    if (!img.complete) return;
    if (img.naturalWidth === 0 || (atStep === 1 && img.naturalWidth < 32)) {
      setStep((s) => (s === atStep ? s + 1 : s));
    }
  }

  // bg-logo-plate is a light plate behind the mark: most company logos are
  // dark-on-transparent and would disappear against the dark theme's surfaces.
  return (
    // eslint-disable-next-line @next/next/no-img-element
    <img
      key={step}
      src={src}
      alt=""
      style={boxStyle}
      className="shrink-0 border border-border bg-logo-plate object-contain p-[3px]"
      onError={(e) => evaluate(e.currentTarget, step)}
      onLoad={(e) => evaluate(e.currentTarget, step)}
      ref={(node) => {
        if (node) evaluate(node, step);
      }}
    />
  );
}
