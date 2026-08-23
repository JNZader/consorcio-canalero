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
  with ``ST_LineMerge`` when the parts touch and admits as N segments when they
  do not — see below).
* **NOT** ``gee/red_vial_provincial.kml``: that is a different, province-wide
  39 127-feature file and is not this layer.

GeoJSON rather than KML so the loader reuses the ``json.load`` +
``parse_features`` shape of the canal loader and adds no XML dependency.

**The docstring is not the pin.** ``RED_VIAL_FEATURE_COUNT`` is: assertion 0
compares the parsed feature count against it and aborts the whole load on a
mismatch, so a truncated or silently re-converted file can never load partially.
The constant is a claim about the source — changing the source means changing it
deliberately, in the same commit.

**A feature is not always one row** *(owner decision, 2026-08-22)*. Almost every
Placemark is a single line and becomes a single row. A Placemark whose
``MultiGeometry`` holds several lines is collapsed by ``ST_LineMerge`` when the
parts touch; when they are genuinely **disconnected**, the feature is admitted as
**N segments of one lineage** — one row per connected part, ``parte`` = 1..N —
instead of aborting the load. The earlier rule aborted naming the id, which was
correct as a refusal to split *silently* — so the split is now **loud** instead:
every multi-part feature is named in the load report with its part count. In the
shipped source exactly one feature is multi-part (``13680``, two parts), and that
one was enough to make the whole network unloadable under the old rule. Whether
another source publishes one or fifty, the rule is the same, and the report says
which. Parts are numbered from the **geometry** (start point x, then y, then the
WKB), never from the source's part order — and since the RDD review that ordering
only assigns ordinals to *brand-new* parts: identity itself is resolved by
geometry (see below), so no ordering can renumber an existing segment.

**Identity, and why there are three ids** *(corrected in RDD review, 2026-08-22:
part identity is geometric, not positional)*. ``id`` is the row identity that
``cruce_camino`` and ``relevamiento_tramo`` reference; ``source_id`` is what the
source publishes; ``parte`` is an **opaque identity label** for one part of it,
*not* a position. Each incoming part is resolved against the active rows of the
same ``source_id`` **by geometry**, one to one: exact ``geom_hash``, then nearest
by Hausdorff within one DEM cell (30 m). Then:

* matched → UPDATE in place, and the row **keeps its own ``parte``**;
* incoming part with no match → INSERT, ``id = source_id`` when free, next free
  ordinal suffix (``28188#2``, ``28188#3``, …) otherwise, with the next free
  ``parte``. Parts and splits draw from the SAME ordinal space, so neither a PK
  nor a ``parte`` is ever reused within a lineage;
* active row with no match → **retired** (``activo = false``, PK and dependents
  intact). A retire+insert pairing within one lineage is the D1 split — a known
  id re-published with a materially different trace — and the report names it.

Why geometry and not the ordinal: see :func:`_match_parts`.
**The loader never issues a row-removing statement, ever** — a crossing or a
field survey is never orphaned, and a road that comes back is a new row, not a
re-used identity. Every UPSERT stamps ``ultima_carga_en`` (with
``clock_timestamp()``, so two loads in one transaction are still two events),
including the case that changes no attribute:
the load itself IS the event, because vertex order alone can invalidate a stored
crossing side.

**Assertions (all inside the load transaction; any failure → ROLLBACK → exit 3)**

0. parsed feature count == ``RED_VIAL_FEATURE_COUNT`` (the fidelity pin — a claim
   about the SOURCE, in features, unchanged by the multi-part admission)
1. active row count == the number of **parts** the source yielded, which is
   ``>= RED_VIAL_FEATURE_COUNT`` and equal to it only when every feature is a
   single line. Two different quantities, deliberately named differently
2. every stored geometry valid under ``ST_IsValid`` — the source is repaired with
   ``ST_MakeValid`` first and the ``MultiGeometry`` wrapper collapsed with
   ``ST_LineMerge``, then decomposed with ``ST_Dump``
3. every stored geometry SRID 4326 and a LineString
4. no geometry empty after the repair
5. **granularity verification** — segment count, min / median / p90 / max of
   ``ST_Length(geom::geography)``, the count of features whose measured length
   disagrees with the declared ``lzn`` by more than 10 %, and the ids of every
   feature beyond p99 or 5 km flagged ``OUTLIER — requiere decisión explícita``.
   Assertion 5 **reports and never corrects**: a long feature is loaded whole and
   the layer is never re-segmented **by length**. The same report names the ids
   retired by this load, every lineage split, and every multi-part feature
   admitted.

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
from importlib.resources import as_file, files
import json
from pathlib import Path
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


@dataclass(frozen=True)
class SourceFeature:
    """One native road feature, coerced to what ``red_vial`` accepts.

    A feature is not necessarily one row: it is decomposed into its connected
    parts by the database (see :func:`explode_parts`), and each part is a row.
    """

    source_id: str
    attributes: dict[str, str | None]
    lzn: float | None
    geometry_json: str

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
# Decomposition into parts + the stored-geometry assertions (2–4)
# ─────────────────────────────────────────────────────────────────────────────


def assert_stored_geometry(
    feature_id: str,
    *,
    valid: bool,
    empty: bool,
    srid: int,
    geom_type: str,
) -> None:
    """Assertions 2-4 on one stored part, attributing every failure to its id."""
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
            f"geometría {geom_type!r} != LINESTRING en id={feature_id!r}: ST_Dump debía "
            "entregar partes simples y no lo hizo"
        )


