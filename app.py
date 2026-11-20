"""StudentVerifi Flask JSON API and Vite/React SPA host.

Existing Neon `students`, `users`, `verification_logs` and
`student_account_requests` tables are reused. This release NEVER drops or
recreates them. The optional support tables have an sv_ prefix.
"""
from __future__ import annotations

import csv
import hashlib
import io
import os
import re
import secrets
from datetime import datetime, timedelta, timezone
from functools import wraps
from pathlib import Path

import qrcode
from flask import Flask, abort, jsonify, request, send_file, send_from_directory, session
from flask_wtf.csrf import CSRFError, CSRFProtect, generate_csrf
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import make_url
from werkzeug.security import check_password_hash, generate_password_hash

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

BASE = Path(__file__).resolve().parent
APP_PRODUCTION = bool(os.environ.get('VERCEL') or os.environ.get('RAILWAY_ENVIRONMENT'))
app = Flask(__name__, static_folder=None)
app.config.update(
    SECRET_KEY=os.environ.get('SECRET_KEY') or ('development-secret-change-before-deploy' if not APP_PRODUCTION else None),
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE='Lax',
    SESSION_COOKIE_SECURE=os.environ.get('COOKIE_SECURE', 'true' if APP_PRODUCTION else 'false').lower() == 'true',
    PERMANENT_SESSION_LIFETIME=timedelta(hours=8),
    MAX_CONTENT_LENGTH=3 * 1024 * 1024,
    WTF_CSRF_TIME_LIMIT=3600,
)
if not app.config['SECRET_KEY']:
    raise RuntimeError('Configure SECRET_KEY before deploying StudentVerifi.')
csrf = CSRFProtect(app)

raw_url = os.environ.get('DATABASE_URL', '').strip()
if not raw_url:
    raise RuntimeError('Configure DATABASE_URL to point at your existing Neon PostgreSQL database.')
parsed_url = make_url(raw_url)
if parsed_url.drivername in {'postgres', 'postgresql', 'postgresql+psycopg2'}:
    parsed_url = parsed_url.set(drivername='postgresql+psycopg')
if not parsed_url.drivername.startswith('postgresql+psycopg'):
    raise RuntimeError('This release requires the existing Neon PostgreSQL database; MySQL is unsupported.')
engine = create_engine(parsed_url, pool_pre_ping=True, pool_recycle=260, pool_size=3, max_overflow=2, pool_timeout=8)


def utc_now():
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


def respond(data=None, *, status=200):
    return jsonify(data if data is not None else {}), status


def fail(message, status=400, code=None):
    return respond({'error': message, 'code': code or 'request_error'}, status=status)


def values(result):
    return [dict(row) for row in result.mappings().all()]


def one(result):
    row = result.mappings().first()
    return dict(row) if row else None


def schema_columns(table):
    """Return known column names; never interpolate client values into SQL."""
    return {col['name'] for col in inspect(engine).get_columns(table)}


def clean(value, max_len=200):
    return str(value or '').strip()[:max_len]


def payload():
    data = request.get_json(silent=True)
    return data if isinstance(data, dict) else {}


def student_name(record):
    return (' '.join(filter(None, [record.get('first_name'), record.get('middle_name'), record.get('last_name')]))
            or record.get('full_name') or 'Unknown student')


def student_public(record, detailed=False):
    if not record:
        return None
    obj = {
        'id': record.get('id'), 'matric_no': record.get('matric_no'),
        'name': student_name(record), 'first_name': record.get('first_name', ''),
        'middle_name': record.get('middle_name', ''), 'last_name': record.get('last_name', ''),
        'faculty': record.get('faculty', ''), 'department': record.get('department', ''),
        'level': record.get('level'), 'status': record.get('status'),
        'photo_url': record.get('photo_url') or None,
    }
    if detailed:
        obj.update(email=record.get('email'), record_source=record.get('record_source'),
                   created_at=record.get('created_at'), claimed=bool(record.get('claimed_at')))
    return obj


def current_user():
    if not session.get('user_id'):
        return None
    return {'id': session['user_id'], 'username': session.get('username'),
            'role': session.get('role'), 'student_id': session.get('student_id')}


