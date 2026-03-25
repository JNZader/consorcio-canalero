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

### 3. Reuniones
El panel de reuniones (`ReunionesPanel.tsx`) no tiene backend v2 — el endpoint `/management/reuniones` no existe.
- **Opción A**: Crear dominio `reuniones` en el backend
- **Opción B**: Integrar con el dominio `tramites` como tipo especial

### 4. Export PDF
Endpoints de generación de PDF no implementados en v2:
- Tramite export-pdf
- Asset ficha técnica export-pdf
- Reunión agenda export-pdf
- Gestión integral export-pdf
- **Referencia**: El viejo `pdf_service.py` fue eliminado — la lógica de ReportLab necesita reimplementarse

### 5. SDD: Rediseño de arquitectura geo (PRÓXIMA SESIÓN)
**Arrancar con**: `/sdd-new geo-architecture`

Decisiones de arquitectura tomadas:
- **GEE Analysis**: On-demand (botón "Analizar" en dashboard), Celery task, resultados en tabla `analisis_gee`
- **DEM Pipeline**: Local en PC del dev con Docker/GDAL, NO en server. Subir resultados al server
- **Intelligence (HCI, conflictos)**: Vistas materializadas en PostGIS, refresh a pedido o periódico
- **Celery**: Mínimo — solo para GEE analysis (tarda minutos) y refresh de vistas materializadas
- **Dashboard stats**: Vista materializada con refresh a pedido
- **Alertas**: Celery beat periódico o manual

| Tipo | Trigger | Procesamiento | Storage |
|------|---------|---------------|---------|
| GEE Analysis | Botón dashboard | Celery task (cloud GEE) | `analisis_gee` |
| DEM Pipeline | Manual desde PC dev | Docker local GDAL | GeoTIFF + `geo_layers` |
| HCI / Conflictos | Botón "Recalcular" | Síncrono o Celery | Vistas materializadas |
| Alertas | Cron o manual | Celery beat | `alertas_geo` |
| Dashboard stats | Cada consulta | Vista materializada | Refresh a pedido |

**Archivos existentes**:
- `gee-backend/Dockerfile.geo` — imagen GDAL para DEM processing
- `gee-backend/app/domains/geo/tasks.py` — tasks Celery (10 pasos DEM)
- `gee-backend/app/domains/geo/processing.py` — funciones puras (rasterio, whiteboxtools)
- `gee-backend/app/domains/geo/gee_service.py` — servicio GEE extraído
- `gee-backend/app/domains/geo/intelligence/` — cálculos de inteligencia operativa

### 6. Clasificación GEE (flood/vegetation)
`analyze_flood_task` y `supervised_classification_task` son stubs — la lógica de clasificación estaba en el legacy `MonitoringService` (~1000 líneas) que fue eliminado.
- **Migrar a**: `gee-backend/app/domains/geo/gee_service.py` o nuevo módulo
- **Incluir en el SDD de geo-architecture**

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