@dataclass(frozen=True)
class Part:
    """One connected part of a source feature — exactly one ``red_vial`` row.

    ``geom_hash`` is the sha256 of this part's WKB, computed by PostgreSQL over
    the very bytes that get stored, so "did this segment change?" is answered by
    comparing two hashes of the same thing rather than two encodings of it.
    ``wkb`` carries the geometry between the decomposition query and the write
    with no text round trip, so no coordinate is ever re-parsed or rounded.
    """

    parte: int
    geom_hash: str
    wkb: bytes


#: Decomposition + assertions 2-4 in one query, run BEFORE any write.
#:
#: `ST_LineMerge` still collapses the KML `MultiGeometry` wrapper whenever the
#: parts are connected — the common case, and the only case the design
#: originally contemplated. What changed (owner decision, 2026-08-22) is the
#: other case: when the parts are genuinely disconnected, the feature is admitted
#: as N segments of one lineage instead of aborting the whole load. The field
#: reality is that several such roads exist, and an abort on the first one hides
#: every other.
#:
#: The `ORDER BY` (start point x, then y, then WKB) is deterministic, and since
#: the RDD review its ONLY job is handing ordinals to brand-new parts. The
#: ordinals here are **provisional**: `_match_parts` resolves identity by
#: geometry, so a matched row keeps the `parte` it already had.
_EXPLODE = text(f"""
    WITH colapsada AS (SELECT {GEOM_EXPRESSION} AS g),
         partes AS (SELECT (ST_Dump(g)).geom AS parte_geom FROM colapsada)
    SELECT
        row_number() OVER (
            ORDER BY ST_X(ST_StartPoint(parte_geom)),
                     ST_Y(ST_StartPoint(parte_geom)),
                     ST_AsBinary(parte_geom)
        ) AS parte,
        encode(sha256(ST_AsBinary(parte_geom)), 'hex') AS geom_hash,
        ST_AsEWKB(parte_geom) AS wkb,
        ST_IsValid(parte_geom) AS valid,
        ST_IsEmpty(parte_geom) AS empty,
        ST_SRID(parte_geom) AS srid,
        GeometryType(parte_geom) AS geom_type
    FROM partes
    ORDER BY parte
""")


def explode_parts(db: Session, feature: SourceFeature) -> list[Part]:
    """Collapse the wrapper, split what cannot be collapsed, assert each part."""
    rows = db.execute(_EXPLODE, {"geom": feature.geometry_json}).all()
    if not rows:
        raise EtlAssertionError(
            f"geometría irreparable en id={feature.source_id!r}: ST_MakeValid no dejó ninguna línea"
        )

    parts: list[Part] = []
    for row in rows:
        assert_stored_geometry(
            f"{feature.source_id}[parte {row.parte}]",
            valid=bool(row.valid),
            empty=bool(row.empty),
            srid=int(row.srid),
            geom_type=str(row.geom_type),
        )
        parts.append(Part(parte=int(row.parte), geom_hash=str(row.geom_hash), wkb=bytes(row.wkb)))
    return parts


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

#: The whole lineage, retired rows included: the active ones are matched against,
#: and every row's ``parte`` is an ordinal a new part must not reuse.
_SELECT_LINEAGE = text(
    "SELECT id, parte, geom_hash, activo FROM red_vial WHERE source_id = :sid ORDER BY parte"
)

