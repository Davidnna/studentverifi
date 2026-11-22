# StudentVerifi 3.1.3

StudentVerifi is a web-based student-record and QR-assisted identity-verification application developed as an academic software prototype for Ebonyi State University (EBSU). It uses a React and React Router interface, a Flask JSON API, and PostgreSQL (including Neon PostgreSQL). It is not an official EBSU service unless the university formally authorises and adopts it.

## What the software does

### Administrator workspace

- Create, search, view, activate and deactivate student records.
- Import up to 5,000 student records from a validated UTF-8 CSV file.
- Add a student's email address when creating a record, import it in the CSV, or update it later from the student record page.
- Review claimed and unclaimed student records, email-verification status and profile-photo completion.
- Invite lecturers and other authorised staff as verifiers without granting them administrator permissions.
- Suspend, reactivate and resend invitations to verifier accounts.
- Review verification activity from administrators, verifiers and public QR checks.
- Review administrative audit records and historical account requests created by the previous claim-code workflow.
- Rotate an active student's QR credential if it is lost or compromised.
- Review and remove the known synthetic `DEMO/2026/` records through a confirmation-controlled maintenance page.

### Student account claiming

- A student must already have a record in the student register. The public claim process does not create a new student record.
- The student enters their matriculation number and the email address already stored in that record.
- A six-digit, single-use OTP is sent to the stored email address. It expires after 10 minutes and is subject to resend and attempt limits.
- After email verification, the student must upload a profile photograph and create a password of at least 12 characters.
- The account is activated automatically after the verified claim and profile completion succeed. Routine administrator approval is not required.
- A unique QR credential is generated only after account activation and successful private photo storage.
- Students can view their own student card, update their photograph and download their QR credential.

If a student record has no email address, or the address is incorrect or shared with another student record, an administrator must add or correct a unique email address before the student can claim the account. The OTP is never sent to an arbitrary address supplied by the claimant.

### Profile photographs

- A profile photograph is mandatory during a new student account claim.
- JPEG, PNG and WebP files are accepted, up to 2 MB.
- Images are validated, orientation-corrected, resized to a maximum dimension of 512 pixels, re-encoded as JPEG and stripped of EXIF metadata.
- New photographs are stored in a **private Vercel Blob store** and delivered through application routes with role and access checks. Public QR verification displays the photograph only to a person who has the student's QR credential.
- A student who already has an account but no private profile photograph can upload one from the student workspace. The QR credential remains unavailable until the photograph is saved.

A student-submitted photograph is not automatically an institution-authenticated photograph. Verifiers should compare it with the person presenting the credential and use any additional identity evidence required by the institution.

### Verifier workspace

- Administrators invite lecturers and other staff using their name and email address.
- The invitee receives a single-use invitation link, valid for 48 hours, and creates their own password.
- Verifiers can scan QR credentials with a supported phone or computer camera, or enter a credential manually.
- Verifiers can view the student information needed for identity checking and their own verification activity.
- Verifiers cannot add, edit, import, activate or delete student records, manage other users, or access administrator audit functions.
- Administrators can suspend or reactivate verifier access.

### Public QR verification

- A person outside the institution can scan a student's QR credential with an ordinary smartphone camera. The QR opens a public verification page; the visitor does not need to create an account or install an application.
- The public page displays limited information: student name, institution, masked matriculation number, profile photograph and active/inactive credential status.
- It does not display the full matriculation number, email address, phone number, date of birth, home address, faculty, department or level.
- The QR credential is carried in the URL fragment rather than the HTTP path. The fragment is not sent in the initial page request or ordinary referrer header; the React page submits it to the verification API.
- Public checks are rate-limited and recorded as public verification events.

A valid QR credential confirms that the code matches a current student record. It does not prove that the person holding the code is the student. The verifier must compare the photograph with the person and follow the institution's identity-checking procedure.

### Security and accountability

