"""API contract and security regression checks; no external database required."""
import ast
import os
import unittest
from pathlib import Path


class ReactAdapterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.environ.setdefault('SECRET_KEY', 'test-sessions-secret-test-sessions-secret')
        import app
        cls.app = app.app
        cls.module = app
        cls.app.config.update(TESTING=True, WTF_CSRF_ENABLED=False)

    def test_all_expected_api_routes_exist(self):
        rules = {rule.rule for rule in self.app.url_map.iter_rules()}
        for path in (
            '/api/session','/api/login','/api/logout','/api/dashboard',
            '/api/catalogue','/api/students','/api/students/<int:student_id>',
            '/api/students/<int:student_id>/claim-code',
            '/api/students/<int:student_id>/rotate-qr',
            '/api/students/<int:student_id>/qr.png',
            '/api/student/my-qr.png','/api/verify','/api/logs',
            '/api/admin-audit','/api/students/demo-cleanup',
            '/api/compatibility','/api/register',
            '/api/registration-requests/<int:rid>/<string:decision>',
        ):
            with self.subTest(path=path): self.assertIn(path, rules)

    def test_unauthenticated_endpoints_reject_access_without_db(self):
        with self.app.test_client() as client:
            for path in ('/api/students','/api/dashboard','/api/compatibility',
                         '/api/admin-audit','/api/student/me'):
                with self.subTest(path=path):
                    r = client.get(path)
                    self.assertEqual(r.status_code, 401)
                    self.assertEqual(r.json['error'], 'Please sign in to continue.')

    def test_public_catalogue_has_no_student_records(self):
        with self.app.test_client() as client:
            r = client.get('/api/catalogue')
            self.assertEqual(r.status_code, 200)
            self.assertEqual(len(r.json['faculties']), 10)
            self.assertEqual(len(r.json['departments']), 59)
            self.assertNotIn('students', r.json)

    def test_csrf_rejects_unauthorised_mutation(self):
        previous = self.app.config.get('WTF_CSRF_ENABLED')
        self.app.config['WTF_CSRF_ENABLED'] = True
        try:
            with self.app.test_client() as client:
                r = client.post('/api/login', json={'username':'not-real','password':'secret'})
                self.assertEqual(r.status_code, 400)
                self.assertIn('csrf', r.json['error'].lower() + ' token')
        finally:
            self.app.config['WTF_CSRF_ENABLED'] = previous

    def test_public_student_response_excludes_secrets(self):
        from spa_api import public_student
        from types import SimpleNamespace
        record = SimpleNamespace(_mapping={
            'id':1,'matric_no':'DEMO/2026/000001','first_name':'Ada',
            'middle_name':'','last_name':'Example','token':'TOP_SECRET_QR',
            'password_hash':'SECRET_HASH','claim_code_hash':'SECRET_CLAIM',
            'status':'Active','faculty':'Science','department':'Computer Science',
            'level':'400'
        })
        result = public_student(record)
        self.assertEqual(result['name'], 'Ada Example')
        self.assertNotIn('token', result)
        self.assertNotIn('password_hash', result)
        self.assertNotIn('claim_code_hash', result)

    def test_react_scanner_prefers_rear_camera(self):
        root = Path(__file__).parents[1]
        source = (root/'frontend/src/pages.js').read_text()
        self.assertIn("{facingMode:{exact:'environment'}}", source)
        self.assertIn("{facingMode:'environment'}", source)
        self.assertIn("Camera could not start", source)

    def test_spa_api_preserves_hardened_database_implementation(self):
        root = Path(__file__).parents[1]
        source = (root/'spa_api.py').read_text()
        self.assertNotIn('DROP TABLE', source)
        self.assertNotIn('CREATE TABLE', source)
        self.assertIn('b.ensure_security_migrations()', source)
        self.assertIn('b.student_identity(', source)
        self.assertIn('b.audit_admin_action(', source)
        self.assertIn('token_fingerprint', source)
        self.assertIn("'[REDACTED]'", source)


if __name__ == '__main__':
    unittest.main()
