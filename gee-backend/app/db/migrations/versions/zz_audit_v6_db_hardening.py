"""Audit v6 database hardening.

FK indexes (DB-06), GiST on canal catchments (DB-07), SRID/type checks,
stored EPSG:32720 parcel geometry (DB-02), Martin parcel matview (DB-08),
timestamptz on geo analysis bounds (DB-09), and materialized-view ownership
for the non-superuser app role (DB-04).

Revision ID: zz_audit_v6_db
Revises: lluvia_ext_006
"""

from typing import Sequence, Union

from alembic import op

revision: str = "zz_audit_v6_db"
down_revision: Union[str, None] = "lluvia_ext_006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

APP_ROLE = "consorcio_app"
PARCEL_VIEW = "vt_parcelas_catastro"
PARCEL_VIEW_COMMENT = "migration-owned DB-08 audit v6"
REFRESHABLE_MATVIEWS = (
    "mv_dashboard_geo_stats",
    "mv_hci_por_zona",
    "mv_alertas_resumen",
    "mv_suelos_por_zona",
    "mv_canales_por_zona",
    "mv_caminos_por_zona",
    PARCEL_VIEW,
)

_MATVIEW_LIST_SQL = ", ".join(f"'{name}'" for name in REFRESHABLE_MATVIEWS)

# Single-column foreign keys whose leading column is not already indexed.
# ``CREATE INDEX CONCURRENTLY`` cannot run inside Alembic's transaction.
FK_INDEXES_SQL = """
DO $fk$
DECLARE
    rec record;
    idx_name text;
BEGIN
    FOR rec IN
        SELECT n.nspname AS nsp, c.relname AS rel, a.attname AS att
        FROM pg_constraint fk
        JOIN pg_class c ON c.oid = fk.conrelid
        JOIN pg_namespace n ON n.oid = c.relnamespace
        JOIN pg_attribute a
          ON a.attrelid = c.oid AND a.attnum = fk.conkey[1]
        WHERE fk.contype = 'f'
          AND n.nspname = 'public'
          AND array_length(fk.conkey, 1) = 1
          AND NOT EXISTS (
              SELECT 1
              FROM pg_index i
              WHERE i.indrelid = fk.conrelid
                AND i.indisvalid
                AND i.indkey[0] = a.attnum
          )
    LOOP
        idx_name := left('ix_fk_' || rec.rel || '_' || rec.att, 63);
        EXECUTE format(
            'CREATE INDEX IF NOT EXISTS %I ON %I.%I (%I)',
            idx_name, rec.nsp, rec.rel, rec.att
        );
    END LOOP;
END
$fk$;
"""

DROP_FK_INDEXES_SQL = r"""
DO $drop_fk$
DECLARE
    rec record;
BEGIN
    FOR rec IN
        SELECT n.nspname AS nsp, ic.relname AS idx
        FROM pg_class ic
        JOIN pg_namespace n ON n.oid = ic.relnamespace
        JOIN pg_index i ON i.indexrelid = ic.oid
        WHERE n.nspname = 'public'
          AND ic.relkind = 'i'
          AND ic.relname LIKE 'ix\_fk\_%' ESCAPE '\'
    LOOP
        EXECUTE format('DROP INDEX IF EXISTS %I.%I', rec.nsp, rec.idx);
    END LOOP;
END
$drop_fk$;
"""

CATCHMENT_GIST_SQL = """
DO $gist$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_schema = 'public' AND table_name = 'canal_catchment'
    ) THEN
        EXECUTE
            'CREATE INDEX IF NOT EXISTS ix_canal_catchment_geometria '
            'ON canal_catchment USING gist (geometria)';
    END IF;
END
$gist$;
"""

