"""StudentVerifi — Flask + Neon PostgreSQL (online-first academic prototype).

NO database I/O occurs when this module is imported by Vercel. Database
schema/bootstrap is explicitly initiated through /setup or flask init-db.
"""
import csv
import hashlib
import hmac
import ipaddress
import io
import os
import re
import secrets
from datetime import datetime, timezone, timedelta
from functools import wraps
from urllib.parse import urlsplit

import qrcode
from dotenv import load_dotenv
from flask import (Flask, abort, flash, g, make_response, redirect, render_template,
                   request, send_file, session, url_for)
from flask_wtf.csrf import CSRFProtect
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from werkzeug.security import check_password_hash, generate_password_hash

from academic_catalogue import (FACULTY_DEPARTMENTS, DEPARTMENT_ALIASES,
                                FACULTY_ALIASES, academic_catalogue_counts,
                                resolve_department, resolve_faculty)

load_dotenv()
app = Flask(__name__)
IS_PRODUCTION = bool(os.environ.get("VERCEL") or os.environ.get("RAILWAY_ENVIRONMENT"))
SECRET_KEY = os.environ.get("SECRET_KEY")
if IS_PRODUCTION and not SECRET_KEY:
    raise RuntimeError("Set SECRET_KEY in the production environment variables.")
if IS_PRODUCTION and SECRET_KEY and len(SECRET_KEY) < 32:
    # Warn without causing an unexpected production outage; replace this value
    # with a unique high-entropy secret in the Vercel project settings.
    import warnings
    warnings.warn("Production SECRET_KEY should contain at least 32 random characters.", RuntimeWarning)
app.config.update(
    SECRET_KEY=SECRET_KEY or "dev-only-not-for-deployment",
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    # HTTPS-only cookies are mandatory in production, regardless of a weaker
    # environment-variable setting.
    SESSION_COOKIE_SECURE=(IS_PRODUCTION or os.environ.get("COOKIE_SECURE", "false").lower() == "true"),
    PERMANENT_SESSION_LIFETIME=timedelta(hours=8),
    SESSION_REFRESH_EACH_REQUEST=False,
    WTF_CSRF_TIME_LIMIT=3600,
    WTF_CSRF_SSL_STRICT=IS_PRODUCTION,
    MAX_CONTENT_LENGTH=9 * 1024 * 1024,
)
csrf = CSRFProtect(app)
_ENGINE = None
_SECURITY_MIGRATIONS_READY = False


@app.before_request
def prepare_security_context():
    """Create a per-response nonce for the strict Content Security Policy."""
    g.csp_nonce = secrets.token_urlsafe(18)


@app.context_processor
def inject_security_context():
    return {"csp_nonce": getattr(g, "csp_nonce", "")}


@app.after_request
def apply_security_headers(response):
    """Apply browser-side security controls and prevent caching of records."""
    nonce = getattr(g, "csp_nonce", "")
    response.headers["Content-Security-Policy"] = "; ".join([
        "default-src 'self'",
        "base-uri 'self'",
        "form-action 'self'",
        "frame-ancestors 'none'",
        "object-src 'none'",
        f"script-src 'self' https://unpkg.com 'nonce-{nonce}'",
        "style-src 'self' 'unsafe-inline'",
        "img-src 'self' data: https:",
        "font-src 'self' data:",
        "connect-src 'self'",
        "worker-src 'self' blob:",
        "media-src 'self' blob:",
        "upgrade-insecure-requests" if IS_PRODUCTION else "",
    ]).replace("; ;", ";").strip("; ")
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Permissions-Policy"] = "camera=(self), microphone=(), geolocation=()"
    response.headers["Cross-Origin-Opener-Policy"] = "same-origin"
    response.headers["Cross-Origin-Resource-Policy"] = "same-origin"
    response.headers["X-Permitted-Cross-Domain-Policies"] = "none"
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    response.headers["Pragma"] = "no-cache"
    if IS_PRODUCTION:
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    return response


def get_engine():
    """Lazily make an SQLAlchemy engine. Importing Flask never opens a connection."""
    global _ENGINE
    if _ENGINE is None:
        raw = (os.environ.get("DATABASE_URL") or "").strip()
        if not raw:
            raise RuntimeError("DATABASE_URL is not configured in Vercel.")
        url = make_url(raw)
        if url.drivername not in ("postgresql", "postgres", "postgresql+psycopg"):
            raise RuntimeError("DATABASE_URL must point to Neon PostgreSQL, not MySQL.")
        url = url.set(drivername="postgresql+psycopg")
        _ENGINE = create_engine(url, pool_pre_ping=True, pool_size=2,
                                max_overflow=1, pool_timeout=10,
                                connect_args={"connect_timeout": 10})
    return _ENGINE


class CompatRow:
    """Support template dot-access and legacy row['field'] access."""
    def __init__(self, row):
        self._row = row
        self._mapping = row._mapping

    def __getitem__(self, key):
        return self._mapping[key] if isinstance(key, str) else self._row[key]

    def __getattr__(self, name):
        try:
            return self._mapping[name]
        except KeyError as exc:
            raise AttributeError(name) from exc


class CompatResult:
    def __init__(self, result):
        self.result = result

    def fetchone(self):
        row = self.result.fetchone()
        return CompatRow(row) if row is not None else None

    def fetchall(self):
        return [CompatRow(row) for row in self.result.fetchall()]

    def first(self):
        row = self.result.first()
        return CompatRow(row) if row is not None else None


class DBCompat:
    def __init__(self, connection):
        self.connection = connection

    def execute_many(self, query, records):
        """Batch inserts via Psycopg 3 executemany in one transaction."""
        return self.connection.execute(text(query), records)

    def execute(self, query, params=()):
        query = query.strip()
        if isinstance(params, dict):
            return CompatResult(self.connection.execute(text(query), params))
        if params:
            parts = query.split("?")
            if len(parts) - 1 != len(params):
                raise ValueError("SQL placeholder count does not match arguments.")
            bindings = {f"param{i}": value for i, value in enumerate(params)}
            sql = parts[0] + "".join(f":param{i}" + parts[i + 1] for i in range(len(params)))
            return CompatResult(self.connection.execute(text(sql), bindings))
        return CompatResult(self.connection.execute(text(query)))


class DBContext:
    def __enter__(self):
        self.transaction = get_engine().begin()
        return DBCompat(self.transaction.__enter__())

    def __exit__(self, exc_type, exc, tb):
        return self.transaction.__exit__(exc_type, exc, tb)


