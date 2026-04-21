"""Local pytest configuration for the Escuelas Rurales ETL test suite.

Ensures the repo root is on ``sys.path`` so ``from scripts.etl_escuelas...``
imports resolve regardless of the current working directory. Mirrors
``scripts/conftest.py`` (which covers tests under ``scripts/tests/``) so the
package-local suite can be run via ``pytest scripts/etl_escuelas/tests/``.
"""

from __future__ import annotations

import sys
from pathlib import Path

# scripts/etl_escuelas/tests/conftest.py → scripts/etl_escuelas/tests → scripts/etl_escuelas → scripts → repo root
_REPO_ROOT = Path(__file__).resolve().parents[3]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))
