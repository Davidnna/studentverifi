"""Offline smoke tests; they do not connect to a live Neon database."""
import os

os.environ.setdefault('DATABASE_URL', 'postgresql+psycopg://example:example@localhost:5432/example')
os.environ.setdefault('SECRET_KEY', 'development-testing-secret-never-deploy')
os.environ.setdefault('COOKIE_SECURE', 'false')

from app import app, student_public, validate_student_row, student_name  # noqa: E402


def test_public_json_and_security_headers():
    client = app.test_client()
    response = client.get('/api/public-info')
    assert response.status_code == 200
    assert response.json['prototype'] is True
    assert response.headers['X-Content-Type-Options'] == 'nosniff'
    assert "frame-ancestors 'none'" in response.headers['Content-Security-Policy']


def test_session_csrf_token():
    client = app.test_client()
    response = client.get('/api/session')
    assert response.status_code == 200
    assert response.json['csrf_token']
    assert response.json['user'] is None


def test_private_endpoints_require_login():
    client = app.test_client()
    for route in ['/api/dashboard', '/api/students', '/api/logs', '/api/admin-audit',
                  '/api/compatibility', '/api/student/my-qr.png']:
        response = client.get(route)
        assert response.status_code == 401, (route, response.status_code)


def test_post_actions_need_csrf():
    client = app.test_client()
    assert client.post('/api/login', json={'username': 'nobody', 'password': 'not-a-password'}).status_code == 400


def test_separate_name_projection():
    obj = {'id': 5, 'first_name': 'Ada', 'middle_name': 'Chiamaka', 'last_name': 'Example',
           'matric_no': 'DEMO/2026/0001', 'department': 'Computer Science', 'level': '400', 'status': 'Active'}
    assert student_name(obj) == 'Ada Chiamaka Example'
    assert student_public(obj)['name'] == 'Ada Chiamaka Example'
    assert 'token' not in student_public({**obj, 'token': 'SECRET'})


def test_student_field_validation():
    cols = {'matric_no', 'first_name', 'middle_name', 'last_name', 'faculty',
            'department', 'level', 'email', 'status', 'token', 'record_source', 'created_at'}
    payload = {'matric_no': 'DEMO/2026/0099', 'first_name': 'Ada', 'last_name': 'Example',
               'faculty': 'Science', 'department': 'Computer Science', 'level': '400'}
    row = validate_student_row(payload, cols)
    assert row['record_source'] == 'synthetic'
    assert len(row['token']) >= 32
    try:
        validate_student_row({**payload, 'level': '900'}, cols)
    except ValueError as e:
        assert 'Level' in str(e)
    else:
        assert False, 'Invalid academic level was accepted'
