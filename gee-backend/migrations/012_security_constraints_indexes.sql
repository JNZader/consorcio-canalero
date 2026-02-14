-- =============================================
-- Migracion 012: Seguridad, Constraints e Indices
-- Fecha: 2026-02-14
-- Descripcion: Habilita RLS en todas las tablas que lo necesitan,
--   agrega politicas de acceso, constraints de integridad,
--   indices faltantes y triggers de updated_at.
-- =============================================

-- ============================================
-- 0. FUNCION AUXILIAR REUTILIZABLE: set_updated_at
-- ============================================
-- Funcion generica que se puede aplicar a cualquier tabla con columna updated_at.
-- No reemplaza las funciones especificas que ya existen (update_updated_at_column,
-- update_perfiles_updated_at, update_sugerencias_updated_at) para no romper triggers existentes.

CREATE OR REPLACE FUNCTION set_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;


-- ============================================
-- 1. ENABLE RLS EN TABLAS QUE LO NECESITAN
-- ============================================
-- Tablas de migration 007
ALTER TABLE infraestructura ENABLE ROW LEVEL SECURITY;
ALTER TABLE mantenimiento_logs ENABLE ROW LEVEL SECURITY;

-- Tablas de migration 008
ALTER TABLE tramites ENABLE ROW LEVEL SECURITY;
ALTER TABLE tramite_avances ENABLE ROW LEVEL SECURITY;
ALTER TABLE gestion_seguimiento ENABLE ROW LEVEL SECURITY;

-- Tablas de migration 009
ALTER TABLE reuniones ENABLE ROW LEVEL SECURITY;
ALTER TABLE agenda_items ENABLE ROW LEVEL SECURITY;
ALTER TABLE agenda_referencias ENABLE ROW LEVEL SECURITY;

-- Tablas de migration 010
ALTER TABLE consorcistas ENABLE ROW LEVEL SECURITY;
ALTER TABLE cuotas_pagos ENABLE ROW LEVEL SECURITY;

-- Tablas de migration 011
ALTER TABLE gastos ENABLE ROW LEVEL SECURITY;
ALTER TABLE presupuestos ENABLE ROW LEVEL SECURITY;
ALTER TABLE presupuesto_items ENABLE ROW LEVEL SECURITY;


-- ============================================
-- 2. RLS POLICIES
-- ============================================

-- ------------------------------------------
-- 2a. infraestructura
-- ------------------------------------------
CREATE POLICY "service_role_all_infraestructura" ON infraestructura
    FOR ALL TO service_role USING (true) WITH CHECK (true);

CREATE POLICY "staff_select_infraestructura" ON infraestructura
    FOR SELECT TO authenticated
    USING (
        EXISTS (SELECT 1 FROM perfiles WHERE id = auth.uid() AND rol IN ('admin', 'operador'))
    );

-- Ciudadanos pueden ver infraestructura (informacion publica del consorcio)
CREATE POLICY "public_select_infraestructura" ON infraestructura
    FOR SELECT TO authenticated
    USING (
        EXISTS (SELECT 1 FROM perfiles WHERE id = auth.uid() AND rol = 'ciudadano')
    );

CREATE POLICY "staff_insert_infraestructura" ON infraestructura
    FOR INSERT TO authenticated
    WITH CHECK (
        EXISTS (SELECT 1 FROM perfiles WHERE id = auth.uid() AND rol IN ('admin', 'operador'))
    );

CREATE POLICY "staff_update_infraestructura" ON infraestructura
    FOR UPDATE TO authenticated
    USING (
        EXISTS (SELECT 1 FROM perfiles WHERE id = auth.uid() AND rol IN ('admin', 'operador'))
    );

CREATE POLICY "admin_delete_infraestructura" ON infraestructura
    FOR DELETE TO authenticated
    USING (
        EXISTS (SELECT 1 FROM perfiles WHERE id = auth.uid() AND rol = 'admin')
    );

-- ------------------------------------------
-- 2b. mantenimiento_logs
-- ------------------------------------------
CREATE POLICY "service_role_all_mantenimiento_logs" ON mantenimiento_logs
    FOR ALL TO service_role USING (true) WITH CHECK (true);

CREATE POLICY "staff_select_mantenimiento_logs" ON mantenimiento_logs
    FOR SELECT TO authenticated
    USING (
        EXISTS (SELECT 1 FROM perfiles WHERE id = auth.uid() AND rol IN ('admin', 'operador'))
    );

