"""Local, repeatable launch: python start.py [--port 8000] [--setup-only]."""

import argparse
import hashlib
import os
import subprocess
import sys
import venv
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def main():
    parser = argparse.ArgumentParser(description="Run the Teplo web MVP locally.")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--setup-only", action="store_true")
    args = parser.parse_args()
    if not 1024 <= args.port <= 65535:
        parser.error("Use a port between 1024 and 65535.")
    env_dir = ROOT / ".venv"
    interpreter = env_dir / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    if not interpreter.exists():
        venv.create(env_dir, with_pip=True)
    requirements = ROOT / "requirements.txt"
    fingerprint = hashlib.sha256(requirements.read_bytes()).hexdigest()
    stamp = env_dir / ".teplo-requirements"

    def run(*command):
        subprocess.run([str(interpreter), *command], cwd=ROOT, check=True)

    if not stamp.exists() or stamp.read_text() != fingerprint:
        pip_available = (
            subprocess.run(
                [str(interpreter), "-m", "pip", "--version"], capture_output=True
            ).returncode
            == 0
        )
        if not pip_available:
            run("-m", "ensurepip", "--upgrade")
        run("-m", "pip", "install", "-r", str(requirements))
        stamp.write_text(fingerprint)
    run("scripts/compile_translations.py")
    run("manage.py", "migrate", "--noinput")
    run("manage.py", "seed_marketplace")
    run("manage.py", "check")
    print(f"\nOpen http://127.0.0.1:{args.port}/", flush=True)
    print("Local data: db.sqlite3; uploaded images: media/", flush=True)
    if not args.setup_only:
        run("manage.py", "runserver", f"127.0.0.1:{args.port}")


if __name__ == "__main__":
    try:
        main()
    except (subprocess.CalledProcessError, KeyboardInterrupt) as error:
        sys.exit(error.returncode if isinstance(error, subprocess.CalledProcessError) else 0)
