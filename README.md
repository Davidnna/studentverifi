# StudentVerifi

StudentVerifi is a QR-code-based student identity verification application for authorised university testing and administration. The interface is built with React and React Router; Flask handles the authenticated JSON API and Neon PostgreSQL stores student records. The application is an academic prototype and must not be presented as institutional verification without approval.

## What the application does

- Administrators register, search, activate and deactivate student records and import validated CSV files.
- Administrators issue private, single-use claim codes and approve or reject student account requests.
- Students can sign in and access their own QR credentials.
- Authorised administrators scan QR credentials, with the rear camera preferred on phones, or verify a code manually.
- QR credentials can be rotated, and verification results and administrative actions are recorded without exposing reusable QR secrets.
- Accessible navigation, labelled forms, large touch targets and mobile-friendly layouts support phone and desktop use.

## Requirements

- Python 3.11 or newer
- Node.js 22.12 or newer
- PostgreSQL database such as Neon
- Modern browser with HTTPS for camera access outside localhost

## Run locally

1. Copy `.env.example` to `.env` and set `DATABASE_URL`, a strong `SECRET_KEY`, `INITIAL_ADMIN_USERNAME` and `INITIAL_ADMIN_PASSWORD`. Do not commit `.env`.
2. Install Python dependencies with `python -m pip install -r requirements.txt`.
3. Initialise a **new** database with `python -m flask --app app init-db`. This is only necessary for an empty database; do not reset an existing database.
4. Run the Flask API with `python app.py`.
5. In a second terminal, run `npm install`, then `npm run dev`. Open `http://localhost:5173`.
6. For a single-server build, run `npm run build`, then open `http://localhost:5000`.

The React application uses same-origin `/api/*` endpoints and secure, HTTP-only Flask session cookies. Its client routes are handled by React Router without full document reloads. The built frontend must exist in `public/` for single-server operation.

## Deploy to Vercel (GitHub builds React first)

Vercel hosts the Flask API and serves compiled React files from its `public/` CDN directory. **There is no separate React server or production start command.** The source files under `frontend/` cannot be served directly as a production React app.

To avoid the missing-build errors previously seen on Vercel, GitHub Actions now compiles the frontend using Node 22 and commits the generated `public/index.html`, `public/assets/`, and branding assets back to the **same branch**. Vercel then redeploys from this commit, with assets present before its Flask builder runs. The Vercel build script only **verifies** the files exist; it does not attempt to install Node or build React inside the Python builder.

1. Extract this complete project and upload its contents to a GitHub **preview branch** of the StudentVerifi repository, replacing corresponding files. Preserve the `.github/workflows/` directory.
2. In GitHub, open **Actions → Compile and verify StudentVerifi**. Confirm **Compile React into public/**, tests, and **Commit generated assets for Vercel** pass.
3. Check the branch received the automatic commit `build: publish React assets for Vercel [skip ci]` and that `public/index.html` and `public/assets/` actually exist in the branch. This is the critical step; the first deployment from source alone may fail until the build commit is present.
4. Vercel should create a new Preview deployment after the generated-assets commit. Confirm `/login` loads, assets under `/assets/` return 200, `/health` is available, and `/dashboard` opens for an authorised administrator.
5. After the preview succeeds, merge or promote the exact tested branch to production. Avoid deleting or resetting the existing Neon database.

If GitHub Actions reports **403 permission denied** when publishing compiled files, enable **Settings → Actions → General → Workflow permissions → Read and write permissions**, if your repository allows it, then re-run the workflow. Protected branches may require permission to commit; use an unprotected preview branch. GitHub's workflow can also be triggered manually by making a new source commit. The project cannot be considered successfully deployed until the compiled asset commit appears.

Keep the existing Vercel values for `DATABASE_URL` and `SECRET_KEY`; set `COOKIE_SECURE=true` and `FLASK_DEBUG=false`. Do not add a production React `npm start` or `vite --host` process. The React Router client is hosted as static files, while Flask continues to answer `/api/*`.

## Security and responsible use

Use only authorised student records. Protect claim codes and QR credentials, use staff accounts with suitable permissions, maintain database backups, and perform accessibility and security testing before institutional deployment. A valid QR credential confirms a database record, not the physical identity of its holder; staff must verify the person's identity independently.

## Troubleshooting

If the site shows `React build missing` or `GET /index.html` errors, check that the GitHub branch Vercel deployed actually contains `public/index.html` and hashed files in `public/assets/`. If not, inspect the GitHub Actions workflow; a successful Flask deploy does not imply that React was built. You may also need to check that Vercel's **Root Directory** is the repository root and **Build Command** has no stale dashboard override. The log line `StudentVerifi React assets verified` indicates that the compiled files were found by the build hook.

If assets load but login is denied, inspect `/api/session`, cookies, administrator role and the live Neon database separately. Never reset administrator passwords or the database merely to fix missing frontend assets.

## Checks

Run `npm run check`, `npm run build`, and `python -m unittest discover -s tests -v`. GitHub Actions runs these on every push and pull request and commits compiled assets after successful checks on push.
