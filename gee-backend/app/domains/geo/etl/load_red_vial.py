"""Load the provincial road network into ``red_vial``.

Run it inside the deployed backend container — the loader lives under ``app/``
and ships its own source data precisely so that it is runnable there::

    # carga completa (modo por defecto)
    docker compose exec backend python -m app.domains.geo.etl.load_red_vial

    # ensayo: corre la carga, las aserciones y el reporte, NO escribe
    docker compose exec backend python -m app.domains.geo.etl.load_red_vial --dry-run

``gee-backend/Dockerfile`` copies only ``app/`` and ``alembic.ini`` into the
runtime image, so the source is **package data**
(``app/domains/geo/etl/data/red_vial.geojson``), never a repo-relative path —
the same constraint that shapes ``load_canales_consorcio``.

**Provenance of the package data.** ``red_vial.geojson`` is a one-off,
authoring-time conversion of the repository file ``gee/red_vial/caminoss.kml``:

* source path: ``gee/red_vial/caminoss.kml``
* source sha256:
  ``c53ca6f3d0b3f785b41b76d2919a81ea7e4dd340b688d395a1311d786323c836``
  (re-checkable with ``sha256sum gee/red_vial/caminoss.kml``)
* converted on 2026-08-22, one GeoJSON Feature per KML ``<Placemark>``, in
  document order, carrying the eleven IDECOR ``<SimpleData>`` attributes and the
  ``<MultiGeometry>``'s ``<LineString>`` coordinates verbatim (a Placemark with
  several LineStrings becomes a ``MultiLineString``, which the load then collapses
  with ``ST_LineMerge`` — or aborts on, see below).
* **NOT** ``gee/red_vial_provincial.kml``: that is a different, province-wide
  39 127-feature file and is not this layer.

GeoJSON rather than KML so the loader reuses the ``json.load`` +
``parse_features`` shape of the canal loader and adds no XML dependency.

**The docstring is not the pin.** ``RED_VIAL_FEATURE_COUNT`` is: assertion 0
compares the parsed feature count against it and aborts the whole load on a
mismatch, so a truncated or silently re-converted file can never load partially.
The constant is a claim about the source — changing the source means changing it
deliberately, in the same commit.

**Identity, and why there are two ids.** ``id`` is the row identity that
``cruce_camino`` and ``relevamiento_tramo`` reference; ``source_id`` is what the
source publishes. For each source feature the loader resolves **the active row
with that ``source_id``** — never "the row whose PK equals the id":

* no active row → INSERT, ``id = source_id`` when free, next free ordinal suffix
  (``28188#2``, ``28188#3``, …) otherwise;
* active row, unchanged or trivially-changed geometry → UPDATE in place;
* active row, **materially changed** geometry (``geom_hash`` differs AND the
  Hausdorff distance to the stored trace exceeds one DEM cell, 30 m) → the
  existing row is **retired** (``activo = false``, PK and dependents intact) and
  the new trace is INSERTed as a new row with the SAME ``source_id`` and the next
  free suffixed PK.

Ids present in the table and absent from the source are likewise **retired**.
**The loader never issues a row-removing statement, ever** — a crossing or a
field survey is never orphaned, and a road that comes back is a new row, not a
re-used identity. Every UPSERT stamps ``ultima_carga_en`` (with
``clock_timestamp()``, so two loads in one transaction are still two events),
including the case that changes no attribute:
the load itself IS the event, because vertex order alone can invalidate a stored
crossing side.

**Assertions (all inside the load transaction; any failure → ROLLBACK → exit 3)**

0. parsed feature count == ``RED_VIAL_FEATURE_COUNT`` (the fidelity pin)
1. active row count == source feature count
2. every stored geometry valid under ``ST_IsValid`` — the source is repaired with
   ``ST_MakeValid`` first and the ``MultiGeometry`` wrapper collapsed with
   ``ST_LineMerge``; a feature surviving as a MultiLineString aborts **naming its
   id** rather than being silently split
3. every stored geometry SRID 4326 and a LineString
4. no geometry empty after the repair
5. **granularity verification** — feature count, min / median / p90 / max of
   ``ST_Length(geom::geography)``, the count of features whose measured length
   disagrees with the declared ``lzn`` by more than 10 %, and the ids of every
   feature beyond p99 or 5 km flagged ``OUTLIER — requiere decisión explícita``.
   Assertion 5 **reports and never corrects**: a long feature is loaded whole and
   the layer is never re-segmented. The same report names the ids retired by this
   load and every lineage split it performed.

Exit codes:
    0  success
    2  invalid invocation
    3  load aborted by an assertion — table left in its prior state
    5  infrastructure failure (unreadable/corrupt source, database error) — the
       load never completed; the table is unchanged
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass, field
import hashlib
from importlib.resources import as_file, files
import json
from pathlib import Path
import struct
import sys
from typing import Any, Final, Sequence

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

EXIT_OK = 0
EXIT_USAGE = 2
EXIT_LOAD_FAILED = 3
EXIT_INFRA_FAILED = 5

PACKAGE_DATA_ANCHOR = "app.domains.geo.etl"
BUNDLED_SOURCE = "data/red_vial.geojson"

#: Assertion 0. Derived at authoring time from the source KML's Placemark count
#: (``grep -c '<Placemark' gee/red_vial/caminoss.kml`` → 380).
RED_VIAL_FEATURE_COUNT: Final[int] = 380

#: The eleven source attributes, ten carried verbatim as TEXT plus ``lzn`` as a
#: float (declared length in km) handled separately.
TEXT_ATTRIBUTES: Final[tuple[str, ...]] = (
    "fna",
    "gna",
    "rtn",
    "fun",
    "rst",
    "hct",
    "ccn",
    "ccc",
    "rcc",
    "red",
)

#: One DEM cell (Copernicus GLO-30). Below it, a geometry change is "trivial" and
#: the row keeps its identity; above it the trace is a different road.
MATERIAL_CHANGE_M: Final[float] = 30.0

#: Metric CRS used everywhere in this repo for measurements (UTM 20S).
METRIC_SRID: Final[int] = 32720

#: A feature longer than this is an outlier regardless of the distribution.
OUTLIER_ABSOLUTE_M: Final[float] = 5_000.0

#: Tolerated disagreement between the measured length and the declared ``lzn``.
LZN_TOLERANCE: Final[float] = 0.10

#: ``ST_MakeValid`` repairs a malformed line, ``ST_LineMerge`` collapses the KML
#: ``MultiGeometry`` wrapper back to a single LineString, and the SRID is set
#: explicitly instead of trusting the GeoJSON default.
GEOM_EXPRESSION: Final[str] = (
    "ST_SetSRID(ST_LineMerge(ST_MakeValid(ST_GeomFromGeoJSON(:geom))), 4326)"
)


class EtlAssertionError(RuntimeError):
    """A load-time assertion failed. Always raised *before* COMMIT."""


class EtlUsageError(RuntimeError):
    """The command was invoked wrong. Nothing was ever attempted against the DB."""


# ─────────────────────────────────────────────────────────────────────────────
# Source parsing
# ─────────────────────────────────────────────────────────────────────────────


def _wkb(geometry: dict[str, Any]) -> bytes:
    """Little-endian WKB of a normalized LineString / MultiLineString.

    Hand-rolled rather than delegated to PostGIS because ``geom_hash`` has to be
    computable *before* the row reaches the database — it is what decides whether
    the row is an UPDATE or a retire-and-insert. Vertex order is part of the
    encoding on purpose: ``lado_cruce`` is defined relative to the segment's
    digitization direction, so a reversed trace is a changed trace.
    """
    geometry_type = geometry.get("type")
    coordinates = geometry.get("coordinates") or []
    if geometry_type == "LineString":
        parts = [coordinates]
        wkb_type = 2
    elif geometry_type == "MultiLineString":
        parts = list(coordinates)
        wkb_type = 5
    else:  # pragma: no cover — parse_features rejects everything else first
        raise EtlAssertionError(f"tipo de geometría no soportado: {geometry_type!r}")

    def line(points: Sequence[Sequence[float]]) -> bytes:
        buffer = struct.pack("<BII", 1, 2, len(points))
        for point in points:
            buffer += struct.pack("<dd", float(point[0]), float(point[1]))
        return buffer

    if wkb_type == 2:
        return line(parts[0])
    buffer = struct.pack("<BII", 1, 5, len(parts))
    for part in parts:
        buffer += line(part)
    return buffer


def geom_hash(geometry: dict[str, Any]) -> str:
    """sha256 of the WKB of the normalized geometry."""
    return hashlib.sha256(_wkb(geometry)).hexdigest()


@dataclass(frozen=True)
class SourceFeature:
    """One native road feature, coerced to what ``red_vial`` accepts."""

    source_id: str
    attributes: dict[str, str | None]
    lzn: float | None
    geometry_json: str
    geom_hash: str

    @classmethod
    def from_geojson(cls, raw: Any, index: int = 0) -> SourceFeature:
        """Coerce one GeoJSON Feature. Fails loudly, naming the id when it has one.

        A silently skipped feature would surface as an assertion-1 count mismatch
        far away from its cause, so nothing is ever skipped.
        """
        properties = (raw or {}).get("properties") or {}
        geometry = (raw or {}).get("geometry")
        source_id = properties.get("id")
        if source_id is None or not str(source_id).strip():
            raise EtlAssertionError(f"feature #{index} sin id de camino")
        source_id = str(source_id).strip()

        if not isinstance(geometry, dict):
            raise EtlAssertionError(f"feature id={source_id!r} sin geometría")
        if geometry.get("type") not in ("LineString", "MultiLineString"):
            raise EtlAssertionError(
                f"feature id={source_id!r} no es LineString ni MultiLineString "
                f"(es {geometry.get('type')!r})"
            )

        lzn = properties.get("lzn")
        if lzn is not None and str(lzn).strip() != "":
            try:
                lzn = float(lzn)
            except (TypeError, ValueError) as exc:
                raise EtlAssertionError(
                    f"feature id={source_id!r} tiene lzn no numérico: {lzn!r}"
                ) from exc
        else:
            lzn = None

        attributes: dict[str, str | None] = {}
        for name in TEXT_ATTRIBUTES:
            value = properties.get(name)
            attributes[name] = None if value is None else str(value)

        return cls(
            source_id=source_id,
            attributes=attributes,
            lzn=lzn,
            geometry_json=json.dumps(geometry),
            geom_hash=geom_hash(geometry),
        )


def parse_features(
    payload: Any, *, expected_count: int = RED_VIAL_FEATURE_COUNT
) -> list[SourceFeature]:
    """Validate the FeatureCollection, coerce every feature, honour the pin.

    ``expected_count`` is assertion 0. It defaults to the shipped pin; tests pass
    their own so a two-feature fixture is not forced to be 380 features long.
    """
    if not isinstance(payload, dict) or payload.get("type") != "FeatureCollection":
        raise EtlAssertionError("el origen no es un FeatureCollection GeoJSON")

    raw_features = payload.get("features")
    if not isinstance(raw_features, list):
        raise EtlAssertionError("el FeatureCollection no tiene features")

    if len(raw_features) != expected_count:
        raise EtlAssertionError(
            f"cantidad de features {len(raw_features)} != el pin del origen {expected_count}: "
            "el GeoJSON empaquetado no es la conversión declarada del KML de origen"
        )

    features: list[SourceFeature] = []
    seen: set[str] = set()
    for index, raw in enumerate(raw_features):
        parsed = SourceFeature.from_geojson(raw, index)
        if parsed.source_id in seen:
            raise EtlAssertionError(f"id de camino duplicado en el origen: {parsed.source_id!r}")
        seen.add(parsed.source_id)
        features.append(parsed)
    return features


def resolve_source() -> Path:
    """Resolve the bundled GeoJSON through ``importlib.resources``."""
    resource = files(PACKAGE_DATA_ANCHOR).joinpath(BUNDLED_SOURCE)
    with as_file(resource) as path:
        return Path(path)


def read_source(path: Path | None = None) -> list[SourceFeature]:
    """Parse the bundled (or given) GeoJSON into coerced source features."""
    path = path or resolve_source()
    with path.open(encoding="utf-8") as handle:
        payload = json.load(handle)
    return parse_features(payload)


# ─────────────────────────────────────────────────────────────────────────────
# Stored-geometry assertions (2–4)
# ─────────────────────────────────────────────────────────────────────────────


def assert_stored_geometry(
    feature_id: str,
    *,
    valid: bool,
    empty: bool,
    srid: int,
    geom_type: str,
) -> None:
    """Assertions 2-4 on one stored row, attributing every failure to its id."""
    if empty:
        raise EtlAssertionError(
            f"geometría irreparable en id={feature_id!r}: ST_MakeValid no dejó ninguna línea"
        )
    if not valid:
        raise EtlAssertionError(f"geometría inválida tras ST_MakeValid en id={feature_id!r}")
    if srid != 4326:
        raise EtlAssertionError(f"SRID {srid} != 4326 en id={feature_id!r}")
    if geom_type != "LINESTRING":
        raise EtlAssertionError(
            f"geometría {geom_type!r} != LINESTRING en id={feature_id!r}: la envoltura "
            "MultiGeometry no se pudo colapsar (partes desconectadas). El tramo NO se "
            "parte en silencio: requiere decisión explícita sobre el origen."
        )


# ─────────────────────────────────────────────────────────────────────────────
# Lineage
# ─────────────────────────────────────────────────────────────────────────────


def next_free_pk(source_id: str, taken: set[str]) -> str:
    """The PK a new row of this lineage gets: the source id, or the next free suffix.

    Derived from what already exists, never a fixed ``#2`` — after one split the
    fixed suffix would collide with the row the previous load created.
    """
    if source_id not in taken:
        return source_id
    ordinal = 2
    while f"{source_id}#{ordinal}" in taken:
        ordinal += 1
    return f"{source_id}#{ordinal}"


_LIKE_ESCAPE = str.maketrans({"\\": "\\\\", "%": "\\%", "_": "\\_"})

_SELECT_ACTIVE = text("SELECT id, geom_hash FROM red_vial WHERE source_id = :sid AND activo")

_SELECT_LINEAGE_PKS = text(
    "SELECT id FROM red_vial WHERE id = :sid OR id LIKE :pattern ESCAPE '\\'"
)

_SELECT_HAUSDORFF = text(
    "SELECT ST_HausdorffDistance("
    f"  ST_Transform(geom, {METRIC_SRID}), ST_Transform({GEOM_EXPRESSION}, {METRIC_SRID})"
    ") FROM red_vial WHERE id = :id"
)

#: Assertions 2-4 run *before* the write, not on its ``RETURNING``: the column's
#: ``geometry(LineString, 4326)`` typmod would reject a surviving MultiLineString
#: with a raw driver error, which is neither attributable to an id nor an
#: assertion failure (it would exit 5 instead of 3). Checking the collapsed
#: geometry first is what lets the abort name the feature.
_PRECHECK = text(
    f"SELECT ST_IsValid(g) AS valid, ST_IsEmpty(g) AS empty, ST_SRID(g) AS srid, "
    f"GeometryType(g) AS geom_type FROM (SELECT {GEOM_EXPRESSION} AS g) AS colapsada"
)

_INSERT = text(
    "INSERT INTO red_vial (id, source_id, "
    + ", ".join(TEXT_ATTRIBUTES)
    + ", lzn, geom, geom_hash, activo, ultima_carga_en) VALUES (:id, :source_id, "
    + ", ".join(f":{name}" for name in TEXT_ATTRIBUTES)
    + f", :lzn, {GEOM_EXPRESSION}, :geom_hash, true, clock_timestamp())"
)

# ``clock_timestamp()`` rather than ``now()``: ``now()`` is the *transaction*
# start, so two loads inside one transaction would stamp the same instant and the
# "the load IS the event" guarantee would be unobservable. The column default
# stays ``now()``; the loader is explicit.
_UPDATE = text(
    "UPDATE red_vial SET "
    + ", ".join(f"{name} = :{name}" for name in TEXT_ATTRIBUTES)
    + f", lzn = :lzn, geom = {GEOM_EXPRESSION}, geom_hash = :geom_hash, "
    + "ultima_carga_en = clock_timestamp(), updated_at = clock_timestamp() WHERE id = :id"
)

_RETIRE = text("UPDATE red_vial SET activo = false, updated_at = clock_timestamp() WHERE id = :id")

_RETIRE_ABSENT = text(
    "UPDATE red_vial SET activo = false, updated_at = clock_timestamp() "
    "WHERE activo AND NOT (source_id = ANY(:source_ids)) RETURNING id"
)


def _row_params(feature: SourceFeature, row_id: str) -> dict[str, Any]:
    params: dict[str, Any] = {
        "id": row_id,
        "source_id": feature.source_id,
        "lzn": feature.lzn,
        "geom": feature.geometry_json,
        "geom_hash": feature.geom_hash,
    }
    params.update(feature.attributes)
    return params


def _write(db: Session, statement, feature: SourceFeature, row_id: str) -> None:
    """Check assertions 2-4 on the collapsed geometry, then write the row."""
    params = _row_params(feature, row_id)
    checked = db.execute(_PRECHECK, {"geom": feature.geometry_json}).one()
    assert_stored_geometry(
        row_id,
        valid=bool(checked.valid),
        empty=bool(checked.empty),
        srid=int(checked.srid),
        geom_type=str(checked.geom_type),
    )
    db.execute(statement, params)


@dataclass(frozen=True)
class Split:
    """One lineage split: a source id whose trace moved beyond one DEM cell."""

    source_id: str
    retired_id: str
    new_id: str
    hausdorff_m: float

    def render(self) -> str:
        return (
            f"    - source_id={self.source_id}: {self.retired_id} → {self.new_id} "
            f"(Hausdorff {self.hausdorff_m:.0f} m > {MATERIAL_CHANGE_M:.0f} m)"
        )


def upsert_features(db: Session, features: Sequence[SourceFeature]) -> tuple[int, int, list[Split]]:
    """Apply the lineage rule to every source feature. Returns (inserted, updated, splits)."""
    inserted = 0
    updated = 0
    splits: list[Split] = []

    for feature in features:
        active = db.execute(_SELECT_ACTIVE, {"sid": feature.source_id}).one_or_none()

        if active is None:
            taken = {
                r.id
                for r in db.execute(
                    _SELECT_LINEAGE_PKS,
                    {
                        "sid": feature.source_id,
                        "pattern": feature.source_id.translate(_LIKE_ESCAPE) + "#%",
                    },
                )
            }
            _write(db, _INSERT, feature, next_free_pk(feature.source_id, taken))
            inserted += 1
            continue

        if active.geom_hash == feature.geom_hash:
            _write(db, _UPDATE, feature, active.id)
            updated += 1
            continue

        distance = db.execute(
            _SELECT_HAUSDORFF, {"id": active.id, "geom": feature.geometry_json}
        ).scalar_one()
        if distance is not None and float(distance) > MATERIAL_CHANGE_M:
            # A different road wearing a known id: retire, never overwrite — the
            # crossings and surveys attached to the old trace stay on the old row.
            db.execute(_RETIRE, {"id": active.id})
            taken = {
                r.id
                for r in db.execute(
                    _SELECT_LINEAGE_PKS,
                    {
                        "sid": feature.source_id,
                        "pattern": feature.source_id.translate(_LIKE_ESCAPE) + "#%",
                    },
                )
            }
            new_id = next_free_pk(feature.source_id, taken)
            _write(db, _INSERT, feature, new_id)
            inserted += 1
            splits.append(
                Split(
                    source_id=feature.source_id,
                    retired_id=active.id,
                    new_id=new_id,
                    hausdorff_m=float(distance),
                )
            )
            continue

        _write(db, _UPDATE, feature, active.id)
        updated += 1

    return inserted, updated, splits


def retire_absent(db: Session, features: Sequence[SourceFeature]) -> list[str]:
    """Flip every active row whose ``source_id`` left the source. Never a removal."""
    source_ids = [feature.source_id for feature in features]
    rows = db.execute(_RETIRE_ABSENT, {"source_ids": source_ids}).all()
    return sorted(r.id for r in rows)


# ─────────────────────────────────────────────────────────────────────────────
# Assertions 1 and 5
# ─────────────────────────────────────────────────────────────────────────────


def assert_active_row_count(db: Session, expected: int) -> int:
    """Assertion 1 — active rows must equal the source feature count.

    Strict equality also proves convergence: a re-run must not grow the working
    set. Retired rows are deliberately outside the count.
    """
    stored = int(db.execute(text("SELECT count(*) FROM red_vial WHERE activo")).scalar_one())
    if stored != expected:
        raise EtlAssertionError(
            f"filas activas en red_vial {stored} != features del origen {expected}"
        )
    return stored


_GRANULARITY_SQL = text("""
    WITH medido AS (
        SELECT id, lzn, ST_Length(geom::geography) AS largo_m
        FROM red_vial WHERE activo
    )
    SELECT
        count(*) AS feature_count,
        min(largo_m) AS min_m,
        percentile_cont(0.5) WITHIN GROUP (ORDER BY largo_m) AS median_m,
        percentile_cont(0.9) WITHIN GROUP (ORDER BY largo_m) AS p90_m,
        percentile_cont(0.99) WITHIN GROUP (ORDER BY largo_m) AS p99_m,
        max(largo_m) AS max_m
    FROM medido