def get_db():
    return DBContext()


SCHEMA_STATEMENTS = (
    """CREATE TABLE IF NOT EXISTS faculties (
        id INTEGER GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
        name VARCHAR(160) UNIQUE NOT NULL
    )""",
    """CREATE TABLE IF NOT EXISTS departments (
        id INTEGER GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
        faculty_id INTEGER NOT NULL REFERENCES faculties(id) ON DELETE RESTRICT,
        name VARCHAR(180) NOT NULL,
        UNIQUE (faculty_id, name),
        UNIQUE (id, faculty_id)
    )""",
    """CREATE TABLE IF NOT EXISTS students (
        id INTEGER GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
        matric_no VARCHAR(100) UNIQUE NOT NULL,
        first_name VARCHAR(100) NOT NULL,
        middle_name VARCHAR(100) NOT NULL DEFAULT '',
        last_name VARCHAR(100) NOT NULL,
        faculty_id INTEGER NOT NULL REFERENCES faculties(id) ON DELETE RESTRICT,
        department_id INTEGER NOT NULL,
        level VARCHAR(50) NOT NULL,
        email VARCHAR(254),
        photo_url VARCHAR(1000),
        token VARCHAR(128) UNIQUE NOT NULL,
        status VARCHAR(20) NOT NULL DEFAULT 'Active' CHECK(status IN ('Active','Inactive')),
        record_source VARCHAR(30) NOT NULL DEFAULT 'imported',
        claim_code_hash VARCHAR(255),
        claimed_at TIMESTAMPTZ,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        CONSTRAINT fk_students_dept_faculty FOREIGN KEY (department_id, faculty_id)
            REFERENCES departments(id, faculty_id)
    )""",
    """CREATE TABLE IF NOT EXISTS users (
        id INTEGER GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
        username VARCHAR(100) UNIQUE NOT NULL,
        password_hash VARCHAR(255) NOT NULL,
        role VARCHAR(30) NOT NULL DEFAULT 'admin' CHECK(role IN ('admin','student')),
        student_id INTEGER UNIQUE REFERENCES students(id) ON DELETE SET NULL,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )""",
    """CREATE TABLE IF NOT EXISTS admin_audit_logs (
        id INTEGER GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
        actor_user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
        action VARCHAR(80) NOT NULL,
        target_type VARCHAR(40),
        target_id INTEGER,
        summary VARCHAR(255) NOT NULL DEFAULT '',
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )""",
    "CREATE INDEX IF NOT EXISTS ix_admin_audit_created_at ON admin_audit_logs(created_at DESC)",
    """CREATE TABLE IF NOT EXISTS student_account_requests (
        id INTEGER GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
        student_id INTEGER NOT NULL REFERENCES students(id) ON DELETE CASCADE,
        password_hash VARCHAR(255) NOT NULL,
        claim_code_verified BOOLEAN NOT NULL DEFAULT FALSE,
        status VARCHAR(20) NOT NULL DEFAULT 'Pending' CHECK(status IN ('Pending','Approved','Rejected')),
        requested_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        reviewed_at TIMESTAMPTZ,
        reviewed_by INTEGER REFERENCES users(id) ON DELETE SET NULL
    )""",
    """CREATE TABLE IF NOT EXISTS verification_logs (
        id INTEGER GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
        student_id INTEGER REFERENCES students(id) ON DELETE SET NULL,
        scanned_token VARCHAR(200) NOT NULL DEFAULT '[REDACTED]',
        token_fingerprint VARCHAR(64),
        result VARCHAR(20) NOT NULL CHECK (result IN ('VALID','INACTIVE','INVALID')),
        verified_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
        verified_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )""",
    "CREATE INDEX IF NOT EXISTS ix_students_names ON students(last_name, first_name)",
    "CREATE INDEX IF NOT EXISTS ix_students_department ON students(department_id)",
    "CREATE INDEX IF NOT EXISTS ix_logs_verified_at ON verification_logs(verified_at DESC)",
    "CREATE INDEX IF NOT EXISTS ix_requests_status ON student_account_requests(status)",
    "CREATE UNIQUE INDEX IF NOT EXISTS uq_pending_request ON student_account_requests(student_id) WHERE status = 'Pending'",
    """CREATE TABLE IF NOT EXISTS auth_rate_limits (
        bucket_hash VARCHAR(64) PRIMARY KEY,
        attempts INTEGER NOT NULL DEFAULT 0,
        window_started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        blocked_until TIMESTAMPTZ
    )""",
    "CREATE INDEX IF NOT EXISTS ix_auth_rate_limits_blocked ON auth_rate_limits(blocked_until)",
    """CREATE OR REPLACE VIEW student_profiles AS
        SELECT s.*, f.name AS faculty, d.name AS department,
        TRIM(CONCAT_WS(' ', s.first_name, NULLIF(s.middle_name,''), s.last_name)) AS full_name
        FROM students s
        JOIN faculties f ON f.id = s.faculty_id
        JOIN departments d ON d.id = s.department_id""",
)


def now():
    return datetime.now(timezone.utc)


def init_db():
    """Explicit, idempotent *fresh PostgreSQL* schema/seed operation.

    Existing schemas from other releases are not automatically migrated. Back
    up and assess them before running this on a populated database.
    """
    username = (os.environ.get("INITIAL_ADMIN_USERNAME") or "admin").strip()
    initial_password = os.environ.get("INITIAL_ADMIN_PASSWORD", "")
    if not username or len(username) > 80:
        raise RuntimeError("Set a valid INITIAL_ADMIN_USERNAME (up to 80 characters).")
    if len(initial_password) < 10 or len(initial_password) > 128:
        raise RuntimeError("INITIAL_ADMIN_PASSWORD must contain between 10 and 128 characters for setup.")
    with get_engine().begin() as conn:
        for statement in SCHEMA_STATEMENTS:
            conn.execute(text(statement))
        for faculty, departments in FACULTY_DEPARTMENTS.items():
            conn.execute(text("INSERT INTO faculties (name) VALUES (:n) ON CONFLICT(name) DO NOTHING"), {"n": faculty})
            faculty_id = conn.execute(text("SELECT id FROM faculties WHERE name = :n"), {"n": faculty}).scalar_one()
            for department in departments:
                conn.execute(text("""INSERT INTO departments (faculty_id, name)
                           VALUES (:f, :n) ON CONFLICT (faculty_id, name) DO NOTHING"""),
                           {"f": faculty_id, "n": department})
        existing_admin = conn.execute(text("SELECT id FROM users WHERE username = :u"), {"u": username}).first()
        if existing_admin is None:
            conn.execute(text("""INSERT INTO users(username,password_hash,role,created_at)
                                 VALUES (:u,:h,'admin',:now)"""),
                         {"u": username, "h": generate_password_hash(initial_password), "now": now()})
    global _SECURITY_MIGRATIONS_READY
    _SECURITY_MIGRATIONS_READY = False
    return academic_catalogue_counts()


