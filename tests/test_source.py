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

    def test_student_registration_is_locked_and_rate_limited(self):
        api = self.text("spa_api.py")
        register = api[api.index("@api.post('/register')"):api.index("@api.get('/registration-requests')")]
        self.assertIn("FOR UPDATE OF s", register)
        self.assertIn("_rate_limit_remaining", register)
        self.assertIn("_record_rate_limit_failure", register)
        self.assertIn("claim_code_hash", register)
        self.assertIn("len(password) < 12", register)

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

    def test_registration_request_history_includes_decisions(self):
        api = self.text("spa_api.py")
        pages = self.text("frontend/src/pages.js")
        endpoint = api[api.index("@api.get('/registration-requests')"):api.index("@api.post('/registration-requests")]
        self.assertNotIn("WHERE r.status='Pending'", endpoint)
        self.assertIn("r.reviewed_at", endpoint)
        self.assertIn("r.reviewed_by", endpoint)
        self.assertIn("reviewer.username AS reviewed_by_name", endpoint)
        self.assertIn("['Approved', 'Approved']", pages)
        self.assertIn("['Rejected', 'Rejected']", pages)
        self.assertIn("Reviewed by ", pages)

    def test_verification_history_is_consolidated(self):
        main = self.text("frontend/src/main.js")
        ui = self.text("frontend/src/components.js")
        pages = self.text("frontend/src/pages.js")
        api = self.text("spa_api.py")
        self.assertIn("route('logs', h(Navigate, { to: '/verify', replace: true }))", main)
        self.assertNotIn("['/logs', 'Verification history'", ui)
        self.assertIn("const history = useResource('/logs')", pages)
        self.assertIn("s.full_name AS student_name", api)
        self.assertIn("VERIFIED ACTIVITY", pages)

    def test_workspace_pages_have_a_render_error_fallback(self):
        ui = self.text("frontend/src/components.js")
        pages = self.text("frontend/src/pages.js")
        api = self.text("spa_api.py")
        self.assertIn("export class PageErrorBoundary", ui)
        self.assertIn("h(PageErrorBoundary, { key: location.pathname, fallbackTo: user?.role === 'admin' ? '/dashboard' : '/student/account' }, h(Outlet))", ui)
        self.assertIn("export function AdminAudit()", pages)
        self.assertIn("a.target_type,a.target_id", api)

    def test_no_public_authorisation_details(self):
        api = self.text("spa_api.py")
        self.assertIn("return err('Please sign in to continue.', 401)", api)
        self.assertIn("safe = {k: s.get(k)", api)
        self.assertNotIn("return ok(token=", api)


if __name__ == "__main__":
    unittest.main()
