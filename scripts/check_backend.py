"""Pre-deploy backend sanity check.

Run this before deploying the backend to catch syntax/import errors
that would prevent the API from starting.

Usage (from project root):

    python scripts/check_backend.py

What it does:
- Compiles all Python files under backend/app to catch SyntaxError.
- Ensures app.main can be imported successfully.
"""

from __future__ import annotations

import compileall
import sys
from pathlib import Path


def main() -> None:
    base_dir = Path(__file__).resolve().parent.parent
    backend_dir = base_dir / "backend"
    app_dir = backend_dir / "app"

    print("[check-backend] Base directory:", base_dir)
    print("[check-backend] Checking Python syntax under:", app_dir)

    # 1) Syntax check: compile all backend/app modules
    success = compileall.compile_dir(str(app_dir), quiet=1)
    if not success:
        print("[check-backend] ❌ Syntax errors detected in backend/app.", file=sys.stderr)
        print("[check-backend]    Fix all syntax errors before deploying.", file=sys.stderr)
        sys.exit(1)

    print("[check-backend] ✅ Syntax check passed (no SyntaxError in backend/app).")

    # 2) Import check: make sure app.main imports without raising
    print("[check-backend] Importing app.main to validate router imports...")
    # Ensure `backend` is on sys.path so `import app.main` works from repo root
    if str(backend_dir) not in sys.path:
        sys.path.insert(0, str(backend_dir))

    try:
        __import__("app.main")
    except Exception as exc:  # pragma: no cover - defensive
        print("[check-backend] ❌ Import of app.main failed:", repr(exc), file=sys.stderr)
        print(
            "[check-backend]    This usually means a broken import, syntax error, or",
            "module-level exception in one of the routers.",
            file=sys.stderr,
        )
        sys.exit(1)

    print("[check-backend] ✅ app.main imported successfully.")
    print("[check-backend] ✅ Backend syntax + import checks passed.")


if __name__ == "__main__":  # pragma: no cover - CLI entry point
    raise SystemExit(main())
