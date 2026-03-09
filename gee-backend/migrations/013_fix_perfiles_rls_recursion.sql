-- =============================================
-- Migracion: Corregir recursion RLS en perfiles
-- Fecha: 2026-03-09
-- Descripcion: Reemplaza policies recursivas por policies seguras sin subqueries a perfiles
-- =============================================

ALTER TABLE public.perfiles ENABLE ROW LEVEL SECURITY;

-- Eliminar policies previas que causan recursion
DROP POLICY IF EXISTS "Service role full access to perfiles" ON public.perfiles;
DROP POLICY IF EXISTS "Users can view own profile" ON public.perfiles;
DROP POLICY IF EXISTS "Users can update own profile" ON public.perfiles;
DROP POLICY IF EXISTS "Staff can view all profiles" ON public.perfiles;
DROP POLICY IF EXISTS "Admins can update any profile" ON public.perfiles;

-- Service role mantiene acceso completo
CREATE POLICY "Service role full access to perfiles"
ON public.perfiles
FOR ALL
TO service_role
USING (true)
WITH CHECK (true);

-- Usuarios autenticados pueden ver su propio perfil
CREATE POLICY "Users can view own profile"
ON public.perfiles
FOR SELECT
TO authenticated
USING (auth.uid() = id);

-- Staff (admin/operador) puede ver todos los perfiles, sin consultar la tabla perfiles
CREATE POLICY "Staff can view all profiles"
ON public.perfiles
FOR SELECT
TO authenticated
USING (
  COALESCE(
    auth.jwt() -> 'app_metadata' ->> 'rol',
    auth.jwt() -> 'user_metadata' ->> 'rol',
    ''
  ) IN ('admin', 'operador')
);

-- Usuarios autenticados pueden actualizar su propio perfil
CREATE POLICY "Users can update own profile"
ON public.perfiles
FOR UPDATE
TO authenticated
USING (auth.uid() = id)
WITH CHECK (auth.uid() = id);

-- Admin puede actualizar cualquier perfil, sin consultar la tabla perfiles
CREATE POLICY "Admins can update any profile"
ON public.perfiles
FOR UPDATE
TO authenticated
USING (
  COALESCE(
    auth.jwt() -> 'app_metadata' ->> 'rol',
    auth.jwt() -> 'user_metadata' ->> 'rol',
    ''
  ) = 'admin'
)
WITH CHECK (
  COALESCE(
    auth.jwt() -> 'app_metadata' ->> 'rol',
    auth.jwt() -> 'user_metadata' ->> 'rol',
    ''
  ) = 'admin'
);

-- Garantizar que el usuario admin conocido conserva rol admin
UPDATE public.perfiles
SET rol = 'admin', updated_at = NOW()
WHERE lower(email) = lower('jnzader@gmail.com');

INSERT INTO public.perfiles (id, email, nombre, rol)
SELECT
  u.id,
  u.email,
  COALESCE(u.raw_user_meta_data ->> 'full_name', u.raw_user_meta_data ->> 'name', ''),
  'admin'
FROM auth.users u
WHERE lower(u.email) = lower('jnzader@gmail.com')
ON CONFLICT (id)
DO UPDATE SET
  email = EXCLUDED.email,
  rol = 'admin',
  updated_at = NOW();
