"""StudentVerifi JSON API. Reuses the production-hardened database services."""
import base64
import csv
import hashlib
import io
import os
import re
import secrets
from datetime import timedelta
from urllib.parse import urlsplit
from functools import wraps
from pathlib import Path
from flask import Blueprint, jsonify, make_response, request, send_file, send_from_directory, session
from flask_wtf.csrf import CSRFError, generate_csrf
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from werkzeug.security import check_password_hash, generate_password_hash

from account_services import (
    CLAIM_COMPLETION_TTL_MINUTES,
    EmailDeliveryError,
    OTP_MAX_ATTEMPTS,
    OTP_MAX_SENDS_PER_HOUR,
    OTP_RESEND_SECONDS,
    OTP_TTL_MINUTES,
    PhotoStorageError,
    create_otp,
    delete_private_profile_photo,
    email_delivery_is_configured,
    otp_digest,
    process_profile_photo,
    read_private_profile_photo,
    send_claim_otp,
    send_verifier_invitation,
    upload_private_profile_photo,
    verify_otp,
)
api = Blueprint('spa_api', __name__, url_prefix='/api')

def install(app, backend):
    """Register JSON endpoints and serve React for client-side routes only."""
    global b
    b = backend
    app.register_blueprint(api)

    @app.errorhandler(CSRFError)
    def csrf_error(error):
        return err('Security check expired. Refresh and try again.', 400)

    @app.errorhandler(413)
    def too_large(error):
        return err('The uploaded file is too large.', 413)

    @app.errorhandler(403)
    def forbidden(error):
        return err('You are not authorised to access this resource.', 403)

    @app.errorhandler(404)
    def not_found(error):
        return err('Resource not found.', 404)

    @app.errorhandler(500)
    def internal_error(error):
        app.logger.exception('Unhandled request error')
        return err('Unable to complete the request.', 500)

    @app.errorhandler(503)
    def unavailable(error):
        return err('The service is temporarily unavailable.', 503)
    root = Path(app.root_path) / 'public'
    client_routes = {'/', '/index.html', '/login', '/register', '/dashboard', '/students', '/students/new', '/students/import', '/students/demo-cleanup', '/verify', '/registration-requests', '/logs', '/admin-audit', '/verifiers', '/verifier/dashboard', '/verifier/activity', '/verifier/accept', '/credential', '/account/password', '/student/account', '/how-it-works', '/about', '/faq', '/privacy', '/contact'}

    @app.before_request
    def react_routes():
        if request.method not in ('GET', 'HEAD'):
            return None
        path = request.path
        if path in ('/favicon.svg', '/logo.svg'):
            return send_from_directory(root, path[1:])
        if path.startswith('/assets/'):
            return send_from_directory(root / 'assets', path[len('/assets/'):])
        if path in client_routes or re.fullmatch('/students/[0-9]+', path) or re.fullmatch('/credential/[A-Za-z0-9_-]{32,128}', path):
            index = root / 'index.html'
            if not index.is_file() or 'STUDENTVERIFI_VITE_BUILD' not in index.read_text():
                app.logger.error('React build missing. Run npm run build before deploying.')
                return ('Application temporarily unavailable.', 503)
            return send_from_directory(root, 'index.html')
        return None

def ok(**kwargs):
    return jsonify(**kwargs)

def err(message, code=400, **kwargs):
    return (jsonify(error=message, **kwargs), code)

def data():
    body = request.get_json(silent=True)
    return body if isinstance(body, dict) else {}

def record(row):
    if row is None:
        return None
    return dict(row._mapping) if hasattr(row, '_mapping') else dict(row)

def lock_student_email(db, email):
    normalized = str(email or '').strip().lower()
    if normalized:
        db.execute('SELECT pg_advisory_xact_lock(hashtextextended(?, 0))', (normalized,))


def ensure_student_email_index(db):
    duplicates = db.execute("""SELECT EXISTS (
        SELECT 1 FROM students WHERE email IS NOT NULL
        GROUP BY LOWER(email) HAVING COUNT(*) > 1
    )""").fetchone()[0]
    if not duplicates:
        db.execute("CREATE UNIQUE INDEX IF NOT EXISTS uq_students_email_lower ON students (LOWER(email)) WHERE email IS NOT NULL")


def public_student(student, photo_href=None):
    if not student:
        return None
    s = record(student)
    safe = {k: s.get(k) for k in (
        'id', 'matric_no', 'first_name', 'middle_name', 'last_name',
        'faculty', 'department', 'level', 'email', 'status',
        'record_source', 'created_at', 'claimed_at', 'email_verified_at',
        'account_claimed'
    )}
    safe['name'] = ' '.join((v for v in (
        s.get('first_name'), s.get('middle_name'), s.get('last_name')
    ) if v))
    has_photo = bool(s.get('photo_blob_path'))
    safe['photo_available'] = has_photo
    safe['photo_private'] = has_photo
    safe['photo_url'] = photo_href if has_photo else None
    safe['has_qr'] = bool(s.get('token') and s.get('photo_blob_path') and s.get('status') == 'Active')
    return safe


def allowed_roles(role):
    if role is None:
        return None
    if isinstance(role, str):
        return {role}
    return set(role)


def protected(role=None):
    """Require a current database-backed session and the requested role."""
    required_roles = allowed_roles(role)

    def decorate(view):
        @wraps(view)
        def wrapped(*args, **kwargs):
            user_id = session.get('user_id')
            if not user_id:
                return err('Please sign in to continue.', 401)
            if required_roles and session.get('role') not in required_roles:
                return err('You are not authorised to access this resource.', 403)
            try:
                b.ensure_security_migrations()
                with b.get_db() as db:
                    user = db.execute(
                        'SELECT id,username,role,student_id,is_active FROM users WHERE id=?',
                        (user_id,)
                    ).fetchone()
                    if not user or not bool(record(user).get('is_active', True)):
                        session.clear()
                        return err('Your account session is no longer active. Sign in again.', 401)
                    user_role = user['role']
                    if user_role != session.get('role'):
                        session.clear()
                        return err('Your account role has changed. Sign in again.', 401)
                    if required_roles and user_role not in required_roles:
                        return err('You do not have permission to access this resource.', 403)
                    if user_role == 'student':
                        student = db.execute(
                            'SELECT status FROM students WHERE id=?',
                            (user['student_id'],)
                        ).fetchone()
                        if not student or student['status'] != 'Active':
                            session.clear()
                            return err('This student account is not currently active.', 403)
                    if user_role == 'student':
                        session['student_id'] = user['student_id']
                    else:
                        session.pop('student_id', None)
            except SQLAlchemyError:
                b.app.logger.exception('Protected API session check failed')
                return err('Your access could not be verified right now. Please try again.', 503)
            return view(*args, **kwargs)
        return wrapped
    return decorate


def application_base_url():
    base = (os.environ.get('APP_BASE_URL') or request.url_root).strip().rstrip('/')
    parsed = urlsplit(base)
    if (parsed.scheme not in ('https', 'http') or not parsed.netloc or
            parsed.username or parsed.password or parsed.path not in ('', '/') or
            parsed.query or parsed.fragment):
        raise ValueError('APP_BASE_URL must be a public application origin without a path or query.')
    if os.environ.get('VERCEL') and parsed.scheme != 'https':
        raise ValueError('APP_BASE_URL must use HTTPS in production.')
    return base


def credential_url(token):
    # Keep bearer credentials in the URL fragment. Fragments are not sent in
    # HTTP requests, access logs or Referer headers.
    return f"{application_base_url()}/credential#{token}"


def verifier_invitation_url(token):
    return f"{application_base_url()}/verifier/accept#{token}"


