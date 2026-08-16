"""W5 — idempotent bootstrap integration (RMEH-002, JDA-001, JDB-004).

Ordered bootstrap over an OWNED disposable stack (RMEH-002-A):

    1. re-read ``rmeh_ownership`` (the marker gate, sole OwnedBoundary path);
    2. ``alembic upgrade head`` (migration-owned schema is the only DDL source);
    3. inspect the migration-owned relations + PostGIS/SRID/index contract;
    4. classify both materialized-view slots (absent / harness-owned /
       migration-owned / unknown) from pg_class + provenance comments;
    5. one bounded disposable rebuild (budget = 1) when the migration state or a
       migration-owned object is absent/incompatible — never ad hoc DDL;
    6. fixture seed transaction (deterministic rows, stable UUIDs/nomenclatures);
    7. ``vt_parcelas_catastro`` provenance gate + ``mv_suelos_por_zona``
       migration-owned postconditions;
    8. service validations (Martin health/catalog/tile, backend /live + real
       ficha POST as ``tipo=parcela``, frontend /mapa from loopback).

Every destructive decision is driven by a ``CommandRunner`` so the recording
adapter can prove ordering (marker read first) and boundedness (one rebuild).

Safety invariants re-asserted here (JD-DES-003):
  * no DATABASE_MUTATING call may precede the marker read;
  * a migration-owned/unknown ``vt_parcelas_catastro`` is NEVER relabeled;
    it must be compatible to be used, and incompatibility consumes the rebuild;
  * ``mv_suelos_por_zona`` is migration-owned: absent/incompatible is a
    migration-only repair path (rebuild + re-migrate), never harness DDL.
"""

from __future__ import annotations

import hashlib
import json
import math
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping, Sequence

from scripts.rainfall_e2e_harness.safety import (
    BootstrapPrerequisiteFailure,
    CommandKind,
    CommandResult,
    CommandRunner,
    OwnedBoundary,
    RunIdentity,
    apply_migrations,
    validate_marker_read_only,
)

# The harness compose file: the runner passes it explicitly everywhere so
# `docker compose` never auto-discovers a production compose from the cwd.
COMPOSE_FILE = "scripts/tests/rainfall-e2e.compose.yml"

# Compose role: the harness stack creates POSTGRES_USER=rmeh_user with DB
# rmeh_<prefix>; every psql exec must connect as that role to the run DB (the
# compose exec default OS user is root, whose psql role does not exist).
DB_ROLE = "rmeh_user"


def _psql_cmd(compose_file: str, database_name: str, sql: str) -> list[str]:
    """The base `docker compose exec db psql` command for the run-owned DB."""
    return [
        "docker", "compose", "-f", compose_file, "exec", "-T", "db", "psql",
        "-U", DB_ROLE, "-d", database_name, "-tA", "-c", sql,
    ]

# Ownership marker carved into the harness-created materialized view. The
# presence of this marker is what makes a slot "harness-owned" (recreatable);
# its absence with a foreign provenance comment is what makes it untouchable.
HARNESS_VIEW_MARKER = "rainfall-multi-parcel-e2e-harness"

# The seven frontend-whitelisted properties published by the harness Martin
# catalog (mirrors src/lib/map/layerPropertyWhitelists.ts — drift is a
# diagnostic, never an auto-rewrite) plus the geometry column.
PARCEL_VIEW_COLUMNS: tuple[str, ...] = (
    "id",
    "nomenclatura",
    "tipo_parcela",
    "desig_oficial",
    "departamento",
    "pedania",
    "superficie_ha",
    "nro_cuenta",
    "par_idparcela",
    "geometria",
)
PARCEL_VIEW_MARTIN_COLUMNS: tuple[str, ...] = (
    "geometria",
    "nro_cuenta",
    "desig_oficial",
    "superficie_ha",
    "departamento",
    "pedania",
    "nomenclatura",
    "tipo_parcela",
)

# Migration-owned mv_suelos_por_zona (0015 + 0017): exact projection with the
# surrogate key 0017 added, and the unique index that makes concurrent refresh
# legal.
SOIL_VIEW_COLUMNS: tuple[str, ...] = (
    "mv_id",
    "zona_id",
    "zona_nombre",
    "cuenca",
    "cap",
    "simbolo",
    "ip",
    "ha_suelo",
)
SOIL_VIEW_UNIQUE_INDEX = "ux_mv_suelos_por_zona_id"

SOURCE_CONTRACTS: Mapping[str, tuple[str, ...]] = {
    "parcelas_catastro": ("nomenclatura", "geometria", "tipo_parcela"),
    "suelos_catastro": ("simbolo", "geometria"),
    "zonas_operativas": ("nombre", "geometria", "cuenca"),
}

