<!-- BEGIN:nextjs-agent-rules -->

# This is NOT the Next.js you know

This version has breaking changes — APIs, conventions, and file structure may all differ from your training data. Read the relevant guide in `node_modules/next/dist/docs/` (resolved from this file's directory; in monorepos the `next` package may not be visible from the repo root) before writing any code. Heed deprecation notices.

This block is written and re-added by `next dev` — verify at `node_modules/next/dist/server/lib/generate-agent-files.js`. Removing it from a diff only re-creates the uncommitted change; committing it with your work keeps the tree clean.

<!-- END:nextjs-agent-rules -->

## Verification

- Run commands from `dashboard/`.
- Typecheck: `npx tsc --noEmit --incremental false`.
- Production build: `npm run build`.
- Browser tests: install Chromium with `npx playwright install chromium`, then run `npm test`.
- Browser tests build and start the production application on port 3100 with Supabase environment variables blanked for isolated sample data. Keep that port free.
- Live deployment check: `PLAYWRIGHT_BASE_URL=https://raised-lac.vercel.app npm test`. This reads real data without mocking image providers, checks dashboard interactions and every saved-domain logo on opening and reload, and fails if the deployment falls back to sample data.
- To check existing dashboard functionality separately from known logo/data failures: `PLAYWRIGHT_BASE_URL=https://raised-lac.vercel.app npm test -- dashboard.spec.ts`.
- Keep the client logo timeout longer than the server endpoint's upstream timeout. The logo endpoint runs on Vercel's Node.js runtime, uses public CDN caching, and rejects known generic placeholder images.
- `.github/workflows/dashboard.yml` runs production regression tests on dashboard changes and the live check after successful Production deployments. Companies without saved domains still need verified website data before a real logo can be checked.
- Logo tests intercept images through Chromium CDP because Playwright's ordinary routing automatically aborts URLs ending in `/favicon.ico`.
- Use Node.js 22 or newer to satisfy the installed Supabase packages' engine requirements.
