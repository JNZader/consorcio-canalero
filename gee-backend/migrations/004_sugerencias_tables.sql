-- =============================================
-- Migracion: Sistema de Sugerencias y Temas
-- Fecha: 2024
-- Descripcion: Tablas para sugerencias ciudadanas y temas de comision
-- =============================================

-- Tabla principal de sugerencias/temas
CREATE TABLE IF NOT EXISTS sugerencias (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    -- Tipo: 'ciudadana' (de ciudadanos) o 'interna' (de la comision)
    tipo VARCHAR(20) NOT NULL DEFAULT 'ciudadana',

    -- Contenido
    titulo VARCHAR(200) NOT NULL,
    descripcion TEXT NOT NULL,

    -- Autor (para sugerencias ciudadanas)
    contacto_nombre VARCHAR(100),
    contacto_email VARCHAR(100),
    contacto_telefono VARCHAR(20),

    -- Autor (para temas internos - miembro de la comision)
    autor_id UUID REFERENCES auth.users(id),

    -- Clasificacion
    categoria VARCHAR(50), -- 'infraestructura', 'servicios', 'administrativo', 'otro'

    -- Gestion
    estado VARCHAR(20) DEFAULT 'pendiente', -- pendiente, en_agenda, tratado, descartado
    prioridad VARCHAR(20) DEFAULT 'normal', -- baja, normal, alta, urgente

    -- Para reunion
    fecha_reunion DATE, -- Fecha de reunion donde se tratara
    notas_comision TEXT, -- Notas internas de la comision
    resolucion TEXT, -- Resultado despues de tratarlo

    -- Timestamps
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Indice para busquedas
CREATE INDEX IF NOT EXISTS idx_sugerencias_tipo ON sugerencias(tipo);
CREATE INDEX IF NOT EXISTS idx_sugerencias_estado ON sugerencias(estado);
CREATE INDEX IF NOT EXISTS idx_sugerencias_prioridad ON sugerencias(prioridad);
CREATE INDEX IF NOT EXISTS idx_sugerencias_fecha_reunion ON sugerencias(fecha_reunion);
CREATE INDEX IF NOT EXISTS idx_sugerencias_created ON sugerencias(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_sugerencias_autor ON sugerencias(autor_id) WHERE autor_id IS NOT NULL;

-- Historial de cambios en sugerencias
CREATE TABLE IF NOT EXISTS sugerencias_historial (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    sugerencia_id UUID NOT NULL REFERENCES sugerencias(id) ON DELETE CASCADE,
    usuario_id UUID REFERENCES auth.users(id),
    accion VARCHAR(50) NOT NULL, -- 'creado', 'estado_cambiado', 'prioridad_cambiada', 'agendado', 'resuelto'
    estado_anterior VARCHAR(20),
    estado_nuevo VARCHAR(20),
    notas TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_sug_historial_sugerencia ON sugerencias_historial(sugerencia_id);
CREATE INDEX IF NOT EXISTS idx_sug_historial_created ON sugerencias_historial(created_at DESC);

-- RLS Policies
ALTER TABLE sugerencias ENABLE ROW LEVEL SECURITY;
ALTER TABLE sugerencias_historial ENABLE ROW LEVEL SECURITY;

-- Service role tiene acceso completo
CREATE POLICY "Service role full access to sugerencias"
ON sugerencias FOR ALL TO service_role
USING (true) WITH CHECK (true);

CREATE POLICY "Service role full access to sugerencias_historial"
ON sugerencias_historial FOR ALL TO service_role
USING (true) WITH CHECK (true);

-- Usuarios autenticados pueden ver sugerencias
CREATE POLICY "Authenticated users can view sugerencias"
ON sugerencias FOR SELECT TO authenticated
USING (true);

-- Usuarios autenticados pueden crear temas internos
CREATE POLICY "Authenticated users can create internal topics"
ON sugerencias FOR INSERT TO authenticated
WITH CHECK (tipo = 'interna' AND autor_id = auth.uid());

-- Operadores y admins pueden actualizar
CREATE POLICY "Staff can update sugerencias"
ON sugerencias FOR UPDATE TO authenticated
USING (
    EXISTS (
        SELECT 1 FROM perfiles
        WHERE id = auth.uid()
        AND rol IN ('admin', 'operador')
    )
);

-- Usuarios autenticados pueden ver historial
CREATE POLICY "Authenticated users can view sugerencias_historial"
ON sugerencias_historial FOR SELECT TO authenticated
USING (true);

-- Trigger para updated_at
CREATE OR REPLACE FUNCTION update_sugerencias_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trigger_sugerencias_updated_at
    BEFORE UPDATE ON sugerencias
    FOR EACH ROW
    EXECUTE FUNCTION update_sugerencias_updated_at();

-- Comentarios
COMMENT ON TABLE sugerencias IS 'Sugerencias ciudadanas y temas internos para reuniones de comision';
COMMENT ON COLUMN sugerencias.tipo IS 'ciudadana: enviada por ciudadano, interna: propuesta por miembro de comision';
COMMENT ON COLUMN sugerencias.estado IS 'pendiente, en_agenda, tratado, descartado';
COMMENT ON COLUMN sugerencias.prioridad IS 'baja, normal, alta, urgente';
COMMENT ON COLUMN sugerencias.fecha_reunion IS 'Fecha de la reunion donde se tratara este tema';
