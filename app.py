"""StudentVerifi API and database services. Database access is lazy.

The PostgreSQL schema and security controls are inherited from the hardened
release; the React client is the only web interface.
"""
import hashlib
import hmac
import io
import os
import re
import secrets
from datetime import datetime, timezone, timedelta

import qrcode
from dotenv import load_dotenv
from flask import Flask, g, request, session
from flask_wtf.csrf import CSRFProtect
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from werkzeug.security import generate_password_hash

from academic_catalogue import (FACULTY_DEPARTMENTS, academic_catalogue_counts,
                                resolve_department)

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
        "img-src 'self' data: blob: https:",
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
    """Expose database rows consistently as mappings."""
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
        token VARCHAR(128) UNIQUE,
        status VARCHAR(20) NOT NULL DEFAULT 'Active' CHECK(status IN ('Active','Inactive')),
        record_source VARCHAR(30) NOT NULL DEFAULT 'imported',
        claim_code_hash VARCHAR(255),
        claimed_at TIMESTAMPTZ,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        photo_blob_path VARCHAR(512),
        email_verified_at TIMESTAMPTZ,
        CONSTRAINT fk_students_dept_faculty FOREIGN KEY (department_id, faculty_id)
            REFERENCES departments(id, faculty_id)
    )""",
    "CREATE UNIQUE INDEX IF NOT EXISTS uq_students_email_lower ON students (LOWER(email)) WHERE email IS NOT NULL",
    """CREATE TABLE IF NOT EXISTS users (
        id INTEGER GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
        username VARCHAR(100) UNIQUE NOT NULL,
        password_hash VARCHAR(255) NOT NULL,
        role VARCHAR(30) NOT NULL DEFAULT 'admin' CHECK(role IN ('admin','student','verifier')),
        student_id INTEGER UNIQUE REFERENCES students(id) ON DELETE SET NULL,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        email VARCHAR(254),
        display_name VARCHAR(160),
        is_active BOOLEAN NOT NULL DEFAULT TRUE,
        last_login_at TIMESTAMPTZ
    )""",
    "CREATE UNIQUE INDEX IF NOT EXISTS uq_users_email_lower ON users (LOWER(email)) WHERE email IS NOT NULL",
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
    """CREATE TABLE IF NOT EXISTS student_claim_challenges (
        id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
        student_id INTEGER NOT NULL REFERENCES students(id) ON DELETE CASCADE,
        email_snapshot VARCHAR(254) NOT NULL,
        otp_hash VARCHAR(64) NOT NULL,
        expires_at TIMESTAMPTZ NOT NULL,
        attempts INTEGER NOT NULL DEFAULT 0,
        last_sent_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        verified_at TIMESTAMPTZ,
        consumed_at TIMESTAMPTZ,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )""",
    "CREATE INDEX IF NOT EXISTS ix_student_claim_challenges_student ON student_claim_challenges(student_id, created_at DESC)",
    """CREATE TABLE IF NOT EXISTS verifier_invitations (
        id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
        user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        token_hash VARCHAR(64) UNIQUE NOT NULL,
        expires_at TIMESTAMPTZ NOT NULL,
        used_at TIMESTAMPTZ,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )""",
    """CREATE TABLE IF NOT EXISTS verification_logs (
        id INTEGER GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
        student_id INTEGER REFERENCES students(id) ON DELETE SET NULL,
        scanned_token VARCHAR(200) NOT NULL DEFAULT '[REDACTED]',
        token_fingerprint VARCHAR(64),
        result VARCHAR(20) NOT NULL CHECK (result IN ('VALID','INACTIVE','INVALID','INCOMPLETE')),
        verified_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
        verified_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        channel VARCHAR(20) NOT NULL DEFAULT 'admin' CHECK(channel IN ('admin','verifier','public'))
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
        SELECT s.id, s.matric_no, s.first_name, s.middle_name, s.last_name,
            s.faculty_id, s.department_id, s.level, s.email, s.photo_url,
            s.token, s.status, s.record_source, s.claim_code_hash, s.claimed_at,
            s.created_at, f.name AS faculty, d.name AS department,
            TRIM(CONCAT_WS(' ', s.first_name, NULLIF(s.middle_name,''), s.last_name)) AS full_name,
            s.photo_blob_path, s.email_verified_at,
            EXISTS (SELECT 1 FROM users u WHERE u.student_id=s.id AND u.role='student') AS account_claimed
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
    """Apply idempotent, additive security and account-claim migrations."""
    global _SECURITY_MIGRATIONS_READY
    if _SECURITY_MIGRATIONS_READY:
        return
    with get_engine().begin() as conn:
        conn.execute(text("SELECT pg_advisory_xact_lock(73294021)"))
        conn.execute(text("""CREATE TABLE IF NOT EXISTS auth_rate_limits (
            bucket_hash VARCHAR(64) PRIMARY KEY,
            attempts INTEGER NOT NULL DEFAULT 0,
            window_started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            blocked_until TIMESTAMPTZ
        )"""))
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_auth_rate_limits_blocked ON auth_rate_limits(blocked_until)"))
        users_exist = bool(conn.execute(text("SELECT to_regclass('public.users') IS NOT NULL")).scalar())
        students_exist = bool(conn.execute(text("SELECT to_regclass('public.students') IS NOT NULL")).scalar())
        requests_exist = bool(conn.execute(text("SELECT to_regclass('public.student_account_requests') IS NOT NULL")).scalar())
        logs_exist = bool(conn.execute(text("SELECT to_regclass('public.verification_logs') IS NOT NULL")).scalar())

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
            conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS email VARCHAR(254)"))
            conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS display_name VARCHAR(160)"))
            conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS is_active BOOLEAN NOT NULL DEFAULT TRUE"))
            conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS last_login_at TIMESTAMPTZ"))
            conn.execute(text("ALTER TABLE users DROP CONSTRAINT IF EXISTS users_role_check"))
            conn.execute(text("ALTER TABLE users ADD CONSTRAINT users_role_check CHECK(role IN ('admin','student','verifier'))"))
            conn.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS uq_users_email_lower ON users (LOWER(email)) WHERE email IS NOT NULL"))
            conn.execute(text("""CREATE TABLE IF NOT EXISTS verifier_invitations (
                id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                token_hash VARCHAR(64) UNIQUE NOT NULL,
                expires_at TIMESTAMPTZ NOT NULL,
                used_at TIMESTAMPTZ,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )"""))

        if students_exist:
            conn.execute(text("ALTER TABLE students ALTER COLUMN token DROP NOT NULL"))
            conn.execute(text("ALTER TABLE students ADD COLUMN IF NOT EXISTS photo_blob_path VARCHAR(512)"))
            conn.execute(text("ALTER TABLE students ADD COLUMN IF NOT EXISTS email_verified_at TIMESTAMPTZ"))
            duplicate_student_emails = conn.execute(text("""SELECT EXISTS (
                SELECT 1 FROM students WHERE email IS NOT NULL
                GROUP BY LOWER(email) HAVING COUNT(*) > 1
            )""")).scalar()
            if not duplicate_student_emails:
                conn.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS uq_students_email_lower ON students (LOWER(email)) WHERE email IS NOT NULL"))
            conn.execute(text("""CREATE TABLE IF NOT EXISTS student_claim_challenges (
                id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
                student_id INTEGER NOT NULL REFERENCES students(id) ON DELETE CASCADE,
                email_snapshot VARCHAR(254) NOT NULL,
                otp_hash VARCHAR(64) NOT NULL,
                expires_at TIMESTAMPTZ NOT NULL,
                attempts INTEGER NOT NULL DEFAULT 0,
                sent_count INTEGER NOT NULL DEFAULT 1,
                window_started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                last_sent_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                verified_at TIMESTAMPTZ,
                consumed_at TIMESTAMPTZ,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )"""))
            conn.execute(text("ALTER TABLE student_claim_challenges ADD COLUMN IF NOT EXISTS sent_count INTEGER NOT NULL DEFAULT 1"))
            conn.execute(text("ALTER TABLE student_claim_challenges ADD COLUMN IF NOT EXISTS window_started_at TIMESTAMPTZ NOT NULL DEFAULT NOW()"))
            conn.execute(text("CREATE INDEX IF NOT EXISTS ix_student_claim_challenges_student ON student_claim_challenges(student_id, created_at DESC)"))
            if users_exist:
                # Retire legacy claim codes and QR tokens that were issued before account claiming.
                conn.execute(text("UPDATE students SET claim_code_hash=NULL"))
                conn.execute(text("""UPDATE students s SET token=NULL
                    WHERE NOT EXISTS (SELECT 1 FROM users u WHERE u.student_id=s.id AND u.role='student')"""))
                if requests_exist:
                    conn.execute(text("""UPDATE student_account_requests SET password_hash='[REDACTED]'
                        WHERE status IN ('Approved','Rejected')"""))
                conn.execute(text("DROP VIEW IF EXISTS student_profiles"))
                conn.execute(text("""CREATE VIEW student_profiles AS
                    SELECT s.id, s.matric_no, s.first_name, s.middle_name, s.last_name,
                        s.faculty_id, s.department_id, s.level, s.email, s.photo_url,
                        s.token, s.status, s.record_source, s.claim_code_hash, s.claimed_at,
                        s.created_at, f.name AS faculty, d.name AS department,
                        TRIM(CONCAT_WS(' ', s.first_name, NULLIF(s.middle_name,''), s.last_name)) AS full_name,
                        s.photo_blob_path, s.email_verified_at,
                        EXISTS (SELECT 1 FROM users u WHERE u.student_id=s.id AND u.role='student') AS account_claimed
                    FROM students s
                    JOIN faculties f ON f.id=s.faculty_id
                    JOIN departments d ON d.id=s.department_id"""))

        if logs_exist:
            conn.execute(text("ALTER TABLE verification_logs ADD COLUMN IF NOT EXISTS token_fingerprint VARCHAR(64)"))
            conn.execute(text("ALTER TABLE verification_logs ADD COLUMN IF NOT EXISTS channel VARCHAR(20) NOT NULL DEFAULT 'admin'"))
            conn.execute(text("ALTER TABLE verification_logs DROP CONSTRAINT IF EXISTS verification_logs_channel_check"))
            conn.execute(text("ALTER TABLE verification_logs ADD CONSTRAINT verification_logs_channel_check CHECK(channel IN ('admin','verifier','public'))"))
            conn.execute(text("ALTER TABLE verification_logs DROP CONSTRAINT IF EXISTS verification_logs_result_check"))
            conn.execute(text("ALTER TABLE verification_logs ADD CONSTRAINT verification_logs_result_check CHECK(result IN ('VALID','INACTIVE','INVALID','INCOMPLETE'))"))
            old_rows = conn.execute(text("""SELECT id, scanned_token FROM verification_logs
                WHERE token_fingerprint IS NULL AND scanned_token <> '[REDACTED]'""")).fetchall()
            for row in old_rows:
                fingerprint = hashlib.sha256(str(row._mapping["scanned_token"]).encode("utf-8")).hexdigest()
                conn.execute(text("""UPDATE verification_logs
                    SET token_fingerprint=:fingerprint, scanned_token='[REDACTED]' WHERE id=:id"""),
                    {"fingerprint": fingerprint, "id": row._mapping["id"]})
            conn.execute(text("""UPDATE verification_logs SET scanned_token='[REDACTED]'
                WHERE scanned_token <> '[REDACTED]' AND token_fingerprint IS NOT NULL"""))
        conn.execute(text("DELETE FROM auth_rate_limits WHERE COALESCE(blocked_until, window_started_at) < NOW() - INTERVAL '1 day'"))
        if students_exist:
            conn.execute(text("DELETE FROM student_claim_challenges WHERE created_at < NOW() - INTERVAL '7 days'"))
        if users_exist:
            conn.execute(text("DELETE FROM verifier_invitations WHERE expires_at < NOW() - INTERVAL '30 days' OR used_at < NOW() - INTERVAL '30 days'"))
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


@app.cli.command("init-db")
def init_db_command():
    faculties, departments = init_db()
    print(f"Schema initialized; {faculties} faculties, {departments} departments seeded.")


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
    email = (source.get("email") or "").strip().lower()
    if not valid_email(email):
        raise ValueError("Email address is not valid.")
    # New profile photographs are uploaded by students and stored privately.
    # Legacy photo_url values remain in the database but are not accepted for new records.
    photo_url = None
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
        raise RuntimeError("Academic catalogue has not been seeded. Initialise the database before adding records.")
    return pair["faculty_id"], pair["department_id"]


def insert_student(db, record, source="imported"):
    faculty_id, department_id = academic_ids(db, record["faculty"], record["department"])
    db.execute("""INSERT INTO students (
            matric_no,first_name,middle_name,last_name,faculty_id,department_id,
            level,email,photo_url,token,status,record_source,created_at)
            VALUES (?,?,?,?,?,?,?,?,?,NULL,?,?,?)""",
            (record["matric_no"], record["first_name"], record["middle_name"],
             record["last_name"], faculty_id, department_id, record["level"],
             record["email"], record["photo_url"], record["status"], source, now()))
    return db.execute("SELECT id FROM students WHERE matric_no = ?", (record["matric_no"],)).fetchone()["id"]




@app.get("/health")
def health():
    """Minimal health response without exposing internal database details."""
    try:
        with get_engine().connect() as conn:
            ready = conn.execute(text(
                "SELECT to_regclass('public.users') IS NOT NULL AND "
                "to_regclass('public.students') IS NOT NULL"
            )).scalar()
        return ({"status": "ok"}, 200) if ready else ({"status": "unavailable"}, 503)
    except Exception:
        app.logger.exception("Health check failed")
        return {"status": "unavailable"}, 503


import sys
import spa_api
spa_api.install(app, sys.modules[__name__])

if __name__ == "__main__":
    app.run(debug=(not IS_PRODUCTION and os.environ.get("FLASK_DEBUG", "false").lower() == "true"))
