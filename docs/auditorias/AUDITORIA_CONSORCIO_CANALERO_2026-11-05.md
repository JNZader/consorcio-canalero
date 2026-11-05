# Auditoría exhaustiva #2 — Consorcio Canalero

Fecha: 2026-11-05
HEAD analizado: `12acabc2` (`origin/main`, post-#657)
Contexto del ciclo: **318 commits** entraron desde la primera auditoría exhaustiva (2026-10-23, `ce951fd0`) — la wave map2d #641–648, el plan DS/mobile ejecutado (#649–657: suite visual, tokens, primitivas, denuncia mobile, estilos, mapa mobile, admin mobile, 3D/PWA/404/bundle) y las olas de dependencias. Todo ese código pasó review normal pero nunca un pase adversarial.
Método: 7 auditorías paralelas por área + refutación adversarial de los 4 candidatos CRITICAL + verificación de los 13 DOM de octubre + fusión de una auditoría visual externa (Grok, mismo HEAD, validada contra código). Sin modificar código.

---

## Resumen ejecutivo

**3 CRITICAL confirmados, ~25 WARNING, ~15 sugerencias.** Las dos áreas que no cambiaron desde octubre (RAG, y el grueso de seguridad) salieron limpias — los CRITICALs se concentran exactamente en el código nuevo de la wave #637–657 y en un endpoint público preexistente que la nueva UI pasó a golpear:

1. **N1 — Los filtros de búsqueda del admin son placebo**: el FE manda `search`/`categoria`/`tipo` que el backend descarta silenciosamente; el server devuelve la página sin filtrar y el FE re-filtra solo la página visible. Denuncias cuyo match vive en la página 2+: invisibles para el operador.
2. **R1-001 — Endpoints GEE públicos sin singleflight**: exentos de rate-limit y sin auth, disparan cómputos de 30s–2min sobre el executor compartido de 6 threads; herd en expiración de TTL + recompute total si Redis cae (cache fail-open).
3. **F1 — Doble-submit del "Reintentar" offline**: el botón del toast vive fuera del overlay, sin guard de re-entrancy ni idempotencia — cada tap dispara una denuncia duplicada que el backend acepta.

**La tesis de re-auditar post-sprint se valida**: review normal + suite visual no atraparon ninguno de los tres.

---

## Refutaciones (verificación adversarial)

| Candidato | Veredicto | Razón decisiva |
|---|---|---|
| N1 filtros placebo | **CONFIRMADO** | Firmas de router sin `search`/`tipo`; FE los envía; re-filtro client-side solo de la página actual; no existe endpoint alternativo |
| R1-001 GEE singleflight | **CONFIRMADO CON MATIZ** | Sin lock, exentos, cache no-op en fallo de Redis, entry sin auth — todo se sostiene. Matices que no lo salvan: GEE-init corre en el loop bajo lock (no en el executor); el key-spray está cerrado por rechazo de query-params — la exposición real es TTL-herd + Redis-outage |
| F1 doble-submit offline | **CONFIRMADO** | Cero guard (enviando jamás se lee); toast en el portal (z 10002 > overlay 10001) con autoClose=false; SubmitButton sin loading; el backend count-then-insert deja pasar ambos POSTs concurrentes |
| N2 enum-filters 500 | **CONFIRMADO CON MATIZ → WARNING** | Mecanismo real (raw string → Enum column → LookupError → 500 en 5 dominios) pero todos los endpoints son operator-gated y el FE manda valores válidos; el alias `status` agrega un nombre, no una clase nueva |

---

## CRITICAL confirmados

### N1 — Búsqueda/filtros admin placebo (DOMINIOS)

**Archivos:** `denuncias/router.py:375-396`, `monitoring/router.py:88-106`, `reports.ts:36-47`, `SugerenciasPanel.tsx:128-132,247-249`, `ReportsPanel.tsx:184-186`

`GET /denuncias` acepta solo `estado/status/cuenca`; `GET /sugerencias` solo `estado/categoria`. El FE (#637) envía `search`+`categoria` (denuncias) y `tipo`+`search` (sugerencias) — FastAPI los descarta en silencio, el server devuelve la página SIN filtrar con `total/pages` del conjunto completo, y el FE re-filtra solo los rows de la página actual. Resultado: buscar cualquier término cuyos matches vivan en página 2+ devuelve "no hay resultados" — falso. El commit que decía "envía query params al backend" cableó solo el emisor. (Los filtros `estado/status` SÍ funcionan server-side.)

**Fix:** implementar `search`/`tipo`/`categoria` server-side (ILIKE estilo padrón) o rechazar params desconocidos; eliminar el re-filtro client-side que fabrica la ilusión.

### R1-001 — Singleflight ausente en cómputos GEE públicos (CORE)

**Archivos:** `router_gee_support.py:27-42,313-396,458-505`, `public_map.py:310,341,382-385`, `middleware.py:159-170`, `cache.py:93-138`

Los tres endpoints de composición (mensual/anual/imagen satelital) hacen `cache.get → miss → asyncio.to_thread(GEE 30s-2min) → cache.set` sin lock por clave. Entrada pública: `/api/v2/public/map/gee/current-image|current-comparison` — sin auth y en la lista de exención del rate limiter. Tres modos de falla: (a) **herd de expiración de TTL** — todos los primeros paints concurrentes tras la hora computan composites completos en paralelo; (b) **outage de Redis** — el cache degrada a no-op por diseño → cada request recomputa; (c) el `gather` de la comparación lo duplica. Todo cae sobre el executor default compartido (`min(32, cpu+4)` = **6 threads en la box de 2 vCPU**) que también sirve las lecturas de fotos — galería y mapa se degradan juntos. El patrón correcto ya existe en el propio repo: `health.py:39-43,222-247` (executor dedicado de 1 worker + lock + double-check).

**Fix:** singleflight por clave + executor/semáforo dedicado GEE, espejando health.py.

### F1 — "Reintentar" offline sin re-entrancy (FRONTEND)

**Archivos:** `useReportFormSubmission.ts:122-231`, `FormularioReporte.tsx:65-80,167,252-256`, `ReportFormFields.tsx:134-140`, `denuncias/service.py:75-84`

El callback de submit jamás lee `enviando` (solo `setEnviando`); el toast offline ("Reintentar", `autoClose: false`) renderiza en el portal de notificaciones — z-index 10002 por encima del overlay 10001 — fuera del Paper que el LoadingOverlay cubre; el botón del toast es un `onClick` pelado y SubmitButton no recibe `loading`. En el escenario exacto que la feature ataca (red floja, POST colgado 10-60s), cada tap de Reintentar dispara un POST concurrente; el limitador backend (count-then-insert sobre filas commiteadas) deja pasar ambos. Denuncias duplicadas en la cola del operador.

**Fix:** guard con ref al entry del callback + `loading={enviando}` en SubmitButton + suprimir el retry del toast mientras `enviando`. (F2, WARNING, pide además idempotency-key client-side para el caso respuesta-perdida.)

---

## WARNING por área (selección)

**Core:** R1-002 branding cache derrotable por race de threads (invalidación pisada por un reader concurrente — 3er auditor que converge en branding; además devuelve el dict vivo por referencia); R1-003 clientes Redis sin socket_timeout (un hang silencioso cuelga el rate limiting — conecta con NUC-3); R1-004 flood-tiles devuelven 200 con body de error (invisible a monitoreo); R1-005 warming task SIGKILLeado a los 600s (7×240s secuencial); R1-006 probe GEE colgado bloquea shutdown del contenedor.

**Dominios (nuevos):** N3 `completado` de agenda inalcanzable (schema muerto, el PDF imprime "No" por siempre); N4 import padrón envenena `seen_cuits` con filas fallidas (CUIT válido posterior salta como duplicado — pérdida silenciosa); N5 TOCTOU CUIT → 500 no 409; N6 ARCO-deleted sigue quemando la cuota 5/24h.

**Frontend:** F2 retry sin idempotency-key (respuesta perdida = duplicada); F3 search padrón sin URL-encode (`&`/`#` rompen la query); F4 virtualización: teclado no alcanza rows fuera de ventana (focus escapa del listado); F5 drag del dock sin `pointercancel` (ghost-resize en touch).

**Geo:** superficie JRC/S2 huérfana (#637 borró el FE, quedaron 4 endpoints vivos consumiendo quota GEE sin consumidor); banda de cobertura de solera jamás renderiza (diferencia ~0-3m ploteada en eje absoluto ~600m); dedupe de cruces a 20m colapsa labels distintos, no solo Parcela.

**Infra:** INF-1 `scripts/tests/` (locks del deploy-script + contrato IDECOR) corre en CERO workflows; INF-2 `GRANT TO PUBLIC` en vistas IDECOR contradiciendo el provision least-privilege; INF-3 `SPA_ROUTES` copia manual sin guardia (doble-confirmado con F6-FE).

**Seguridad:** limpia — 0 hallazgos; 5 hardening (cuota GEE por usuario en time-layers, idempotency-key, validación https de logo_url, tile-proxy si las capas temporales van al mapa público, cache-control selectivo).

**RAG:** limpia — byte-stable; 1 sugerencia (DB caída en boot del worker toma el path de traceback, no el de rechazo limpio).

---

## Auditoría visual externa (Grok, mismo HEAD) — fusionada

Validada contra código (credibilidad alta; 2 verificaciones propias ganadas: precache y banner). Entra al backlog unificado:

- **Alta:** CTAs principales casi ilegibles (texto oscuro sobre verde ~#0a3b2b, ambos temas) — PR "Río limpio" ya en curso.
- **Media:** banner PWA `fixed top` tapando el nav en /, /mapa, /participacion (verificado `PwaInstallPrompt.tsx:69-70`).
- **P1:** precache SW con 77 entradas/2.5MB incluyendo worker MapLibre 519KB (verificado: globIgnores no cubre chunks del mapa); paridad sugerencias vs denuncia; dock 44px; sheets sin semántica dialog; ConfirmDialog en POI.
- **P2:** home "Canales existentes relevados" mostrando "—"; `/reports` 200 no 301 para crawlers; 46 `c="gray.6"`; Leaflet CSS muerto.

---

## Verificación de los 13 DOM de octubre

12 siguen abiertos (1 parcial: DOM-3 tz, mitigado por el FE ISO-Z; DOM-5 parcialmente fixeado; DOM-8 parcial: público filtrado, operador/dashboard no). Destacados del estado actual: DOM-1 el fix quedó **medio construido y abandonado** (`update_presupuesto` + schema muertos, sin ruta); DOM-2 "peor que latente" (el DELETE de usuario con análisis falla); DOM-10 ahora **tumba el endpoint público de branding** (`BrandingResponse(**get_branding())`); DOM-13 la query sigue ignorando `fecha_reunion` y las agendadas nunca aparecen.

## Conocimiento/RAG (verificación de octubre)

Los 5 fixes intactos byte-a-byte; los 6 known-opens confirmados sin regresar; 3 ángulos profundos nuevos (boot-crash, privacidad, bypass del digest) todos negativos.

---

## Lo que está sólido (verificado)

- **La wave #650–657 es de calidad alta**: la suite visual es un gate real (permissions contenidos, baselines 8.3MB, sin bloat), el outbox sigue siendo textbook, la cadena Alembic (96 revs, head única) camina, el orden de middleware intacto, la superficie ff19a9e8 (fotos/ARCO de denuncias) con razonamiento de durabilidad poco común.
- **El redesign móvil/DS no rompió lo que tocó**: #655 (split CSS) sin regresiones de especificidad, #657 (bundle diet) con claims que se sostienen bajo gate real (`mantineCssSurface.test.ts`).
- **Seguridad y RAG**: cero hallazgos nuevos con impacto — las olas de octubre aguantaron 318 commits.

---

## Ledger resumen

| Severidad | Cantidad | IDs clave |
|---|---|---|
| CRITICAL (confirmados) | 3 | N1, R1-001, F1 |
| CRITICAL (refutado/degradado) | 1 | N2 → WARNING |
| WARNING | ~25 | R1-002..006, N3..N6, F2..F5, geo×3, INF-1..3, seguridad-hardening aparte |
| SUGGESTIÓN | ~15 | incl. RAG boot-taxonomy, FE focus-trap gaps, DOM residuals |
| DOM octubre abiertos | 12/13 | wave-3 sigue pendiente |
| RAG octubre abiertos | 6/6 | sugerencias, sin regresión |

**Orden de fix recomendado:** N1 (los operadores están ciegos AHORA) → F1 (duplicados en producción) → R1-001 (quota GEE + starvation bajo carga) → branding (3 auditors convergieron: lock + copy + shared-cache) → resto de WARNINGs en batches por área. Los 12 DOM de octubre siguen siendo la wave-3 post-ceremonia según lo acordado.

*Verificado en 12acabc2. Sin modificaciones de código durante la auditoría.*