def extract_qr_token(value):
    raw = str(value or '').strip()
    if not raw or len(raw) > 2048:
        return None
    if raw.startswith(('https://', 'http://')):
        parsed = urlsplit(raw)
        configured = (os.environ.get('APP_BASE_URL') or '').strip()
        expected_host = urlsplit(configured).netloc.lower() if configured else request.host.lower()
        local_http = (
            parsed.scheme == 'http' and not os.environ.get('VERCEL') and
            parsed.hostname in ('localhost', '127.0.0.1')
        )
        if (parsed.scheme != 'https' and not local_http) or parsed.netloc.lower() != expected_host or parsed.username or parsed.password or parsed.query:
            return None
        fragment_token = parsed.fragment.strip()
        if parsed.path == '/credential' and re.fullmatch(r'[A-Za-z0-9_-]{32,128}', fragment_token):
            return fragment_token
        # Accept older preview QR URLs during the migration period.
        match = re.fullmatch(r'/credential/([A-Za-z0-9_-]{32,128})', parsed.path)
        return match.group(1) if match else None
    return raw if re.fullmatch(r'[A-Za-z0-9_-]{32,128}', raw) else None


def send_private_photo_response(pathname):
    if not pathname:
        return err('Profile photograph not found.', 404)
    image_bytes = read_private_profile_photo(pathname)
    if not image_bytes:
        raise PhotoStorageError('Private profile photograph could not be retrieved.')
    response = make_response(send_file(
        io.BytesIO(image_bytes),
        mimetype='image/jpeg',
        as_attachment=False,
        download_name='student-profile.jpg',
        conditional=False
    ))
    response.headers['Content-Disposition'] = 'inline; filename="student-profile.jpg"'
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['Cross-Origin-Resource-Policy'] = 'same-origin'
    response.headers['Vary'] = 'Cookie'
    response.headers['Cache-Control'] = 'private, no-store, max-age=0'
    return response



@api.get('/session')
def current_session():
    user = None
    if session.get('user_id'):
        try:
            b.ensure_security_migrations()
            with b.get_db() as db:
                row = db.execute(
                    'SELECT id, username, role, student_id, email, display_name, is_active FROM users WHERE id=?',
                    (session['user_id'],)
                ).fetchone()
                if row and row['role'] == session.get('role') and bool(record(row).get('is_active', True)):
                    user = record(row)
                else:
                    session.clear()
        except Exception:
            b.app.logger.exception('Session lookup failed')
            return err('Cannot check your session currently.', 503)
    return ok(user=user, csrf_token=generate_csrf())


@api.post('/login')
def login():
    body = data()
    username = str(body.get('username') or '').strip()
    password = str(body.get('password') or '')
    if not username or not password or len(username) > 254 or len(password) > 128:
        return err('Invalid username, email or password.', 401)
    try:
        b.ensure_security_migrations()
        buckets = b._login_rate_limit_buckets(username)
        with b.get_db() as db:
            remaining = b._rate_limit_remaining(db, buckets)
            if remaining:
                reply, status = err('Too many sign-in attempts. Try again later.', 429)
                reply.headers['Retry-After'] = str(remaining)
                return reply, status
            user = db.execute(
                "SELECT * FROM users WHERE username=? OR LOWER(email)=LOWER(?) "
                "ORDER BY CASE WHEN username=? THEN 0 ELSE 1 END LIMIT 1",
                (username, username, username)
            ).fetchone()
            valid = False
            if user and bool(record(user).get('is_active', True)):
                try:
                    valid = check_password_hash(user['password_hash'], password)
                except (ValueError, TypeError):
                    valid = False
                if valid and user['role'] == 'student':
                    student = db.execute(
                        'SELECT status FROM students WHERE id=?',
                        (user['student_id'],)
                    ).fetchone()
                    valid = bool(student and student['status'] == 'Active')
            if not valid:
                b._record_rate_limit_failure(db, buckets)
                return err('Invalid username, email or password.', 401)
            b._clear_rate_limit_failures(db, buckets)
            db.execute('UPDATE users SET last_login_at=? WHERE id=?', (b.now(), user['id']))
            session.clear()
            session.permanent = True
            session.update(
                user_id=user['id'],
                username=user['username'],
                role=user['role'],
                student_id=user['student_id']
            )
            safe = {
                'id': user['id'],
                'username': user['username'],
                'role': user['role'],
                'student_id': user['student_id'],
                'email': record(user).get('email'),
                'display_name': record(user).get('display_name'),
            }
        return ok(user=safe, csrf_token=generate_csrf())
    except SQLAlchemyError:
        b.app.logger.exception('API login failed')
        return err('Sign-in is temporarily unavailable.', 503)


@api.post('/logout')
def logout():
    session.clear()
    return ok(message='Signed out.')

@api.post('/account/password')
@protected()
def update_password():
    body = data()
    current = str(body.get('current_password') or '')
    new = str(body.get('new_password') or '')
    if len(current) > 128 or len(new) < 12 or len(new) > 128 or (body.get('confirm') != new):
        return err('Your new password must be 12–128 characters and match confirmation.')
    with b.get_db() as db:
        user = db.execute('SELECT password_hash FROM users WHERE id=?', (session['user_id'],)).fetchone()
        if not user or not check_password_hash(user['password_hash'], current):
            return err('Current password is incorrect.', 403)
        db.execute('UPDATE users SET password_hash=? WHERE id=?', (generate_password_hash(new), session['user_id']))
        b.audit_admin_action(db, 'account.password_changed', 'user', session['user_id'], 'User changed account password.')
    session.clear()
    return ok(message='Password changed. Sign in again with your new password.')

@api.get('/dashboard')
@protected('admin')
def dashboard():
    with b.get_db() as db:
        total = db.execute('SELECT COUNT(*) FROM students').fetchone()[0]
        active = db.execute("SELECT COUNT(*) FROM students WHERE status='Active'").fetchone()[0]
        checks = db.execute('SELECT COUNT(*) FROM verification_logs').fetchone()[0]
        pending = db.execute("SELECT COUNT(*) FROM student_account_requests WHERE status='Pending'").fetchone()[0]
        claimed = db.execute("SELECT COUNT(*) FROM users WHERE role='student'").fetchone()[0]
        verifiers = db.execute("SELECT COUNT(*) FROM users WHERE role='verifier' AND is_active=TRUE").fetchone()[0]
        unclaimed = max(0, total - claimed)
        recent = db.execute("""
            SELECT l.id,l.result,l.channel,l.verified_at,s.matric_no,s.full_name,
                COALESCE(u.display_name,u.username,'Public visitor') AS verifier_name
            FROM verification_logs l
            LEFT JOIN student_profiles s ON s.id=l.student_id
            LEFT JOIN users u ON u.id=l.verified_by
            ORDER BY l.id DESC
            LIMIT 8
        """).fetchall()
        faculty_rows = db.execute("""
            SELECT f.name AS faculty, COUNT(s.id) AS total
            FROM faculties f
            LEFT JOIN students s ON s.faculty_id = f.id
            GROUP BY f.id, f.name
            ORDER BY total DESC, f.name ASC
            LIMIT 6
        """).fetchall()
        weekly_rows = db.execute("""
            SELECT DATE(verified_at) AS day, COUNT(*) AS total
            FROM verification_logs
            WHERE verified_at >= NOW() - INTERVAL '6 days'
            GROUP BY DATE(verified_at)
            ORDER BY DATE(verified_at)
        """).fetchall()

    weekly_counts = {}
    for row in weekly_rows:
        values = record(row)
        day_value = values.get('day')
        if day_value is None:
            continue
        day_key = day_value.isoformat() if hasattr(day_value, 'isoformat') else str(day_value)
        weekly_counts[day_key] = int(values.get('total') or 0)
    today = b.now().date()
    weekly = []
    for offset in range(6, -1, -1):
        day = today - timedelta(days=offset)
        weekly.append({
            'date': day.isoformat(),
            'label': day.strftime('%a'),
            'total': weekly_counts.get(day.isoformat(), 0)
        })

    return ok(
        total=total,
        students=total,
        active=active,
        inactive=total - active,
        checks=checks,
        verifications=checks,
        pending=pending,
        claimed=claimed,
        unclaimed=unclaimed,
        verifiers=verifiers,
        recent=[record(row) for row in recent],
        faculty_summary=[record(row) for row in faculty_rows],
        weekly_verifications=weekly
    )

@api.get('/catalogue')
def catalogue():
    return ok(faculties=list(b.FACULTY_DEPARTMENTS), departments=sorted(set((d for ds in b.FACULTY_DEPARTMENTS.values() for d in ds))), faculty_departments=b.FACULTY_DEPARTMENTS)

