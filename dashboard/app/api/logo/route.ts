import { createHash } from "node:crypto";

export const runtime = "nodejs";

const DOMAIN = /^(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}$/;
const PLACEHOLDER_HASH = "59bfe9bc385ad69f50793ce4a53397316d7a875a7148a63c16df9b674c6cda64";
const IMAGE_TYPES = new Set(["image/png", "image/jpeg", "image/gif", "image/webp", "image/x-icon", "image/vnd.microsoft.icon"]);

function unavailable(status = 404) {
  return new Response(null, {
    status,
    headers: { "Cache-Control": status === 404 ? "public, max-age=300, s-maxage=300" : "no-store" },
  });
}

export async function GET(request: Request) {
  const domain = new URL(request.url).searchParams.get("domain")?.toLowerCase() ?? "";
  if (domain.length > 253 || !DOMAIN.test(domain)) return unavailable(400);

  try {
    const options = { signal: AbortSignal.timeout(8000), next: { revalidate: 86400 } };
    for (const scheme of ["https", "http"]) {
      let response = await fetch(
        `https://www.google.com/s2/favicons?domain_url=${encodeURIComponent(`${scheme}://${domain}`)}&sz=128`,
        { ...options, redirect: "manual" }
      );
      if (response.status >= 300 && response.status < 400) {
        const location = response.headers.get("location");
        if (!location) return unavailable(502);
        const target = new URL(location, "https://www.google.com");
        if (target.protocol !== "https:" || !target.hostname.endsWith(".gstatic.com") || target.port || target.username || target.password) {
          return unavailable(502);
        }
        response = await fetch(target, { ...options, redirect: "error" });
      }
      if (response.status === 404) continue;
      if (!response.ok) return unavailable(502);
      const type = response.headers.get("content-type")?.split(";")[0].trim().toLowerCase() ?? "";
      if (!IMAGE_TYPES.has(type)) continue;
      const bytes = await response.arrayBuffer();
      if (!bytes.byteLength || bytes.byteLength > 262144) continue;
      if (createHash("sha256").update(new Uint8Array(bytes)).digest("hex") === PLACEHOLDER_HASH) continue;
      return new Response(bytes, {
        headers: {
          "Content-Type": type,
          "Cache-Control": "public, max-age=86400, s-maxage=86400, stale-while-revalidate=604800",
          "X-Content-Type-Options": "nosniff",
        },
      });
    }
    return unavailable();
  } catch {
    return unavailable(502);
  }
}
