# StudentVerifi · EBSU

Flask web application for registering students, generating QR tokens, verifying student identity, and reviewing verification logs. Database: MySQL.

## Run locally
1. Use Python 3.11 or 3.12.
2. Create and activate a virtual environment.
3. Install dependencies: `pip install -r requirements.txt`.
4. Copy `.env.example` to `.env` and set `DATABASE_URL`, `SECRET_KEY`, `INITIAL_ADMIN_USERNAME`, and `INITIAL_ADMIN_PASSWORD`.
5. Create a MySQL database and ensure the URL points to it. URL-encode special characters in usernames/passwords.
6. Run `python app.py`.
7. Sign in using the initial credentials and change the password immediately.

## Fresh deployment: Vercel + Aiven MySQL

### 1. Create a fresh GitHub repository
Create an empty repository named `studentverifi` (or another available name), then upload the contents of this folder to the repository root. The repository name does not guarantee the matching `vercel.app` URL will be available; choose an available Vercel project name during import.


- Commit this project's files, including `vercel.json` and `public/static/`.
- Do not commit `.env`, passwords, or other secrets.
- `app.py` is the Flask entry point detected by Vercel. `public/static/` contains the static assets for Vercel hosting.

### 2. Import into Vercel
- Import the GitHub repository into Vercel.
- Keep the root directory as `./` and the Flask preset if it is detected.
- Configure these Environment Variables for Production (and Preview only if needed):
  - `DATABASE_URL`: Aiven's MySQL connection URL, using `mysql+pymysql://` or `mysql://`, with the database name and port supplied by Aiven.
  - `SECRET_KEY`: a long, random secret unique to this deployment.
  - `INITIAL_ADMIN_USERNAME`: desired initial administrator username.
  - `INITIAL_ADMIN_PASSWORD`: a strong, unique initial password.
  - `COOKIE_SECURE`: `true`.
  - `MYSQL_SSL_CA_PEM`: optional but recommended; paste the Aiven service CA certificate PEM to verify the database server certificate.
- Do not put secrets in source files or commit them to GitHub.
- Deploy and check the Vercel function logs if startup fails.

### 3. Aiven connection details
Use the host, port, database name, and credentials from the Aiven service's connection information. Aiven MySQL requires TLS. For certificate verification, download the service CA certificate from Aiven and add its complete PEM text as `MYSQL_SSL_CA_PEM` in Vercel. Do not share the password or full connection string publicly.

### 4. First deployment checks
- Open `/health` and confirm it returns `{"status":"ok"}`.
- Sign in with the configured initial admin credentials.
- Change the initial admin password.
- Test student registration, QR image download, active/inactive/invalid verification, logs, logout, and password change.

## Branding
The application name is StudentVerifi. The institution subtitle remains Ebonyi State University (EBSU).

## Important notes
- The application creates its tables during startup. This is convenient for a small prototype but is not a substitute for versioned database migrations in a larger system.
- Serverless instances may start and stop, so the database must remain the persistent source of truth.
- Before entering real student data, confirm database backups and access controls.


## Public information pages
The public interface includes Home, About, How it works, FAQ, Privacy, and Contact pages. These pages are informational and do not expose student records or operational verification tools. Sign-in is labelled neutrally in the public navigation.

Accessibility and responsive design include semantic page structure, a skip link, visible keyboard focus, scalable headings, responsive layouts, accessible status messages, and reduced-motion support. Please still test with keyboard navigation, a screen reader, and small-screen devices before presenting the prototype.