@api.get('/students')
@protected('admin')
def students():
    page = min(max(request.args.get('page', 1, type=int), 1), 100_000)
    q = request.args.get('q', '').strip()[:100]
    status = request.args.get('status', '').strip()
    if status and status not in ('Active', 'Inactive'):
        return err('Invalid status filter.')
    limit = 20
    offset = (page - 1) * limit
    with b.get_db() as db:
        filters = []
        params = []
        if q:
            pat = f'%{q}%'
            filters.append('(matric_no ILIKE ? OR full_name ILIKE ? OR department ILIKE ? OR faculty ILIKE ?)')
            params.extend([pat] * 4)
        if status:
            filters.append('status=?')
            params.append(status)
        where = ' WHERE ' + ' AND '.join(filters) if filters else ''
        total = db.execute('SELECT COUNT(*) FROM student_profiles' + where, tuple(params)).fetchone()[0]
        rows = db.execute('SELECT * FROM student_profiles' + where + ' ORDER BY id DESC LIMIT ? OFFSET ?', tuple(params) + (limit, offset)).fetchall()
    return ok(total=total, page=page, items=[public_student(x, f"/api/students/{x['id']}/photo") for x in rows])

@api.get('/students/<int:student_id>')
@protected('admin')
def student_detail(student_id):
    with b.get_db() as db:
        row = db.execute('SELECT * FROM student_profiles WHERE id=?', (student_id,)).fetchone()
    if not row:
        return err('Student not found.', 404)
    return ok(student=public_student(row, f'/api/students/{student_id}/photo'))

@api.post('/students/<int:student_id>/email')
@protected('admin')
def update_student_email(student_id):
    email = str(data().get('email') or '').strip().lower()
    if email and not b.valid_email(email):
        return err('Enter a valid email address or leave the field empty.')
    with b.get_db() as db:
        student = db.execute('SELECT id,email FROM students WHERE id=? FOR UPDATE', (student_id,)).fetchone()
        if not student:
            return err('Student not found.', 404)
        if email:
            lock_student_email(db, email)
            duplicate = db.execute(
                'SELECT id FROM students WHERE LOWER(email)=LOWER(?) AND id<>? LIMIT 1',
                (email, student_id)
            ).fetchone()
            if duplicate:
                return err('That email address is already associated with another student record.', 409)
        old_email = (student['email'] or '').strip().lower()
        new_email = email or None
        if old_email != (new_email or ''):
            db.execute(
                'UPDATE students SET email=?,email_verified_at=NULL WHERE id=?',
                (new_email, student_id)
            )
            db.execute(
                'UPDATE student_claim_challenges SET consumed_at=? WHERE student_id=? AND consumed_at IS NULL',
                (b.now(), student_id)
            )
            b.audit_admin_action(db, 'student.email_updated', 'student', student_id, 'Administrator updated a student contact email.')
            ensure_student_email_index(db)
    return ok(message='Student email address updated. Any previous uncompleted email-verification code has been invalidated.')


@api.post('/students')
@protected('admin')
def add_student():
    try:
        info = b.student_identity(data())
    except ValueError as e:
        return err(str(e))
    try:
        with b.get_db() as db:
            if info['email']:
                lock_student_email(db, info['email'])
                duplicate_email = db.execute('SELECT id FROM students WHERE LOWER(email)=LOWER(?) LIMIT 1', (info['email'],)).fetchone()
                if duplicate_email:
                    return err('That email address is already associated with another student record.', 409)
            student_id = b.insert_student(db, info, source='manual')
            ensure_student_email_index(db)
            b.audit_admin_action(db, 'student.created', 'student', student_id, 'Administrator created a student record.')
        return (ok(id=student_id, message='Student added.'), 201)
    except IntegrityError:
        return err('That matriculation number already exists.', 409)

@api.get('/students/import-template')
@protected('admin')
def import_template():
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['matric_no', 'first_name', 'middle_name', 'last_name', 'faculty', 'department', 'level', 'email', 'status'])
    writer.writerow(['DEMO/2026/000001', 'Ada', '', 'Example', 'Science', 'Computer Science', '400', '', 'Active'])
    return send_file(io.BytesIO(output.getvalue().encode('utf-8-sig')), mimetype='text/csv', as_attachment=True, download_name='studentverifi-import-template.csv')

@api.post('/students/import')
@protected('admin')
def import_students():
    file = request.files.get('file')
    if not file or not file.filename or (not file.filename.lower().endswith('.csv')):
        return err('Select a UTF-8 CSV file.')
    raw = file.stream.read(2 * 1024 * 1024 + 1)
    if len(raw) > 2 * 1024 * 1024:
        return err('CSV file exceeds the 2 MB limit.', 413)
    try:
        reader = csv.DictReader(io.StringIO(raw.decode('utf-8-sig')), strict=True)
        headings = {str(h).strip().lower() for h in reader.fieldnames or [] if h}
        if not {'matric_no', 'department', 'level'}.issubset(headings) or not ({'first_name', 'last_name'}.issubset(headings) or {'first_name', 'surname'}.issubset(headings) or 'full_name' in headings):
            return err('Missing CSV headings. Use the downloadable template.')
        items = []
        seen = set()
        seen_emails = set()
        errors = []
        for line, row in enumerate(reader, 2):
            if len(items) >= 5000:
                return err('Upload no more than 5,000 student records.')
            source = {str(k).strip().lower(): str(v or '').strip() for k, v in row.items() if k is not None}
            if not any(source.values()):
                continue
            try:
                rec = b.student_identity(source, legacy=True)
                if rec['matric_no'] in seen:
                    raise ValueError('Duplicate matriculation number in CSV.')
                seen.add(rec['matric_no'])
                if rec['email']:
                    if rec['email'] in seen_emails:
                        raise ValueError('Email address appears more than once; use a unique address for each student account claim.')
                    seen_emails.add(rec['email'])
                items.append(rec)
            except ValueError as exc:
                errors.append({'line': line, 'message': str(exc)})
        if errors:
            return err('CSV validation failed. No records were imported.', 422, details=errors[:50])
        if not items:
            return err('No usable student rows found.')
    except (UnicodeDecodeError, csv.Error, TypeError):
        return err('Could not read the CSV. Save it as UTF-8.')
    try:
        with b.get_db() as db:
            existing = db.execute('SELECT matric_no FROM students WHERE matric_no = ANY(:ids)', {'ids': [r['matric_no'] for r in items]}).fetchall()
            if existing:
                return err('Some matriculation numbers already exist. No rows imported.', 409, details=[{'line': 'database', 'message': r['matric_no']} for r in existing[:30]])
            emails = sorted({r['email'].lower() for r in items if r['email']})
            if emails:
                for email_value in emails:
                    lock_student_email(db, email_value)
                existing_emails = db.execute(
                    'SELECT email FROM students WHERE LOWER(email)=ANY(:emails)',
                    {'emails': [value.lower() for value in emails]}
                ).fetchall()
                if existing_emails:
                    return err('Some email addresses are already assigned to existing student records. Use a unique email for each claimable student.', 409)
            lookup = db.execute('SELECT f.id AS faculty_id,f.name AS faculty,\n                           d.id AS department_id,d.name AS department\n                           FROM faculties f JOIN departments d ON d.faculty_id=f.id').fetchall()
            ids = {(r['faculty'], r['department']): (r['faculty_id'], r['department_id']) for r in lookup}
            payload = []
            created = b.now()
            for r in items:
                fid, did = ids[r['faculty'], r['department']]
                payload.append({'matric': r['matric_no'], 'first': r['first_name'], 'middle': r['middle_name'], 'last': r['last_name'], 'faculty_id': fid, 'department_id': did, 'level': r['level'], 'email': r['email'], 'photo': r['photo_url'], 'token': None, 'status': r['status'], 'source': 'imported', 'created': created})
            db.execute_many('INSERT INTO students(matric_no,first_name,middle_name,last_name,faculty_id,\n                department_id,level,email,photo_url,token,status,record_source,created_at)\n                VALUES (:matric,:first,:middle,:last,:faculty_id,:department_id,:level,\n                        :email,:photo,:token,:status,:source,:created)', payload)
            b.audit_admin_action(db, 'student.bulk_imported', 'student_batch', None, f'Administrator imported {len(items)} student records.')
    except (IntegrityError, KeyError):
        return err('CSV could not be imported because of conflicting student data.', 409)
    return ok(message=f'Imported {len(items)} students.', count=len(items))

