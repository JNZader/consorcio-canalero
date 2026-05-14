# Cold start del backend — diagnóstico y plan de fix

**Fecha:** 2026-05-14
**Síntoma reportado:** El mapa (2D y 3D) tarda 10-12 segundos en cargar tras un hard refresh; a veces no termina de cargar.
**Status:** diagnóstico cerrado, fix no aplicado.

## TL;DR

El cold start no viene del frontend ni del 3D. Hay **cuatro causas reales en el backend**, en orden de impacto:

1. **`ee.Initialize()` sin lock + bloqueante en el event loop** → 25 requests concurrentes inicializan GEE en paralelo, todos bloqueados 5-10s.
2. **`uvicorn --reload` en producción** → fuerza 1 solo worker; cualquier escritura a `/app/app` (bind-mount desde el host) gatilla restart y pierde el cache de GEE init.
3. **Swap usage en Hetzner (1.4 GiB ocupado)** → primer request tras idle paga el costo de paginar de disco a RAM.
4. **`Access-Control-Max-Age: 600`** (10 min) → preflights re-disparados con frecuencia, cada uno ~800ms tibio / 8s frío.

Lo que el commit `e3fdff2` (defaults del 3D) intentó arreglar (GPU/render) **no es el cuello de botella**.

## Evidencia

### Comparación de tiempos: 1er refresh (frío) vs 2do refresh (tibio)

| Endpoint | 1er refresh | 2do refresh | Speedup |
|---|---|---|---|
| `OPTIONS /api/v2/public/settings/branding` (CORS preflight) | 8713 ms | 860 ms | 10× |
| `GET /api/v2/public/settings/branding` | 3094 ms | 779 ms | 4× |
| `GET /api/v2/geo/layers/public?fuente=dem_pipeline` | 11473 ms | 1012 ms | 11× |
| `GET /api/v2/geo/gee/layers/caminos/coloreados` | 10648 ms | 584 ms | 18× |
| `GET /api/v2/geo/gee/layers/zona` | 10622 ms | 577 ms | 18× |
| `GET /api/v2/geo/basins?tolerance=0.001&limit=500` | 11429 ms | 1301 ms | 9× |
| `GET /api/v2/geo/basins/approved-zones/current` | 11428 ms | 1299 ms | 9× |
| `GET /api/v2/geo/basins/approved-zones/history` | 11168 ms | 1036 ms | 11× |

El 1er refresh también muestra una catarata de XHRs cancelados (`NS_BINDING_ABORTED` en cliente, `H3_REQUEST_CANCELLED` en Caddy upstream) en el mismo milisegundo — síntoma de doble-mount de React + frontend que aborta cuando el backend no responde.

### Logs del backend muestran que el procesamiento es rápido

Pegando un refresh tibio en el server:
```
GET /api/v2/geo/gee/layers/caminos/coloreados | 200 | 61.72 ms
GET /api/v2/geo/gee/layers/zona               | 200 | 62.34 ms
GET /api/v2/geo/basins/approved-zones/current | 200 | 120.15 ms
GET /api/v2/geo/basins                        | 200 | 160.35 ms
GET /api/v2/geo/basins/approved-zones/history | 200 | 169.31 ms
GET /api/v2/geo/layers/public                 | 200 | 165.93 ms
```

Backend → 60-200 ms; cliente vio 10 000 ms. La diferencia se la come la inicialización de GEE bloqueante + serialización de workers + handshake TLS de Caddy.

### Auditoría del server Hetzner (157.180.29.238)

**Estado de contenedores:**
- `consorcio-backend` — Up 8 days (healthy), corriendo `uvicorn --reload` con **1 solo worker**.
- `consorcio-postgres` — Up 8 days (healthy).
- `consorcio-redis` — Up 2 weeks (healthy).
- `consorcio-martin` — Up 8 days (**unhealthy**) — el healthcheck apunta a `localhost:3000` pero el contenedor escucha solo en su IP de red Docker; sirve tráfico OK vía `consorcio-network`, el healthcheck está mal escrito (FailingStreak: 70 038).
- `consorcio-worker` — Up 2 weeks (healthy).
- `caddy` — Up 3 days (healthy).

**Server:** Ubuntu 22, kernel 6.8, 7.6 GiB RAM, **1.4 GiB swap usado**, load promedio 0.75. Uptime 58 días.

**Compose en producción (`~/stacks/consorcio/docker-compose.yml`):**
```yaml
backend:
  build:
    target: development         # ← Imagen DEV en PROD
  command: >
    uvicorn app.main:app --host 0.0.0.0 --port 8000
    --reload                    # ← Auto-reload en PROD
    --reload-dir /app/app
  volumes:
    - ./gee-backend/app:/app/app:ro   # ← código bind-mounted desde host
```

El `Dockerfile` ya tiene un target `production` limpio (sin gcc, non-root user, sin `--reload`), pero el compose no lo usa.

**Pool de DB (`app/db/session.py`):** `pool_size=5`, `max_overflow=10` → máximo 15 conexiones. Razonable, no es el cuello.

**CORS (`app/main.py`):** `max_age=600` (10 minutos). El browser respeta este valor, pero 10 min es bajo: cualquier navegación tras 10 min de idle vuelve a disparar preflights.

