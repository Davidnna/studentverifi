# StudentVerifi — Neon PostgreSQL edition

A web-based academic prototype for QR-code-assisted student identity verification
at Ebonyi State University (EBSU). Built with Flask, SQLAlchemy, Psycopg 3,
Neon PostgreSQL, and Vercel. **Not an official EBSU service.**

## Online-only deployment (no local Python installation)

Follow **[ONLINE_DEPLOYMENT.md](ONLINE_DEPLOYMENT.md)**. It covers uploading the
extracted **contents** of this complete project ZIP to the existing GitHub
repository, adding Vercel environment variables, deploying, inspecting `/health`,
visiting the private `/setup` page once, and removing the setup token afterwards.

A ZIP committed as a single file **will not deploy the Flask source**. GitHub
must contain the project files (`app.py`, `academic_catalogue.py`,
`requirements.txt`, `vercel.json`, `templates/`, `static/`, etc.) at the repository
root. No commands on your computer are necessary.

## Features

- 10 faculties and 59 departments from the [published EBSU faculties page](https://ebsu.edu.ng/faculties/).
- Academic catalogue aliases for ordinary spelling variations; unrecognised or
  ambiguous academic units are rejected rather than guessed.
- Separate first, middle and surname fields, with a computed full-name view.
- Configurable matriculation number validation. The default verifies structure
  only; it is **not** an official EBSU matriculation-format specification.
- Manual student registration and UTF-8 CSV import (up to 8 MB). Supports the
  new separated names and legacy `full_name` CSVs; 2,500-row datasets are
  supported in principle, subject to actual file validation and server limits.
- Admin/student authentication and administrator approval of student requests.
- Token-based student QR images, camera scanner, verification audit logs and
  dashboard. A QR token alone is not proof of the holder's identity.
- PostgreSQL schema creation through explicitly protected browser setup or
  `flask init-db` command. **No database initialization during import**.
- `/health` checks connectivity and whether initial database tables exist.

## Important safeguards

Keep all environment secrets in Vercel (not source control). Use an SSL-enabled,
pooled Neon `DATABASE_URL`. Remove `SETUP_TOKEN` after setup. Only import student
records you have permission to process. Do not assume uploaded records are
university-verified. Do not run setup against an existing production database
without first inspecting its schema and taking a backup; this release assumes
new, empty PostgreSQL tables.

## Local development (optional only)

```bash
pip install -r requirements.txt
# Configure a .env with your own PostgreSQL DATABASE_URL and secrets.
python -m flask --app app init-db
python app.py
```

Vercel does not run the optional CLI. The browser-based `/setup` route is the
recommended option for this project.