_SELECT_LINEAGE_PKS = text(
    "SELECT id FROM red_vial WHERE id = :sid OR id LIKE :pattern ESCAPE '\\'"
)

_SELECT_HAUSDORFF = text(
    "SELECT ST_HausdorffDistance("
    f"  ST_Transform(geom, {METRIC_SRID}), "
    f"  ST_Transform(ST_GeomFromEWKB(:geom_wkb), {METRIC_SRID})"
    ") FROM red_vial WHERE id = :id"
)

#: The geometry travels as the EWKB the decomposition already produced, so the
#: stored bytes are exactly the bytes ``geom_hash`` was computed over.
_INSERT = text(
    "INSERT INTO red_vial (id, source_id, parte, "
    + ", ".join(TEXT_ATTRIBUTES)
    + ", lzn, geom, geom_hash, activo, ultima_carga_en) VALUES (:id, :source_id, :parte, "
    + ", ".join(f":{name}" for name in TEXT_ATTRIBUTES)
    + ", :lzn, ST_GeomFromEWKB(:geom_wkb), :geom_hash, true, clock_timestamp())"
)

# ``clock_timestamp()`` rather than ``now()``: ``now()`` is the *transaction*
# start, so two loads inside one transaction would stamp the same instant and the
# "the load IS the event" guarantee would be unobservable. The column default
# stays ``now()``; the loader is explicit.
_UPDATE = text(
    "UPDATE red_vial SET "
    + ", ".join(f"{name} = :{name}" for name in TEXT_ATTRIBUTES)
    + ", lzn = :lzn, parte = :parte, geom = ST_GeomFromEWKB(:geom_wkb), geom_hash = :geom_hash, "
    + "ultima_carga_en = clock_timestamp(), updated_at = clock_timestamp() WHERE id = :id"
)

#: Retirement is per ``(source_id, parte)``, not per ``source_id``: a feature that
#: drops from three parts to two must retire the vanished part while the other
#: two keep their identities.
_RETIRE_ABSENT = text(
    "UPDATE red_vial SET activo = false, updated_at = clock_timestamp() "
    "WHERE activo AND NOT EXISTS ("
    "  SELECT 1 FROM unnest(CAST(:source_ids AS text[]), CAST(:partes AS int[])) AS t(sid, p)"
    "  WHERE t.sid = red_vial.source_id AND t.p = red_vial.parte"
    ") RETURNING id"
)


def _row_params(feature: SourceFeature, part: Part, row_id: str, parte: int) -> dict[str, Any]:
    """``parte`` is passed in, never taken from ``part``: a matched row KEEPS its own."""
    params: dict[str, Any] = {
        "id": row_id,
        "source_id": feature.source_id,
        "parte": parte,
        "lzn": feature.lzn,
        "geom_wkb": part.wkb,
        "geom_hash": part.geom_hash,
    }
    params.update(feature.attributes)
    return params


def _lineage_pks(db: Session, source_id: str) -> set[str]:
    """Every PK the lineage has ever used — parts and splits share one space."""
    return {
        r.id
        for r in db.execute(
            _SELECT_LINEAGE_PKS,
            {"sid": source_id, "pattern": source_id.translate(_LIKE_ESCAPE) + "#%"},
        )
    }


@dataclass(frozen=True)
class Split:
    """One lineage split: a source id whose trace moved beyond one DEM cell."""

    source_id: str
    retired_id: str
    new_id: str
    hausdorff_m: float | None

    def render(self) -> str:
        # ``None`` when ST_HausdorffDistance returned NULL for the pair: an
        # unmeasurable distance is reported as such, never as ``inf``.
        distancia = (
            "Hausdorff no medible"
            if self.hausdorff_m is None
            else f"Hausdorff {self.hausdorff_m:.0f} m > {MATERIAL_CHANGE_M:.0f} m"
        )
        return f"    - source_id={self.source_id}: {self.retired_id} → {self.new_id} ({distancia})"