- Separate administrator, verifier and student roles with server-side role checks.
- Password hashing, secure session cookies, CSRF protection, login and OTP rate limiting, one-time OTPs and one-time verifier invitations.
- QR credentials are opaque, unpredictable and revocable. Unclaimed student records have no QR credential.
- Verification logs store token fingerprints rather than reusable QR tokens.
- Administrative actions are recorded in an audit trail.
- Student photographs are stored privately, not in the public React asset directory or PostgreSQL as binary files.
- Additive database migrations preserve existing student records and historical verification activity. The application does not reset or initialise an existing database during deployment.

## External services required for the new workflows

The new email-claim and private-photo features require two external services. The existing application can still deploy without them, but student email claims and photo uploads will report that the relevant service is not configured until setup is complete.

### 1. Transactional email with Nylas

StudentVerifi uses **Nylas Transactional Send (Beta)** for student claim OTPs and verifier invitations. This is the domain-based send API; it does not require students, lecturers or administrators to connect personal Gmail or Microsoft accounts.

1. Create a Nylas application in the Nylas Dashboard and choose its data-residency region. The region cannot be changed for that application.
2. Generate an API key for the application.
3. Register and verify a sending domain in Nylas. For development, Nylas may provide a free `nylas.email` domain. For production, use a domain that Nylas has verified.
4. Configure the sender email so its domain matches the verified Nylas sending domain.
5. Add these Vercel environment variables to Preview and Production as appropriate:
   - `NYLAS_API_KEY`: private Nylas application API key.
   - `NYLAS_DOMAIN`: verified sending domain only, without `https://` or a path.
   - `NYLAS_FROM_EMAIL`: sender address on that verified domain.
   - `NYLAS_FROM_NAME`: sender display name; defaults to `StudentVerifi`.
   - `NYLAS_API_BASE_URL`: `https://api.us.nylas.com` for a US application or `https://api.eu.nylas.com` for a European application.
   - `NYLAS_REPLY_TO`: optional monitored reply address.

The server sends HTML messages to `POST /v3/domains/{domain_name}/messages/send`, authenticates with the Nylas API key, and uses an idempotency key for each OTP or verifier invitation. Keep the API key server-side; never put it in React/browser code or commit it to GitHub. Transactional Send is currently documented by Nylas as a Beta feature. Do not use an unverified sender domain.

### 2. Private profile-photo storage with Vercel Blob

1. Open the StudentVerifi project in Vercel.
2. Open **Storage** and create a **Blob** store.
3. Choose **Private** access, not Public.
4. Connect the store to the StudentVerifi project and select the environments that need access.
5. Vercel supplies `BLOB_READ_WRITE_TOKEN` to the connected project. Confirm that it is present for Production and Preview as required. Do not expose it to the browser or commit it.

The application reads and writes photographs through authenticated server-side Blob SDK operations. Release 3.1.3 pins the official `vercel==0.5.7` Python SDK, which documents `AsyncBlobClient` and constructor-based token authentication. Both dependency manifests use the same pin. The client is explicitly authenticated and closed; uploads and retrieval require private access. The existing GitHub Actions test suite now checks the real installed SDK import and call signatures without contacting the store. These tests do not verify a live upload. Upload failures are logged using safe diagnostic codes rather than provider response bodies. In Vercel Logs, filter for `Student claim photo upload failed` or `Photo storage operation=upload`:

- `missing_blob_token`: check that the read/write token is present in the exact deployment environment, and redeploy after changing it.
- `blob_access_denied`: check the token belongs to the connected Private store and has write access.
- `blob_sdk_incompatible`: check the installed SDK version in the diagnostic log; verify `vercel==0.5.7` was installed in the deployed function, and that the real-SDK test passed in GitHub Actions. If necessary redeploy the corrected generated-assets commit without reusing the build cache.
- `blob_timeout`, `blob_store_unavailable`, `blob_provider_error` or `blob_invalid_response`: check store availability and the provider request's status. Do not share secrets or raw provider exception messages.

