# StudentVerifi — React interface / Flask + Neon API

**Release:** React migration candidate `2.0.0-rc.1` (20 November 2026).

This is a **complete source-code candidate**, rebuilt from the older `studentverifi-main.zip` that was supplied for this task and the more recent workflow described in the conversation. **The archive was NOT the currently deployed security-hardened code**. That distinction matters: this release has not been tested against the live Neon schema, and it is **not a verified drop-in replacement for your current working Vercel production deployment**. Use a Vercel Preview deployment and a Neon database branch/snapshot first. Do not upload genuine student data until the compatibility/security review is complete.

## Features implemented

- React SPA, React Router navigation, Vite asset bundling and lazy-loaded QR scanner package.
- Mobile-first responsive layout: navigation collapses on phones; forms and cards reflow; tables are horizontally scrollable; layouts are supported down to a narrow phone viewport.
- Accessibility-oriented semantics: skip link, labelled inputs, keyboard focus indicators, status text in addition to colours, live error announcements, modal keyboard navigation, reduced-motion style, and readable touch controls.
- Rear-facing mobile camera is requested **first** (`facingMode: { exact: 'environment' }`), with a softer environment fallback; a camera picker and manual QR token entry remain available.
- JSON API `/api/*` backed by Flask sessions and existing Neon Postgres tables; raw QR secrets are omitted from verification logs and API student responses.
- Admin overview, student directory, add student, CSV import, registration requests, audit events, QR issuance/rotation, account/password screens, verification history, test-data cleanup.
- Legacy database tables are never dropped/recreated; extra namespaced support tables `sv_login_attempts` and `sv_admin_audit` are created as needed.

## What this release does not demonstrate

No live Neon credentials were available, and outbound dependency installation was unavailable in the packaging environment. We completed **Python syntax compilation and JavaScript syntax checks**, but could not execute Vite's build, Flask runtime tests, automated accessibility browser checks, or the actual Vercel deployment. GitHub Actions contains the build and runtime smoke tests that must pass. Mobile camera selection must also be tested on at least Android Chrome and iOS Safari, because browser permissions and hardware differ.

The uploaded snapshot was MySQL based. This release provides a new PostgreSQL API implementation rather than transplanting the live Flask implementation line-for-line. Pre-existing security releases may have additional features, constraints, tables or roles which this source **does not implement**. These must be reconciled with your actual deployed repository before a production switch.

## Project structure

```text
studentverifi-react-release/
├── app.py                      Flask API and SPA fallback
├── requirements.txt            Python runtime dependencies
├── package.json                React, React Router, scanner and Vite
├── vite.config.js              Vite: build to public/
├── frontend/
│   ├── index.html
│   └── src/
│       ├── main.js             Client-side routes
│       ├── components.js       Navigation, forms, accessibility
│       ├── pages.js            User-facing screens and scanner
│       ├── api.js              CSRF-aware API client
│       └── style.css
├── public/                     Logo and favicon; Vite adds built index/assets
├── tests/test_release.py       Offline backend smoke tests
├── .github/workflows/check.yml Automated GitHub checks
├── vercel.json                  Flask + frontend build configuration
├── .env.example                Placeholder configuration, NO REAL SECRETS
└── DEPLOYMENT_AND_TESTING.md
```

## Development (optional, not needed for user's browser-only workflow)

```bash
npm install
npm run build
python -m pip install -r requirements.txt
export DATABASE_URL='postgresql+psycopg://...'
export SECRET_KEY='a-long-local-secret'
python app.py
```

During UI-only development, `npm run dev` launches Vite and proxies `/api/*` and `/health` to Flask on port 5000.

## Browser-only deployment

See `DEPLOYMENT_AND_TESTING.md`. Start with a Vercel Preview deployment connected to a separate Neon branch. A successful build does **not** validate existing table compatibility. After signing in, visit `/api/compatibility` to inspect required columns and missing schema fields. Do not perform state-changing checks on the production database before compatibility is established.

## Data and security considerations

- Never share `DATABASE_URL`, `SECRET_KEY`, administrator passwords or student claim codes.
- All imported records should be independently validated against an authorised register.
- Avoid treating a QR code as sufficient proof of the bearer's identity; compare against authorised photo identification.
- Even if the compatibility endpoint says `compatible: true`, verify login, accounts, scanning, audit, imports and revocation against a **test branch** before release.
- `SETUP_TOKEN` is neither required nor used by this version. Your existing database should already be initialised.
- Use the official institution's data retention and incident response policies; do not assume this prototype has independent penetration-test certification.