PARCEL_VIEW_DDL = f"""
CREATE MATERIALIZED VIEW vt_parcelas_catastro AS
SELECT {", ".join(PARCEL_VIEW_COLUMNS)}
FROM parcelas_catastro
WITH DATA;
"""


class RelationKind(Enum):
    PARCEL_SOURCE = "parcelas_catastro"
    SOIL_SOURCE = "suelos_catastro"
    ZONE_SOURCE = "zonas_operativas"
    PARCEL_VIEW = "vt_parcelas_catastro"
    SOIL_VIEW = "mv_suelos_por_zona"


@dataclass(frozen=True)
class RelationInspection:
    """Read-only snapshot of one relation (pg_namespace/pg_class/pg_indexes)."""

    name: str
    schema: str
    relkind: str  # r | v | m | ...
    owner: str
    comment: str
    columns: tuple[str, ...]
    indexes: tuple[str, ...]
    definition_digest: str | None


@dataclass(frozen=True)
class BootstrapReport:
    migrations_run: bool
    rebuilt: bool
    parcel_view_action: str  # create | recreate | refresh
    seed_digest: str
    soil_rows: int
    srid: int
    postgis: str
    postconditions: tuple[str, ...]


@dataclass(frozen=True)
class ServiceReport:
    martin_ok: bool
    martin_source: str
    tile_ok_for: tuple[str, ...]
    backend_live: bool
    ficha_ok_for: tuple[str, ...]
    frontend_ok: bool


# --------------------------------------------------------------------------- #
# Relation inspection (read-only)
# --------------------------------------------------------------------------- #
def inspect_relation(
    runner: CommandRunner,
    name: str,
    *,
    compose_file: str = COMPOSE_FILE,
    database_name: str | None = None,
) -> RelationInspection | None:
    """One read-only catalog query over pg_namespace/pg_class/pg_indexes.
    Returns None when the relation is absent (empty stdout). ``database_name``
    is the run-owned DB (``rmeh_<prefix>``); when omitted (unit layer) the
    command is built without the role/db flags, unchanged from W1.

    ``name`` is a FIXED internal constant from the harness's own relation
    catalog (``RelationKind``) — never caller input — so it is inlined into the
    SQL rather than passed as a psql parameter (``psql -c`` does not do
    ``%s`` substitution)."""
    quoted = name.replace("'", "''")
    sql = (
        "SELECT json_build_object("
        "'schema', n.nspname, "
        "'relkind', c.relkind, "
        "'owner', pg_get_userbyid(c.relowner), "
        "'comment', COALESCE(obj_description(c.oid, 'pg_class'), ''), "
        "'columns', COALESCE((SELECT array_agg(a.attname ORDER BY a.attnum) "
        "FROM pg_attribute a WHERE a.attrelid = c.oid AND a.attnum > 0 "
        "AND NOT a.attisdropped), '{}'), "
        "'indexes', COALESCE((SELECT array_agg(i.indexname ORDER BY i.indexname) "
        "FROM pg_indexes i WHERE i.schemaname = n.nspname AND i.tablename = c.relname), '{}'), "
        "'definition_digest', CASE WHEN c.relkind IN ('m','v') "
        "THEN md5(pg_get_viewdef(c.oid, true)) ELSE NULL END"
        f") FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
        f"WHERE n.nspname = 'public' AND c.relname = '{quoted}'"
    )
    if database_name is not None:
        command = _psql_cmd(compose_file, database_name, sql)
    else:
        command = [
            "docker", "compose", "-f", compose_file, "exec", "-T", "db", "psql",
            "-tA", "-c", sql,
        ]
    result = runner.run(command, kind=CommandKind.DATABASE_READONLY)
    if result.exit_code != 0:
        raise BootstrapPrerequisiteFailure(
            f"relation inspection error for {name}: {result.stderr.strip()}"
        )
    body = result.stdout.strip()
    if not body:
        return None
    row = json.loads(body)
    return RelationInspection(
        name=name,
        schema=row.get("schema", ""),
        relkind=row.get("relkind", ""),
        owner=row.get("owner", ""),
        comment=row.get("comment", ""),
        columns=tuple(row.get("columns") or ()),
        indexes=tuple(row.get("indexes") or ()),
        definition_digest=row.get("definition_digest"),
    )


