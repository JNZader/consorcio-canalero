# Auditoría exhaustiva — Consorcio Canalero

Fecha: 2026-10-23
HEAD analizado: `ce951fd0` (rama `feat/conocimiento-ingesta-sin-orden`)
Alcance: aplicación completa — backend (auth, núcleo, 9 dominios de negocio, RAG/conocimiento), frontend `consorcio-web`, ETLs de `scripts/`, infraestructura (Docker/compose, Caddy, Martin, Makefile), CI (`.github/workflows`).
Método: 7 auditorías paralelas por área (lentes: seguridad, fiabilidad, corrección de negocio, geo, RAG, frontend, infra) + **ronda de refutación adversarial** sobre todos los candidatos CRITICAL + verificación inline puntual. Sin modificar código, sin builds, sin ejecutar suites de tests.

---

## Resumen ejecutivo

La salud general del repo es **alta** — varias áreas (sesiones/transacciones, auth, CI, determinismo del RAG, disciplina async) están por encima del estándar — pero la auditoría confirma **5 hallazgos CRITICAL**, **~37 WARNING** y **~16 sugerencias**.

Los 5 CRITICAL en una línea:

1. El proxy público de tiles solo verifica la lista de capas publicadas cuando la request lleva `rescale_min` — sin él, acceso anónimo (exento de rate limit) a 8 tipos de capas deliberadamente privadas.
2. Las tareas `gee.*` no matchean el routing `geo.*` de Celery y caen en el worker de mantenimiento (sin GDAL, 512 MB) — análisis de 3 horas sobre el worker equivocado, con riesgo de stall en cascada del outbox.
3. Bootstrap de clone fresco roto: `REDIS_PASSWORD` es requerido por el compose de dev pero no lo provisiona ni `setup.sh` ni `.env.example`.
4. Regresión 84c0a9c4: la capa del límite del consorcio en `/admin/images` es código muerto (el efecto de zona lee `mapInstanceRef.current` antes de que el IIFE async asigne el mapa).
5. Mutaciones de finanzas: errores 100% silenciosos (catch con solo `logger.error`, sin toast ni estado) y doble-submit posible en los 4 modales (sin `loading`/`disabled`).

**La refutación derribó 2 CRITICAL preliminares** (ver §Refutaciones) — el sistema de presupuestos tiene un unique index en la migración que el modelo no declara, y la UI de reuniones envía UTC ISO. Quedan como WARNING con matiz.

---

## Refutaciones (verificación adversarial)

Todo candidato CRITICAL fue sometido a refutación independiente. Veredictos:

| Candidato | Veredicto | Razón decisiva |
|---|---|---|
| Presupuesto duplicable con suma doble (DOM) | **REFUTADO como CRITICAL** | La migración `b5c2e8f3a194_add_finanzas_tables.py:129-134` crea `ix_presupuestos_v2_anio_rubro` **unique** sobre `(anio, rubro)`; un segundo POST idéntico produce IntegrityError → 500 (no commit, no suma doble). Queda como WARNING: el modelo no declara el constraint (drift metadata/DB), el 500 debería ser 409, y no existe PATCH/DELETE para corregir líneas. |
| `AnalisisGee.usuario_id` con `ondelete=SET NULL` sobre columna NOT NULL (DOM) | **CONFIRMADO CON MATIZ** | El defecto es real y la migration `zz_users_fk_nullable.py` arregló exactamente esta clase para 6 tablas hermanas pero omite `analisis_gee`. Matiz: hoy no hay escritor vivo de filas (`save_analysis` sin callers en producción) → defecto latente, no ruptura activa. |
| Reuniones acepta datetimes naive → corrimiento de 3 h (DOM) | **REFUTADO como CRITICAL** | La única UI escritora (`useReunionesController.ts:144`) envía `new Date(...).toISOString()` (UTC con Z); el instante round-trip correctamente. El corrimiento solo afecta a clientes no-UI que posteen naive directo a la API → queda como hardening de schema (rechazar naive). |
| Proxy de tiles sin check de publicidad (GEO) | **CONFIRMADO** | Verificado inline: el check corre solo dentro de `if parsed_rescale_min is not None` (`router_core.py:477`). |
| Routing Celery `gee.*` → cola equivocada (NUC) | **CONFIRMADO** | Verificado empíricamente con el venv del repo: `gee.analyze_flood → cola "celery"`, `geo.process_dem_pipeline → cola "geo"`. |
| Bootstrap `REDIS_PASSWORD` (INF) | **CONFIRMADO** | Compose `:?` aborta la carga completa del archivo; `.env.example` raíz no tiene la clave; `setup.sh` nunca crea `.env` raíz. |
| Capa de zona muerta en `/admin/images` (FE) | **CONFIRMADO** | IIFE async + efecto sync con deps `[]` en el mismo flush; `rg` confirma que ningún otro path renderiza la zona; `git show 84c0a9c4` confirma la forma pre-regresión. |
| Finanzas silencioso + doble-submit (FE) | **CONFIRMADO** | Los 4 handlers hacen catch con solo `logger.error`; botones submit sin `loading`/`disabled` en 4 modales; sin `useMutation` ni dedupe en `apiFetch`. Cuarta instancia sumada por el refuter: `EditIngresoModal.tsx:69`. |

