# Migraciones SQL Pendientes - Consorcio Canalero

Este documento contiene los scripts SQL necesarios para actualizar la base de datos de Supabase con los nuevos módulos de gestión (Infraestructura, Trámites, Reuniones, Padrón y Finanzas).

**Instrucciones:**
1. Accede al [Dashboard de Supabase](https://supabase.com/dashboard).
2. Entra en tu proyecto y ve a la sección **SQL Editor**.
3. Copia y pega los bloques de código en el orden indicado (007 al 011).
4. Ejecuta cada bloque (botón "Run").

---

### 1. Infraestructura y Mantenimiento (007)
Gestiona activos físicos como alcantarillas y puentes, junto con su historial de reparaciones.

```sql
-- Tabla de activos de infraestructura
CREATE TABLE IF NOT EXISTS infraestructura (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    nombre TEXT NOT NULL,
    tipo TEXT NOT NULL, -- 'alcantarilla', 'puente', 'canal', etc.
    cuenca TEXT,
    latitud DOUBLE PRECISION NOT NULL,
    longitud DOUBLE PRECISION NOT NULL,
    estado_actual TEXT DEFAULT 'bueno',
    ultima_inspeccion TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Tabla de bitácora/mantenimiento
CREATE TABLE IF NOT EXISTS mantenimiento_logs (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    infraestructura_id UUID REFERENCES infraestructura(id),
    fecha TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    tipo_tarea TEXT NOT NULL,
    descripcion TEXT,
    operario_nombre TEXT,
    costo_estimado DECIMAL(12,2)
);
```

### 2. Trámites y Seguimiento (008)
Permite llevar el control de expedientes con la provincia y el historial de gestión de reportes ciudadanos.

```sql
-- Tabla para expedientes provinciales (APRHI, etc)
CREATE TABLE IF NOT EXISTS tramites (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    titulo TEXT NOT NULL,
    numero_expediente TEXT,
    organismo TEXT, -- 'APRHI', 'Ambiente', etc.
    estado TEXT DEFAULT 'iniciado',
    prioridad TEXT DEFAULT 'media',
    ultima_actualizacion TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Avances detallados de cada trámite
CREATE TABLE IF NOT EXISTS tramite_avances (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tramite_id UUID REFERENCES tramites(id) ON DELETE CASCADE,
    fecha TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    titulo_avance TEXT NOT NULL,
    comentario TEXT,
    documento_url TEXT 
);

-- Log de gestión para Reportes y Sugerencias
CREATE TABLE IF NOT EXISTS gestion_seguimiento (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    entidad_tipo TEXT NOT NULL, -- 'reporte' o 'sugerencia'
    entidad_id UUID NOT NULL,
    fecha TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    estado_nuevo TEXT,
    comentario_interno TEXT,
    comentario_publico TEXT 
);
```

### 3. Reuniones y Agenda (009)
Organización de asambleas y vinculación de temas de agenda con infraestructura o trámites.

```sql
CREATE TABLE IF NOT EXISTS reuniones (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    titulo TEXT NOT NULL,
    fecha_reunion TIMESTAMP WITH TIME ZONE NOT NULL,
    lugar TEXT,
    estado TEXT DEFAULT 'programada', 
    acta_resumen TEXT
);

CREATE TABLE IF NOT EXISTS agenda_items (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    reunion_id UUID REFERENCES reuniones(id) ON DELETE CASCADE,
    orden INTEGER NOT NULL,
    titulo TEXT NOT NULL,
    descripcion TEXT
);

-- Referencias cruzadas
CREATE TABLE IF NOT EXISTS agenda_referencias (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    agenda_item_id UUID REFERENCES agenda_items(id) ON DELETE CASCADE,
    entidad_tipo TEXT NOT NULL, -- 'reporte', 'tramite', 'infraestructura'
    entidad_id UUID NOT NULL,
    metadata JSONB 
);
```

### 4. Padrón y Cuotas (010)
Registro de productores y control de pagos anuales.

```sql
-- Padrón de productores
CREATE TABLE IF NOT EXISTS padron (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    nombre_completo TEXT NOT NULL,
    cuit TEXT UNIQUE,
    email TEXT,
    telefono TEXT,
    hectareas_totales DECIMAL(10,2),
    estado TEXT DEFAULT 'activo'
);

-- Registro de pagos
CREATE TABLE IF NOT EXISTS cuotas_pagos (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    productor_id UUID REFERENCES padron(id),
    anio INTEGER NOT NULL,
    monto DECIMAL(12,2) NOT NULL,
    fecha_pago DATE,
    estado TEXT DEFAULT 'pendiente', 
    comprobante_nro TEXT
);
```

### 5. Finanzas y Presupuesto (011)
Control de egresos generales y planificación presupuestaria por rubro.

```sql
-- Gastos generales
CREATE TABLE IF NOT EXISTS gastos (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    fecha DATE NOT NULL DEFAULT CURRENT_DATE,
    monto DECIMAL(12,2) NOT NULL,
    categoria TEXT NOT NULL, -- 'combustible', 'sueldos', etc.
    descripcion TEXT,
    proveedor TEXT,
    infraestructura_id UUID REFERENCES infraestructura(id) 
);

-- Presupuesto anual
CREATE TABLE IF NOT EXISTS presupuestos (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    anio INTEGER UNIQUE NOT NULL,
    monto_total_proyectado DECIMAL(15,2),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS presupuesto_items (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    presupuesto_id UUID REFERENCES presupuestos(id) ON DELETE CASCADE,
    rubro TEXT NOT NULL,
    monto_asignado DECIMAL(12,2) NOT NULL
);
```

---
**Nota Final:** Una vez ejecutados los scripts, el backend detectará las tablas automáticamente. Los tipos de TypeScript ya han sido regenerados en el frontend (`src/types/schema.d.ts`) para soportar estas nuevas estructuras.
