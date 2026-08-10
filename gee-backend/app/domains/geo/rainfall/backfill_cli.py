"""One-shot 1991-2020 Rainfall v2 historical baseline backfill runner.

Mirrors the hand-run ETL precedent
(``app/domains/geo/etl/generate_chirps_normals.py``): this is NOT a Beat
schedule -- the 1991-2020 baseline is computed ONCE per deployment, by hand,
inside the deployed backend container::

    docker compose exec backend python -m app.domains.geo.rainfall.backfill_cli

Precondition: the ``historical`` role feature flag must be enabled
(``feature_flags.py``, ``tasks._role_enabled``) -- an outage-fast provider
call is otherwise refused before any GEE contact.

**Recovery-window rule (design.md D2).** This runner stops LABELLED --
never a bare traceback -- on a provider outage (``adapter_error``) or an
open circuit breaker (``circuit_open``), and exits non-zero with the
reason. The breaker is Redis-backed **per role** and persists roughly 300
seconds ACROSS PROCESSES (``resilience.py``): a brand-new run of this
module inherits the open breaker of the run that just failed. On a
``circuit_open`` stop, WAIT OUT the ~300s recovery window before rerunning
-- a rerun inside that window is expected to stop again immediately with
the same labelled event, never another provider call. Rerunning is always
safe and idempotent: the checkpoint (``rainfall_backfill_checkpoint``)
resumes at the first year without ``completed_at`` and re-fetches nothing
already completed (``tasks.backfill_baseline_range``).
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence

from app.domains.geo.rainfall.adapters.gee_client import DEFAULT_ZONE_ASSET
from app.domains.geo.rainfall.tasks import backfill_baseline_range

EXIT_OK = 0
EXIT_STOPPED = 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="backfill_cli",
        description=(
            "One-shot 1991-2020 Rainfall v2 historical baseline backfill. "
            "Stops LABELLED (never a bare traceback) on a provider outage "
            "(adapter_error) or an open circuit breaker (circuit_open). On a "
            "circuit_open stop, the breaker is Redis-backed per role and "
            "persists roughly 300s ACROSS PROCESSES -- wait out that "
            "recovery window before rerunning; a rerun inside the window is "
            "expected to stop again immediately with the same labelled "
            "event, never another provider call. Idempotent by checkpoint: "
            "rerunning re-fetches nothing already completed."
        ),
    )
    parser.add_argument(
        "--asset",
        default=DEFAULT_ZONE_ASSET,
        help=(
            "GEE asset name to backfill (default: the deployment's single "
            "zone asset, %(default)r). The key is the asset itself, not any "
            "particular zone or basin scope id (design.md D1)."
        ),
    )
    parser.add_argument("--start-year", type=int, default=1991)
    parser.add_argument("--end-year", type=int, default=2020, help="inclusive")
    parser.add_argument(
        "--source-id",
        default="chirps-v3-final",
        help="provider source id (default: %(default)r)",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    result = backfill_baseline_range(
        args.asset,
        years=range(args.start_year, args.end_year + 1),
        source_id=args.source_id,
    )

    if result["stopped"]:
        print(
            f"STOPPED at year {result['year']} (reason={result['reason']}). "
            f"Completed years so far: {result['completed_years']}. "
            "See this module's docstring for the recovery-window wait-out rule.",
            file=sys.stderr,
        )
        return EXIT_STOPPED

    print(f"completed years: {result['completed_years']}")
    return EXIT_OK


if __name__ == "__main__":  # pragma: no cover — module entry point
    raise SystemExit(main())
