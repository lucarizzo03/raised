"use client";

import { useState } from "react";

export default function Logo({ domain, name }: { domain: string | null; name: string }) {
  const [failed, setFailed] = useState(!domain);
  const initials = name
    .split(/\s+/)
    .slice(0, 2)
    .map((w) => w[0])
    .join("")
    .toUpperCase();

  if (failed || !domain) {
    return (
      <span className="flex h-6 w-6 items-center justify-center rounded bg-neutral-200 text-[10px] font-semibold text-neutral-600">
        {initials}
      </span>
    );
  }
  return (
    // eslint-disable-next-line @next/next/no-img-element
    <img
      src={`https://logo.clearbit.com/${domain}`}
      alt=""
      width={24}
      height={24}
      className="h-6 w-6 rounded"
      onError={() => setFailed(true)}
    />
  );
}
