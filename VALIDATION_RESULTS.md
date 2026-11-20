# Validation results — security-hardened React integration

Source version: GitHub hardened commit 78a5351 plus React preview 7e1cb5f.

Checks completed in the packaging environment:
- The authoritative security release `app.py` and `academic_catalogue.py` were retained; an isolated `spa_api.py` was added.
- All Python files parsed and compiled successfully.
- All React and Vite JavaScript source files passed Node syntax checking.
- React uses React Router `BrowserRouter` with protected admin and student UI routes.
- Mobile QR scanner requests `{facingMode:{exact:'environment'}}` before fallback.
- Responsive styles include breakpoints for <= 1000px, 760px and 390px, reduced motion and increased contrast.
- JSON API uses the existing PostgreSQL schema, rate limiter, one-time claim code workflow and audit helpers.
- Student API responses explicitly exclude QR bearer tokens, password hashes and claim-code hashes.
- Verification-log writes use token SHA-256 fingerprints and `[REDACTED]` raw token fields.
- No replacement schema or destructive DDL exists in the SPA API adapter.
- Existing source-based security regression tests and newly added API contract tests were included.
- No real DATABASE_URL, administrator credentials or tokens are included in this project archive.

Not completed in this environment:
- `npm install` and Vite production build (no external package registry access).
- Python Flask test execution (Flask, Flask-WTF and Psycopg not installed here).
- Live integration with a Neon PostgreSQL branch or Vercel preview deployment.
- Browser/device camera permissions and accessibility audit with assistive technology.

Release status: **integration release candidate requiring preview acceptance tests**.
