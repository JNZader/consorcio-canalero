-- Tabla de Reuniones de Comisión
CREATE TABLE IF NOT EXISTS reuniones (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    titulo TEXT NOT NULL,
    fecha_reunion TIMESTAMP WITH TIME ZONE NOT NULL,
    lugar TEXT DEFAULT 'Sede Consorcio',
    estado TEXT DEFAULT 'planificada', -- 'planificada', 'en_curso', 'finalizada', 'cancelada'
    acta_resumen TEXT, -- Notas finales de la reunión
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Temas de la Agenda (Items)
CREATE TABLE IF NOT EXISTS agenda_items (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    reunion_id UUID REFERENCES reuniones(id) ON DELETE CASCADE,
    orden INTEGER DEFAULT 0,
    titulo TEXT NOT NULL,
    descripcion TEXT,
    completado BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Referencias Cruzadas (El @arroba de elementos)
CREATE TABLE IF NOT EXISTS agenda_referencias (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    agenda_item_id UUID REFERENCES agenda_items(id) ON DELETE CASCADE,
    entidad_tipo TEXT NOT NULL, -- 'reporte', 'sugerencia', 'tramite', 'infraestructura', 'camino', 'poi'
    entidad_id UUID NOT NULL, -- ID del elemento referido
    metadata JSONB, -- Para guardar datos rápidos como nombre/folio y no hacer tantos joins
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_reunion_fecha ON reuniones(fecha_reunion);
CREATE INDEX IF NOT EXISTS idx_agenda_item_reunion ON agenda_items(reunion_id);
CREATE INDEX IF NOT EXISTS idx_referencia_item ON agenda_referencias(agenda_item_id);