def guarded(role=None):
    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            user = current_user()
            if not user:
                return fail('Please sign in to continue.', 401, 'unauthenticated')
            if role and user['role'] != role:
                return fail('You do not have permission for this action.', 403, 'forbidden')
            return fn(*args, **kwargs)
        return wrapper
    return decorator


def safe_page():
    try:
        return min(max(int(request.args.get('page', '1')), 1), 100000)
    except (ValueError, TypeError):
        return 1


def safe_limit():
    try:
        return min(max(int(request.args.get('limit', '20')), 1), 100)
    except (ValueError, TypeError):
        return 20


def support_tables(conn):
    # Creates only new, namespaced support tables. No existing user data changed.
    conn.execute(text('''CREATE TABLE IF NOT EXISTS sv_login_attempts (
        attempt_key VARCHAR(64) PRIMARY KEY, hits INTEGER NOT NULL,
        window_started TIMESTAMPTZ NOT NULL)'''))
    conn.execute(text('''CREATE TABLE IF NOT EXISTS sv_admin_audit (
        id BIGSERIAL PRIMARY KEY, actor_id INTEGER, event VARCHAR(90) NOT NULL,
        details VARCHAR(300) NOT NULL DEFAULT '', created_at TIMESTAMPTZ NOT NULL DEFAULT NOW())'''))


def record_audit(conn, event, details=''):
    support_tables(conn)
    conn.execute(text('''INSERT INTO sv_admin_audit (actor_id, event, details)
                         VALUES (:actor, :event, :details)'''),
                 {'actor': session.get('user_id'), 'event': event[:90], 'details': str(details)[:300]})


def record_failed_login(conn, username):
    support_tables(conn)
    ip = request.headers.get('X-Forwarded-For', request.remote_addr or '').split(',')[0].strip()[:120]
    key = hashlib.sha256((ip + ':' + username.casefold()).encode()).hexdigest()
    attempts = conn.execute(text('''INSERT INTO sv_login_attempts(attempt_key, hits, window_started)
        VALUES (:key, 1, NOW()) ON CONFLICT(attempt_key) DO UPDATE SET
        hits = CASE WHEN sv_login_attempts.window_started < NOW() - INTERVAL '15 minutes'
                    THEN 1 ELSE sv_login_attempts.hits + 1 END,
        window_started = CASE WHEN sv_login_attempts.window_started < NOW() - INTERVAL '15 minutes'
                    THEN NOW() ELSE sv_login_attempts.window_started END
        RETURNING hits'''), {'key': key}).scalar_one()
    return attempts


def login_is_limited(conn, username):
    support_tables(conn)
    ip = request.headers.get('X-Forwarded-For', request.remote_addr or '').split(',')[0].strip()[:120]
    key = hashlib.sha256((ip + ':' + username.casefold()).encode()).hexdigest()
    hits = conn.execute(text('''SELECT hits FROM sv_login_attempts
        WHERE attempt_key=:key AND window_started > NOW() - INTERVAL '15 minutes' '''), {'key': key}).scalar()
    return bool(hits is not None and hits >= 8)


def clear_failed_logins(conn, username):
    ip = request.headers.get('X-Forwarded-For', request.remote_addr or '').split(',')[0].strip()[:120]
    key = hashlib.sha256((ip + ':' + username.casefold()).encode()).hexdigest()
    conn.execute(text('DELETE FROM sv_login_attempts WHERE attempt_key=:key'), {'key': key})


@app.after_request
def security_headers(response):
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
    response.headers['X-Frame-Options'] = 'DENY'
    response.headers['Permissions-Policy'] = 'camera=(self), microphone=(), geolocation=()'
    response.headers['Content-Security-Policy'] = (
        "default-src 'self'; base-uri 'self'; form-action 'self'; frame-ancestors 'none'; "
        "object-src 'none'; script-src 'self'; style-src 'self'; "
        "img-src 'self' data: https:; connect-src 'self'; media-src 'self' blob:; "
        "font-src 'self' data:"
    )
    if request.path.startswith('/api/') or request.path.endswith('/qr.png'):
        response.headers['Cache-Control'] = 'no-store, private'
    return response


@app.errorhandler(CSRFError)
def csrf_failure(_e):
    return fail('Your security session expired. Refresh the page and try again.', 400, 'csrf_expired')


@app.errorhandler(413)
def upload_too_large(_e):
    return fail('The file exceeds the 3 MB upload limit.', 413)