def ensure_security_migrations():
    """Apply safe, additive security migrations to an already initialised DB.

    This is deliberately lazy: Vercel can import the Flask application without
    opening a database connection. The migration runs on login or an
    authenticated request, not during module import.
    """
    global _SECURITY_MIGRATIONS_READY
    if _SECURITY_MIGRATIONS_READY:
        return
    with get_engine().begin() as conn:
        conn.execute(text("""CREATE TABLE IF NOT EXISTS auth_rate_limits (
            bucket_hash VARCHAR(64) PRIMARY KEY,
            attempts INTEGER NOT NULL DEFAULT 0,
            window_started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            blocked_until TIMESTAMPTZ
        )"""))
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_auth_rate_limits_blocked ON auth_rate_limits(blocked_until)"))
        users_exist = bool(conn.execute(text("SELECT to_regclass('public.users') IS NOT NULL")).scalar())
        if users_exist:
            conn.execute(text("""CREATE TABLE IF NOT EXISTS admin_audit_logs (
                id INTEGER GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
                actor_user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
                action VARCHAR(80) NOT NULL,
                target_type VARCHAR(40),
                target_id INTEGER,
                summary VARCHAR(255) NOT NULL DEFAULT '',
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )"""))
            conn.execute(text("CREATE INDEX IF NOT EXISTS ix_admin_audit_created_at ON admin_audit_logs(created_at DESC)"))
        logs_exist = bool(conn.execute(text("SELECT to_regclass('public.verification_logs') IS NOT NULL")).scalar())
        if logs_exist:
            conn.execute(text("ALTER TABLE verification_logs ADD COLUMN IF NOT EXISTS token_fingerprint VARCHAR(64)"))
            old_rows = conn.execute(text("""SELECT id, scanned_token FROM verification_logs
                WHERE token_fingerprint IS NULL AND scanned_token <> '[REDACTED]'""")).fetchall()
            for row in old_rows:
                fingerprint = hashlib.sha256(str(row._mapping["scanned_token"]).encode("utf-8")).hexdigest()
                conn.execute(text("""UPDATE verification_logs
                    SET token_fingerprint=:fingerprint, scanned_token='[REDACTED]' WHERE id=:id"""),
                    {"fingerprint": fingerprint, "id": row._mapping["id"]})
            # Redact any legacy token even if a prior partial migration populated
            # the fingerprint but did not replace the original token.
            conn.execute(text("""UPDATE verification_logs SET scanned_token='[REDACTED]'
                WHERE scanned_token <> '[REDACTED]' AND token_fingerprint IS NOT NULL"""))
        conn.execute(text("DELETE FROM auth_rate_limits WHERE COALESCE(blocked_until, window_started_at) < NOW() - INTERVAL '1 day'"))
    _SECURITY_MIGRATIONS_READY = True


def _rate_limit_hash(scope, value):
    key = str(app.config["SECRET_KEY"]).encode("utf-8")
    payload = f"{scope}:{value}".encode("utf-8", "replace")
    return hmac.new(key, payload, hashlib.sha256).hexdigest()


def _login_rate_limit_buckets(username):
    buckets = [_rate_limit_hash("login-username", (username or "").strip().casefold())]
    remote = request.remote_addr or ""
    if remote and remote not in ("127.0.0.1", "::1", "unknown"):
        buckets.append(_rate_limit_hash("login-ip", remote))
    return buckets


def _rate_limit_remaining(db, buckets):
    rows = db.execute("SELECT blocked_until FROM auth_rate_limits WHERE bucket_hash = ANY(:buckets)",
                      {"buckets": buckets}).fetchall()
    current = now()
    remaining = [max(1, int((row["blocked_until"] - current).total_seconds()))
                 for row in rows if row["blocked_until"] and row["blocked_until"] > current]
    return max(remaining, default=0)


def _record_rate_limit_failure(db, buckets, *, limit=8, window_minutes=15, block_minutes=15):
    current = now()
    cutoff = current - timedelta(minutes=window_minutes)
    blocked = current + timedelta(minutes=block_minutes)
    for bucket in buckets:
        db.execute("""INSERT INTO auth_rate_limits(bucket_hash, attempts, window_started_at, blocked_until)
            VALUES (:bucket, 1, :current, NULL)
            ON CONFLICT (bucket_hash) DO UPDATE SET
              attempts = CASE WHEN auth_rate_limits.window_started_at < :cutoff
                              THEN 1 ELSE auth_rate_limits.attempts + 1 END,
              window_started_at = CASE WHEN auth_rate_limits.window_started_at < :cutoff
                                       THEN EXCLUDED.window_started_at
                                       ELSE auth_rate_limits.window_started_at END,
              blocked_until = CASE WHEN
                (CASE WHEN auth_rate_limits.window_started_at < :cutoff
                      THEN 1 ELSE auth_rate_limits.attempts + 1 END) >= :limit
                THEN :blocked ELSE NULL END""",
            {"bucket": bucket, "current": current, "cutoff": cutoff,
             "limit": limit, "blocked": blocked})


def _clear_rate_limit_failures(db, buckets):
    db.execute("DELETE FROM auth_rate_limits WHERE bucket_hash = ANY(:buckets)", {"buckets": buckets})


def audit_admin_action(db, action, target_type=None, target_id=None, summary=""):
    """Record a concise admin action without copying student PII or secrets."""
    actor_id = session.get("user_id")
    if actor_id:
        db.execute("""INSERT INTO admin_audit_logs
            (actor_user_id, action, target_type, target_id, summary, created_at)
            VALUES (?, ?, ?, ?, ?, ?)""",
            (actor_id, action[:80], target_type[:40] if target_type else None,
             target_id, summary[:255], now()))


