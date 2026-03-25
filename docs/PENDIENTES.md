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

### 7. Endpoint de invitación de usuarios
Para invitar miembros de la comisión con roles elevados (operador/admin).
- `POST /api/v2/admin/invite` — recibe lista de emails y roles
- Opción: pre-autorizar emails para auto-asignar rol al registrarse

### 8. Password reset / update
`resetPassword()` y `updatePassword()` son stubs en `consorcio-web/src/lib/auth.ts`.
- fastapi-users tiene `get_reset_password_router()` — solo falta incluirlo
- Necesita configurar envío de email (SMTP o servicio)

### 9. Celery Worker como recurso Coolify
- Recurso Dockerfile individual en Coolify
- Mismo repo, base directory `gee-backend`
- Custom start command: `celery -A app.core.celery_app worker --loglevel=info --concurrency=2 -Q celery`
- Sin dominio (no recibe HTTP)

---

## Deuda técnica

### 10. Pre-commit/pre-push hooks rotos
Los hooks de javi-forge requieren Docker corriendo + venv en PATH.
- Usar `--no-verify` mientras tanto
- Considerar simplificar hooks o usar lint-staged

### 11. README.md desactualizado
Referencia Supabase, arquitectura vieja, endpoints v1.
- Reescribir basándose en CLAUDE.md (que sí está actualizado)

### 12. CONTRIBUTING.md desactualizado
Referencia flujos de CI/CD que ya no existen.

### 13. Tests unitarios backend
Los tests en `tests/new/` necesitan PostgreSQL + PostGIS local para correr.
- Considerar testcontainers o docker-compose para test DB

### 14. @supabase/supabase-js en package.json
Verificar si fue removido. Si aún está, eliminar + npm install.

---

## Nice to have (futuro)

### 15. DEM real de Copernicus
Cargar DEM del área del consorcio y probar el pipeline geo completo.

### 16. Monitoreo SAR temporal
Sentinel-1/2 series temporales para detección de inundaciones.

### 17. Rate limiting por usuario
Actualmente es por IP — cambiar a por usuario autenticado.

### 18. WhatsApp Bot
Plan documentado en `docs/PLAN_WHATSAPP_BOT.md`.

### 19. PWA offline
Service worker ya genera, pero no hay estrategia de cache offline.