@api.post('/students/<int:student_id>/status')
@protected('admin')
def status(student_id):
    desired = data().get('status')
    if desired not in ('Active', 'Inactive'):
        return err('Select Active or Inactive.')
    with b.get_db() as db:
        row = db.execute('SELECT status FROM students WHERE id=?', (student_id,)).fetchone()
        if not row:
            return err('Student not found.', 404)
        db.execute('UPDATE students SET status=? WHERE id=?', (desired, student_id))
        b.audit_admin_action(db, 'student.status_changed', 'student', student_id, f'Administrator changed student status to {desired}.')
    return ok(message=f'Student status updated to {desired}.')

@api.post('/students/<int:student_id>/rotate-qr')
@protected('admin')
def rotate_qr(student_id):
    with b.get_db() as db:
        row = db.execute(
            'SELECT token, status, photo_blob_path, photo_url, account_claimed FROM student_profiles WHERE id=?',
            (student_id,)
        ).fetchone()
        if not row:
            return err('Student not found.', 404)
        if not row['account_claimed'] or not row['photo_blob_path']:
            return err('A QR credential is issued only after the student claims the account and completes the profile photograph.', 409)
        if row['status'] != 'Active':
            return err('Activate the student record before rotating its QR credential.', 409)
        db.execute('UPDATE students SET token=? WHERE id=?', (secrets.token_urlsafe(32), student_id))
        b.audit_admin_action(db, 'student.qr_rotated', 'student', student_id, 'Administrator rotated a QR credential.')
    return ok(message='Student QR credential rotated. Previous QR codes are no longer valid.')


@api.post('/students/<int:student_id>/claim-code')
@protected('admin')
def issue_claim(student_id):
    return err('Manual claim codes have been retired. Students now claim accounts by verifying the email address on their existing record.', 410)


@api.get('/students/<int:student_id>/qr.png')
@protected('admin')
def student_qr(student_id):
    with b.get_db() as db:
        student = db.execute(
            'SELECT token, status, photo_blob_path, photo_url, account_claimed FROM student_profiles WHERE id=?',
            (student_id,)
        ).fetchone()
    if not student:
        return err('Student not found.', 404)
    if not student['account_claimed'] or not student['token'] or not student['photo_blob_path']:
        return err('The student QR credential becomes available after account activation and profile-photo completion.', 409)
    if student['status'] != 'Active':
        return err('Inactive students cannot obtain a QR code.', 403)
    try:
        image = b.qr_image_for_token(credential_url(student['token']))
    except ValueError as error:
        return err(str(error), 503)
    return send_file(image, mimetype='image/png', as_attachment=request.args.get('download') == '1', download_name=f'student-{student_id}-qr.png')


@api.get('/students/<int:student_id>/photo')
@protected('admin')
def admin_student_photo(student_id):
    with b.get_db() as db:
        student = db.execute('SELECT photo_blob_path, photo_url FROM students WHERE id=?', (student_id,)).fetchone()
    if not student:
        return err('Student not found.', 404)
    try:
        return send_private_photo_response(student['photo_blob_path'])
    except PhotoStorageError as error:
        b.app.logger.warning('Administrator profile-photo retrieval failed: %s', error.reason)
        return err('The profile photograph is temporarily unavailable.', 503)


@api.get('/student/me')
@protected('student')
def student_account():
    with b.get_db() as db:
        student = db.execute('SELECT * FROM student_profiles WHERE id=?', (session['student_id'],)).fetchone()
    if not student:
        return err('Student record not found.', 404)
    return ok(student=public_student(student, '/api/student/my-photo'))


@api.get('/student/my-photo')
@protected('student')
def student_photo():
    with b.get_db() as db:
        student = db.execute('SELECT photo_blob_path, photo_url FROM students WHERE id=?', (session['student_id'],)).fetchone()
    if not student:
        return err('Student record not found.', 404)
    try:
        return send_private_photo_response(student['photo_blob_path'])
    except PhotoStorageError as error:
        b.app.logger.warning('Student profile-photo retrieval failed: %s', error.reason)
        return err('Your profile photograph is temporarily unavailable.', 503)


@api.post('/student/profile-photo')
@protected('student')
def update_student_photo():
    upload = request.files.get('photo')
    try:
        image_bytes = process_profile_photo(upload) if upload else None
        if image_bytes is None:
            return err('Choose a profile photograph before continuing.')
    except (ValueError, PhotoStorageError) as error:
        return err(str(error))

    student_id = session['student_id']
    try:
        new_path = upload_private_profile_photo(student_id, image_bytes)
    except PhotoStorageError as error:
        b.app.logger.warning('Student profile-photo upload failed: %s', error.reason)
        return err('Profile-photo storage is temporarily unavailable. Please try again.', 503)

    old_path = None
    try:
        with b.get_db() as db:
            student = db.execute('SELECT id, status, photo_blob_path FROM students WHERE id=? FOR UPDATE', (student_id,)).fetchone()
            if not student or student['status'] != 'Active':
                raise ValueError('Your student record is unavailable.')
            old_path = student['photo_blob_path']
            token = db.execute('SELECT token FROM students WHERE id=?', (student_id,)).fetchone()['token']
            token = token or secrets.token_urlsafe(32)
            db.execute('UPDATE students SET photo_blob_path=?, photo_url=NULL, token=? WHERE id=?', (new_path, token, student_id))
            b.audit_admin_action(db, 'student.profile_photo_updated', 'student', student_id, 'Student updated their profile photograph.')
        if old_path and old_path != new_path:
            delete_private_profile_photo(old_path)
        return ok(message='Your profile photograph has been saved. Your QR credential is now available.')
    except Exception as error:
        delete_private_profile_photo(new_path)
        if isinstance(error, ValueError):
            return err(str(error), 403)
        b.app.logger.exception('Student profile-photo update failed')
        return err('Your profile photograph could not be saved. Please try again.', 503)


@api.get('/student/my-qr.png')
@protected('student')
def own_qr():
    with b.get_db() as db:
        student = db.execute('SELECT token, status, photo_blob_path, photo_url FROM students WHERE id=?', (session['student_id'],)).fetchone()
    if not student:
        return err('Student record not found.', 404)
    if student['status'] != 'Active':
        return err('Inactive students cannot obtain a QR code.', 403)
    if not student['token'] or not student['photo_blob_path']:
        return err('Complete your profile photograph before accessing your QR credential.', 409)
    try:
        image = b.qr_image_for_token(credential_url(student['token']))
    except ValueError as error:
        return err(str(error), 503)
    return send_file(image, mimetype='image/png', as_attachment=request.args.get('download') == '1', download_name='my-student-qr.png')