def inspect_srid_contract(
    runner: CommandRunner,
    *,
    compose_file: str = COMPOSE_FILE,
    database_name: str | None = None,
) -> Mapping[str, Any]:
    """PostGIS presence + geometry SRID contract (one read-only query)."""
    sql = (
        "SELECT json_build_object("
        "'postgis', COALESCE((SELECT extversion FROM pg_extension "
        "WHERE extname = 'postgis'), ''), "
        "'srid', COALESCE((SELECT srid FROM geometry_columns LIMIT 1), 0)"
        ")"
    )
    if database_name is not None:
        command = _psql_cmd(compose_file, database_name, sql)
    else:
        command = [
            "docker", "compose", "-f", compose_file, "exec", "-T", "db", "psql",
            "-tA", "-c", sql,
        ]
    result = runner.run(command, kind=CommandKind.DATABASE_READONLY)
    if result.exit_code != 0:
        raise BootstrapPrerequisiteFailure(
            f"srid contract error: {result.stderr.strip()}"
        )
    row = json.loads(result.stdout.strip() or "{}")
    return {"postgis": row.get("postgis", ""), "srid": int(row.get("srid") or 0)}


# --------------------------------------------------------------------------- #
# Classification
# --------------------------------------------------------------------------- #
def classify_parcel_view(inspection: RelationInspection | None) -> str:
    """absent | harness-owned | migration-owned | unknown.

    The harness marker comment is the ONLY proof of ownership. A provenance
    comment that is not the harness marker is migration-owned; a commentless
    view is unknown. Both migration-owned and unknown are treated identically
    by the bootstrap (compatibility required, never relabeled)."""
    if inspection is None:
        return "absent"
    if HARNESS_VIEW_MARKER in (inspection.comment or ""):
        return "harness-owned"
    if inspection.comment:
        return "migration-owned"
    return "unknown"


def classify_soil_view(inspection: RelationInspection | None) -> str:
    """absent | compatible | incompatible (migration-owned only)."""
    if inspection is None:
        return "absent"
    if inspection.relkind != "m":
        return "incompatible"
    if set(inspection.columns) != set(SOIL_VIEW_COLUMNS):
        return "incompatible"
    if SOIL_VIEW_UNIQUE_INDEX not in inspection.indexes:
        return "incompatible"
    return "compatible"


def _parcel_view_compatible(inspection: RelationInspection | None) -> bool:
    if inspection is None:
        return False
    return (
        inspection.relkind == "m"
        and inspection.schema == "public"
        and set(PARCEL_VIEW_MARTIN_COLUMNS).issubset(set(inspection.columns))
        and inspection.definition_digest is not None
    )


def _source_contract_ok(inspection: RelationInspection | None, expected: tuple[str, ...]) -> bool:
    if inspection is None:
        return False
    return inspection.relkind == "r" and set(expected).issubset(set(inspection.columns))


# --------------------------------------------------------------------------- #
# Deterministic fixture seed (RMEH-003-A/D)
# --------------------------------------------------------------------------- #
def _stable_uuid(namespace: str, key: str) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"{HARNESS_VIEW_MARKER}:{namespace}:{key}"))


