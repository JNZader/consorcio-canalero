"""add geo materialized views

Revision ID: k5f2g1h2i361
Revises: j4e1f0g1h250
Create Date: 2026-03-24
"""

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "k5f2g1h2i361"
down_revision: Union[str, None] = "j4e1f0g1h250"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# ── SQL: mv_dashboard_geo_stats ────────────────────

MV_DASHBOARD_GEO_STATS = """
CREATE MATERIALIZED VIEW mv_dashboard_geo_stats AS
SELECT
    1 AS id,
    -- geo_layers counts
    COUNT(*) FILTER (WHERE src = 'geo_layers') AS total_geo_layers,
    COUNT(*) FILTER (WHERE src = 'geo_layers' AND tipo = 'slope') AS geo_layers_slope,
    COUNT(*) FILTER (WHERE src = 'geo_layers' AND tipo = 'aspect') AS geo_layers_aspect,
    COUNT(*) FILTER (WHERE src = 'geo_layers' AND tipo = 'flow_dir') AS geo_layers_flow_dir,
    COUNT(*) FILTER (WHERE src = 'geo_layers' AND tipo = 'flow_acc') AS geo_layers_flow_acc,
    COUNT(*) FILTER (WHERE src = 'geo_layers' AND tipo = 'twi') AS geo_layers_twi,
    COUNT(*) FILTER (WHERE src = 'geo_layers' AND tipo = 'hand') AS geo_layers_hand,
    COUNT(*) FILTER (WHERE src = 'geo_layers' AND tipo = 'drainage') AS geo_layers_drainage,
    COUNT(*) FILTER (WHERE src = 'geo_layers' AND tipo = 'terrain_class') AS geo_layers_terrain_class,
    -- geo_jobs counts
    COUNT(*) FILTER (WHERE src = 'geo_jobs') AS total_geo_jobs,
    COUNT(*) FILTER (WHERE src = 'geo_jobs' AND estado = 'pending') AS geo_jobs_pending,
    COUNT(*) FILTER (WHERE src = 'geo_jobs' AND estado = 'running') AS geo_jobs_running,
    COUNT(*) FILTER (WHERE src = 'geo_jobs' AND estado = 'completed') AS geo_jobs_completed,
    COUNT(*) FILTER (WHERE src = 'geo_jobs' AND estado = 'failed') AS geo_jobs_failed,
    -- geo_analisis_gee counts
    COUNT(*) FILTER (WHERE src = 'geo_analisis') AS total_geo_analisis,
    COUNT(*) FILTER (WHERE src = 'geo_analisis' AND tipo = 'flood') AS geo_analisis_flood,
    COUNT(*) FILTER (WHERE src = 'geo_analisis' AND tipo = 'vegetation') AS geo_analisis_vegetation,
    COUNT(*) FILTER (WHERE src = 'geo_analisis' AND tipo = 'ndvi') AS geo_analisis_ndvi,
    COUNT(*) FILTER (WHERE src = 'geo_analisis' AND tipo = 'custom') AS geo_analisis_custom,
    COUNT(*) FILTER (WHERE src = 'geo_analisis' AND estado = 'pending') AS geo_analisis_pending,
    COUNT(*) FILTER (WHERE src = 'geo_analisis' AND estado = 'running') AS geo_analisis_running,
    COUNT(*) FILTER (WHERE src = 'geo_analisis' AND estado = 'completed') AS geo_analisis_completed,
    COUNT(*) FILTER (WHERE src = 'geo_analisis' AND estado = 'failed') AS geo_analisis_failed,
    -- zonas_operativas count
    (SELECT COUNT(*) FROM zonas_operativas) AS total_zonas_operativas,
    -- alertas activas count
    (SELECT COUNT(*) FROM alertas_geo WHERE activa = true) AS total_alertas_activas,
    -- puntos_conflicto count
    (SELECT COUNT(*) FROM puntos_conflicto) AS total_conflictos
FROM (
    SELECT 'geo_layers' AS src, tipo::text AS tipo, NULL AS estado FROM geo_layers
    UNION ALL
    SELECT 'geo_jobs' AS src, tipo::text AS tipo, estado::text AS estado FROM geo_jobs
    UNION ALL
    SELECT 'geo_analisis' AS src, tipo::text AS tipo, estado::text AS estado FROM geo_analisis_gee
) combined;
"""

IX_DASHBOARD_GEO_STATS = """
CREATE UNIQUE INDEX ix_mv_dashboard_geo_stats_id
    ON mv_dashboard_geo_stats (id);
"""

# ── SQL: mv_hci_por_zona ──────────────────────────

MV_HCI_POR_ZONA = """
CREATE MATERIALIZED VIEW mv_hci_por_zona AS
SELECT DISTINCT ON (zo.id)
    zo.id        AS zona_id,
    zo.nombre    AS zona_nombre,
    zo.cuenca,
    zo.superficie_ha,
    ih.indice_final,
    ih.nivel_riesgo,
    ih.fecha_calculo
FROM zonas_operativas zo
JOIN indices_hidricos ih ON ih.zona_id = zo.id
ORDER BY zo.id, ih.fecha_calculo DESC;
"""

IX_HCI_POR_ZONA = """
CREATE UNIQUE INDEX ix_mv_hci_por_zona_zona_id
    ON mv_hci_por_zona (zona_id);
"""

# ── SQL: mv_alertas_resumen ───────────────────────

MV_ALERTAS_RESUMEN = """
CREATE MATERIALIZED VIEW mv_alertas_resumen AS
SELECT
    1 AS id,
    COUNT(*) FILTER (WHERE nivel = 'info') AS alertas_info,
    COUNT(*) FILTER (WHERE nivel = 'advertencia') AS alertas_advertencia,
    COUNT(*) FILTER (WHERE nivel = 'critico') AS alertas_critico,
    COUNT(*) FILTER (WHERE tipo = 'umbral_superado') AS alertas_umbral_superado,
    COUNT(*) FILTER (WHERE tipo = 'lluvia_reciente') AS alertas_lluvia_reciente,
    COUNT(*) FILTER (WHERE tipo = 'cambio_sar') AS alertas_cambio_sar,
    MAX(created_at) AS fecha_alerta_mas_reciente
FROM alertas_geo
WHERE activa = true;
"""

IX_ALERTAS_RESUMEN = """
CREATE UNIQUE INDEX ix_mv_alertas_resumen_id
    ON mv_alertas_resumen (id);
"""


def upgrade() -> None:
    # mv_dashboard_geo_stats
    op.execute(MV_DASHBOARD_GEO_STATS)
    op.execute(IX_DASHBOARD_GEO_STATS)

    # mv_hci_por_zona
    op.execute(MV_HCI_POR_ZONA)
    op.execute(IX_HCI_POR_ZONA)

    # mv_alertas_resumen
    op.execute(MV_ALERTAS_RESUMEN)
    op.execute(IX_ALERTAS_RESUMEN)


def downgrade() -> None:
    op.execute("DROP MATERIALIZED VIEW IF EXISTS mv_alertas_resumen CASCADE;")
    op.execute("DROP MATERIALIZED VIEW IF EXISTS mv_hci_por_zona CASCADE;")
    op.execute("DROP MATERIALIZED VIEW IF EXISTS mv_dashboard_geo_stats CASCADE;")