@api.post('/claim/start')
def start_student_claim():
    """Start a private email-OTP claim for an existing, unclaimed student record."""
    if session.get('user_id'):
        return err('Sign out before claiming another account.', 409)
    session.pop('claim_student_id', None)
    session.pop('claim_challenge_id', None)
    session.pop('claim_verified_at', None)
    body = data()
    try:
        matric_no = b.validate_matric(body.get('matric_no', ''))
    except ValueError:
        matric_no = ''
    email = str(body.get('email') or '').strip().lower()
    generic_message = (
        'If these details match an eligible student record, a verification code has been sent to the email address on file.'
    )
    if not matric_no or not email or not b.valid_email(email):
        return err('Enter a valid matriculation number and email address.')
    if not email_delivery_is_configured():
        return err('Email verification is not configured yet. Please contact the system administrator.', 503)

    try:
        b.ensure_security_migrations()
        buckets = [
            b._rate_limit_hash('claim-start-matric', matric_no),
            b._rate_limit_hash('claim-start-ip', request.remote_addr or 'unknown'),
        ]
        challenge_id = None
        otp = None
        with b.get_db() as db:
            remaining = b._rate_limit_remaining(db, buckets)
            if remaining:
                reply, status = err('Please wait before requesting another verification code.', 429)
                reply.headers['Retry-After'] = str(remaining)
                return reply, status

            student = db.execute(
                'SELECT id, email, status, claimed_at FROM students WHERE matric_no=? FOR UPDATE',
                (matric_no,)
            ).fetchone()
            eligible = bool(
                student and student['status'] == 'Active' and
                student['email'] and student['email'].strip().lower() == email and
                not student['claimed_at']
            )
            if eligible:
                linked = db.execute(
                    "SELECT id FROM users WHERE student_id=? AND role='student' LIMIT 1",
                    (student['id'],)
                ).fetchone()
                email_count = db.execute(
                    'SELECT COUNT(*) FROM students WHERE LOWER(email)=LOWER(?)',
                    (email,)
                ).fetchone()[0]
                eligible = not linked and int(email_count or 0) == 1

            if not eligible:
                b._record_rate_limit_failure(db, buckets, limit=8, window_minutes=15, block_minutes=15)
                return ok(message=generic_message)

            recent_sends = db.execute(
                'SELECT COUNT(*) FROM student_claim_challenges WHERE student_id=? AND created_at>=?',
                (student['id'], b.now() - timedelta(hours=1))
            ).fetchone()[0]
            latest = db.execute(
                "SELECT last_sent_at FROM student_claim_challenges WHERE student_id=? AND consumed_at IS NULL ORDER BY id DESC LIMIT 1 FOR UPDATE",
                (student['id'],)
            ).fetchone()
            if latest and latest['last_sent_at'] > b.now() - timedelta(seconds=OTP_RESEND_SECONDS):
                reply, status = err(f'Please wait {OTP_RESEND_SECONDS} seconds before requesting another code.', 429)
                reply.headers['Retry-After'] = str(OTP_RESEND_SECONDS)
                return reply, status
            if int(recent_sends or 0) >= OTP_MAX_SENDS_PER_HOUR:
                reply, status = err('You have reached the verification-code limit. Try again in an hour.', 429)
                reply.headers['Retry-After'] = '3600'
                return reply, status

            db.execute(
                'UPDATE student_claim_challenges SET consumed_at=? WHERE student_id=? AND consumed_at IS NULL',
                (b.now(), student['id'])
            )
            otp = create_otp()
            expires = b.now() + timedelta(minutes=OTP_TTL_MINUTES)
            inserted = db.execute("""
                INSERT INTO student_claim_challenges
                    (student_id,email_snapshot,otp_hash,expires_at,attempts,last_sent_at,created_at)
                VALUES (?,?,?,?,0,?,?) RETURNING id
            """, (
                student['id'], email, 'pending', expires,
                b.now(), b.now()
            )).fetchone()
            challenge_id = inserted['id']
            db.execute(
                'UPDATE student_claim_challenges SET otp_hash=? WHERE id=?',
                (otp_digest(b.app.config['SECRET_KEY'], challenge_id, otp), challenge_id)
            )
            b._record_rate_limit_failure(db, buckets, limit=5, window_minutes=60, block_minutes=60)

        try:
            send_claim_otp(email, otp, challenge_id, os.environ.get('INSTITUTION_NAME', 'StudentVerifi'))
        except EmailDeliveryError:
            with b.get_db() as db:
                db.execute('UPDATE student_claim_challenges SET consumed_at=? WHERE id=?', (b.now(), challenge_id))
            b.app.logger.exception('Student claim OTP delivery through Nylas failed')
            return err('The verification email could not be sent. Please try again later or contact the administrator.', 503)
        return ok(message=generic_message)
    except SQLAlchemyError:
        b.app.logger.exception('Student claim start failed')
        return err('Account claiming is temporarily unavailable. Please try again shortly.', 503)


@api.post('/claim/verify')
def verify_student_claim_otp():
    if session.get('user_id'):
        return err('Sign out before claiming another account.', 409)
    body = data()
    try:
        matric_no = b.validate_matric(body.get('matric_no', ''))
    except ValueError:
        matric_no = ''
    otp = str(body.get('otp') or '').strip()
    if not matric_no or not otp:
        return err('Enter your matriculation number and the six-digit code.')

    try:
        b.ensure_security_migrations()
        buckets = [
            b._rate_limit_hash('claim-verify-matric', matric_no),
            b._rate_limit_hash('claim-verify-ip', request.remote_addr or 'unknown'),
        ]
        with b.get_db() as db:
            remaining = b._rate_limit_remaining(db, buckets)
            if remaining:
                reply, status = err('Too many verification attempts. Try again later.', 429)
                reply.headers['Retry-After'] = str(remaining)
                return reply, status

            student = db.execute(
                'SELECT id,email,status,claimed_at FROM students WHERE matric_no=? FOR UPDATE',
                (matric_no,)
            ).fetchone()
            challenge = None
            if student:
                challenge = db.execute("""
                    SELECT * FROM student_claim_challenges
                    WHERE student_id=? AND consumed_at IS NULL
                    ORDER BY id DESC LIMIT 1 FOR UPDATE
                """, (student['id'],)).fetchone()

            eligible = bool(
                student and challenge and student['status'] == 'Active' and
                not student['claimed_at'] and
                student['email'] and
                student['email'].strip().lower() == challenge['email_snapshot'].strip().lower() and
                challenge['expires_at'] > b.now() and
                challenge['attempts'] < OTP_MAX_ATTEMPTS and
                challenge['verified_at'] is None
            )
            if not eligible:
                b._record_rate_limit_failure(db, buckets, limit=OTP_MAX_ATTEMPTS, window_minutes=15, block_minutes=15)
                return err('The code is invalid or has expired. Request a new code and try again.', 400)

            valid = verify_otp(
                b.app.config['SECRET_KEY'],
                challenge['id'],
                otp,
                challenge['otp_hash']
            )
            if not valid:
                attempts = int(challenge['attempts']) + 1
                db.execute(
                    'UPDATE student_claim_challenges SET attempts=?, consumed_at=CASE WHEN ? >= ? THEN ? ELSE consumed_at END WHERE id=?',
                    (attempts, attempts, OTP_MAX_ATTEMPTS, b.now(), challenge['id'])
                )
                b._record_rate_limit_failure(db, buckets, limit=OTP_MAX_ATTEMPTS, window_minutes=15, block_minutes=15)
                return err('The code is invalid or has expired. Request a new code and try again.', 400)

            db.execute(
                'UPDATE student_claim_challenges SET verified_at=? WHERE id=?',
                (b.now(), challenge['id'])
            )
            b._clear_rate_limit_failures(db, buckets)
            claim_student_id = student['id']
            claim_challenge_id = challenge['id']

        session.pop('claim_student_id', None)
        session['claim_student_id'] = claim_student_id
        session['claim_challenge_id'] = claim_challenge_id
        session['claim_verified_at'] = b.now().isoformat()
        return ok(message='Email verified. Complete your profile photograph and password to activate your account.')
    except SQLAlchemyError:
        b.app.logger.exception('Student claim OTP verification failed')
        return err('Email verification is temporarily unavailable. Please try again.', 503)