---

## Hallazgos CRITICAL

### C1 — GEO: el proxy de tiles público hace fail-open del allowlist de publicidad

**Archivo:** `gee-backend/app/domains/geo/router_core.py:472-522` + `tile_service.py:59-76`

El único chequeo de que un `layer_id` pertenece a `PUBLIC_PRODUCTION_LAYER_TYPES` (`_public_layer_for_rescale`) corre dentro de `if parsed_rescale_min is not None:`. Sin parámetros de rescale, el proxy forwarea cualquier UUID de `GeoLayer` al geo-worker, cuyo `get_tile` selecciona por id **sin filtro de tipo/publicidad**. Los GET de tiles están exentos del rate limiter (`middleware.py:25-27`).

**Impacto:** acceso anónimo y sin throttle a los 8 tipos de capas privadas del pipeline DEM (`slope`, `aspect`, `twi`, `flow_dir`, `flow_acc`, `drainage`, `profile_curvature`, `tpi`) + fuentes `manual`, cacheadas con `Cache-Control: public`. El test que claims cobertura (`test_geo_public_route_caps.py:437-457`) siempre envía rescale — el path default está sin testear.

**Fix:** correr el check de publicidad incondicionalmente antes de forwar (ya se paga el lookup indexado cuando hay rescale).

### C2 — NÚCLEO: tareas `gee.*` enrutan a la cola de mantenimiento, no a `geo`

**Archivo:** `gee-backend/app/core/celery_app.py:109-111`, `app/domains/geo/gee_tasks.py:122,204,303`, `app/shared/celery_outbox.py:447-452`

`task_routes = {"geo.*": {"queue": "geo"}}` es regex (`re.match`); `gee.*` no matchea. Verificado con el venv: `gee.analyze_flood`, `gee.supervised_classification` y `gee.sar_temporal` (exactamente las 3 `RECOVERABLE_LONG_TASKS` de 3 h) caen en la cola default `celery`, consumida por `consorcio-celery-worker` (documentado "sin GDAL", `--concurrency=2`, 512 MB), mientras `geo-worker` solo recibe el warming.

**Impacto:** dos análisis concurrentes ocupan ambos slots prefork hasta 3 h, privando de `outbox.publish_pending` (cadencia por minuto), `rainfall.process_outbox` y `geo.reconcile_stale_jobs` (la red de seguridad de jobs stale) → stall en cascada bajo exactamente la carga que geo-worker existe para absorber, más riesgo de OOM.

**Fix:** una línea — agregar `"gee.*": {"queue": "geo"}` a `task_routes` (o pasar `queue="geo"` en `_publish_claimed`); drenar los mensajes ya encolados.

