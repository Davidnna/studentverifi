import os
import io
import secrets
import re
import tempfile
from datetime import datetime, timezone
from functools import wraps

import qrcode
from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL, make_url
from sqlalchemy.exc import IntegrityError
from flask_wtf.csrf import CSRFProtect
from dotenv import load_dotenv

load_dotenv()
from flask import (
    Flask, render_template, request, redirect, url_for, flash,
    session, send_file, abort
)
from werkzeug.security import generate_password_hash, check_password_hash

BASE_DIR = os.path.abspath(os.path.dirname(__file__))

app = Flask(__name__)
secret_key = os.environ.get("SECRET_KEY")
is_production = bool(os.environ.get("VERCEL") or os.environ.get("RAILWAY_ENVIRONMENT"))
if is_production and not secret_key:
    raise RuntimeError("SECRET_KEY must be configured in production environment variables.")
app.config["SECRET_KEY"] = secret_key or "local-development-only-change-this-secret"
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
app.config["SESSION_COOKIE_SECURE"] = os.environ.get("COOKIE_SECURE", "true" if is_production else "false").lower() == "true"
app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get("DATABASE_URL", "")


def database_url():
    """Resolve Railway's MySQL URL or local DATABASE_URL into a PyMySQL URL."""
    raw = os.environ.get("DATABASE_URL") or os.environ.get("MYSQL_URL")
    if not raw:
        # Local development also uses MySQL; configure DATABASE_URL in .env.
        raise RuntimeError("Set DATABASE_URL (or Railway's MYSQL_URL) before starting the app.")
    parsed = make_url(raw)
    if parsed.drivername in ("mysql", "mysql+pymysql"):
        parsed = parsed.set(drivername="mysql+pymysql")
    # Aiven connection strings may include ssl-mode=REQUIRED, which is a
    # MySQL client option rather than a PyMySQL URL query parameter.
    query = dict(parsed.query)
    query.pop("ssl-mode", None)
    query.pop("ssl_mode", None)
    return parsed.set(query=query)

def mysql_connect_args():
    """Enable TLS for hosted MySQL; optionally verify using a supplied CA PEM."""
    ca_pem = os.environ.get("MYSQL_SSL_CA_PEM")
    if not ca_pem:
        # Aiven requires TLS. PyMySQL negotiates TLS when ssl is enabled; for
        # certificate verification, provide the service CA in MYSQL_SSL_CA_PEM.
        return {"ssl": {}}
    ca_path = os.path.join(tempfile.gettempdir(), "aiven-mysql-ca.pem")
    with open(ca_path, "w", encoding="utf-8") as ca_file:
        ca_file.write(ca_pem)
    return {"ssl": {"ca": ca_path}}

engine = create_engine(database_url(), pool_pre_ping=True, pool_recycle=280,
                       connect_args=mysql_connect_args())
csrf = CSRFProtect(app)


class DBCompat:
    """Small compatibility layer to keep the starter's parameterized SQL readable."""
    def __init__(self, connection):
        self.connection = connection

    def execute(self, sql, params=()):
        sql = sql.strip()
        if params:
            parts = sql.split("?")
            if len(parts) - 1 != len(params):
                raise ValueError("SQL placeholder count does not match parameters")
            rendered = parts[0]
            values = {}
            for i, value in enumerate(params):
                key = f"p{i}"
                rendered += f":{key}" + parts[i + 1]
                values[key] = value
            return self.connection.execute(text(rendered), values)
        return self.connection.execute(text(sql))

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


class DBContext:
    def __enter__(self):
        self.transaction = engine.begin()
        self.connection = self.transaction.__enter__()
        return DBCompat(self.connection)

    def __exit__(self, exc_type, exc, tb):
        return self.transaction.__exit__(exc_type, exc, tb)


def get_db():
    return DBContext()