CREATE POLICY "staff_insert_mantenimiento_logs" ON mantenimiento_logs
    FOR INSERT TO authenticated
    WITH CHECK (
        EXISTS (SELECT 1 FROM perfiles WHERE id = auth.uid() AND rol IN ('admin', 'operador'))
    );

CREATE POLICY "staff_update_mantenimiento_logs" ON mantenimiento_logs
    FOR UPDATE TO authenticated
    USING (
        EXISTS (SELECT 1 FROM perfiles WHERE id = auth.uid() AND rol IN ('admin', 'operador'))
    );

CREATE POLICY "admin_delete_mantenimiento_logs" ON mantenimiento_logs
    FOR DELETE TO authenticated
    USING (
        EXISTS (SELECT 1 FROM perfiles WHERE id = auth.uid() AND rol = 'admin')
    );

-- ------------------------------------------
-- 2c. tramites
-- ------------------------------------------
CREATE POLICY "service_role_all_tramites" ON tramites
    FOR ALL TO service_role USING (true) WITH CHECK (true);

CREATE POLICY "staff_select_tramites" ON tramites
    FOR SELECT TO authenticated
    USING (
        EXISTS (SELECT 1 FROM perfiles WHERE id = auth.uid() AND rol IN ('admin', 'operador'))
    );

CREATE POLICY "staff_insert_tramites" ON tramites
    FOR INSERT TO authenticated
    WITH CHECK (
        EXISTS (SELECT 1 FROM perfiles WHERE id = auth.uid() AND rol IN ('admin', 'operador'))
    );

CREATE POLICY "staff_update_tramites" ON tramites
    FOR UPDATE TO authenticated
    USING (
        EXISTS (SELECT 1 FROM perfiles WHERE id = auth.uid() AND rol IN ('admin', 'operador'))
    );

CREATE POLICY "admin_delete_tramites" ON tramites
    FOR DELETE TO authenticated
    USING (
        EXISTS (SELECT 1 FROM perfiles WHERE id = auth.uid() AND rol = 'admin')
    );

-- ------------------------------------------
-- 2d. tramite_avances
-- ------------------------------------------
CREATE POLICY "service_role_all_tramite_avances" ON tramite_avances
    FOR ALL TO service_role USING (true) WITH CHECK (true);

CREATE POLICY "staff_select_tramite_avances" ON tramite_avances
    FOR SELECT TO authenticated
    USING (
        EXISTS (SELECT 1 FROM perfiles WHERE id = auth.uid() AND rol IN ('admin', 'operador'))
    );

CREATE POLICY "staff_insert_tramite_avances" ON tramite_avances
    FOR INSERT TO authenticated
    WITH CHECK (
        EXISTS (SELECT 1 FROM perfiles WHERE id = auth.uid() AND rol IN ('admin', 'operador'))
    );

CREATE POLICY "staff_update_tramite_avances" ON tramite_avances
    FOR UPDATE TO authenticated
    USING (
        EXISTS (SELECT 1 FROM perfiles WHERE id = auth.uid() AND rol IN ('admin', 'operador'))
    );

CREATE POLICY "admin_delete_tramite_avances" ON tramite_avances
    FOR DELETE TO authenticated
    USING (
        EXISTS (SELECT 1 FROM perfiles WHERE id = auth.uid() AND rol = 'admin')
    );

-- ------------------------------------------
-- 2e. gestion_seguimiento
-- ------------------------------------------
CREATE POLICY "service_role_all_gestion_seguimiento" ON gestion_seguimiento
    FOR ALL TO service_role USING (true) WITH CHECK (true);

CREATE POLICY "staff_select_gestion_seguimiento" ON gestion_seguimiento
    FOR SELECT TO authenticated
    USING (
        EXISTS (SELECT 1 FROM perfiles WHERE id = auth.uid() AND rol IN ('admin', 'operador'))
    );

CREATE POLICY "staff_insert_gestion_seguimiento" ON gestion_seguimiento
    FOR INSERT TO authenticated
    WITH CHECK (
        EXISTS (SELECT 1 FROM perfiles WHERE id = auth.uid() AND rol IN ('admin', 'operador'))
    );

CREATE POLICY "staff_update_gestion_seguimiento" ON gestion_seguimiento
    FOR UPDATE TO authenticated
    USING (
        EXISTS (SELECT 1 FROM perfiles WHERE id = auth.uid() AND rol IN ('admin', 'operador'))
    );