def build_seed_sql(fixture: Mapping[str, Any]) -> str:
    """Deterministic SQL transaction seeding the run-owned tables from the W2
    fixture JSON (camelCase -> snake_case column mapping). Byte-for-byte stable
    for the same fixture, which is what the idempotency probe compares."""
    parcels = fixture.get("parcels") or []
    if len(parcels) != 3 or {p.get("alias") for p in parcels} != {"A", "B", "C"}:
        raise BootstrapPrerequisiteFailure(
            f"fixture seed requires exactly 3 parcels (A/B/C), got {[p.get('alias') for p in parcels]}"
        )
    covering_zone = fixture.get("coveringZone") or {}
    covering_soil = fixture.get("coveringSoil") or {}

    parcel_rows = []
    for idx, p in enumerate(parcels, start=1):
        geometry = json.dumps(p["geometry"], separators=(",", ":"))
        rainfall = p.get("rainfall") or {}
        parcel_rows.append(
            "("
            f"'{p['stableUuid']}'::uuid, "
            f"'{p['nomenclature']}', "
            f"ST_GeomFromGeoJSON('{geometry}'::json), "
            f"'e2e', "
            f"'{p.get('displayIdentity', 'RMEH-PARCEL')}', "
            "'San Justo', "
            f"'RMEH-{idx}', "
            f"ST_Area(ST_Transform(ST_GeomFromGeoJSON('{geometry}'::json), 32720)) / 10000.0, "
            f"'RMEH-000{idx}', "
            f"{idx}"
            ")"
        )

    # The ten pre-existing rainfall tests navigate to and click the REAL
    # legacy parcel 3603003210041000 (catastroFixture.ts PARCELA_FIXTURE); the
    # ficha POST resolves it by nomenclatura from parcelas_catastro. Seeding
    # only A/B/C truncates that parcel away and the legacy tests soft-skip,
    # breaking the W9 exact 11/0/0/0 gate. A top-level fixture `legacyParcel`
    # (NOT inside `parcels`, which stays exactly 3 for RMEH-003) adds it as a
    # 4th deterministic row when present; absent fixtures are unchanged.
    legacy = fixture.get("legacyParcel") or {}
    if legacy.get("nomenclature"):
        geometry = json.dumps(legacy["geometry"], separators=(",", ":"))
        parcel_rows.append(
            "("
            f"'{legacy['stableUuid']}'::uuid, "
            f"'{legacy['nomenclature']}', "
            f"ST_GeomFromGeoJSON('{geometry}'::json), "
            "'e2e', "
            f"'{legacy.get('displayIdentity', 'RMEH-LEGACY-PARCEL')}', "
            "'San Justo', "
            "'RMEH-LEGACY', "
            f"ST_Area(ST_Transform(ST_GeomFromGeoJSON('{geometry}'::json), 32720)) / 10000.0, "
            "'RMEH-LEGACY', "
            "0"
            ")"
        )

    zone_geometry = json.dumps(covering_zone.get("geometry") or {"type": "Polygon", "coordinates": []}, separators=(",", ":"))
    soil_geometry = json.dumps(covering_soil.get("geometry") or {"type": "Polygon", "coordinates": []}, separators=(",", ":"))
    zone_uuid = _stable_uuid("zona", str(covering_zone.get("id") or "fixture"))
    soil_uuid = _stable_uuid("suelo", str(covering_soil.get("id") or "fixture"))
    zone_area = (
        "ST_Area(ST_Transform(ST_GeomFromGeoJSON("
        f"'{zone_geometry}'::json), 32720)) / 10000.0"
    )

    sql = "\n".join(
        [
            "BEGIN;",
            # CASCADE is required: migration-owned FKs reference the run-owned
            # tables (e.g. indices_hidricos -> zonas_operativas). The whole
            # seed is one transaction that fully re-populates the run-owned
            # tables from the fixture, so cascading the truncate is safe.
            "TRUNCATE parcelas_catastro, suelos_catastro, zonas_operativas CASCADE;",
            "INSERT INTO parcelas_catastro "
            "(id, nomenclatura, geometria, tipo_parcela, desig_oficial, departamento, "
            "pedania, superficie_ha, nro_cuenta, par_idparcela) VALUES",
            ",\n".join(parcel_rows) + ";",
            "INSERT INTO zonas_operativas (id, nombre, geometria, cuenca, superficie_ha) VALUES",
            f"('{zone_uuid}'::uuid, '{covering_zone.get('nomenclature', 'RMEH-FIXTURE-ZONE')}', "
            f"ST_GeomFromGeoJSON('{zone_geometry}'::json), 'RMEH', {zone_area});",
            "INSERT INTO suelos_catastro (id, simbolo, cap, ip, geometria) VALUES",
            f"('{soil_uuid}'::uuid, '{covering_soil.get('simbolo', 'RMEH-SIMB')}', "
            f"'{covering_soil.get('cap', 'I')}', 'RMEH', "
            f"ST_Multi(ST_GeomFromGeoJSON('{soil_geometry}'::json)));",
            "COMMIT;",
        ]
    )
    return sql


def seed_digest(fixture: Mapping[str, Any]) -> str:
    return hashlib.sha256(build_seed_sql(fixture).encode("utf-8")).hexdigest()


# --------------------------------------------------------------------------- #
# One bounded disposable rebuild (RMEH-002-A, budget = 1)
# --------------------------------------------------------------------------- #
def _rebuild_once(
    runner: CommandRunner,
    identity: RunIdentity,
    *,
    compose_file: str,
) -> OwnedBoundary:
    """Recreate the run-owned DB volume (exact compose project, -v), let the
    init script reinstall the marker on the fresh volume, re-run migrations,
    and re-prove ownership. Returns the re-validated OwnedBoundary."""
    runner.run(
        ["docker", "compose", "-f", compose_file, "down", "-v"],
        kind=CommandKind.DOCKER_CONTROL,
    )
    runner.run(
        ["docker", "compose", "-f", compose_file, "up", "-d"],
        kind=CommandKind.DOCKER_CONTROL,
    )
    owned = validate_marker_read_only(runner, identity, compose_file=compose_file)
    apply_migrations(owned, runner, compose_file=compose_file)
    return owned


