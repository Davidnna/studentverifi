"""Flask smoke tests. Executed by CI after installing requirements.txt."""
import os
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("SECRET_KEY", "test-only-secret-at-least-thirty-two-chars")

import app  # noqa: E402


class Result:
    def __init__(self, values):
        self.values = values

    def fetchone(self):
        return self.values[0] if self.values else None

    def fetchall(self):
        return self.values


class FakeDatabase:
    def __init__(self, user, requests=None, audit=None, logs=None, weekly=None):
        self.user = user
        self.requests = requests or []
        self.audit = audit or []
        self.logs = logs or []
        self.weekly = weekly or []

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def execute(self, statement, params=()):
        query = statement.strip()
        if "FROM users WHERE username" in query or "FROM users WHERE id" in query:
            return Result([self.user])
        if "FROM student_account_requests r" in query:
            return Result(self.requests)
        if "FROM admin_audit_logs a" in query:
            return Result(self.audit)
        if "SELECT DATE(verified_at) AS day" in query:
            return Result(self.weekly)
        if "FROM verification_logs l" in query:
            return Result(self.logs)
        if "COUNT(*)" in query:
            return Result([(0,)])
        if "FROM verification_logs" in query:
            return Result([])
        if "FROM faculties f" in query:
            return Result([])
        raise AssertionError("Unexpected query: " + query)


class RuntimeTests(unittest.TestCase):
    def setUp(self):
        app.app.config.update(TESTING=True, WTF_CSRF_ENABLED=False)
        self.client = app.app.test_client()

    def test_catalogue_and_anonymous_session(self):
        session = self.client.get("/api/session")
        self.assertEqual(session.status_code, 200)
        self.assertIsNone(session.json["user"])
        self.assertTrue(session.json["csrf_token"])
        catalogue = self.client.get("/api/catalogue")
        self.assertEqual(len(catalogue.json["faculties"]), 10)
        self.assertEqual(len(catalogue.json["departments"]), 59)

    def test_data_requires_login(self):
        for path in ("/api/students", "/api/dashboard", "/api/admin-audit"):
            with self.subTest(path=path):
                response = self.client.get(path)
                self.assertEqual(response.status_code, 401)

    def test_react_entrypoint_is_not_replaced_by_legacy_flask(self):
        root = Path(app.app.root_path) / "public"
        root.mkdir(exist_ok=True)
        index = root / "index.html"
        original = index.read_bytes() if index.exists() else None
        try:
            index.write_text("<html>STUDENTVERIFI_VITE_BUILD React</html>")
            for path in ("/login", "/dashboard", "/students/42", "/verify", "/registration-requests", "/logs", "/admin-audit"):
                with self.subTest(path=path):
                    result = self.client.get(path)
                    try:
                        self.assertEqual(result.status_code, 200)
                        self.assertIn(b"STUDENTVERIFI_VITE_BUILD", result.data)
                    finally:
                        result.close()
        finally:
            if original is None:
                index.unlink(missing_ok=True)
            else:
                index.write_bytes(original)

    def test_administrator_login_and_dashboard_api(self):
        from werkzeug.security import generate_password_hash
        user = {"id": 15, "username": "admin", "password_hash": generate_password_hash("SecurePass123!"),
                "role": "admin", "student_id": None}
        today = app.now().date()
        db = FakeDatabase(user, weekly=[{"day": today, "total": 3}])
        with patch.object(app, "get_db", return_value=db), \
             patch.object(app, "ensure_security_migrations"), \
             patch.object(app, "_rate_limit_remaining", return_value=0), \
             patch.object(app, "_clear_rate_limit_failures"):
            login = self.client.post("/api/login", json={"username": "admin", "password": "SecurePass123!"})
            self.assertEqual(login.status_code, 200)
            self.assertEqual(login.json["user"]["role"], "admin")
            dashboard = self.client.get("/api/dashboard")
            self.assertEqual(dashboard.status_code, 200)
            self.assertEqual(dashboard.json["students"], 0)
            self.assertEqual(len(dashboard.json["weekly_verifications"]), 7)
            self.assertEqual(dashboard.json["weekly_verifications"][-1]["date"], today.isoformat())
            self.assertEqual(dashboard.json["weekly_verifications"][-1]["total"], 3)


    def test_registration_requests_returns_pending_and_decided_history(self):
        user = {"id": 15, "username": "admin", "role": "admin", "student_id": None}
        requests = [
            {"id": 3, "status": "Pending", "matric_no": "MAT/003", "name": "Student Three"},
            {"id": 2, "status": "Approved", "matric_no": "MAT/002", "name": "Student Two",
             "reviewed_by_name": "admin", "reviewed_at": "2026-11-20T10:00:00Z"},
            {"id": 1, "status": "Rejected", "matric_no": "MAT/001", "name": "Student One",
             "reviewed_by_name": "admin", "reviewed_at": "2026-11-19T10:00:00Z"}
        ]
        db = FakeDatabase(user, requests=requests)
        with self.client.session_transaction() as sess:
            sess.update(user_id=15, username="admin", role="admin", student_id=None)
        with patch.object(app, "get_db", return_value=db), patch.object(app, "ensure_security_migrations"):
            response = self.client.get("/api/registration-requests")
        self.assertEqual(response.status_code, 200)
        self.assertEqual([row["status"] for row in response.json["items"]], ["Pending", "Approved", "Rejected"])
        self.assertEqual(response.json["items"][1]["reviewed_by_name"], "admin")

    def test_admin_audit_and_verification_history_return_display_fields(self):
        user = {"id": 15, "username": "admin", "role": "admin", "student_id": None}
        db = FakeDatabase(
            user,
            audit=[{"id": 4, "event": "student.updated", "target_type": "student", "target_id": 9,
                    "details": "Administrator updated a student record.", "actor": "admin"}],
            logs=[{"id": 8, "result": "VALID", "student_name": "Student Eight", "matric_no": "MAT/008"}]
        )
        with self.client.session_transaction() as sess:
            sess.update(user_id=15, username="admin", role="admin", student_id=None)
        with patch.object(app, "get_db", return_value=db), patch.object(app, "ensure_security_migrations"):
            audit = self.client.get("/api/admin-audit")
            logs = self.client.get("/api/logs")
        self.assertEqual(audit.status_code, 200)
        self.assertEqual(audit.json["items"][0]["target_type"], "student")
        self.assertEqual(logs.status_code, 200)
        self.assertEqual(logs.json["items"][0]["student_name"], "Student Eight")
        self.assertNotIn("scanned_token", logs.json["items"][0])

    def test_registration_endpoint_requires_a_valid_csrf_token(self):
        app.app.config.update(TESTING=True, WTF_CSRF_ENABLED=True)
        client = app.app.test_client()
        session = client.get("/api/session")
        self.assertEqual(session.status_code, 200)
        token = session.json["csrf_token"]

        rejected = client.post("/api/register", json={})
        self.assertEqual(rejected.status_code, 400)
        self.assertIn("Security check expired", rejected.json["error"])

        accepted_by_csrf = client.post(
            "/api/register",
            json={"matric_no": ""},
            headers={"X-CSRFToken": token}
        )
        self.assertEqual(accepted_by_csrf.status_code, 400)
        self.assertNotIn("Security check expired", accepted_by_csrf.json["error"])

    def test_student_role_cannot_access_admin_api(self):
        with self.client.session_transaction() as sess:
            sess.update(user_id=17, username="student", role="student", student_id=8)
        response = self.client.get("/api/dashboard")
        self.assertEqual(response.status_code, 403)


if __name__ == "__main__":
    unittest.main()
