"""
Demo API 容器入口：bootstrap → uvicorn。

compose command: python scripts/demo_entrypoint.py
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def main() -> None:
    env = os.environ.copy()
    env.setdefault("APP_ENV", "demo")
    profile = env.get("DEMO_PROFILE", "excel")
    print(f"[entrypoint] bootstrap profile={profile}", flush=True)
    r = subprocess.run(
        [sys.executable, "scripts/bootstrap_demo.py", "--profile", profile],
        cwd=str(ROOT),
        env=env,
        check=False,
    )
    if r.returncode != 0:
        print(f"[entrypoint] bootstrap failed rc={r.returncode}", flush=True)
        sys.exit(r.returncode)
    print("[entrypoint] starting uvicorn", flush=True)
    os.execvp(
        sys.executable,
        [
            sys.executable,
            "-m",
            "uvicorn",
            "app.main:app",
            "--host",
            "0.0.0.0",
            "--port",
            "8000",
        ],
    )


if __name__ == "__main__":
    main()