# --------------------------------------------------------------------------- #
# Ordered bootstrap driver
# --------------------------------------------------------------------------- #
def bootstrap_database(
    identity: RunIdentity,
    runner: CommandRunner,
    fixture: Mapping[str, Any],
    *,
    compose_file: str = COMPOSE_FILE,
    rebuild_budget: int = 1,
) -> BootstrapReport:
    """Run the ordered bootstrap (5.1-5.4). The caller has ALREADY provisioned
    the compose stack (which ran ``alembic upgrade head`` via the migrate
    service) and validated the marker; this re-reads ownership first."""
    # Step 1: re-read the marker (ordering invariant: no mutating call before it).
    owned = validate_marker_read_only(runner, identity, compose_file=compose_file)
    # Step 2: migration head (idempotent — no-op when already at head).
    apply_migrations(owned, runner, compose_file=compose_file)

    rebuilt = False

    def _inspect_all() -> tuple[Mapping[str, RelationInspection | None], Mapping[str, Any]]:
        sources = {
            "parcelas_catastro": inspect_relation(runner, "parcelas_catastro", compose_file=compose_file, database_name=identity.database_name),
            "suelos_catastro": inspect_relation(runner, "suelos_catastro", compose_file=compose_file, database_name=identity.database_name),
            "zonas_operativas": inspect_relation(runner, "zonas_operativas", compose_file=compose_file, database_name=identity.database_name),
        }
        srid_contract = inspect_srid_contract(runner, compose_file=compose_file, database_name=identity.database_name)
        views = {
            "vt_parcelas_catastro": inspect_relation(runner, "vt_parcelas_catastro", compose_file=compose_file, database_name=identity.database_name),
            "mv_suelos_por_zona": inspect_relation(runner, "mv_suelos_por_zona", compose_file=compose_file, database_name=identity.database_name),
        }
        return {**sources, **views}, srid_contract

    def _needs_rebuild(
        relations: Mapping[str, RelationInspection | None],
        contract: Mapping[str, Any],
    ) -> bool:
        for source, expected in SOURCE_CONTRACTS.items():
            if not _source_contract_ok(relations.get(source), expected):
                return True
        if not contract.get("postgis") or int(contract.get("srid") or 0) != 4326:
            return True
        if classify_soil_view(relations.get("mv_suelos_por_zona")) in ("absent", "incompatible"):
            return True
        parcel = relations.get("vt_parcelas_catastro")
        if classify_parcel_view(parcel) in ("migration-owned", "unknown"):
            if not _parcel_view_compatible(parcel):
                return True
        return False

    relations, contract = _inspect_all()
    if _needs_rebuild(relations, contract):
        if rebuild_budget <= 0:
            raise BootstrapPrerequisiteFailure(
                "bootstrap rebuild budget exhausted: migration state or a "
                "migration-owned object remains absent/incompatible; aborting "
                "instead of hand-creating migration objects"
            )
        owned = _rebuild_once(runner, identity, compose_file=compose_file)
        rebuilt = True
        relations, contract = _inspect_all()
        if _needs_rebuild(relations, contract):
            raise BootstrapPrerequisiteFailure(
                "one bounded rebuild did not repair the migration state; "
                "remaining mismatch aborts (never ad hoc DDL)"
            )

    # Step 5.3: fixture seed transaction (deterministic rows).
    sql = build_seed_sql(fixture)
    seed_result = runner.run(
        _psql_cmd(compose_file, identity.database_name, sql),
        kind=CommandKind.DATABASE_MUTATING,
    )
    if seed_result.exit_code != 0:
        raise BootstrapPrerequisiteFailure(
            f"fixture seed failed (transaction aborted, no partial rows): "
            f"{seed_result.stderr.strip()}"
        )

    # Step 5.4: vt_parcelas_catastro provenance gate.
    parcel_view = relations["vt_parcelas_catastro"]
    parcel_kind = classify_parcel_view(parcel_view)
    if parcel_kind == "absent":
        _create_parcel_view(runner, owned, compose_file=compose_file, database_name=identity.database_name)
        action = "create"
    elif parcel_kind == "harness-owned":
        _recreate_parcel_view(runner, owned, compose_file=compose_file, database_name=identity.database_name)
        action = "recreate"
    else:
        # migration-owned / unknown: compatible REQUIRED, never relabeled.
        if not _parcel_view_compatible(parcel_view):
            raise BootstrapPrerequisiteFailure(
                f"vt_parcelas_catastro is {parcel_kind} and incompatible "
                "(kind/schema/columns/definition); refusing to relabel a "
                "migration-owned/unknown object"
            )
        _refresh_parcel_view(runner, owned, compose_file=compose_file, database_name=identity.database_name)
        action = "refresh"

    # Step 5.4: mv_suelos_por_zona migration-owned postconditions.
    soil_view = relations["mv_suelos_por_zona"]
    soil_kind = classify_soil_view(soil_view)
    if soil_kind == "absent":
        raise BootstrapPrerequisiteFailure(
            "mv_suelos_por_zona absent after migrations; this is a migration-"
            "owned object — migration-only repair (rebuild + re-migrate), "
            "never harness DDL"
        )
    if soil_kind != "compatible":
        raise BootstrapPrerequisiteFailure(
            "mv_suelos_por_zona incompatible (relkind/columns/unique mv_id); "
            "migration-only repair required, never ad hoc DDL"
        )
    _refresh_soil_view(runner, owned, compose_file=compose_file, database_name=identity.database_name)
    soil_rows = _count_soil_rows(runner, compose_file=compose_file, database_name=identity.database_name)
    if soil_rows != 1:
        raise BootstrapPrerequisiteFailure(
            f"mv_suelos_por_zona must hold exactly one fixture zone/soil row "
            f"with positive ha_suelo, got {soil_rows}"
        )

    postconditions = (
        "marker_re-read",
        "migrations_at_head",
        "sources_contract_ok",
        f"postgis={contract.get('postgis')}",
        f"srid={contract.get('srid')}",
        f"parcel_view={action}",
        f"soil_view={soil_kind}",
        f"soil_rows={soil_rows}",
    )
    return BootstrapReport(
        migrations_run=True,
        rebuilt=rebuilt,
        parcel_view_action=action,
        seed_digest=seed_digest(fixture),
        soil_rows=soil_rows,
        srid=int(contract.get("srid") or 0),
        postgis=str(contract.get("postgis") or ""),
        postconditions=postconditions,
    )


