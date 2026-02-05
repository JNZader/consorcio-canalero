-- Tabla de Gastos
CREATE TABLE IF NOT EXISTS gastos (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    fecha DATE DEFAULT CURRENT_DATE,
    descripcion TEXT NOT NULL,
    monto DECIMAL(12, 2) NOT NULL,
    categoria TEXT NOT NULL, -- 'combustible', 'maquinaria', 'sueldos', 'administrativo', 'obras', 'otros'
    infraestructura_id UUID REFERENCES infraestructura(id) ON DELETE SET NULL, -- Opcional: vincular a un activo
    comprobante_url TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Tabla de Presupuestos Anuales
CREATE TABLE IF NOT EXISTS presupuestos (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    anio INTEGER UNIQUE NOT NULL,
    ingresos_estimados DECIMAL(12, 2) DEFAULT 0,
    gastos_estimados DECIMAL(12, 2) DEFAULT 0,
    notas TEXT,
    estado TEXT DEFAULT 'borrador', -- 'borrador', 'aprobado_asamblea', 'cerrado'
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Items detallados del presupuesto (por categoría)
CREATE TABLE IF NOT EXISTS presupuesto_items (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    presupuesto_id UUID REFERENCES presupuestos(id) ON DELETE CASCADE,
    categoria TEXT NOT NULL,
    monto_previsto DECIMAL(12, 2) NOT NULL,
    notas TEXT
);

CREATE INDEX IF NOT EXISTS idx_gastos_fecha ON gastos(fecha);
CREATE INDEX IF NOT EXISTS idx_gastos_categoria ON gastos(categoria);