@app.errorhandler(404)
def missing(_e):
    if request.path.startswith('/api/') or request.path.startswith('/assets/'):
        return fail('This resource was not found.', 404, 'not_found')
    return serve_spa()


@app.get('/health')
def health():
    try:
        with engine.connect() as conn:
            conn.execute(text('SELECT 1'))
            initialized = conn.execute(text('''SELECT to_regclass('public.students') IS NOT NULL
                                     AND to_regclass('public.users') IS NOT NULL''')).scalar()
        return respond({'status': 'ok', 'database': 'connected', 'initialized': bool(initialized)})
    except Exception:
        app.logger.exception('Database connectivity check failed')
        return fail('Database unavailable.', 503, 'database_unavailable')


@app.get('/api/compatibility')
@guarded('admin')
def compatibility():
    """Read-only check before placing a React release over an existing database."""
    required = {
        'users': {'id', 'username', 'password_hash', 'role', 'student_id', 'created_at'},
        'students': {'id', 'matric_no', 'department', 'level', 'email', 'token',
                     'status', 'record_source', 'claim_code_hash', 'claimed_at'},
        'student_account_requests': {'id', 'student_id', 'password_hash', 'status',
                                     'requested_at', 'reviewed_at', 'reviewed_by'},
        'verification_logs': {'id', 'student_id', 'result', 'verified_by', 'verified_at'}
    }
    checks = {}
    try:
        tables = set(inspect(engine).get_table_names())
        for table, fields in required.items():
            if table not in tables:
                checks[table] = {'present': False, 'missing': sorted(fields)}
                continue
            columns = schema_columns(table)
            missing = fields - columns
            if table == 'students' and not ('full_name' in columns or {'first_name','last_name'} <= columns):
                missing.add('full_name OR first_name+last_name')
            if table == 'verification_logs' and not ('scanned_token' in columns or 'token_fingerprint' in columns):
                missing.add('scanned_token OR token_fingerprint')
            checks[table] = {'present': True, 'missing': sorted(missing)}
        compatible = all(item['present'] and not item['missing'] for item in checks.values())
        return respond({'compatible': compatible, 'checks': checks,
                        'message': 'This is a read-only structure check. It does not validate live workflows or constraints.'})
    except Exception:
        app.logger.exception('Compatibility inspection failed')
        return fail('Unable to inspect database tables.', 503)


@app.get('/api/session')
def api_session():
    return respond({'user': current_user(), 'csrf_token': generate_csrf()})


@app.post('/api/login')
def api_login():
    d = payload()
    username = clean(d.get('username'), 80)
    password = str(d.get('password') or '')
    if not username or not password:
        return fail('Enter your username and password.')
    with engine.begin() as conn:
        if login_is_limited(conn, username):
            return fail('Too many sign-in attempts. Try again in 15 minutes.', 429, 'rate_limited')
        user = one(conn.execute(text('SELECT * FROM users WHERE username=:u'), {'u': username}))
        if not user or not check_password_hash(user['password_hash'], password):
            hits = record_failed_login(conn, username)
            if hits >= 8:
                return fail('Too many sign-in attempts. Try again in 15 minutes.', 429, 'rate_limited')
            return fail('Incorrect username or password.', 401, 'invalid_credentials')
        clear_failed_logins(conn, username)
    session.clear()
    session.permanent = True
    session.update(user_id=user['id'], username=user['username'], role=user['role'], student_id=user.get('student_id'))
    return respond({'user': current_user(), 'csrf_token': generate_csrf()})


@app.post('/api/logout')
@guarded()
def api_logout():
    session.clear()
    return respond({'ok': True})


@app.post('/api/account/password')
@guarded()
def change_password():
    d = payload()
    old, new = str(d.get('current_password') or ''), str(d.get('new_password') or '')
    if not 12 <= len(new) <= 128:
        return fail('Choose a password containing 12–128 characters.')
    with engine.begin() as conn:
        user = one(conn.execute(text('SELECT password_hash FROM users WHERE id=:id'), {'id': session['user_id']}))
        if not user or not check_password_hash(user['password_hash'], old):
            return fail('Your current password is incorrect.', 403)
        conn.execute(text('UPDATE users SET password_hash=:pw WHERE id=:id'),
                     {'pw': generate_password_hash(new), 'id': session['user_id']})
        if session.get('role') == 'admin':
            record_audit(conn, 'password_changed', 'Administrator updated own password')
    return respond({'message': 'Your password has been updated.'})


