"use client";

import { useEffect, useState } from "react";

function initials(name: string): string {
  return name
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((w) => w[0])
    .join("")
    .toUpperCase();
}

type LogoProps = {
  domain: string | null;
  name: string;
  size: number;
  verified: boolean;
};

export default function CompanyLogo(props: LogoProps) {
  return <LogoImage key={`${props.domain}:${props.verified}`} {...props} />;
}

function LogoImage({ domain, name, size, verified }: LogoProps) {
  // 0 = cached logo endpoint, 1 = company favicon, 2 = initials fallback
  const [step, setStep] = useState(0);
  const [loadedStep, setLoadedStep] = useState(-1);
  // Radius scales with the box so the 24px and 40px marks share one
  // app-icon geometry instead of one reading as a circle.
  const boxStyle = { width: size, height: size, borderRadius: Math.round(size * 0.24) };

  // An unverified domain may belong to a different company entirely, so we
  // never request a logo for one - that is how other companies' marks ended
  // up on these rows. Straight to initials.
  const shouldLoad = verified && Boolean(domain) && step < 2;
  const loaded = shouldLoad && loadedStep === step;

  useEffect(() => {
    if (!shouldLoad || loaded) return;
    const timer = window.setTimeout(() => {
      setStep((s) => (s === step ? s + 1 : s));
    }, 10000);
    return () => window.clearTimeout(timer);
  }, [shouldLoad, loaded, step]);

  const src =
    step === 0
      ? `/api/logo?domain=${encodeURIComponent(domain ?? "")}`
      : `https://${domain}/favicon.ico`;

  // Accept small favicons too: dimensions alone cannot distinguish a real
  // 16x16 company icon from a provider placeholder. Check on load AND
  // via ref: a browser that already has the URL cached (failed or not)
  // resolves it before React attaches the listener, so onLoad/onError never
  // fire for it — the ref catches that by checking img.complete on mount.
  function evaluate(img: HTMLImageElement, atStep: number) {
    if (!img.complete) return;
    if (img.naturalWidth === 0) {
      setStep((s) => (s === atStep ? s + 1 : s));
    } else {
      setLoadedStep(atStep);
    }
  }

  // bg-logo-plate is a light plate behind the mark: most company logos are
  // dark-on-transparent and would disappear against the dark theme's surfaces.
  return (
    <span
      role="img"
      aria-label={`${name} logo`}
      style={boxStyle}
      className="relative flex shrink-0 items-center justify-center overflow-hidden border border-border bg-initials-bg text-[11px] font-semibold text-text-secondary"
    >
      <span aria-hidden="true" className={loaded ? "invisible" : ""}>
        {initials(name)}
      </span>
      {shouldLoad && (
        // eslint-disable-next-line @next/next/no-img-element
        <img
          key={step}
          src={src}
          alt=""
          width={size}
          height={size}
          loading="eager"
          decoding="async"
          referrerPolicy="no-referrer"
          className={`absolute inset-0 h-full w-full bg-logo-plate object-contain p-[3px] ${loaded ? "opacity-100" : "opacity-0"}`}
          onError={() => setStep((s) => (s === step ? s + 1 : s))}
          onLoad={(e) => evaluate(e.currentTarget, step)}
          ref={(node) => {
            if (node) evaluate(node, step);
          }}
        />
      )}
    </span>
  );
}
