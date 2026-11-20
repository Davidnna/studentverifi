"""The deployment hook must generate a complete, usable frontend."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import build


class BuildHookTests(unittest.TestCase):
    def test_react_assets_are_checked_after_npm_build(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            output = root / "public"
            commands = []

            def pretend_subprocess(command, **_kwargs):
                commands.append(command)
                if command == ["npm", "run", "build"]:
                    (output / "assets").mkdir(parents=True)
                    (output / "index.html").write_text(
                        '<div>STUDENTVERIFI_VITE_BUILD</div><script src="/assets/app.js"></script>',
                        encoding="utf-8",
                    )
                    (output / "assets" / "app.js").write_text("console.log('ok')", encoding="utf-8")

            with patch.object(build, "BASE", root), patch.object(build, "OUTPUT", output), \
                    patch.object(build.subprocess, "run", side_effect=pretend_subprocess):
                build.main()
            self.assertEqual(commands[0][0:2], ["npm", "install"])
            self.assertEqual(commands[1], ["npm", "run", "build"])

    def test_missing_assets_are_a_failed_build(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            with patch.object(build, "BASE", root), patch.object(build, "OUTPUT", root / "public"), \
                    patch.object(build.subprocess, "run"):
                with self.assertRaisesRegex(RuntimeError, "React build incomplete"):
                    build.main()


if __name__ == "__main__":
    unittest.main()