def _create_parcel_view(runner: CommandRunner, owned: OwnedBoundary, *, compose_file: str, database_name: str) -> None:
    sql = PARCEL_VIEW_DDL + (
        f"COMMENT ON MATERIALIZED VIEW vt_parcelas_catastro IS "
        f"'{HARNESS_VIEW_MARKER} owned run={owned.run_id}';"
    )
    result = runner.run(
        _psql_cmd(compose_file, database_name, sql),
        kind=CommandKind.DATABASE_MUTATING,
    )
    if result.exit_code != 0:
        raise BootstrapPrerequisiteFailure(
            f"vt_parcelas_catastro create failed: {result.stderr.strip()}"
        )


def _recreate_parcel_view(runner: CommandRunner, owned: OwnedBoundary, *, compose_file: str, database_name: str) -> None:
    sql = (
        "DROP MATERIALIZED VIEW IF EXISTS vt_parcelas_catastro;"
        + PARCEL_VIEW_DDL
        + f"COMMENT ON MATERIALIZED VIEW vt_parcelas_catastro IS "
        f"'{HARNESS_VIEW_MARKER} owned run={owned.run_id}';"
    )
    result = runner.run(
        _psql_cmd(compose_file, database_name, sql),
        kind=CommandKind.DATABASE_MUTATING,
    )
    if result.exit_code != 0:
        raise BootstrapPrerequisiteFailure(
            f"vt_parcelas_catastro recreate failed: {result.stderr.strip()}"
        )


def _refresh_parcel_view(runner: CommandRunner, owned: OwnedBoundary, *, compose_file: str, database_name: str) -> None:
    result = runner.run(
        _psql_cmd(compose_file, database_name, "REFRESH MATERIALIZED VIEW vt_parcelas_catastro"),
        kind=CommandKind.DATABASE_MUTATING,
    )
    if result.exit_code != 0:
        raise BootstrapPrerequisiteFailure(
            f"vt_parcelas_catastro refresh failed: {result.stderr.strip()}"
        )


def _refresh_soil_view(runner: CommandRunner, owned: OwnedBoundary, *, compose_file: str, database_name: str) -> None:
    result = runner.run(
        _psql_cmd(compose_file, database_name, "REFRESH MATERIALIZED VIEW CONCURRENTLY mv_suelos_por_zona"),
        kind=CommandKind.DATABASE_MUTATING,
    )
    if result.exit_code != 0:
        raise BootstrapPrerequisiteFailure(
            f"mv_suelos_por_zona refresh failed: {result.stderr.strip()}"
        )


def _count_soil_rows(runner: CommandRunner, *, compose_file: str, database_name: str) -> int:
    result = runner.run(
        _psql_cmd(
            compose_file, database_name,
            "SELECT count(*) FROM mv_suelos_por_zona WHERE ha_suelo > 0",
        ),
        kind=CommandKind.DATABASE_READONLY,
    )
    if result.exit_code != 0:
        raise BootstrapPrerequisiteFailure(f"soil row count error: {result.stderr.strip()}")
    try:
        return int(result.stdout.strip() or "0")
    except ValueError:
        raise BootstrapPrerequisiteFailure(
            f"soil row count unparseable: {result.stdout.strip()!r}"
        ) from None


# --------------------------------------------------------------------------- #
# Service validations (5.5)
# --------------------------------------------------------------------------- #
def tile_xyz(lng: float, lat: float, zoom: int) -> tuple[int, int, int]:
    """Web Mercator tile x/y/z for a lng/lat at a zoom (Martin tile URL)."""
    lat = max(-85.05112878, min(85.05112878, lat))
    n = 2 ** zoom
    x = int((lng + 180.0) / 360.0 * n)
    lat_rad = math.radians(lat)
    y = int((1.0 - math.asinh(math.tan(lat_rad)) / math.pi) / 2.0 * n)
    return x, y, zoom


