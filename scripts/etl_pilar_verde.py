#!/usr/bin/env python3
"""Entry point — ``python scripts/etl_pilar_verde.py`` runs the full ETL.

The real logic lives in :mod:`scripts.etl_pilar_verde.main`.
"""

from __future__ import annotations

import sys
from pathlib import Path

# When invoked as a script (not imported), ensure the repo root is on sys.path
# so ``from scripts.etl_pilar_verde...`` imports resolve.
_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from scripts.etl_pilar_verde.main import main  # noqa: E402


if __name__ == "__main__":
    raise SystemExit(main())
