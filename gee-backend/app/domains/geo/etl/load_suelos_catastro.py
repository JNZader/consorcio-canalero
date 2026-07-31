"""Load ``suelos_cu.geojson`` into ``suelos_catastro``.

Run it inside the deployed backend container — the loader lives under ``app/``
and ships its own source data precisely so that it is runnable there::

    # carga completa (modo por defecto)
    docker compose exec backend python -m app.domains.geo.etl.load_suelos_catastro

    # ensayo: corre la carga y las aserciones, imprime el delta, NO escribe
    docker compose exec backend python -m app.domains.geo.etl.load_suelos_catastro --dry-run

    # sólo el chequeo de prerequisitos (gate de despliegue del PR A1a)
    docker compose exec backend python -m app.domains.geo.etl.load_suelos_catastro --check-prereqs

``gee-backend/Dockerfile:107`` copies only ``app/`` and ``alembic.ini`` into the
runtime image, so neither ``gee-backend/scripts/`` nor the repo-root ``scripts/``
exists in the container and the deployed host has no venv. Hence: module entry
point, source geojson as **package data**
(``app/domains/geo/etl/data/suelos_cu.geojson``, overridable with ``--source``),
never a repo-relative path. A test asserts the packaged copy is byte-identical to
``consorcio-web/public/data/suelos_cu.geojson``.

**Idempotence** = full refresh inside ONE transaction: ``DELETE`` → bulk insert →
assertions → ``COMMIT``. Re-running converges on the same row set, and it also
converges over rows loaded out-of-band (prod already holds these 45 rows). No
manual truncate is ever required.

**Assertions (all inside the load transaction; any failure → ROLLBACK → exit 3)**

1. stored row count == source feature count
2. every stored geometry valid under ``ST_IsValid`` — the source is repaired with
   ``ST_MakeValid`` first; an unrepairable feature aborts the load naming its ``gid``
3. every stored geometry SRID 4326
4. Σ hectares in EPSG:32720 within 1 % of the raw-source total
5. ``ip`` coerced int → str explicitly (source ``ip`` is an **int**, the column is
   ``String(50)`` — without the cast the insert is driver-dependent)
6. a NULL ``cap`` is valid source data (2 of 45 features) and never aborts

**Materialized view.** The final step refreshes ``mv_suelos_por_zona`` with
``REFRESH MATERIALIZED VIEW CONCURRENTLY``, which PostgreSQL forbids inside a
transaction block — so it runs on a separate AUTOCOMMIT connection *after* the
load commits. Consequence, and it is deliberate: the "assertions roll the load
back" guarantee covers **the load only**. A refresh that fails leaves the data
loaded and the view stale (exit 4, distinct from a load failure). The view has
**no readers today** — its consumer arrives in a later slice of this change, and
the ficha endpoint never reads it (it runs the same SQL parameterized by the
request geometry). So a stale view degrades nothing right now; the refresh is
kept correct because the consumer is coming, not because something breaks today.
Recovery is either re-running this command or the operator action
``POST /api/v2/admin/geo/suelos/refresh-mv`` (admin-only).

**Destructive-source guard.** The load is a full replace, so a truncated or
wrong ``--source`` would silently wipe good rows. When ``--source`` is given and
it carries fewer than half the rows currently stored, the load refuses unless
``--force`` is passed. The packaged source is not gated: it *is* the reference
data set.

Exit codes:
    0  success
    1  ``parcelas_catastro`` missing or empty (deployment blocker for tipo=parcela)
    2  invalid invocation (bad flag combination, ``--source`` that does not exist)
    3  load aborted by an assertion or by the destructive-source guard — table
       left in its prior state
    4  load committed but the view refresh failed — data loaded, view STALE
    5  infrastructure failure (unreadable/corrupt source, database error) — the
       load never completed; the table is unchanged
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from importlib.resources import as_file, files
import json
from pathlib import Path
import sys
from typing import Any, Sequence

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

EXIT_OK = 0
EXIT_PREREQ_FAILED = 1
EXIT_USAGE = 2
EXIT_LOAD_FAILED = 3
EXIT_REFRESH_FAILED = 4
EXIT_INFRA_FAILED = 5

#: Tables reported by ``--check-prereqs``. Also the identifier whitelist for
#: :func:`table_row_count` — these names are interpolated into SQL, so nothing
#: outside this tuple is ever accepted.
PREREQ_TABLES: tuple[str, ...] = ("parcelas_catastro", "suelos_catastro")

#: Emptiness of these tables is a blocker, not a warning.
REQUIRED_NON_EMPTY: frozenset[str] = frozenset({"parcelas_catastro"})

#: Package (not filesystem) location of the shipped source file.
PACKAGE_DATA_ANCHOR = "app.domains.geo.etl"
PACKAGE_DATA_NAME = "data/suelos_cu.geojson"

#: Assertion 4 tolerance: |Σ ha stored − Σ ha source| / Σ ha source.
HECTARE_TOLERANCE = 0.01

MATERIALIZED_VIEW = "mv_suelos_por_zona"

#: Destructive-source guard: an explicit ``--source`` carrying less than this
#: fraction of the rows already stored is refused unless ``--force`` is passed.
DESTRUCTIVE_SOURCE_RATIO = 0.5


class EtlAssertionError(RuntimeError):
    """A load-time assertion failed. Always raised *before* COMMIT."""


class EtlUsageError(RuntimeError):
    """The command was invoked wrong. Nothing was ever attempted against the DB.

    Distinct from :class:`EtlAssertionError` on purpose: an invocation error is
    not a load abort, so it must not claim a rollback that never happened.
    """


# ─────────────────────────────────────────────────────────────────────────────
# Prerequisites (PR A1a)
# ─────────────────────────────────────────────────────────────────────────────


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


# ─────────────────────────────────────────────────────────────────────────────
# Source parsing
# ─────────────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class SourceFeature:
    """One source feature, already coerced to what the columns accept.

    ``ip`` is a **str** here on purpose: the source ships it as an int and
    ``suelos_catastro.ip`` is ``String(50)`` (assertion 5). The coercion happens
    at parse time so nothing downstream can hand the driver an int and hope.
    """

    gid: int | None
    simbolo: str
    cap: str | None
    ip: str | None
    geometry_json: str


def read_source(path: Path) -> list[SourceFeature]:
    """Parse a GeoJSON FeatureCollection into coerced source features."""
    with path.open(encoding="utf-8") as handle:
        payload = json.load(handle)
    return parse_features(payload)


def parse_features(payload: Any) -> list[SourceFeature]:
    """Validate the FeatureCollection shape and coerce every attribute.

    Fails loudly on anything unexpected: a silently skipped feature would break
    assertion 1 far away from its cause.
    """
    if not isinstance(payload, dict) or payload.get("type") != "FeatureCollection":
        raise EtlAssertionError("el origen no es un FeatureCollection GeoJSON")

    raw_features = payload.get("features")
    if not isinstance(raw_features, list) or not raw_features:
        raise EtlAssertionError("el FeatureCollection no tiene features")

    features: list[SourceFeature] = []
    for index, raw in enumerate(raw_features):
        properties = raw.get("properties") or {}
        geometry = raw.get("geometry")
        gid = properties.get("gid")
        if not isinstance(geometry, dict):
            raise EtlAssertionError(f"feature #{index} (gid={gid}) sin geometría")

        simbolo = properties.get("simbolo")
        if not simbolo:
            raise EtlAssertionError(f"feature #{index} (gid={gid}) sin simbolo")

        ip = properties.get("ip")
        cap = properties.get("cap")
        features.append(
            SourceFeature(
                gid=gid,
                simbolo=str(simbolo),
                # Assertion 6: a NULL cap is valid source data, never an abort.
                cap=None if cap is None else str(cap),
                # Assertion 5: int → str, explicitly, never driver-dependent.
                ip=None if ip is None else str(ip),
                geometry_json=json.dumps(geometry),
            )
        )
    return features


# ─────────────────────────────────────────────────────────────────────────────
# Load
# ─────────────────────────────────────────────────────────────────────────────

# ``ST_MakeValid`` repairs self-intersections; the repair can yield a
# GeometryCollection, so ``ST_CollectionExtract(..., 3)`` keeps only the polygonal
# part and ``ST_Multi`` matches the MULTIPOLYGON column. The SRID is set
# explicitly instead of trusting the GeoJSON default (assertion 3).
_INSERT_SQL = text("""
    INSERT INTO suelos_catastro (simbolo, cap, ip, geometria)
    VALUES (
        :simbolo, :cap, :ip,
        ST_SetSRID(
            ST_Multi(ST_CollectionExtract(ST_MakeValid(ST_GeomFromGeoJSON(:geom)), 3)),
            4326
        )
    )
    RETURNING ST_IsValid(geometria), ST_IsEmpty(geometria), ST_SRID(geometria)
