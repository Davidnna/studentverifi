# StudentVerifi — React and security-hardened Flask integration

This complete project was merged from the **security-hardened StudentVerifi 78a5351 release** and the React `7e1cb5f` preview. It does **not** replace the original hardened backend with the preview backend.

- **Frontend:** React 18, React Router 6, Vite, mobile-first CSS and rear-camera-first QR scanning (with camera selector/manual entry fallback).
- **Backend:** the existing production security-hardened `app.py` and `academic_catalogue.py`, extended with a namespaced `spa_api.py` JSON adapter.
- **Database:** the existing Neon PostgreSQL schema and additive security migrations. No database reset or re-initialisation.
- **Login/session protection:** hardened session cookie, CSRF, database-backed rate limiting and 8-hour session expiry.
- **Student protection:** administrator-issued one-time claim codes, full academic identity comparison, approval-based account access.
- **Verification:** never sends raw QR token in API student JSON; verification history stores fingerprints and `[REDACTED]` values; authorised administrators can rotate QR credentials.
- **Audit:** original administrative audit trail preserved.
- **Cleanup:** original exact `DEMO/2026/NNNNNN` cleanup pattern and administrator confirmation retained.
- **Legacy:** original Jinja templates/routes kept for safe fallback when a React build is absent. When Vite builds `public/index.html`, the user-facing routes are handled by React.

## No local execution required

See `DEPLOYMENT_AND_TESTING.md` for browser-only GitHub and Vercel preview deployment. **Do not overwrite the live production branch before the new build and live checks pass.**

## Limitations

Static Python/JavaScript tests can be run offline, but the production Vercel build, actual Neon database compatibility, browser assistive-technology checks, and rear-camera selection on iOS Safari and Android Chrome must be confirmed in a preview deployment. The package is a release candidate, not a security certification. No university student information should be imported without approval.
