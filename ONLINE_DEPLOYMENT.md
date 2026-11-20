# Deploy StudentVerifi online — GitHub + Vercel + Neon

This is a complete source update for the existing StudentVerifi application. It retains the Neon PostgreSQL/Vercel architecture and adds application security hardening. You do not need to run Python or the application on your computer.

## 1. Upload the project to GitHub

1. Download and extract the complete ZIP.
2. Open the existing GitHub repository connected to your Vercel project.
3. Upload/replace the **contents** of the extracted folder at the repository root. The root must contain `app.py`, `academic_catalogue.py`, `requirements.txt`, `vercel.json`, `templates/` and `static/`.
4. Commit to the branch Vercel deploys. The included GitHub Actions workflow will run the unit/smoke tests automatically on pushes to `main` or `master` and on pull requests. Check the repository's **Actions** tab for the result; Vercel's successful build is not a substitute for these tests.

**Commit message:**

```text
security: harden StudentVerifi authentication, QR credentials and data handling
```

Do not upload the ZIP as one file and expect Vercel to deploy its contents.

## 2. Vercel environment variables

Keep these Production variables configured:

| Variable | Requirement |
|---|---|
| `DATABASE_URL` | Neon pooled PostgreSQL URL with SSL enabled (`sslmode=require`) |
| `SECRET_KEY` | Unique, random Flask secret; use at least 32 random characters |
| `INITIAL_ADMIN_USERNAME` | Existing administrator username; only used when initial admin is absent |
| `INITIAL_ADMIN_PASSWORD` | Strong password, 10–128 characters; only used to create a missing admin |
| `COOKIE_SECURE` | `true` |
| `FLASK_DEBUG` | `false` |

`SETUP_TOKEN` is not required now because your database has already been initialised. Do not add it again. If a brand-new empty database is ever created, temporarily add a different random token of at least 32 characters, initialise once at `/setup`, then remove it and redeploy. The setup route also blocks itself once the core schema and administrator account exist.

## 3. Deploy and sign in

1. Wait for Vercel to finish deploying the new GitHub commit.
2. Open `/health`; expect a connected database and ready schema.
3. Sign in through `/login` with the existing administrator credentials.
4. The first login/authenticated request applies the additive security migration. This creates the rate-limit table, adds the verification token fingerprint column if needed, and redacts legacy raw QR tokens in existing verification logs.
5. Confirm that Dashboard, Students, Verify ID and Logs load.

No existing student rows are automatically deleted or changed by the security migration.

## 4. Remove the synthetic test dataset before real data

The current database contains the 2,500 synthetic records generated for testing. After deploying this version:

1. Sign in as administrator.
2. Open Students.
3. Select **Review and remove the known synthetic DEMO/2026 test dataset**.
4. Confirm the preview count is the expected synthetic dataset only.
5. Type exactly `DELETE DEMO RECORDS` and submit.

This deletes only records whose matriculation numbers match `DEMO/2026/` followed by exactly six digits, plus linked student accounts. Verification history remains but is detached from the deleted student rows. Do not submit if the preview count is unexpected. The action is not performed automatically.

## 5. Security features included

- CSRF protection for state-changing forms.
- Eight-hour, non-sliding authenticated sessions and production Secure cookies.
- Database-backed failed-login throttling.
- Mandatory administrator-issued one-time claim code for student account registration.
- One-time claim-code consumption and safe display outside the session cookie.
- QR-token fingerprinting in verification logs and migration/redaction of legacy raw tokens.
- Administrator audit trail for sensitive record and credential changes.
- Administrator QR credential rotation.
- Security response headers, CSP nonce and no-store caching.
- HTTPS-only photo URLs.
- Generic 500/503 error pages.

## 6. Before genuine EBSU student data is used

- Change the initial administrator password to a unique strong password.
- Confirm the official matriculation-number format with the institution; the default expression only checks structure.
- Obtain institutional approval and define lawful purpose, access roles, retention, privacy notice and incident response.
- Use only an authorised student register and authorised photographs.
- Configure Neon backups and complete a restore test.
- Test student claim-code issuance, registration, approval/rejection, password changes, QR rotation, inactive-student checks, administrator audit entries and import rollback on the live deployment.
- Arrange independent penetration testing and staff access/offboarding procedures.

Read `SECURITY_AUDIT.md` for the full scope and limitations. This code review is not a penetration test or a production security certification.
