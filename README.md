# StudentVerifi

StudentVerifi is a web-based student-record management and QR-assisted identity verification application. It combines a React and React Router interface with a Flask JSON API and PostgreSQL database support, including Neon PostgreSQL.

It is an academic software prototype. Use genuine institutional records only after obtaining institutional authorisation and establishing appropriate privacy, access-control, backup and retention procedures.

## What the software does

### Administrator workspace

- View student totals, active and inactive records, pending account requests and verification activity.
- Search, add, view, activate and deactivate student records.
- Import student records from a validated UTF-8 CSV file.
- Issue private one-time claim codes to students whose records already exist.
- Review, approve or reject student account requests and filter the complete pending, approved and rejected history.
- Verify student QR credentials using a camera or manual code entry.
- Review the latest verification outcomes directly beneath the scanner and manual-entry tools in one verification centre.
- Review administrative activity, including the actor, action, target and summary.
- Rotate a QR credential if it is lost or compromised.
- Review and remove the known synthetic `DEMO/2026/` test records through a confirmation-controlled maintenance page.

### Student workspace

- Request an account using an existing student record and a private claim code issued by an administrator.
- Sign in after the administrator approves the request.
- View personal student details and access the student's own QR credential.
- Change the account password.

### Public information and accessibility

- Read about the platform, account requests, the verification workflow, privacy and responsible use.
- Use the application on desktop, tablet and mobile screens.
- Navigate with a keyboard and assistive technologies using labelled controls, visible focus states, accessible status messages and reduced-motion support.
- Scan QR credentials on a supported phone browser. The scanner requests the rear-facing camera first and provides camera selection and manual-entry alternatives.

A successful QR scan confirms that a credential matches a current record. It does not prove that the person presenting it is the student. Verifiers must independently check the person's identity.

## Technology

- Frontend: React 18, React Router 6, Vite and `html5-qrcode`.
- Backend: Python, Flask and Flask-WTF CSRF protection.
- Database: PostgreSQL, including Neon PostgreSQL.
- Database access: SQLAlchemy and Psycopg 3.
- Deployment: Vercel, with GitHub Actions compiling React into the `public/` directory before Vercel packages Flask.

The signed-in administrator workspace uses a persistent left sidebar, an expanded operational dashboard and client-side React Router navigation. Verification history is consolidated with the scanner, while account requests retain their approval and rejection history. A route-level error boundary prevents unexpected page-rendering errors from leaving the workspace blank. The React API client obtains a CSRF token before state-changing requests and refreshes an expired token once before retrying. Server-side CSRF protection remains enabled.

## Run locally

### Requirements

- Python 3.12 or newer.
- Node.js 22.12 or newer and npm.
- A PostgreSQL database. A Neon development branch is suitable.
- A modern browser. Camera access requires HTTPS, except on `localhost`.

### 1. Configure the environment

Copy `.env.example` to `.env` and set:

- `DATABASE_URL`: PostgreSQL connection string for your development database. Use the Neon pooled connection string when using Neon.
- `SECRET_KEY`: a unique random secret of at least 32 characters.
- `INITIAL_ADMIN_USERNAME`: username for the first administrator account.
- `INITIAL_ADMIN_PASSWORD`: unique password for the first administrator account, between 10 and 128 characters.
- `COOKIE_SECURE`: set to `false` for local HTTP development. Production deployments must use secure cookies.
- `FLASK_DEBUG`: set to `true` only for local development.

Never commit `.env` or share database credentials, passwords or secret keys.

### 2. Install Python dependencies

```bash
python -m pip install -r requirements.txt
```

### 3. Initialise an empty development database

Run this only against a new, empty development database:

```bash
python -m flask --app app init-db
```

This creates the schema, seeds the academic catalogue and creates the initial administrator if one does not already exist. Do not run fresh-database setup against the existing production database as a troubleshooting step. Back up and assess an existing database before any schema operation.

### 4. Start the Flask API

```bash
python app.py
```

The API runs at `http://127.0.0.1:5000`.

### 5. Start the React development server

Open a second terminal in the project root:

```bash
npm install
npm run dev
```

Open the local URL printed by Vite, normally `http://localhost:5173`. Vite proxies `/api/` and `/health` requests to Flask on port 5000.

### 6. Run checks

```bash
npm run check
npm run build
python -m unittest discover -s tests -v
```

The Python tests require the dependencies in `requirements.txt`. The client tests use Node's built-in test runner.

## Deployment notes

Vercel serves the compiled React files from `public/` and runs Flask for the API. React does not need a separate production start command. The GitHub Actions workflow installs dependencies, runs client and source checks, builds React into `public/`, writes a source-commit marker, runs the Python tests and commits the generated frontend assets. Vercel ignores the intermediate source commit and builds only the generated-assets commit whose marker matches its parent source commit. This prevents Vercel from deploying a backend update with stale or missing React files. The deployed commit must contain `public/index.html` and `public/assets/`.

Keep the existing production Neon database and environment variables when deploying an application update. Do not rerun `init-db` against the production database. Confirm the GitHub Actions workflow and Vercel deployment logs before promoting a preview release.

## Data protection and operational responsibilities

Use only authorised student records. Administrators should issue claim codes privately, review account requests and maintain appropriate access permissions. Keep database backups and test recovery. Establish an institution-approved privacy notice, retention policy and process for correcting student information before using the application operationally.