CREATE POLICY "admin_delete_gestion_seguimiento" ON gestion_seguimiento
    FOR DELETE TO authenticated
    USING (
        EXISTS (SELECT 1 FROM perfiles WHERE id = auth.uid() AND rol = 'admin')
    );

-- ------------------------------------------
-- 2f. reuniones
-- ------------------------------------------
CREATE POLICY "service_role_all_reuniones" ON reuniones
    FOR ALL TO service_role USING (true) WITH CHECK (true);

CREATE POLICY "staff_select_reuniones" ON reuniones
    FOR SELECT TO authenticated
    USING (
        EXISTS (SELECT 1 FROM perfiles WHERE id = auth.uid() AND rol IN ('admin', 'operador'))
    );

CREATE POLICY "staff_insert_reuniones" ON reuniones
    FOR INSERT TO authenticated
    WITH CHECK (
        EXISTS (SELECT 1 FROM perfiles WHERE id = auth.uid() AND rol IN ('admin', 'operador'))
    );

CREATE POLICY "staff_update_reuniones" ON reuniones
    FOR UPDATE TO authenticated
    USING (
        EXISTS (SELECT 1 FROM perfiles WHERE id = auth.uid() AND rol IN ('admin', 'operador'))
    );

CREATE POLICY "admin_delete_reuniones" ON reuniones
    FOR DELETE TO authenticated
    USING (
        EXISTS (SELECT 1 FROM perfiles WHERE id = auth.uid() AND rol = 'admin')
    );

-- ------------------------------------------
-- 2g. agenda_items
-- ------------------------------------------
CREATE POLICY "service_role_all_agenda_items" ON agenda_items
    FOR ALL TO service_role USING (true) WITH CHECK (true);

CREATE POLICY "staff_select_agenda_items" ON agenda_items
    FOR SELECT TO authenticated
    USING (
        EXISTS (SELECT 1 FROM perfiles WHERE id = auth.uid() AND rol IN ('admin', 'operador'))
    );

CREATE POLICY "staff_insert_agenda_items" ON agenda_items
    FOR INSERT TO authenticated
    WITH CHECK (
        EXISTS (SELECT 1 FROM perfiles WHERE id = auth.uid() AND rol IN ('admin', 'operador'))
    );

CREATE POLICY "staff_update_agenda_items" ON agenda_items
    FOR UPDATE TO authenticated
    USING (
        EXISTS (SELECT 1 FROM perfiles WHERE id = auth.uid() AND rol IN ('admin', 'operador'))
    );

CREATE POLICY "admin_delete_agenda_items" ON agenda_items
    FOR DELETE TO authenticated
    USING (
        EXISTS (SELECT 1 FROM perfiles WHERE id = auth.uid() AND rol = 'admin')
    );

-- ------------------------------------------
-- 2h. agenda_referencias
-- ------------------------------------------
CREATE POLICY "service_role_all_agenda_referencias" ON agenda_referencias
    FOR ALL TO service_role USING (true) WITH CHECK (true);

CREATE POLICY "staff_select_agenda_referencias" ON agenda_referencias
    FOR SELECT TO authenticated
    USING (
        EXISTS (SELECT 1 FROM perfiles WHERE id = auth.uid() AND rol IN ('admin', 'operador'))
    );

CREATE POLICY "staff_insert_agenda_referencias" ON agenda_referencias
    FOR INSERT TO authenticated
    WITH CHECK (
        EXISTS (SELECT 1 FROM perfiles WHERE id = auth.uid() AND rol IN ('admin', 'operador'))
    );

CREATE POLICY "staff_update_agenda_referencias" ON agenda_referencias
    FOR UPDATE TO authenticated
    USING (
        EXISTS (SELECT 1 FROM perfiles WHERE id = auth.uid() AND rol IN ('admin', 'operador'))
    );

CREATE POLICY "admin_delete_agenda_referencias" ON agenda_referencias
    FOR DELETE TO authenticated
    USING (
        EXISTS (SELECT 1 FROM perfiles WHERE id = auth.uid() AND rol = 'admin')
    );

-- ------------------------------------------
-- 2i. consorcistas (PII - restricted to staff only)
-- ------------------------------------------
CREATE POLICY "service_role_all_consorcistas" ON consorcistas
    FOR ALL TO service_role USING (true) WITH CHECK (true);

CREATE POLICY "staff_select_consorcistas" ON consorcistas
    FOR SELECT TO authenticated
    USING (
        EXISTS (SELECT 1 FROM perfiles WHERE id = auth.uid() AND rol IN ('admin', 'operador'))
    );