# NOT VALID so a bad historical row does not abort the migration. New writes
# are still checked. parcelas stays generic-enough for POLYGON and
# MULTIPOLYGON (migration b9 widened it on purpose). canal_suggestions stays
# a generic geometry: point, line and polygon are all legal.
PARCEL_CHECK_SQL = """
DO $ck$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_schema = 'public' AND table_name = 'parcelas_catastro'
    ) AND NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'ck_parcelas_catastro_geometria_srid'
    ) THEN
        ALTER TABLE parcelas_catastro
            ADD CONSTRAINT ck_parcelas_catastro_geometria_srid
            CHECK (
                geometria IS NULL
                OR (
                    ST_SRID(geometria) = 4326
                    AND ST_IsValid(geometria)
                    AND GeometryType(geometria) IN ('POLYGON', 'MULTIPOLYGON')
                )
            ) NOT VALID;
    END IF;
END
$ck$;
"""

SUGGESTION_CHECK_SQL = """
DO $ck$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_schema = 'public' AND table_name = 'canal_suggestions'
    ) AND NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'ck_canal_suggestions_geometry_srid'
    ) THEN
        ALTER TABLE canal_suggestions
            ADD CONSTRAINT ck_canal_suggestions_geometry_srid
            CHECK (
                geometry IS NULL
                OR (
                    ST_SRID(geometry) = 4326
                    AND ST_IsValid(geometry)
                    AND GeometryType(geometry) IN (
                        'POINT', 'LINESTRING', 'POLYGON',
                        'MULTIPOINT', 'MULTILINESTRING', 'MULTIPOLYGON'
                    )
                )
            ) NOT VALID;
    END IF;
END
$ck$;
"""

PARCEL_32720_SQL = """
ALTER TABLE parcelas_catastro
    ADD COLUMN IF NOT EXISTS geometria_32720 geometry(Geometry, 32720);
"""

PARCEL_32720_TRIGGER_FN_SQL = """
CREATE OR REPLACE FUNCTION parcelas_catastro_sync_32720()
RETURNS trigger
LANGUAGE plpgsql
AS $fn$
BEGIN
    IF NEW.geometria IS NULL THEN
        NEW.geometria_32720 := NULL;
    ELSE
        NEW.geometria_32720 := ST_Transform(NEW.geometria, 32720);
    END IF;
    RETURN NEW;
END
$fn$;
"""

PARCEL_32720_DROP_TRIGGER_SQL = (
    "DROP TRIGGER IF EXISTS parcelas_catastro_sync_32720 ON parcelas_catastro"
)

PARCEL_32720_TRIGGER_SQL = """
CREATE TRIGGER parcelas_catastro_sync_32720
BEFORE INSERT OR UPDATE OF geometria ON parcelas_catastro
FOR EACH ROW
EXECUTE FUNCTION parcelas_catastro_sync_32720()
"""

PARCEL_32720_BACKFILL_SQL = """
UPDATE parcelas_catastro
SET geometria_32720 = ST_Transform(geometria, 32720)
WHERE geometria IS NOT NULL
  AND geometria_32720 IS NULL;
"""

PARCEL_32720_GIST_SQL = """
CREATE INDEX IF NOT EXISTS ix_parcelas_catastro_geom_32720
    ON parcelas_catastro USING gist (geometria_32720);
"""

# A plain VIEW would fail the rainfall harness (it requires relkind 'm').
# An existing relation is left in place. A regular view is replaced because
# it holds no data of its own. The harness marker comment is never overwritten.
PARCEL_VIEW_SQL = f"""
DO $mv$
DECLARE
    kind "char";
BEGIN
    SELECT c.relkind INTO kind
    FROM pg_class c
    JOIN pg_namespace n ON n.oid = c.relnamespace
    WHERE n.nspname = 'public' AND c.relname = '{PARCEL_VIEW}';

    IF kind = 'v' THEN
        EXECUTE 'DROP VIEW public.{PARCEL_VIEW}';
        kind := NULL;
    END IF;

    IF kind IS NULL THEN
        EXECUTE $create$
            CREATE MATERIALIZED VIEW {PARCEL_VIEW} AS
            SELECT id,
                   nomenclatura,
                   tipo_parcela,
                   desig_oficial,
                   departamento,
                   pedania,
                   superficie_ha,
                   nro_cuenta,
                   par_idparcela,
                   geometria
            FROM parcelas_catastro
            WITH DATA
        $create$;
    END IF;
END
$mv$;
"""

