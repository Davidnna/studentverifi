"""Release invariants that run without Flask or a live database."""
import ast
import json
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class SourceContractTests(unittest.TestCase):
    def text(self, relative):
        return (ROOT / relative).read_text(encoding="utf-8")

    def test_sole_markdown_is_readme(self):
        names = sorted(path.name for path in ROOT.rglob("*.md")
                       if not any(folder in path.parts for folder in
                                  ("node_modules", ".venv", ".git", "public")))
        self.assertEqual(names, ["README.md"])

    def test_legacy_page_templates_removed(self):
        self.assertFalse((ROOT / "templates").exists())
        source = self.text("app.py")
        self.assertNotIn("render_template", source)
        self.assertNotIn('@app.route("/login"', source)
        self.assertIn('spa_api.install(app', source)

    def test_database_setup_is_not_automatic(self):
        tree = ast.parse(self.text("app.py"))
        calls = [node.func.id for node in tree.body
                 if isinstance(node, ast.Expr) and isinstance(node.value, ast.Call)
                 and isinstance(node.value.func, ast.Name)
                 for unused in [node.value.func] if unused.id == "init_db"]
        self.assertEqual(calls, [])
        self.assertIn('command("init-db")', self.text("app.py"))

    def test_bundled_brand_assets_exist(self):
        self.assertTrue((ROOT / "frontend/public/favicon.svg").is_file())
        self.assertTrue((ROOT / "frontend/public/logo.svg").is_file())
        self.assertIn("../public", self.text("vite.config.js"))

    def test_react_router_drives_navigation(self):
        main = self.text("frontend/src/main.js")
        ui = self.text("frontend/src/components.js")
        self.assertIn("BrowserRouter", main)
        self.assertIn("NavLink", ui)
        self.assertIn("useNavigate", ui)
        self.assertNotIn("window.location.href", ui)
        self.assertNotIn("location.reload", ui)

    def test_compiled_assets_are_published_with_source(self):
        package = json.loads(self.text("package.json"))
        config = json.loads(self.text("vercel.json"))
        workflow = self.text(".github/workflows/verify.yml")
        self.assertIn("vite build", package["scripts"]["build"])
        self.assertEqual(config["buildCommand"], "python build.py")
        self.assertIn('[tool.vercel.scripts]', self.text("pyproject.toml"))
        self.assertIn('build = "python build.py"', self.text("pyproject.toml"))
        self.assertIn("npm run build", workflow)
        self.assertIn("git add -f public/index.html", workflow)
        self.assertIn("github.event_name == 'push'", workflow)
        self.assertIn("STUDENTVERIFI_SOURCE_COMMIT", workflow)
        self.assertIn("STUDENTVERIFI_SOURCE_COMMIT", config["ignoreCommand"])
        self.assertIn("git log -1 --pretty=%s", config["ignoreCommand"])
        self.assertIn("build: publish React assets for Vercel", config["ignoreCommand"])
        self.assertIn("startsWith(github.event.head_commit.message", workflow)
        self.assertIn("contents: write", workflow)
        self.assertNotIn("/public/", self.text(".gitignore"))
        self.assertIn("verify_assets()", self.text("build.py"))
        self.assertNotIn("subprocess.run", self.text("build.py"))
        self.assertNotIn("SETUP_TOKEN", self.text(".env.example"))

    def test_api_and_security_contract(self):
        api = self.text("spa_api.py")
        app = self.text("app.py")
        self.assertIn("token_fingerprint", api)
        self.assertIn("'[REDACTED]'", api)
        self.assertIn("@protected('admin')", api)
        self.assertIn("generate_csrf", api)
        self.assertIn("SESSION_COOKIE_HTTPONLY=True", app)
        self.assertIn("SESSION_COOKIE_SECURE=", app)
        self.assertIn("CSRFProtect(app)", app)
        self.assertNotIn("DROP TABLE", api)

    def test_mobile_accessibility_and_rear_camera(self):
        scanner = self.text("frontend/src/pages.js")
        css = self.text("frontend/src/style.css")
        self.assertIn("facingMode: { exact: 'environment' }".replace(" ", ""),
                          scanner.replace(" ", ""))
        self.assertIn("@media(max-width:700px)", css.replace(" ", ""))
        self.assertIn("prefers-reduced-motion", css)
        self.assertIn(":focus-visible", css)

    def test_csrf_token_refresh_and_single_retry(self):
        client = self.text("frontend/src/api.js")
        self.assertIn("async function refreshCsrf()", client)
        self.assertIn("credentials: 'same-origin'", client)
        self.assertIn("isCsrfFailure(response, data)", client)
        self.assertIn("await refreshCsrf()", client)
        self.assertIn("CSRFProtect(app)", self.text("app.py"))

    def test_legacy_registration_is_retired_and_new_claim_is_rate_limited(self):
        api = self.text("spa_api.py")
        legacy = api[api.index("@api.post('/register')"):api.index("@api.get('/verifiers')")]
        claim = api[api.index("@api.post('/claim/start')"):api.index("@api.post('/register')")]
        self.assertIn("return err('The old approval-based registration form has been retired", legacy)
        self.assertIn("FOR UPDATE", claim)
        self.assertIn("_rate_limit_remaining", claim)
        self.assertIn("_record_rate_limit_failure", claim)
        self.assertIn("email_snapshot", claim)
        self.assertIn("student['email'].strip().lower() == email", claim)

    def test_workspace_redesign_and_public_information_content(self):
        ui = self.text("frontend/src/components.js")
        pages = self.text("frontend/src/pages.js")
        css = self.text("frontend/src/style.css")
        self.assertIn("app-sidebar", ui)
        self.assertIn("sidebar-backdrop", ui)
        self.assertIn("aria-hidden", ui)
        self.assertIn("studentGroups", ui)
        self.assertIn("Protecting student information", pages)
        self.assertIn("dashboard-insights-grid", pages)
        self.assertIn("@media (max-width: 700px)", css)
        self.assertIn("prefers-reduced-motion", css)
        self.assertIn(":focus-visible", css)

    def test_public_and_workspace_shells_are_route_specific(self):
        ui = self.text("frontend/src/components.js")
        css = self.text("frontend/src/style.css")
        self.assertIn("function isWorkspaceRoute(pathname)", ui)
        self.assertIn("const isWorkspace = isWorkspaceRoute(location.pathname)", ui)
        self.assertIn("return user && isWorkspace ? h(DashboardShell) : h(PublicShell)", ui)
        for path in ("'/dashboard'", "'/students'", "'/verify'", "'/registration-requests'",
                     "'/admin-audit'", "'/verifiers'", "'/verifier/dashboard'",
                     "'/verifier/activity'", "'/student/account'", "'/account/password'"):
            self.assertIn(path, ui)
        self.assertIn("pathname.startsWith('/students/')", ui)
        self.assertIn("pathname.replace(/\\/+$/, '')", ui)
        self.assertIn("scrollbar-width: thin", css)
        self.assertIn("scrollbar-color:", css)
        self.assertIn(".sidebar-navigation::-webkit-scrollbar", css)
        self.assertIn(".sidebar-navigation::-webkit-scrollbar-thumb:active", css)

    def test_registration_request_history_includes_decisions(self):
        api = self.text("spa_api.py")
        pages = self.text("frontend/src/pages.js")
        endpoint = api[api.index("@api.get('/registration-requests')"):api.index("@api.post('/registration-requests")]
        self.assertNotIn("WHERE r.status='Pending'", endpoint)
        self.assertIn("r.reviewed_at", endpoint)
        self.assertIn("r.reviewed_by", endpoint)
        self.assertIn("AS reviewed_by_name", endpoint)
        self.assertIn("Student self-service", endpoint)
        self.assertIn("['Approved', 'Approved']", pages)
        self.assertIn("['Rejected', 'Rejected']", pages)
        self.assertIn("Decision recorded by ", pages)

    def test_verification_history_is_consolidated(self):
        main = self.text("frontend/src/main.js")
        ui = self.text("frontend/src/components.js")
        pages = self.text("frontend/src/pages.js")
        api = self.text("spa_api.py")
        self.assertIn("route('logs', h(Navigate, { to: '/verify', replace: true }))", main)
        self.assertNotIn("['/logs', 'Verification history'", ui)
        self.assertIn("const history = useResource(user?.role === 'admin' ? '/logs' : '/verifier/activity')", pages)
        self.assertIn("s.full_name AS student_name", api)
        self.assertIn("VERIFIED ACTIVITY", pages)

    def test_workspace_pages_have_a_render_error_fallback(self):
        ui = self.text("frontend/src/components.js")
        pages = self.text("frontend/src/pages.js")
        api = self.text("spa_api.py")
        self.assertIn("export class PageErrorBoundary", ui)
        self.assertIn("fallbackTo: user?.role === 'admin' ? '/dashboard' : user?.role === 'verifier' ? '/verify' : '/student/account'", ui)
        self.assertIn("className: 'page-transition'", ui)
        self.assertIn("export function AdminAudit()", pages)
        self.assertIn("a.target_type,a.target_id", api)

    def test_automatic_email_claim_requires_private_profile_photo_before_qr(self):
        api = self.text("spa_api.py")
        app = self.text("app.py")
        services = self.text("account_services.py")
        pages = self.text("frontend/src/pages.js")
        self.assertIn("@api.post('/claim/start')", api)
        self.assertIn("@api.post('/claim/verify')", api)
        self.assertIn("@api.post('/claim/complete')", api)
        self.assertIn("email_snapshot", api)
        self.assertIn("verify_otp(", api)
        self.assertIn("process_profile_photo(", api)
        self.assertIn("photo_blob_path=?,photo_url=NULL,token=?,claimed_at=?", api)
        self.assertIn("ALTER TABLE students ALTER COLUMN token DROP NOT NULL", app)
        self.assertIn("WHERE NOT EXISTS (SELECT 1 FROM users u WHERE u.student_id=s.id", app)
        self.assertIn('access="private"', services)
        self.assertIn("NYLAS_API_KEY", services)
        self.assertIn("/v3/domains/{config['domain']}/messages/send", services)
        self.assertIn("email_delivery_is_configured", api)
        self.assertNotIn("RESEND_API_KEY", services)
        self.assertNotIn("api.resend.com", services)
        self.assertIn("NYLAS_DOMAIN", self.text(".env.example"))
        self.assertIn("NYLAS_API_BASE_URL", self.text(".env.example"))
        self.assertIn("access=\"private\"", services)
        self.assertIn("BLOB_READ_WRITE_TOKEN", self.text(".env.example"))
        self.assertNotIn("MAIL_FROM", self.text(".env.example"))
        self.assertIn("Nylas Transactional Send", self.text("README.md"))
        self.assertNotIn("Resend", self.text("README.md"))
        self.assertIn("MAX_PROFILE_PHOTO_BYTES = 2 * 1024 * 1024", services)
        self.assertIn("/claim/complete", pages)
        self.assertIn("profile photograph", pages)

    def test_verifier_role_and_public_limited_verification(self):
        api = self.text("spa_api.py")
        app = self.text("app.py")
        main = self.text("frontend/src/main.js")
        ui = self.text("frontend/src/components.js")
        pages = self.text("frontend/src/pages.js")
        self.assertIn("role IN ('admin','student','verifier')", app)
        self.assertIn("@api.post('/verifiers')", api)
        self.assertIn("@api.post('/verifier-invitations/accept')", api)
        self.assertIn("@protected(('admin', 'verifier'))", api)
        self.assertEqual(api.count("def protected(role=None):"), 1)
        self.assertIn("@api.post('/public/verify')", api)
        self.assertIn("matric_no_masked", api)
        self.assertIn("photo_data", api)
        self.assertIn("/credential#{token}", api)
        self.assertIn("NULL,?,'public'", api)
        self.assertIn("route('credential'", main)
        self.assertIn("VerifierManagement", main)
        self.assertIn("verifierGroups", ui)
        self.assertIn("PublicCredential", pages)
        self.assertIn("location.hash.replace", pages)
        self.assertIn("VerifierAccept", pages)

    def test_student_email_is_supported_by_manual_and_bulk_entry(self):
        api = self.text("spa_api.py")
        pages = self.text("frontend/src/pages.js")
        self.assertIn("'email'", api[api.index("@api.get('/students/import-template')"):api.index("@api.post('/students/import')")])
        self.assertIn("label: 'Student email address'", pages)
        self.assertIn("@api.post('/students/<int:student_id>/email')", api)
        self.assertIn("student.email", pages)

    def test_scroll_to_top_and_reduced_motion_page_transitions(self):
        components = self.text("frontend/src/components.js")
        css = self.text("frontend/src/style.css")
        self.assertIn("function ScrollToTopButton()", components)
        self.assertIn("'aria-label': 'Scroll to top'", components)
        self.assertIn("window.scrollTo({", components)
        self.assertIn("className: 'page-transition'", components)
        self.assertIn("@media (prefers-reduced-motion: reduce)", css)
        self.assertIn(".scroll-to-top:focus-visible", css)

    def test_shell_uses_defined_element_factory_and_recovery(self):
        ui = self.text("frontend/src/components.js")
        main = self.text("frontend/src/main.js")
        self.assertNotRegex(ui, r"\bel\s*\(")
        self.assertEqual(ui.count("h('div', { className: 'page-transition' }"), 2)
        self.assertIn("h(PageErrorBoundary, { resetKey: location.pathname", main)
        self.assertIn("controller.abort();", ui)
        self.assertIn("}, 15000);", ui)
        self.assertIn("Opening the application", self.text("frontend/index.html"))
        self.assertIn("npm run test:render", json.loads(self.text("package.json"))["scripts"]["check"])
        self.assertIn('"studentverifi-v3*"', self.text(".github/workflows/verify.yml"))

    def test_no_public_authorisation_details(self):
        api = self.text("spa_api.py")
        self.assertIn("return err('Please sign in to continue.', 401)", api)
        self.assertIn("safe = {k: s.get(k)", api)
        self.assertNotIn("return ok(token=", api)


if __name__ == "__main__":
    unittest.main()
