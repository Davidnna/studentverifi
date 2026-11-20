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

## Deploy to Vercel

Vercel detects the Flask application. The `vercel.json` build command installs Node dependencies and builds React into `public/` during deployment. Keep your existing `DATABASE_URL`, `SECRET_KEY`, `INITIAL_ADMIN_USERNAME` and `INITIAL_ADMIN_PASSWORD` values. Set `COOKIE_SECURE=true` and `FLASK_DEBUG=false`. Do not reintroduce `SETUP_TOKEN` to an already initialised system.

Deploy first to a preview environment using an isolated Neon branch. Check the Vercel build log contains a successful Vite build and that `public/index.html` is generated. Verify administrator sign-in, direct navigation to `/dashboard`, mobile scanner behaviour, student management, claim codes, QR rotation and audit logs before promoting to production. The `GET /health` endpoint returns only a minimal service status.

The build must fail rather than silently serve the legacy Flask pages. The legacy server-rendered interface has been removed to avoid conflicting login and navigation behaviours.

## Security and responsible use

Use only authorised student records. Protect claim codes and QR credentials, use staff accounts with suitable permissions, maintain database backups, and perform accessibility and security testing before institutional deployment. A valid QR credential confirms a database record, not the physical identity of its holder; staff must verify the person's identity independently.

## Checks

Run `npm run check`, `npm run build`, and `python -m unittest discover -s tests -v`. GitHub Actions runs these on every push and pull request.