@app.get('/api/dashboard')
@guarded('admin')
def dashboard():
    with engine.connect() as conn:
        students = conn.execute(text('SELECT COUNT(*) FROM students')).scalar_one()
        active = conn.execute(text("SELECT COUNT(*) FROM students WHERE status='Active'")).scalar_one()
        pending = conn.execute(text("SELECT COUNT(*) FROM student_account_requests WHERE status='Pending'")).scalar_one()
        total_verifications = conn.execute(text('SELECT COUNT(*) FROM verification_logs')).scalar_one()
    return respond({'students': students, 'active': active, 'pending': pending, 'verifications': total_verifications})


@app.get('/api/catalogue')
@guarded('admin')
def catalogue():
    columns = schema_columns('students')
    with engine.connect() as conn:
        faculties = [r[0] for r in conn.execute(text('''SELECT DISTINCT faculty FROM students
                    WHERE faculty IS NOT NULL AND faculty <> '' ORDER BY faculty''')).all()] if 'faculty' in columns else []
        depts = [r[0] for r in conn.execute(text('''SELECT DISTINCT department FROM students
                    WHERE department IS NOT NULL AND department <> '' ORDER BY department''')).all()]
    return respond({'faculties': faculties, 'departments': depts,
                    'note': 'Names are derived from the existing student register, not an authoritative university catalogue.'})


@app.get('/api/students')
@guarded('admin')
def list_students():
    page, limit = safe_page(), safe_limit()
    query = clean(request.args.get('q'), 100)
    status = request.args.get('status', '')
    where = ['1=1']
    params = {'limit': limit, 'offset': (page - 1) * limit}
    if query:
        columns = schema_columns('students')
        searchable = ['matric_no', 'department', 'first_name', 'last_name', 'full_name']
        clauses = [f'{c} ILIKE :q' for c in searchable if c in columns]
        where.append('(' + ' OR '.join(clauses) + ')')
        params['q'] = '%' + query.replace('%', '\\%').replace('_', '\\_') + '%'
    if status in {'Active', 'Inactive'}:
        where.append('status = :status')
        params['status'] = status
    condition = ' AND '.join(where)
    with engine.connect() as conn:
        total = conn.execute(text(f'SELECT COUNT(*) FROM students WHERE {condition}'), params).scalar_one()
        records = values(conn.execute(text(f'''SELECT * FROM students WHERE {condition}
                            ORDER BY id DESC LIMIT :limit OFFSET :offset'''), params))
    return respond({'items': [student_public(s, True) for s in records], 'total': total, 'page': page, 'limit': limit})


@app.get('/api/students/<int:student_id>')
@guarded('admin')
def get_student(student_id):
    with engine.connect() as conn:
        record = one(conn.execute(text('SELECT * FROM students WHERE id=:id'), {'id': student_id}))
    if not record:
        return fail('Student not found.', 404)
    return respond({'student': student_public(record, True)})


def validate_student_row(row, columns):
    matric = clean(row.get('matric_no'), 100).upper()
    fname = clean(row.get('first_name'), 90)
    mname = clean(row.get('middle_name'), 90)
    lname = clean(row.get('last_name'), 90)
    fullname = clean(row.get('full_name'), 200)
    if 'first_name' in columns and not (fname and lname) and fullname:
        words = fullname.split()
        fname, lname = words[0], (words[-1] if len(words) > 1 else '')
        mname = ' '.join(words[1:-1])
    if 'full_name' in columns and not fullname:
        fullname = ' '.join(filter(None, (fname, mname, lname)))
    faculty = clean(row.get('faculty'), 200)
    dept = clean(row.get('department'), 200)
    level = clean(row.get('level'), 20)
    email = clean(row.get('email'), 254)
    status = clean(row.get('status') or 'Active', 20).capitalize()
    if not matric or not dept or not level:
        raise ValueError('Matriculation number, department and level are required.')
    if 'first_name' in columns and not (fname and lname):
        raise ValueError('First name and surname are required.')
    if 'full_name' in columns and not fullname:
        raise ValueError('Student name is required.')
    if 'faculty' in columns and not faculty:
        raise ValueError('Faculty is required.')
    if not re.fullmatch(r'[A-Z0-9][A-Z0-9/._-]{2,99}', matric):
        raise ValueError('Matriculation number has unsupported characters or length.')
    if not re.fullmatch(r'[1-6]00', level):
        raise ValueError('Level must be 100, 200, 300, 400, 500 or 600.')
    if email and not re.fullmatch(r'[^@\s]+@[^@\s]+\.[^@\s]+', email):
        raise ValueError('Email address is invalid.')
    if status not in ('Active', 'Inactive'):
        raise ValueError('Status must be Active or Inactive.')
    data = {'matric_no': matric, 'department': dept, 'level': level, 'email': email or None, 'status': status}
    for key, value in [('first_name', fname), ('middle_name', mname or None), ('last_name', lname),
                       ('full_name', fullname), ('faculty', faculty)]:
        if key in columns:
            data[key] = value
    if 'token' in columns:
        data['token'] = secrets.token_urlsafe(32)
    if 'record_source' in columns:
        data['record_source'] = 'synthetic' if matric.startswith(('DEMO/', 'TEST/')) else 'imported'
    if 'created_at' in columns:
        data['created_at'] = utc_now()
    return data


