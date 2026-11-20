"""Flask smoke/security tests; run in an environment with requirements installed."""
import os
import unittest
from pathlib import Path


class AppSmokeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.environ.setdefault('SECRET_KEY', 'test-sessions-secret-test-sessions-secret')
        import app as app_module
        cls.flask_app = app_module.app
        cls.flask_app.config.update(TESTING=True, WTF_CSRF_ENABLED=False)
        cls.mod = app_module

    def test_app_does_not_connect_during_import(self):
        self.assertIsNone(self.mod._ENGINE)

    def test_public_pages_and_security_headers(self):
        with self.flask_app.test_client() as client:
            for path in ('/', '/login', '/register'):
                response = client.get(path)
                self.assertEqual(response.status_code, 200, path)
                self.assertEqual(response.headers.get('X-Content-Type-Options'), 'nosniff')
                self.assertEqual(response.headers.get('X-Frame-Options'), 'DENY')
                self.assertEqual(response.headers.get('Referrer-Policy'), 'no-referrer')
                self.assertIn('Content-Security-Policy', response.headers)
                self.assertIn('no-store', response.headers.get('Cache-Control', ''))

    def test_setup_disabled_without_token(self):
        old = os.environ.pop('SETUP_TOKEN', None)
        try:
            with self.flask_app.test_client() as client:
                self.assertEqual(client.get('/setup').status_code, 404)
        finally:
            if old is not None:
                os.environ['SETUP_TOKEN'] = old

    def test_protected_pages_require_authentication(self):
        with self.flask_app.test_client() as client:
            # With the React build in place, these client routes return the
            # SPA shell; access is enforced by the protected JSON API.
            built = (Path(__file__).parents[1] / 'public' / 'index.html').exists()
            for path in ('/dashboard', '/students', '/verify'):
                self.assertIn(client.get(path).status_code,
                              (200,) if built else (302, 401))
            for path in ('/api/dashboard', '/api/students', '/api/logs'):
                self.assertEqual(client.get(path).status_code, 401)

    def test_csrf_rejects_state_change_without_token(self):
        old = self.flask_app.config.get('WTF_CSRF_ENABLED', True)
        self.flask_app.config['WTF_CSRF_ENABLED'] = True
        try:
            with self.flask_app.test_client() as client:
                response = client.post('/logout')
                self.assertEqual(response.status_code, 400)
        finally:
            self.flask_app.config['WTF_CSRF_ENABLED'] = old

    def test_photo_urls_require_https(self):
        valid = {
            'matric_no': 'TEST/SCI/001', 'first_name': 'Ada', 'last_name': 'Example',
            'faculty': 'Science', 'department': 'Computer Science', 'level': '400',
            'photo_url': 'https://images.example.org/student.png'
        }
        self.mod.student_identity(valid)
        invalid = dict(valid, photo_url='http://images.example.org/student.png')
        with self.assertRaises(ValueError):
            self.mod.student_identity(invalid)
        private_host = dict(valid, photo_url='https://127.0.0.1/student.png')
        with self.assertRaises(ValueError):
            self.mod.student_identity(private_host)

    def test_rate_limit_identifiers_are_hashed(self):
        with self.flask_app.test_request_context('/', environ_base={'REMOTE_ADDR': '203.0.113.10'}):
            buckets = self.mod._login_rate_limit_buckets('admin')
        self.assertGreaterEqual(len(buckets), 2)
        self.assertTrue(all(len(value) == 64 for value in buckets))
        self.assertNotIn('admin', buckets)
        self.assertNotIn('203.0.113.10', buckets)

    def test_production_cookie_policy_is_configured(self):
        self.assertTrue(self.flask_app.config['SESSION_COOKIE_HTTPONLY'])
        self.assertEqual(self.flask_app.config['SESSION_COOKIE_SAMESITE'], 'Lax')
        self.assertEqual(self.flask_app.config['PERMANENT_SESSION_LIFETIME'].total_seconds(), 8 * 60 * 60)
        self.assertFalse(self.flask_app.config['SESSION_REFRESH_EACH_REQUEST'])

    def test_production_features_have_routes(self):
        rules = {rule.rule for rule in self.flask_app.url_map.iter_rules()}
        self.assertIn('/students/<int:student_id>/rotate-qr', rules)
        self.assertIn('/admin/maintenance/demo-records', rules)
        self.assertIn('/admin/audit', rules)
        self.assertNotIn('/students/synthetic-demo', rules)

    def test_registration_requires_claim_code_in_template(self):
        template = Path(__file__).parents[1] / 'templates' / 'student_register.html'
        content = template.read_text(encoding='utf-8')
        self.assertIn('name="claim_code"', content)
        self.assertIn('required minlength="16"', content)

    def test_claim_code_is_not_put_in_flash_message(self):
        source = (Path(__file__).parents[1] / 'app.py').read_text(encoding='utf-8')
        self.assertNotIn('flash("One-time claim code. Share privately with the student: " + code', source)
        self.assertIn('return render_template("student_detail.html", student=profile, claim_code=code)', source)

    def test_verification_logs_store_fingerprint_not_raw_token(self):
        source = (Path(__file__).parents[1] / 'app.py').read_text(encoding='utf-8')
        self.assertIn("hashlib.sha256(raw_submitted[:512]", source)
        self.assertIn("VALUES (?,'[REDACTED]',?,?,?,?)", source)
        self.assertIn("token_fingerprint VARCHAR(64)", source)


if __name__ == '__main__':
    unittest.main()
