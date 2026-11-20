# StudentVerifi React migration: deployment and acceptance checklist

## Git commit

`refactor: migrate StudentVerifi UI to accessible React and prefer rear-camera QR scanning`

## Important pre-deployment decision

The supplied archive predates the currently running Neon security release. To avoid overwriting working security changes, **do not replace the live production branch blindly**. Use a branch and Vercel Preview deployment first, ideally connecting its `DATABASE_URL` to a safe, isolated Neon branch cloned from the test database. Keep the original deployment untouched until the newer code has been compared and merged.

## Browser-only GitHub/Vercel workflow

1. Extract the entire ZIP. Create a separate branch in your existing StudentVerifi GitHub repository or use a separate temporary repository for the React preview.
2. Upload **the extracted files and directories**, not the ZIP itself. Keep the `frontend/`, `.github/workflows/`, `public/` and `tests/` directories intact. Commit with the message above.
3. In GitHub **Actions**, open "StudentVerifi release checks". Wait for **both** `frontend` and `python` jobs to pass. Fix any reported build/tests before advancing.
4. In Vercel, deploy the preview branch with the project root at the repository root. Retain the existing environment-variable **names** (but use non-production credentials against a Neon test branch): `DATABASE_URL`, `SECRET_KEY`, `COOKIE_SECURE`, `FLASK_DEBUG`, `INITIAL_ADMIN_USERNAME`, `INITIAL_ADMIN_PASSWORD`.
5. Set `COOKIE_SECURE=true` and `FLASK_DEBUG=false`. Confirm the Preview deployment has an HTTPS URL. No `SETUP_TOKEN` is needed.
6. Open `https://YOUR-PREVIEW-URL/health`. Expected connected and initialised response: `{"status":"ok","database":"connected","initialized":true}`.
7. Sign in as administrator to the preview and open `https://YOUR-PREVIEW-URL/api/compatibility`. Confirm `compatible: true` and **no missing fields**. The compatibility check is read-only, but the preview login creates the new `sv_login_attempts` and `sv_admin_audit` support tables in the **test** branch.
8. Carry out every test below in the preview. Only then consider a controlled migration of the current security release and production deployment.

## Required acceptance tests

| Area | Test | Expected outcome |
| --- | --- | --- |
| Build | GitHub Actions `frontend` and `python` | Both pass |
| React routing | Refresh `/students`, `/verify`, `/student/account` | No browser 404 |
| API | `/health`, `/api/session` | Valid JSON and session CSRF |
| Auth | Correct/incorrect passwords | Correct login; generic error on incorrect login |
| RBAC | Student visits `/api/students` | HTTP 403 |
| CSRF | Unauthorised POST without CSRF header | HTTP 400 |
| Dashboard | Compare totals with existing test records | Counts match |
| Student directory | Search by matriculation no. and department | Accurate results and pagination |
| CSV import | One valid test CSV and one duplicate CSV | Valid imports once; duplicates rejected atomically |
| Registration | Issue claim code; student registers; administrator approves | Student can sign in only after approval |
| QR scan | Android Chrome (rear-facing camera) | Rear camera requested first; verify response works |
| QR scan | iOS Safari (rear-facing camera) | Rear camera when permitted; fallback is usable |
| Camera options | Deny camera permission | Manual verification remains usable |
| QR revocation | Rotate a credential then scan old code | Old code INVALID |
| Status | Deactivate a student and scan | INACTIVE |
| Audit | Import, status and QR rotation | Logged without raw token |
| Test cleanup | Preview the DEMO removal count | No deletion without exact confirmation |
| Mobile viewports | 320, 360, 390, 768, 1024, 1440 px | No clipped forms or inaccessible controls |
| Accessibility | Keyboard-only navigation, zoom to 200%, screen reader | Labels, focus, announcements and reading order usable |
| Security | Verify CSP/permissions; check hidden admin endpoints | Sensitive endpoints require authentication |

## Important limits / precautions

- **Never run the DEMO cleanup against genuine records**. It targets exactly `DEMO/2026/%` with `record_source='synthetic'` and is only intended for the earlier fictional test dataset.
- **Never use `INITIAL_ADMIN_PASSWORD` as a reset tool**. Existing hashed users remain in the database; this release uses existing accounts.
- **No schema re-initialisation is performed** by this application. It never calls `init_db()` on import.
- If Preview reports missing columns or crashes on an action, leave production untouched. Obtain the exact currently deployed security-release ZIP or GitHub repository snapshot and reconcile the backend schema and any additional roles/workflows before proceeding.
- Vercel's Flask build and static asset handling can change across runtime versions; verify the generated asset paths and SPA fallback in the preview.
- This package is a release candidate, **not** a proof of WCAG 2.2 AA conformance or a completed penetration test.