PARCEL_VIEW_INDEX_SQL = f"""
DO $idx$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = '{PARCEL_VIEW}'
          AND column_name = 'id'
    ) THEN
        EXECUTE
            'CREATE UNIQUE INDEX IF NOT EXISTS ux_vt_parcelas_catastro_id '
            'ON {PARCEL_VIEW} (id)';
    END IF;
END
$idx$;
"""

PARCEL_VIEW_COMMENT_SQL = f"""
DO $cmt$
DECLARE
    current_comment text;
    kind "char";
BEGIN
    SELECT c.relkind, d.description INTO kind, current_comment
    FROM pg_class c
    JOIN pg_namespace n ON n.oid = c.relnamespace
    LEFT JOIN pg_description d ON d.objoid = c.oid AND d.objsubid = 0
    WHERE n.nspname = 'public' AND c.relname = '{PARCEL_VIEW}';

    IF kind = 'm' AND (current_comment IS NULL OR current_comment = '') THEN
        EXECUTE 'COMMENT ON MATERIALIZED VIEW {PARCEL_VIEW} IS '
            || quote_literal('{PARCEL_VIEW_COMMENT}');
    END IF;
END
$cmt$;
"""

TIMESTAMPTZ_SQL = """
DO $tz$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = 'geo_analisis_gee'
          AND column_name = 'fecha_inicio'
          AND data_type = 'timestamp without time zone'
    ) THEN
        ALTER TABLE geo_analisis_gee
            ALTER COLUMN fecha_inicio TYPE timestamptz
            USING fecha_inicio AT TIME ZONE 'UTC';
    END IF;
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = 'geo_analisis_gee'
          AND column_name = 'fecha_fin'
          AND data_type = 'timestamp without time zone'
    ) THEN
        ALTER TABLE geo_analisis_gee
            ALTER COLUMN fecha_fin TYPE timestamptz
            USING fecha_fin AT TIME ZONE 'UTC';
    END IF;
END
$tz$;
"""

TIMESTAMP_SQL = """
DO $tz$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = 'geo_analisis_gee'
          AND column_name = 'fecha_inicio'
          AND data_type = 'timestamp with time zone'
    ) THEN
        ALTER TABLE geo_analisis_gee
            ALTER COLUMN fecha_inicio TYPE timestamp without time zone
            USING fecha_inicio AT TIME ZONE 'UTC';
    END IF;
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = 'geo_analisis_gee'
          AND column_name = 'fecha_fin'
          AND data_type = 'timestamp with time zone'
    ) THEN
        ALTER TABLE geo_analisis_gee
            ALTER COLUMN fecha_fin TYPE timestamp without time zone
            USING fecha_fin AT TIME ZONE 'UTC';
    END IF;
END
$tz$;
"""

# PostgreSQL has no GRANT REFRESH. REFRESH CONCURRENTLY cannot run inside a
# SECURITY DEFINER function, so the app role must own the views it refreshes.
# No-op until provision_app_rw.sql creates the role (migrations run first).
OWNERSHIP_SQL = f"""
DO $own$
DECLARE
    rel record;
    idx record;
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{APP_ROLE}') THEN
        RETURN;
    END IF;
    FOR rel IN
        SELECT c.oid, c.relname
        FROM pg_class c
        JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE n.nspname = 'public'
          AND c.relkind = 'm'
          AND c.relname = ANY (ARRAY[{_MATVIEW_LIST_SQL}])
    LOOP
        EXECUTE format(
            'ALTER MATERIALIZED VIEW public.%I OWNER TO %I',
            rel.relname, '{APP_ROLE}'
        );
        FOR idx IN
            SELECT ic.relname
            FROM pg_index i
            JOIN pg_class ic ON ic.oid = i.indexrelid
            WHERE i.indrelid = rel.oid
        LOOP
            EXECUTE format(
                'ALTER INDEX public.%I OWNER TO %I',
                idx.relname, '{APP_ROLE}'
            );
        END LOOP;
    END LOOP;
END
$own$;
"""