### C3 — INFRA: bootstrap de clone fresco aborta (REDIS_PASSWORD requerido y sin provisioning)

**Archivos:** `docker-compose.yml:200,206`, `setup.sh:35`, `.env.example` (raíz)

Compose interpola `${REDIS_PASSWORD:?...}` en la carga de config del archivo completo; la clave no existe en `.env.example` raíz (solo en `.env.prod.example`/`.env.deploy.example`), y `setup.sh` crea los `.env` de backend/frontend pero nunca un `.env` raíz antes de `docker compose up -d postgres redis`. La promesa de `.env.example:16` ("bootea con defaults dev-safe si .env falta") es falsa.

**Impacto:** Quick Start del README y cualquier `docker compose up` abortan en máquina limpia. Registrado como conocido en `openspec/changes/archive/2026-08-07-lluvia-v2/apply-progress.md:38` y nunca arreglado.

**Fix:** default dev (`${REDIS_PASSWORD:-consorcio_dev_redis}`), agregar la clave a `.env.example`, y que `setup.sh` genere un `.env` raíz si no existe.

### C4 — FRONTEND: la capa del límite del consorcio en el explorador de imágenes es código muerto (regresión 84c0a9c4)

**Archivo:** `consorcio-web/src/components/admin/images/useImageExplorerMap.tsx:65-187`

La 84c0a9c4 (2026-10-14) movió `new maplibregl.Map()` detrás de `await bootMapLibreWorker()` en un IIFE async; `mapInstanceRef.current` se asigna (línea 106) solo tras el await. El efecto de zona (deps `[]`, líneas 145-187) corre sincrónico en el mismo flush de efectos pasivos, lee el ref en `null` y hace early-return — sin reintento (microtasks no interleavan con el flush; ninguna reconexión posterior). Antes de la 84c0a9c4 la asignación era síncrona y funcionaba.

**Impacto:** el polígono rojo del consorcio nunca se renderiza en `/admin/images` (siempre, no intermitente), y `zonaLayerIdRef` queda null → el ráster GEE pierde su `beforeId` de z-order. Confirmado por `rg`: ningún otro path consume `/geo/gee/layers/zona`.

**Fix:** mover el fetch de zona al IIFE de init tras crear el mapa (patrón `pendingTileUrlRef`) o exponer el mapa via state del que el efecto dependa.

### C5 — FRONTEND: mutaciones de finanzas fallan en silencio y admiten doble-submit

**Archivos:** `consorcio-web/src/components/admin/management/finanzas/useFinanzasController.ts:96-183`, `finanzas/components/{GastoFormModal.tsx:63, IngresoFormModal.tsx:71, EditGastoModal.tsx:37, EditIngresoModal.tsx:69}`

Los 4 handlers de mutación hacen catch con `logger.error` únicamente — sin toast, sin estado de error. Contraste interno: `handleDownloadSummaryPdf` (líneas 212-218) sí notifica en rojo. Los botones submit de los 4 modales no tienen `loading`/`disabled` (el único botón de finanzas con `loading=` es el PDF). Sin `useMutation` ni dedupe en `apiFetch`.

**Impacto:** un POST fallido (422/500) deja el modal abierto sin feedback alguno (pérdida de trabajo silenciosa); un POST lento permite un segundo click → registro financiero duplicado.

**Fix:** notificar errores (patrón ya existente en el mismo archivo), `loading` en los 4 submits, y migrar los paneles admin a React Query (raíz común con varios WARNING de FE).

---

## Hallazgos WARNING

### Seguridad (backend)

| ID | Hallazgo | Ubicación |
|---|---|---|
| SEG-1 | Upload de fotos de denuncias: sin tope de píxeles decodificados (10 MB JPEG ≈ 100-150 Mpx → 300-450 MB RGB × doble decode) y el trabajo de Pillow corre inline en el event loop. Amplificación de memoria DoS para cualquier ciudadano autenticado. El estándar ya existe: `geo_map_pdf_max_image_px` (40 Mpx). | `app/shared/storage.py:111,275`, `denuncias/router.py:242` |
| SEG-2 | Access token de 8 h; la revocación por epoch solo se alcanza con logout-all o force-revoke admin — logout común, reset de password y robo de header no tocan los JWT outstanding. El refresh rotativo (30 días, family replay-burn) es suficientemente fuerte como para bajar el access a 30-60 min. | `app/auth/dependencies.py:317` |

