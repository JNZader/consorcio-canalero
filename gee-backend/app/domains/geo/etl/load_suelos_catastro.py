"""Load ``suelos_cu.geojson`` into ``suelos_catastro``.

**This PR (A1a) ships the prerequisite check only.** The load itself — full
refresh in one transaction, load-time assertions, concurrent MV refresh — lands
in PR A1b. ``--check-prereqs`` is the deployment gate that runs first.

Why a prerequisite check exists at all: the parcel ficha resolves its geometry
from ``parcelas_catastro``. An empty ``parcelas_catastro`` in the target
environment means ``tipo=parcela`` answers 404 for every request — a deployment
blocker that must be named before merge, not discovered as a runtime 404 storm.

Usage::

    docker compose exec backend python -m app.domains.geo.etl.load_suelos_catastro \\
        --check-prereqs

Exit codes:
    0  every prerequisite satisfied
    1  ``parcelas_catastro`` missing or empty (deployment blocker for tipo=parcela)
    2  invalid invocation / not-yet-implemented mode
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import sys
from typing import Sequence

from sqlalchemy import text
from sqlalchemy.orm import Session

EXIT_OK = 0
EXIT_PREREQ_FAILED = 1
EXIT_USAGE = 2

#: Tables reported by ``--check-prereqs``. Also the identifier whitelist for
#: :func:`table_row_count` — these names are interpolated into SQL, so nothing
#: outside this tuple is ever accepted.
PREREQ_TABLES: tuple[str, ...] = ("parcelas_catastro", "suelos_catastro")

#: Emptiness of these tables is a blocker, not a warning.
REQUIRED_NON_EMPTY: frozenset[str] = frozenset({"parcelas_catastro"})


@dataclass(frozen=True)
class TableReport:
    """Row count for one prerequisite table. ``rows is None`` → table missing."""

    table: str
    rows: int | None

    @property
    def missing(self) -> bool:
        return self.rows is None

    @property
    def blocking(self) -> bool:
        """A required table that is missing OR empty blocks the deployment."""
        return self.table in REQUIRED_NON_EMPTY and not self.rows


def table_row_count(db: Session, table: str) -> int | None:
    """Return the row count of ``table``, or ``None`` when it does not exist.

    ``to_regclass`` is the non-throwing existence probe: a missing table is a
    legitimate answer here (a database that never ran the migrations), not an
    exception to swallow later.
    """
    if table not in PREREQ_TABLES:
        raise ValueError(f"refusing to count unknown table: {table!r}")

    if db.execute(text("SELECT to_regclass(:table)"), {"table": table}).scalar() is None:
        return None

    # Safe interpolation: ``table`` is whitelisted against PREREQ_TABLES above.
    return int(db.execute(text(f"SELECT count(*) FROM {table}")).scalar_one())


def check_prereqs(db: Session) -> list[TableReport]:
    """Collect the row counts the operator has to paste into the PR body."""
    return [TableReport(table=name, rows=table_row_count(db, name)) for name in PREREQ_TABLES]


def format_report(reports: Sequence[TableReport]) -> str:
    """Render the check as the plain-text block that goes into the PR body."""
    lines = ["prerequisitos ficha territorial:"]
    for report in reports:
        if report.missing:
            state = "AUSENTE (la base no corrió las migraciones)"
        elif report.blocking:
            state = "0 filas — BLOQUEANTE para tipo=parcela"
        else:
            state = f"{report.rows} filas"
        lines.append(f"  - {report.table}: {state}")

    blockers = [report.table for report in reports if report.blocking]
    if blockers:
        lines.append(f"RESULTADO: BLOQUEANTE — {', '.join(blockers)} sin datos")
    else:
        lines.append("RESULTADO: OK")
    return "\n".join(lines)


def run_check_prereqs(db: Session) -> int:
    """Print the report and return the process exit code."""
    reports = check_prereqs(db)
    print(format_report(reports))
    return EXIT_PREREQ_FAILED if any(report.blocking for report in reports) else EXIT_OK


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m app.domains.geo.etl.load_suelos_catastro",
        description=(
            "Carga de suelos_catastro. Por ahora sólo está implementado "
            "--check-prereqs; la carga llega en el PR A1b."
        ),
    )
    parser.add_argument(
        "--check-prereqs",
        action="store_true",
        help="Reporta las filas de parcelas_catastro / suelos_catastro y sale "
        "distinto de cero si parcelas_catastro está vacía.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    if not args.check_prereqs:
        print(
            "sólo --check-prereqs está implementado en esta versión; "
            "la carga completa llega en el PR A1b",
            file=sys.stderr,
        )
        return EXIT_USAGE

    from app.db.session import SessionLocal

    with SessionLocal() as db:
        return run_check_prereqs(db)


if __name__ == "__main__":  # pragma: no cover — module entry point
    raise SystemExit(main())
