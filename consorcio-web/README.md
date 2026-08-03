# Consorcio Canalero 10 de Mayo · Web

Frontend del sistema de gestión y monitoreo del **Consorcio Canalero 10 de Mayo** — departamento Unión, Córdoba, Argentina.

Aplicación React 19 con visor cartográfico interactivo, panel de administración y formularios públicos de participación ciudadana.

---

## Índice

- [Stack tecnológico](#stack-tecnológico)
- [Funcionalidades](#funcionalidades)
- [Rutas](#rutas)
- [Estructura del proyecto](#estructura-del-proyecto)
- [Instalación](#instalación)
- [Comandos](#comandos)
- [Configuración](#configuración)
- [Capas estáticas servidas](#capas-estáticas-servidas)
- [Exportación de datos](#exportación-de-datos)
- [Deploy a Cloudflare Pages](#deploy-a-cloudflare-pages)
- [Integración con backend](#integración-con-backend)

---

## Stack tecnológico

| Componente | Tecnología |
|-----------|------------|
| **Framework** | React 19 + Vite 7 |
| **Lenguaje** | TypeScript |
| **Routing** | TanStack Router |
| **State** | Zustand + TanStack Query |
| **UI** | Mantine v8 |
| **Mapas** | MapLibre GL + PMTiles |
| **3D** | Terrain integrado en MapLibre + backend geo/render para PNG/MP4 |
| **Geo cálculos** | Turf.js (`@turf/*`) |
| **Drawing tools** | `@mapbox/mapbox-gl-draw` con compatibilidad sobre MapLibre |
| **Charts** | Recharts |
| **Formularios** | Mantine Form + Zod (validación) |
| **HTTP** | Fetch nativo + interceptors |
| **Auth** | JWT del backend + Google OAuth |
| **Lint / Format** | Biome |
| **Tests** | Vitest + Testing Library |
| **E2E** | Playwright |
| **Mutation testing** | Stryker |
| **Hosting** | Cloudflare Pages |

---

## Funcionalidades

### Visor cartográfico

- Mapa 2D interactivo con MapLibre GL.
- Capas vectoriales: cuencas, canales (relevados + propuestas), caminos, escuelas, alertas, conflictos, suelos.
- Capas raster derivadas de DEM: hillshade, slope, TWI, HAND, flow accumulation.
- **Toggle 2D / 3D terrain**.
- Capa **PMTiles** servida desde Martin para tiles vectoriales eficientes.
- Controles: zoom, pan, búsqueda geoespacial, selector de capas, leyenda dinámica.
- **Comparador temporal de imágenes** Sentinel-2 (antes / después).
- Visualización de imágenes SAR Sentinel-1 para detección sin nubes.

### Panel de administración

Dashboard unificado con KPIs cruzados de denuncias, trámites y finanzas. Subpáginas:

- **Padrón** — CRUD de consorcistas con búsqueda, filtros y **importación CSV/XLSX**.
- **Denuncias** — gestión de reportes ciudadanos: estados, asignación, respuesta, historial.
- **Sugerencias** — gestión de sugerencias públicas, marcado para próxima reunión, incorporación como obras.
- **Trámites** — CRUD con seguimiento cronológico y exportación a PDF.
- **Reuniones** — calendario, agenda colaborativa, exportación de orden del día.
- **Finanzas** — ingresos, gastos, presupuesto, ejecución y resumen anual con exportación PDF.
- **Image Explorer** — selector de fecha + visualización de Sentinel-2 (true color, NDVI, índices de agua).
- **DEM Pipeline** — ejecutor visual del pipeline DEM → HAND → zonas → HCI con progress bars.

### Formularios públicos (sin auth)

- **Denuncia** — descripción, tipo, **adjuntar fotos**, **selección de ubicación en mapa**.
- **Sugerencia** — categorización, posibilidad de adjuntar contexto, vinculación opcional a una zona.

### Sistema de auth

- Login con email + contraseña (JWT del backend).
- Login con Google OAuth (opcional).
- Refresh automático de token antes de expirar.
- Perfil de usuario editable.
- Sistema de invitaciones (admin → operador) con activación por email.

### Branding dinámico

- El viewer carga logo, colores y nombre del consorcio desde el endpoint público `/api/v2/public/settings/branding`.
- Permite que distintos consorcios usen el mismo build con identidad propia.

---

## Rutas

| Ruta | Componente | Acceso | Función |
|------|-----------|--------|---------|
| `/` | HomePage | Público | Landing con introducción al consorcio |
| `/login` | LoginForm | Público | Auth (JWT o Google OAuth) |
| `/mapa` | MapaPage | Público | Visor cartográfico interactivo |
| `/denuncias` | ReportesPage | Público | Formulario de denuncia |
| `/sugerencias` | SugerenciasPage | Público | Formulario de sugerencia |
| `/admin` | AdminDashboard | Operador+ | KPIs y accesos rápidos |
| `/admin/images` | ImageExplorerPanel | Operador+ | Selector de imagen satelital |
| `/admin/participacion` | ParticipacionPanel | Operador+ | Denuncias y sugerencias (tabs; las rutas viejas `/admin/reports` y `/admin/sugerencias` redirigen acá) |
| `/admin/tramites` | TramitesPanel | Operador+ | Gestión de trámites |
| `/admin/reuniones` | ReunionesPanel | Operador+ | Gestión de reuniones |
| `/admin/padron` | PadronPanel | Operador+ | Gestión de consorcistas |
| `/admin/finanzas` | FinanzasPanel | Operador+ | Gestión financiera |
| `/admin/dem-pipeline` | DemPipelinePanel | Operador+ | Pipeline DEM |
| `/user/profile` | ProfilePanel | Autenticado | Perfil de usuario |

---

## Estructura del proyecto

```
consorcio-web/
├── public/
│   ├── _headers                      # Headers de seguridad + CSP + cache
│   ├── _redirects                    # SPA fallback hacia index.html
│   └── capas/                        # Capas estáticas servidas como assets
│       ├── canales/                  # relevados + propuestas + index
│       ├── escuelas/                 # escuelas rurales
│       ├── pilar-verde/              # capas agroforestación
│       ├── caminos.geojson
│       ├── candil.geojson
│       ├── inundacion_demo.geojson
│       └── (otras zonas)
├── src/
│   ├── components/
│   │   ├── admin/                    # Paneles de administración
│   │   ├── auth/                     # Login, registro, OAuth
│   │   ├── map/                      # Controles de dibujo/compatibilidad MapLibre
│   │   ├── map2d/                    # Visor 2D principal (MapLibre)
│   │   ├── report-form/              # Formulario de denuncia
│   │   ├── suggestion-form/          # Formulario de sugerencia
│   │   ├── terrain/                  # Visualización + análisis terreno
│   │   ├── verification/             # Workflows de verificación
│   │   └── ui/                       # Componentes Mantine reutilizables
│   ├── hooks/                        # Custom hooks (useCanales, useGEELayers, etc.)
│   ├── lib/
│   │   ├── api/                      # Cliente HTTP + endpoints
│   │   ├── auth/                     # Adaptador JWT
│   │   ├── kmzExport/                # Exportación KMZ con PII strip
│   │   └── query.ts                  # TanStack Query client
│   ├── routes/                       # Rutas TanStack Router
│   ├── stores/                       # Zustand stores
│   ├── styles/                       # CSS modules + globales
│   └── types/                        # Definiciones TypeScript
├── tests/
│   ├── unit/                         # Tests unitarios Vitest
│   ├── components/                   # Tests de componentes
│   ├── hooks/                        # Tests de hooks
│   ├── stores/                       # Tests de stores
│   └── fixtures/                     # Datos de prueba (incluye canales)
├── e2e/                              # Tests Playwright
├── package.json
├── vite.config.ts
├── biome.json
├── playwright.config.ts
└── stryker-canales-format.config.mjs
```

---

## Instalación

```bash
# Instalar dependencias
npm install

# Copiar variables de entorno
cp .env.example .env

# Configurar VITE_API_URL apuntando al backend (local o producción)
# VITE_MARTIN_URL es opcional (PMTiles server)

# Iniciar servidor de desarrollo
npm run dev
```

Servidor disponible en `http://localhost:5173`.

---

## Comandos

| Comando | Descripción |
|---------|-------------|
| `npm install` | Instalar dependencias |
| `npm run dev` | Servidor de desarrollo (`localhost:5173`) |
| `npm run build` | Build de producción a `dist/` |
| `npm run preview` | Preview local del build |
| `npm test` | Tests unitarios con Vitest |
| `npm run test:coverage` | Tests + reporte de cobertura |
| `npm run test:mutation` | Mutation testing con Stryker (canales-format) |
| `npm run lint` | Linting con Biome |
| `npm run lint:fix` | Lint + autofix |
| `npx playwright test` | Tests E2E |

---

## Configuración

### Variables de entorno

```env
VITE_API_URL=http://localhost:8000        # URL del backend FastAPI
VITE_MARTIN_URL=http://localhost:3001     # URL del Martin tile server (opcional)
```

En producción se setean en el panel de Cloudflare Pages.

### Auth backend

1. Setear `VITE_API_URL` apuntando al backend.
2. En el backend: configurar `JWT_SECRET` y opcionalmente credenciales Google OAuth.
3. El frontend usa el endpoint `/api/v2/auth/*` para todo el flujo de auth.

---

## Capas estáticas servidas

Bajo `public/capas/` se sirven datasets versionados con el repo:

| Carpeta | Contenido |
|---------|-----------|
| `canales/` | `relevados.geojson`, `propuestas.geojson`, `index.json` (con códigos, prioridades, longitudes) |
| `escuelas/` | `escuelas_rurales.geojson` (7 escuelas con datos del establecimiento) |
| `pilar-verde/` | Capas de agroforestación: `agro_*`, `bpa_*`, `porcentaje_forestacion`, `zona_ampliada` |
| Raíz | `caminos.geojson`, `candil.geojson`, `inundacion_demo.geojson`, zonas (`norte`, `noroeste`, `ml`, `zona`) |

Estas capas se regeneran offline desde KMZ con los ETLs en `scripts/etl_canales/`, `scripts/etl_pilar_verde/`, `scripts/etl_escuelas/`.

---

## Exportación de datos

### KMZ (Google Earth)

Módulo `lib/kmzExport/` permite exportar las capas visibles del visor a un archivo KMZ:

- **`kmzBuilder`** — construcción del archivo zip.
- **`kmzLayerRegistry`** — registro de capas exportables.
- **`kmzPiiStrip`** — remoción automática de datos sensibles antes de exportar (CUIT, contacto del padrón).
- **`kmzStyles`** — estilos KML personalizados por tipo de capa.
- **`triggerKmzDownload`** — disparo de descarga en navegador.

### PDFs

Los PDFs se generan en el backend (ReportLab) y se descargan desde el frontend con cliente HTTP.

---

## Deploy a Cloudflare Pages

Cloudflare Pages construye el proyecto desde `consorcio-web/` y publica el contenido de `dist/`.

### Configuración recomendada

| Setting | Valor |
|---------|-------|
| Framework preset | Vite |
| Build command | `npm run build` |
| Build output directory | `dist` |
| Root directory | `consorcio-web` |
| Node version | 20+ |

### Archivos relevantes

- `public/_headers` — headers de seguridad, CSP, cache de assets.
- `public/_redirects` — fallback SPA hacia `index.html` (rutas TanStack Router).
- `public/robots.txt` — control de indexación.

### Variables de entorno en Cloudflare Pages

Definir en el dashboard de Cloudflare:

- `VITE_API_URL` — URL pública del backend.
- `VITE_MARTIN_URL` — URL pública del Martin tile server (si aplica).

Cada push a `main` dispara un build automático de Cloudflare Pages.

---

## Integración con backend

El backend (`gee-backend/`) provee:

- **API REST v2** completa bajo `/api/v2/*` con OpenAPI en `/docs`.
- **Tiles MVT** desde Martin para capas vectoriales pesadas.
- **Imágenes GEE** procesadas (Sentinel-1 SAR, Sentinel-2 multiespectral).
- **Análisis hidrológico** y de inteligencia (HCI, escorrentía, conflictos).
- **PDFs generados** vía ReportLab (trámites, fichas, resúmenes financieros).
- **Branding público** — logo y colores del consorcio sin requerir auth.

---

Desarrollado para el **Consorcio Canalero 10 de Mayo** — departamento Unión, Córdoba, Argentina.