def insert_student(conn, data):
    # Only column names returned from the database inspector are accepted.
    keys = list(data)
    statement = 'INSERT INTO students (' + ','.join(keys) + ') VALUES (' + ','.join(':' + k for k in keys) + ') RETURNING id'
    return conn.execute(text(statement), data).scalar_one()


@app.post('/api/students')
@guarded('admin')
def add_student():
    columns = schema_columns('students')
    try:
        data = validate_student_row(payload(), columns)
    except ValueError as exc:
        return fail(str(exc))
    with engine.begin() as conn:
        existing = conn.execute(text('SELECT 1 FROM students WHERE matric_no=:m'), {'m': data['matric_no']}).scalar()
        if existing:
            return fail('This matriculation number already exists.', 409)
        sid = insert_student(conn, data)
        record_audit(conn, 'student_created', data['matric_no'])
    return respond({'id': sid, 'message': 'Student record added.'}, status=201)


@app.post('/api/students/import')
@guarded('admin')
def import_students():
    upload = request.files.get('file')
    if not upload or not upload.filename or not upload.filename.lower().endswith('.csv'):
        return fail('Choose a CSV file.')
    raw = upload.read(2 * 1024 * 1024 + 1)
    if len(raw) > 2 * 1024 * 1024:
        return fail('The CSV file must be 2 MB or smaller.')
    try:
        reader = csv.DictReader(io.StringIO(raw.decode('utf-8-sig')))
        if not reader.fieldnames:
            return fail('The CSV file is empty.')
        columns = schema_columns('students')
        rows, seen, errors = [], set(), []
        for index, row in enumerate(reader, 2):
            if not any(str(v or '').strip() for v in row.values()):
                continue
            if len(rows) >= 5000:
                return fail('Import a maximum of 5,000 records per file.')
            try:
                normalised = {(k or '').strip().lower(): v for k, v in row.items() if k}
                value = validate_student_row(normalised, columns)
                if value['matric_no'] in seen:
                    raise ValueError('Duplicate matriculation number within CSV.')
                seen.add(value['matric_no'])
                rows.append(value)
            except ValueError as exc:
                errors.append({'line': index, 'message': str(exc)})
        if errors:
            return respond({'error': 'The CSV contains invalid records. No students were imported.',
                            'details': errors[:15]}, status=422)
        if not rows:
            return fail('The CSV has no student records.')
        with engine.begin() as conn:
            existing = [r[0] for r in conn.execute(text('SELECT matric_no FROM students WHERE matric_no = ANY(:m)'),
                          {'m': list(seen)}).all()]
            if existing:
                return respond({'error': 'Import cancelled because some records already exist.', 'duplicates': existing[:15]}, status=409)
            for row in rows:
                insert_student(conn, row)
            record_audit(conn, 'students_imported', f'{len(rows)} student records imported')
        return respond({'count': len(rows), 'message': f'Imported {len(rows)} student records.'}, status=201)
    except (UnicodeDecodeError, csv.Error):
        return fail('The file must be valid UTF-8 CSV.')