**GEE init (`app/domains/geo/gee_service.py`):**
```python
_gee_initialized = False  # módulo-level, sin lock

def _ensure_initialized() -> None:
    global _gee_initialized, _gee_init_error
    if _gee_initialized:
        return
    # ...
    ee.Initialize(credentials, project=settings.gee_project_id)  # BLOQUEANTE 2-5s
    _gee_initialized = True
```
Sin `threading.Lock` ni `asyncio.Lock`. Bajo concurrencia, los 25 requests entran al init al mismo tiempo.

## Plan de fix

### Fase 1 — quick wins (máximo impacto, mínimo riesgo)

| # | Cambio | Dónde | Impacto |
|---|--------|-------|---------|
| 1.1 | Agregar `asyncio.Lock` (o `threading.Lock` si hay paths sync) alrededor de `_ensure_initialized()` y mover `ee.Initialize()` a un `run_in_executor` para no bloquear el event loop. | `gee-backend/app/domains/geo/gee_service.py` | Mata el cold start de 10s. |
| 1.2 | Pre-inicializar GEE en el `startup` event de FastAPI (que el worker arranque ya autenticado). | `gee-backend/app/main.py` | Hace el cold start = arranque del worker, no del primer request. |
| 1.3 | Subir `max_age` de CORS de 600 a 86400 (24h). | `gee-backend/app/main.py:CORSMiddleware` | Elimina preflights repetidos durante el día. |
| 1.4 | Frontend: TanStack Query con `staleTime: 5 * 60 * 1000` para `branding`, `basins`, `layers/public`. | `consorcio-web/src/lib/...` (donde se definan las queries) | Misma sesión no refetch repetida. |
| 1.5 | Cron de warmup en Hetzner: `curl https://cc10demayo-api.javierzader.com/api/v2/public/settings/branding` cada 4 min. | crontab del server | Mantiene worker + DB pool + GEE caliente. |

### Fase 2 — fixes estructurales (medio esfuerzo)

| # | Cambio | Dónde | Impacto |
|---|--------|-------|---------|
| 2.1 | Migrar el compose de prod a `target: production`, sacar `--reload`, sacar el bind-mount de código (que el código vaya dentro de la imagen). | `~/stacks/consorcio/docker-compose.yml` en Hetzner. | Habilita múltiples workers, deja de bindear código. |
| 2.2 | Configurar uvicorn (o mejor, gunicorn como process manager) con `--workers 4` (CX33 tiene 4 vCPU según pricing). | comando del backend en compose. | Elimina el bottleneck del worker único bajo concurrencia. |
| 2.3 | Arreglar el healthcheck de `consorcio-martin` (apunta a `localhost:3000` pero el contenedor no escucha ahí; usar `wget -O- http://martin:3000/health` desde la red `consorcio-network` o cambiar a `127.0.0.1` si está bindeado). | compose Martin. | Saca el `unhealthy` confuso. |
| 2.4 | Revisar swap en Hetzner: 1.4 GiB activo sobre 7.6 GiB de RAM física sugiere que el server está en el límite. Identificar qué stacks consumen más y considerar `mem_limit` por stack. | Hetzner. | Reduce paginación a disco. |

### Fase 3 — optimizaciones (mayor esfuerzo, opcionales)

| # | Cambio | Impacto |
|---|--------|---------|
| 3.1 | Materialized view para `basins?tolerance=0.001&limit=500` con geometrías pre-simplificadas. | Endpoint de 160ms → <30ms. |
| 3.2 | Cache de respuestas de GEE (`caminos/coloreados`, `zona`) con TTL de 1 hora en Redis. | Saca ~60ms de cada hit + protege contra rate limit de GEE. |
| 3.3 | Cache layer en Caddy con `Cache-Control` headers + reverse_proxy con `transport.tls.client_session_ticket_disabled false` para acelerar handshakes. | Reduce TLS overhead en clientes recurrentes. |

## Lección — qué nos llevamos

- El commit `e3fdff2` intentó optimizar **GPU/rendering** (defaults 3D lightweight). El cuello de botella real era **I/O backend bloqueante**. Dos problemas distintos, fix mal apuntado.
- **Medir antes de optimizar.** Abrir DevTools → Network tab antes de tocar código. Si lo hacíamos al principio, no perdíamos el commit en el lugar equivocado.
- **`uvicorn --reload` y bind-mounts de código en producción** son anti-patrones que se filtraron del setup de desarrollo. Hay que separar `docker-compose.yml` (dev) de `docker-compose.prod.yml` (prod) y asegurarse que el server use el correcto.

## Referencias

- Backend code:
  - `gee-backend/app/domains/geo/gee_service.py:43-145` — init sin lock
  - `gee-backend/app/db/session.py` — pool config
  - `gee-backend/app/main.py` — CORS config
- Server config:
  - `~/stacks/consorcio/docker-compose.yml` en Hetzner — uvicorn command, build target
  - `~/caddy/Caddyfile` — proxy rules
- Commits relacionados:
  - `e3fdff2` — feat(map): improve 3d defaults and project docs (fix mal apuntado)
  - `b58fce8` — docs: clarify scope of e3fdff2 (mixed-concerns commit)
