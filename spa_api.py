"""StudentVerifi JSON API. Reuses the production-hardened database services."""
import csv
import hashlib
import io
import re
import secrets
from functools import wraps
from pathlib import Path
from flask import Blueprint, jsonify, request, send_file, send_from_directory, session
from flask_wtf.csrf import CSRFError, generate_csrf
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from werkzeug.security import check_password_hash, generate_password_hash
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
    client_routes = {'/', '/login', '/register', '/dashboard', '/students', '/students/new', '/students/import', '/students/demo-cleanup', '/verify', '/registration-requests', '/logs', '/admin-audit', '/account/password', '/student/account', '/how-it-works', '/about', '/faq', '/privacy', '/contact'}

    @app.before_request
    def react_routes():
        if request.method not in ('GET', 'HEAD'):
            return None
        path = request.path
        if path in ('/favicon.svg', '/logo.svg'):
            return send_from_directory(root, path[1:])
        if path.startswith('/assets/'):
            return send_from_directory(root / 'assets', path[len('/assets/'):])
        if path in client_routes or re.fullmatch('/students/[0-9]+', path):
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

def public_student(student):
    if not student:
        return None
    s = record(student)
    safe = {k: s.get(k) for k in ('id', 'matric_no', 'first_name', 'middle_name', 'last_name', 'faculty', 'department', 'level', 'email', 'photo_url', 'status', 'record_source', 'created_at')}
    safe['name'] = ' '.join((v for v in (s.get('first_name'), s.get('middle_name'), s.get('last_name')) if v))
    return safe

def protected(role=None):

    def decorator(view):

        @wraps(view)
        def inner(*args, **kwargs):
            uid = session.get('user_id')
            if not uid:
                return err('Please sign in to continue.', 401)
            if role and session.get('role') != role:
                return err('You are not authorised to perform this action.', 403)
            try:
                b.ensure_security_migrations()
                with b.get_db() as db:
                    user = db.execute('SELECT id, role, student_id FROM users WHERE id=?', (uid,)).fetchone()
                    if not user or user['role'] != session.get('role'):
                        session.clear()
                        return err('Your session has expired. Please sign in again.', 401)
                    if user['role'] == 'student':
                        linked = db.execute('SELECT status FROM students WHERE id=?', (user['student_id'],)).fetchone()
                        if not linked or linked['status'] != 'Active':
                            session.clear()
                            return err('Your student account is unavailable.', 403)
            except SQLAlchemyError:
                b.app.logger.exception('API authorisation unavailable')
                return err('Authentication service temporarily unavailable.', 503)
            return view(*args, **kwargs)
        return inner
    return decorator

def safe_page():
    try:
        return max(1, min(100000, int(request.args.get('page', '1'))))
    except ValueError:
        return 1

@api.get('/session')
def current_session():
    user = None
    if session.get('user_id'):
        try:
            b.ensure_security_migrations()
            with b.get_db() as db:
                r = db.execute('SELECT id, username, role, student_id FROM users WHERE id=?', (session['user_id'],)).fetchone()
                if r and r['role'] == session.get('role'):
                    user = record(r)
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
    if not username or not password or len(username) > 100 or (len(password) > 128):
        return err('Invalid username or password.', 401)
    try:
        b.ensure_security_migrations()
        buckets = b._login_rate_limit_buckets(username)
        with b.get_db() as db:
            remaining = b._rate_limit_remaining(db, buckets)
            if remaining:
                reply, status = err('Too many sign-in attempts. Try again later.', 429)
                reply.headers['Retry-After'] = str(remaining)
                return (reply, status)
            user = db.execute('SELECT * FROM users WHERE username=?', (username,)).fetchone()
            valid = False
            if user:
                try:
                    valid = check_password_hash(user['password_hash'], password)
                except (ValueError, TypeError):
                    pass
                if valid and user['role'] == 'student':
                    s = db.execute('SELECT status FROM students WHERE id=?', (user['student_id'],)).fetchone()
                    valid = bool(s and s['status'] == 'Active')
            if not valid:
                b._record_rate_limit_failure(db, buckets)
                return err('Invalid username or password.', 401)
            b._clear_rate_limit_failures(db, buckets)
            session.clear()
            session.permanent = True
            session.update(user_id=user['id'], username=user['username'], role=user['role'], student_id=user['student_id'])
            safe = {'id': user['id'], 'username': user['username'], 'role': user['role'], 'student_id': user['student_id']}
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
        recent = db.execute('SELECT l.id,l.result,l.verified_at,s.matric_no,s.full_name\n            FROM verification_logs l LEFT JOIN student_profiles s ON s.id=l.student_id\n            ORDER BY l.id DESC LIMIT 8').fetchall()
    return ok(total=total, students=total, active=active, inactive=total - active, checks=checks, verifications=checks, pending=pending, recent=[record(x) for x in recent])

