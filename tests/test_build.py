"""The release must carry real, precompiled React assets into Vercel."""
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


if __name__ == "__main__":
    unittest.main()