@api.post('/claim/complete')
def complete_student_claim():
    if session.get('user_id'):
        return err('Sign out before claiming another account.', 409)
    student_id = session.get('claim_student_id')
    challenge_id = session.get('claim_challenge_id')
    if not student_id or not challenge_id or not session.get('claim_verified_at'):
        return err('Your verified claim session has expired. Start the account-claim process again.', 401)

    password = str(request.form.get('password') or '')
    confirm = str(request.form.get('confirm') or '')
    if len(password) < 12 or len(password) > 128 or password != confirm:
        return err('Choose a password of 12–128 characters and confirm it correctly.')

    try:
        b.ensure_security_migrations()
        with b.get_db() as db:
            eligible = db.execute("""
                SELECT s.id,s.matric_no,s.first_name,s.middle_name,s.last_name,s.email,s.status,
                    c.id AS challenge_id,c.verified_at,c.consumed_at,c.email_snapshot
                FROM students s
                JOIN student_claim_challenges c ON c.student_id=s.id
                WHERE s.id=? AND c.id=?
                FOR UPDATE OF s,c
            """, (student_id, challenge_id)).fetchone()
            if (not eligible or eligible['status'] != 'Active' or eligible['consumed_at'] or
                    not eligible['verified_at'] or eligible['verified_at'] < b.now() - timedelta(minutes=20) or
                    not eligible['email'] or eligible['email'].strip().lower() != eligible['email_snapshot'].strip().lower()):
                session.pop('claim_student_id', None)
                session.pop('claim_challenge_id', None)
                session.pop('claim_verified_at', None)
                return err('Your verified claim session has expired. Start again.', 401)
            existing = db.execute('SELECT id FROM users WHERE student_id=? OR username=? LIMIT 1',
                                   (student_id, eligible['matric_no'])).fetchone()
            if existing:
                return err('This student record already has an account. Please sign in.', 409)
    except SQLAlchemyError:
        b.app.logger.exception('Student claim preflight failed')
        return err('Account claiming is temporarily unavailable.', 503)

    photo_file = request.files.get('photo')
    try:
        image_bytes = process_profile_photo(photo_file) if photo_file else None
        if image_bytes is None:
            return err('A profile photograph is required before account activation.')
    except (ValueError, PhotoStorageError) as error:
        return err(str(error))

    try:
        photo_path = upload_private_profile_photo(student_id, image_bytes)
    except PhotoStorageError as error:
        b.app.logger.warning('Student claim photo upload failed: %s', error.reason)
        return err('Secure photo storage is not configured or is temporarily unavailable.', 503)

    try:
        with b.get_db() as db:
            student = db.execute(
                'SELECT id,matric_no,first_name,middle_name,last_name,email,status,claimed_at FROM students WHERE id=? FOR UPDATE',
                (student_id,)
            ).fetchone()
            challenge = db.execute(
                'SELECT * FROM student_claim_challenges WHERE id=? AND student_id=? FOR UPDATE',
                (challenge_id, student_id)
            ).fetchone()
            if (not student or student['status'] != 'Active' or student['claimed_at'] or
                    not challenge or challenge['consumed_at'] or not challenge['verified_at'] or
                    challenge['verified_at'] < b.now() - timedelta(minutes=CLAIM_COMPLETION_TTL_MINUTES) or
                    not student['email'] or student['email'].strip().lower() != challenge['email_snapshot'].strip().lower()):
                raise ValueError('Your verified claim session has expired. Start again.')
            existing = db.execute('SELECT id FROM users WHERE student_id=? OR username=? LIMIT 1',
                                   (student_id, student['matric_no'])).fetchone()
            if existing:
                raise ValueError('This student record already has an account. Please sign in.')

            username = student['matric_no']
            password_hash = generate_password_hash(password)
            db.execute("""
                INSERT INTO users(username,password_hash,role,student_id,created_at,display_name,is_active)
                VALUES (?,?,'student',?,?,?,TRUE)
            """, (
                username, password_hash, student_id, b.now(),
                ' '.join(v for v in (student['first_name'], student['middle_name'], student['last_name']) if v)
            ))
            token = secrets.token_urlsafe(32)
            db.execute("""
                UPDATE students SET photo_blob_path=?,photo_url=NULL,token=?,claimed_at=?,email_verified_at=?,claim_code_hash=NULL
                WHERE id=?
            """, (photo_path, token, b.now(), b.now(), student_id))
            db.execute('UPDATE student_claim_challenges SET consumed_at=? WHERE id=?', (b.now(), challenge_id))
            db.execute("""
                UPDATE student_account_requests
                SET status='Approved',password_hash='[REDACTED]',reviewed_at=?,reviewed_by=NULL
                WHERE student_id=? AND status='Pending'
            """, (b.now(), student_id))
            db.execute("""
                INSERT INTO admin_audit_logs(actor_user_id,action,target_type,target_id,summary,created_at)
                VALUES (NULL,'student.account_claimed','student',?,'Student completed email verification and profile claim.',?)
            """, (student_id, b.now()))
            user_id = db.execute('SELECT id FROM users WHERE username=?', (username,)).fetchone()['id']

        session.clear()
        session.permanent = True
        session.update(user_id=user_id, username=username, role='student', student_id=student_id)
        return ok(
            message='Your StudentVerifi account is active. Your QR credential has been generated.',
            user={'id': user_id, 'username': username, 'role': 'student', 'student_id': student_id},
            csrf_token=generate_csrf()
        )
    except ValueError as error:
        delete_private_profile_photo(photo_path)
        return err(str(error), 409)
    except IntegrityError:
        delete_private_profile_photo(photo_path)
        return err('This student record already has an account. Please sign in.', 409)
    except SQLAlchemyError:
        delete_private_profile_photo(photo_path)
        b.app.logger.exception('Student account activation failed')
        return err('Your account could not be activated. Please try again.', 503)


@api.post('/register')
def register_student():
    return err('The old approval-based registration form has been retired. Use the email-verified student account-claim process.', 410)


@api.get('/verifiers')
@protected('admin')
def list_verifiers():
    with b.get_db() as db:
        rows = db.execute("""
            SELECT u.id,u.email,u.display_name,u.is_active,u.created_at,u.last_login_at,
                (SELECT i.created_at FROM verifier_invitations i
                    WHERE i.user_id=u.id ORDER BY i.id DESC LIMIT 1) AS invited_at,
                (SELECT i.used_at FROM verifier_invitations i
                    WHERE i.user_id=u.id ORDER BY i.id DESC LIMIT 1) AS accepted_at
            FROM users u
            WHERE u.role='verifier'
            ORDER BY u.created_at DESC,u.id DESC
        """).fetchall()
    return ok(items=[record(row) for row in rows])


@api.post('/verifiers')
@protected('admin')
def create_verifier():
    body = data()
    email = str(body.get('email') or '').strip().lower()
    display_name = str(body.get('display_name') or '').strip()[:160]
    if not b.valid_email(email) or not email or not display_name:
        return err('Provide the verifier’s name and a valid email address.')
    token = secrets.token_urlsafe(32)
    try:
        invitation_url = verifier_invitation_url(token)
    except ValueError as error:
        return err(str(error), 503)
    token_hash = hashlib.sha256(token.encode('utf-8')).hexdigest()
    username = 'verifier_' + secrets.token_hex(8)
    try:
        with b.get_db() as db:
            existing = db.execute('SELECT id FROM users WHERE LOWER(email)=LOWER(?) LIMIT 1', (email,)).fetchone()
            if existing:
                return err('An account already uses this email address.', 409)
            inserted = db.execute("""
                INSERT INTO users(username,password_hash,role,student_id,created_at,email,display_name,is_active)
                VALUES (?,?,'verifier',NULL,?,?,?,FALSE) RETURNING id
            """, (
                username, generate_password_hash(secrets.token_urlsafe(48)),
                b.now(), email, display_name
            )).fetchone()
            user_id = inserted['id']
            invite = db.execute("""
                INSERT INTO verifier_invitations(user_id,token_hash,expires_at,created_at)
                VALUES (?,?,?,?) RETURNING id
            """, (user_id, token_hash, b.now() + timedelta(hours=48), b.now())).fetchone()
            invitation_id = invite['id']
            b.audit_admin_action(db, 'verifier.invited', 'user', user_id, 'Administrator invited a verifier.')
        try:
            send_verifier_invitation(email, display_name, invitation_url, invitation_id)
        except EmailDeliveryError:
            b.app.logger.exception('Verifier invitation email through Nylas failed')
            return err('The verifier account was created, but its invitation email could not be delivered. Use the invitation resend action to try again.', 503, verifier_id=user_id)
        return ok(id=user_id, message='Verifier invitation sent. The account becomes active after the invitation is accepted.'), 201
    except IntegrityError:
        return err('A verifier account already uses this email address.', 409)
    except SQLAlchemyError:
        b.app.logger.exception('Verifier invitation creation failed')
        return err('The verifier invitation could not be created.', 503)