### Núcleo backend

| ID | Hallazgo | Ubicación |
|---|---|---|
| NUC-2 | `request_id` se bindea en el middleware más interno → logs de acceso, 429 y CSRF rechazado viajan sin correlation id (el contextvar del hijo no propaga al dispatch externo). | `app/main.py:209-210`, `app/core/middleware.py:236-241` |
| NUC-3 | `/ready` drena el LB completo si Redis cae al fallback in-process — el fallback fail-closed cuidadosamente construido jamás puede servir tráfico. Contradicción readiness vs fallback; una de las dos está muerta en la práctica. | `app/main.py:517-535`, `app/core/health.py:87-104` |
| NUC-4 | Healthcheck de prod depende de `HEALTHCHECK_HOST`/`API_BASE_URL` que el fail-fast de producción nunca valida → deploy prod sin `API_BASE_URL` = crash-loop de un contador sano. | `app/healthcheck.py:41-49`, `app/config.py:452` |
| NUC-5 | `async def get_denuncia_photo` usa sesión DB síncrona directo en el event loop (única excepción al patrón `run_in_threadpool` del repo) — stall por foto renderizada, mecanismo exacto del incidente de 21-161 s documentado. | `app/main.py:407-454` |

### Dominios de negocio

| ID | Hallazgo | Ubicación |
|---|---|---|
| DOM-1 | Presupuestos: el unique index existe SOLO en la migración (drift metadata/DB — el modelo no lo declara); el duplicate POST produce 500 crudo en vez de 409; no hay PATCH/DELETE para corregir líneas (`update_presupuesto` es código muerto sin endpoint). | `finanzas/models.py:82-94` vs `b5c2e8f3a194:129-134`; `finanzas/repository.py:188-204` |
| DOM-2 | `analisis_gee.usuario_id`: `ondelete=SET NULL` sobre `nullable=False` — la migration que arregló esta clase en 6 tablas hermanas omite esta. Latente (sin escritor vivo hoy), pero bloqueará el borrado de usuarios cuando el feature se cablee. | `monitoring/models.py:107-111`, `zz_users_fk_nullable.py` |
| DOM-3 | Reuniones: schema acepta datetimes naive (la UI hoy envía ISO-Z; clientes directos de API pueden mandar naive → corrimiento). Endurecer con `AwareDatetime` o validator. | `reuniones/schemas.py:19` |
| DOM-4 | Sugerencias: sin máquina de estados (setattr libre del estado), sin audit log — el único lifecycle sin VALID_TRANSITIONS del repo. | `monitoring/service.py:201-212` |
| DOM-5 | Enums inválidos → 500 (no 422) en 5 dominios: filtros GET (`denuncias?estado=foo`, `tramites?tipo=foo`, `settings/{clave}`) y writes (padron `estado`, tramites `tipo/prioridad`, capas `tipo/fuente`). | `denuncias/repository.py:55`, `tramites/repository.py:49-53`, `settings/repository.py:29-30`, `padron/schemas.py:86-89`, etc. |
| DOM-6 | Schemas de respuesta declaran `usuario_id` no-Optional sobre columnas `SET NULL` nullable — al borrarse el usuario referenciado, cada GET de esas entidades falla validación Pydantic → 500 permanente. | `denuncias/schemas.py:61`, `finanzas/schemas.py:55,116`, `tramites/schemas.py:75,94`, `reuniones/schemas.py:118`, `monitoring/schemas.py:155` |
| DOM-7 | Nulls explícitos en PATCH bypassean columnas NOT NULL → IntegrityError 500 en vez de 422 (cuit/nombre/apellido en padron, estado en denuncias, etc.). | `padron/repository.py:109-111`, `denuncias/repository.py:139-144` |
| DOM-8 | Denuncias soft-deleteadas (ARCO, Ley 25.326) siguen contadas en `get_stats` y `get_dashboard_stats` — sin filtro `deleted_at IS NULL`, contradictorio con todos los listados. | `denuncias/repository.py:175-195`, `monitoring/repository.py:226-230` |
| DOM-9 | `Ingreso.consorcista_id`: UUID plano sin FK ni check — un ingreso puede referenciar un consoncista inexistente para siempre. Única referencia cruzada del repo sin FK. | `finanzas/models.py:67-70` |
| DOM-10 | Settings: el write genérico `PUT /settings/key/{clave}` acepta `valor: Any` — escribir JSON basura en `mapa/imagen_principal` rompe con 500 permanente el endpoint público de imagen (la lectura tipada confía en el shape). | `settings/router.py:73-85` vs `:137-138` |
| DOM-11 | Settings: read-modify-write sin `FOR UPDATE` ni optimistic locking — dos admins concurrentes → lost update silencioso del blob JSONB completo; sin audit log de settings. | `settings/service.py:213-230` |
| DOM-12 | Trámites: `fecha_resolucion` usa `date.today()` server-local (contenedores UTC → entre 21:00-24:00 ART fecha del día siguiente) y no se limpia al reabrir (RECHAZADO→INGRESADO deja fecha de resolución con estado pendiente). | `tramites/service.py:107-111` |
| DOM-13 | `proxima-reunion`: filtra solo `estado==REVISADA` ordenado por `created_at desc` limit 20 — sin predicado de fecha futura ni orden por `fecha_reunion`. El endpoint devuelve datos directamente equivocados. | `monitoring/repository.py:146-154` |

