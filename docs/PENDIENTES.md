# Pendientes — Consorcio Canalero v2

Última actualización: 2026-03-25

## Estado actual
- 55 tests E2E en producción — 100% pass rate
- Backend: https://cc10demayo-api.javierzader.com (healthy)
- Frontend: https://consorcio-canalero.pages.dev
- Auth JWT + Google OAuth configurado
- GEE conectado con 6 capas
- 8 dominios CRUD completos
- User admin: jnzader@gmail.com (superuser)

---

## Completados (sesión 2026-03-25)
- ~~SDD geo-architecture~~ ✅ 5 fases, 21 tasks, 26 commits (ver detalle abajo)
- ~~Clasificación GEE (flood/vegetation)~~ ✅ Incluido en geo-architecture
- ~~Reuniones~~ ✅ Dominio CRUD completo (9 endpoints, 25+ tests, agenda items con referencias)
- ~~Export PDF~~ ✅ 4 endpoints (tramite, asset, reunión, gestión integral) con branding dinámico
- ~~Invitaciones~~ ✅ Batch invite + auto-assign role on register (14 tests)
- ~~Password reset frontend~~ ✅ UI completa (SMTP diferido — logs por ahora)
- ~~Celery Worker en Coolify~~ ✅ Dockerfile.worker + recurso en Coolify (worker + beat)
- ~~Hooks pre-push~~ ✅ Graceful fallback sin Docker (fix en javi-forge + local)
- ~~README + CONTRIBUTING~~ ✅ Reescritos sin Supabase
- ~~@supabase/supabase-js~~ ✅ Ya limpio
- ~~Tests backend~~ ✅ Testcontainers PostGIS (3-tier fallback)
- ~~Rate limiter por usuario~~ ✅ user:{uuid} / ip:{address}
- ~~PWA offline~~ ✅ CacheFirst + NetworkFirst + SPA fallback
- ~~Google OAuth~~ ✅ id_token + callback fix

## Completados (sesión 2026-03-24)
- ~~Google OAuth redirect http→https~~ ✅ Funciona con --proxy-headers + COOLIFY_URL
- ~~Frontend login flow UI~~ ✅ 4 tests E2E pasando (form, login, error, Google)
- ~~Password reset~~ ✅ Endpoints forgot-password + reset-password + verify
- ~~Endpoint de invitación~~ ✅ Admin user management (list users, set role by email)
- ~~@supabase/supabase-js cleanup~~ ✅ Verificado limpio
- ~~15 enums values_callable~~ ✅ Todos arreglados
- ~~asyncpg UUID compat~~ ✅ str(user.id) en 7 ocurrencias
- ~~capas publicacion_fecha column~~ ✅ ALTER TABLE ejecutado

---

## Prioritario

### 1. ~~Google OAuth redirect http→https~~ ✅ HECHO
El redirect_uri genera `http://` en vez de `https://`. Coolify/Traefik no pasa `X-Forwarded-Proto` correctamente al container.
- **Archivo**: `gee-backend/app/auth/router.py` (usa COOLIFY_URL para forzar https)
- **Config**: `--proxy-headers` ya está en Dockerfile CMD
- **Verificar**: Traefik headers en Coolify

### 2. Frontend login flow UI completo
Login funciona por API (Swagger) pero el flujo en el frontend necesita verificación:
- Formulario login → llama JWT adapter → guarda token → redirect a dashboard
- Google OAuth → redirect a Google → callback → guarda token
- **Archivos**: `consorcio-web/src/stores/authStore.ts`, `consorcio-web/src/lib/auth/jwt-adapter.ts`

### 3. ~~Reuniones~~ ✅ HECHO (2026-03-25)
Dominio completo en `gee-backend/app/domains/reuniones/`. 9 endpoints bajo `/api/v2/reuniones`.
Frontend actualizado (`ReunionesPanel.tsx` → `/api/v2/reuniones`). Estado workflow: planificada→en_curso→finalizada.
Agenda items con referencias cruzadas a tramites/infraestructura. 25+ tests.

### 4. ~~Export PDF~~ ✅ HECHO (2026-03-25)
4 endpoints de generación PDF con ReportLab + branding dinámico desde SettingsService.
- `GET /api/v2/tramites/{id}/export-pdf` — Ficha trámite + seguimientos
- `GET /api/v2/infraestructura/assets/{id}/export-pdf` — Ficha técnica + mantenimientos
- `GET /api/v2/reuniones/{id}/export-pdf` — Agenda + asistentes
- `GET /api/v2/finanzas/resumen/{year}/export-pdf` — Informe gestión integral
- **Módulo**: `app/shared/pdf/` (base.py + builders.py), 25 tests