@api.post('/verifiers/<int:user_id>/invite')
@protected('admin')
def resend_verifier_invitation(user_id):
    token = secrets.token_urlsafe(32)
    try:
        invitation_url = verifier_invitation_url(token)
    except ValueError as error:
        return err(str(error), 503)
    token_hash = hashlib.sha256(token.encode('utf-8')).hexdigest()
    with b.get_db() as db:
        user = db.execute(
            "SELECT id,email,display_name,is_active FROM users WHERE id=? AND role='verifier'",
            (user_id,)
        ).fetchone()
        if not user:
            return err('Verifier account not found.', 404)
        if user['is_active']:
            return err('This verifier has already accepted the invitation.', 409)
        db.execute('UPDATE verifier_invitations SET used_at=? WHERE user_id=? AND used_at IS NULL', (b.now(), user_id))
        invite = db.execute("""
            INSERT INTO verifier_invitations(user_id,token_hash,expires_at,created_at)
            VALUES (?,?,?,?) RETURNING id
        """, (user_id, token_hash, b.now() + timedelta(hours=48), b.now())).fetchone()
        invitation_id = invite['id']
        b.audit_admin_action(db, 'verifier.invitation_resent', 'user', user_id, 'Administrator resent a verifier invitation.')
    try:
        send_verifier_invitation(
            user['email'], user['display_name'], invitation_url, invitation_id
        )
    except EmailDeliveryError:
        b.app.logger.exception('Verifier invitation resend through Nylas failed')
        return err('The invitation email could not be delivered. Check the email provider configuration.', 503)
    return ok(message='A new verifier invitation has been sent.')


@api.post('/verifiers/<int:user_id>/status')
@protected('admin')
def set_verifier_status(user_id):
    desired = data().get('is_active')
    if not isinstance(desired, bool):
        return err('Choose whether this verifier account should be active or suspended.')
    with b.get_db() as db:
        user = db.execute(
            "SELECT id,is_active FROM users WHERE id=? AND role='verifier' FOR UPDATE",
            (user_id,)
        ).fetchone()
        if not user:
            return err('Verifier account not found.', 404)
        db.execute('UPDATE users SET is_active=? WHERE id=?', (desired, user_id))
        b.audit_admin_action(
            db,
            'verifier.' + ('activated' if desired else 'suspended'),
            'user', user_id,
            'Administrator changed verifier access status.'
        )
    return ok(message='Verifier access ' + ('activated.' if desired else 'suspended.'))


@api.post('/verifier-invitations/accept')
def accept_verifier_invitation():
    if session.get('user_id'):
        return err('Sign out before accepting a verifier invitation.', 409)
    body = data()
    token = str(body.get('token') or '').strip()
    password = str(body.get('password') or '')
    confirm = str(body.get('confirm') or '')
    if len(token) < 32 or len(token) > 128:
        return err('This invitation link is invalid or has expired.', 400)
    if len(password) < 12 or len(password) > 128 or password != confirm:
        return err('Choose a password of 12–128 characters and confirm it correctly.')
    token_hash = hashlib.sha256(token.encode('utf-8')).hexdigest()
    try:
        with b.get_db() as db:
            invitation = db.execute("""
                SELECT i.id AS invitation_id,i.expires_at,i.used_at,
                    u.id,u.username,u.email,u.display_name,u.role,u.is_active
                FROM verifier_invitations i
                JOIN users u ON u.id=i.user_id
                WHERE i.token_hash=?
                FOR UPDATE OF i,u
            """, (token_hash,)).fetchone()
            if (not invitation or invitation['role'] != 'verifier' or invitation['used_at'] or
                    invitation['expires_at'] <= b.now() or invitation['is_active']):
                return err('This invitation link is invalid, expired or already used.', 400)
            db.execute(
                'UPDATE users SET password_hash=?,is_active=TRUE WHERE id=?',
                (generate_password_hash(password), invitation['id'])
            )
            db.execute('UPDATE verifier_invitations SET used_at=? WHERE id=?', (b.now(), invitation['invitation_id']))
            db.execute("""
                INSERT INTO admin_audit_logs(actor_user_id,action,target_type,target_id,summary,created_at)
                VALUES (NULL,'verifier.invitation_accepted','user',?,'Verifier accepted an invitation.',?)
            """, (invitation['id'], b.now()))
            safe_user = {
                'id': invitation['id'],
                'username': invitation['username'],
                'email': invitation['email'],
                'display_name': invitation['display_name'],
                'role': 'verifier',
                'student_id': None,
            }
        session.clear()
        session.permanent = True
        session.update(user_id=safe_user['id'], username=safe_user['username'], role='verifier', student_id=None)
        return ok(message='Your verifier account is active.', user=safe_user, csrf_token=generate_csrf())
    except SQLAlchemyError:
        b.app.logger.exception('Verifier invitation acceptance failed')
        return err('The verifier invitation could not be accepted. Please try again.', 503)


@api.get('/verifier/activity')
@protected('verifier')
def verifier_activity():
    with b.get_db() as db:
        rows = db.execute("""
            SELECT l.id,l.result,l.verified_at,l.channel,s.matric_no,s.full_name AS student_name,
                s.department,COALESCE(u.display_name,u.username,'Verifier') AS verified_by_name
            FROM verification_logs l
            LEFT JOIN student_profiles s ON s.id=l.student_id
            LEFT JOIN users u ON u.id=l.verified_by
            WHERE l.verified_by=?
            ORDER BY l.id DESC LIMIT 250
        """, (session['user_id'],)).fetchall()
    return ok(items=[record(row) for row in rows])


@api.get('/verification/students/<int:student_id>/photo')
@protected(('admin', 'verifier'))
def verifier_student_photo(student_id):
    with b.get_db() as db:
        student = db.execute('SELECT photo_blob_path,photo_url FROM students WHERE id=?', (student_id,)).fetchone()
    if not student:
        return err('Student not found.', 404)
    try:
        return send_private_photo_response(student['photo_blob_path'])
    except PhotoStorageError as error:
        b.app.logger.warning('Verifier profile-photo retrieval failed: %s', error.reason)
        return err('The profile photograph is temporarily unavailable.', 503)


@api.post('/public/verify')
def public_verify_credential():
    raw_value = str(data().get('token') or '').strip()
    token = extract_qr_token(raw_value)
    fingerprint = hashlib.sha256(raw_value[:2048].encode('utf-8', 'replace')).hexdigest()
    bucket = b._rate_limit_hash('public-verification-ip', request.remote_addr or 'unknown')
    try:
        b.ensure_security_migrations()
        with b.get_db() as db:
            remaining = b._rate_limit_remaining(db, [bucket])
            if remaining:
                reply, status = err('Too many public verification attempts. Try again later.', 429)
                reply.headers['Retry-After'] = str(remaining)
                return reply, status
            b._record_rate_limit_failure(db, [bucket], limit=120, window_minutes=15, block_minutes=15)
            student = db.execute('SELECT * FROM student_profiles WHERE token=?', (token,)).fetchone() if token else None
            if not student:
                outcome = 'INVALID'
            elif student['status'] != 'Active':
                outcome = 'INACTIVE'
            elif not student['photo_blob_path']:
                outcome = 'INCOMPLETE'
            else:
                outcome = 'VALID'
            db.execute("""
                INSERT INTO verification_logs(student_id,scanned_token,token_fingerprint,result,verified_by,verified_at,channel)
                VALUES (?,'[REDACTED]',?, ?,NULL,?,'public')
            """, (student['id'] if student else None, fingerprint, outcome, b.now()))

        messages = {
            'VALID': 'The credential matches an active student record.',
            'INACTIVE': 'A student record was found, but it is not currently active.',
            'INCOMPLETE': 'A student record was found, but the profile photograph is not complete. Contact the institution for assistance.',
            'INVALID': 'This QR credential could not be matched to a current student record.',
        }
        public_record = None
        if student and outcome != 'INVALID':
            matric = str(student['matric_no'] or '')
            photo_data = None
            if student['photo_blob_path']:
                photo_bytes = read_private_profile_photo(student['photo_blob_path'])
                if not photo_bytes:
                    return err('The student photograph is temporarily unavailable.', 503)
                photo_data = 'data:image/jpeg;base64,' + base64.b64encode(photo_bytes).decode('ascii')
            public_record = {
                'name': student['full_name'],
                'matric_no_masked': ('••••' + matric[-4:]) if len(matric) > 4 else '••••',
                'institution': os.environ.get('INSTITUTION_NAME', 'Ebonyi State University'),
                'status': student['status'],
                'photo_data': photo_data,
            }
        return ok(outcome=outcome, message=messages[outcome], student=public_record)
    except PhotoStorageError as error:
        b.app.logger.warning('Public credential photo retrieval failed: %s', error.reason)
        return err('Public verification is temporarily unavailable.', 503)
    except SQLAlchemyError:
        b.app.logger.exception('Public credential verification failed')
        return err('Public verification is temporarily unavailable.', 503)