The student-facing error remains generic. If a claim expires while troubleshooting, restart the claim and request a new code. No account or QR is created until the photograph has been stored and account activation completes.

 Do not change the store to Public: student photographs are personal information.

### Application URL

Set `APP_BASE_URL` to the public origin used by the deployment, for example `https://studentverifi.example`. It must be an origin only, with no path, query or trailing application route. This origin is embedded in QR credentials and verifier invitations. If left unset, the application uses the current request origin. For Preview deployments, use the Preview origin in the Preview environment or leave it unset so the current deployment origin is used.

The two currently implemented transactional messages (student OTP and verifier invitation) share a branded, mobile-friendly HTML email template. The public PNG branding asset is published as `/email-logo.png`. Set `APP_BASE_URL` to a publicly accessible HTTPS origin for the logo to render in email clients, including a public preview if testing there. Clients may block remote images, in which case the alternative brand text remains visible. Never use a private student photo as the email logo.

Registration uses progressive disclosure: the form displays only the current action, with no advance roadmap or step count. All claim verification and mandatory-photo requirements remain enforced server-side.

`INSTITUTION_NAME` controls the institution label displayed on the public verification result. Its default is `Ebonyi State University`. Only use an institution's name and logo in an official capacity with appropriate permission.

## Deployment to GitHub and Vercel

The intended deployment is online through GitHub, Vercel and Neon. You do not need to run the application on your personal computer to deploy it.

The established GitHub Actions workflow performs the React production build, runs the automated checks and publishes the generated `public/` assets in a follow-up commit. Vercel serves those compiled files and the Flask API; there is no separate React production server or React start command.

1. Use a preview branch named `studentverifi-v3.1` (or another branch beginning with `studentverifi-v3`) from the currently working StudentVerifi branch.
2. Create a separate Neon branch for Preview testing. In Vercel Project Settings → Environment Variables, keep the current `DATABASE_URL` value scoped to Production and set the Preview `DATABASE_URL` to the new Neon test branch. Do not point Preview at the live Production database while testing migrations.
3. Create/connect a private Vercel Blob store for Preview. Use a separate private store for Production if the project setup permits it, so test photographs do not mix with genuine student photographs. Confirm the `BLOB_READ_WRITE_TOKEN` is available in the relevant environment.
4. Upload the complete extracted project contents to the repository root, preserving `.github/workflows/`, `frontend/` and the other directories. The root `public/` production bundle is generated by GitHub Actions; it is not expected in the source ZIP. Do not upload the ZIP as one file.
5. Add the Nylas API key, verified sender domain and sender address to Preview and Production. Set `APP_BASE_URL` separately for Preview and Production, or leave it unset so the deployment's own request origin is used.
6. Open **GitHub → Actions → Compile and verify StudentVerifi**. Wait for React compilation and all tests to pass.
7. Confirm the workflow creates the follow-up commit `build: publish React assets for Vercel [skip ci]` and that `public/index.html` and `public/assets/` are present in the branch.
8. Let Vercel deploy the generated-assets commit as a Preview deployment.
9. Test administrator login, email delivery, student claim, mandatory photo upload, automatic account activation, QR generation, public verification, verifier invitation and role restrictions before promoting the release. Use test student records and mailboxes in Preview.

The existing GitHub Actions workflow is retained, with public and workspace React rendering smoke checks and the v3 preview branch filter included. It does not access Neon, change Vercel environment variables, initialise the database or perform production data deletion. Its repository write permission is used only to commit the compiled React assets after tests pass.

## Environment variables

Keep the existing production values:

- `DATABASE_URL`: Neon PostgreSQL connection string. Use the pooled connection string supplied by Neon.
- `SECRET_KEY`: a unique, high-entropy secret of at least 32 characters.
- `INITIAL_ADMIN_USERNAME`: first administrator username; used only when creating a new database.
- `INITIAL_ADMIN_PASSWORD`: first administrator password; used only when creating a new database.
- `COOKIE_SECURE`: `true` in production.
- `FLASK_DEBUG`: `false` in production.

