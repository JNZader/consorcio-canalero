"""Wave 7 database hygiene: informes_area indexes/checks and legacy matview cleanup.

Adds ``ix_informes_area_estado`` and ``ix_informes_area_usuario_created_at``
indexes plus ``NOT VALID`` blob-size ``CHECK`` constraints on ``informes_area``,
and drops the obsolete ``mv_caminos_por_zona`` materialized view (superseded by
``mv_caminos_unificados`` over ``red_vial``).

Revision ID: zz_wave7_db_hygiene
Revises: zz_wave1_postgis_indexes
"""

from typing import Sequence, Union

from alembic import op

revision: str = "zz_wave7_db_hygiene"
down_revision: Union[str, None] = "zz_wave1_postgis_indexes"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

INFORMES_INDEXES_SQL = """
DO $informes_idx$
BEGIN
    IF to_regclass('public.informes_area') IS NOT NULL THEN
        CREATE INDEX IF NOT EXISTS ix_informes_area_estado
            ON public.informes_area (estado);
        CREATE INDEX IF NOT EXISTS ix_informes_area_usuario_created_at
            ON public.informes_area (usuario_id, created_at DESC);
    END IF;
END
$informes_idx$;
"""

INFORMES_CHECKS_SQL = """
DO $informes_ck$
DECLARE
    rec record;
BEGIN
    IF to_regclass('public.informes_area') IS NULL THEN
        RETURN;
    END IF;

    FOR rec IN
        SELECT *
        FROM (
            VALUES
                (
                    'ck_informes_area_pdf_bytes_size',
                    'pdf_bytes IS NULL OR octet_length(pdf_bytes) <= 20971520'
                ),
                (
                    'ck_informes_area_kmz_bytes_size',
                    'kmz_bytes IS NULL OR octet_length(kmz_bytes) <= 26214400'
                ),
                (
                    'ck_informes_area_campo_paquete_size',
                    'campo_paquete IS NULL OR octet_length(campo_paquete) <= 20971520'
                )
        ) AS t(con_name, con_expr)
    LOOP
        IF NOT EXISTS (
            SELECT 1
            FROM pg_constraint
            WHERE conrelid = to_regclass('public.informes_area')
              AND conname = rec.con_name
        ) THEN
            EXECUTE format(
                'ALTER TABLE public.informes_area ADD CONSTRAINT %I CHECK (%s) NOT VALID',
                rec.con_name,
                rec.con_expr
            );
        END IF;
    END LOOP;
END
$informes_ck$;
"""

RESTORE_MV_CAMINOS_SQL = """
DO $restore_mv$
BEGIN
    IF to_regclass('public.mv_caminos_por_zona') IS NULL
       AND to_regclass('public.zonas_operativas') IS NOT NULL
       AND to_regclass('public.caminos_geo') IS NOT NULL THEN
        EXECUTE $mv$
            CREATE MATERIALIZED VIEW public.mv_caminos_por_zona AS
            SELECT
                z.id                AS zona_id,
                z.nombre            AS zona_nombre,
                z.cuenca,
                COALESCE(c.consorcio_codigo, c.jerarquia, 'sin_tipo') AS consorcio_codigo,
                COALESCE(c.consorcio_nombre, c.jerarquia, 'Sin tipo') AS consorcio_nombre,
                SUM(
                    ST_Length(ST_Transform(
                        ST_Intersection(c.geometria, z.geometria),
                        32720
                    ))
                ) / 1000.0          AS km_caminos
            FROM public.zonas_operativas z
            JOIN public.caminos_geo c ON ST_Intersects(c.geometria, z.geometria)
            GROUP BY z.id, z.nombre, z.cuenca,
                COALESCE(c.consorcio_codigo, c.jerarquia, 'sin_tipo'),
                COALESCE(c.consorcio_nombre, c.jerarquia, 'Sin tipo')
            WITH DATA
        $mv$;
        CREATE INDEX IF NOT EXISTS ix_mv_caminos_zona
            ON public.mv_caminos_por_zona (zona_id);
        CREATE INDEX IF NOT EXISTS ix_mv_caminos_cuenca
            ON public.mv_caminos_por_zona (cuenca);
        CREATE INDEX IF NOT EXISTS ix_mv_caminos_consorcio
            ON public.mv_caminos_por_zona (consorcio_codigo);
    END IF;
END
$restore_mv$;
"""

UPGRADE_SQL: tuple[str, ...] = (
    INFORMES_INDEXES_SQL,
    INFORMES_CHECKS_SQL,
    "DROP MATERIALIZED VIEW IF EXISTS public.mv_caminos_por_zona",
)

DOWNGRADE_SQL: tuple[str, ...] = (
    RESTORE_MV_CAMINOS_SQL,
    "ALTER TABLE IF EXISTS public.informes_area DROP CONSTRAINT IF EXISTS ck_informes_area_campo_paquete_size",
    "ALTER TABLE IF EXISTS public.informes_area DROP CONSTRAINT IF EXISTS ck_informes_area_kmz_bytes_size",
    "ALTER TABLE IF EXISTS public.informes_area DROP CONSTRAINT IF EXISTS ck_informes_area_pdf_bytes_size",
    "DROP INDEX IF EXISTS public.ix_informes_area_usuario_created_at",
    "DROP INDEX IF EXISTS public.ix_informes_area_estado",
)


def upgrade() -> None:
    for statement in UPGRADE_SQL:
        op.execute(statement)


def downgrade() -> None:
    for statement in DOWNGRADE_SQL:
        op.execute(statement)
