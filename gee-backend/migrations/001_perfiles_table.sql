-- =============================================
-- Migracion: Tabla de Perfiles de Usuario
-- Fecha: 2024
-- Descripcion: Tabla para almacenar perfiles de usuarios con roles
-- =============================================

-- Tabla de perfiles de usuario (vinculada a auth.users de Supabase)
CREATE TABLE IF NOT EXISTS perfiles (
    id UUID PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
    email VARCHAR(255) NOT NULL,
    nombre VARCHAR(100),
    telefono VARCHAR(20),
    rol VARCHAR(20) DEFAULT 'ciudadano', -- ciudadano, operador, admin
    avatar_url TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Indices
CREATE INDEX IF NOT EXISTS idx_perfiles_email ON perfiles(email);
CREATE INDEX IF NOT EXISTS idx_perfiles_rol ON perfiles(rol);

-- RLS Policies
ALTER TABLE perfiles ENABLE ROW LEVEL SECURITY;

-- Service role tiene acceso completo
CREATE POLICY "Service role full access to perfiles"
ON perfiles FOR ALL TO service_role
USING (true) WITH CHECK (true);

-- Usuarios pueden ver su propio perfil
CREATE POLICY "Users can view own profile"
ON perfiles FOR SELECT TO authenticated
USING (auth.uid() = id);

-- Usuarios pueden actualizar su propio perfil (excepto rol)
CREATE POLICY "Users can update own profile"
ON perfiles FOR UPDATE TO authenticated
USING (auth.uid() = id)
WITH CHECK (auth.uid() = id);

-- Admins y operadores pueden ver todos los perfiles
CREATE POLICY "Staff can view all profiles"
ON perfiles FOR SELECT TO authenticated
USING (
    EXISTS (
        SELECT 1 FROM perfiles p
        WHERE p.id = auth.uid()
        AND p.rol IN ('admin', 'operador')
    )
);

-- Solo admins pueden cambiar roles
CREATE POLICY "Admins can update any profile"
ON perfiles FOR UPDATE TO authenticated
USING (
    EXISTS (
        SELECT 1 FROM perfiles p
        WHERE p.id = auth.uid()
        AND p.rol = 'admin'
    )
);

-- Trigger para updated_at
CREATE OR REPLACE FUNCTION update_perfiles_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trigger_perfiles_updated_at
    BEFORE UPDATE ON perfiles
    FOR EACH ROW
    EXECUTE FUNCTION update_perfiles_updated_at();

-- Funcion para crear perfil automaticamente cuando se registra usuario
CREATE OR REPLACE FUNCTION handle_new_user()
RETURNS TRIGGER AS $$
BEGIN
    INSERT INTO public.perfiles (id, email, nombre)
    VALUES (
        NEW.id,
        NEW.email,
        COALESCE(NEW.raw_user_meta_data->>'full_name', NEW.raw_user_meta_data->>'name', '')
    );
    RETURN NEW;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- Trigger para crear perfil en registro (si no existe)
DROP TRIGGER IF EXISTS on_auth_user_created ON auth.users;
CREATE TRIGGER on_auth_user_created
    AFTER INSERT ON auth.users
    FOR EACH ROW
    EXECUTE FUNCTION handle_new_user();

-- Comentarios
COMMENT ON TABLE perfiles IS 'Perfiles de usuario con roles para el sistema';
COMMENT ON COLUMN perfiles.rol IS 'ciudadano: usuario comun, operador: personal del consorcio, admin: administrador';