@app.get('/api/students/import-template')
@guarded('admin')
def import_template():
    content = ('matric_no,first_name,middle_name,last_name,faculty,department,level,email,status\n'
               'DEMO/2026/000001,Ada,Chiamaka,Example,Science,Computer Science,400,,Active\n')
    output = io.BytesIO(content.encode('utf-8-sig'))
    return send_file(output, mimetype='text/csv', as_attachment=True,
                     download_name='studentverifi-import-template.csv')


@app.post('/api/students/<int:student_id>/status')
@guarded('admin')
def student_status(student_id):
    desired = payload().get('status')
    if desired not in ('Active', 'Inactive'):
        return fail('Status must be Active or Inactive.')
    with engine.begin() as conn:
        result = conn.execute(text('UPDATE students SET status=:s WHERE id=:id'), {'s': desired, 'id': student_id})
        if not result.rowcount:
            return fail('Student not found.', 404)
        record_audit(conn, 'student_status_changed', f'{student_id}: {desired}')
    return respond({'message': 'Student status updated.', 'status': desired})


@app.post('/api/students/<int:student_id>/rotate-qr')
@guarded('admin')
def rotate_qr(student_id):
    with engine.begin() as conn:
        changed = conn.execute(text('UPDATE students SET token=:token WHERE id=:id'),
                     {'token': secrets.token_urlsafe(32), 'id': student_id})
        if not changed.rowcount:
            return fail('Student not found.', 404)
        record_audit(conn, 'qr_rotated', f'Student {student_id}')
    return respond({'message': 'New QR credential issued. Previous QR codes no longer work.'})


@app.post('/api/students/<int:student_id>/claim-code')
@guarded('admin')
def issue_claim(student_id):
    if 'claim_code_hash' not in schema_columns('students'):
        return fail('The database is missing the required claim-code column.', 503)
    code = secrets.token_urlsafe(22)
    with engine.begin() as conn:
        student = one(conn.execute(text('SELECT id, claimed_at FROM students WHERE id=:id'), {'id': student_id}))
        if not student:
            return fail('Student not found.', 404)
        if student.get('claimed_at'):
            return fail('This student account has already been claimed.', 409)
        conn.execute(text('UPDATE students SET claim_code_hash=:code WHERE id=:id'),
                     {'code': generate_password_hash(code), 'id': student_id})
        record_audit(conn, 'claim_code_issued', f'Student {student_id}')
    return respond({'code': code, 'message': 'Copy this code now. It will not be displayed again.'})


@app.get('/api/students/<int:student_id>/qr.png')
@guarded('admin')
def qr_admin(student_id):
    with engine.connect() as conn:
        student = one(conn.execute(text('SELECT token FROM students WHERE id=:id'), {'id': student_id}))
    if not student:
        return fail('Student not found.', 404)
    return make_qr(student['token'], student_id)


def make_qr(token, student_id):
    output = io.BytesIO()
    qrcode.make(token).save(output, format='PNG')
    output.seek(0)
    return send_file(output, mimetype='image/png', download_name=f'student-{student_id}-qr.png')


@app.get('/api/student/me')
@guarded('student')
def student_account():
    with engine.connect() as conn:
        student = one(conn.execute(text('SELECT * FROM students WHERE id=:id'), {'id': session.get('student_id')}))
    if not student:
        return fail('Student record not found.', 404)
    return respond({'student': student_public(student, True)})


@app.get('/api/student/my-qr.png')
@guarded('student')
def student_my_qr():
    with engine.connect() as conn:
        student = one(conn.execute(text('SELECT id, token, status FROM students WHERE id=:id'),
                                   {'id': session.get('student_id')}))
    if not student or student.get('status') != 'Active':
        return fail('The QR code is unavailable for inactive accounts.', 403)
    return make_qr(student['token'], student['id'])


