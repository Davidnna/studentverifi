"""Required Vercel Python build step: compile React before publishing Flask."""
import os
import subprocess
from pathlib import Path

BASE = Path(__file__).resolve().parent
OUTPUT = BASE / "public"


def main():
    # Vercel's Flask builder does not automatically compile a Vite frontend.
    # Fail visibly when Node/npm or React dependencies are unavailable.
    environment = os.environ.copy()
    environment.setdefault("CI", "true")
    subprocess.run(
        ["npm", "install", "--include=dev", "--no-audit", "--no-fund"],
        cwd=BASE,
        env=environment,
        check=True,
    )
    subprocess.run(["npm", "run", "build"], cwd=BASE, env=environment, check=True)
    index = OUTPUT / "index.html"
    if not index.is_file() or "STUDENTVERIFI_VITE_BUILD" not in index.read_text(encoding="utf-8"):
        raise RuntimeError("React build incomplete: public/index.html not generated")
    if not list((OUTPUT / "assets").glob("*.js")):
        raise RuntimeError("React build incomplete: JavaScript bundles not generated")
    print("StudentVerifi React build ready: public/index.html and bundled assets found", flush=True)


if __name__ == "__main__":
    main()