""")

_OUTLIERS_SQL = text("""
    WITH medido AS (
        SELECT id, ST_Length(geom::geography) AS largo_m
        FROM red_vial WHERE activo
    )
    SELECT id, largo_m FROM medido
    WHERE largo_m > :p99 OR largo_m > :absolute
    ORDER BY largo_m DESC
""")

_LZN_MISMATCH_SQL = text("""
    WITH medido AS (
        SELECT id, lzn, ST_Length(geom::geography) AS largo_m
        FROM red_vial WHERE activo
    )
    SELECT id FROM medido
    WHERE lzn IS NOT NULL AND lzn > 0
      AND abs(largo_m - lzn * 1000) > :tolerance * (lzn * 1000)
    ORDER BY id
""")


@dataclass(frozen=True)
class GranularityReport:
    """Assertion 5 — what the segmentation actually looks like, per load."""

    feature_count: int
    min_m: float
    median_m: float
    p90_m: float
    p99_m: float
    max_m: float
    outliers: list[tuple[str, float]] = field(default_factory=list)
    lzn_mismatch_ids: list[str] = field(default_factory=list)

    @property
    def outlier_ids(self) -> list[str]:
        return [row_id for row_id, _ in self.outliers]

    @property
    def lzn_mismatch_count(self) -> int:
        return len(self.lzn_mismatch_ids)

    def render(self) -> str:
        lines = [
            "  verificación de granularidad (aserción 5)",
            f"    - tramos activos:            {self.feature_count}",
            f"    - largo min:                 {self.min_m:.0f} m",
            f"    - largo mediana:             {self.median_m:.0f} m",
            f"    - largo p90:                 {self.p90_m:.0f} m",
            f"    - largo p99:                 {self.p99_m:.0f} m",
            f"    - largo max:                 {self.max_m:.0f} m",
            f"    - lzn declarado vs medido con desvío > {LZN_TOLERANCE:.0%}: "
            f"{self.lzn_mismatch_count}",
        ]
        if self.lzn_mismatch_ids:
            lines.append(f"      ids: {', '.join(self.lzn_mismatch_ids)}")
        if self.outliers:
            lines.append(
                f"    - OUTLIER — requiere decisión explícita "
                f"(> p99 o > {OUTLIER_ABSOLUTE_M / 1000:.0f} km): {len(self.outliers)}"
            )
            for row_id, largo in self.outliers:
                lines.append(f"      * id={row_id} largo={largo:.0f} m")
        else:
            lines.append("    - OUTLIER — requiere decisión explícita: ninguno")
        return "\n".join(lines)


def granularity_report(db: Session) -> GranularityReport:
    """Measure the loaded segmentation. Reports; never re-segments."""
    stats = db.execute(_GRANULARITY_SQL).one()
    if not stats.feature_count:
        return GranularityReport(0, 0.0, 0.0, 0.0, 0.0, 0.0)

    outliers = [
        (r.id, float(r.largo_m))
        for r in db.execute(
            _OUTLIERS_SQL, {"p99": float(stats.p99_m), "absolute": OUTLIER_ABSOLUTE_M}
        )
    ]
    mismatches = [r.id for r in db.execute(_LZN_MISMATCH_SQL, {"tolerance": LZN_TOLERANCE})]
    return GranularityReport(
        feature_count=int(stats.feature_count),
        min_m=float(stats.min_m),
        median_m=float(stats.median_m),
        p90_m=float(stats.p90_m),
        p99_m=float(stats.p99_m),
        max_m=float(stats.max_m),
        outliers=outliers,
        lzn_mismatch_ids=mismatches,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Load
# ─────────────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class LoadResult:
    """What the operator has to record: the load, its splits, its retirements."""

    rows_before: int
    rows_after: int
    inserted: int
    updated: int
    splits: list[Split]
    retired_ids: list[str]
    granularity: GranularityReport
    committed: bool

    def render(self) -> str:
        verb = "cargado" if self.committed else "ENSAYO (rollback, no se escribió)"
        lines = [
            f"carga de red_vial [{verb}]",
            f"  - tramos activos antes:      {self.rows_before}",
            f"  - tramos activos después:    {self.rows_after}",
            f"  - insertados:                {self.inserted}",
            f"  - actualizados:              {self.updated}",
            f"  - retirados (activo=false):  {len(self.retired_ids)}",
        ]
        if self.retired_ids:
            lines.append(f"      ids: {', '.join(self.retired_ids)}")
        lines.append(f"  - splits de linaje:          {len(self.splits)}")
        lines.extend(split.render() for split in self.splits)
        lines.append(self.granularity.render())
        return "\n".join(lines)


def load(db: Session, features: Sequence[SourceFeature], *, dry_run: bool = False) -> LoadResult:
    """Apply the whole load in ONE transaction, then assert & COMMIT.

    ``dry_run`` runs everything, assertions and report included, and rolls back.
    Any assertion failure rolls back and propagates :class:`EtlAssertionError`.
    """
    rows_before = int(db.execute(text("SELECT count(*) FROM red_vial WHERE activo")).scalar_one())
    try:
        inserted, updated, splits = upsert_features(db, features)
        retired_ids = retire_absent(db, features)
        rows_after = assert_active_row_count(db, len(features))
        report = granularity_report(db)

        result = LoadResult(
            rows_before=rows_before,
            rows_after=rows_after,
            inserted=inserted,
            updated=updated,
            splits=splits,
            retired_ids=retired_ids,
            granularity=report,
            committed=not dry_run,
        )
        if dry_run:
            db.rollback()
        else:
            db.commit()
        return result
    except Exception:
        db.rollback()
        raise


def _report_infra_failure(exc: BaseException) -> int:
    """Print the actionable message for a non-assertion failure and give its code."""
    print(
        f"FALLO DE INFRAESTRUCTURA: {type(exc).__name__}: {exc}\n"
        "no es una aserción de la carga: el origen no se pudo leer/parsear o la base "
        "falló. red_vial quedó sin cambios. Revisar que el GeoJSON empaquetado sea "
        "legible y válido, que la base esté accesible y que las migraciones estén "
        "aplicadas (`alembic upgrade head`), y volver a correr el comando.",
        file=sys.stderr,
    )
    return EXIT_INFRA_FAILED


def run_load(db: Session, *, dry_run: bool = False) -> int:
    """Parse and load the bundled road network. Returns the process exit code."""
    try:
        features = read_source()
        result = load(db, features, dry_run=dry_run)
    except EtlUsageError as exc:
        print(f"INVOCACIÓN INVÁLIDA: {exc}", file=sys.stderr)
        return EXIT_USAGE
    except EtlAssertionError as exc:
        print(f"CARGA ABORTADA: {exc}", file=sys.stderr)
        print("red_vial quedó en su estado anterior (sin cambios)", file=sys.stderr)
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
        prog="python -m app.domains.geo.etl.load_red_vial",
        description=(
            "Carga la red vial provincial (segmentación nativa, un tramo por feature) "
            "en red_vial: UPSERT por linaje, retiro sin borrado, en una transacción."
        ),
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Corre la carga, las aserciones y el reporte, y hace rollback.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    from app.db.session import SessionLocal  # noqa: PLC0415

    with SessionLocal() as db:
        return run_load(db, dry_run=args.dry_run)


if __name__ == "__main__":  # pragma: no cover — module entry point
    raise SystemExit(main())
