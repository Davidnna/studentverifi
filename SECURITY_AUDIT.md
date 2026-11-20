# StudentVerifi Security Hardening Review

**Release:** Security-hardening update for the Neon PostgreSQL/Vercel application  
**Review scope:** Application source, Flask routes, database access patterns, templates, session handling, QR workflows, CSV import and deployment configuration.  
**Review type:** Source-code review and static/automated checks. This is not a penetration test, independent security certification, or review of the live Vercel/Neon account configuration.

## Corrections included

1. **Login abuse controls:** Added database-backed rate limiting for repeated failed sign-in attempts. Username and client-address identifiers are HMAC-hashed before storage; raw usernames and IP addresses are not written to the rate-limit table. The limit is eight failed attempts per 15-minute window, followed by a temporary 15-minute block.
2. **Student account ownership:** Student self-registration now requires a private one-time claim code issued by an administrator. Matching a matriculation number and personal details alone is no longer sufficient. The claim code is consumed when the account request is submitted; rejected requests require a newly issued code.
3. **Claim-code disclosure:** The one-time code is rendered only in the authenticated, no-store administrator response. It is no longer placed in Flask's signed client-side session/flash cookie.
4. **QR-token confidentiality:** New verification events store a SHA-256 fingerprint, not the bearer QR token. A lazy additive migration fingerprints and redacts older raw token values in the existing verification log table.
5. **QR revocation:** Administrators can rotate a student's QR token. Previously issued QR images become invalid after rotation.
6. **Session security:** Sessions are limited to eight hours, are not refreshed on every request, and are marked permanent only after successful authentication. Secure, HttpOnly and SameSite=Lax cookie settings are applied; HTTPS-only cookies are enforced in production.
7. **Password bounds:** Authentication and password-change inputs are bounded to 128 characters; the existing minimum of ten characters is retained to avoid unexpectedly invalidating existing account policy.
8. **Browser security headers:** Added a nonce-based Content Security Policy, HSTS in production, frame protection, MIME-sniffing protection, restrictive referrer and permissions policies, and no-store caching headers.
9. **Third-party script control:** The QR scanner library is pinned to a fixed release rather than following an unpinned latest CDN version. Its inline initialisation script uses a per-response CSP nonce.
10. **Setup hardening:** The browser setup route becomes unavailable once the core schema and an administrator account exist, even if a setup token is accidentally left configured. The route still requires a high-entropy `SETUP_TOKEN` before initialisation.
11. **Test-data cleanup:** Added an administrator-only preview-and-confirm workflow that targets only the exact synthetic matriculation pattern `DEMO/2026/NNNNNN`. Linked test student accounts are deleted; verification history is retained with its student relationship detached.
12. **Operational error handling:** Added generic 500/503 pages so internal exception details are not shown to visitors.
13. **Administrator audit trail:** Added a restricted audit page and append-only-style event records for student creation/import, status changes, claim-code issuance, QR rotation, account approvals/rejections, password changes and synthetic-data cleanup. Entries avoid storing passwords, claim codes, QR tokens or student names.
14. **Account maintenance:** Both administrator and student users can change their passwords; changing a password ends the current session and requires a fresh sign-in. Inactive student accounts cannot sign in or retrieve their QR image.
15. **Input validation:** Photo URLs now require HTTPS hostnames, reject literal IP/localhost destinations, and cannot contain embedded URL credentials.

## Database compatibility

The application continues to use Neon PostgreSQL through SQLAlchemy and Psycopg 3. It does not connect during module import. The security migration is lazy and additive: it creates the rate-limit table if absent, adds the token fingerprint column if absent, and redacts legacy raw verification tokens. It runs on the first login attempt or authenticated request after deployment.

The application does not automatically drop or rewrite student identity records. The synthetic-data cleanup is an explicit administrator action and is narrowly restricted to the generated `DEMO/2026/NNNNNN` pattern.

## Required administrator actions after deployment

1. Replace the project files in the existing GitHub repository and deploy the new commit.
2. Keep `DATABASE_URL`, `SECRET_KEY`, `INITIAL_ADMIN_USERNAME`, `INITIAL_ADMIN_PASSWORD`, `COOKIE_SECURE=true` and `FLASK_DEBUG=false` configured in Vercel Production. Do not expose their values.
3. Do not re-add `SETUP_TOKEN` unless a genuinely new/empty database needs initialisation. The current database is already initialised.
4. Sign in as administrator. The first sign-in after deployment applies the additive security migration. Open the dashboard to confirm it loads.
5. Open Students → synthetic-data cleanup. Review the exact matching count. Only if it corresponds to the test dataset, type `DELETE DEMO RECORDS` and submit. This action is intentionally manual and is not run automatically by deployment.
6. Confirm the student count is zero (or equals any records deliberately retained) before importing authorised student records.
7. Change the initial administrator password if it has not already been changed to a unique strong password. Do not reuse the Vercel environment variable password for other services.
8. Configure and test Neon backups/restore and restrict database credentials to the application environment.

## Remaining production controls outside this code package

These cannot be completed or certified from the uploaded source archive alone:

- Confirm the institution's authority, lawful basis, privacy notice, data-retention schedule, data-subject process and approved purpose before processing genuine student records.
- Use a university-authorised student register and confirm the official matriculation-number format. The default regular expression validates structure only; it does not prove a matriculation number is genuine.
- Obtain and store student photographs only through an authorised process. The current application references HTTPS photo URLs; it does not provide managed image storage or consent management.
- Restrict Vercel and Neon account access with MFA and least privilege; rotate credentials if they have ever been shared.
- Configure Neon automated backups and perform a restore test. A backup policy is not proven merely by enabling a provider feature.
- Run a live deployment test for the login throttle, claim-code lifecycle, QR rotation, admin audit entries, import rollback, role separation and backup restore.
- Conduct an independent penetration test before institutional production use.
- Establish a verifier role and staff onboarding/offboarding process if staff other than administrators will perform verification. The current permission model intentionally has only administrator and student roles.

## Verification performed for this package

- Python source compilation (`py_compile`).
- GitHub Actions workflow added to run the Flask unit/smoke tests automatically after the commit is pushed; it has not run yet because this package has not been pushed to the user's repository.
- Jinja template parsing.
- Static route/form checks, including CSRF token presence on POST forms.
- Academic catalogue count and alias checks (10 faculties / 59 departments).
- Synthetic CSV structural checks against the application's catalogue.
- Static checks for secret values, unpinned scanner scripts, removed demo-generation route, and raw QR-token logging.

The execution environment used to prepare this archive did not contain Flask, Flask-WTF, Psycopg or Werkzeug and had no package-index network access. Therefore, full Flask test-client execution and live PostgreSQL/Vercel integration tests could not be run here. The deployment must be smoke-tested after upload; no claim of live penetration testing or full production certification is made.
