"""Smoke tests; run only if optional Flask dependencies are installed."""
import os
import unittest


class AppSmokeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.environ.setdefault('SECRET_KEY', 'test-sessions-secret-test-sessions-secret')
        import app
        cls.flask_app = app.app
        cls.flask_app.config.update(TESTING=True, WTF_CSRF_ENABLED=False)
        cls.mod = app

    def test_app_does_not_connect_during_import(self):
        self.assertIsNone(self.mod._ENGINE)

    def test_public_pages(self):
        with self.flask_app.test_client() as client:
            self.assertEqual(client.get('/').status_code, 200)
            self.assertEqual(client.get('/login').status_code, 200)
            self.assertEqual(client.get('/register').status_code, 200)

    def test_setup_disabled_without_token(self):
        old = os.environ.pop('SETUP_TOKEN', None)
        try:
            with self.flask_app.test_client() as client:
                self.assertEqual(client.get('/setup').status_code, 404)
        finally:
            if old is not None:
                os.environ['SETUP_TOKEN'] = old


if __name__ == '__main__':
    unittest.main()
