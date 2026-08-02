"""Load the curated consorcio canals into ``canal_consorcio``.

Run it inside the deployed backend container — the loader lives under ``app/`` and
ships its own source data precisely so that it is runnable there::

    # carga completa (modo por defecto)
    docker compose exec backend python -m app.domains.geo.etl.load_canales_consorcio

    # ensayo: corre la carga y las aserciones, imprime el delta, NO escribe
    docker compose exec backend python -m app.domains.geo.etl.load_canales_consorcio --dry-run

``gee-backend/Dockerfile`` copies only ``app/`` and ``alembic.ini`` into the
runtime image, so neither ``gee-backend/scripts/`` nor the repo-root ``scripts/``
exists in the container and the deployed host has no venv. Hence: module entry
point, source GeoJSONs as **package data**
(``app/domains/geo/etl/data/relevados.geojson`` + ``propuestas.geojson``), never a
repo-relative path. These are byte-copies of
``consorcio-web/public/capas/canales/{relevados,propuestas}.geojson`` — the 41
relevados + 19 propuestos the consorcio actually manages (60 canals total).

**The two sources fix ``estado``.** Each bundled file IS one ``estado`` family:
``relevados.geojson`` → ``relevado``, ``propuestas.geojson`` → ``propuesto``. Every
feature also carries ``properties.estado``; the loader cross-checks the two and
aborts loudly on a mismatch rather than trusting one silently.

**Idempotence = UPSERT on the string id.** Each feature is inserted
``ON CONFLICT (id) DO UPDATE``, so a re-run converges on the same 60 rows and also
converges over rows loaded out-of-band. No truncate is ever required, and a canal
that already has computed catchments keeps its ``canal_ref`` (the FK target does
not move). The whole load runs in ONE transaction: any assertion failure →
ROLLBACK → the table is left in its prior state.

**Assertions (all inside the load transaction; any failure → ROLLBACK → exit 3)**

1. stored row count == source feature count (60)
2. every stored geometry valid under ``ST_IsValid`` — the source is repaired with
   ``ST_MakeValid`` first; an unrepairable / non-LineString feature aborts naming
   its ``id``
3. every stored geometry SRID 4326 and a LineString
4. ``estado`` of every stored row is one of ``relevado`` / ``propuesto`` (the CHECK
   constraint enforces this too; the assertion attributes it to an ``id``)

Exit codes:
    0  success
    2  invalid invocation
    3  load aborted by an assertion — table left in its prior state
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
EXIT_USAGE = 2
EXIT_LOAD_FAILED = 3
EXIT_INFRA_FAILED = 5

#: Package (not filesystem) location of the shipped source files, each paired with
#: the ``estado`` family it represents. The file is the authority on ``estado``;
#: ``properties.estado`` is cross-checked against it.
PACKAGE_DATA_ANCHOR = "app.domains.geo.etl"
BUNDLED_SOURCES: tuple[tuple[str, str], ...] = (
    ("data/relevados.geojson", "relevado"),
    ("data/propuestas.geojson", "propuesto"),
)

VALID_ESTADOS: frozenset[str] = frozenset({"relevado", "propuesto"})


class EtlAssertionError(RuntimeError):
    """A load-time assertion failed. Always raised *before* COMMIT."""


class EtlUsageError(RuntimeError):
    """The command was invoked wrong. Nothing was ever attempted against the DB."""


# ─────────────────────────────────────────────────────────────────────────────
# Source parsing
# ─────────────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class SourceFeature:
    """One curated canal, coerced to what ``canal_consorcio`` accepts.

    ``longitud_m`` is a float-or-None; ``prioridad`` a str-or-None (relevados carry
    none, propuestas carry a label). ``estado`` is the file-family value, already
    cross-checked against ``properties.estado``.
    """

    id: str
    nombre: str
    estado: str
    prioridad: str | None
    longitud_m: float | None
    geometry_json: str


def read_source(path: Path, expected_estado: str) -> list[SourceFeature]:
    """Parse one GeoJSON FeatureCollection into coerced source features."""
    with path.open(encoding="utf-8") as handle:
        payload = json.load(handle)
    return parse_features(payload, expected_estado)


def parse_features(payload: Any, expected_estado: str) -> list[SourceFeature]:
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
        canal_id = properties.get("id")
        if not canal_id or not isinstance(canal_id, str):
            raise EtlAssertionError(f"feature #{index} sin id de canal (string)")
        if not isinstance(geometry, dict):
            raise EtlAssertionError(f"feature id={canal_id!r} sin geometría")
        if geometry.get("type") != "LineString":
            raise EtlAssertionError(
                f"feature id={canal_id!r} no es LineString (es {geometry.get('type')!r})"
            )

        nombre = properties.get("nombre")
        if not nombre:
            raise EtlAssertionError(f"feature id={canal_id!r} sin nombre")

        estado = properties.get("estado")
        if estado is not None and estado != expected_estado:
            raise EtlAssertionError(
                f"feature id={canal_id!r} declara estado {estado!r} pero el archivo "
                f"es de la familia {expected_estado!r}: origen inconsistente"
            )

        longitud_m = properties.get("longitud_m")
        if longitud_m is not None and not isinstance(longitud_m, (int, float)):
            raise EtlAssertionError(
                f"feature id={canal_id!r} tiene longitud_m no numérico: {longitud_m!r}"
            )

        prioridad = properties.get("prioridad")
        features.append(
            SourceFeature(
                id=canal_id,
                nombre=str(nombre),
                estado=expected_estado,
                prioridad=None if prioridad is None else str(prioridad),
                longitud_m=None if longitud_m is None else float(longitud_m),
                geometry_json=json.dumps(geometry),
            )
        )
    return features


def read_all_sources(sources: Sequence[tuple[Path, str]]) -> list[SourceFeature]:
    """Parse every bundled source and reject a duplicate id across files."""
    features: list[SourceFeature] = []
    seen: dict[str, str] = {}
    for path, expected_estado in sources:
        for feature in read_source(path, expected_estado):
            prior = seen.get(feature.id)
            if prior is not None:
                raise EtlAssertionError(
                    f"id de canal duplicado {feature.id!r} (visto en {prior!r} y "
                    f"{expected_estado!r})"
                )
            seen[feature.id] = expected_estado
            features.append(feature)
    return features


# ─────────────────────────────────────────────────────────────────────────────
# Load
# ─────────────────────────────────────────────────────────────────────────────

# ``ST_MakeValid`` repairs a malformed line; ``ST_LineMerge`` collapses a repaired
# MultiLineString back to a single LineString when the repair split it, and the
# SRID is set explicitly instead of trusting the GeoJSON default (assertion 3).
_UPSERT_SQL = text("""
    INSERT INTO canal_consorcio (id, nombre, estado, prioridad, longitud_m, geom)
    VALUES (
        :id, :nombre, :estado, :prioridad, :longitud_m,
        ST_SetSRID(ST_LineMerge(ST_MakeValid(ST_GeomFromGeoJSON(:geom))), 4326)
    )
    ON CONFLICT (id) DO UPDATE SET
        nombre = EXCLUDED.nombre,
        estado = EXCLUDED.estado,
        prioridad = EXCLUDED.prioridad,
        longitud_m = EXCLUDED.longitud_m,
        geom = EXCLUDED.geom,
        updated_at = now()
    RETURNING ST_IsValid(geom), ST_IsEmpty(geom), ST_SRID(geom), GeometryType(geom)
