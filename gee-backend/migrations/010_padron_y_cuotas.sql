-- Tabla de Consorcistas
CREATE TABLE IF NOT EXISTS consorcistas (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    nombre TEXT NOT NULL,
    apellido TEXT NOT NULL,
    cuit TEXT UNIQUE NOT NULL,
    representa_a TEXT, -- Nombre de la empresa o establecimiento
    email TEXT,
    telefono TEXT,
    direccion_postal TEXT,
    activo BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Tabla de Pagos de Cuotas Anuales
CREATE TABLE IF NOT EXISTS cuotas_pagos (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    consorcista_id UUID REFERENCES consorcistas(id) ON DELETE CASCADE,
    anio INTEGER NOT NULL,
    monto DECIMAL(12, 2),
    fecha_pago DATE,
    estado TEXT DEFAULT 'pendiente', -- 'pendiente', 'pagado', 'parcial', 'exento'
    metodo_pago TEXT, -- 'transferencia', 'efectivo', 'cheque'
    comprobante_url TEXT,
    notas TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    UNIQUE(consorcista_id, anio) -- Evita duplicar el mismo año para la misma persona
);

CREATE INDEX IF NOT EXISTS idx_consorcista_apellido ON consorcistas(apellido);
CREATE INDEX IF NOT EXISTS idx_cuota_anio ON cuotas_pagos(anio);