def _database_is_initialized():
    with get_engine().connect() as conn:
        ready = conn.execute(text("""SELECT
            to_regclass('public.students') IS NOT NULL AND
            to_regclass('public.users') IS NOT NULL AND
            to_regclass('public.faculties') IS NOT NULL AND
            to_regclass('public.departments') IS NOT NULL""")).scalar()
        if not ready:
            return False
        return bool(conn.execute(text("SELECT EXISTS (SELECT 1 FROM users WHERE role='admin')")).scalar())


@app.cli.command("init-db")
def init_db_command():
    faculties, departments = init_db()
    print(f"Schema initialized; {faculties} faculties, {departments} departments seeded.")


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not session.get("user_id"):
            flash("Please sign in to continue.", "warning")
            return redirect(url_for("login"))
        try:
            ensure_security_migrations()
        except SQLAlchemyError:
            app.logger.exception("Security database migration failed")
            abort(503)
        return view(*args, **kwargs)
    return wrapped


def admin_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not session.get("user_id"):
            flash("Please sign in to continue.", "warning")
            return redirect(url_for("login"))
        if session.get("role") != "admin":
            abort(403)
        try:
            ensure_security_migrations()
        except SQLAlchemyError:
            app.logger.exception("Security database migration failed")
            abort(503)
        return view(*args, **kwargs)
    return wrapped


def qr_image_for_token(token):
    image = qrcode.make(token)
    stream = io.BytesIO()
    image.save(stream, format="PNG")
    stream.seek(0)
    return stream


def validate_matric(value):
    value = (value or "").strip().upper()
    pattern = os.environ.get("MATRIC_REGEX") or r"^[A-Z0-9][A-Z0-9/._-]{3,49}$"
    if not re.fullmatch(pattern, value):
        raise ValueError("Invalid matriculation-number structure. Check letters, digits and separators.")
    return value