def init_db():
    statements = [
        """CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTO_INCREMENT,
            username VARCHAR(80) UNIQUE NOT NULL,
            password_hash VARCHAR(255) NOT NULL,
            role VARCHAR(30) NOT NULL DEFAULT 'admin',
            created_at VARCHAR(40) NOT NULL
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""",
        """CREATE TABLE IF NOT EXISTS students (
            id INTEGER PRIMARY KEY AUTO_INCREMENT,
            matric_no VARCHAR(100) UNIQUE NOT NULL,
            full_name VARCHAR(200) NOT NULL,
            department VARCHAR(200) NOT NULL,
            level VARCHAR(50) NOT NULL,
            email VARCHAR(254),
            photo_url VARCHAR(1000),
            token VARCHAR(128) UNIQUE NOT NULL,
            status VARCHAR(20) NOT NULL DEFAULT 'Active',
            created_at VARCHAR(40) NOT NULL,
            INDEX idx_students_full_name (full_name),
            INDEX idx_students_department (department)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""",
        """CREATE TABLE IF NOT EXISTS verification_logs (
            id INTEGER PRIMARY KEY AUTO_INCREMENT,
            student_id INTEGER NULL,
            scanned_token VARCHAR(200) NOT NULL,
            result VARCHAR(20) NOT NULL,
            verified_by INTEGER NULL,
            verified_at VARCHAR(40) NOT NULL,
            INDEX idx_logs_verified_at (verified_at),
            CONSTRAINT fk_logs_student FOREIGN KEY(student_id) REFERENCES students(id) ON DELETE SET NULL,
            CONSTRAINT fk_logs_user FOREIGN KEY(verified_by) REFERENCES users(id) ON DELETE SET NULL
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4"""
    ]
    with engine.begin() as connection:
        for statement in statements:
            connection.execute(text(statement))
        existing = connection.execute(text("SELECT id FROM users WHERE username = :username"), {"username": "admin"}).first()
        if not existing:
            # Set INITIAL_ADMIN_PASSWORD in Railway variables before first deploy.
            initial_password = os.environ.get("INITIAL_ADMIN_PASSWORD")
            if not initial_password:
                if is_production:
                    raise RuntimeError("Set INITIAL_ADMIN_PASSWORD before first production deployment.")
                initial_password = "ChangeMe123!"
            connection.execute(text("INSERT INTO users (username, password_hash, role, created_at) VALUES (:u, :p, :r, :c)"), {
                "u": os.environ.get("INITIAL_ADMIN_USERNAME", "admin"),
                "p": generate_password_hash(initial_password), "r": "admin", "c": now()
            })


def now():
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not session.get("user_id"):
            flash("Please log in to continue.", "warning")
            return redirect(url_for("login"))
        return view(*args, **kwargs)
    return wrapped


def qr_image_for_token(token):
    img = qrcode.make(token)
    output = io.BytesIO()
    img.save(output, format="PNG")
    output.seek(0)
    return output