@app.post('/api/register')
def register():
    d = payload()
    matric = clean(d.get('matric_no'), 100).upper()
    code = str(d.get('claim_code') or '')
    password = str(d.get('password') or '')
    if not matric or not code or not 12 <= len(password) <= 128:
        return fail('Enter your matriculation number, claim code and a password of 12–128 characters.')
    with engine.begin() as conn:
        student = one(conn.execute(text('SELECT * FROM students WHERE matric_no=:m FOR UPDATE'), {'m': matric}))
        valid = student and student.get('claim_code_hash') and check_password_hash(student['claim_code_hash'], code)
        if not valid or student.get('status') != 'Active':
            return fail('The details or claim code could not be verified.', 403)
        if conn.execute(text('SELECT id FROM users WHERE username=:u'), {'u': matric}).first():
            return fail('An account already exists. Please sign in.', 409)
        if conn.execute(text('''SELECT id FROM student_account_requests
              WHERE student_id=:id AND status='Pending' '''), {'id': student['id']}).first():
            return fail('A registration request is already pending.', 409)
        conn.execute(text('''INSERT INTO student_account_requests(student_id,password_hash,status,requested_at)
            VALUES (:id,:pw,'Pending',:at)'''),
            {'id': student['id'], 'pw': generate_password_hash(password), 'at': utc_now()})
        conn.execute(text('UPDATE students SET claim_code_hash=NULL WHERE id=:id'), {'id': student['id']})
    return respond({'message': 'Registration submitted. An administrator must approve your account.'}, status=201)


@app.get('/api/registration-requests')
@guarded('admin')
def requests_list():
    with engine.connect() as conn:
        pending = values(conn.execute(text('''SELECT r.id, r.status, r.requested_at,
               s.matric_no, s.id AS student_id, s.department
               FROM student_account_requests r JOIN students s ON s.id=r.student_id
               WHERE r.status='Pending' ORDER BY r.id DESC LIMIT 200''')))
        for req in pending:
            stud = one(conn.execute(text('SELECT * FROM students WHERE id=:id'), {'id': req['student_id']}))
            req['name'] = student_name(stud) if stud else 'Unknown student'
    return respond({'items': pending})


@app.post('/api/registration-requests/<int:rid>/<string:decision>')
@guarded('admin')
def review_request(rid, decision):
    if decision not in ('approve', 'reject'):
        return fail('Unsupported decision.', 404)
    with engine.begin() as conn:
        row = one(conn.execute(text('SELECT * FROM student_account_requests WHERE id=:id FOR UPDATE'), {'id': rid}))
        if not row:
            return fail('Request not found.', 404)
        if row['status'] != 'Pending':
            return fail('This request has already been reviewed.', 409)
        student = one(conn.execute(text('SELECT * FROM students WHERE id=:id'), {'id': row['student_id']}))
        if decision == 'approve':
            if not student or student.get('status') != 'Active':
                return fail('Only active student records can be approved.', 409)
            if conn.execute(text('SELECT id FROM users WHERE username=:u'), {'u': student['matric_no']}).first():
                return fail('A student account already exists.', 409)
            conn.execute(text('''INSERT INTO users(username,password_hash,role,student_id,created_at)
                VALUES (:u,:pw,'student',:sid,:at)'''),
                {'u': student['matric_no'], 'pw': row['password_hash'], 'sid': student['id'], 'at': utc_now()})
            if 'claimed_at' in schema_columns('students'):
                conn.execute(text('UPDATE students SET claimed_at=:at WHERE id=:id'), {'at': utc_now(), 'id': student['id']})
        conn.execute(text('''UPDATE student_account_requests
               SET status=:status,reviewed_at=:at,reviewed_by=:reviewer WHERE id=:id'''),
            {'status': 'Approved' if decision == 'approve' else 'Rejected', 'at': utc_now(),
             'reviewer': session['user_id'], 'id': rid})
        record_audit(conn, 'request_' + decision, f'Request {rid}')
    return respond({'message': f'Registration request {decision}d.'})


@app.post('/api/verify')
@guarded('admin')
def verify():
    token = str(payload().get('token') or '').strip()
    if not token or len(token) > 1024:
        return fail('Scan a QR code or enter a valid token.')
    fingerprint = hashlib.sha256(token.encode('utf-8')).hexdigest()
    with engine.begin() as conn:
        record = one(conn.execute(text('SELECT * FROM students WHERE token=:t'), {'t': token}))
        outcome = 'VALID' if record and record['status'] == 'Active' else 'INACTIVE' if record else 'INVALID'
        columns = schema_columns('verification_logs')
        data = {'student_id': record['id'] if record else None,
                'result': outcome, 'verified_by': session['user_id'], 'verified_at': utc_now()}
        if 'token_fingerprint' in columns:
            data['token_fingerprint'] = fingerprint
        if 'scanned_token' in columns:
            # Store a non-reusable fingerprint, never the QR secret itself.
            data['scanned_token'] = fingerprint
        cols = ','.join(data.keys())
        args = ','.join(':' + key for key in data)
        conn.execute(text(f'INSERT INTO verification_logs ({cols}) VALUES ({args})'), data)
    return respond({'outcome': outcome, 'student': student_public(record) if record else None,
                    'message': 'Active record found.' if outcome == 'VALID'
                    else 'The record is inactive.' if outcome == 'INACTIVE' else 'No matching student record.'})