@api.get('/catalogue')
def catalogue():
    return ok(faculties=list(b.FACULTY_DEPARTMENTS), departments=sorted(set((d for ds in b.FACULTY_DEPARTMENTS.values() for d in ds))), faculty_departments=b.FACULTY_DEPARTMENTS)

@api.get('/students')
@protected('admin')
def students():
    page = safe_page()
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
    return ok(total=total, page=page, items=[public_student(x) for x in rows])

@api.get('/students/<int:student_id>')
@protected('admin')
def student_detail(student_id):
    with b.get_db() as db:
        row = db.execute('SELECT * FROM student_profiles WHERE id=?', (student_id,)).fetchone()
    if not row:
        return err('Student not found.', 404)
    return ok(student=public_student(row))

@api.post('/students')
@protected('admin')
def add_student():
    try:
        info = b.student_identity(data())
    except ValueError as e:
        return err(str(e))
    try:
        with b.get_db() as db:
            student_id = b.insert_student(db, info, source='manual')
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
            lookup = db.execute('SELECT f.id AS faculty_id,f.name AS faculty,\n                           d.id AS department_id,d.name AS department\n                           FROM faculties f JOIN departments d ON d.faculty_id=f.id').fetchall()
            ids = {(r['faculty'], r['department']): (r['faculty_id'], r['department_id']) for r in lookup}
            payload = []
            created = b.now()
            for r in items:
                fid, did = ids[r['faculty'], r['department']]
                payload.append({'matric': r['matric_no'], 'first': r['first_name'], 'middle': r['middle_name'], 'last': r['last_name'], 'faculty_id': fid, 'department_id': did, 'level': r['level'], 'email': r['email'], 'photo': r['photo_url'], 'token': secrets.token_urlsafe(32), 'status': r['status'], 'source': 'imported', 'created': created})
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
        row = db.execute('SELECT id FROM students WHERE id=?', (student_id,)).fetchone()
        if not row:
            return err('Student not found.', 404)
        db.execute('UPDATE students SET token=? WHERE id=?', (secrets.token_urlsafe(32), student_id))
        b.audit_admin_action(db, 'student.qr_rotated', 'student', student_id, 'Administrator rotated a QR credential.')
    return ok(message='QR credential rotated. The old code is now invalid.')

@api.post('/students/<int:student_id>/claim-code')
@protected('admin')
def issue_claim(student_id):
    with b.get_db() as db:
        student = db.execute('SELECT id,status FROM students WHERE id=?', (student_id,)).fetchone()
        if not student:
            return err('Student not found.', 404)
        if student['status'] != 'Active':
            return err('Activate the student before issuing a claim code.', 409)
        existing = db.execute('SELECT id FROM users WHERE student_id=?', (student_id,)).fetchone()
        if existing:
            return err('The student already has an account.', 409)
        code = secrets.token_urlsafe(24)
        db.execute('UPDATE students SET claim_code_hash=? WHERE id=?', (generate_password_hash(code), student_id))
        b.audit_admin_action(db, 'student.claim_code_issued', 'student', student_id, 'Administrator issued a private one-time claim code.')
    return ok(code=code, message='Private claim code issued. Share it securely.')

@api.get('/students/<int:student_id>/qr.png')
@protected('admin')
def student_qr(student_id):
    with b.get_db() as db:
        s = db.execute('SELECT token FROM students WHERE id=?', (student_id,)).fetchone()
    if not s:
        return err('Student not found.', 404)
    return send_file(b.qr_image_for_token(s['token']), mimetype='image/png', as_attachment=request.args.get('download') == '1', download_name=f'student-{student_id}-qr.png')

@api.get('/student/me')
@protected('student')
def student_account():
    with b.get_db() as db:
        student = db.execute('SELECT * FROM student_profiles WHERE id=?', (session['student_id'],)).fetchone()
    if not student:
        return err('Student record not found.', 404)
    return ok(student=public_student(student))

@api.get('/student/my-qr.png')
@protected('student')
def own_qr():
    with b.get_db() as db:
        s = db.execute('SELECT token,status FROM students WHERE id=?', (session['student_id'],)).fetchone()
    if not s:
        return err('Student record not found.', 404)
    if s['status'] != 'Active':
        return err('Inactive students cannot obtain a QR code.', 403)
    return send_file(b.qr_image_for_token(s['token']), mimetype='image/png', as_attachment=request.args.get('download') == '1', download_name='my-student-qr.png')

