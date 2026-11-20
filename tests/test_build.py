"""The release must carry real, precompiled React assets into Vercel."""
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from build import verify_assets


class BundleTests(unittest.TestCase):
    def test_complete_compiled_bundle_passes(self):
        with tempfile.TemporaryDirectory() as d:
            out = Path(d)
            (out / "assets").mkdir()
            (out / "index.html").write_text("<div>STUDENTVERIFI_VITE_BUILD</div><!-- STUDENTVERIFI_SOURCE_COMMIT:test --><script src='/assets/app.js'></script>", encoding="utf-8")
            (out / "assets" / "app.js").write_text("/* built script */", encoding="utf-8")
            (out / "assets" / "style.css").write_text("body{}", encoding="utf-8")
            verify_assets(out)

    def test_missing_assets_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaisesRegex(RuntimeError, "React bundle missing"):
                verify_assets(Path(d))

    def test_missing_js_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            out = Path(d)
            (out / "assets").mkdir()
            (out / "assets" / "style.css").write_text("body{}", encoding="utf-8")
            (out / "index.html").write_text("<div>STUDENTVERIFI_VITE_BUILD</div><!-- STUDENTVERIFI_SOURCE_COMMIT:test --><script src='/assets/absent.js'></script>", encoding="utf-8")
            with self.assertRaisesRegex(RuntimeError, "bundle .* missing"):
                verify_assets(out)

    def test_vercel_deploys_only_the_generated_assets_commit(self):
        root = Path(__file__).resolve().parents[1]
        config = json.loads((root / "vercel.json").read_text(encoding="utf-8"))
        command = config["ignoreCommand"]

        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)

            def git(*args):
                return subprocess.run(
                    ["git", *args], cwd=repo, check=True,
                    capture_output=True, text=True
                ).stdout.strip()

            git("init", "-b", "main")
            git("config", "user.name", "StudentVerifi Test")
            git("config", "user.email", "test@example.invalid")
            (repo / "public").mkdir()
            (repo / "public" / "index.html").write_text("previous bundle")
            (repo / "source.txt").write_text("initial")
            git("add", ".")
            git("commit", "-m", "initial")
            (repo / "source.txt").write_text("application source")
            git("add", ".")
            git("commit", "-m", "feat: update StudentVerifi")
            source_commit = git("rev-parse", "HEAD")

            source_result = subprocess.run(["sh", "-c", command], cwd=repo)
            self.assertEqual(source_result.returncode, 0)

            (repo / "public" / "index.html").write_text(
                f"<!-- STUDENTVERIFI_SOURCE_COMMIT:{source_commit} -->"
            )
            git("add", "public/index.html")
            git("commit", "-m", "build: publish React assets for Vercel [skip ci]")
            built_result = subprocess.run(["sh", "-c", command], cwd=repo)
            self.assertEqual(built_result.returncode, 1)

            (repo / "public" / "index.html").write_text("<!-- stale bundle -->")
            git("add", "public/index.html")
            git("commit", "-m", "build: publish React assets for Vercel [skip ci]")
            stale_result = subprocess.run(["sh", "-c", command], cwd=repo)
            self.assertEqual(stale_result.returncode, 0)


if __name__ == "__main__":
    unittest.main()
