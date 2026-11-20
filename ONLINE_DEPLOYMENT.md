# Deploy StudentVerifi entirely online — GitHub + Vercel + Neon

This release corrects the `academic_catalogue.py` circular import, replaces
MySQL with Neon PostgreSQL, and supports browser-only database initialisation.
You do **not** need to run the application on your laptop.

### 1. Upload the complete source archive into GitHub

1. Download `studentverifi-neon-fixed-full.zip` and extract it using the normal
   operating-system ZIP extractor. Extraction is **not** running the application.
2. Open your existing StudentVerifi GitHub repository in your browser. Keep the
   same repository and Vercel-linked branch you have already configured.
3. Use **Add file → Upload files** to upload the project files and folders from
   inside the extracted archive. In particular, the GitHub repository root must
   contain `app.py`, `academic_catalogue.py`, `requirements.txt`, `vercel.json`,
   `templates/` and `static/`. If GitHub's browser uploader does not support
   folder drag-and-drop on your browser, use a browser-based GitHub file upload
   approach that retains directory structure.
4. Replace the older files, not just add the ZIP as an attachment. Commit to
   the Vercel-linked branch with the message below.

**Git commit message:**

```
fix: rebuild StudentVerifi for Neon and resolve catalogue circular import
```

A ZIP uploaded as just `studentverifi-neon-fixed-full.zip` will NOT replace the
repository's Flask application.

### 2. Check the Vercel environment variables

In Vercel → StudentVerifi → Settings → Environment Variables, confirm the
**Production** environment has these (do not share their secret values):

- `DATABASE_URL`: complete Neon **pooled** PostgreSQL connection URL, including
  `?sslmode=require` (Neon host usually contains `-pooler`).
- `SECRET_KEY`: unique, strong random secret for Flask sessions.
- `INITIAL_ADMIN_USERNAME`: e.g. `admin` (or your chosen username).
- `INITIAL_ADMIN_PASSWORD`: unique password of at least ten characters. Used
  **only when creating a missing administrator**; does not reset an existing one.
- `SETUP_TOKEN`: another **different**, unguessable value at least 32 characters.
  This temporarily protects the `/setup` route and is removed after setup.
- `COOKIE_SECURE`: `true` (for the HTTPS Vercel domain).

Do not include quotes around values unless they are part of the actual value.
Never paste these secrets into a chat, issue, screenshot or GitHub file.

### 3. Deploy and check basic application startup

Open Vercel → Deployments. Make sure the newest Git commit has deployed
successfully. If you changed environment variables AFTER the build, redeploy.
Open your site home page (`/`), then `/health`.

- `{"status":"ok","database":"connected","schema":"not_initialized"}`:
  Neon connectivity works, but tables need initialisation (expected on new DB).
- `{"status":"ok","database":"connected","schema":"ready"}`:
  Neon connected and core tables are present; continue to site/login testing.
- 503 `{"status":"unavailable","database":"unavailable"}`: inspect latest
  **Vercel runtime logs** to identify Neon authentication, URL/TLS, timeout or
  network errors. Do not change credentials by guesswork.
- A Python import traceback: the deployed repository may have missing files or
  mismatched code. In particular, `academic_catalogue.py` must NOT import itself.

### 4. Initialise Neon once through your browser

For a **new or verified empty** Neon database, open:

```
https://YOUR-ACTUAL-VERCEL-DOMAIN.vercel.app/setup
```

Paste your private `SETUP_TOKEN` into the form and click **Initialise database**.
The application will make the schema, load ten faculties and 59 departments,
and create the initial administrator when the configured username is absent.
The operation is intended to be repeatable and will not reset an existing
admin password. It does not migrate unknown legacy PostgreSQL schemas.

If setup fails, check Vercel → Logs and send only the redacted error traceback.
You do not have to use the Neon SQL Editor for this step.

After success, remove **`SETUP_TOKEN`** from Vercel → Environment Variables and
redeploy. This disables `/setup` (404). Do not keep it permanently exposed.

### 5. Log in and verify

- Open `/login` using `INITIAL_ADMIN_USERNAME` and `INITIAL_ADMIN_PASSWORD`.
- Visit Dashboard → Students → Add sample test records.
- Open a test student and verify its QR from the **Verify ID** page.
- Visit Logs and ensure the verification is recorded.
- Then use the CSV template and import actual records **only with permission**.

### 6. Optional Neon read-only query

In the SQL Editor, select the SAME branch/database used in your Vercel URL, then:

```sql
SELECT table_name FROM information_schema.tables
WHERE table_schema = 'public' ORDER BY table_name;
```

This is diagnostic, **not** a necessary deployment or setup step.

### Limitations

This update was tested statically and through simulated tests, not against your
private live Neon database or deployed Vercel project. Browser setup must be
verified after deployment. The attached earlier source archive was the MySQL
version, so this is a coordinated rebuild that preserves its known features;
we cannot establish byte-for-byte identity with the newer PostgreSQL package
already in your GitHub repository. Existing populated databases require a
separately reviewed schema migration/backup.
