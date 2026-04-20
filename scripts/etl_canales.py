#!/usr/bin/env python3
"""Entry point — ``python scripts/etl_canales.py`` runs the full canales ETL.

The real logic lives in :mod:`scripts.etl_canales.main`; this shim exists so
repo-root invocation works without requiring ``python -m``.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Ensure the repo root is on sys.path when invoked as a script so
# ``from scripts.etl_canales...`` imports resolve.
_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from scripts.etl_canales.main import main  # noqa: E402


if __name__ == "__main__":
    raise SystemExit(main())
