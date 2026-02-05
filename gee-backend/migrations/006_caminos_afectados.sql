-- =============================================
-- Migracion: Caminos Afectados por Inundaciones
-- Fecha: 2024
-- Descripcion: Almacena datos de caminos afectados por analisis de inundacion
-- =============================================

-- Tabla para almacenar caminos afectados por cada analisis
CREATE TABLE IF NOT EXISTS caminos_afectados (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    -- Relacion con analisis
    analisis_id UUID REFERENCES analisis_gee(id) ON DELETE CASCADE,

    -- Identificadores del camino (del GeoJSON original)
    camino_id VARCHAR(50),           -- caminoss:id

    -- Datos del camino
    nombre_completo VARCHAR(200),    -- fna: "Camino Provincial T269-03"
    nombre_generico VARCHAR(100),    -- gna: "Camino Provincial"
    ruta VARCHAR(50),                -- rtn: "T269-03"
    jerarquia VARCHAR(50),           -- hct: "Camino Terciario"
    superficie VARCHAR(50),          -- rst: "No pavimentado"
    red VARCHAR(50),                 -- red: "Terciaria"

    -- Consorcio Caminero
    consorcio_nombre VARCHAR(150),   -- ccn: "C.C. 269 - SAN MARCOS SUD"
    consorcio_codigo VARCHAR(20),    -- ccc: "CC269"
    consorcio_numero INTEGER,        -- rcc: 19

    -- Cuenca (calculada por interseccion)
    cuenca_id VARCHAR(20),           -- candil, ml, noroeste, norte

    -- Datos de afectacion
    longitud_total_km DECIMAL(10,3), -- lzn: longitud total del tramo
    longitud_afectada_km DECIMAL(10,3), -- km bajo agua
    porcentaje_afectado DECIMAL(5,2),   -- % del tramo afectado

    -- Geometria del tramo afectado (opcional, para visualizar en mapa)
    geojson TEXT,

    -- Timestamps
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Indices para busquedas eficientes
CREATE INDEX IF NOT EXISTS idx_caminos_afectados_analisis ON caminos_afectados(analisis_id);
CREATE INDEX IF NOT EXISTS idx_caminos_afectados_cuenca ON caminos_afectados(cuenca_id);
CREATE INDEX IF NOT EXISTS idx_caminos_afectados_consorcio ON caminos_afectados(consorcio_codigo);
CREATE INDEX IF NOT EXISTS idx_caminos_afectados_jerarquia ON caminos_afectados(jerarquia);
CREATE INDEX IF NOT EXISTS idx_caminos_afectados_red ON caminos_afectados(red);

-- RLS
ALTER TABLE caminos_afectados ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Service role full access to caminos_afectados"
ON caminos_afectados FOR ALL TO service_role
USING (true) WITH CHECK (true);

CREATE POLICY "Authenticated users can view caminos_afectados"
ON caminos_afectados FOR SELECT TO authenticated
USING (true);

-- Vista materializada para estadisticas rapidas (opcional)
-- CREATE MATERIALIZED VIEW IF NOT EXISTS caminos_afectados_stats AS
-- SELECT
--     analisis_id,
--     cuenca_id,
--     consorcio_codigo,
--     consorcio_nombre,
--     jerarquia,
--     red,
--     COUNT(*) as tramos_afectados,
--     SUM(longitud_total_km) as km_totales,
--     SUM(longitud_afectada_km) as km_afectados,
--     AVG(porcentaje_afectado) as porcentaje_promedio
-- FROM caminos_afectados
-- GROUP BY analisis_id, cuenca_id, consorcio_codigo, consorcio_nombre, jerarquia, red;

-- Comentarios
COMMENT ON TABLE caminos_afectados IS 'Caminos afectados por inundaciones detectadas en analisis GEE';
COMMENT ON COLUMN caminos_afectados.porcentaje_afectado IS 'Porcentaje del tramo bajo agua (0-100)';
COMMENT ON COLUMN caminos_afectados.cuenca_id IS 'Cuenca donde se encuentra: candil, ml, noroeste, norte';