### Geo

| ID | Hallazgo | Ubicación |
|---|---|---|
| GEO-2 | Escorrentía reporta `longitud_m` como conteo de pasos de celda (~factor 30x de error); la longitud real ya es computable del LineString que construye. Operator-only, sin consumidor frontend hoy. | `intelligence/calculations_hydrology_support.py:1217` |
| GEO-3 | Zonal stats: `nodata=-32768` hardcodeado pisa el nodata declarado de cada ráster — el fill 255 de `terrain_class` (uint8) cuenta como dato válido (255 se vuelve el máximo). | `zonal_stats.py:89`; `processing.py:461-464` |
| GEO-4 | `POST /public/map/elevation-profile`: geometry dict sin tope de body — los caps de compute se aplican solo tras parse+reproject completos; cache Postgres por traza única con prune solo por edad. El patrón `enforce_body_limit` de ficha es el precedente in-repo. | `public_elevation.py:22-45`; `router_ficha.py:154-194` |
| GEO-5 | Descarga DEM: `.tmp.tif` de tamaño completo queda huérfano si el worker muere a mitad (unlink solo en el path de éxito; sin sweep en ningún lado) → agotamiento de disco del geo-worker con crashes repetidos. | `processing_wbt_support.py:233-244` |

### Conocimiento / RAG

