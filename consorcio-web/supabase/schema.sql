-- ============================================
-- CONSORCIO CANALERO 10 DE MAYO
-- Schema para Supabase
-- ============================================

-- Habilitar extension para UUID
create extension if not exists "uuid-ossp";

-- ============================================
-- TABLA: perfiles de usuario
-- ============================================
create table public.perfiles (
  id uuid references auth.users on delete cascade primary key,
  email text not null,
  nombre text,
  telefono text,
  rol text default 'ciudadano' check (rol in ('ciudadano', 'operador', 'admin')),
  created_at timestamp with time zone default timezone('utc'::text, now()) not null,
  updated_at timestamp with time zone default timezone('utc'::text, now()) not null
);

-- RLS para perfiles
alter table public.perfiles enable row level security;

create policy "Los usuarios pueden ver su propio perfil"
  on public.perfiles for select
  using (auth.uid() = id);

create policy "Los usuarios pueden crear su propio perfil"
  on public.perfiles for insert
  with check (auth.uid() = id);

create policy "Los usuarios pueden actualizar su propio perfil"
  on public.perfiles for update
  using (auth.uid() = id);

-- Trigger para crear perfil automaticamente al registrarse
create or replace function public.handle_new_user()
returns trigger as $$
begin
  insert into public.perfiles (id, email)
  values (new.id, new.email);
  return new;
end;
$$ language plpgsql security definer;

create trigger on_auth_user_created
  after insert on auth.users
  for each row execute procedure public.handle_new_user();

-- ============================================
-- TABLA: denuncias
-- ============================================
create table public.denuncias (
  id uuid default uuid_generate_v4() primary key,
  user_id uuid references public.perfiles(id) on delete set null,
  tipo text not null check (tipo in ('alcantarilla_tapada', 'desborde', 'camino_danado', 'otro')),
  descripcion text not null,
  latitud double precision not null,
  longitud double precision not null,
  foto_url text,
  estado text default 'pendiente' check (estado in ('pendiente', 'en_revision', 'resuelto', 'rechazado')),
  cuenca text,
  notas_internas text,
  asignado_a uuid references public.perfiles(id),
  created_at timestamp with time zone default timezone('utc'::text, now()) not null,
  updated_at timestamp with time zone default timezone('utc'::text, now()) not null,
  resuelto_at timestamp with time zone
);

-- RLS para denuncias
alter table public.denuncias enable row level security;

-- Todos pueden ver denuncias (publico)
create policy "Las denuncias son visibles publicamente"
  on public.denuncias for select
  using (true);

-- Solo usuarios autenticados pueden crear denuncias
create policy "Usuarios autenticados pueden crear denuncias"
  on public.denuncias for insert
  with check (auth.role() = 'authenticated');

-- Solo el autor o admins pueden actualizar
create policy "Autores y admins pueden actualizar denuncias"
  on public.denuncias for update
  using (
    auth.uid() = user_id
    or exists (
      select 1 from public.perfiles
      where id = auth.uid() and rol in ('operador', 'admin')
    )
  );

-- Solo admins pueden eliminar denuncias
create policy "Solo admins pueden eliminar denuncias"
  on public.denuncias for delete
  using (
    exists (
      select 1 from public.perfiles
      where id = auth.uid() and rol = 'admin'
    )
  );

-- ============================================
-- TABLA: comentarios en denuncias
-- ============================================
create table public.comentarios (
  id uuid default uuid_generate_v4() primary key,
  denuncia_id uuid references public.denuncias(id) on delete cascade not null,
  user_id uuid references public.perfiles(id) on delete set null,
  texto text not null,
  es_interno boolean default false,
  created_at timestamp with time zone default timezone('utc'::text, now()) not null
);

-- RLS para comentarios
alter table public.comentarios enable row level security;

-- CORREGIDO: Separar politicas para comentarios publicos e internos
-- Comentarios publicos visibles para todos
create policy "Comentarios publicos para todos"
  on public.comentarios for select
  using (es_interno = false);

-- Comentarios internos solo visibles para staff (operadores y admins)
create policy "Comentarios internos para staff"
  on public.comentarios for select
  using (
    es_interno = true
    and exists (
      select 1 from public.perfiles
      where id = auth.uid() and rol in ('operador', 'admin')
    )
  );

