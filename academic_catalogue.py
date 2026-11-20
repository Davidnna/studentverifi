import csv
import io
import os
import re
import secrets
import unicodedata
from datetime import datetime, timezone
from functools import wraps

import qrcode
from dotenv import load_dotenv
from flask import (
    Flask, abort, flash, redirect, render_template, request, send_file,
    session, url_for,
)
from flask_wtf.csrf import CSRFProtect
from sqlalchemy import (
    Column, ForeignKey, Index, Integer, MetaData, String, Table, create_engine,
    text,
)
from sqlalchemy.engine import make_url
from sqlalchemy.exc import IntegrityError
from werkzeug.security import check_password_hash, generate_password_hash

from academic_catalogue import (
    DEPARTMENT_ALIASES,
    FACULTY_ALIASES,
    FACULTY_DEPARTMENTS,
)

load_dotenv()

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
app = Flask(__name__)

secret_key = os.environ.get("SECRET_KEY")
is_production = bool(os.environ.get("VERCEL") or os.environ.get("RAILWAY_ENVIRONMENT"))
if is_production and not secret_key:
    raise RuntimeError("SECRET_KEY must be configured in production environment variables.")

app.config.update(
    SECRET_KEY=secret_key or "local-development-only-change-this-secret",
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=os.environ.get(
        "COOKIE_SECURE", "true" if is_production else "false"
    ).lower() == "true",
    MAX_CONTENT_LENGTH=5 * 1024 * 1024,
)
csrf = CSRFProtect(app)


# ---------------------------------------------------------------------------
# Database configuration
# ---------------------------------------------------------------------------

_engine = None


def database_url():
    """Return a SQLAlchemy URL using Psycopg 3 for PostgreSQL/Neon."""
    raw = os.environ.get("DATABASE_URL") or os.environ.get("NEON_DATABASE_URL")
    if not raw:
        raise RuntimeError(
            "Set DATABASE_URL to your Neon PostgreSQL connection string before "
            "running database commands or database-backed routes."
        )

    parsed = make_url(raw)
    if parsed.drivername in ("postgres", "postgresql"):
        parsed = parsed.set(drivername="postgresql+psycopg")
    elif parsed.drivername == "postgresql+psycopg2":
        parsed = parsed.set(drivername="postgresql+psycopg")

    if parsed.drivername.startswith("postgresql") and parsed.host:
        query = dict(parsed.query)
        if parsed.host.endswith(".neon.tech") and "sslmode" not in query:
            query["sslmode"] = "require"
        parsed = parsed.set(query=query)

    return parsed


def get_engine():
    """Create the engine lazily so Vercel can import app.py without connecting."""
    global _engine
    if _engine is None:
        _engine = create_engine(
            database_url(),
            pool_pre_ping=True,
            pool_recycle=300,
            pool_size=3,
            max_overflow=2,
        )
    return _engine


metadata = MetaData()

faculties_table = Table(
    "faculties",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("name", String(180), nullable=False, unique=True),
)

departments_table = Table(
    "departments",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("faculty_id", Integer, ForeignKey("faculties.id", ondelete="CASCADE"), nullable=False),
    Column("name", String(180), nullable=False),
)

students_table = Table(
    "students",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("matric_no", String(100), nullable=False, unique=True),
    Column("first_name", String(100), nullable=False),
    Column("middle_name", String(100), nullable=True),
    Column("last_name", String(100), nullable=False),
    Column("faculty_id", Integer, ForeignKey("faculties.id"), nullable=False),
    Column("department_id", Integer, ForeignKey("departments.id"), nullable=False),
    Column("level", String(50), nullable=False),
    Column("email", String(254), nullable=True),
    Column("photo_url", String(1000), nullable=True),
    Column("token", String(128), nullable=False, unique=True),
    Column("status", String(20), nullable=False, default="Active"),
    Column("record_source", String(30), nullable=False, default="manual"),
    Column("created_at", String(40), nullable=False),
)

users_table = Table(
    "users",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("username", String(80), nullable=False, unique=True),
    Column("password_hash", String(255), nullable=False),
    Column("role", String(30), nullable=False, default="admin"),
    Column("student_id", Integer, ForeignKey("students.id", ondelete="SET NULL"), nullable=True),
    Column("created_at", String(40), nullable=False),
)