""")

_SOURCE_AREA_SQL = text("SELECT ST_Area(ST_Transform(ST_GeomFromGeoJSON(:geom), 32720)) / 10000.0")

_STORED_AREA_SQL = text(
    "SELECT coalesce(sum(ST_Area(ST_Transform(geometria, 32720))), 0) / 10000.0 "
    "FROM suelos_catastro"
)


def source_total_hectares(db: Session, features: Sequence[SourceFeature]) -> float:
    """Σ ha of the **raw** source geometries in EPSG:32720.

    Raw on purpose: comparing the stored (repaired) total against a repaired
    source total would compare a number with itself. The 1 % tolerance exists to
    catch a repair that silently dropped area.
    """
    total = 0.0
    for feature in features:
        total += float(
            db.execute(_SOURCE_AREA_SQL, {"geom": feature.geometry_json}).scalar_one() or 0.0
        )
    return total


def insert_features(db: Session, features: Sequence[SourceFeature]) -> None:
    """Insert every feature, validating each one as it lands (assertions 2 & 3).

    Per-row rather than one executemany because the abort has to name the
    offending ``gid`` — ``suelos_catastro`` has no ``gid`` column, so the
    attribution is only available here.
    """
    for feature in features:
        valid, empty, srid = db.execute(
            _INSERT_SQL,
            {
                "simbolo": feature.simbolo,
                "cap": feature.cap,
                "ip": feature.ip,
                "geom": feature.geometry_json,
            },
        ).one()

        if empty:
            raise EtlAssertionError(
                f"geometría irreparable en gid={feature.gid} (simbolo={feature.simbolo!r}): "
                "ST_MakeValid no dejó ninguna parte poligonal"
            )
        if not valid:
            raise EtlAssertionError(
                f"geometría inválida tras ST_MakeValid en gid={feature.gid} "
                f"(simbolo={feature.simbolo!r})"
            )
        if srid != 4326:
            raise EtlAssertionError(f"SRID {srid} != 4326 en gid={feature.gid}")


def assert_row_count(db: Session, expected: int) -> int:
    """Assertion 1 — stored rows must equal the source feature count."""
    stored = int(db.execute(text("SELECT count(*) FROM suelos_catastro")).scalar_one())
    if stored != expected:
        raise EtlAssertionError(
            f"filas insertadas {stored} != features del origen {expected}; se aborta la carga"
        )
    return stored


def assert_geometries_are_sane(db: Session) -> None:
    """Assertions 2 & 3, table-wide — belt and braces over the per-row checks."""
    invalid = int(
        db.execute(
            text("SELECT count(*) FROM suelos_catastro WHERE NOT ST_IsValid(geometria)")
        ).scalar_one()
    )
    if invalid:
        raise EtlAssertionError(f"{invalid} geometrías inválidas en suelos_catastro")

    wrong_srid = int(
        db.execute(
            text("SELECT count(*) FROM suelos_catastro WHERE ST_SRID(geometria) <> 4326")
        ).scalar_one()
    )
    if wrong_srid:
        raise EtlAssertionError(f"{wrong_srid} geometrías con SRID != 4326")


def assert_total_hectares(db: Session, source_ha: float) -> float:
    """Assertion 4 — stored Σ ha within 1 % of the source Σ ha."""
    stored_ha = float(db.execute(_STORED_AREA_SQL).scalar_one())
    if source_ha <= 0:
        raise EtlAssertionError("el origen tiene superficie total 0 ha")

    drift = abs(stored_ha - source_ha) / source_ha
    if drift > HECTARE_TOLERANCE:
        raise EtlAssertionError(
            f"superficie almacenada {stored_ha:.2f} ha vs origen {source_ha:.2f} ha "
            f"(desvío {drift:.2%} > {HECTARE_TOLERANCE:.0%})"
        )
    return stored_ha


@dataclass(frozen=True)
class LoadResult:
    """What the operator has to record in the PR body."""

    rows_before: int
    rows_after: int
    hectares: float
    committed: bool

    def render(self) -> str:
        verb = "cargado" if self.committed else "ENSAYO (rollback, no se escribió)"
        return (
            f"carga de suelos_catastro [{verb}]\n"
            f"  - filas antes:   {self.rows_before}\n"
            f"  - filas después: {self.rows_after}\n"
            f"  - superficie:    {self.hectares:.2f} ha (EPSG:32720)"
        )


def load(db: Session, features: Sequence[SourceFeature], *, dry_run: bool = False) -> LoadResult:
    """Full refresh in ONE transaction: DELETE → insert → assertions → COMMIT.

    ``dry_run`` runs the whole thing, assertions included, and rolls back — so an
    ensayo proves the load *would* succeed instead of merely counting features.
    Any assertion failure rolls back and propagates :class:`EtlAssertionError`.
    """
    rows_before = int(db.execute(text("SELECT count(*) FROM suelos_catastro")).scalar_one())
    try:
        source_ha = source_total_hectares(db, features)

        # Full replace: the only shape of idempotence that also converges over
        # rows loaded out-of-band (prod holds these 45 already).
        db.execute(text("DELETE FROM suelos_catastro"))
        insert_features(db, features)

        rows_after = assert_row_count(db, len(features))
        assert_geometries_are_sane(db)
        stored_ha = assert_total_hectares(db, source_ha)

        if dry_run:
            db.rollback()
            return LoadResult(rows_before, rows_after, stored_ha, committed=False)

        db.commit()
        return LoadResult(rows_before, rows_after, stored_ha, committed=True)
    except Exception:
        db.rollback()
        raise


def refresh_materialized_view(db: Session) -> int:
    """``REFRESH ... CONCURRENTLY`` on a separate AUTOCOMMIT connection.

    PostgreSQL forbids ``REFRESH MATERIALIZED VIEW CONCURRENTLY`` inside a
    transaction block, so this MUST run after the load commits and MUST NOT
    share the load's session transaction. Returns the view's row count.

    A failed concurrent refresh falls back to a plain ``REFRESH`` — same
    precedent as ``intelligence/repository_metrics.py`` — because a view that is
    correct while briefly locking readers beats a view that stays stale. The
    usual cause is a database still on 0015's schema, whose view has no unique
    index and therefore cannot be refreshed concurrently at all; the fix for
    that one is ``alembic upgrade head``, and the warning says so.
    """
    engine = db.get_bind().engine
    with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as conn:
        try:
            conn.execute(text(f"REFRESH MATERIALIZED VIEW CONCURRENTLY {MATERIALIZED_VIEW}"))
        except Exception as exc:  # noqa: BLE001 — the fallback IS the handling
            conn.rollback()
            print(
                f"refresco CONCURRENTLY de {MATERIALIZED_VIEW} falló ({exc}); "
                "se reintenta con REFRESH común, que bloquea lectores. Si la base "
                "quedó en el esquema de 0015 la vista no tiene índice único y el "
                "modo concurrente NUNCA va a andar: correr `alembic upgrade head`.",
                file=sys.stderr,
            )
            conn.execute(text(f"REFRESH MATERIALIZED VIEW {MATERIALIZED_VIEW}"))
        return int(conn.execute(text(f"SELECT count(*) FROM {MATERIALIZED_VIEW}")).scalar_one())


def resolve_source(explicit: str | None) -> Path:
    """``--source`` wins; otherwise the geojson packaged inside the image.

    Resolved through ``importlib.resources`` — never a repo-relative path, which
    would not exist in the container (JDB-002).
    """
    if explicit:
        path = Path(explicit)
        if not path.is_file():
            raise EtlUsageError(f"--source no existe: {path}")
        return path

    resource = files(PACKAGE_DATA_ANCHOR).joinpath(PACKAGE_DATA_NAME)
    with as_file(resource) as path:
        return Path(path)


def assert_source_is_not_destructive(
    db: Session,
    features: Sequence[SourceFeature],
    *,
    explicit_source: bool,
    force: bool,
) -> None:
    """Refuse an explicit ``--source`` that would wipe most of the table.

    The load is a full replace, so a truncated or plain wrong ``--source`` is
    indistinguishable from a legitimate one until the rows are already gone.
    Only the explicit source is gated: the packaged copy *is* the reference data
    set, and gating it would block the intended re-run.
    """
    if not explicit_source or force:
        return

    stored = int(db.execute(text("SELECT count(*) FROM suelos_catastro")).scalar_one())
    if stored and len(features) < stored * DESTRUCTIVE_SOURCE_RATIO:
        raise EtlAssertionError(
            f"el origen trae {len(features)} features y suelos_catastro tiene {stored} "
            f"filas (menos de la mitad): la carga es un reemplazo completo y perdería "
            "datos. Verificar el --source, o pasar --force si es deliberado. "
            "Refusing to destroy data silently."
        )


def _report_infra_failure(exc: BaseException) -> int:
    """Print the actionable message for a non-assertion failure and give its code."""
    print(
        f"FALLO DE INFRAESTRUCTURA: {type(exc).__name__}: {exc}\n"
        "no es una aserción de la carga: el origen no se pudo leer/parsear o la base "
        "falló. suelos_catastro quedó sin cambios. Revisar que el GeoJSON sea legible "
        "y válido, que la base esté accesible y que las migraciones estén aplicadas "
        "(`alembic upgrade head`), y volver a correr el comando.",
        file=sys.stderr,
    )
    return EXIT_INFRA_FAILED


def run_load(
    db: Session,
    *,
    source: str | None = None,
    dry_run: bool = False,
    force: bool = False,
) -> int:
    """Parse, load and refresh. Returns the process exit code."""
    try:
        features = read_source(resolve_source(source))
        assert_source_is_not_destructive(
            db, features, explicit_source=source is not None, force=force
        )
        result = load(db, features, dry_run=dry_run)
    except EtlUsageError as exc:
        print(f"INVOCACIÓN INVÁLIDA: {exc}", file=sys.stderr)
        return EXIT_USAGE
    except EtlAssertionError as exc:
        print(f"CARGA ABORTADA: {exc}", file=sys.stderr)
        print("suelos_catastro quedó en su estado anterior (sin cambios)", file=sys.stderr)
        return EXIT_LOAD_FAILED
    except (json.JSONDecodeError, OSError, SQLAlchemyError) as exc:
        return _report_infra_failure(exc)
    except Exception as exc:  # noqa: BLE001 — the exit code IS the handling
        return _report_infra_failure(exc)

    print(result.render())

    if dry_run:
        print(f"ensayo: no se refrescó {MATERIALIZED_VIEW}")
        return EXIT_OK

    try:
        view_rows = refresh_materialized_view(db)
    except Exception as exc:  # noqa: BLE001 — the exit code IS the handling
        print(
            f"DATOS CARGADOS pero {MATERIALIZED_VIEW} quedó DESACTUALIZADA: {exc}\n"
            "recuperación: POST /api/v2/admin/geo/suelos/refresh-mv (admin) "
            "o volver a correr este comando",
            file=sys.stderr,
        )
        return EXIT_REFRESH_FAILED

    print(f"  - {MATERIALIZED_VIEW}: {view_rows} filas tras el refresh concurrente")
    return EXIT_OK


# ─────────────────────────────────────────────────────────────────────────────
# Entry point
# ─────────────────────────────────────────────────────────────────────────────


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m app.domains.geo.etl.load_suelos_catastro",
        description=(
            "Carga suelos_cu.geojson en suelos_catastro (refresco completo en una "
            "transacción) y refresca mv_suelos_por_zona al final."
        ),
    )
    parser.add_argument(
        "--check-prereqs",
        action="store_true",
        help="Sólo reporta las filas de parcelas_catastro / suelos_catastro y sale "
        "distinto de cero si parcelas_catastro está vacía. No carga nada.",
    )
    parser.add_argument(
        "--source",
        default=None,
        help="Ruta alternativa al GeoJSON de origen (por defecto, la copia "
        "empaquetada dentro de la imagen).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Corre la carga y las aserciones, imprime el delta y hace rollback.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Permite que un --source con menos de la mitad de las filas actuales "
        "reemplace la tabla igual. Sin este flag esa carga se rechaza.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    # Mutually exclusive on purpose: --check-prereqs never writes, so combining
    # it with load flags can only mean the operator expected a load that would
    # silently not happen.
    if args.check_prereqs and (args.source or args.dry_run or args.force):
        print(
            "--check-prereqs no se combina con --source/--dry-run/--force: "
            "es un modo de sólo lectura",
            file=sys.stderr,
        )
        return EXIT_USAGE

    from app.db.session import SessionLocal

    with SessionLocal() as db:
        if args.check_prereqs:
            return run_check_prereqs(db)
        return run_load(db, source=args.source, dry_run=args.dry_run, force=args.force)


if __name__ == "__main__":  # pragma: no cover — module entry point
    raise SystemExit(main())