create policy "Usuarios autenticados pueden comentar"
  on public.comentarios for insert
  with check (auth.role() = 'authenticated');

-- Autores pueden eliminar sus propios comentarios
create policy "Autores pueden eliminar sus comentarios"
  on public.comentarios for delete
  using (user_id = auth.uid());

-- ============================================
-- TABLA: estadisticas (cache de datos GEE)
-- ============================================
create table public.estadisticas (
  id uuid default uuid_generate_v4() primary key,
  fecha date not null,
  cuenca text,
  hectareas_inundadas double precision,
  tramos_afectados integer,
  datos_extra jsonb,
  created_at timestamp with time zone default timezone('utc'::text, now()) not null
);

-- RLS para estadisticas (lectura publica)
alter table public.estadisticas enable row level security;

create policy "Estadisticas son publicas"
  on public.estadisticas for select
  using (true);

-- ============================================
-- INDICES
-- ============================================
create index denuncias_estado_idx on public.denuncias(estado);
create index denuncias_tipo_idx on public.denuncias(tipo);
create index denuncias_cuenca_idx on public.denuncias(cuenca);
create index denuncias_created_at_idx on public.denuncias(created_at desc);
create index estadisticas_fecha_idx on public.estadisticas(fecha desc);

-- ============================================
-- STORAGE BUCKET para fotos
-- ============================================
insert into storage.buckets (id, name, public)
values ('denuncias-fotos', 'denuncias-fotos', true);

-- Politica para subir fotos (usuarios autenticados)
create policy "Usuarios pueden subir fotos"
  on storage.objects for insert
  with check (
    bucket_id = 'denuncias-fotos'
    and auth.role() = 'authenticated'
  );

-- Politica para ver fotos (publico)
create policy "Fotos son publicas"
  on storage.objects for select
  using (bucket_id = 'denuncias-fotos');

-- ============================================
-- NUEVAS TABLAS PARA PANEL DE ADMINISTRACION
-- ============================================

-- ============================================
-- TABLA: analisis_gee
-- Almacena resultados de analisis de GEE
-- ============================================
create table public.analisis_gee (
  id uuid default uuid_generate_v4() primary key,
  created_at timestamp with time zone default timezone('utc'::text, now()) not null,
  created_by uuid references public.perfiles(id),

  -- Parametros del analisis
  fecha_inicio date not null,
  fecha_fin date not null,
  umbral_db decimal(4,1) default -15.0,
  cuencas_analizadas text[] default array['candil', 'ml', 'noroeste', 'norte'],

  -- Resultados generales
  hectareas_inundadas decimal(10,2),
  porcentaje_area decimal(5,2),
  caminos_afectados integer,
  imagenes_procesadas integer,

  -- Resultados por cuenca (JSONB)
  stats_cuencas jsonb,

  -- Referencias a archivos
  geojson_url text,
  thumbnail_url text,

  -- Estado
  status varchar(20) default 'pending'
    check (status in ('pending', 'processing', 'completed', 'failed')),
  error_message text,

  -- Metadatos GEE
  gee_job_id text,
  processing_time_seconds integer
);

-- Indices para analisis_gee
create index idx_analisis_fecha on public.analisis_gee(fecha_inicio, fecha_fin);
create index idx_analisis_status on public.analisis_gee(status);
create index idx_analisis_created on public.analisis_gee(created_at desc);

-- RLS para analisis_gee
alter table public.analisis_gee enable row level security;

create policy "Analisis visible para todos"
  on public.analisis_gee for select
  using (true);

create policy "Solo admins pueden crear analisis"
  on public.analisis_gee for insert
  with check (
    exists (
      select 1 from public.perfiles
      where id = auth.uid() and rol in ('admin', 'operador')
    )
  );

create policy "Solo admins pueden actualizar analisis"
  on public.analisis_gee for update
  using (
    exists (
      select 1 from public.perfiles
      where id = auth.uid() and rol in ('admin', 'operador')
    )
  );