def _pair_splits(
    source_id: str,
    retired: Sequence[Any],
    inserted: Sequence[tuple[Part, str]],
    distances: dict[tuple[str, int], float],
) -> list[Split]:
    """Pair each retired row with the geometrically NEAREST new part.

    Pairing by list position — which this reporter did until the RDD review —
    contradicts the identity rule the rest of the loader follows: with more than
    one retirement and more than one new part the printed
    ``retired_id → new_id`` was arbitrary, and its distance fell back to ``inf``
    because ``distances`` is keyed on the geometric pair that positional pairing
    need not have produced. Greedy ascending, same deterministic tie-break as
    :func:`_match_parts`, so the audit line always names the nearest pair and
    always prints the distance actually measured for it.
    """
    rows, news = list(retired), list(inserted)
    splits: list[Split] = []

    for _, row_id, parte in sorted(
        (distances[(row.id, part.parte)], row.id, part.parte)
        for row in rows
        for part, _ in news
        if (row.id, part.parte) in distances
    ):
        row = next((r for r in rows if r.id == row_id), None)
        entry = next((e for e in news if e[0].parte == parte), None)
        if row is not None and entry is not None:
            splits.append(Split(source_id, row.id, entry[1], distances[(row.id, parte)]))
            rows.remove(row)
            news.remove(entry)

    # Leftovers: no measurable distance between them, so no pair can be claimed
    # to be the nearest one. Reported, with the distance named as unmeasurable.
    splits.extend(Split(source_id, row.id, new_id, None) for row, (_, new_id) in zip(rows, news))
    return splits


def _match_parts(
    db: Session, existing: Sequence[Any], incoming: Sequence[Part]
) -> tuple[list[tuple[Any, Part]], list[Any], list[Part], dict[tuple[str, int], float]]:
    """Resolve incoming parts against existing active rows **by geometry**.

    One-to-one, in two passes: exact ``geom_hash``, then greedy by ascending
    Hausdorff within ``MATERIAL_CHANGE_M`` (ties broken by stored id then
    incoming ordinal, so the result is deterministic).

    Matching by the ``parte`` ordinal instead — which this loader did until the
    RDD review — holds only while the SET of parts never changes: one part added
    or dropped shifts every survivor's ordinal, each incoming part is then
    compared against a stored trace kilometres away, and the resulting "material
    change" retires the whole lineage and detaches its surveys, exiting 0.

    Returns (pairs, unmatched_rows, unmatched_parts, distances).
    """
    rows, parts = list(existing), list(incoming)
    pairs: list[tuple[Any, Part]] = []

    by_hash = {row.geom_hash: row for row in rows}
    for part in list(parts):
        row = by_hash.pop(part.geom_hash, None)
        if row is not None:
            pairs.append((row, part))
            rows.remove(row)
            parts.remove(part)

    distances: dict[tuple[str, int], float] = {}
    for row in rows:
        for part in parts:
            distance = db.execute(
                _SELECT_HAUSDORFF, {"id": row.id, "geom_wkb": part.wkb}
            ).scalar_one()
            if distance is not None:
                distances[(row.id, part.parte)] = float(distance)

    for _, row_id, parte in sorted(
        (distance, row_id, parte)
        for (row_id, parte), distance in distances.items()
        if distance <= MATERIAL_CHANGE_M
    ):
        row = next((r for r in rows if r.id == row_id), None)
        part = next((p for p in parts if p.parte == parte), None)
        if row is not None and part is not None:
            pairs.append((row, part))
            rows.remove(row)
            parts.remove(part)

    return pairs, rows, parts, distances


def next_free_parte(used: set[int]) -> int:
    """The ordinal a NEW part gets. Opaque label, never reused, never a position."""
    ordinal = 1
    while ordinal in used:
        ordinal += 1
    return ordinal


@dataclass
class UpsertOutcome:
    """What the write pass did, and the key set the retirement pass needs."""

    inserted: int = 0
    updated: int = 0
    splits: list[Split] = field(default_factory=list)
    multipart: list[tuple[str, int]] = field(default_factory=list)
    loaded_keys: list[tuple[str, int]] = field(default_factory=list)