def _http_code(body: str) -> int:
    """The probe convention: the last non-empty line of stdout is the HTTP code."""
    lines = [ln for ln in body.splitlines() if ln.strip()]
    if not lines:
        return 0
    try:
        return int(lines[-1])
    except ValueError:
        return 0


def _catalog_sources(body: str) -> set[str]:
    """Source names from a Martin /catalog response. Martin v0.14.2 shape is
    ``{"tiles": {...}}`` (+ sprites/fonts); older shapes used ``{"tables": ...}``
    / ``{"functions": ...}`` — accept all three so a catalog-shape drift is a
    diagnostic, not a parse hole."""
    try:
        payload = json.loads(body.rsplit("\n", 1)[0] or "{}")
    except ValueError:
        return set()
    return set((payload.get("tiles") or {}).keys()) | set(
        (payload.get("tables") or {}).keys()
    ) | set((payload.get("functions") or {}).keys())


def _probe_get(runner: CommandRunner, url: str, *, discard_body: bool = False) -> CommandResult:
    command = ["curl", "-s", "-w", "\\n%{http_code}"]
    if discard_body:
        # Vector tiles are binary protobuf; the probe only needs the HTTP
        # code, so the body is dropped instead of decoding bytes as text.
        command.extend(["-o", "/dev/null"])
    command.append(url)
    result = runner.run(command, kind=CommandKind.DOCKER_INSPECT)
    return result


def _probe_post(runner: CommandRunner, url: str, payload: str) -> CommandResult:
    result = runner.run(
        ["curl", "-s", "-w", "\\n%{http_code}", "-X", "POST",
         "-H", "Content-Type: application/json", "-d", payload, url],
        kind=CommandKind.DOCKER_INSPECT,
    )
    return result