-- Solo admins pueden eliminar analisis
create policy "Solo admins pueden eliminar analisis"
  on public.analisis_gee for delete
  using (
    exists (
      select 1 from public.perfiles
      where id = auth.uid() and rol = 'admin'
    )
  );

-- ============================================
-- TABLA: capas
-- Gestion de capas GeoJSON
-- ============================================
create table public.capas (
  id uuid default uuid_generate_v4() primary key,
  created_at timestamp with time zone default timezone('utc'::text, now()) not null,
  updated_at timestamp with time zone default timezone('utc'::text, now()) not null,
  created_by uuid references public.perfiles(id),

  -- Informacion basica
  nombre varchar(100) not null,
  descripcion text,
  tipo varchar(50) not null
    check (tipo in ('zona', 'cuenca', 'caminos', 'inundacion', 'custom')),

  -- Archivo
  geojson_url text not null,
  file_size_kb integer,

  -- Visualizacion
  visible boolean default true,
  orden integer default 0,

  -- Estilo (JSONB)
  estilo jsonb default '{
    "color": "#3388ff",
    "weight": 2,
    "fillColor": "#3388ff",
    "fillOpacity": 0.1
  }',

  -- Metadata
  fuente varchar(100),
  fecha_datos date,

  -- Vinculo a analisis (si fue generada por GEE)
  analisis_id uuid references public.analisis_gee(id) on delete set null
);

-- Indices para capas
create index idx_capas_tipo on public.capas(tipo);
create index idx_capas_orden on public.capas(orden);

-- RLS para capas
alter table public.capas enable row level security;

create policy "Capas visibles para todos"
  on public.capas for select
  using (true);

create policy "Solo admins pueden insertar capas"
  on public.capas for insert
  with check (
    exists (
      select 1 from public.perfiles
      where id = auth.uid() and rol = 'admin'
    )
  );

create policy "Solo admins pueden actualizar capas"
  on public.capas for update
  using (
    exists (
      select 1 from public.perfiles
      where id = auth.uid() and rol in ('admin', 'operador')
    )
  );

create policy "Solo admins pueden eliminar capas"
  on public.capas for delete
  using (
    exists (
      select 1 from public.perfiles
      where id = auth.uid() and rol = 'admin'
    )
  );

-- ============================================
-- TABLA: denuncias_historial
-- Historial de cambios en denuncias
-- ============================================
create table public.denuncias_historial (
  id uuid default uuid_generate_v4() primary key,
  created_at timestamp with time zone default timezone('utc'::text, now()) not null,

  denuncia_id uuid not null references public.denuncias(id) on delete cascade,
  admin_id uuid references public.perfiles(id),

  accion varchar(50) not null
    check (accion in ('creada', 'estado_cambiado', 'asignada', 'comentario', 'resuelta')),

  estado_anterior varchar(20),
  estado_nuevo varchar(20),
  notas text
);

-- Indices para historial
create index idx_historial_denuncia on public.denuncias_historial(denuncia_id);
create index idx_historial_created on public.denuncias_historial(created_at desc);

-- RLS para historial
alter table public.denuncias_historial enable row level security;

create policy "Historial visible para admins y operadores"
  on public.denuncias_historial for select
  using (
    exists (
      select 1 from public.perfiles
      where id = auth.uid() and rol in ('admin', 'operador')
    )
  );

-- CORREGIDO: Solo staff puede crear historial (no cualquier usuario)
create policy "Solo staff puede crear historial"
  on public.denuncias_historial for insert
  with check (
    exists (
      select 1 from public.perfiles
      where id = auth.uid() and rol in ('admin', 'operador')
    )
  );

-- ============================================
-- COLUMNAS ADICIONALES EN DENUNCIAS
-- ============================================
alter table public.denuncias
  add column if not exists prioridad varchar(10) default 'normal'
    check (prioridad in ('baja', 'normal', 'alta', 'urgente')),
  add column if not exists resolucion_descripcion text;

-- ============================================
-- STORAGE BUCKETS ADICIONALES
-- ============================================

-- Bucket para GeoJSON de capas
insert into storage.buckets (id, name, public)
values ('geojson', 'geojson', true)
on conflict (id) do nothing;

