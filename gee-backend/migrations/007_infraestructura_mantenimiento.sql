-- Tabla de activos de infraestructura
CREATE TABLE IF NOT EXISTS infraestructura (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    nombre TEXT NOT NULL,
    tipo TEXT NOT NULL, -- 'canal', 'alcantarilla', 'puente', 'otro'
    descripcion TEXT,
    latitud DOUBLE PRECISION NOT NULL,
    longitud DOUBLE PRECISION NOT NULL,
    cuenca TEXT, -- 'candil', 'ml', etc.
    estado_actual TEXT DEFAULT 'bueno', -- 'bueno', 'regular', 'malo', 'critico'
    ultima_inspeccion TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Tabla de logs de mantenimiento
CREATE TABLE IF NOT EXISTS mantenimiento_logs (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    infraestructura_id UUID REFERENCES infraestructura(id) ON DELETE CASCADE,
    fecha TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    tipo_tarea TEXT NOT NULL, -- 'limpieza', 'reparacion', 'inspeccion', 'obra_nueva'
    descripcion TEXT NOT NULL,
    operario_nombre TEXT,
    costo_estimado DECIMAL(12, 2),
    fotos_urls TEXT[], -- Array de URLs de fotos en Supabase Storage
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Indices para busqueda rapida
CREATE INDEX IF NOT EXISTS idx_infraestructura_cuenca ON infraestructura(cuenca);
CREATE INDEX IF NOT EXISTS idx_mantenimiento_infra_id ON mantenimiento_logs(infraestructura_id);