CREATE POLICY "staff_insert_consorcistas" ON consorcistas
    FOR INSERT TO authenticated
    WITH CHECK (
        EXISTS (SELECT 1 FROM perfiles WHERE id = auth.uid() AND rol IN ('admin', 'operador'))
    );

CREATE POLICY "staff_update_consorcistas" ON consorcistas
    FOR UPDATE TO authenticated
    USING (
        EXISTS (SELECT 1 FROM perfiles WHERE id = auth.uid() AND rol IN ('admin', 'operador'))
    );

CREATE POLICY "admin_delete_consorcistas" ON consorcistas
    FOR DELETE TO authenticated
    USING (
        EXISTS (SELECT 1 FROM perfiles WHERE id = auth.uid() AND rol = 'admin')
    );

-- ------------------------------------------
-- 2j. cuotas_pagos (PII-adjacent - restricted to staff only)
-- ------------------------------------------
CREATE POLICY "service_role_all_cuotas_pagos" ON cuotas_pagos
    FOR ALL TO service_role USING (true) WITH CHECK (true);

CREATE POLICY "staff_select_cuotas_pagos" ON cuotas_pagos
    FOR SELECT TO authenticated
    USING (
        EXISTS (SELECT 1 FROM perfiles WHERE id = auth.uid() AND rol IN ('admin', 'operador'))
    );

CREATE POLICY "staff_insert_cuotas_pagos" ON cuotas_pagos
    FOR INSERT TO authenticated
    WITH CHECK (
        EXISTS (SELECT 1 FROM perfiles WHERE id = auth.uid() AND rol IN ('admin', 'operador'))
    );

CREATE POLICY "staff_update_cuotas_pagos" ON cuotas_pagos
    FOR UPDATE TO authenticated
    USING (
        EXISTS (SELECT 1 FROM perfiles WHERE id = auth.uid() AND rol IN ('admin', 'operador'))
    );

CREATE POLICY "admin_delete_cuotas_pagos" ON cuotas_pagos
    FOR DELETE TO authenticated
    USING (
        EXISTS (SELECT 1 FROM perfiles WHERE id = auth.uid() AND rol = 'admin')
    );

-- ------------------------------------------
-- 2k. gastos
-- ------------------------------------------
CREATE POLICY "service_role_all_gastos" ON gastos
    FOR ALL TO service_role USING (true) WITH CHECK (true);

CREATE POLICY "staff_select_gastos" ON gastos
    FOR SELECT TO authenticated
    USING (
        EXISTS (SELECT 1 FROM perfiles WHERE id = auth.uid() AND rol IN ('admin', 'operador'))
    );

CREATE POLICY "staff_insert_gastos" ON gastos
    FOR INSERT TO authenticated
    WITH CHECK (
        EXISTS (SELECT 1 FROM perfiles WHERE id = auth.uid() AND rol IN ('admin', 'operador'))
    );

CREATE POLICY "staff_update_gastos" ON gastos
    FOR UPDATE TO authenticated
    USING (
        EXISTS (SELECT 1 FROM perfiles WHERE id = auth.uid() AND rol IN ('admin', 'operador'))
    );

CREATE POLICY "admin_delete_gastos" ON gastos
    FOR DELETE TO authenticated
    USING (
        EXISTS (SELECT 1 FROM perfiles WHERE id = auth.uid() AND rol = 'admin')
    );

-- ------------------------------------------
-- 2l. presupuestos
-- ------------------------------------------
CREATE POLICY "service_role_all_presupuestos" ON presupuestos
    FOR ALL TO service_role USING (true) WITH CHECK (true);

CREATE POLICY "staff_select_presupuestos" ON presupuestos
    FOR SELECT TO authenticated
    USING (
        EXISTS (SELECT 1 FROM perfiles WHERE id = auth.uid() AND rol IN ('admin', 'operador'))
    );

CREATE POLICY "staff_insert_presupuestos" ON presupuestos
    FOR INSERT TO authenticated
    WITH CHECK (
        EXISTS (SELECT 1 FROM perfiles WHERE id = auth.uid() AND rol IN ('admin', 'operador'))
    );

CREATE POLICY "staff_update_presupuestos" ON presupuestos
    FOR UPDATE TO authenticated
    USING (
        EXISTS (SELECT 1 FROM perfiles WHERE id = auth.uid() AND rol IN ('admin', 'operador'))
    );

CREATE POLICY "admin_delete_presupuestos" ON presupuestos
    FOR DELETE TO authenticated
    USING (
        EXISTS (SELECT 1 FROM perfiles WHERE id = auth.uid() AND rol = 'admin')
    );

