import { expect, test } from "@playwright/test";
import { GET } from "../app/api/logo/route";

const originalFetch = globalThis.fetch;
const request = (domain = "acme.com") => new Request(`https://raised.example/api/logo?domain=${encodeURIComponent(domain)}`);
const png = Buffer.from("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jRZkAAAAASUVORK5CYII=", "base64");
const placeholder = Buffer.from("iVBORw0KGgoAAAANSUhEUgAAABAAAAAQCAYAAAAf8/9hAAAACXBIWXMAAAsSAAALEgHS3X78AAACiElEQVQ4EaVTzU8TURCf2tJuS7tQtlRb6UKBIkQwkRRSEzkQgyEc6lkOKgcOph78Y+CgjXjDs2i44FXY9AMTlQRUELZapVlouy3d7kKtb0Zr0MSLTvL2zb75eL838xtTvV6H/xELBptMJojeXLCXyobnyog4YhzXYvmCFi6qVSfaeRdXdrfaU1areV5KykmX06rcvzumjY/1ggkR3Jh+bNf1mr8v1D5bLuvR3qDgFbvbBJYIrE1mCIoCrKxsHuzK+Rzvsi29+6DEbTZz9unijEYI8ObBgXOzlcrx9OAlXyDYKUCzwwrDQx1wVDGg089Dt+gR3mxmhcUnaWeoxwMbm/vzDFzmDEKMMNhquRqduT1KwXiGt0vre6iSeAUHNDE0d26NBtAXY9BACQyjFusKuL2Ry+IPb/Y9ZglwuVscdHaknUChqLF/O4jn3V5dP4mhgRJgwSYm+gV0Oi3XrvYB30yvhGa7BS70eGFHPoTJyQHhMK+F0ZesRVVznvXw5Ixv7/C10moEo6OZXbWvlFAF9FVZDOqEABUMRIkMd8GnLwVWg9/RkJF9sA4oDfYQAuzzjqzwvnaRUFxn/X2ZlmGLXAE7AL52B4xHgqAUqrC1nSNuoJkQtLkdqReszz/9aRvq90NOKdOS1nch8TpL555WDp49f3uAMXhACRjD5j4ykuCtf5PP7Fm1b0DIsl/VHGezzP1KwOiZQobFF9YyjSRYQETRENSlVzI8iK9mWlzckpSSCQHVALmN9Az1euDho9Xo8vKGd2rqooA8yBcrwHgCqYR0kMkWci08t/R+W4ljDCanWTg9TJGwGNaNk3vYZ7VUdeKsYJGFNkfSzjXNrSX20s4/h6kB81/271ghG17l+rPTAAAAAElFTkSuQmCC", "base64");

test.afterEach(() => { globalThis.fetch = originalFetch; });

test("serves small valid icons with Vercel-compatible cache headers", async () => {
  const urls: string[] = [];
  globalThis.fetch = async (url) => {
    urls.push(String(url));
    return new Response(png, { headers: { "content-type": "image/png" } });
  };
  const response = await GET(request());
  expect(response.status).toBe(200);
  expect(Buffer.from(await response.arrayBuffer())).toEqual(png);
  expect(response.headers.get("cache-control")).toContain("s-maxage=86400");
  expect(response.headers.get("x-content-type-options")).toBe("nosniff");
  expect(urls).toEqual(["https://www.google.com/s2/favicons?domain_url=https%3A%2F%2Facme.com&sz=128"]);
});

test("rejects the generic globe even if the provider returns HTTP 200", async () => {
  globalThis.fetch = async () => new Response(placeholder, { headers: { "content-type": "image/png" } });
  expect((await GET(request())).status).toBe(404);
});

test("rejects HTTP-error images rather than displaying their decoded pixels", async () => {
  globalThis.fetch = async () => new Response(png, { status: 404, headers: { "content-type": "image/png" } });
  expect((await GET(request())).status).toBe(404);
});

test("follows only the expected HTTPS Google image redirect", async () => {
  const urls: string[] = [];
  globalThis.fetch = async (url) => {
    urls.push(String(url));
    return urls.length === 1
      ? new Response(null, { status: 302, headers: { location: "https://t0.gstatic.com/faviconV2?size=128" } })
      : new Response(png, { headers: { "content-type": "image/png" } });
  };
  expect((await GET(request())).status).toBe(200);
  expect(urls).toHaveLength(2);
});

test("checks the HTTP-indexed icon when the HTTPS entry is missing", async () => {
  const urls: string[] = [];
  globalThis.fetch = async (url) => {
    urls.push(String(url));
    return urls.length === 1
      ? new Response(null, { status: 404 })
      : new Response(png, { headers: { "content-type": "image/png" } });
  };
  expect((await GET(request())).status).toBe(200);
  expect(urls[1]).toBe("https://www.google.com/s2/favicons?domain_url=http%3A%2F%2Facme.com&sz=128");
});

test("does not follow arbitrary upstream redirects", async () => {
  let calls = 0;
  globalThis.fetch = async () => {
    calls++;
    return new Response(null, { status: 302, headers: { location: "http://127.0.0.1/private" } });
  };
  expect((await GET(request())).status).toBe(502);
  expect(calls).toBe(1);
});

for (const domain of ["", "localhost", "127.0.0.1", "https://acme.com", "acme.com/path", "acme.com:8080"]) {
  test(`rejects invalid domain ${JSON.stringify(domain)} without fetching`, async () => {
    let called = false;
    globalThis.fetch = async () => { called = true; return new Response(png); };
    expect((await GET(request(domain))).status).toBe(400);
    expect(called).toBe(false);
  });
}

test("rejects non-image responses and oversized payloads", async () => {
  globalThis.fetch = async () => new Response("<html>blocked</html>", { headers: { "content-type": "text/html" } });
  expect((await GET(request())).status).toBe(404);
  globalThis.fetch = async () => new Response(new Uint8Array(262145), { headers: { "content-type": "image/png" } });
  expect((await GET(request())).status).toBe(404);
});

test("handles upstream timeouts without caching a temporary outage", async () => {
  globalThis.fetch = async () => { throw new DOMException("Timed out", "TimeoutError"); };
  const response = await GET(request());
  expect(response.status).toBe(502);
  expect(response.headers.get("cache-control")).toBe("no-store");
});