RESTORE_OWNERSHIP_SQL = f"""
DO $own$
DECLARE
    rel record;
    idx record;
    migrator text := current_user;
BEGIN
    FOR rel IN
        SELECT c.oid, c.relname
        FROM pg_class c
        JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE n.nspname = 'public'
          AND c.relkind = 'm'
          AND c.relname = ANY (ARRAY[{_MATVIEW_LIST_SQL}])
    LOOP
        EXECUTE format(
            'ALTER MATERIALIZED VIEW public.%I OWNER TO %I',
            rel.relname, migrator
        );
        FOR idx IN
            SELECT ic.relname
            FROM pg_index i
            JOIN pg_class ic ON ic.oid = i.indexrelid
            WHERE i.indrelid = rel.oid
        LOOP
            EXECUTE format('ALTER INDEX public.%I OWNER TO %I', idx.relname, migrator);
        END LOOP;
    END LOOP;
END
$own$;
"""

DROP_PARCEL_VIEW_SQL = f"""
DO $drop_mv$
DECLARE
    kind "char";
    current_comment text;
BEGIN
    SELECT c.relkind, d.description INTO kind, current_comment
    FROM pg_class c
    JOIN pg_namespace n ON n.oid = c.relnamespace
    LEFT JOIN pg_description d ON d.objoid = c.oid AND d.objsubid = 0
    WHERE n.nspname = 'public' AND c.relname = '{PARCEL_VIEW}';
    IF kind = 'm' AND current_comment = '{PARCEL_VIEW_COMMENT}' THEN
        EXECUTE 'DROP MATERIALIZED VIEW public.{PARCEL_VIEW}';
    END IF;
END
$drop_mv$;
"""

UPGRADE_SQL: tuple[str, ...] = (
    FK_INDEXES_SQL,
    CATCHMENT_GIST_SQL,
    PARCEL_CHECK_SQL,
    SUGGESTION_CHECK_SQL,
    PARCEL_32720_SQL,
    PARCEL_32720_TRIGGER_FN_SQL,
    PARCEL_32720_DROP_TRIGGER_SQL,
    PARCEL_32720_TRIGGER_SQL,
    PARCEL_32720_BACKFILL_SQL,
    PARCEL_32720_GIST_SQL,
    PARCEL_VIEW_SQL,
    PARCEL_VIEW_INDEX_SQL,
    PARCEL_VIEW_COMMENT_SQL,
    TIMESTAMPTZ_SQL,
    OWNERSHIP_SQL,
)

DOWNGRADE_SQL: tuple[str, ...] = (
    RESTORE_OWNERSHIP_SQL,
    DROP_PARCEL_VIEW_SQL,
    TIMESTAMP_SQL,
    "DROP TRIGGER IF EXISTS parcelas_catastro_sync_32720 ON parcelas_catastro",
    "DROP FUNCTION IF EXISTS parcelas_catastro_sync_32720()",
    "DROP INDEX IF EXISTS ix_parcelas_catastro_geom_32720",
    "ALTER TABLE parcelas_catastro DROP COLUMN IF EXISTS geometria_32720",
    "ALTER TABLE parcelas_catastro DROP CONSTRAINT IF EXISTS ck_parcelas_catastro_geometria_srid",
    "ALTER TABLE canal_suggestions DROP CONSTRAINT IF EXISTS ck_canal_suggestions_geometry_srid",
    "DROP INDEX IF EXISTS ix_canal_catchment_geometria",
    DROP_FK_INDEXES_SQL,
)


def _run(statements: tuple[str, ...]) -> None:
    for statement in statements:
        op.execute(statement)


def upgrade() -> None:
    _run(UPGRADE_SQL)


def downgrade() -> None:
    _run(DOWNGRADE_SQL)
