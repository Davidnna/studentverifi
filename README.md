# StudentVerifi — Neon PostgreSQL edition

A web-based academic prototype for QR-code-assisted student identity verification at Ebonyi State University (EBSU). Built with Flask, SQLAlchemy, Psycopg 3, Neon PostgreSQL and Vercel. **It is not an official EBSU service.**

## Online-only deployment

Use `ONLINE_DEPLOYMENT.md`. The project is designed for GitHub + Vercel + Neon; local execution is optional and is not required for the intended deployment workflow. Upload the extracted contents of this ZIP to the root of the existing GitHub repository, not the ZIP as one file.

## Main capabilities

- 10 faculties and 59 departments in the bundled academic catalogue.
- Separate first, middle and surname fields.
- Configurable matriculation-number structural validation; the default pattern is not an official EBSU validation specification.
- UTF-8 CSV import (up to 8 MB) with duplicate checks and all-or-nothing transaction behaviour.
- Administrator and student authentication with role-separated access.
- Private one-time claim codes for student account requests, with administrator approval.
- Unique opaque QR tokens, camera scanning, manual verification, verification history and QR rotation.
- Neon PostgreSQL schema initialisation through the protected browser setup route.
- Lazy additive security migration after deployment; no database I/O during Flask module import.
- Login rate limiting, CSRF protection, session limits, security headers and no-store responses.
- Administrator audit trail for record creation/import, status changes, claim-code issuance, QR rotation, account approvals, password changes and synthetic-data cleanup.
- Administrator-only preview and removal of the exact synthetic `DEMO/2026/NNNNNN` test dataset.

## Important operational points

- Keep secrets in Vercel environment variables; never commit `.env` or secret values.
- The production environment should have `DATABASE_URL`, `SECRET_KEY`, `INITIAL_ADMIN_USERNAME`, `INITIAL_ADMIN_PASSWORD`, `COOKIE_SECURE=true` and `FLASK_DEBUG=false`.
- `SETUP_TOKEN` is needed only for one-time initialisation of a new database. The route automatically returns 404 after an administrator and core schema exist. Remove the token after initialisation.
- On the first administrator sign-in after this security update, the application applies additive security migrations, including rate-limit storage and verification-token redaction.
- Before importing genuine records, use Students → synthetic-data cleanup and confirm that only the generated `DEMO/2026/NNNNNN` rows are selected. The cleanup action is not automatic.
- Only process student records and photographs with proper institutional authorisation. The project remains an academic prototype until the university approves its use and operating procedures.

## Testing and limitations

The included `tests/` directory contains Flask unit/smoke tests. A GitHub Actions workflow runs them automatically on pushes to `main`/`master` and on pull requests; Vercel deployment itself does not run these tests. Package preparation also checks Python syntax, Jinja template parsing, CSRF form coverage, endpoint references and catalogue consistency. The packaging environment did not permit installing missing Flask/Werkzeug/Flask-WTF/Psycopg packages, so the full Flask test-client suite and live Neon/Vercel integration could not be run before delivery. See `SECURITY_AUDIT.md` for scope and remaining production controls.