### 5. ~~SDD: Rediseño de arquitectura geo~~ ✅ HECHO (2026-03-25)
21 tasks en 5 fases — 26 commits atómicos. Migraciones aplicadas en producción.

**Fase 1 — Bug Fixes**: dispatch_job() en router, fix compute_hand() signature
**Fase 2 — GEE Classification**: modelo AnalisisGeo, flood/classification tasks implementadas
**Fase 3 — Intelligence**: conflict detection, batch HCI con zonal stats, alertas con dedup
**Fase 4 — Materialized Views**: 3 vistas (dashboard, HCI por zona, alertas resumen) + refresh endpoint
**Fase 5 — Celery Beat**: 2 tareas periódicas cada 6h (alertas + mat views), configurable via env vars

**Archivos nuevos/modificados**:
- `geo/models.py` — AnalisisGeo + TipoAnalisisGee enum
- `geo/gee_tasks.py` — flood analysis + supervised classification (reemplazo de stubs)
- `geo/intelligence/tasks.py` — conflict detection, batch HCI, mat view refresh
- `geo/intelligence/service.py` — alertas critico/advertencia con dedup
- `geo/intelligence/router.py` — endpoints reales + POST /hci/batch + refresh-views
- `core/celery_app.py` — beat_schedule con env vars configurables
- 3 migraciones Alembic (tabla + mat views + campos fecha)
- 4 archivos de tests nuevos (test_geo_analisis, test_geo_intelligence, test_geo_matviews, test_celery_beat)

### 6. ~~Clasificación GEE (flood/vegetation)~~ ✅ HECHO (incluido en etapa 5)

---

## Mejoras

### 7. ~~Endpoint de invitación de usuarios~~ ✅ HECHO (2026-03-25)
Modelo `PreAuthorizedEmail` + 3 endpoints admin (POST batch invite, GET pending, DELETE revoke).
Auto-assign role on register si el email está pre-autorizado. 14 tests.

### 8. ~~Password reset / update~~ ✅ HECHO (2026-03-25)
Frontend completo: ForgotPasswordForm + ResetPasswordForm + rutas + link en login.
Backend hooks ya existían (fastapi-users). SMTP **NO configurado** — el token se loguea en backend logs.
**Decisión**: SMTP diferido — pocos usuarios, admin tiene contacto directo. Alternativas documentadas en engram (Gmail SMTP, Resend, SendGrid, Mailgun).

### 9. ~~Celery Worker como recurso Coolify~~ ✅ HECHO (2026-03-25)
Recurso `celery-worker` en Coolify, mismo Dockerfile, start command:
`celery -A app.core.celery_app worker --beat --loglevel=info --concurrency=2 -Q celery,geo`
Incluye beat para tareas periódicas (alertas cada 6h + refresh mat views cada 6h).

---

## Deuda técnica

### 10. ~~Pre-commit/pre-push hooks rotos~~ ✅ HECHO (2026-03-25)
Fix en javi-forge (upstream) + consorcio-canalero (local). Docker no disponible → graceful fallback a quick checks (lint + typecheck). Fix también aplicado al template en javi-forge para que todos los repos futuros hereden el comportamiento.

### 11. ~~README.md desactualizado~~ ✅ HECHO (2026-03-25)
Reescrito completo. Sin referencias a Supabase, con stack actual y 10 dominios documentados.

### 12. ~~CONTRIBUTING.md desactualizado~~ ✅ HECHO (2026-03-25)
Reescrito con screaming architecture, conventional commits, y workaround de hooks documentado.

### 13. ~~Tests unitarios backend~~ ✅ HECHO (2026-03-25)
Testcontainers con `postgis/postgis:16-3.4`. 3-tier fallback: Docker → TEST_DATABASE_URL → exit con instrucciones.
Per-test transaction rollback preservado. `pytest tests/new/ -v` just works si Docker está corriendo.

### 14. ~~@supabase/supabase-js en package.json~~ ✅ YA LIMPIO
No está en package.json ni hay imports. Fue removido en sesión anterior.

---

## Nice to have (futuro)

### 15. DEM real de Copernicus
Cargar DEM del área del consorcio y probar el pipeline geo completo.

### 16. Monitoreo SAR temporal
Sentinel-1/2 series temporales para detección de inundaciones.

### 17. ~~Rate limiting por usuario~~ ✅ HECHO (2026-03-26)
Autenticado → `user:{uuid}`, no autenticado → `ip:{address}`. Cambio solo en middleware.

### 18. WhatsApp Bot
Plan documentado en `docs/PLAN_WHATSAPP_BOT.md`.

### 19. ~~PWA offline~~ ✅ HECHO (2026-03-26)
CacheFirst para estáticos/tiles, NetworkFirst para API (24h), SPA fallback offline. Manifest integrado.