Add or connect the new services:

- `NYLAS_API_KEY`: Nylas application API key.
- `NYLAS_DOMAIN`: verified Nylas sending domain.
- `NYLAS_FROM_EMAIL`: sender address on the verified Nylas domain.
- `NYLAS_FROM_NAME`: sender display name (optional; defaults to StudentVerifi).
- `NYLAS_API_BASE_URL`: Nylas regional API URL (US or EU).
- `NYLAS_REPLY_TO`: monitored reply address (optional).
- `BLOB_READ_WRITE_TOKEN`: supplied when a private Vercel Blob store is connected.
- `APP_BASE_URL`: public application origin, preferably the production domain.
- `INSTITUTION_NAME`: optional display name; defaults to Ebonyi State University.

Never commit `.env`, `.env.local`, API keys, database URLs, passwords, Blob tokens or secret keys.

## Database migration and existing accounts

The first authenticated API use applies additive migrations to the database selected by that Vercel environment. Test the migration on the separate Preview Neon branch first. Do not run the database initialisation command against the existing production database, do not delete tables, and do not change the Production database URL for this release.

The migration:

- Allows student records to have a null QR token until a student account is claimed.
- Adds private photo references and email-verification timestamps.
- Adds OTP challenge and verifier-invitation tables.
- Adds the verifier role and account status fields.
- Adds the public/verifier verification-channel value and the `INCOMPLETE` result.
- Preserves existing student records, user accounts, historical account requests, verification records and audit records.
- Removes QR tokens from student records that do not have a linked student account.

Existing student accounts are preserved. If an existing account has no private profile photograph, the student should upload one from the student workspace before a QR credential can be issued or displayed. Existing external photo URLs are not automatically copied into private Blob storage.

Historical approval-based account requests remain available in the administrator's request-history page. New claims use the email OTP and profile-completion workflow and do not enter the old approval queue. The old claim-code registration endpoint is retired for new registrations.

## Run locally (optional)

Local execution is optional; the intended deployment workflow is online. If a developer needs to run the project locally, the requirements are:

- Python 3.12 or newer.
- Node.js 22.12 or newer and npm.
- A PostgreSQL development database (a separate Neon development branch is suitable).
- A Nylas API key and verified sending domain for transactional email claims.
- A private Vercel Blob store token for photo upload and retrieval.
- A modern browser. Camera access requires HTTPS except on `localhost`.

1. Copy `.env.example` to `.env` and fill in development database and service credentials. Never use production secrets in a shared development environment.
2. Install Python dependencies: `python -m pip install -r requirements.txt`.
3. Install frontend dependencies: `npm install`.
4. Only if using a new, empty development database, initialise it with `python -m flask --app app init-db`. Never run this against an existing database containing student records.
5. Start the Flask application with `python app.py`.
6. In a second terminal, start the Vite development server with `npm run dev` and open the local address printed by Vite.
7. To create the single-server React bundle, run `npm run build`; the built frontend is placed in `public/`.

## Tests

- `npm run check` checks frontend JavaScript syntax and the API-client tests.
- `npm run build` creates the React production bundle.
- `python -m unittest discover -s tests -v` runs Python source, build, claim-service and Flask runtime tests in an environment with all dependencies installed.
- GitHub Actions runs the build and tests on source pushes to `main`, `master` and branches beginning with `studentverifi-v3`. Vercel deployment itself does not run the GitHub test suite.

## Responsible use and limitations

StudentVerifi is an academic prototype. Before using genuine student records, obtain institutional authorisation, approve a privacy notice and retention schedule, restrict staff permissions, establish backup and recovery procedures, and carry out security and accessibility testing. The institution must confirm the correct student-record source, matriculation-number rules, staff verification procedures and permitted public information. A QR scan alone does not establish the physical identity of its holder.