verification_logs_table = Table(
    "verification_logs",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("student_id", Integer, ForeignKey("students.id", ondelete="SET NULL"), nullable=True),
    Column("scanned_token", String(200), nullable=False),
    Column("result", String(20), nullable=False),
    Column("verified_by", Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
    Column("verified_at", String(40), nullable=False),
)

student_account_requests_table = Table(
    "student_account_requests",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("student_id", Integer, ForeignKey("students.id", ondelete="CASCADE"), nullable=False),
    Column("password_hash", String(255), nullable=False),
    Column("status", String(20), nullable=False, default="Pending"),
    Column("requested_at", String(40), nullable=False),
    Column("reviewed_at", String(40), nullable=True),
    Column("reviewed_by", Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
)

Index("ix_departments_faculty_id", departments_table.c.faculty_id)
Index("ix_departments_faculty_name", departments_table.c.faculty_id, departments_table.c.name, unique=True)
Index("ix_students_faculty_id", students_table.c.faculty_id)
Index("ix_students_department_id", students_table.c.department_id)
Index("ix_verification_logs_verified_at", verification_logs_table.c.verified_at)
Index("ix_account_requests_status", student_account_requests_table.c.status)


class CompatRow:
    """Small adapter preserving the mapping/index access used by the templates."""
    def __init__(self, row):
        self.row = row
        self.mapping = row._mapping

    def __getitem__(self, key):
        return self.mapping[key] if isinstance(key, str) else self.row[key]

    def __getattr__(self, name):
        try:
            return self.mapping[name]
        except KeyError:
            raise AttributeError(name) from None


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
    """Allows the existing route code to use qmark-style SQL parameters."""
    def __init__(self, connection):
        self.connection = connection

    @staticmethod
    def _prepare(sql, params):
        sql = sql.strip()
        params = tuple(params or ())
        if not params:
            return text(sql), {}
        parts = sql.split("?")
        if len(parts) - 1 != len(params):
            raise ValueError("SQL placeholder count does not match parameters.")
        rendered = parts[0]
        values = {}
        for index, value in enumerate(params):
            key = f"p{index}"
            rendered += f":{key}" + parts[index + 1]
            values[key] = value
        return text(rendered), values

    def execute(self, sql, params=()):
        statement, values = self._prepare(sql, params)
        return CompatResult(self.connection.execute(statement, values))

    def executemany(self, sql, rows):
        rows = list(rows)
        if not rows:
            return None
        parts = sql.strip().split("?")
        placeholder_count = len(parts) - 1
        if any(len(row) != placeholder_count for row in rows):
            raise ValueError("SQL placeholder count does not match a batch row.")
        rendered = parts[0]
        keys = []
        for index in range(placeholder_count):
            key = f"p{index}"
            keys.append(key)
            rendered += f":{key}" + parts[index + 1]
        values = [
            {key: value for key, value in zip(keys, row)}
            for row in rows
        ]
        return self.connection.execute(text(rendered), values)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


class DBContext:
    def __enter__(self):
        self.transaction = get_engine().begin()
        self.connection = self.transaction.__enter__()
        return DBCompat(self.connection)

    def __exit__(self, exc_type, exc, tb):
        return self.transaction.__exit__(exc_type, exc, tb)


def get_db():
    return DBContext()


def now():
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def init_db():
    """Create the schema, seed the EBSU catalogue and create the first admin."""
    engine = get_engine()
    metadata.create_all(engine)

    with engine.begin() as connection:
        for faculty_name, department_names in FACULTY_DEPARTMENTS.items():
            connection.execute(
                text("INSERT INTO faculties (name) VALUES (:name) ON CONFLICT (name) DO NOTHING"),
                {"name": faculty_name},
            )
            faculty_id = connection.execute(
                text("SELECT id FROM faculties WHERE name = :name"),
                {"name": faculty_name},
            ).scalar_one()

            for department_name in department_names:
                connection.execute(
                    text(
                        "INSERT INTO departments (faculty_id, name) "
                        "VALUES (:faculty_id, :name) ON CONFLICT DO NOTHING"
                    ),
                    {"faculty_id": faculty_id, "name": department_name},
                )

        admin_username = os.environ.get("INITIAL_ADMIN_USERNAME", "admin").strip()
        existing = connection.execute(
            text("SELECT id FROM users WHERE username = :username"),
            {"username": admin_username},
        ).first()

        if not existing:
            initial_password = os.environ.get("INITIAL_ADMIN_PASSWORD")
            if not initial_password:
                if is_production:
                    raise RuntimeError(
                        "Set INITIAL_ADMIN_PASSWORD before initialising the production database."
                    )
                initial_password = "ChangeMe123!"
            connection.execute(
                text(
                    "INSERT INTO users (username, password_hash, role, created_at) "
                    "VALUES (:username, :password_hash, 'admin', :created_at)"
                ),
                {
                    "username": admin_username,
                    "password_hash": generate_password_hash(initial_password),
                    "created_at": now(),
                },
            )


@app.cli.command("init-db")
def init_db_command():
    """Initialise the PostgreSQL schema and seed the EBSU academic catalogue."""
    init_db()
    print("StudentVerifi database initialised; EBSU faculties and departments seeded.")


# ---------------------------------------------------------------------------
# Academic catalogue and validation helpers
# ---------------------------------------------------------------------------

def normalise_label(value):
    value = unicodedata.normalize("NFKD", str(value or "")).encode("ascii", "ignore").decode()
    value = value.casefold().replace("&", " and ").replace("/", " ")
    value = re.sub(r"\bfaculty of\b", " ", value)
    value = re.sub(r"\bdepartment of\b", " ", value)
    value = re.sub(r"[^a-z0-9]+", " ", value)
    return " ".join(value.split())


def canonical_faculty_name(value):
    raw = str(value or "").strip()
    if not raw:
        return ""
    target = normalise_label(raw)
    for alias, canonical in FACULTY_ALIASES.items():
        if target == normalise_label(alias):
            return canonical
    for canonical in FACULTY_DEPARTMENTS:
        if target == normalise_label(canonical):
            return canonical
    return raw


def canonical_department_name(value):
    raw = str(value or "").strip()
    if not raw:
        return ""
    target = normalise_label(raw)
    for alias, canonical in DEPARTMENT_ALIASES.items():
        if target == normalise_label(alias):
            return canonical
    for departments in FACULTY_DEPARTMENTS.values():
        for canonical in departments:
            if target == normalise_label(canonical):
                return canonical
    return raw


def normalise_matric_no(value):
    return re.sub(r"\s+", "", str(value or "")).upper()


def normalise_level(value):
    value = " ".join(str(value or "").strip().upper().split())
    value = re.sub(r"\s*LEVEL$", "", value)
    value = re.sub(r"^(\d{3})L$", r"\1", value)
    if value in {"POSTGRADUATE", "POST GRADUATE", "POST-GRADUATE", "PG"}:
        return "Postgraduate"
    return value


def valid_matric_no(value):
    """Validate safe EBSU-style identifier syntax without assuming one cohort format.

    Public EBSU records show more than one matriculation-number convention. This
    checks structure and characters; matching a record in the database remains
    the actual identity-record check.
    """
    value = normalise_matric_no(value)
    return (
        5 <= len(value) <= 40
        and bool(re.fullmatch(r"[A-Z0-9]+(?:[/-][A-Z0-9]+)*", value))
        and any(character.isdigit() for character in value)
    )


def split_full_name(full_name):
    parts = " ".join(str(full_name or "").split()).split(" ")
    if len(parts) < 2:
        return None
    return parts[0], " ".join(parts[1:-1]) or None, parts[-1]


def name_key(value):
    return " ".join(str(value or "").casefold().split())


def load_catalogue():
    with get_db() as db:
        faculties = db.execute(
            "SELECT id, name FROM faculties ORDER BY name"
        ).fetchall()
        departments = db.execute(
            """SELECT d.id, d.name, d.faculty_id, f.name AS faculty_name
               FROM departments d
               JOIN faculties f ON f.id = d.faculty_id
               ORDER BY f.name, d.name"""
        ).fetchall()
    return faculties, departments


def render_with_catalogue(template_name, **context):
    faculties, departments = load_catalogue()
    return render_template(
        template_name,
        faculties=faculties,
        departments=departments,
        **context,
    )


def resolve_catalogue_entry(faculty_value, department_value, department_rows):
    """Resolve a CSV faculty/department pair to seeded catalogue IDs."""
    department_name = canonical_department_name(department_value)
    department_key = normalise_label(department_name)
    department = next(
        (row for row in department_rows if normalise_label(row["name"]) == department_key),
        None,
    )
    if department is None:
        return None, f"Department '{department_value}' is not in the EBSU catalogue."

    faculty_name = canonical_faculty_name(faculty_value)
    if faculty_name == "__MEDICINE_FACULTY__":
        if department["faculty_name"] not in {
            "Faculty of Basic Medical Sciences",
            "Faculty of Clinical Medicine",
        }:
            return None, f"Department '{department_value}' does not belong to the supplied faculty."
    elif faculty_value and normalise_label(faculty_name) != normalise_label(department["faculty_name"]):
        return None, (
            f"Department '{department_value}' does not belong to faculty "
            f"'{faculty_value}'. Expected '{department['faculty_name']}'."
        )

    return {
        "faculty_id": department["faculty_id"],
        "department_id": department["id"],
        "faculty_name": department["faculty_name"],
        "department_name": department["name"],
    }, None


def validate_student_form(form):
    matric_no = normalise_matric_no(form.get("matric_no", ""))
    first_name = " ".join(form.get("first_name", "").split())
    middle_name = " ".join(form.get("middle_name", "").split()) or None
    last_name = " ".join(form.get("last_name", "").split())
    faculty_id = form.get("faculty_id", "").strip()
    department_id = form.get("department_id", "").strip()
    level = normalise_level(form.get("level", ""))
    email = form.get("email", "").strip()
    photo_url = form.get("photo_url", "").strip()

    if not all([matric_no, first_name, last_name, faculty_id, department_id, level]):
        return None, "Complete all required fields."
    if not valid_matric_no(matric_no):
        return None, "Enter a valid matriculation number using letters, numbers, '/' or '-'."
    if len(first_name) > 100 or len(last_name) > 100 or len(middle_name or "") > 100:
        return None, "A student name is too long."
    if len(level) > 50 or len(email) > 254 or len(photo_url) > 1000:
        return None, "One or more fields exceed the permitted length."
    if email and not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", email):
        return None, "Enter a valid email address."

    try:
        faculty_id_int = int(faculty_id)
        department_id_int = int(department_id)
    except ValueError:
        return None, "Select a valid faculty and department."

    with get_db() as db:
        department = db.execute(
            "SELECT id FROM departments WHERE id = ? AND faculty_id = ?",
            (department_id_int, faculty_id_int),
        ).fetchone()
    if not department:
        return None, "The selected department does not belong to the selected faculty."

    return {
        "matric_no": matric_no,
        "first_name": first_name,
        "middle_name": middle_name,
        "last_name": last_name,
        "faculty_id": faculty_id_int,
        "department_id": department_id_int,
        "level": level,
        "email": email or None,
        "photo_url": photo_url or None,
    }, None


# ---------------------------------------------------------------------------
# Authentication, QR and page helpers
# ---------------------------------------------------------------------------

def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not session.get("user_id"):
            flash("Please log in to continue.", "warning")
            return redirect(url_for("login"))
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
        return view(*args, **kwargs)
    return wrapped


def student_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not session.get("user_id"):
            flash("Please sign in to continue.", "warning")
            return redirect(url_for("login"))
        if session.get("role") != "student":
            abort(403)
        return view(*args, **kwargs)
    return wrapped


def qr_image_for_token(token):
    image = qrcode.make(token)
    output = io.BytesIO()
    image.save(output, format="PNG")
    output.seek(0)
    return output


STUDENT_SELECT = """
    SELECT s.*,
           f.name AS faculty,
           d.name AS department,
           CASE WHEN s.middle_name IS NULL OR s.middle_name = ''
                THEN s.first_name || ' ' || s.last_name
                ELSE s.first_name || ' ' || s.middle_name || ' ' || s.last_name
           END AS full_name
    FROM students s
    JOIN faculties f ON f.id = s.faculty_id
    JOIN departments d ON d.id = s.department_id
"""


# ---------------------------------------------------------------------------
# Public information pages
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Login and student account request workflow
# ---------------------------------------------------------------------------

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        with get_db() as db:
            user = db.execute(
                "SELECT * FROM users WHERE username = ?", (username,)
            ).fetchone()

        if user and check_password_hash(user["password_hash"], password):
            session.clear()
            session["user_id"] = user["id"]
            session["username"] = user["username"]
            session["role"] = user["role"]
            session["student_id"] = user["student_id"]
            return redirect(
                url_for("dashboard")
                if user["role"] == "admin"
                else url_for("student_account")
            )

        flash("Invalid username or password.", "danger")
    return render_template("login.html")


@app.route("/register", methods=["GET", "POST"])
def student_register():
    if session.get("user_id"):
        return redirect(
            url_for("dashboard")
            if session.get("role") == "admin"
            else url_for("student_account")
        )

    if request.method == "POST":
        student_data, error = validate_student_form(request.form)
        password = request.form.get("password", "")
        confirm = request.form.get("confirm_password", "")

        if error:
            flash(error, "danger")
            return render_with_catalogue("student_register.html")
        if len(password) < 10:
            flash("Choose a password with at least 10 characters.", "danger")
            return render_with_catalogue("student_register.html")
        if password != confirm:
            flash("The passwords do not match. Please try again.", "danger")
            return render_with_catalogue("student_register.html")

        with get_db() as db:
            student = db.execute(
                "SELECT * FROM students WHERE matric_no = ?",
                (student_data["matric_no"],),
            ).fetchone()

            if not student:
                flash("No student record matches that matriculation number.", "danger")
                return render_with_catalogue("student_register.html")
            if student["status"] != "Active":
                flash("This student record is inactive. Contact the institution's authorised office.", "danger")
                return render_with_catalogue("student_register.html")

            supplied_names = (
                name_key(student_data["first_name"]),
                name_key(student_data["middle_name"]),
                name_key(student_data["last_name"]),
            )
            stored_names = (
                name_key(student["first_name"]),
                name_key(student["middle_name"]),
                name_key(student["last_name"]),
            )
            details_match = (
                supplied_names == stored_names
                and student["faculty_id"] == student_data["faculty_id"]
                and student["department_id"] == student_data["department_id"]
                and normalise_level(student["level"]) == normalise_level(student_data["level"])
            )
            if not details_match:
                flash(
                    "The details do not match the student record. Check the information or contact the project administrator.",
                    "danger",
                )
                return render_with_catalogue("student_register.html")

            existing = db.execute(
                "SELECT id FROM users WHERE username = ?",
                (student_data["matric_no"],),
            ).fetchone()
            if existing:
                flash("An account already exists for this record. Please sign in.", "warning")
                return redirect(url_for("login"))

            pending = db.execute(
                "SELECT id FROM student_account_requests "
                "WHERE student_id = ? AND status = 'Pending'",
                (student["id"],),
            ).fetchone()
            if pending:
                flash("An account request for this record is already awaiting review.", "warning")
                return redirect(url_for("login"))

            db.execute(
                """INSERT INTO student_account_requests
                   (student_id, password_hash, status, requested_at)
                   VALUES (?, ?, 'Pending', ?)""",
                (
                    student["id"],
                    generate_password_hash(password),
                    now(),
                ),
            )

        flash(
            "Your request has been submitted for review. You can sign in after an administrator approves it.",
            "success",
        )
        return redirect(url_for("login"))

    return render_with_catalogue("student_register.html")


@app.route("/registration-requests")
@admin_required
def registration_requests():
    with get_db() as db:
        requests = db.execute(
            """SELECT r.id, r.status, r.requested_at,
                      s.matric_no, s.first_name, s.middle_name, s.last_name,
                      f.name AS faculty, d.name AS department, s.level,
                      CASE WHEN s.middle_name IS NULL OR s.middle_name = ''
                      THEN s.first_name || ' ' || s.last_name
                      ELSE s.first_name || ' ' || s.middle_name || ' ' || s.last_name
                 END AS full_name
               FROM student_account_requests r
               JOIN students s ON s.id = r.student_id
               JOIN faculties f ON f.id = s.faculty_id
               JOIN departments d ON d.id = s.department_id
               WHERE r.status = 'Pending'
               ORDER BY r.id ASC"""
        ).fetchall()
    return render_template("registration_requests.html", requests=requests)


@app.route("/registration-requests/<int:request_id>/<decision>", methods=["POST"])
@admin_required
def review_registration_request(request_id, decision):
    if decision not in ("approve", "reject"):
        abort(404)

    with get_db() as db:
        account_request = db.execute(
            "SELECT * FROM student_account_requests WHERE id = ?",
            (request_id,),
        ).fetchone()
        if not account_request:
            abort(404)
        if account_request["status"] != "Pending":
            flash("This request has already been reviewed.", "warning")
            return redirect(url_for("registration_requests"))

        student = db.execute(
            "SELECT * FROM students WHERE id = ?",
            (account_request["student_id"],),
        ).fetchone()
        if not student:
            db.execute(
                """UPDATE student_account_requests
                   SET status = 'Rejected', reviewed_at = ?, reviewed_by = ?
                   WHERE id = ?""",
                (now(), session["user_id"], request_id),
            )
            flash("The student record no longer exists; the request was rejected.", "warning")
            return redirect(url_for("registration_requests"))

        if decision == "approve":
            existing = db.execute(
                "SELECT id FROM users WHERE username = ?",
                (student["matric_no"],),
            ).fetchone()
            if existing:
                db.execute(
                    """UPDATE student_account_requests
                       SET status = 'Rejected', reviewed_at = ?, reviewed_by = ?
                       WHERE id = ?""",
                    (now(), session["user_id"], request_id),
                )
                flash("An account already exists for this student; the request was not approved.", "warning")
                return redirect(url_for("registration_requests"))

            db.execute(
                """INSERT INTO users
                   (username, password_hash, role, student_id, created_at)
                   VALUES (?, ?, 'student', ?, ?)""",
                (
                    student["matric_no"],
                    account_request["password_hash"],
                    student["id"],
                    now(),
                ),
            )
            status = "Approved"
        else:
            status = "Rejected"

        db.execute(
            """UPDATE student_account_requests
               SET status = ?, reviewed_at = ?, reviewed_by = ?
               WHERE id = ?""",
            (status, now(), session["user_id"], request_id),
        )

    flash(
        "Account request approved. The student can now sign in."
        if decision == "approve"
        else "Account request rejected.",
        "success" if decision == "approve" else "warning",
    )
    return redirect(url_for("registration_requests"))


@app.route("/student/account")
@student_required
def student_account():
    with get_db() as db:
        student = db.execute(
            STUDENT_SELECT + " WHERE s.id = ?",
            (session.get("student_id"),),
        ).fetchone()
    if not student:
        abort(404)
    return render_template("student_account.html", student=student)


@app.route("/student/qr.png")
@student_required
def student_qr_self():
    with get_db() as db:
        student = db.execute(
            "SELECT token FROM students WHERE id = ?",
            (session.get("student_id"),),
        ).fetchone()
    if not student:
        abort(404)
    return send_file(
        qr_image_for_token(student["token"]),
        mimetype="image/png",
        download_name="my-studentverifi-qr.png",
    )


@app.route("/logout", methods=["POST"])
def logout():
    session.clear()
    flash("You have been logged out.", "success")
    return redirect(url_for("index"))


# ---------------------------------------------------------------------------
# Administrator dashboard and student management
# ---------------------------------------------------------------------------

@app.route("/dashboard")
@admin_required
def dashboard():
    with get_db() as db:
        total = db.execute("SELECT COUNT(*) FROM students").fetchone()[0]
        active = db.execute(
            "SELECT COUNT(*) FROM students WHERE status = 'Active'"
        ).fetchone()[0]
        inactive = db.execute(
            "SELECT COUNT(*) FROM students WHERE status <> 'Active'"
        ).fetchone()[0]
        checks = db.execute("SELECT COUNT(*) FROM verification_logs").fetchone()[0]
        recent = db.execute(
            """SELECT l.*, s.matric_no, u.username,
                      CASE WHEN s.middle_name IS NULL OR s.middle_name = ''
                      THEN s.first_name || ' ' || s.last_name
                      ELSE s.first_name || ' ' || s.middle_name || ' ' || s.last_name
                 END AS full_name
               FROM verification_logs l
               LEFT JOIN students s ON s.id = l.student_id
               LEFT JOIN users u ON u.id = l.verified_by
               ORDER BY l.id DESC LIMIT 8"""
        ).fetchall()
    return render_template(
        "dashboard.html",
        total=total,
        active=active,
        inactive=inactive,
        checks=checks,
        recent=recent,
    )


@app.route("/students")
@admin_required
def students():
    query = request.args.get("q", "").strip()
    with get_db() as db:
        base_query = """
            SELECT s.*, f.name AS faculty, d.name AS department,
                   CASE WHEN s.middle_name IS NULL OR s.middle_name = ''
                   THEN s.first_name || ' ' || s.last_name
                   ELSE s.first_name || ' ' || s.middle_name || ' ' || s.last_name
              END AS full_name
            FROM students s
            JOIN faculties f ON f.id = s.faculty_id
            JOIN departments d ON d.id = s.department_id
        """
        if query:
            pattern = f"%{query}%"
            rows = db.execute(
                base_query
                + """ WHERE lower(s.first_name || ' ' || coalesce(s.middle_name, '') || ' ' || s.last_name) LIKE lower(?)
                      OR lower(s.matric_no) LIKE lower(?)
                      OR lower(d.name) LIKE lower(?)
                      OR lower(f.name) LIKE lower(?)
                      ORDER BY s.id DESC""",
                (pattern, pattern, pattern, pattern),
            ).fetchall()
        else:
            rows = db.execute(base_query + " ORDER BY s.id DESC").fetchall()

    return render_template("students.html", students=rows, q=query)


@app.route("/students/new", methods=["GET", "POST"])
@admin_required
def add_student():
    if request.method == "POST":
        student_data, error = validate_student_form(request.form)
        if error:
            flash(error, "danger")
            return render_with_catalogue("student_form.html", student=None)

        token = secrets.token_urlsafe(32)
        try:
            with get_db() as db:
                db.execute(
                    """INSERT INTO students
                       (matric_no, first_name, middle_name, last_name,
                        faculty_id, department_id, level, email, photo_url,
                        token, status, record_source, created_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'Active', 'manual', ?)""",
                    (
                        student_data["matric_no"],
                        student_data["first_name"],
                        student_data["middle_name"],
                        student_data["last_name"],
                        student_data["faculty_id"],
                        student_data["department_id"],
                        student_data["level"],
                        student_data["email"],
                        student_data["photo_url"],
                        token,
                        now(),
                    ),
                )
                student_id = db.execute(
                    "SELECT id FROM students WHERE token = ?", (token,)
                ).fetchone()["id"]

            flash("Student registered successfully.", "success")
            return redirect(url_for("student_detail", student_id=student_id))
        except IntegrityError:
            flash("That matriculation number is already registered.", "danger")

    return render_with_catalogue("student_form.html", student=None)


@app.route("/students/import-template.csv")
@admin_required
def student_import_template():
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(
        [
            "matric_no",
            "first_name",
            "middle_name",
            "last_name",
            "faculty",
            "department",
            "level",
            "email",
            "status",
        ]
    )
    writer.writerow(
        [
            "TEST/2026/000001",
            "Ada",
            "",
            "Example",
            "Faculty of Science",
            "Computer Science",
            "400",
            "ada.example@example.com",
            "Active",
        ]
    )
    return send_file(
        io.BytesIO(output.getvalue().encode("utf-8-sig")),
        mimetype="text/csv",
        as_attachment=True,
        download_name="studentverifi-student-template.csv",
    )


def normalise_csv_header(value):
    value = unicodedata.normalize("NFKD", str(value or "")).encode("ascii", "ignore").decode()
    value = value.casefold().replace("&", " and ")
    value = re.sub(r"[^a-z0-9]+", "_", value)
    return value.strip("_")


CSV_HEADER_ALIASES = {
    "matric_no": {
        "matric_no", "matric_number", "matriculation_number", "matriculation_no",
        "matric_no_", "matric", "reg_no", "registration_no", "registration_number",
        "registration_num", "matriculation_registration_number",
    },
    "first_name": {"first_name", "firstname", "given_name", "forename"},
    "middle_name": {"middle_name", "middlename", "other_name", "other_names"},
    "last_name": {"last_name", "lastname", "surname", "family_name"},
    "full_name": {"full_name", "fullname", "student_name", "name"},
    "faculty": {"faculty", "faculty_name", "faculty_of"},
    "department": {"department", "department_name", "dept", "dept_name"},
    "level": {"level", "study_level", "student_level", "class_level"},
    "email": {"email", "email_address", "e_mail"},
    "status": {"status", "student_status", "registration_status"},
}


def canonical_csv_row(source):
    row = {
        normalise_csv_header(key): (value or "").strip()
        for key, value in source.items()
        if key
    }
    result = {}
    for target, aliases in CSV_HEADER_ALIASES.items():
        if row.get(target):
            result[target] = row[target]
            continue
        for alias in sorted(aliases):
            if row.get(alias):
                result[target] = row[alias]
                break
    return result


@app.route("/students/import", methods=["GET", "POST"])
@admin_required
def import_students():
    if request.method == "GET":
        return render_template("student_import.html")

    upload = request.files.get("file")
    if not upload or not upload.filename or not upload.filename.lower().endswith(".csv"):
        flash("Choose a CSV file to import.", "danger")
        return redirect(url_for("import_students"))

    raw = upload.stream.read(app.config["MAX_CONTENT_LENGTH"] + 1)
    if len(raw) > app.config["MAX_CONTENT_LENGTH"]:
        flash("The CSV file is too large. Maximum size is 5 MB.", "danger")
        return redirect(url_for("import_students"))

    try:
        reader = csv.DictReader(io.StringIO(raw.decode("utf-8-sig")))
        if not reader.fieldnames:
            flash("The CSV file has no header row.", "danger")
            return redirect(url_for("import_students"))

        headers = {normalise_csv_header(header) for header in reader.fieldnames if header}
        recognised = {
            alias
            for aliases in CSV_HEADER_ALIASES.values()
            for alias in aliases
        }
        if not headers.intersection(recognised):
            flash("The CSV header row could not be recognised. Download the template to see the supported format.", "danger")
            return redirect(url_for("import_students"))

        _, department_rows = load_catalogue()
        rows_to_insert = []
        errors = []
        seen = set()

        for line_number, source in enumerate(reader, start=2):
            row = canonical_csv_row(source)
            if not any(row.values()):
                continue

            matric = normalise_matric_no(row.get("matric_no", ""))
            first_name = " ".join(row.get("first_name", "").split())
            middle_name = " ".join(row.get("middle_name", "").split()) or None
            last_name = " ".join(row.get("last_name", "").split())

            if not first_name or not last_name:
                parsed_name = split_full_name(row.get("full_name", ""))
                if parsed_name:
                    first_name, parsed_middle, last_name = parsed_name
                    middle_name = middle_name or parsed_middle

            faculty_value = row.get("faculty", "")
            department_value = row.get("department", "")
            level = normalise_level(row.get("level", ""))
            email = row.get("email", "").strip()
            status = (row.get("status") or "Active").strip().title()

            if not all([matric, first_name, last_name, department_value, level]):
                errors.append(f"Row {line_number}: matriculation number, first name, surname, department and level are required.")
                continue
            if not valid_matric_no(matric):
                errors.append(f"Row {line_number}: invalid matriculation number '{matric}'.")
                continue
            if len(first_name) > 100 or len(middle_name or "") > 100 or len(last_name) > 100:
                errors.append(f"Row {line_number}: student name exceeds 100 characters.")
                continue
            if len(level) > 50 or len(email) > 254:
                errors.append(f"Row {line_number}: level or email exceeds the permitted length.")
                continue
            if email and not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", email):
                errors.append(f"Row {line_number}: invalid email address.")
                continue
            if status not in {"Active", "Inactive"}:
                errors.append(f"Row {line_number}: status must be Active or Inactive.")
                continue
            if matric in seen:
                errors.append(f"Row {line_number}: duplicate matriculation number '{matric}' in the file.")
                continue

            resolved, catalogue_error = resolve_catalogue_entry(
                faculty_value, department_value, department_rows
            )
            if catalogue_error:
                errors.append(f"Row {line_number}: {catalogue_error}")
                continue

            seen.add(matric)
            rows_to_insert.append(
                (
                    matric,
                    first_name,
                    middle_name,
                    last_name,
                    resolved["faculty_id"],
                    resolved["department_id"],
                    level,
                    email or None,
                    None,
                    secrets.token_urlsafe(32),
                    status,
                    "imported",
                    now(),
                )
            )

        if errors:
            for error in errors[:10]:
                flash(error, "danger")
            if len(errors) > 10:
                flash(f"{len(errors) - 10} additional validation errors were found.", "danger")
            return redirect(url_for("import_students"))

        if not rows_to_insert:
            flash("No student rows were found in the CSV.", "warning")
            return redirect(url_for("import_students"))

        with get_db() as db:
            existing = {
                row[0]
                for row in db.execute("SELECT matric_no FROM students").fetchall()
            }
            duplicates = sorted(existing.intersection(seen))
            if duplicates:
                flash(
                    "Import cancelled; these matriculation numbers already exist: "
                    + ", ".join(duplicates[:10]),
                    "danger",
                )
                return redirect(url_for("import_students"))

            db.executemany(
                """INSERT INTO students
                   (matric_no, first_name, middle_name, last_name,
                    faculty_id, department_id, level, email, photo_url,
                    token, status, record_source, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                rows_to_insert,
            )

        flash(
            f"Successfully imported {len(rows_to_insert)} student record(s).",
            "success",
        )
        return redirect(url_for("students"))

    except (UnicodeDecodeError, csv.Error):
        flash("Could not read this CSV. Save it as UTF-8 CSV and try again.", "danger")
        return redirect(url_for("import_students"))


@app.route("/students/synthetic-demo", methods=["POST"])
@admin_required
def create_synthetic_demo():
    samples = [
        ("TEST/CSC/001", "Ada", None, "Example", "Faculty of Science", "Computer Science", "400", "ada.example@example.com"),
        ("TEST/CSC/002", "Chidi", None, "Sample", "Faculty of Science", "Computer Science", "300", "chidi.sample@example.com"),
        ("TEST/BCH/003", "Nneka", None, "Demo", "Faculty of Science", "Biochemistry", "200", "nneka.demo@example.com"),
        ("TEST/ENG/004", "Obinna", None, "Sample", "Faculty of Engineering", "Electrical & Electronics Engineering", "400", "obinna.sample@example.com"),
        ("TEST/EDU/005", "Amara", None, "Demo", "Faculty of Education", "Arts / Social Science", "100", "amara.demo@example.com"),
    ]

    _, department_rows = load_catalogue()
    created = 0
    with get_db() as db:
        for matric, first, middle, last, faculty, department, level, email in samples:
            if db.execute(
                "SELECT id FROM students WHERE matric_no = ?", (matric,)
            ).fetchone():
                continue
            resolved, error = resolve_catalogue_entry(faculty, department, department_rows)
            if error:
                continue
            db.execute(
                """INSERT INTO students
                   (matric_no, first_name, middle_name, last_name,
                    faculty_id, department_id, level, email, photo_url,
                    token, status, record_source, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, NULL, ?, 'Active', 'synthetic', ?)""",
                (
                    matric, first, middle, last,
                    resolved["faculty_id"], resolved["department_id"],
                    level, email, secrets.token_urlsafe(32), now(),
                ),
            )
            created += 1

    flash(
        f"Added {created} fictional test record(s). These are not official EBSU records."
        if created
        else "No new sample records were added.",
        "success" if created else "warning",
    )
    return redirect(url_for("students"))


@app.route("/students/<int:student_id>")
@admin_required
def student_detail(student_id):
    with get_db() as db:
        student = db.execute(
            STUDENT_SELECT + " WHERE s.id = ?",
            (student_id,),
        ).fetchone()
    if not student:
        abort(404)
    return render_template("student_detail.html", student=student)


@app.route("/students/<int:student_id>/qr.png")
@admin_required
def student_qr(student_id):
    with get_db() as db:
        student = db.execute(
            "SELECT token FROM students WHERE id = ?",
            (student_id,),
        ).fetchone()
    if not student:
        abort(404)
    return send_file(
        qr_image_for_token(student["token"]),
        mimetype="image/png",
        download_name=f"student-{student_id}-qr.png",
    )


@app.route("/students/<int:student_id>/toggle-status", methods=["POST"])
@admin_required
def toggle_status(student_id):
    with get_db() as db:
        student = db.execute(
            "SELECT status FROM students WHERE id = ?",
            (student_id,),
        ).fetchone()
        if not student:
            abort(404)
        new_status = "Inactive" if student["status"] == "Active" else "Active"
        db.execute(
            "UPDATE students SET status = ? WHERE id = ?",
            (new_status, student_id),
        )
    flash(f"Student status changed to {new_status}.", "success")
    return redirect(url_for("student_detail", student_id=student_id))


# ---------------------------------------------------------------------------
# QR identity verification and audit history
# ---------------------------------------------------------------------------

@app.route("/verify", methods=["GET", "POST"])
@admin_required
def verify():
    result = None
    submitted = ""

    if request.method == "POST":
        submitted = request.form.get("token", "").strip()
        with get_db() as db:
            student = db.execute(
                STUDENT_SELECT + " WHERE s.token = ?",
                (submitted,),
            ).fetchone() if submitted else None

            if student and student["status"] == "Active":
                outcome = "VALID"
            elif student:
                outcome = "INACTIVE"
            else:
                outcome = "INVALID"

            db.execute(
                """INSERT INTO verification_logs
                   (student_id, scanned_token, result, verified_by, verified_at)
                   VALUES (?, ?, ?, ?, ?)""",
                (
                    student["id"] if student else None,
                    submitted[:200],
                    outcome,
                    session.get("user_id"),
                    now(),
                ),
            )
        result = {"outcome": outcome, "student": student}

    return render_template("verify.html", result=result, submitted=submitted)


@app.route("/logs")
@admin_required
def logs():
    with get_db() as db:
        rows = db.execute(
            """SELECT l.*, s.matric_no, u.username,
                      CASE WHEN s.middle_name IS NULL OR s.middle_name = ''
                      THEN s.first_name || ' ' || s.last_name
                      ELSE s.first_name || ' ' || s.middle_name || ' ' || s.last_name
                 END AS full_name
               FROM verification_logs l
               LEFT JOIN students s ON s.id = l.student_id
               LEFT JOIN users u ON u.id = l.verified_by
               ORDER BY l.id DESC LIMIT 250"""
        ).fetchall()
    return render_template("logs.html", logs=rows)


@app.route("/account/password", methods=["GET", "POST"])
@admin_required
def change_password():
    if request.method == "POST":
        current = request.form.get("current_password", "")
        new_password = request.form.get("new_password", "")
        if len(new_password) < 10:
            flash("Use a new password of at least 10 characters.", "danger")
        else:
            with get_db() as db:
                user = db.execute(
                    "SELECT * FROM users WHERE id = ?",
                    (session["user_id"],),
                ).fetchone()
                if user and check_password_hash(user["password_hash"], current):
                    db.execute(
                        "UPDATE users SET password_hash = ? WHERE id = ?",
                        (generate_password_hash(new_password), session["user_id"]),
                    )
                    flash("Password updated.", "success")
                    return redirect(url_for("dashboard"))
                flash("Current password was incorrect.", "danger")
    return render_template("change_password.html")


@app.errorhandler(403)
def forbidden(_error):
    return render_template("403.html"), 403


@app.errorhandler(404)
def not_found(_error):
    return render_template("404.html"), 404


@app.errorhandler(413)
def request_entity_too_large(_error):
    flash("The uploaded file is too large. The maximum permitted size is 5 MB.", "danger")
    return redirect(url_for("import_students")), 303


@app.route("/health")
def health():
    try:
        with get_engine().connect() as connection:
            connection.execute(text("SELECT 1"))
        return {"status": "ok"}, 200
    except Exception:
        app.logger.exception("Health check database connection failed.")
        return {"status": "unavailable"}, 503


if __name__ == "__main__":
    app.run(debug=os.environ.get("FLASK_DEBUG", "false").lower() == "true")
