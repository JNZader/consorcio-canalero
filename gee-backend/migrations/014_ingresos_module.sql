-- Tabla de Ingresos operativos (ademas de cuotas)
CREATE TABLE IF NOT EXISTS ingresos (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    fecha DATE DEFAULT CURRENT_DATE,
    descripcion TEXT NOT NULL,
    monto DECIMAL(12, 2) NOT NULL,
    fuente TEXT NOT NULL, -- 'subsidio', 'alquiler', 'aporte_extraordinario', etc.
    pagador TEXT,
    comprobante_url TEXT,
    notas TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_ingresos_fecha ON ingresos(fecha);
CREATE INDEX IF NOT EXISTS idx_ingresos_fuente ON ingresos(fuente);