| ID | Hallazgo | Ubicación |
|---|---|---|
| RAG-1 | El kernel de normas sirve `texto` completo de unidades `privado` sin filtro ni etiqueta (`UnidadNorma` no lleva `clasificacion`), y el espejo MCP lo pipetea a clientes LLM arbitrarios — la compuerta `CLASIFICACIONES_ENVIABLES` existe solo en el path de generación. El sharp edge es MCP (auth = posesión de `DATABASE_URL`). | `normas.py:90-137`, `schemas.py:434-453`, `scripts/rag_normas_mcp.py:98-123` |
| RAG-2 | El artefacto de la barra no tiene binding de integridad: un hand-edit internamente consistente (`estado: superada` + figuras) pasa `--exigir-barra` Y flapea el ranking en serving sobre figuras fabricadas. La disciplina `regla_sha256` de clasificación es el modelo a copiar. | `eval/barra_sin_gpu.py:144-180,384-395` |
| RAG-3 | La ingesta nunca rota `rag_corpus.activo` (ningún path desactiva la fila anterior); "exactamente una activa" es checklist humano. Re-ingestar un SHA viejo como rollback es un no-op silencioso para serving (`ORDER BY ingested_at DESC`) con exit 0. | `repository.py:478-489,965-989`; runbook:949-957 |
| RAG-4 | `--verify-unchanged` hashea solo `texto`; `texto_indexado` (la superficie real de búsqueda) puede reescribirse bajo el mismo SHA vía cambio de parser/enriquecimiento con `divergencias: []` y exit 0 — exactamente la clase de rewrite silencioso que el flag claims cerrar. | `scripts/rag_ingest.py:204-221`; `repository.py:659-671` |
| RAG-5 | Un ítem venenoso wedgea el mailbox completo: excepción en el ítem más viejo → worker muere → systemd reinicia en 10 s → reclama el mismo ítem. Crash-loop sin progreso ni dead-letter (claim sin contador de intentos). Blast radius, no state leak. | `scripts/rag_worker.py:197-200`; `buzon.py:161-179` |

### Frontend

| ID | Hallazgo | Ubicación |
|---|---|---|
| FE-3 | La política "nunca reintentar 4xx" se rompe silenciosamente para errores con `detail` string: el `Error` lanzado no lleva status → 403/404/409 se reintentan 3x con backoff (~7 s de delay, 4x carga). `QueryError` tiene `statusCode` pero nunca se lanza — el wiring se diseñó y no se conectó. | `src/lib/api/core.ts:294`, `src/lib/queryRetry.ts:1-15` |
| FE-4 | Los `detail` array de 422 de FastAPI nunca se superfician — `getApiErrorMessage` solo maneja string → mensajes de validación por campo descartados app-wide (combinado con C5: cero feedback en finanzas/trámites). | `src/lib/api/core.ts:189-205` |
| FE-5 | Guards de doble-submit ausentes en TramitesPanel y ReunionCreateModal (el formulario público de denuncias y LoginForm lo hacen bien — el patrón existe). | `TramitesPanel.tsx:133-152`, `ReunionCreateModal.tsx:131` |
| FE-6 | TramitesPanel: fallos de fetch/create se renderizan como estado vacío — una carga fallida es visualmente idéntica a "no hay trámites". | `TramitesPanel.tsx:91-93,104-106,149-151` |

### Infra / ETL / CI

| ID | Hallazgo | Ubicación |
|---|---|---|
| INF-2 | El overlay pgvector buildea sobre `pgrouting:16-3.4-3.6.1` (sin digest pin) mientras el compose base pinea `16-3.5-3.8@sha256` — `make rag-db` baja binarios PostGIS 3.4 sobre un volumen inicializado por 3.5 (downgrade sin camino soportado). El comentario del Dockerfile afirma lo contrario dos veces. | `docker/postgres/Dockerfile:3,19,24` vs `docker-compose.yml:6` |
| INF-3 | Targets `docker-monitoring`/`docker-scheduler` referencian profiles que no existen (compose ignora profiles desconocidos y levanta el stack default) + imprimen URL de Flower que no está definida en ningún lado. | `Makefile:210-219` |
| INF-4 | `make db-upgrade`/`db-downgrade` convierten fallos reales de migración en éxito (`2>/dev/null || echo "no migrations"`, exit 0) — gate silent-pass; el deploy.yml hace lo contrario por esa razón. | `Makefile:228-236` |
| INF-5 | 83 MB de blobs trackeados en HEAD (`gee/red_vial_provincial.kml` 65.5 MB, `suelos_cu.geojson` 18.3 MB) + ~60 MB de historia muerta (reportes Stryker committed-then-deleted, sandboxes `.stryker-tmp`). Todo clone los paga. | — |
| INF-6 | `nginx/nginx.conf` huérfano: ninguna compose lo monta, el frontend tiene su nginx embebido, el edge prod es Caddy — describe una topología que ya no existe (CSP con unpkg/mapbox, sin TLS). | `nginx/nginx.conf` |