@api.get('/registration-requests')
@protected('admin')
def requests_list():
    """Return pending and completed account requests without exposing secrets."""
    with b.get_db() as db:
        rows = db.execute("""
            SELECT
                r.id,
                r.requested_at,
                r.status,
                r.claim_code_verified,
                r.reviewed_at,
                r.reviewed_by,
                CASE WHEN r.reviewed_by IS NULL AND r.status='Approved' THEN 'Student self-service' ELSE COALESCE(reviewer.display_name,reviewer.username,'System') END AS reviewed_by_name,
                s.matric_no,
                s.full_name AS name,
                s.faculty,
                s.department,
                s.level
            FROM student_account_requests r
            JOIN student_profiles s ON s.id = r.student_id
            LEFT JOIN users reviewer ON reviewer.id = r.reviewed_by
            ORDER BY r.requested_at DESC, r.id DESC
        """).fetchall()
    return ok(items=[record(row) for row in rows])

@api.post('/registration-requests/<int:rid>/<string:decision>')
@protected('admin')
def review_request(rid, decision):
    if decision not in ('approve', 'reject'):
        return err('Invalid action.', 404)
    with b.get_db() as db:
        row = db.execute('SELECT * FROM student_account_requests WHERE id=? FOR UPDATE', (rid,)).fetchone()
        if not row:
            return err('Request not found.', 404)
        if row['status'] != 'Pending':
            return err('This request was already reviewed.', 409)
        student = db.execute('SELECT * FROM student_profiles WHERE id=?', (row['student_id'],)).fetchone()
        if decision == 'approve' and (not row['claim_code_verified']):
            return err('Unverified legacy claims cannot be approved.', 403)
        if decision == 'approve' and (not student or student['status'] != 'Active'):
            return err('Only active students can be approved.', 403)
        status = 'Rejected'
        if decision == 'approve' and student:
            exists = db.execute('SELECT id FROM users WHERE username=?', (student['matric_no'],)).fetchone()
            if not exists:
                db.execute("INSERT INTO users(username,password_hash,role,student_id,created_at) VALUES (?,?,'student',?,?)", (student['matric_no'], row['password_hash'], student['id'], b.now()))
                db.execute('UPDATE students SET claimed_at=?,claim_code_hash=NULL WHERE id=?', (b.now(), student['id']))
                status = 'Approved'
        db.execute("UPDATE student_account_requests SET status=?,password_hash='[REDACTED]',reviewed_at=?,reviewed_by=? WHERE id=?", (status, b.now(), session['user_id'], rid))
        b.audit_admin_action(db, 'student_account_request.' + status.lower(), 'student', row['student_id'], 'Administrator reviewed a student account request.')
    return ok(message='Request approved.' if status == 'Approved' else 'Request rejected.')

@api.post('/verify')
@protected(('admin', 'verifier'))
def verify():
    raw_value = str(data().get('token') or '').strip()
    token = extract_qr_token(raw_value)
    if not raw_value:
        return err('Please scan a QR code or enter a code.')
    fingerprint = hashlib.sha256(raw_value[:2048].encode('utf-8', 'replace')).hexdigest()
    with b.get_db() as db:
        student = db.execute('SELECT * FROM student_profiles WHERE token=?', (token,)).fetchone() if token else None
        if not student:
            outcome = 'INVALID'
        elif student['status'] != 'Active':
            outcome = 'INACTIVE'
        elif not student['photo_blob_path']:
            outcome = 'INCOMPLETE'
        else:
            outcome = 'VALID'
        channel = 'admin' if session.get('role') == 'admin' else 'verifier'
        db.execute("""
            INSERT INTO verification_logs(student_id,scanned_token,token_fingerprint,result,verified_by,verified_at,channel)
            VALUES (?,'[REDACTED]',?,?,?, ?,?)
        """, (student['id'] if student else None, fingerprint, outcome, session['user_id'], b.now(), channel))

    message = {
        'VALID': 'The credential matches an active student record. Compare the photograph with the person presenting it.',
        'INACTIVE': 'A student record was found, but it is not currently active.',
        'INCOMPLETE': 'A student record was found, but it does not have a current private profile photograph. Ask the student to upload one before verification.',
        'INVALID': 'No matching student credential was found.',
    }[outcome]
    verified = None
    if student and outcome != 'INVALID':
        verified = {
            'id': student['id'],
            'name': student['full_name'],
            'matric_no': student['matric_no'],
            'faculty': student['faculty'],
            'department': student['department'],
            'level': student['level'],
            'photo_url': f"/api/verification/students/{student['id']}/photo" if student['photo_blob_path'] else None,
            'status': student['status'],
        }
    return ok(outcome=outcome, message=message, student=verified)


@api.get('/logs')
@protected('admin')
def logs():
    """Return redacted verification activity for administrator review."""
    with b.get_db() as db:
        rows = db.execute("""
            SELECT
                l.id,
                l.result,
                l.channel,
                l.verified_at,
                s.matric_no,
                s.full_name AS student_name,
                s.department,
                COALESCE(u.display_name,u.username,'Public visitor') AS verified_by_name
            FROM verification_logs l
            LEFT JOIN student_profiles s ON s.id = l.student_id
            LEFT JOIN users u ON u.id = l.verified_by
            ORDER BY l.id DESC
            LIMIT 250
        """).fetchall()
    return ok(items=[record(row) for row in rows])


@api.get('/admin-audit')
@protected('admin')
def audit():
    with b.get_db() as db:
        rows = db.execute("""SELECT a.id,a.action AS event,a.target_type,a.target_id,a.summary AS details,a.created_at,
                     CASE WHEN a.action='student.account_claimed' THEN 'Student self-service'
                          WHEN a.action='verifier.invitation_accepted' THEN 'Verifier self-service'
                          ELSE COALESCE(u.display_name,u.username,'System') END AS actor
                     FROM admin_audit_logs a LEFT JOIN users u ON u.id=a.actor_user_id
                     ORDER BY a.id DESC LIMIT 250""").fetchall()
    return ok(items=[record(x) for x in rows])
_DEMO_RE = '^DEMO/2026/[0-9]{6}$'

@api.get('/students/demo-cleanup')
@protected('admin')
def demo_preview():
    with b.get_db() as db:
        count = db.execute('SELECT COUNT(*) FROM students WHERE matric_no ~ ?', (_DEMO_RE,)).fetchone()[0]
    return ok(count=count)

@api.post('/students/demo-cleanup')
@protected('admin')
def demo_delete():
    if data().get('confirmation') != 'DELETE DEMO RECORDS':
        return err('Enter DELETE DEMO RECORDS to confirm.')
    with b.get_db() as db:
        ids = [r['id'] for r in db.execute('SELECT id FROM students WHERE matric_no ~ ?', (_DEMO_RE,)).fetchall()]
        if not ids:
            return ok(message='No matching demo records found.', count=0)
        db.execute('DELETE FROM users WHERE student_id=ANY(:ids)', {'ids': ids})
        db.execute('DELETE FROM students WHERE id=ANY(:ids)', {'ids': ids})
        b.audit_admin_action(db, 'student.synthetic_data_deleted', 'student_batch', None, f'Administrator deleted {len(ids)} demo records.')
    return ok(message=f'Deleted {len(ids)} synthetic demo records.', count=len(ids))