def validate_services(
    identity: RunIdentity,
    runner: CommandRunner,
    fixture: Mapping[str, Any],
    *,
    origins: Mapping[str, str],
    camera_zoom: int = 14,
    martin_poll_seconds: float = 2.0,
) -> ServiceReport:
    """Martin health/catalog/tile + backend /live + real ficha POST + frontend
    /mapa, all from loopback. HTTP 204 / non-200 on a tile aborts as a
    prerequisite failure BEFORE the browser starts (RMEH-002-C/D).

    ``martin_poll_seconds`` is the sleep between catalog readiness probes after
    the one bounded martin restart; unit tests pass ``0`` to stay fast."""
    martin = origins["martin"]
    backend = origins["backend"]
    frontend = origins["frontend"]

    # Martin catalog: exactly the one source. The one bounded martin restart
    # mirrors the one bounded DB rebuild: on a fresh stack martin boots before
    # bootstrap creates vt_parcelas_catastro, so its startup catalog is empty;
    # one restart picks the view up (Martin reads the schema at startup).
    catalog = _probe_get(runner, f"{martin}/catalog")
    if _http_code(catalog.stdout) != 200:
        raise BootstrapPrerequisiteFailure(
            f"martin /catalog failed (HTTP {_http_code(catalog.stdout)}); "
            "browser must not start against a broken tile server"
        )
    sources = _catalog_sources(catalog.stdout)
    if "parcelas_catastro" not in sources:
        restart = runner.run(
            ["docker", "compose", "-f", COMPOSE_FILE, "restart", "martin"],
            kind=CommandKind.DOCKER_CONTROL,
        )
        if restart.exit_code != 0:
            raise BootstrapPrerequisiteFailure(
                f"martin restart failed ({restart.stderr.strip()}); "
                "catalog lacks source 'parcelas_catastro' and cannot be repaired"
            )
        import time as _time
        for _ in range(30):
            _time.sleep(martin_poll_seconds)
            catalog = _probe_get(runner, f"{martin}/catalog")
            if _http_code(catalog.stdout) == 200:
                sources = _catalog_sources(catalog.stdout)
                if "parcelas_catastro" in sources:
                    break
        else:
            sources = set()
    if "parcelas_catastro" not in sources:
        raise BootstrapPrerequisiteFailure(
            "martin catalog does not publish exactly source 'parcelas_catastro'; "
            f"sources={sorted(sources)}"
        )

    # One vector tile per declared click target (parcel interior point). The
    # URL matches the production client (useMartinLayers.ts): Martin v0.14.2
    # serves `/{source}/{z}/{x}/{y}` with the format negotiated via the Accept
    # header (the `.pbf` suffix is NOT a route in this version).
    tile_ok: list[str] = []
    for parcel in fixture.get("parcels") or []:
        alias = parcel["alias"]
        point = parcel.get("interiorPoint") or {}
        x, y, z = tile_xyz(float(point.get("lng", 0.0)), float(point.get("lat", 0.0)), camera_zoom)
        tile = _probe_get(runner, f"{martin}/parcelas_catastro/{z}/{x}/{y}", discard_body=True)
        code = _http_code(tile.stdout)
        if code == 204 or code != 200:
            raise BootstrapPrerequisiteFailure(
                f"martin tile {z}/{x}/{y} for {alias} returned HTTP {code}; "
                "a 204/empty source aborts before the browser"
            )
        # With the body discarded the last line is still the code; an empty
        # body would show up as an unparseable/missing code and abort.
        if not tile.stdout.strip():
            raise BootstrapPrerequisiteFailure(
                f"martin tile {z}/{x}/{y} for {alias} produced no probe output; "
                "aborting before the browser"
            )
        tile_ok.append(alias)

    # The ten pre-existing tests also click the REAL legacy parcel at its own
    # declared zoom (catastroFixture.ts PARCELA_FIXTURE.zoom). Fail closed on
    # it too: a non-200 legacy tile would soft-skip all ten and break the W9
    # exact-11 gate after the browser already ran.
    legacy = fixture.get("legacyParcel") or {}
    if legacy.get("nomenclature"):
        point = legacy.get("interiorPoint") or {}
        legacy_zoom = int(legacy.get("zoom") or 16)
        lx, ly, lz = tile_xyz(float(point.get("lng", 0.0)), float(point.get("lat", 0.0)), legacy_zoom)
        ltile = _probe_get(runner, f"{martin}/parcelas_catastro/{lz}/{lx}/{ly}", discard_body=True)
        lcode = _http_code(ltile.stdout)
        if lcode == 204 or lcode != 200:
            raise BootstrapPrerequisiteFailure(
                f"martin tile {lz}/{lx}/{ly} for legacy parcel "
                f"{legacy.get('nomenclature')} returned HTTP {lcode}; "
                "the ten pre-existing legacy tests would soft-skip"
            )
        if not ltile.stdout.strip():
            raise BootstrapPrerequisiteFailure(
                f"martin tile {lz}/{lx}/{ly} for legacy parcel produced no "
                "probe output; aborting before the browser"
            )
        tile_ok.append("LEGACY")

    # Backend /live (liveness only — the ficha POST proves the flag is on).
    live = _probe_get(runner, f"{backend}/live")
    backend_live = _http_code(live.stdout) == 200

    # Real ficha POST A/B/C as tipo=parcela (FICHA_ENABLED effective, not just
    # env-dumped).
    ficha_ok: list[str] = []
    for parcel in fixture.get("parcels") or []:
        alias = parcel["alias"]
        payload = json.dumps({"tipo": "parcela", "nomenclatura": parcel["nomenclature"]})
        ficha = _probe_post(runner, f"{backend}/api/v2/geo/analisis-zona", payload)
        if _http_code(ficha.stdout) != 200:
            raise BootstrapPrerequisiteFailure(
                f"ficha POST tipo=parcela for {alias} failed "
                f"(HTTP {_http_code(ficha.stdout)}); FICHA_ENABLED not effective"
            )
        ficha_ok.append(alias)

    # Legacy parcel ficha POST — the ten pre-existing tests open this ficha
    # through the real backend (rainfall mocked, ficha real).
    if legacy.get("nomenclature"):
        lpayload = json.dumps({"tipo": "parcela", "nomenclatura": legacy["nomenclature"]})
        lficha = _probe_post(runner, f"{backend}/api/v2/geo/analisis-zona", lpayload)
        if _http_code(lficha.stdout) != 200:
            raise BootstrapPrerequisiteFailure(
                f"ficha POST tipo=parcela for legacy parcel "
                f"{legacy['nomenclature']} failed (HTTP {_http_code(lficha.stdout)}); "
                "the ten pre-existing legacy tests would soft-skip"
            )
        ficha_ok.append("LEGACY")

    # Frontend /mapa from loopback (camera parameters).
    camera = (fixture.get("cameras") or {}).get("mobile") or {}
    qs = f"lat={camera.get('lat', -32.5)}&lng={camera.get('lng', -62.5)}&zoom={camera.get('zoom', camera_zoom)}"
    mapa = _probe_get(runner, f"{frontend}/mapa?{qs}")
    frontend_ok = _http_code(mapa.stdout) == 200

    return ServiceReport(
        martin_ok=True,
        martin_source="parcelas_catastro",
        tile_ok_for=tuple(tile_ok),
        backend_live=backend_live,
        ficha_ok_for=tuple(ficha_ok),
        frontend_ok=frontend_ok,
    )