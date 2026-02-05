-- Tabla de Trámites Administrativos (Recursos Hídricos)
CREATE TABLE IF NOT EXISTS tramites (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    titulo TEXT NOT NULL,
    numero_expediente TEXT UNIQUE,
    descripcion TEXT,
    reparticion TEXT DEFAULT 'Recursos Hídricos Provincia',
    estado TEXT DEFAULT 'iniciado', -- 'iniciado', 'en_revision', 'aprobado', 'detenido', 'finalizado'
    prioridad TEXT DEFAULT 'normal',
    fecha_inicio DATE DEFAULT CURRENT_DATE,
    ultima_actualizacion TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Avances de los trámites
CREATE TABLE IF NOT EXISTS tramite_avances (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tramite_id UUID REFERENCES tramites(id) ON DELETE CASCADE,
    fecha TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    titulo_avance TEXT NOT NULL,
    comentario TEXT,
    documentos_urls TEXT[], -- PDF de resoluciones, etc.
    usuario_id UUID -- Quién cargó el avance
);

-- Logs de gestión para Reportes y Sugerencias
CREATE TABLE IF NOT EXISTS gestion_seguimiento (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    entidad_tipo TEXT NOT NULL, -- 'reporte' o 'sugerencia'
    entidad_id UUID NOT NULL, -- ID del reporte o sugerencia
    estado_anterior TEXT,
    estado_nuevo TEXT,
    comentario_publico TEXT, -- Lo que ve el ciudadano
    comentario_interno TEXT, -- Solo para el consorcio
    fecha TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    usuario_gestion UUID -- Operador que realizó el cambio
);

CREATE INDEX IF NOT EXISTS idx_tramite_expediente ON tramites(numero_expediente);
CREATE INDEX IF NOT EXISTS idx_seguimiento_entidad ON gestion_seguimiento(entidad_tipo, entidad_id);