@app.get('/api/logs')
@guarded('admin')
def logs():
    with engine.connect() as conn:
        rows = values(conn.execute(text('''SELECT l.id, l.student_id, l.result, l.verified_at,
                 s.matric_no, u.username AS verified_by_name
                 FROM verification_logs l
                 LEFT JOIN students s ON s.id=l.student_id
                 LEFT JOIN users u ON u.id=l.verified_by
                 ORDER BY l.id DESC LIMIT 200''')))
    return respond({'items': rows})


@app.get('/api/admin-audit')
@guarded('admin')
def audit_logs():
    with engine.begin() as conn:
        support_tables(conn)
        rows = values(conn.execute(text('''SELECT a.id,a.event,a.details,a.created_at,
                            u.username AS actor FROM sv_admin_audit a
                            LEFT JOIN users u ON a.actor_id=u.id
                            ORDER BY a.id DESC LIMIT 200''')))
    return respond({'items': rows})


@app.get('/api/students/demo-cleanup')
@guarded('admin')
def demo_cleanup_preview():
    with engine.connect() as conn:
        count = conn.execute(text('''SELECT COUNT(*) FROM students WHERE
            matric_no LIKE 'DEMO/2026/%' AND record_source = 'synthetic' ''' )).scalar_one()
    return respond({'count': count, 'pattern': 'DEMO/2026/%', 'confirmation': 'DELETE DEMO RECORDS'})


@app.post('/api/students/demo-cleanup')
@guarded('admin')
def demo_cleanup():
    if payload().get('confirmation') != 'DELETE DEMO RECORDS':
        return fail('Type DELETE DEMO RECORDS to confirm.')
    with engine.begin() as conn:
        student_ids = [row[0] for row in conn.execute(text('''SELECT id FROM students WHERE
                    matric_no LIKE 'DEMO/2026/%' AND record_source='synthetic' FOR UPDATE''')).all()]
        if not student_ids:
            return respond({'removed': 0, 'message': 'No matching synthetic records were found.'})
        # Preserve anonymous verification outcome history, but detach student references.
        conn.execute(text('UPDATE verification_logs SET student_id=NULL WHERE student_id = ANY(:ids)'), {'ids': student_ids})
        conn.execute(text('DELETE FROM student_account_requests WHERE student_id = ANY(:ids)'), {'ids': student_ids})
        conn.execute(text('DELETE FROM users WHERE student_id = ANY(:ids)'), {'ids': student_ids})
        conn.execute(text('DELETE FROM students WHERE id = ANY(:ids)'), {'ids': student_ids})
        record_audit(conn, 'demo_students_deleted', f'{len(student_ids)} DEMO/2026 records removed')
    return respond({'removed': len(student_ids), 'message': f'Removed {len(student_ids)} synthetic records.'})


@app.get('/api/public-info')
def info():
    return respond({'name': 'StudentVerifi', 'institution': 'Ebonyi State University',
                    'prototype': True, 'support': 'Contact your institution administrator for help.'})


def serve_spa():
    target = BASE / 'public' / 'index.html'
    if not target.exists():
        return fail('React application has not been built. Run npm run build before serving.', 503, 'frontend_not_built')
    return send_file(target)


@app.get('/assets/<path:filename>')
def serve_frontend_assets(filename):
    return send_from_directory(BASE / 'public' / 'assets', filename)


@app.route('/', defaults={'path': ''})
@app.route('/<path:path>')
def spa(path):
    if path.startswith(('api/', 'assets/')):
        abort(404)
    if path in ('logo.svg', 'favicon.svg'):
        return send_file(BASE / 'public' / path)
    return serve_spa()


if __name__ == '__main__':
    app.run(port=5000, debug=os.environ.get('FLASK_DEBUG', 'false').lower() == 'true')
