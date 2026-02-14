# Propuestas de Mejora - Consorcio Canalero v1

**Fecha:** 2026-02-14
**Alcance:** Monorepo completo (frontend, backend, infra, DB)
**Agentes utilizados:** Backend Code Reviewer, Frontend Code Reviewer, Security Auditor, DevOps Engineer, Database Specialist, API Designer, Test Engineer, Performance Engineer

---

## Tabla de Contenidos

1. [Resumen Ejecutivo](#1-resumen-ejecutivo)
2. [Seguridad](#2-seguridad)
3. [Backend](#3-backend)
4. [Frontend](#4-frontend)
5. [Base de Datos](#5-base-de-datos)
6. [DevOps e Infraestructura](#6-devops-e-infraestructura)
7. [Diseno de API](#7-diseno-de-api)
8. [Testing](#8-testing)
9. [Performance](#9-performance)
10. [Plan de Accion Priorizado](#10-plan-de-accion-priorizado)

---

## 1. Resumen Ejecutivo

| Severidad | Cantidad |
|-----------|----------|
| CRITICA   | 12       |
| ALTA      | 28       |
| MEDIA     | 35       |
| BAJA      | 18       |

**Puntuaciones por area:**

| Area | Puntuacion | Notas |
|------|-----------|-------|
| Backend | 6.5/10 | Bugs criticos de auth, blocking GEE, sin validacion |
| Frontend | 7.5/10 | Buena lazy loading y a11y, pero providers duplicados y hooks sin React Query |
| Seguridad | 5/10 | Credenciales expuestas, auth bypass, 13 tablas sin RLS |
| Base de Datos | 6/10 | Schema divergente, sin RLS en migraciones, sin FK constraints |
| DevOps | 7.8/10 | Buen CI/CD pero pipelines duplicados y fallos silenciados |
| API Design | 8.4/10 | Buenas convenciones REST, falta estandarizar responses |
| Testing | 4/10 | Solo 19% endpoints y 0% services testeados en backend |
| Performance | 6/10 | Map page 5-15s de carga, GEE bloquea event loop |

---

## 2. Seguridad

### 2.1 CRITICAS

#### SEC-01: Credenciales reales en `.env` en disco
- **Archivos:** `gee-backend/.env` (lineas 9-12), `consorcio-web/.env`
- **Impacto:** SUPABASE_SECRET_KEY permite bypass de RLS. JWT_SECRET permite forjar tokens de cualquier usuario.
- **Accion:** Rotar todas las credenciales (Supabase secret key, JWT secret, GEE service account key). Verificar con `git log --all -- gee-backend/.env` que nunca fueron commiteados.

#### SEC-02: Authentication bypass en multiples endpoints
- **Archivos:** `gee-backend/app/api/v1/endpoints/infrastructure.py`, `management.py`, `padron.py`, `finance.py`, `jobs.py`, `monitoring.py`
- **Impacto:** Usan `Depends(get_current_user)` que retorna `None` para usuarios no autenticados. Endpoints sin role check procesan requests sin auth.
- **Accion:** Reemplazar `get_current_user` por `require_authenticated` o `require_admin_or_operator` en todos los endpoints protegidos.

#### SEC-03: `user.rol` vs `user.role` - atributo inexistente
- **Archivos:** `infrastructure.py:30`, `management.py:31`, `padron.py:27`, `finance.py:29`
- **Impacto:** El modelo `User` define `role` (ingles) pero los endpoints usan `user.rol` (espanol). Causa `AttributeError` en runtime, devuelve 500 en vez de 403.
- **Accion:** Cambiar todos los `user.rol` a `user.role`, o mejor, usar `Depends(require_admin_or_operator)`.

#### SEC-04: GEE Analysis endpoints sin autenticacion
- **Archivo:** `gee-backend/app/api/v1/endpoints/gee_analysis.py`
- **Impacto:** `/indices` y `/visualizations` sin auth. Cualquier usuario anonimo puede disparar computaciones GEE costosas.
- **Accion:** Agregar `user: User = Depends(require_authenticated)`.

#### SEC-05: Google Cloud Service Account private key en disco
- **Archivo:** `gee-backend/credentials/gee-service-account.json`
- **Impacto:** Acceso completo al proyecto GCP `cc10demayo`. Aunque esta en `.gitignore`, existe localmente.
- **Accion:** Rotar la key en GCP Console. Usar secrets manager en produccion.

### 2.2 ALTAS

#### SEC-06: Backend Docker container corre como root
- **Archivo:** `gee-backend/Dockerfile` (lineas 49-62)
- **Accion:** Agregar `USER app` con `addgroup/adduser` en la stage de produccion.

#### SEC-07: Redis sin autenticacion
- **Archivo:** `docker-compose.yml` (lineas 41-53)
- **Impacto:** Redis expuesto en puerto 6379 sin password. En produccion tampoco tiene `--requirepass`.
- **Accion:** Agregar `--requirepass <password>` y actualizar `REDIS_URL`.

#### SEC-08: Input sin validacion - `Dict[str, Any]` en endpoints
- **Archivos:** `infrastructure.py:26`, `management.py:28,48`, `padron.py:24,42`, `finance.py:26`
- **Impacto:** Diccionarios arbitrarios pasan directo a Supabase insert/update. Riesgo de mass assignment.
- **Accion:** Reemplazar con modelos Pydantic tipados.

#### SEC-09: HSTS ausente en nginx
- **Archivo:** `nginx/nginx.conf`
- **Impacto:** Sin HSTS, usuarios vulnerables a SSL stripping.
- **Accion:** Agregar `Strict-Transport-Security` header y configurar TLS.

#### SEC-10: Rol del usuario en mensajes de error
- **Archivo:** `gee-backend/app/auth.py` (lineas 255-258)
- **Impacto:** `f"Tu rol: {user.role}"` filtra informacion de autorizacion al atacante.
- **Accion:** Usar mensaje generico: `"No tienes permisos para realizar esta accion"`.

### 2.3 MEDIAS

#### SEC-11: DEBUG=true en `.env` por defecto
- **Archivo:** `gee-backend/.env:33`
- **Accion:** Asegurar `DEBUG=false` en produccion. Agregar check al arrancar.

#### SEC-12: CSRF bypass para endpoints con "upload" en la URL
- **Archivo:** `gee-backend/app/main.py` (lineas 153-155)
- **Accion:** Restringir a paths especificos en lugar de substring match.

#### SEC-13: Rate limiter in-memory sin cleanup
- **Archivo:** `gee-backend/app/core/rate_limit.py` (lineas 185-218)
- **Impacto:** Sin Redis, el dict en memoria crece indefinidamente. Puede causar OOM.
- **Accion:** Agregar limpieza periodica de entries expirados.

#### SEC-14: Content-Security-Policy ausente en nginx
- **Archivos:** `nginx/nginx.conf`, `consorcio-web/Dockerfile`
- **Accion:** Agregar CSP header equivalente al de `vercel.json`.

#### SEC-15: Instalacion insegura de Koyeb CLI en CI
- **Archivos:** `.github/workflows/ci.yml:316`, `backend-ci.yml:228`
- **Impacto:** `curl | bash` sin verificacion de integridad.
- **Accion:** Pinear version y verificar checksum.

### 2.4 BAJAS

#### SEC-16: `server_error.log` trackeado en frontend
- **Archivo:** `consorcio-web/server_error.log`
- **Accion:** Eliminar y agregar `*.log` a `.gitignore`.

#### SEC-17: Archivos temporales tmpclaude en git
- **Archivos:** `consorcio-web/tmpclaude-*`
- **Accion:** `git rm --cached` y agregar `tmpclaude-*` a `.gitignore`.

#### SEC-18: Auth store persiste PII en localStorage
- **Archivo:** `consorcio-web/src/stores/authStore.ts` (lineas 251-263)
- **Accion:** Considerar `sessionStorage` o no persistir PII.

#### SEC-19: `contacto_verificado` controlado por el cliente
- **Archivo:** `gee-backend/app/api/v1/endpoints/sugerencias.py` (lineas 128-133)
- **Impacto:** No hay verificacion server-side (OTP, email link).
- **Accion:** Implementar verificacion real o documentar como decision de diseno.

### 2.5 OWASP Top 10

| # | Categoria | Estado |
|---|-----------|--------|
| A01 | Broken Access Control | FALLA - `get_current_user` retorna None; `user.rol` bug |
| A02 | Cryptographic Failures | ALERTA - JWT secret con baja entropia (formato UUID) |
| A03 | Injection | PASA - Supabase ORM consistente; Pydantic en la mayoria |
| A04 | Insecure Design | ALERTA - Sin lockout; `contacto_verificado` client-side |
| A05 | Security Misconfiguration | FALLA - DEBUG=true; Redis sin auth; Docker root; sin HSTS/CSP |
| A06 | Vulnerable Components | PASA - Dependencies razonablemente actuales; Trivy en CI |
| A07 | Auth Failures | FALLA - Auth bypass via dependencia incorrecta |
| A08 | Data Integrity Failures | ALERTA - CI permite fallos silenciosos; Koyeb CLI sin verificar |
| A09 | Logging/Monitoring | PASA - Structured logging con sanitizacion |
| A10 | SSRF | PASA - Sin URL fetching controlado por usuario |

---

## 3. Backend

### 3.1 CRITICAS

#### BE-01: `getInfo()` de GEE bloquea el event loop async
- **Archivo:** `gee-backend/app/services/gee_service.py` (lineas 130, 141, 201, 242, 296, 305, 379, 462, 648, 661, 744, 753)
- **Impacto:** Bloquea el worker de uvicorn completo. Con 5 usuarios concurrentes cargando el mapa (8 requests GEE cada uno = 40 llamadas), el server se vuelve irresponsivo.
- **Accion:** Envolver en `asyncio.to_thread()`:
  ```python
  geojson = await asyncio.to_thread(fc.getInfo)
  ```

#### BE-02: Imports faltantes en `management.py`
- **Archivo:** `gee-backend/app/api/v1/endpoints/management.py` (lineas 122-137)
- **Impacto:** `NameError` en runtime para `get_pdf_service()` y `Response`.
- **Accion:** Agregar:
  ```python
  from fastapi import Response
  from app.services.pdf_service import get_pdf_service
  ```

### 3.2 ALTAS

#### BE-03: Celery tasks referencian metodos inexistentes
- **Archivo:** `gee-backend/app/services/gee_analysis_tasks.py` (lineas 31, 59)
- **Impacto:** `monitoring.analyze_floods()` y `monitoring.get_supervised_classification()` no existen en `MonitoringService`. Tasks siempre fallan con `AttributeError`.
- **Accion:** Actualizar a metodos reales: `classify_parcels`, `detect_changes`, etc.

#### BE-04: Singletons no thread-safe
- **Archivos:** `supabase_service.py:469-477`, `gee_service.py:152-160`, `monitoring_service.py:1027-1036`
- **Accion:** Usar `functools.lru_cache(maxsize=1)` o inicializar en el `lifespan` context manager.

#### BE-05: N+1 query en `get_agenda_detalle()`
- **Archivo:** `gee-backend/app/services/management_service.py` (lineas 92-111)
- **Impacto:** 1 query por items + N queries por referencias.
- **Accion:** Usar nested select: `select("*, agenda_referencias(*)")`.

#### BE-06: `get_deudores()` carga todo en memoria
- **Archivo:** `gee-backend/app/services/padron_service.py` (lineas 43-50)
- **Impacto:** Fetch ALL members + ALL payments, filtra en Python con O(N*M).
- **Accion:** Usar LEFT JOIN en SQL via RPC.

#### BE-07: `get_balance_summary()` suma en Python
- **Archivo:** `gee-backend/app/services/finance_service.py` (lineas 50-66)
- **Accion:** Usar `SELECT SUM(monto)` via RPC.

#### BE-08: Endpoints stats/dashboard sin autenticacion
- **Archivo:** `gee-backend/app/api/v1/endpoints/stats.py` (lineas 49-61, 167-216, 301-329)
- **Impacto:** Datos operacionales y export de CSV accesibles sin auth.
- **Accion:** Agregar `Depends(require_authenticated)`.

#### BE-09: CSRF middleware permite requests sin header Origin
- **Archivo:** `gee-backend/app/main.py` (lineas 131-145)
- **Accion:** Documentar como decision (Bearer token mitiga) o requerir Origin en endpoints publicos.

### 3.3 MEDIAS

#### BE-10: `python-jose` sin mantenimiento
- **Archivo:** `gee-backend/requirements.txt:20`
- **Accion:** Migrar a `PyJWT[crypto]>=2.8.0`.

#### BE-11: `datetime.utcnow()` deprecado
- **Archivo:** `gee-backend/app/api/v1/endpoints/sugerencias.py` (lineas 145, 239)
- **Accion:** Usar `datetime.now(timezone.utc)`.

#### BE-12: `data.dict()` deprecado en Pydantic v2
- **Archivo:** `gee-backend/app/api/v1/endpoints/sugerencias.py:510`
- **Accion:** Usar `data.model_dump(exclude_none=True)`.

#### BE-13: Monitoring dashboard cache bloquea event loop
- **Archivo:** `gee-backend/app/api/v1/endpoints/monitoring.py` (lineas 21-47)
- **Accion:** Convertir `_get_cached_or_fetch()` a async con `asyncio.to_thread()`.

#### BE-14: Sugerencias stats fetch todo para contar en memoria
- **Archivo:** `gee-backend/app/api/v1/endpoints/sugerencias.py` (lineas 317-353)
- **Accion:** Usar count queries de Supabase en lugar de iterar.

#### BE-15: Search parameter filter injection risk
- **Archivo:** `gee-backend/app/services/padron_service.py:22`
- **Accion:** Sanitizar input de busqueda antes de interpolar en filter string.

#### BE-16: Hardcoded version "1.0.0" en 3 lugares
- **Archivo:** `gee-backend/app/main.py` (lineas 311, 424, 455)
- **Accion:** Definir una vez en config o `__version__`.

#### BE-17: Inconsistencia en formatos de error
- **Archivos:** `layers.py`, `infrastructure.py`, `management.py`, `padron.py`, `finance.py`
- **Accion:** Estandarizar todos a `AppException` subclasses.

### 3.4 BAJAS

#### BE-18: `get_reports_stats()` hace 4 queries secuenciales como fallback
- **Archivo:** `gee-backend/app/services/supabase_service.py` (lineas 390-406)
- **Accion:** Usar `asyncio.gather()` o asegurar que la RPC `get_denuncias_stats` exista.

#### BE-19: Layers GET sin autenticacion
- **Archivo:** `gee-backend/app/api/v1/endpoints/layers.py` (lineas 72-80)
- **Accion:** Evaluar si la metadata de capas debe ser publica.

---

## 4. Frontend

### 4.1 CRITICAS

#### FE-01: `.env` con credenciales trackeado en git
- **Archivo:** `consorcio-web/.env`
- **Impacto:** Supabase URL y anon key en historial de git (commit `d772243`).
- **Accion:** `git rm --cached consorcio-web/.env`. Limpiar historial con BFG si es necesario.

#### FE-02: Duplicate `onClick` handler en FormularioReporte
- **Archivo:** `consorcio-web/src/components/FormularioReporte.tsx` (lineas 143-144)
- **Impacto:** Dos `onClick` en el mismo elemento. El segundo sobreescribe silenciosamente al primero. `onObtenerGPS` es dead code.
- **Accion:** Eliminar el primer `onClick={onObtenerGPS}`.

### 4.2 ALTAS

#### FE-03: Providers duplicados (MantineProvider, AppProvider)
- **Archivos:** `main.tsx`, `components/MantineProvider.tsx`, `components/AppProvider.tsx`
- **Impacto:** Multiples instancias de MantineProvider, QueryClientProvider, Notifications y AuthInitializer. Causa re-renders innecesarios y stacks de notificaciones duplicados.
- **Accion:** Eliminar `MantineProvider.tsx` y `AppProvider.tsx`. Solo usar providers en `main.tsx`.

#### FE-04: Export stats sin auth token
- **Archivo:** `consorcio-web/src/lib/api/reports.ts` (lineas 218-233)
- **Impacto:** Usa `fetch` directo sin `Authorization` header, a diferencia del resto que usa `apiFetch`.
- **Accion:** Agregar `getAuthToken()` y header `Authorization: Bearer ${token}`.

#### FE-05: Token cache ignora expiracion JWT
- **Archivo:** `consorcio-web/src/lib/api/core.ts` (lineas 19-51)
- **Impacto:** Cache de 5 minutos fijos sin importar el `exp` del JWT. Si el token expira antes, API calls fallan con 401.
- **Accion:** Parsear `session.expires_at` y cachear hasta 30s antes de la expiracion real.

#### FE-06: Admin PDF export sin feedback de error + DOM leak
- **Archivo:** `consorcio-web/src/components/admin/AdminDashboard.tsx` (lineas 73-98)
- **Impacto:** `console.error` en vez de `logger`. Sin notificacion al usuario. Elemento `<a>` no se remueve del DOM. `revokeObjectURL` inmediato puede interrumpir la descarga.
- **Accion:** Agregar notificacion de error, `removeChild(a)`, y `setTimeout` para revoke.

#### FE-07: `waitForAuth()` puede colgar indefinidamente
- **Archivo:** `consorcio-web/src/routeTree.gen.tsx` (lineas 59-71)
- **Impacto:** Si auth initialization falla o nunca setea `initialized = true`, la promesa nunca resuelve. Pantalla en blanco.
- **Accion:** Agregar timeout de 10 segundos con `Promise.race`.

#### FE-08: `useAuth` hook con 8 subscripciones separadas al store
- **Archivo:** `consorcio-web/src/hooks/useAuth.ts` (lineas 129-136)
- **Impacto:** 8 llamadas a `useAuthStore()` = 8 subscripciones independientes. Anti-patron de performance en Zustand.
- **Accion:** Usar `useShallow` con un unico selector.

#### FE-09: Admin panels bypasean la capa centralizada de API
- **Archivos:** `FinanzasPanel.tsx`, `TramitesPanel.tsx`, `ReunionesPanel.tsx`, `ReportsPanel.tsx`
- **Impacto:** `apiFetch` directo en vez de modulos API centralizados. `useState/useEffect` en vez de TanStack Query. Sin cache, retry, ni deduplicacion.
- **Accion:** Crear modulos API (`api/finance.ts`, `api/management.ts`) y hooks de TanStack Query.

### 4.3 MEDIAS

#### FE-10: `configStore` nunca setea `initialized: true` en error
- **Archivo:** `consorcio-web/src/stores/configStore.ts` (lineas 33-39)
- **Accion:** Agregar `initialized: true` en el branch de error.

#### FE-11: `noUnusedLocals` y `noUnusedParameters` deshabilitados
- **Archivo:** `consorcio-web/tsconfig.json` (lineas 20-21)
- **Accion:** Habilitar para prevenir dead code.

#### FE-12: `console.error` inconsistente vs `logger.error`
- **Impacto:** 14 instancias de `console.error` en admin panels y config store.
- **Accion:** Migrar a `logger`.

#### FE-13: `@types/leaflet-draw` en dependencies en vez de devDependencies
- **Archivo:** `consorcio-web/package.json:41`
- **Accion:** Mover a `devDependencies`.

#### FE-14: `safeJsonParse` usa type assertion inseguro
- **Archivo:** `consorcio-web/src/lib/errorHandler.ts:160`
- **Accion:** Usar `safeJsonParseWithValidation` en su lugar.

#### FE-15: `as any` en MapaLeaflet
- **Archivo:** `consorcio-web/src/components/MapaLeaflet.tsx:398`
- **Accion:** Usar type mapping o enum validation.

#### FE-16: PWA manifest referencia iconos inexistentes
- **Archivo:** `consorcio-web/vite.config.ts` (lineas 18-28)
- **Accion:** Crear los iconos PWA o remover el manifest.

#### FE-17: Biome desactiva reglas importantes
- **Archivo:** `consorcio-web/biome.json`
- **Impacto:** `noNonNullAssertion: off`, `noArrayIndexKey: off`, `useSemanticElements: off`
- **Accion:** Re-evaluar si se pueden habilitar.

#### FE-18: Cognitive complexity threshold muy alto (30)
- **Archivo:** `consorcio-web/biome.json` (lineas 17-22)
- **Accion:** Reducir a 15-20.

### 4.4 BAJAS

#### FE-19: Hardcoded year "2026"
- **Archivo:** `consorcio-web/src/components/admin/management/FinanzasPanel.tsx:58`
- **Accion:** Usar `new Date().getFullYear()`.

#### FE-20: Link roto a `/denuncias` (deberia ser `/reportes`)
- **Archivo:** `consorcio-web/src/components/MapaPage.tsx:114`
- **Accion:** Cambiar `href="/denuncias"` a `href="/reportes"`.

#### FE-21: `ProtectedRoute` usa `globalThis.location.href` en vez de router
- **Archivo:** `consorcio-web/src/components/admin/ProtectedRoute.tsx:90`
- **Accion:** Usar `navigate` de TanStack Router para evitar full page reload.

#### FE-22: `onVerified` callback puede dispararse multiples veces
- **Archivo:** `consorcio-web/src/hooks/useContactVerification.ts` (lineas 82-86)
- **Accion:** Agregar guardia para single-fire.

---

## 5. Base de Datos

### 5.1 CRITICAS

#### DB-01: 13 tablas sin Row Level Security (RLS)
- **Archivos:** Migraciones 007-011
- **Tablas afectadas:** `infraestructura`, `mantenimiento_logs`, `tramites`, `tramite_avances`, `gestion_seguimiento`, `reuniones`, `agenda_items`, `agenda_referencias`, `consorcistas` (PII), `cuotas_pagos` (financiero), `gastos`, `presupuestos`, `presupuesto_items`
- **Impacto:** Supabase expone PostgREST directamente. Cualquier usuario con la anon key puede leer/escribir estas tablas, bypass del backend.
- **Accion:** Habilitar RLS y crear policies para cada tabla.

#### DB-02: Schema divergente entre `schema.sql` y migracion `001`
- **Archivos:** `consorcio-web/supabase/schema.sql` vs `gee-backend/migrations/001_perfiles_table.sql`
- **Impacto:** `perfiles` definida dos veces con columnas diferentes. `handle_new_user()` trigger diferente. RLS policies diferentes.
- **Accion:** Establecer una unica fuente de verdad para el schema.

### 5.2 ALTAS

#### DB-03: Foreign keys faltantes
- `tramite_avances.usuario_id` - sin FK constraint
- `gestion_seguimiento.usuario_gestion` - sin FK constraint
- **Accion:** Agregar `REFERENCES auth.users(id)` o `REFERENCES perfiles(id)`.

#### DB-04: Sin CHECK constraints en coordenadas
- **Tablas:** `denuncias`, `infraestructura`
- **Accion:** Agregar `CHECK (latitud BETWEEN -90 AND 90)` y `CHECK (longitud BETWEEN -180 AND 180)`.

#### DB-05: FKs polimorficas sin integridad referencial
- **Tablas:** `gestion_seguimiento.entidad_id`, `agenda_referencias.entidad_id`
- **Impacto:** Referencian multiples tablas segun `entidad_tipo` pero PostgreSQL no puede enforcer esto.
- **Accion:** Considerar columnas FK separadas nullable con CHECK constraint.

#### DB-06: `denuncias` INSERT policy no enforce `user_id = auth.uid()`
- **Archivo:** `schema.sql` (lineas 80-82)
- **Impacto:** Un usuario podria crear reportes atribuidos a otro usuario.
- **Accion:** Agregar `WITH CHECK (user_id = auth.uid())`.

#### DB-07: Indexes faltantes en FK columns
- `denuncias.user_id` - sin index
- `comentarios.denuncia_id` - sin index
- `comentarios.user_id` - sin index
- `tramite_avances.tramite_id` - sin index
- `cuotas_pagos.consorcista_id` - sin index
- **Accion:** Crear indexes para cada FK column.

#### DB-08: Operaciones multi-tabla sin transacciones
- `infrastructure_service.py:add_maintenance_log()` - insert log + update asset sin tx
- `management_service.py:add_seguimiento()` - insert seguimiento + update entity sin tx
- `management_service.py:add_tramite_avance()` - insert avance + update tramite sin tx
- `supabase_service.py:update_report()` - get + update + insert history sin tx
- **Accion:** Usar RPC functions para operaciones atomicas.

### 5.3 MEDIAS

#### DB-09: `cuenca` como texto libre en multiples tablas
- **Tablas:** `denuncias`, `infraestructura`, `caminos_afectados`, `sugerencias`
- **Accion:** Crear tabla `cuencas` de referencia con FK.

#### DB-10: Sin CHECK constraints en montos financieros
- `cuotas_pagos.monto` - puede ser negativo
- `gastos.monto` - puede ser negativo
- **Accion:** Agregar `CHECK (monto >= 0)`.

#### DB-11: `updated_at` sin trigger en tablas clave
- **Tablas sin trigger:** `denuncias`, `reuniones`, `perfiles` (schema.sql version)
- **Accion:** Crear trigger `set_updated_at()`.

#### DB-12: `auth.role()` deprecado en RLS policies
- **Archivo:** `schema.sql` (lineas 82, 139)
- **Accion:** Usar `auth.uid() IS NOT NULL` o `TO authenticated`.

#### DB-13: Sin herramienta de migracion
- **Impacto:** No hay Flyway, Alembic o Supabase CLI migrations configurado. Migraciones se aplican manualmente.
- **Accion:** Adoptar Supabase CLI migrations o Alembic.

#### DB-14: `sugerencias` permite ver internas a ciudadanos
- **Archivo:** `004_sugerencias_tables.sql` (lineas 80-82)
- **Impacto:** SELECT policy permite leer sugerencias `tipo = 'interna'` a cualquier autenticado.
- **Accion:** Filtrar por rol en la policy.

#### DB-15: `batch_update_layer_order()` es SECURITY DEFINER sin auth check
- **Archivo:** `schema.sql` (linea 509)
- **Impacto:** Cualquier usuario podria reordenar capas via RPC.
- **Accion:** Agregar verificacion de rol dentro de la funcion.

#### DB-16: `v_dashboard_stats` view con 6 subqueries
- **Archivo:** `schema.sql` (lineas 471-478)
- **Accion:** Reemplazar con materialized view o cache en Redis.

### 5.4 BAJAS

#### DB-17: UUID generation inconsistente
- **Impacto:** Mezcla `uuid_generate_v4()` y `gen_random_uuid()`.
- **Accion:** Estandarizar en `gen_random_uuid()`.

#### DB-18: `caminos_afectados.geojson` es TEXT en vez de JSONB
- **Accion:** Cambiar a JSONB para habilitar queries JSON.

#### DB-19: Migraciones con gaps (001, 004, 005... sin 002, 003)
- **Accion:** Documentar las migraciones faltantes.

#### DB-20: `perfiles.email` sin UNIQUE constraint
- **Archivo:** `schema.sql:13`
- **Accion:** Agregar constraint UNIQUE.

#### DB-21: Sin `updated_at` en 10 tablas
- **Tablas:** `caminos_afectados`, `mantenimiento_logs`, `tramite_avances`, `gestion_seguimiento`, `agenda_items`, `agenda_referencias`, `consorcistas`, `cuotas_pagos`, `gastos`, `presupuesto_items`
- **Accion:** Agregar columna y trigger.

#### DB-22: Sin soft-delete en tablas criticas
- **Accion:** Considerar `deleted_at TIMESTAMPTZ` en `denuncias`, `consorcistas`, `tramites`.

---

## 6. DevOps e Infraestructura

### 6.1 ALTAS

#### DO-01: Pipelines CI duplicados
- **Archivos:** `.github/workflows/ci.yml` + `backend-ci.yml`
- **Impacto:** Ambos se disparan en push a main, consumiendo doble CI minutes y causando race conditions en deploy.
- **Accion:** Eliminar `backend-ci.yml` y mantener `ci.yml` como pipeline unico.

#### DO-02: `|| true` y `continue-on-error` silencian fallos
- **Archivos:** `ci.yml` (lineas 87-88, 146, 154), `backend-ci.yml:113`
- **Impacto:** Tests, MyPy, Bandit pueden fallar sin bloquear deployment.
- **Accion:** Remover `|| true` y `continue-on-error: true` de steps criticos.

#### DO-03: Sin staging environment
- **Impacto:** Changes van directo a produccion.
- **Accion:** Agregar staging en Vercel (preview) y/o Koyeb.

#### DO-04: Backend Dockerfile sin non-root user
- **Archivo:** `gee-backend/Dockerfile`
- **Accion:** Agregar `addgroup/adduser` + `USER app`.

#### DO-05: Sin .dockerignore por servicio
- **Impacto:** Build contexts por subdirectorio no leen el `.dockerignore` raiz.
- **Accion:** Crear `.dockerignore` en `gee-backend/` y `consorcio-web/`.

### 6.2 MEDIAS

#### DO-06: Deploy usa tag `latest` en vez de SHA
- **Archivo:** `ci.yml` (lineas 324, 332)
- **Impacto:** Race condition si dos pushes ocurren cercanos.
- **Accion:** Usar `${{ github.sha }}` como tag.

#### DO-07: Build ARG mismatch en frontend Dockerfile
- **Archivos:** `consorcio-web/Dockerfile` vs `docker-compose.prod.yml`
- **Impacto:** Dockerfile usa `PUBLIC_SUPABASE_URL` pero compose pasa `VITE_SUPABASE_URL`. Build-time env injection rota.
- **Accion:** Alinear nombres a `VITE_*`.

#### DO-08: gcc en imagen de produccion backend
- **Archivo:** `gee-backend/Dockerfile:12`
- **Accion:** Separar en stage de compilacion y stage de runtime limpio.

#### DO-09: Supabase keep-alive con curl malformado
- **Archivo:** `.github/workflows/supabase-keep-alive.yml` (lineas 15-17)
- **Accion:** Agregar backslashes de continuacion de linea.

#### DO-10: Sin monitoring ni alerting externo
- **Impacto:** Si Koyeb cae, nadie se entera.
- **Accion:** Integrar UptimeRobot, BetterStack, o similar.

#### DO-11: Sin Sentry para error tracking
- **Impacto:** DSN placeholder existe pero no esta integrado.
- **Accion:** Configurar Sentry. Quick win.

#### DO-12: Celery worker sin healthcheck en docker-compose
- **Archivo:** `docker-compose.yml:58`
- **Accion:** Agregar `celery inspect ping` como healthcheck.

#### DO-13: Dos nginx configs compitiendo
- **Archivos:** `nginx/nginx.conf` vs config embebida en `consorcio-web/Dockerfile`
- **Accion:** Consolidar en una sola estrategia.

#### DO-14: Topologia de deploy confusa (Vercel vs Koyeb para frontend)
- **Impacto:** CI deploya frontend a Koyeb pero existe `vercel.json`.
- **Accion:** Documentar y clarificar la topologia de produccion.

#### DO-15: Makefile `backend-build` usa target incorrecto
- **Archivo:** `Makefile:97` - `--target runtime` pero stage se llama `production`
- **Accion:** Cambiar a `--target production`.

### 6.3 BAJAS

#### DO-16: Hook versions desactualizados en pre-commit
- **Archivo:** `.pre-commit-config.yaml`
- **Accion:** Correr `pre-commit autoupdate`.

#### DO-17: Hadolint skippeado en CI
- **Accion:** Considerar habilitar en CI.

#### DO-18: Makefile muestra puerto incorrecto
- **Archivo:** `Makefile:165` - muestra 4321 en vez de 5173.
- **Accion:** Corregir mensaje.

---

## 7. Diseno de API

**Puntuacion general: 8.4/10 (B+)**

### 7.1 ALTAS

#### API-01: Inconsistencia en response envelopes
- **Patron 1:** Array directo `[{...}, ...]`
- **Patron 2:** Wrapped `{"items": [...], "total": 100}`
- **Patron 3:** Named wrapper `{"consorcios": [...], "total": 5}`
- **Accion:** Estandarizar en formato tipo JSON:API:
  ```json
  {"data": [...], "meta": {"total": 100, "page": 1, "per_page": 20}}
  ```

#### API-02: `/agendar` usa query param en vez de body para POST
- **Archivos:** Backend `sugerencias.py`, Frontend `sugerencias.ts`
- **Accion:** Mover `fecha_reunion` al request body.

### 7.2 MEDIAS

#### API-03: DELETE retorna 200 en vez de 204
- **Accion:** Cambiar a 204 No Content.

#### API-04: Paginacion inconsistente
- Algunos endpoints paginan, otros retornan todo.
- Falta `total_pages`, `has_next`, `has_previous`.
- **Accion:** Crear `PaginatedResponse` estandar.

#### API-05: Sin OpenAPI 3.1 specification auto-generada
- **Accion:** Configurar `custom_openapi()` en FastAPI con security schemes y examples.

#### API-06: Sin deprecation strategy ni versionado documentado
- **Accion:** Documentar policy de versionado y agregar headers `Deprecation`/`Sunset`.

#### API-07: Sin ETags para conditional requests
- **Accion:** Implementar ETag + `If-None-Match` para GET endpoints.

### 7.3 BAJAS

#### API-08: Sin operaciones bulk
- **Accion:** Considerar `POST /reports/bulk`, `POST /layers/bulk`.

#### API-09: Sin rate limits por rol
- **Accion:** Implementar limites diferenciados para ciudadano/operador/admin.

#### API-10: Sin API changelog
- **Accion:** Documentar breaking changes y deprecaciones.

---

## 8. Testing

### 8.1 Estado Actual

| Metrica | Backend | Frontend | Objetivo |
|---------|---------|----------|----------|
| Archivos test | 4 (1 invalido) | 6 | -- |
| Tests estimados | ~35 | ~106 | -- |
| Endpoints cubiertos | 3/16 (19%) | N/A | 80%+ |
| Services cubiertos | 0/9 (0%) | N/A | 70%+ |
| Components cubiertos | N/A | 1/50+ (2%) | 30%+ |
| Hooks cubiertos | N/A | 1/10 (10%) | 70%+ |
| Integration tests | 0 | 0 | 5-10 |
| E2E tests | 0 | 0 | 3-5 journeys |

### 8.2 CRITICAS

#### TEST-01: CI silencia fallos de tests
- **Archivos:** `ci.yml`, `backend-ci.yml`
- **Accion:** Remover `continue-on-error: true` y `|| echo` de test steps.

### 8.3 Tests Prioritarios Faltantes

#### Prioridad 1 - CRITICA

| ID | Test | Archivo Target | Razon |
|----|------|---------------|-------|
| TEST-02 | `validators.ts` unit tests | `consorcio-web/src/lib/validators.ts` | Valida input usuario (email, phone, CUIT). Bugs = vulnerabilidades. |
| TEST-03 | Reports endpoint tests | `gee-backend/app/api/v1/endpoints/reports.py` | Core business - lifecycle de reportes. |
| TEST-04 | Layers endpoint tests | `gee-backend/app/api/v1/endpoints/layers.py` | GeoJSON layer management. Upload validation critica. |
| TEST-05 | `typeGuards.ts` unit tests | `consorcio-web/src/lib/typeGuards.ts` | Runtime type guards son capa de seguridad. |
| TEST-06 | Exception sanitization tests | `gee-backend/app/core/exceptions.py` | `sanitize_error_message` previene leak de paths/secrets. |

#### Prioridad 2 - ALTA

| ID | Test | Archivo Target |
|----|------|---------------|
| TEST-07 | `errorHandler.ts` tests | `consorcio-web/src/lib/errorHandler.ts` |
| TEST-08 | Stats endpoint tests | `gee-backend/app/api/v1/endpoints/stats.py` |
| TEST-09 | Sugerencias endpoint tests | `gee-backend/app/api/v1/endpoints/sugerencias.py` |
| TEST-10 | Rate limiter unit tests | `gee-backend/app/core/rate_limit.py` |
| TEST-11 | File validation tests | `gee-backend/app/core/file_validation.py` |
| TEST-12 | `useAuth.ts` hook tests | `consorcio-web/src/hooks/useAuth.ts` |
| TEST-13 | `useJobStatus.ts` hook tests | `consorcio-web/src/hooks/useJobStatus.ts` |

#### Prioridad 3 - MEDIA

| ID | Test | Archivo Target |
|----|------|---------------|
| TEST-14 | Monitoring endpoint tests | `monitoring.py` |
| TEST-15 | Infrastructure endpoint tests | `infrastructure.py` |
| TEST-16 | Management endpoint tests | `management.py` |
| TEST-17 | Padron/Finance endpoint tests | `padron.py`, `finance.py` |
| TEST-18 | `FormularioReporte.tsx` tests | Component test |
| TEST-19 | `FormularioSugerencia.tsx` tests | Component test |
| TEST-20 | `ErrorBoundary.tsx` tests | Component test |
| TEST-21 | `ProtectedRoute.tsx` tests | Component test |

---

## 9. Performance

### 9.1 CRITICAS

#### PERF-01: Map page carga en 5-15 segundos
- **Archivo:** `consorcio-web/src/components/MapaLeaflet.tsx` (lineas 357-365)
- **Impacto:** 3 hooks disparan 8 requests GEE paralelos en cada mount. Cada `getInfo()` es 1-5 segundos.
- **Accion:**
  1. Servir GeoJSON estatico desde `public/capas/` (ya existen los archivos, 553-3000 bytes cada uno)
  2. Implementar cache Redis para respuestas GEE (TTL 24h)
  3. Migrar `useGEELayers` a React Query
  4. Crear batch endpoint `/api/v1/gee/layers/batch`
- **Impacto estimado:** De 5-15s a 0.5-1.5s.

#### PERF-02: `get_caminos_con_colores()` descarga TODA la red vial de GEE
- **Archivo:** `gee-backend/app/services/gee_service.py` (lineas 361-446)
- **Impacto:** 10-30 segundos y megabytes de datos. Itera 3 veces por features.
- **Accion:** Cache en Redis 24h. Pre-computar como archivo estatico con Celery cron.

#### PERF-03: `getInfo()` bloquea event loop (ver BE-01)
- **Impacto estimado de fix:** 5-10x mejora en throughput bajo carga concurrente.

### 9.2 ALTAS

#### PERF-04: Sin uvicorn workers en produccion
- **Archivo:** `docker-compose.prod.yml`
- **Impacto:** Single worker + blocking GEE = solo 1 request GEE a la vez.
- **Accion:** Agregar `--workers 4` o usar gunicorn con uvicorn workers.

#### PERF-05: `recharts` (~200KB) no en manual chunk
- **Archivo:** `consorcio-web/vite.config.ts` (lineas 86-97)
- **Impacto:** Se bundlea en el chunk del primer componente que lo importa.
- **Accion:** Agregar `'vendor-charts': ['recharts']` a manualChunks.

#### PERF-06: `useGEELayers`, `useCaminosColoreados`, `useInfrastructure` no usan React Query
- **Archivos:** `useGEELayers.ts`, `useCaminosColoreados.ts`, `useInfrastructure.ts`
- **Impacto:** Sin cache entre navegaciones, sin deduplicacion, sin retry.
- **Accion:** Migrar a `useQueries()` de TanStack Query.

#### PERF-07: `defaultPreloadStaleTime: 0` desactiva preload
- **Archivo:** `consorcio-web/src/main.tsx:29`
- **Impacto:** Intent-based preloading no funciona porque data se marca stale inmediatamente.
- **Accion:** Cambiar a `defaultPreloadStaleTime: 30000`.

### 9.3 MEDIAS

#### PERF-08: `@mantine/charts` y `@mantine/dates` no chunkeados
- **Accion:** Crear `'vendor-mantine-extras': ['@mantine/charts', '@mantine/dates', '@mantine/dropzone']`.

#### PERF-09: MapContainer key incluye coordenadas, causa remount completo
- **Archivo:** `consorcio-web/src/components/MapaLeaflet.tsx:573`
- **Accion:** Usar `setView()` via ref en vez de cambiar key.

#### PERF-10: GeoJSON key con `features.length` fuerza remount
- **Archivo:** `MapaLeaflet.tsx` (lineas 613-660)
- **Accion:** Usar key estable basada en nombre de capa.

#### PERF-11: Sin Canvas renderer para capas de caminos pesadas
- **Archivo:** `MapaLeaflet.tsx` (lineas 647-659)
- **Accion:** Agregar `preferCanvas: true` en MapContainer.

#### PERF-12: Assets como Overlay individuales en LayersControl
- **Archivo:** `MapaLeaflet.tsx` (lineas 682-727)
- **Accion:** Agrupar en un solo `FeatureGroup`.

#### PERF-13: Config no se pre-fetcha en app init
- **Archivo:** `consorcio-web/src/stores/configStore.ts`
- **Accion:** Llamar `fetchConfig()` en `main.tsx` despues de crear el router.

#### PERF-14: BaseHTTPMiddleware chain overhead
- **Archivo:** `gee-backend/app/main.py` (lineas 380-406)
- **Impacto:** 6 middlewares con BaseHTTPMiddleware agrega 5-15ms/request.
- **Accion:** Convertir middlewares simples a pure ASGI.

#### PERF-15: Health check hace query a Supabase cada 30s
- **Archivo:** `gee-backend/app/main.py` (lineas 216-227)
- **Accion:** Docker healthcheck debe usar `/` en vez de `/health`.

#### PERF-16: Sin font subsetting para `@fontsource/inter`
- **Accion:** Importar solo weights necesarios (400, 600, 700) y Latin subset.

#### PERF-17: Redis `maxmemory` solo 128MB
- **Archivo:** `docker-compose.prod.yml:69`
- **Accion:** Aumentar a 256-512MB si se implementa cache GEE. Usar `volatile-lru`.

#### PERF-18: Sin Brotli en nginx
- **Archivo:** `nginx/nginx.conf`
- **Accion:** Agregar Brotli o pre-comprimir con vite-plugin-compression.

#### PERF-19: `application/geo+json` no en gzip_types
- **Archivo:** `nginx/nginx.conf` (lineas 42-52)
- **Accion:** Agregar a la lista.

---

## 10. Plan de Accion Priorizado

### Fase 0 - Inmediato (hoy)

| # | Accion | Esfuerzo | Area | IDs |
|---|--------|----------|------|-----|
| 1 | Rotar credenciales (Supabase, JWT, GEE key) | 30 min | Seguridad | SEC-01, SEC-02, SEC-05 |
| 2 | Fix `user.rol` -> `user.role` + usar `require_admin_or_operator` | 1h | Seguridad/Backend | SEC-03, SEC-02, BE-01 |
| 3 | Agregar auth a endpoints desprotegidos | 1h | Seguridad | SEC-04, BE-08 |
| 4 | Agregar imports faltantes en `management.py` | 5 min | Backend | BE-02 |

### Fase 1 - Semana 1

| # | Accion | Esfuerzo | Area | IDs |
|---|--------|----------|------|-----|
| 5 | Habilitar RLS en 13 tablas (migraciones 007-011) | 4h | Database | DB-01 |
| 6 | Servir GeoJSON estatico + cache Redis para GEE | 4h | Performance | PERF-01, PERF-02 |
| 7 | Wrap `getInfo()` en `asyncio.to_thread()` | 2h | Backend/Perf | BE-01, PERF-03 |
| 8 | Eliminar pipeline CI duplicado + remover `|| true` | 1h | DevOps | DO-01, DO-02, TEST-01 |
| 9 | Agregar modelos Pydantic a endpoints `Dict[str,Any]` | 3h | Seguridad | SEC-08 |
| 10 | Fix duplicate onClick + providers duplicados | 1h | Frontend | FE-02, FE-03 |

### Fase 2 - Semana 2-3

| # | Accion | Esfuerzo | Area | IDs |
|---|--------|----------|------|-----|
| 11 | Non-root user en backend Dockerfile | 30 min | DevOps | DO-04, SEC-06 |
| 12 | Redis auth + password | 30 min | Seguridad | SEC-07 |
| 13 | Migrar hooks GEE a React Query | 4h | Frontend/Perf | PERF-06, FE-09 |
| 14 | Agregar uvicorn workers | 15 min | Performance | PERF-04 |
| 15 | Fix token cache con JWT exp | 1h | Frontend | FE-05 |
| 16 | Fix waitForAuth timeout | 30 min | Frontend | FE-07 |
| 17 | Agregar tests criticos (validators, typeGuards, endpoints) | 8h | Testing | TEST-02 a TEST-06 |
| 18 | Resolver schema divergente DB | 2h | Database | DB-02 |
| 19 | Agregar FK constraints faltantes | 1h | Database | DB-03 |

### Fase 3 - Semana 4+

| # | Accion | Esfuerzo | Area | IDs |
|---|--------|----------|------|-----|
| 20 | Estandarizar response envelopes | 4h | API | API-01 |
| 21 | Fix Celery tasks con metodos reales | 2h | Backend | BE-03 |
| 22 | Agregar Sentry + uptime monitoring | 1h | DevOps | DO-10, DO-11 |
| 23 | Agregar recharts a manualChunks + extras | 30 min | Performance | PERF-05, PERF-08 |
| 24 | Fix defaultPreloadStaleTime | 5 min | Performance | PERF-07 |
| 25 | Migrar python-jose a PyJWT | 2h | Backend | BE-10 |
| 26 | Agregar indexes faltantes | 1h | Database | DB-07 |
| 27 | Tests prioridad 2 y 3 | 16h | Testing | TEST-07 a TEST-21 |
| 28 | Transacciones atomicas en operaciones multi-tabla | 4h | Database | DB-08 |

---

## Aspectos Positivos Identificados

No todo son problemas. Los agentes tambien identificaron practicas solidas:

- **Structured logging con sanitizacion PII** - Excelente implementacion con structlog
- **File upload validation con magic bytes** - Previene MIME spoofing
- **Path traversal prevention** en GeoJSON upload
- **CSRF middleware** con validacion de Origin
- **Security headers** completos (X-Frame-Options, X-Content-Type-Options, etc.)
- **Rate limiting** con sliding window y Redis con fallback in-memory
- **Pre-commit hooks** excelentes (gitleaks, ruff, biome, hadolint, commitizen)
- **Error sanitization** previene leak de paths y stack traces
- **Lazy loading** bien implementado en todas las paginas
- **Accessibility** con skip links, ARIA labels, live regions, focus traps
- **PWA caching** inteligente para tile servers
- **Auth architecture** con singleton initialization anti-race condition
- **Dependabot** con grouping y scheduling excelentes (9/10)
- **Health checks** comprehensivos para Supabase, Redis y GEE
- **Test infrastructure** con buenos fixtures y mocking en conftest.py