""")


def upsert_features(db: Session, features: Sequence[SourceFeature]) -> None:
    """UPSERT every feature, validating each one as it lands (assertions 2 & 3).

    Per-row rather than one executemany because the abort has to name the
    offending ``id``.
    """
    for feature in features:
        valid, empty, srid, geom_type = db.execute(
            _UPSERT_SQL,
            {
                "id": feature.id,
                "nombre": feature.nombre,
                "estado": feature.estado,
                "prioridad": feature.prioridad,
                "longitud_m": feature.longitud_m,
                "geom": feature.geometry_json,
            },
        ).one()

        if empty:
            raise EtlAssertionError(
                f"geometría irreparable en id={feature.id!r}: ST_MakeValid no dejó ninguna línea"
            )
        if not valid:
            raise EtlAssertionError(f"geometría inválida tras ST_MakeValid en id={feature.id!r}")
        if srid != 4326:
            raise EtlAssertionError(f"SRID {srid} != 4326 en id={feature.id!r}")
        if geom_type != "LINESTRING":
            raise EtlAssertionError(f"geometría {geom_type!r} != LINESTRING en id={feature.id!r}")


def assert_row_count(db: Session, expected: int) -> int:
    """Assertion 1 — stored rows must equal the source feature count.

    A strict equality also proves the UPSERT converged: re-running must not grow
    the table past the 60 curated canals.
    """
    stored = int(db.execute(text("SELECT count(*) FROM canal_consorcio")).scalar_one())
    if stored != expected:
        raise EtlAssertionError(
            f"filas en canal_consorcio {stored} != features del origen {expected}"
        )
    return stored


def counts_by_estado(db: Session) -> dict[str, int]:
    """Rows grouped by ``estado`` — the relevado/propuesto tally the PR records."""
    rows = db.execute(text("SELECT estado, count(*) FROM canal_consorcio GROUP BY estado")).all()
    return {estado: int(n) for estado, n in rows}


@dataclass(frozen=True)
class LoadResult:
    """What the operator has to record in the PR body."""

    rows_before: int
    rows_after: int
    by_estado: dict[str, int]
    committed: bool

    def render(self) -> str:
        verb = "cargado" if self.committed else "ENSAYO (rollback, no se escribió)"
        relevado = self.by_estado.get("relevado", 0)
        propuesto = self.by_estado.get("propuesto", 0)
        return (
            f"carga de canal_consorcio [{verb}]\n"
            f"  - filas antes:   {self.rows_before}\n"
            f"  - filas después: {self.rows_after}\n"
            f"  - relevados:     {relevado}\n"
            f"  - propuestas:    {propuesto}"
        )


def load(db: Session, features: Sequence[SourceFeature], *, dry_run: bool = False) -> LoadResult:
    """UPSERT every curated canal in ONE transaction, then assert & COMMIT.

    ``dry_run`` runs the whole thing, assertions included, and rolls back. Any
    assertion failure rolls back and propagates :class:`EtlAssertionError`.
    """
    rows_before = int(db.execute(text("SELECT count(*) FROM canal_consorcio")).scalar_one())
    try:
        upsert_features(db, features)
        rows_after = assert_row_count(db, len(features))
        by_estado = counts_by_estado(db)

        # Belt-and-braces: no stored estado outside the CHECK domain (attributed).
        bad = db.execute(
            text("SELECT id FROM canal_consorcio WHERE estado NOT IN ('relevado', 'propuesto')")
        ).all()
        if bad:
            raise EtlAssertionError(f"estados fuera de dominio en ids={[r.id for r in bad]}")

        if dry_run:
            db.rollback()
            return LoadResult(rows_before, rows_after, by_estado, committed=False)

        db.commit()
        return LoadResult(rows_before, rows_after, by_estado, committed=True)
    except Exception:
        db.rollback()
        raise


# ─────────────────────────────────────────────────────────────────────────────
# Source resolution
# ─────────────────────────────────────────────────────────────────────────────


def resolve_sources() -> list[tuple[Path, str]]:
    """Resolve the two bundled GeoJSONs through ``importlib.resources``.

    Never a repo-relative path, which would not exist in the container.
    """
    resolved: list[tuple[Path, str]] = []
    for name, estado in BUNDLED_SOURCES:
        resource = files(PACKAGE_DATA_ANCHOR).joinpath(name)
        with as_file(resource) as path:
            resolved.append((Path(path), estado))
    return resolved


def _report_infra_failure(exc: BaseException) -> int:
    """Print the actionable message for a non-assertion failure and give its code."""
    print(
        f"FALLO DE INFRAESTRUCTURA: {type(exc).__name__}: {exc}\n"
        "no es una aserción de la carga: el origen no se pudo leer/parsear o la base "
        "falló. canal_consorcio quedó sin cambios. Revisar que los GeoJSON sean "
        "legibles y válidos, que la base esté accesible y que las migraciones estén "
        "aplicadas (`alembic upgrade head`), y volver a correr el comando.",
        file=sys.stderr,
    )
    return EXIT_INFRA_FAILED


def run_load(db: Session, *, dry_run: bool = False) -> int:
    """Parse and load the bundled canals. Returns the process exit code."""
    try:
        features = read_all_sources(resolve_sources())
        result = load(db, features, dry_run=dry_run)
    except EtlUsageError as exc:
        print(f"INVOCACIÓN INVÁLIDA: {exc}", file=sys.stderr)
        return EXIT_USAGE
    except EtlAssertionError as exc:
        print(f"CARGA ABORTADA: {exc}", file=sys.stderr)
        print("canal_consorcio quedó en su estado anterior (sin cambios)", file=sys.stderr)
        return EXIT_LOAD_FAILED
    except (json.JSONDecodeError, OSError, SQLAlchemyError) as exc:
        return _report_infra_failure(exc)
    except Exception as exc:  # noqa: BLE001 — the exit code IS the handling
        return _report_infra_failure(exc)

    print(result.render())
    return EXIT_OK


# ─────────────────────────────────────────────────────────────────────────────
# Entry point
# ─────────────────────────────────────────────────────────────────────────────


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m app.domains.geo.etl.load_canales_consorcio",
        description=(
            "Carga los 60 canales curados del consorcio (41 relevados + 19 "
            "propuestos) en canal_consorcio (UPSERT idempotente en una transacción)."
        ),
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Corre la carga y las aserciones, imprime el delta y hace rollback.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    from app.db.session import SessionLocal  # noqa: PLC0415

    with SessionLocal() as db:
        return run_load(db, dry_run=args.dry_run)


if __name__ == "__main__":  # pragma: no cover — module entry point
    raise SystemExit(main())