---

## Sugerencias y mejoras (no defectos)

- **SEG-H (hardening):** auth app-level en `/metrics` (hoy solo protegido por el 404 del edge en Caddy); achicar el rate-limit-exempt de `GET /geo/basins/**` (cubre `approved-zones/history` y `current/export-pdf` que filtran nombres de operadores); retirar el deprecated `GET /public/denuncias/{id}/status`; completar `.env.example` (`ENABLE_DOCS`, `RATE_LIMIT_DISABLED`, `AUTH_RATE_LIMIT_*`, `UPLOADS_ROOT`, SMTP/Sentry/BetterStack); tope de body en el POST público de elevation-profile (duplicado del WARNING GEO-4).
- **GEO-S:** la publicación de canales hace fail-open cuando la tabla está vacía (default `publicado=TRUE` para TODO antes de que alguien abra el panel staff — "no configurado" y "todo publicado" son indistinguibles); la comparación pública degrada all-or-nothing si falla un solo lado de la dupla.
- **RAG-S:** un YAML corrupto de la barra 500-a la ruta de normas en vez de degradar a unranked (`superada_para` solo atrapa `BarraInvalida|BarraNoSuperada`); `--verify-unchanged` se dropea silenciosamente en el dry-run sin DB; el dedup de follows de cita se computa contra la página pre-corte; `_textos_privados` valida `para`/`corpus_sha` solo si existen; el motivo `truncado_dos_veces` puede ser la tercera truncación.
- **FE-S:** `tile_url` sigue sin validación de origen en el explorador (hallazgo 3 de la auditoría de julio — el path de fotos sí tiene validador dedicado, inconsistente); no hay ErrorBoundary app-level (solo el mapa está wrappeado; `SentryErrorBoundary` exportado y jamás usado); código muerto (AppProvider.tsx duplicado y driftado, ~10 hooks de query sin uso).
- **INF-S:** `Dockerfile.trainer` es la única imagen sin digest pin y fuera del image-gate (acotado: profile training, nunca publicada); los endpoints públicos de Martin publican 5 vistas sin `max_feature_count` explícito (parcelas poligonales en hostname público — verificar z≤8).
- **Sugerencia estructural (transversal):** los paneles admin bypass React Query (fetch manual + useState en finanzas/reuniones/trámites/sugerencias/reportes) — es la raíz común de C5, FE-4, FE-5, FE-6. Migrarlos a `useMutation` arregla los cuatro de una vez.

---

## Code smells seleccionados

1. **God modules en geo**: 12 archivos >700 líneas (`rainfall/repository.py` 1445, `ficha_service.py` 1416, `rainfall/compute.py` 1239, `rainfall/tasks.py` 1221).
2. **main.py hace laburo de dominio**: ~170 líneas de filesystem/serving de fotos de denuncias viven en el bootstrap.
3. **Boilerplate copiado**: el `get_all` filter→count→paginate repetido 8 veces; los shims `_require_operator` repetidos en 6 routers — pertenecen a `app/shared/`.
4. **CUIT normalizado dos veces con reglas divergentes** (schema valida dígito verificador AFIP, service no; mismo nombre `_normalize_cuit`).
5. **Árbol de migraciones legacy paralelo**: `gee-backend/migrations/` (16 SQL crudos) convive con el Alembic real — hazard para el operador de la box.
6. **Pool sizing por sniffing de `sys.argv`** (`db/session.py:31-36`) — un wrapper que renombre argv duplica la carga de conexiones.
7. **4 copias del state machine de cliente Redis** (rate limiter, JSONCache, BytesCache, limiters de ficha/PDF).
8. **`routeTree.gen.tsx` mantenido a mano** pese al sufijo `.gen` — un codegen se traga las ediciones manuales.
9. **Defaults hardcoded del operador**: `etl_canales/main.py:50-51` (`/home/javier/Descargas/...`) y `deploy_b3p.py:39-44` (IP/SSH/key de prod en el repo).
10. **`make redis-cli` muere con NOAUTH** (redis siempre arranca con `--requirepass`, el target no pasa `-a`).

