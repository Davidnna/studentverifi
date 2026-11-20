# StudentVerifi integrated React — deployment and testing

**Baseline:** Existing security release (GitHub commit `78a5351`) plus React preview (`7e1cb5f`), with a JSON adapter that uses the original secure Flask functions and database schema. Do not run database setup again.

## Browser-only deployment with GitHub + Vercel

1. Preserve your live GitHub branch and existing Vercel production deployment. Save a GitHub commit reference or create a release tag for rollback.
2. Download and extract the complete ZIP. Create a *separate branch* named `react-security-integration` from the current repository on GitHub. Upload the ZIP contents, preserving the directory tree, into that branch. A new branch prevents an untested change from auto-deploying to production.
3. Commit using the message in `COMMIT_MESSAGE.txt`.
4. Check the GitHub Actions workflows `React build and source checks` and `StudentVerifi automated checks`. Both Python tests and `npm run build` should pass. A broken build is a stop condition.
5. Use a Vercel preview deployment from that branch. Verify the frontend build created `public/index.html` and versioned JS/CSS assets. Ensure Vercel uses the `Flask` framework preset and the specified build command. If your Vercel project settings override the build command, disable the override for the preview or set the equivalent command there. Avoid changing production variables for the test.
6. Create a separate Neon database branch from production using Neon Console. Set the preview deployment's `DATABASE_URL` to that **preview branch**, never the live production branch, using Vercel Preview environment variables. Set an independent strong `SECRET_KEY` for the preview. Keep `COOKIE_SECURE=true` and `FLASK_DEBUG=false`.
7. Confirm `/health` returns database `connected` and schema `ready`. The database is already initialised; `/setup` must remain inaccessible with no `SETUP_TOKEN`.
8. Visit `/api/compatibility` after administrator login. The endpoint lists accessible table columns and confirms the backend is integrated. The React app should show user-facing pages rather than JSON.
9. Test authentication (invalid password and rate-limiting), the dashboard, student search/add/CSV import, private claim-code issuance, registration request/approval, student QR viewing, admin QR rotation, invalid/inactive/valid QR scans, redacted verification history, administrator audit, password change, and demo cleanup **only with synthetic data in the preview Neon branch**.
10. Test Android Chrome and iOS Safari: rear camera selected initially, allow permission, camera switch, manual QR entry, portrait/landscape reflow and screen reader/keyboard navigation. Test at 320px, 375px, 768px and desktop viewports, including 200% text zoom and reduced motion. Compare foreground/background contrast with WCAG 2.2 AA as the target.
11. Do not promote to production until automated checks, live integration testing, accessibility verification, and a rollback rehearsal pass. After passing, prepare a production database backup and promote the reviewed Git commit. Preserve your current Neon database; **do not re-run `/setup`, re-import the 2,500 synthetic records or delete genuine data.**

## Current test scope

Python syntax compilation and Node JavaScript syntax checks can be performed without installing runtime dependencies. GitHub Actions is configured to run fuller Python and frontend build checks. This environment cannot confirm a live Vercel deployment, browser camera behaviour, or live Neon connection.

## Safety

Never share `DATABASE_URL`, `SECRET_KEY`, `SETUP_TOKEN`, administrator passwords, or issued student claim codes in chat or commit them to GitHub. A private one-time claim code is shown only in the authorised administrator response. Browser camera permissions are requested only when starting verification.

## Rollback

Redeploy the last known-good security-hardened commit `78a5351` or the previously recorded production commit. Keep the same production `DATABASE_URL`; this integration does not intentionally modify the database schema, but standard security migrations may run lazily when needed.