def valid_email(value):
    return not value or (len(value) <= 254 and bool(re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", value)))


def student_identity(source, *, legacy=False):
    """Validate and canonicalize a form/CSV row. No DB connection required."""
    matric = validate_matric(source.get("matric_no", ""))
    first = (source.get("first_name") or "").strip()
    middle = (source.get("middle_name") or "").strip()
    last = (source.get("last_name") or source.get("surname") or "").strip()
    if legacy and (not first or not last) and source.get("full_name"):
        parts = source["full_name"].split()
        if len(parts) < 2:
            raise ValueError("Legacy full_name requires at least two words; supply separate name columns.")
        first, middle, last = parts[0], " ".join(parts[1:-1]), parts[-1]
    if not first or not last:
        raise ValueError("First name and surname are required.")
    if max(map(len, (first, middle, last))) > 100:
        raise ValueError("A name field exceeds 100 characters.")
    faculty, department = resolve_department(source.get("department", ""), source.get("faculty") or None)
    level = (source.get("level") or "").strip()
    if not level or len(level) > 50:
        raise ValueError("Provide a valid level.")
    email = (source.get("email") or "").strip()
    if not valid_email(email):
        raise ValueError("Email address is not valid.")
    photo_url = (source.get("photo_url") or "").strip()
    parsed_photo = urlsplit(photo_url) if photo_url else None
    if photo_url:
        host = (parsed_photo.hostname or "").lower()
        is_ip_literal = False
        try:
            ipaddress.ip_address(host)
            is_ip_literal = True
        except ValueError:
            pass
        if (len(photo_url) > 1000 or parsed_photo.scheme != "https" or not host or
                not parsed_photo.netloc or parsed_photo.username or parsed_photo.password or
                is_ip_literal or host == "localhost" or host.endswith((".localhost", ".local"))):
            raise ValueError("Photo URL must use a public HTTPS hostname without embedded credentials.")
    status = (source.get("status") or "Active").strip().capitalize()
    if status not in ("Active", "Inactive"):
        raise ValueError("Status must be Active or Inactive.")
    return {"matric_no": matric, "first_name": first, "middle_name": middle,
            "last_name": last, "faculty": faculty, "department": department,
            "level": level, "email": email or None, "photo_url": photo_url or None,
            "status": status}


def academic_ids(db, faculty, department):
    pair = db.execute("""SELECT f.id AS faculty_id, d.id AS department_id
            FROM faculties f JOIN departments d ON d.faculty_id=f.id
            WHERE f.name = ? AND d.name = ?""", (faculty, department)).fetchone()
    if not pair:
        raise RuntimeError("Academic catalogue has not been seeded. Use /setup first.")
    return pair["faculty_id"], pair["department_id"]


def insert_student(db, record, source="imported"):
    faculty_id, department_id = academic_ids(db, record["faculty"], record["department"])
    token = secrets.token_urlsafe(32)
    db.execute("""INSERT INTO students (
            matric_no,first_name,middle_name,last_name,faculty_id,department_id,
            level,email,photo_url,token,status,record_source,created_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (record["matric_no"], record["first_name"], record["middle_name"],
             record["last_name"], faculty_id, department_id, record["level"],
             record["email"], record["photo_url"], token, record["status"], source, now()))
    return db.execute("SELECT id FROM students WHERE token = ?", (token,)).fetchone()["id"]


@app.route("/setup", methods=["GET", "POST"])
def setup():
    """One-time browser bootstrap; unavailable after an administrator exists."""
    expected = os.environ.get("SETUP_TOKEN") or ""
    if len(expected) < 32:
        abort(404)
    try:
        if _database_is_initialized():
            abort(404)
    except SQLAlchemyError:
        app.logger.exception("Could not check database setup state")
        abort(503)
    if request.method == "POST":
        submitted = request.form.get("setup_token", "")
        if not secrets.compare_digest(submitted, expected):
            app.logger.warning("Incorrect setup token submitted")
            flash("Invalid setup token.", "danger")
            return render_template("setup.html"), 403
        try:
            faculties, departments = init_db()
        except Exception:
            app.logger.exception("Database initialization failed")
            flash("Setup could not finish. Check the Vercel runtime logs for the cause.", "danger")
            return render_template("setup.html"), 503
        flash(f"Database initialized: {faculties} faculties and {departments} departments. Sign in as administrator. Remove SETUP_TOKEN from Vercel once finished.", "success")
        return redirect(url_for("login"))
    return render_template("setup.html")


@app.route("/health")
def health():
    try:
        with get_engine().connect() as conn:
            conn.execute(text("SELECT 1"))
            schema_ready = bool(conn.execute(text("SELECT to_regclass('public.students') IS NOT NULL AND to_regclass('public.users') IS NOT NULL")).scalar())
        return {"status": "ok", "database": "connected", "schema": "ready" if schema_ready else "not_initialized"}, 200
    except Exception:
        app.logger.exception("Neon health check failed")
        return {"status": "unavailable", "database": "unavailable"}, 503


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/about")
def about():
    return render_template("about.html")


@app.route("/how-it-works")
def how_it_works():
    return render_template("how_it_works.html")


@app.route("/privacy")
def privacy():
    return render_template("privacy.html")


@app.route("/faq")
def faq():
    return render_template("faq.html")


@app.route("/contact")
def contact():
    return render_template("contact.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        if len(username) > 100 or len(password) > 128:
            flash("Invalid username or password.", "danger")
            return render_template("login.html"), 401
        try:
            ensure_security_migrations()
            buckets = _login_rate_limit_buckets(username)
            with get_db() as db:
                retry_after = _rate_limit_remaining(db, buckets)
                if retry_after:
                    flash("Too many unsuccessful sign-in attempts. Please wait before trying again.", "danger")
                    response = make_response(render_template("login.html"), 429)
                    response.headers["Retry-After"] = str(retry_after)
                    return response
                user = db.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
                valid = False
                if user:
                    try:
                        valid = check_password_hash(user["password_hash"], password)
                    except (ValueError, TypeError):
                        valid = False
                    if valid and user["role"] == "student":
                        linked_student = db.execute("SELECT status FROM students WHERE id=?", (user["student_id"],)).fetchone()
                        valid = bool(linked_student and linked_student["status"] == "Active")
                if valid:
                    _clear_rate_limit_failures(db, buckets)
                    session.clear()
                    session.permanent = True
                    session.update(user_id=user["id"], username=user["username"],
                                   role=user["role"], student_id=user["student_id"])
                    return redirect(url_for("dashboard") if user["role"] == "admin" else url_for("student_account"))
                _record_rate_limit_failure(db, buckets)
        except SQLAlchemyError:
            app.logger.exception("Login database operation failed")
            abort(503)
        flash("Invalid username or password.", "danger")
        return render_template("login.html"), 401
    return render_template("login.html")


@app.route("/register", methods=["GET", "POST"])
def student_register():
    if session.get("user_id"):
        return redirect(url_for("dashboard") if session.get("role") == "admin" else url_for("student_account"))
    if request.method == "POST":
        try:
            identity = student_identity(request.form)
        except ValueError as exc:
            flash(str(exc), "danger")
            return render_template("student_register.html", catalogue=FACULTY_DEPARTMENTS)
        password = request.form.get("password", "")
        confirm = request.form.get("confirm_password", "")
        if len(password) < 10 or password != confirm:
            flash("Password must be at least 10 characters and match confirmation.", "danger")
            return render_template("student_register.html", catalogue=FACULTY_DEPARTMENTS)
        with get_db() as db:
            student = db.execute("SELECT * FROM student_profiles WHERE matric_no = ?", (identity["matric_no"],)).fetchone()
            matches = (student and student["status"] == "Active"
                       and student["first_name"].casefold() == identity["first_name"].casefold()
                       and (student["middle_name"] or "").casefold() == identity["middle_name"].casefold()
                       and student["last_name"].casefold() == identity["last_name"].casefold()
                       and student["faculty"] == identity["faculty"] and student["department"] == identity["department"]
                       and student["level"].casefold() == identity["level"].casefold())
            if not matches:
                flash("These details do not match an existing student record. Contact the project administrator.", "danger")
                return render_template("student_register.html", catalogue=FACULTY_DEPARTMENTS)
            if db.execute("SELECT id FROM users WHERE username = ?", (identity["matric_no"],)).fetchone():
                flash("An account already exists. Please sign in.", "warning")
                return redirect(url_for("login"))
            if db.execute("SELECT id FROM student_account_requests WHERE student_id=? AND status='Pending'", (student["id"],)).fetchone():
                flash("Your account request is already awaiting review.", "warning")
                return redirect(url_for("login"))
            claim_hash = student["claim_code_hash"]
            code = request.form.get("claim_code", "").strip()
            if not claim_hash:
                flash("A private one-time claim code must be issued by the administrator before account registration.", "danger")
                return render_template("student_register.html", catalogue=FACULTY_DEPARTMENTS)
            if not code or len(code) > 128 or not check_password_hash(claim_hash, code):
                flash("The one-time claim code is invalid. Contact the administrator if you need a new code.", "danger")
                return render_template("student_register.html", catalogue=FACULTY_DEPARTMENTS)
            if len(password) > 128:
                flash("Password must not exceed 128 characters.", "danger")
                return render_template("student_register.html", catalogue=FACULTY_DEPARTMENTS)
            db.execute("""INSERT INTO student_account_requests
                (student_id,password_hash,claim_code_verified,status,requested_at)
                VALUES (?,?,TRUE,'Pending',?)""", (student["id"], generate_password_hash(password), now()))
            # Consume the one-time code when a request is submitted. A rejected
            # request requires the administrator to issue a fresh code.
            db.execute("UPDATE students SET claim_code_hash=NULL WHERE id=?", (student["id"],))
        flash("Account request submitted. An administrator must approve it before sign-in.", "success")
        return redirect(url_for("login"))
    return render_template("student_register.html", catalogue=FACULTY_DEPARTMENTS)


@app.route("/registration-requests")
@admin_required
def registration_requests():
    with get_db() as db:
        rows = db.execute("""SELECT r.id,r.status,r.requested_at,s.matric_no,s.full_name,
           s.faculty,s.department,s.level,r.claim_code_verified
           FROM student_account_requests r JOIN student_profiles s ON s.id=r.student_id
           WHERE r.status='Pending' ORDER BY r.id ASC""").fetchall()
    return render_template("registration_requests.html", requests=rows)


@app.route("/registration-requests/<int:request_id>/<decision>", methods=["POST"])
@admin_required
def review_registration_request(request_id, decision):
    if decision not in ("approve", "reject"):
        abort(404)
    with get_db() as db:
        req = db.execute("SELECT * FROM student_account_requests WHERE id = ? FOR UPDATE", (request_id,)).fetchone()
        if not req:
            abort(404)
        if req["status"] != "Pending":
            flash("This request has already been reviewed.", "warning")
            return redirect(url_for("registration_requests"))
        student = db.execute("SELECT * FROM student_profiles WHERE id=?", (req["student_id"],)).fetchone()
        if decision == "approve" and not req["claim_code_verified"]:
            flash("This legacy request has no verified one-time claim code and cannot be approved. Reject it and issue a new code.", "danger")
            return redirect(url_for("registration_requests"))
        if decision == "approve" and (not student or student["status"] != "Active"):
            flash("Only an active student record can be approved for an account.", "danger")
            return redirect(url_for("registration_requests"))
        status = "Rejected"
        if student and decision == "approve":
            existing = db.execute("SELECT id FROM users WHERE username=?", (student["matric_no"],)).fetchone()
            if not existing:
                db.execute("""INSERT INTO users(username,password_hash,role,student_id,created_at)
                              VALUES (?,?,'student',?,?)""", (student["matric_no"], req["password_hash"], student["id"], now()))
                if req["claim_code_verified"]:
                    db.execute("UPDATE students SET claimed_at=?,claim_code_hash=NULL WHERE id=?", (now(), student["id"]))
                status = "Approved"
        db.execute("UPDATE student_account_requests SET status=?, reviewed_at=?,reviewed_by=? WHERE id=?",
                   (status, now(), session["user_id"], request_id))
        audit_admin_action(db, "student_account_request." + status.lower(), "student", req["student_id"],
                           "Administrator reviewed a student account request.")
    flash("Account request approved." if status == "Approved" else "Account request rejected or duplicate.",
          "success" if status == "Approved" else "warning")
    return redirect(url_for("registration_requests"))


@app.route("/student/account")
@login_required
def student_account():
    if session.get("role") != "student":
        abort(403)
    with get_db() as db:
        student = db.execute("SELECT * FROM student_profiles WHERE id=?", (session.get("student_id"),)).fetchone()
    if not student:
        abort(404)
    return render_template("student_account.html", student=student)


@app.route("/student/qr.png")
@login_required
def own_student_qr():
    if session.get("role") != "student":
        abort(403)
    with get_db() as db:
        student = db.execute("SELECT token,status FROM students WHERE id=?", (session.get("student_id"),)).fetchone()
    if not student:
        abort(404)
    if student["status"] != "Active":
        abort(403)
    return send_file(qr_image_for_token(student["token"]), mimetype="image/png",
                     as_attachment=(request.args.get("download") == "1"), download_name="studentverifi-qr.png")


@app.route("/students/<int:student_id>/claim-code", methods=["POST"])
@admin_required
def issue_claim_code(student_id):
    code = secrets.token_urlsafe(24)
    with get_db() as db:
        student = db.execute("SELECT id,claimed_at,status FROM students WHERE id=?", (student_id,)).fetchone()
        if not student:
            abort(404)
        if student["status"] != "Active":
            flash("A claim code can only be issued for an active student record.", "warning")
            return redirect(url_for("student_detail", student_id=student_id))
        if student["claimed_at"]:
            flash("This record has already been claimed.", "warning")
            return redirect(url_for("student_detail", student_id=student_id))
        pending = db.execute("SELECT id FROM student_account_requests WHERE student_id=? AND status='Pending'",
                              (student_id,)).fetchone()
        if pending:
            flash("A student account request is already pending. Review it before issuing another code.", "warning")
            return redirect(url_for("student_detail", student_id=student_id))
        db.execute("UPDATE students SET claim_code_hash=? WHERE id=?",
                   (generate_password_hash(code), student_id))
        audit_admin_action(db, "student.claim_code_issued", "student", student_id,
                           "Administrator issued a private one-time claim code.")
        profile = db.execute("SELECT * FROM student_profiles WHERE id=?", (student_id,)).fetchone()
    # Do not put the plaintext code in Flask's signed client-side session cookie.
    # It is disclosed only in this authenticated, no-store response.
    return render_template("student_detail.html", student=profile, claim_code=code)


@app.route("/logout", methods=["POST"])
def logout():
    session.clear()
    flash("Signed out.", "success")
    return redirect(url_for("index"))


@app.route("/dashboard")
@admin_required
def dashboard():
    with get_db() as db:
        total = db.execute("SELECT COUNT(*) FROM students").fetchone()[0]
        active = db.execute("SELECT COUNT(*) FROM students WHERE status='Active'").fetchone()[0]
        inactive = total - active
        checks = db.execute("SELECT COUNT(*) FROM verification_logs").fetchone()[0]
        recent = db.execute("""SELECT l.*,s.full_name,s.matric_no,u.username
            FROM verification_logs l LEFT JOIN student_profiles s ON s.id=l.student_id
            LEFT JOIN users u ON u.id=l.verified_by ORDER BY l.id DESC LIMIT 8""").fetchall()
    return render_template("dashboard.html", total=total, active=active, inactive=inactive, checks=checks, recent=recent)


@app.route("/students")
@admin_required
def students():
    q = request.args.get("q", "").strip()
    try:
        page = max(1, int(request.args.get("page", "1")))
    except ValueError:
        page = 1
    per_page = 100
    with get_db() as db:
        if q:
            pattern = f"%{q}%"
            count = db.execute("""SELECT COUNT(*) FROM student_profiles
                WHERE full_name ILIKE ? OR matric_no ILIKE ? OR department ILIKE ? OR faculty ILIKE ?""",
                (pattern, pattern, pattern, pattern)).fetchone()[0]
            pages = max(1, (count + per_page - 1) // per_page)
            page = min(page, pages)
            rows = db.execute("""SELECT * FROM student_profiles
                WHERE full_name ILIKE ? OR matric_no ILIKE ? OR department ILIKE ? OR faculty ILIKE ?
                ORDER BY id DESC LIMIT ? OFFSET ?""",
                (pattern, pattern, pattern, pattern, per_page, (page-1)*per_page)).fetchall()
        else:
            count = db.execute("SELECT COUNT(*) FROM students").fetchone()[0]
            pages = max(1, (count + per_page - 1) // per_page)
            page = min(page, pages)
            rows = db.execute("SELECT * FROM student_profiles ORDER BY id DESC LIMIT ? OFFSET ?",
                (per_page, (page-1)*per_page)).fetchall()
    return render_template("students.html", students=rows, q=q, page=page,
                           pages=pages, count=count)


@app.route("/students/new", methods=["GET", "POST"])
@admin_required
def add_student():
    if request.method == "POST":
        try:
            record = student_identity(request.form)
            with get_db() as db:
                student_id = insert_student(db, record, source="manual")
                audit_admin_action(db, "student.created", "student", student_id,
                                   "Administrator created a student record.")
            flash("Student registered successfully.", "success")
            return redirect(url_for("student_detail", student_id=student_id))
        except ValueError as exc:
            flash(str(exc), "danger")
        except IntegrityError:
            flash("That matriculation number is already registered.", "danger")
    return render_template("student_form.html", student=None, catalogue=FACULTY_DEPARTMENTS)


@app.route("/students/import-template.csv")
@admin_required
def student_import_template():
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(("matric_no", "first_name", "middle_name", "last_name", "faculty", "department", "level", "email", "status"))
    writer.writerow(("TEST/CSC/0001", "Ada", "", "Example", "Science", "Computer Science", "400", "example@example.com", "Active"))
    return send_file(io.BytesIO(output.getvalue().encode("utf-8-sig")), mimetype="text/csv",
                     as_attachment=True, download_name="studentverifi-import-template.csv")


@app.route("/students/import", methods=["GET", "POST"])
@admin_required
def import_students():
    if request.method == "GET":
        return render_template("student_import.html")
    upload = request.files.get("file")
    if not upload or not upload.filename or not upload.filename.lower().endswith(".csv"):
        flash("Choose a CSV file to import.", "danger")
        return redirect(url_for("import_students"))
    raw = upload.stream.read(8 * 1024 * 1024 + 1)
    if len(raw) > 8 * 1024 * 1024:
        flash("CSV limit is 8 MB.", "danger")
        return redirect(url_for("import_students"))
    try:
        reader = csv.DictReader(io.StringIO(raw.decode("utf-8-sig")), strict=True)
        headers = {h.strip().lower() for h in (reader.fieldnames or []) if h}
        if not {"matric_no", "department", "level"}.issubset(headers) or not (
                {"first_name", "last_name"}.issubset(headers) or {"first_name", "surname"}.issubset(headers) or "full_name" in headers):
            flash("CSV needs matric_no, department, level, and either first_name/last_name or full_name. Faculty is strongly recommended.", "danger")
            return redirect(url_for("import_students"))
        records, seen, errors = [], set(), []
        for line, source in enumerate(reader, 2):
            row = {(key or "").strip().lower(): (val or "").strip()
                   for key, val in source.items() if key is not None}
            if not any(row.values()):
                continue
            try:
                record = student_identity(row, legacy=True)
                if record["matric_no"] in seen:
                    raise ValueError("Duplicate matriculation number in this CSV.")
                seen.add(record["matric_no"])
                records.append(record)
            except ValueError as exc:
                errors.append(f"Row {line}: {exc}")
        if errors:
            for error in errors[:8]:
                flash(error, "danger")
            if len(errors) > 8:
                flash(f"{len(errors) - 8} more rows have errors. No data were imported.", "danger")
            return redirect(url_for("import_students"))
        if not records:
            flash("The CSV had no usable rows.", "warning")
            return redirect(url_for("import_students"))
        try:
            with get_db() as db:
                # Lookup all matric numbers and all faculty/department IDs in
                # two queries instead of thousands of network round-trips.
                existing = db.execute("SELECT matric_no FROM students WHERE matric_no = ANY(:numbers)",
                                      {"numbers": [rec["matric_no"] for rec in records]}).fetchall()
                if existing:
                    flash("Import cancelled. Existing matric number(s): " +
                          ", ".join(row["matric_no"] for row in existing[:8]), "danger")
                    return redirect(url_for("import_students"))
                lookup = db.execute("""SELECT f.id AS faculty_id, f.name AS faculty,
                    d.id AS department_id, d.name AS department
                    FROM faculties f JOIN departments d ON d.faculty_id=f.id""").fetchall()
                ids = {(row["faculty"], row["department"]):
                       (row["faculty_id"], row["department_id"]) for row in lookup}
                inserted_at = now()
                payload = []
                for rec in records:
                    faculty_id, department_id = ids[(rec["faculty"], rec["department"])]
                    payload.append({
                        "matric": rec["matric_no"], "first": rec["first_name"],
                        "middle": rec["middle_name"], "last": rec["last_name"],
                        "faculty_id": faculty_id, "department_id": department_id,
                        "level": rec["level"], "email": rec["email"],
                        "photo": rec["photo_url"], "token": secrets.token_urlsafe(32),
                        "status": rec["status"], "source": "imported", "created": inserted_at,
                    })
                db.execute_many("""INSERT INTO students
                    (matric_no,first_name,middle_name,last_name,faculty_id,department_id,
                     level,email,photo_url,token,status,record_source,created_at)
                    VALUES (:matric,:first,:middle,:last,:faculty_id,:department_id,
                            :level,:email,:photo,:token,:status,:source,:created)""", payload)
                audit_admin_action(db, "student.bulk_imported", "student_batch", None,
                                   f"Administrator imported {len(records)} student records.")
        except (IntegrityError, KeyError):
            app.logger.exception("Bulk import constraint/catalogue mismatch")
            flash("Import cancelled due to a duplicate or catalogue mismatch. No records were committed.", "danger")
            return redirect(url_for("import_students"))
        flash(f"Imported {len(records)} student records.", "success")
        return redirect(url_for("students"))
    except (UnicodeDecodeError, csv.Error):
        flash("Could not read CSV. Export as valid UTF-8 CSV and try again.", "danger")
        return redirect(url_for("import_students"))


@app.route("/admin/maintenance/demo-records", methods=["GET", "POST"])
@admin_required
def demo_data_cleanup():
    """Safely preview and remove only the known DEMO/2026 synthetic dataset."""
    demo_pattern = r"^DEMO/2026/[0-9]{6}$"
    if request.method == "POST":
        confirmation = request.form.get("confirmation", "").strip()
        if confirmation != "DELETE DEMO RECORDS":
            flash("Confirmation text did not match. No records were deleted.", "danger")
            return redirect(url_for("demo_data_cleanup"))
        with get_db() as db:
            ids = [row["id"] for row in db.execute(
                "SELECT id FROM students WHERE matric_no ~ ?", (demo_pattern,)).fetchall()]
            if not ids:
                flash("No matching synthetic demo records were found.", "warning")
                return redirect(url_for("demo_data_cleanup"))
            db.execute("DELETE FROM users WHERE student_id = ANY(:ids)", {"ids": ids})
            db.execute("DELETE FROM students WHERE id = ANY(:ids)", {"ids": ids})
            audit_admin_action(db, "student.synthetic_data_deleted", "student_batch", None,
                               f"Administrator deleted {len(ids)} exact-pattern synthetic demo records.")
        flash(f"Deleted {len(ids)} synthetic demo student records and their linked student accounts. Verification history was retained without student links.", "success")
        return redirect(url_for("students"))
    with get_db() as db:
        count = db.execute("SELECT COUNT(*) FROM students WHERE matric_no ~ ?", (demo_pattern,)).fetchone()[0]
    return render_template("data_cleanup.html", demo_count=count)


@app.route("/students/<int:student_id>")
@admin_required
def student_detail(student_id):
    with get_db() as db:
        student = db.execute("SELECT * FROM student_profiles WHERE id=?", (student_id,)).fetchone()
    if not student:
        abort(404)
    return render_template("student_detail.html", student=student)


@app.route("/students/<int:student_id>/qr.png")
@admin_required
def student_qr(student_id):
    with get_db() as db:
        student = db.execute("SELECT token FROM students WHERE id=?", (student_id,)).fetchone()
    if not student:
        abort(404)
    return send_file(qr_image_for_token(student["token"]), mimetype="image/png",
                     as_attachment=(request.args.get("download") == "1"), download_name=f"student-{student_id}-qr.png")


@app.route("/students/<int:student_id>/rotate-qr", methods=["POST"])
@admin_required
def rotate_student_qr(student_id):
    replacement = secrets.token_urlsafe(32)
    with get_db() as db:
        db.execute("UPDATE students SET token=? WHERE id=?", (replacement, student_id))
        student = db.execute("SELECT id FROM students WHERE id=?", (student_id,)).fetchone()
        if student:
            audit_admin_action(db, "student.qr_rotated", "student", student_id,
                               "Administrator rotated the student's QR credential.")
        if not student:
            abort(404)
    flash("QR credential rotated. Any previously issued QR code is now invalid.", "success")
    return redirect(url_for("student_detail", student_id=student_id))


@app.route("/students/<int:student_id>/toggle-status", methods=["POST"])
@admin_required
def toggle_status(student_id):
    with get_db() as db:
        student = db.execute("SELECT status FROM students WHERE id=?", (student_id,)).fetchone()
        if not student:
            abort(404)
        status = "Inactive" if student["status"] == "Active" else "Active"
        db.execute("UPDATE students SET status=? WHERE id=?", (status, student_id))
        audit_admin_action(db, "student.status_changed", "student", student_id,
                           f"Administrator changed student status to {status}.")
    flash(f"Student status changed to {status}.", "success")
    return redirect(url_for("student_detail", student_id=student_id))


@app.route("/verify", methods=["GET", "POST"])
@admin_required
def verify():
    result, submitted = None, ""
    if request.method == "POST":
        raw_submitted = request.form.get("token", "").strip()
        submitted = raw_submitted[:128]
        fingerprint = hashlib.sha256(raw_submitted[:512].encode("utf-8", "replace")).hexdigest()
        with get_db() as db:
            student = (db.execute("SELECT * FROM student_profiles WHERE token=?", (submitted,)).fetchone()
                       if submitted and len(raw_submitted) <= 128 else None)
            outcome = "VALID" if student and student["status"] == "Active" else ("INACTIVE" if student else "INVALID")
            # QR tokens are bearer credentials: retain only a one-way fingerprint.
            db.execute("""INSERT INTO verification_logs
                (student_id,scanned_token,token_fingerprint,result,verified_by,verified_at)
                VALUES (?,'[REDACTED]',?,?,?,?)""", (student["id"] if student else None, fingerprint,
                    outcome, session["user_id"], now()))
        result = {"outcome": outcome, "student": student}
    return render_template("verify.html", result=result, submitted=submitted)


@app.route("/admin/audit")
@admin_required
def admin_audit():
    with get_db() as db:
        rows = db.execute("""SELECT a.*, u.username FROM admin_audit_logs a
            LEFT JOIN users u ON u.id=a.actor_user_id
            ORDER BY a.id DESC LIMIT 250""").fetchall()
    return render_template("admin_audit.html", audit_rows=rows)


@app.route("/logs")
@admin_required
def logs():
    with get_db() as db:
        rows = db.execute("""SELECT l.*,s.full_name,s.matric_no,u.username FROM verification_logs l
                LEFT JOIN student_profiles s ON s.id=l.student_id
                LEFT JOIN users u ON u.id=l.verified_by ORDER BY l.id DESC LIMIT 250""").fetchall()
    return render_template("logs.html", logs=rows)


@app.route("/account/password", methods=["GET", "POST"])
@login_required
def change_password():
    if request.method == "POST":
        current = request.form.get("current_password", "")
        new = request.form.get("new_password", "")
        if len(current) > 128 or len(new) < 10 or len(new) > 128:
            flash("Current and new passwords must not exceed 128 characters; new passwords need at least 10 characters.", "danger")
        else:
            with get_db() as db:
                user = db.execute("SELECT * FROM users WHERE id=?", (session["user_id"],)).fetchone()
                if user and check_password_hash(user["password_hash"], current):
                    db.execute("UPDATE users SET password_hash=? WHERE id=?", (generate_password_hash(new), session["user_id"]))
                    audit_admin_action(db, "account.password_changed", "user", session["user_id"],
                                       "Authenticated user changed their password.")
                    session.clear()
                    flash("Password updated. Please sign in again with your new password.", "success")
                    return redirect(url_for("login"))
                flash("Current password was incorrect.", "danger")
    return render_template("change_password.html")


@app.errorhandler(403)
def forbidden(_error):
    return render_template("403.html"), 403


@app.errorhandler(404)
def not_found(_error):
    return render_template("404.html"), 404


@app.errorhandler(500)
def internal_error(_error):
    app.logger.exception("Unhandled application error")
    return render_template("500.html"), 500


@app.errorhandler(503)
def service_unavailable(_error):
    return render_template("503.html"), 503


if __name__ == "__main__":
    app.run(debug=(not IS_PRODUCTION and os.environ.get("FLASK_DEBUG", "false").lower() == "true"))