@api.post('/register')
def register_student():
    body = data()
    try:
        identity = b.student_identity(body)
    except ValueError as e:
        return err(str(e))
    password = str(body.get('password') or '')
    if len(password) < 10 or len(password) > 128 or password != body.get('confirm'):
        return err('Password must be 10–128 characters and match confirmation.')
    code = str(body.get('claim_code') or '').strip()
    if not code or len(code) > 128:
        return err('Enter your one-time claim code.')
    with b.get_db() as db:
        student = db.execute('SELECT * FROM student_profiles WHERE matric_no=?', (identity['matric_no'],)).fetchone()
        matches = student and student['status'] == 'Active' and (student['first_name'].casefold() == identity['first_name'].casefold()) and ((student['middle_name'] or '').casefold() == identity['middle_name'].casefold()) and (student['last_name'].casefold() == identity['last_name'].casefold()) and (student['faculty'] == identity['faculty']) and (student['department'] == identity['department']) and (student['level'].casefold() == identity['level'].casefold())
        if not matches:
            return err('Registration details do not match an active record. Contact your administrator.', 403)
        if db.execute('SELECT id FROM users WHERE username=?', (identity['matric_no'],)).fetchone():
            return err('An account already exists. Please sign in.', 409)
        if db.execute("SELECT id FROM student_account_requests WHERE student_id=? AND status='Pending'", (student['id'],)).fetchone():
            return err('A registration request is already pending.', 409)
        if not student['claim_code_hash'] or not check_password_hash(student['claim_code_hash'], code):
            return err('The claim code is invalid or has expired.', 403)
        db.execute("INSERT INTO student_account_requests\n                  (student_id,password_hash,claim_code_verified,status,requested_at)\n                  VALUES (?,?,TRUE,'Pending',?)", (student['id'], generate_password_hash(password), b.now()))
        db.execute('UPDATE students SET claim_code_hash=NULL WHERE id=?', (student['id'],))
    return ok(message='Account request submitted. An administrator will review it.')

@api.get('/registration-requests')
@protected('admin')
def requests_list():
    with b.get_db() as db:
        rows = db.execute("SELECT r.id,r.requested_at,r.status,r.claim_code_verified,\n                         s.matric_no,s.full_name AS name,s.department\n                         FROM student_account_requests r JOIN student_profiles s ON s.id=r.student_id\n                         WHERE r.status='Pending' ORDER BY r.id ASC").fetchall()
    return ok(items=[record(r) for r in rows])

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
        db.execute('UPDATE student_account_requests SET status=?,reviewed_at=?,reviewed_by=? WHERE id=?', (status, b.now(), session['user_id'], rid))
        b.audit_admin_action(db, 'student_account_request.' + status.lower(), 'student', row['student_id'], 'Administrator reviewed a student account request.')
    return ok(message='Request approved.' if status == 'Approved' else 'Request rejected.')

@api.post('/verify')
@protected('admin')
def verify():
    token = str(data().get('token') or '').strip()
    if not token:
        return err('Please scan a QR code or enter a code.')
    fingerprint = hashlib.sha256(token[:512].encode('utf-8', 'replace')).hexdigest()
    with b.get_db() as db:
        s = db.execute('SELECT * FROM student_profiles WHERE token=?', (token,)).fetchone() if len(token) <= 128 else None
        result = 'VALID' if s and s['status'] == 'Active' else 'INACTIVE' if s else 'INVALID'
        db.execute("INSERT INTO verification_logs(student_id,scanned_token,token_fingerprint,result,verified_by,verified_at)\n                     VALUES (?,'[REDACTED]',?,?,?,?)", (s['id'] if s else None, fingerprint, result, session['user_id'], b.now()))
    message = {'VALID': 'The stored student record is active.', 'INACTIVE': 'This record is inactive. Contact the administrator.', 'INVALID': 'No matching active credential was found.'}[result]
    verified = public_student(s)
    if verified:
        verified = {key: verified.get(key) for key in (
            'id', 'name', 'matric_no', 'faculty', 'department',
            'level', 'photo_url', 'status'
        )}
    return ok(outcome=result, message=message, student=verified)

@api.get('/logs')
@protected('admin')
def logs():
    with b.get_db() as db:
        rows = db.execute('SELECT l.id,l.result,l.verified_at,s.matric_no,u.username AS verified_by_name\n          FROM verification_logs l LEFT JOIN student_profiles s ON s.id=l.student_id\n          LEFT JOIN users u ON u.id=l.verified_by ORDER BY l.id DESC LIMIT 250').fetchall()
    return ok(items=[record(x) for x in rows])

@api.get('/admin-audit')
@protected('admin')
def audit():
    with b.get_db() as db:
        rows = db.execute('SELECT a.id,a.action AS event,a.summary AS details,a.created_at,\n                     u.username AS actor FROM admin_audit_logs a LEFT JOIN users u\n                     ON u.id=a.actor_user_id ORDER BY a.id DESC LIMIT 250').fetchall()
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