-- Bucket para resultados de analisis
insert into storage.buckets (id, name, public)
values ('resultados', 'resultados', true)
on conflict (id) do nothing;

-- Politicas de storage
create policy "GeoJSON es publico"
  on storage.objects for select
  using (bucket_id = 'geojson');

create policy "Admins pueden subir GeoJSON"
  on storage.objects for insert
  with check (
    bucket_id = 'geojson'
    and exists (
      select 1 from public.perfiles
      where id = auth.uid() and rol in ('admin', 'operador')
    )
  );

create policy "Resultados son publicos"
  on storage.objects for select
  using (bucket_id = 'resultados');

-- CORREGIDO: Solo staff puede subir resultados (no cualquier usuario)
create policy "Staff puede subir resultados"
  on storage.objects for insert
  with check (
    bucket_id = 'resultados'
    and exists (
      select 1 from public.perfiles
      where id = auth.uid() and rol in ('admin', 'operador')
    )
  );

-- ============================================
-- TRIGGER: updated_at automatico
-- ============================================
create or replace function update_updated_at_column()
returns trigger as $$
begin
  new.updated_at = timezone('utc'::text, now());
  return new;
end;
$$ language plpgsql;

create trigger capas_updated_at
  before update on public.capas
  for each row execute function update_updated_at_column();

-- ============================================
-- VISTAS UTILES
-- ============================================

-- Vista: Dashboard stats
create or replace view v_dashboard_stats as
select
  (select count(*) from public.denuncias where estado = 'pendiente') as denuncias_pendientes,
  (select count(*) from public.denuncias where estado = 'en_revision') as denuncias_en_revision,
  (select count(*) from public.denuncias where estado = 'resuelto') as denuncias_resueltas,
  (select hectareas_inundadas from public.analisis_gee where status = 'completed' order by created_at desc limit 1) as ultima_inundacion_ha,
  (select caminos_afectados from public.analisis_gee where status = 'completed' order by created_at desc limit 1) as caminos_afectados,
  (select created_at from public.analisis_gee where status = 'completed' order by created_at desc limit 1) as ultimo_analisis;

-- ============================================
-- RPC FUNCTIONS (Optimizadas)
-- ============================================

-- Funcion para obtener stats de denuncias con GROUP BY
create or replace function get_denuncias_stats()
returns json
language plpgsql
security definer
as $$
declare
  result json;
begin
  select json_build_object(
    'pendiente', coalesce(sum(case when estado = 'pendiente' then 1 else 0 end), 0),
    'en_revision', coalesce(sum(case when estado = 'en_revision' then 1 else 0 end), 0),
    'resuelto', coalesce(sum(case when estado = 'resuelto' then 1 else 0 end), 0),
    'rechazado', coalesce(sum(case when estado = 'rechazado' then 1 else 0 end), 0),
    'total', count(*)
  ) into result
  from public.denuncias;

  return result;
end;
$$;

-- Funcion para batch update de orden de capas
create or replace function batch_update_layer_order(layer_updates json)
returns void
language plpgsql
security definer
as $$
declare
  layer_item json;
begin
  for layer_item in select * from json_array_elements(layer_updates)
  loop
    update public.capas
    set orden = (layer_item->>'orden')::integer,
        updated_at = timezone('utc'::text, now())
    where id = (layer_item->>'id')::uuid;
  end loop;
end;
$$;

-- ============================================
-- INDICES COMPUESTOS (Optimizacion)
-- ============================================

-- Indice compuesto para filtros comunes de denuncias
create index if not exists idx_denuncias_estado_cuenca
  on public.denuncias(estado, cuenca);

create index if not exists idx_denuncias_estado_tipo
  on public.denuncias(estado, tipo);

create index if not exists idx_denuncias_asignado_estado
  on public.denuncias(asignado_a, estado)
  where asignado_a is not null;

-- Indice para busqueda por fecha y estado en analisis
create index if not exists idx_analisis_status_created
  on public.analisis_gee(status, created_at desc);

-- Indice para capas visibles ordenadas
create index if not exists idx_capas_visible_orden
  on public.capas(visible, orden)
  where visible = true;