@app.route("/")
def index():
    if session.get("user_id"):
        return redirect(url_for("dashboard"))
    return render_template("index.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        with get_db() as db:
            user = db.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
        if user and check_password_hash(user["password_hash"], password):
            session.clear()
            session["user_id"] = user["id"]
            session["username"] = user["username"]
            session["role"] = user["role"]
            return redirect(url_for("dashboard"))
        flash("Invalid username or password.", "danger")
    return render_template("login.html")


@app.route("/logout", methods=["POST"])
def logout():
    session.clear()
    flash("You have been logged out.", "success")
    return redirect(url_for("index"))


@app.route("/dashboard")
@login_required
def dashboard():
    with get_db() as db:
        total = db.execute("SELECT COUNT(*) FROM students").fetchone()[0]
        active = db.execute("SELECT COUNT(*) FROM students WHERE status = 'Active'").fetchone()[0]
        inactive = db.execute("SELECT COUNT(*) FROM students WHERE status != 'Active'").fetchone()[0]
        checks = db.execute("SELECT COUNT(*) FROM verification_logs").fetchone()[0]
        recent = db.execute("""
            SELECT l.*, s.full_name, s.matric_no, u.username
            FROM verification_logs l
            LEFT JOIN students s ON s.id = l.student_id
            LEFT JOIN users u ON u.id = l.verified_by
            ORDER BY l.id DESC LIMIT 8
        """).fetchall()
    return render_template("dashboard.html", total=total, active=active, inactive=inactive, checks=checks, recent=recent)


@app.route("/students")
@login_required
def students():
    q = request.args.get("q", "").strip()
    with get_db() as db:
        if q:
            rows = db.execute("""
                SELECT * FROM students
                WHERE full_name LIKE ? OR matric_no LIKE ? OR department LIKE ?
                ORDER BY id DESC
            """, (f"%{q}%", f"%{q}%", f"%{q}%")).fetchall()
        else:
            rows = db.execute("SELECT * FROM students ORDER BY id DESC").fetchall()
    return render_template("students.html", students=rows, q=q)


@app.route("/students/new", methods=["GET", "POST"])
@login_required
def add_student():
    if request.method == "POST":
        matric_no = request.form.get("matric_no", "").strip().upper()
        full_name = request.form.get("full_name", "").strip()
        department = request.form.get("department", "").strip()
        level = request.form.get("level", "").strip()
        email = request.form.get("email", "").strip()
        photo_url = request.form.get("photo_url", "").strip()

        if not all([matric_no, full_name, department, level]):
            flash("Matriculation number, full name, department and level are required.", "danger")
            return render_template("student_form.html", student=None)

        token = secrets.token_urlsafe(32)
        try:
            with get_db() as db:
                db.execute("""
                    INSERT INTO students
                    (matric_no, full_name, department, level, email, photo_url, token, status, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, 'Active', ?)
                """, (matric_no, full_name, department, level, email, photo_url, token, now()))
                student_id = db.execute("SELECT id FROM students WHERE token = ?", (token,)).fetchone()["id"]
            flash("Student registered successfully.", "success")
            return redirect(url_for("student_detail", student_id=student_id))
        except IntegrityError:
            flash("That matriculation number is already registered.", "danger")
    return render_template("student_form.html", student=None)


@app.route("/students/<int:student_id>")
@login_required
def student_detail(student_id):
    with get_db() as db:
        student = db.execute("SELECT * FROM students WHERE id = ?", (student_id,)).fetchone()
    if not student:
        abort(404)
    return render_template("student_detail.html", student=student)


@app.route("/students/<int:student_id>/qr.png")
@login_required
def student_qr(student_id):
    with get_db() as db:
        student = db.execute("SELECT token FROM students WHERE id = ?", (student_id,)).fetchone()
    if not student:
        abort(404)
    return send_file(qr_image_for_token(student["token"]), mimetype="image/png", download_name=f"student-{student_id}-qr.png")


@app.route("/students/<int:student_id>/toggle-status", methods=["POST"])
@login_required
def toggle_status(student_id):
    with get_db() as db:
        student = db.execute("SELECT status FROM students WHERE id = ?", (student_id,)).fetchone()
        if not student:
            abort(404)
        new_status = "Inactive" if student["status"] == "Active" else "Active"
        db.execute("UPDATE students SET status = ? WHERE id = ?", (new_status, student_id))
    flash(f"Student status changed to {new_status}.", "success")
    return redirect(url_for("student_detail", student_id=student_id))


@app.route("/verify", methods=["GET", "POST"])
@login_required
def verify():
    result = None
    submitted = ""
    if request.method == "POST":
        submitted = request.form.get("token", "").strip()
        with get_db() as db:
            student = db.execute("SELECT * FROM students WHERE token = ?", (submitted,)).fetchone() if submitted else None
            if student and student["status"] == "Active":
                outcome = "VALID"
            elif student:
                outcome = "INACTIVE"
            else:
                outcome = "INVALID"
            db.execute("""
                INSERT INTO verification_logs (student_id, scanned_token, result, verified_by, verified_at)
                VALUES (?, ?, ?, ?, ?)
            """, (student["id"] if student else None, submitted[:200], outcome, session.get("user_id"), now()))
        result = {"outcome": outcome, "student": student}
    return render_template("verify.html", result=result, submitted=submitted)


@app.route("/logs")
@login_required
def logs():
    with get_db() as db:
        rows = db.execute("""
            SELECT l.*, s.full_name, s.matric_no, u.username
            FROM verification_logs l
            LEFT JOIN students s ON s.id = l.student_id
            LEFT JOIN users u ON u.id = l.verified_by
            ORDER BY l.id DESC LIMIT 250
        """).fetchall()
    return render_template("logs.html", logs=rows)


@app.route("/account/password", methods=["GET", "POST"])
@login_required
def change_password():
    if request.method == "POST":
        current = request.form.get("current_password", "")
        new = request.form.get("new_password", "")
        if len(new) < 10:
            flash("Use a new password of at least 10 characters.", "danger")
        else:
            with get_db() as db:
                user = db.execute("SELECT * FROM users WHERE id = ?", (session["user_id"],)).fetchone()
                if user and check_password_hash(user["password_hash"], current):
                    db.execute("UPDATE users SET password_hash = ? WHERE id = ?",
                               (generate_password_hash(new), session["user_id"]))
                    flash("Password updated.", "success")
                    return redirect(url_for("dashboard"))
                flash("Current password was incorrect.", "danger")
    return render_template("change_password.html")


@app.errorhandler(404)
def not_found(_error):
    return render_template("404.html"), 404


# Schema creation is safe to repeat on deploy. For larger systems, use Alembic migrations.
init_db()

@app.route("/health")
def health():
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        return {"status": "ok"}, 200
    except Exception:
        app.logger.exception("Health check database connection failed")
        return {"status": "unavailable"}, 503

if __name__ == "__main__":
    app.run(debug=os.environ.get("FLASK_DEBUG", "false").lower() == "true")
