-- =============================================
-- Migracion: Agregar cuenca a sugerencias
-- Fecha: 2024
-- Descripcion: Campo opcional para asignar sugerencias a cuencas
-- =============================================

-- Agregar columna cuenca_id a sugerencias
ALTER TABLE sugerencias
ADD COLUMN IF NOT EXISTS cuenca_id VARCHAR(20);

-- Crear indice para busquedas por cuenca
CREATE INDEX IF NOT EXISTS idx_sugerencias_cuenca ON sugerencias(cuenca_id) WHERE cuenca_id IS NOT NULL;

-- Comentario
COMMENT ON COLUMN sugerencias.cuenca_id IS 'Cuenca asociada: candil, ml, noroeste, norte (opcional, solo asignable por comision)';
