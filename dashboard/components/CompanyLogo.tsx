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
}: {
  domain: string;
  name: string;
  size: number;
}) {
  // 0 = Clearbit, 1 = Google favicons, 2 = initials fallback
  const [step, setStep] = useState(0);
  const boxStyle = { width: size, height: size };

  if (step >= 2) {
    return (
      <span
        style={boxStyle}
        className="flex shrink-0 items-center justify-center rounded border border-border bg-initials-bg text-[11px] font-semibold text-text-secondary"
      >
        {initials(name)}
      </span>
    );
  }

  const src =
    step === 0
      ? `https://logo.clearbit.com/${domain}`
      : `https://www.google.com/s2/favicons?domain=${domain}&sz=128`;

  // Google's favicon endpoint returns 200 with a generic 16x16 globe icon
  // (ignoring sz=128) for domains it has no favicon for, instead of
  // erroring — treat that as a miss and fall through to initials. Checked
  // both on load and via ref (for images the browser already had cached,
  // where the "load" event fires before React attaches the listener).
  function checkFavicon(img: HTMLImageElement) {
    if (step === 1 && img.naturalWidth > 0 && img.naturalWidth < 32) {
      setStep((s) => s + 1);
    }
  }

  return (
    // eslint-disable-next-line @next/next/no-img-element
    <img
      key={step}
      src={src}
      alt=""
      style={boxStyle}
      className="shrink-0 border border-border object-contain"
      onError={() => setStep((s) => s + 1)}
      onLoad={(e) => checkFavicon(e.currentTarget)}
      ref={(node) => {
        if (node && node.complete) checkFavicon(node);
      }}
    />
  );
}
