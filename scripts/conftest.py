"""Local pytest configuration for the ETL test suite.

Ensures the repo root is on ``sys.path`` so ``from scripts.etl_pilar_verde``
imports resolve regardless of the current working directory.
"""

from __future__ import annotations

import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))
