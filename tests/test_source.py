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

    def test_deployment_build_is_required(self):
        package = json.loads(self.text("package.json"))
        config = json.loads(self.text("vercel.json"))
        self.assertIn("vite build", package["scripts"]["build"])
        self.assertIn("npm run build", config["buildCommand"])
        self.assertEqual(config["framework"], "flask")
        self.assertIn({"source": "/dashboard", "destination": "/index.html"},
                      config["rewrites"])
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
        self.assertIn("@media(max-width:760px)", css.replace(" ", ""))
        self.assertIn("prefers-reduced-motion", css)
        self.assertIn(":focus-visible", css)

    def test_no_public_authorisation_details(self):
        api = self.text("spa_api.py")
        self.assertIn("return err('Please sign in to continue.', 401)", api)
        self.assertIn("safe = {k: s.get(k)", api)
        self.assertNotIn("return ok(token=", api)


if __name__ == "__main__":
    unittest.main()