---

## Comparación con la auditoría 2026-07-09

| Hallazgo julio | Estado |
|---|---|
| 1) Escenas históricas pisadas por el fetch del día | **FIXED** — AbortController + suppression refs (`useImageExplorerController.tsx:150-159`), con comentarios que citan la auditoría; backend con floors. |
| 2) Persistencia de imagen lossy | **FIXED** — `mode: Literal[...]` en schema, backend rechaza modes con 422, persistencia lleva `days_buffer`/`max_cloud`/`mode`; round-trip lossless. |
| 3) Validación laxa de `tile_url` | **PARCIAL** — backend endurecido; el frontend sigue pasando `tile_url` sin check de origen (FE-S). |
| 4) Sin cancelación de requests | **FIXED** — AbortController + requestId en el explorador. |

---

## Lo que está sólido (verificado)

- **Auth/authorization backend**: superficie de roles explícita en cada router, `/mine`-scope estricto para ciudadanos, sin IDOR encontrado (fotos con ownership 404-colapsado); SQLi efectivamente cero (bound params en todo `text()`, incluida la query pgvector); refresh rotativo hashed-at-rest con family replay-burn; boot fail-fast que rechaza secrets placeholder, CORS wildcard y debug en prod; supply chain con hash-lock y pip-audit pins.
- **Sesiones/transacciones y async**: disciplina de commit/rollback limpia en todo lo muestreado; timeouts de statement/idle-in-transaction en connect; PgBouncer con NullPool + randomización de prepared statements; offload sistemático de bloqueos GEE vía `run_in_threadpool` con la razón documentada en cada sitio (una sola excepción: NUC-5).
- **Geo lifecycle**: outbox durable con CAS-fencing, heartbeat 60 s y reconciliación beat-programada; init GEE con backoff latch + detección de rotación de credenciales; longitud geodésica `ST_Length(geom::geography)` pineada por test.
- **RAG conocimiento**: topología de gates genuinamente pre-transaccional; enforcement de citas estructural (byte-membership contra el payload post-exclusión, `CompuertaEludida` haciendo inconstructibles los paths off-path); determinismo ejemplar (sorts secundarios en cada leg, `math.fsum`, RRF sin blending de scores, `hnsw.ef_search` pineado).
- **CI/infra prod**: actions pineadas por SHA, tokens read-only, publish con digest-verify + webhook replay-protected, agregadores fail-closed; compose prod textbook (cap_drop ALL, no-new-privileges, read_only+tmpfs, secrets `:?`); backup cifrado con sidecar sha256 y drill de restore que rechaza DB viva; separación de privilegios Martin/app exemplary; chain Alembic verificada íntegra para el `upgrade head` one-shot planeado (95 revisiones, single head, sin el trap de enum-in-transaction).
- **ETLs**: PII de escuelas strip completo con whitelist reforzada en la frontera de emisión; longitudes geodésicas correctas (pyproj WGS84); gates de input faltante con exit 3.

---

## Ledger resumen

| Severidad | Cantidad | IDs |
|---|---|---|
| CRITICAL (confirmados) | 5 | GEO-1, NUC-1, INF-1, FE-1, FE-2 |
| CRITICAL (refutados, → WARNING) | 3 | DOM-1, DOM-2 (latente), DOM-3 (hardening) |
| WARNING | 37 | SEG-1..2, NUC-2..5, DOM-1..13, GEO-2..5, RAG-1..5, FE-3..6, INF-2..6 |
| SUGGESTIÓN / hardening | ~21 | ver §Sugerencias |
| Code smells | 10+ | ver §Code smells |

*Verificado todo en HEAD `ce951fd0`. Ningún archivo fue modificado durante la auditoría.*