-- ------------------------------------------
-- 2m. presupuesto_items
-- ------------------------------------------
CREATE POLICY "service_role_all_presupuesto_items" ON presupuesto_items
    FOR ALL TO service_role USING (true) WITH CHECK (true);

CREATE POLICY "staff_select_presupuesto_items" ON presupuesto_items
    FOR SELECT TO authenticated
    USING (
        EXISTS (SELECT 1 FROM perfiles WHERE id = auth.uid() AND rol IN ('admin', 'operador'))
    );

CREATE POLICY "staff_insert_presupuesto_items" ON presupuesto_items
    FOR INSERT TO authenticated
    WITH CHECK (
        EXISTS (SELECT 1 FROM perfiles WHERE id = auth.uid() AND rol IN ('admin', 'operador'))
    );

CREATE POLICY "staff_update_presupuesto_items" ON presupuesto_items
    FOR UPDATE TO authenticated
    USING (
        EXISTS (SELECT 1 FROM perfiles WHERE id = auth.uid() AND rol IN ('admin', 'operador'))
    );

CREATE POLICY "admin_delete_presupuesto_items" ON presupuesto_items
    FOR DELETE TO authenticated
    USING (
        EXISTS (SELECT 1 FROM perfiles WHERE id = auth.uid() AND rol = 'admin')
    );


-- ============================================
-- 3. FOREIGN KEY CONSTRAINTS
-- ============================================

-- tramite_avances.usuario_id -> auth.users(id)
-- Column exists but has no FK constraint in migration 008
ALTER TABLE tramite_avances
    ADD CONSTRAINT fk_tramite_avances_usuario
    FOREIGN KEY (usuario_id) REFERENCES auth.users(id) ON DELETE SET NULL;

-- gestion_seguimiento.usuario_gestion -> auth.users(id)
-- Column exists but has no FK constraint in migration 008
ALTER TABLE gestion_seguimiento
    ADD CONSTRAINT fk_gestion_seguimiento_usuario
    FOREIGN KEY (usuario_gestion) REFERENCES auth.users(id) ON DELETE SET NULL;


-- ============================================
-- 4. CHECK CONSTRAINTS
-- ============================================

-- Coordinate validation for denuncias
ALTER TABLE denuncias ADD CONSTRAINT chk_denuncias_latitud
    CHECK (latitud BETWEEN -90 AND 90);
ALTER TABLE denuncias ADD CONSTRAINT chk_denuncias_longitud
    CHECK (longitud BETWEEN -180 AND 180);

-- Coordinate validation for infraestructura
ALTER TABLE infraestructura ADD CONSTRAINT chk_infra_latitud
    CHECK (latitud BETWEEN -90 AND 90);
ALTER TABLE infraestructura ADD CONSTRAINT chk_infra_longitud
    CHECK (longitud BETWEEN -180 AND 180);

-- Monetary constraints: cuotas cannot be negative
ALTER TABLE cuotas_pagos ADD CONSTRAINT chk_cuotas_monto
    CHECK (monto >= 0);

-- Monetary constraints: gastos must be positive
ALTER TABLE gastos ADD CONSTRAINT chk_gastos_monto
    CHECK (monto > 0);

-- Percentage constraint on caminos_afectados
ALTER TABLE caminos_afectados ADD CONSTRAINT chk_porcentaje
    CHECK (porcentaje_afectado BETWEEN 0 AND 100);

-- Date range constraint on analisis_gee
ALTER TABLE analisis_gee ADD CONSTRAINT chk_fechas
    CHECK (fecha_inicio <= fecha_fin);


-- ============================================
-- 5. MISSING INDEXES ON FK AND QUERY COLUMNS
-- ============================================

-- denuncias.user_id (FK to perfiles, used in policy checks and filtering)
CREATE INDEX IF NOT EXISTS idx_denuncias_user_id ON denuncias(user_id);

-- comentarios FK columns
CREATE INDEX IF NOT EXISTS idx_comentarios_denuncia_id ON comentarios(denuncia_id);
CREATE INDEX IF NOT EXISTS idx_comentarios_user_id ON comentarios(user_id);

-- tramite_avances FK columns
CREATE INDEX IF NOT EXISTS idx_tramite_avances_tramite_id ON tramite_avances(tramite_id);

-- cuotas_pagos FK and common query columns
CREATE INDEX IF NOT EXISTS idx_cuotas_consorcista_id ON cuotas_pagos(consorcista_id);
CREATE INDEX IF NOT EXISTS idx_cuotas_estado_anio ON cuotas_pagos(estado, anio);

