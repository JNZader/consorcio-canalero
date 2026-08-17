"""``python -m scripts.rainfall_e2e_harness`` — runner driver entry point.

This is the SAME Python runner used locally and by the manual GitHub workflow
(W10.1) and documented in the runbook (W11.4), so the local and hosted paths
share one fail-closed lifecycle (RMEH-010-A).

Example::

    python3 -m scripts.rainfall_e2e_harness run
    python3 -m scripts.rainfall_e2e_harness cleanup --run-id <run_id>
"""

from __future__ import annotations

import sys

from scripts.rainfall_e2e_harness.driver import main

if __name__ == "__main__":
    sys.exit(main())