def upsert_features(db: Session, features: Sequence[SourceFeature]) -> UpsertOutcome:
    """Apply the lineage rule to every part of every source feature."""
    outcome = UpsertOutcome()

    for feature in features:
        parts = explode_parts(db, feature)
        if len(parts) > 1:
            outcome.multipart.append((feature.source_id, len(parts)))

        lineage = db.execute(_SELECT_LINEAGE, {"sid": feature.source_id}).all()
        pairs, unmatched_rows, unmatched_parts, distances = _match_parts(
            db, [row for row in lineage if row.activo], parts
        )

        for row, part in pairs:
            # The matched row KEEPS its ordinal: it is an identity label, not a
            # position, so nothing renumbers when the part set changes.
            db.execute(_UPDATE, _row_params(feature, part, row.id, row.parte))
            outcome.loaded_keys.append((feature.source_id, row.parte))
            outcome.updated += 1

        used_partes = {row.parte for row in lineage}
        taken_pks = _lineage_pks(db, feature.source_id)
        # Unmatched incoming = new part; unmatched active row = gone. Both at
        # once is the D1 split, reported as such by ``_pair_splits``. The
        # retirement itself is left to ``retire_absent``: every key missing from
        # ``loaded_keys``.
        inserted: list[tuple[Part, str]] = []
        for part in unmatched_parts:
            new_id = next_free_pk(feature.source_id, taken_pks)
            parte = next_free_parte(used_partes)
            taken_pks.add(new_id)
            used_partes.add(parte)
            db.execute(_INSERT, _row_params(feature, part, new_id, parte))
            outcome.loaded_keys.append((feature.source_id, parte))
            outcome.inserted += 1
            inserted.append((part, new_id))

        outcome.splits.extend(_pair_splits(feature.source_id, unmatched_rows, inserted, distances))

    return outcome


def retire_absent(db: Session, loaded_keys: Sequence[tuple[str, int]]) -> list[str]:
    """Flip every active row whose ``(source_id, parte)`` left the source.

    Never a removal: a retired row keeps its PK, and its crossings and field
    surveys keep resolving.
    """
    rows = db.execute(
        _RETIRE_ABSENT,
        {
            "source_ids": [key[0] for key in loaded_keys],
            "partes": [key[1] for key in loaded_keys],
        },
    ).all()
    return sorted(r.id for r in rows)


# ─────────────────────────────────────────────────────────────────────────────
# Assertions 1 and 5
# ─────────────────────────────────────────────────────────────────────────────


def assert_active_row_count(db: Session, expected: int) -> int:
    """Assertion 1 — active rows must equal the number of parts the source yielded.

    **Not** the source feature count. Since the owner's exit (B) a feature whose
    ``MultiGeometry`` holds disconnected lines becomes N rows, so
    ``rows >= features``, with equality exactly when every feature is a single
    line. The pin that still speaks about features is ``RED_VIAL_FEATURE_COUNT``
    (assertion 0); this one is about parts, and saying so is what keeps both
    honest. Strict equality still proves convergence: a re-run must not grow the
    working set. Retired rows are deliberately outside the count.
    """
    stored = int(db.execute(text("SELECT count(*) FROM red_vial WHERE activo")).scalar_one())
    if stored != expected:
        raise EtlAssertionError(
            f"filas activas en red_vial {stored} != partes del origen {expected}"
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
    """What the operator has to record: the load, its parts, splits, retirements."""

    feature_count: int
    rows_before: int
    rows_after: int
    inserted: int
    updated: int
    splits: list[Split]
    multipart: list[tuple[str, int]]
    retired_ids: list[str]
    granularity: GranularityReport
    committed: bool

    def render(self) -> str:
        verb = "cargado" if self.committed else "ENSAYO (rollback, no se escribió)"
        lines = [
            f"carga de red_vial [{verb}]",
            f"  - features del origen:       {self.feature_count}",
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
        lines.append(
            f"  - MULTIPARTE (feature con partes desconectadas → N tramos del mismo "
            f"linaje): {len(self.multipart)}"
        )
        for source_id, count in self.multipart:
            lines.append(f"      * source_id={source_id} partes={count}")
        lines.append(self.granularity.render())
        return "\n".join(lines)


def load(db: Session, features: Sequence[SourceFeature], *, dry_run: bool = False) -> LoadResult:
    """Apply the whole load in ONE transaction, then assert & COMMIT.

    ``dry_run`` runs everything, assertions and report included, and rolls back.
    Any assertion failure rolls back and propagates :class:`EtlAssertionError`.
    """
    rows_before = int(db.execute(text("SELECT count(*) FROM red_vial WHERE activo")).scalar_one())
    try:
        outcome = upsert_features(db, features)
        retired_ids = retire_absent(db, outcome.loaded_keys)
        rows_after = assert_active_row_count(db, len(outcome.loaded_keys))
        report = granularity_report(db)

        result = LoadResult(
            feature_count=len(features),
            rows_before=rows_before,
            rows_after=rows_after,
            inserted=outcome.inserted,
            updated=outcome.updated,
            splits=outcome.splits,
            multipart=outcome.multipart,
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