-- gastos FK column
CREATE INDEX IF NOT EXISTS idx_gastos_infraestructura_id ON gastos(infraestructura_id);

-- presupuesto_items FK column
CREATE INDEX IF NOT EXISTS idx_presupuesto_items_presupuesto_id ON presupuesto_items(presupuesto_id);


-- ============================================
-- 6. UPDATED_AT TRIGGERS
-- ============================================
-- Apply the generic set_updated_at trigger to tables that have an updated_at
-- column but no trigger yet. Tables that already have triggers:
--   perfiles -> trigger_perfiles_updated_at (migration 001)
--   sugerencias -> trigger_sugerencias_updated_at (migration 004)
--   capas -> capas_updated_at (schema.sql)
--   denuncias -> NONE (schema.sql defines updated_at column but no trigger)
-- Tables with updated_at column from later migrations:
--   infraestructura -> has updated_at, no trigger
--   reuniones -> has updated_at, no trigger

-- denuncias (has updated_at in schema.sql but no trigger)
DROP TRIGGER IF EXISTS trigger_denuncias_updated_at ON denuncias;
CREATE TRIGGER trigger_denuncias_updated_at
    BEFORE UPDATE ON denuncias
    FOR EACH ROW
    EXECUTE FUNCTION set_updated_at();

-- infraestructura (has updated_at in migration 007 but no trigger)
DROP TRIGGER IF EXISTS trigger_infraestructura_updated_at ON infraestructura;
CREATE TRIGGER trigger_infraestructura_updated_at
    BEFORE UPDATE ON infraestructura
    FOR EACH ROW
    EXECUTE FUNCTION set_updated_at();

-- reuniones (has updated_at in migration 009 but no trigger)
DROP TRIGGER IF EXISTS trigger_reuniones_updated_at ON reuniones;
CREATE TRIGGER trigger_reuniones_updated_at
    BEFORE UPDATE ON reuniones
    FOR EACH ROW
    EXECUTE FUNCTION set_updated_at();


-- ============================================
-- 7. FIX DENUNCIAS INSERT POLICY
-- ============================================
-- Current policy allows any authenticated user to insert without enforcing
-- that user_id matches auth.uid(). This means a user could create a denuncia
-- impersonating another user.

DROP POLICY IF EXISTS "Usuarios autenticados pueden crear denuncias" ON denuncias;

CREATE POLICY "denuncias_insert_own" ON denuncias
    FOR INSERT TO authenticated
    WITH CHECK (user_id = auth.uid());


-- ============================================
-- 8. UNIQUE CONSTRAINT ON perfiles.email
-- ============================================
-- perfiles.email should be unique since it maps 1:1 with auth.users.email.
-- An index already exists (idx_perfiles_email) but it is not unique.

ALTER TABLE perfiles ADD CONSTRAINT uq_perfiles_email UNIQUE (email);


-- ============================================
-- 9. FIX batch_update_layer_order SECURITY
-- ============================================
-- The original function is SECURITY DEFINER (runs as owner), which means
-- any authenticated user can call it and bypass RLS to update capas.orden.
-- Add an explicit role check inside the function body.

CREATE OR REPLACE FUNCTION batch_update_layer_order(layer_updates json)
RETURNS void
LANGUAGE plpgsql
SECURITY DEFINER
AS $$
DECLARE
    layer_item json;
    caller_role text;
BEGIN
    -- Verify the caller is admin or operador
    SELECT rol INTO caller_role
    FROM public.perfiles
    WHERE id = auth.uid();

    IF caller_role IS NULL OR caller_role NOT IN ('admin', 'operador') THEN
        RAISE EXCEPTION 'Permiso denegado: solo admin y operador pueden reordenar capas';
    END IF;

    FOR layer_item IN SELECT * FROM json_array_elements(layer_updates)
    LOOP
        UPDATE public.capas
        SET orden = (layer_item->>'orden')::integer,
            updated_at = timezone('utc'::text, now())
        WHERE id = (layer_item->>'id')::uuid;
    END LOOP;
END;
$$;


-- ============================================
-- 10. COMMENTS
-- ============================================
COMMENT ON FUNCTION set_updated_at() IS 'Generic trigger function that sets updated_at = NOW() on row update';
COMMENT ON FUNCTION batch_update_layer_order(json) IS 'Batch updates layer ordering, restricted to admin/operador roles';
