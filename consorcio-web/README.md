# Consorcio Canalero 10 de Mayo - Web

Sistema web para el monitoreo de cuencas hidricas del Consorcio Canalero 10 de Mayo, Bell Ville, Cordoba.

## Stack Tecnologico

- **Framework:** React 19 + Vite 7
- **Routing:** TanStack Router
- **State:** Zustand + TanStack Query
- **UI:** Mantine v8
- **Mapas:** MapLibre GL + PMTiles
- **Backend:** FastAPI + Google Earth Engine
- **Auth:** JWT del backend + Google OAuth
- **Hosting:** Cloudflare Pages

## Funcionalidades

- Mapa interactivo con capas de cuencas, caminos e inundaciones
- Explorador de imagenes satelitales (Sentinel-1, Sentinel-2, Landsat)
- Analisis de inundaciones con SAR
- Entrenamiento de clasificacion supervisada
- Sistema de denuncias con ubicacion GPS y fotos
- Sistema de sugerencias
- Dashboard con estadisticas
- Panel de administracion

## Instalacion

```bash
# Instalar dependencias
npm install

# Copiar variables de entorno
cp .env.example .env

# Configurar las variables en .env
# - VITE_API_URL
# - VITE_MARTIN_URL (opcional)

# Iniciar servidor de desarrollo
npm run dev
```

## Estructura del Proyecto

```
src/
├── components/          # Componentes React
│   ├── admin/           # Componentes del panel admin
│   ├── map/             # Componentes de mapas
│   ├── training/        # Componentes de entrenamiento ML
│   └── ui/              # Componentes UI reutilizables
├── hooks/               # Custom hooks
├── lib/                 # Utilidades y clientes
│   ├── api/             # Cliente HTTP y endpoints
│   ├── auth/            # Adaptador JWT/backend
│   └── query.ts         # TanStack Query client
├── routes/              # Rutas TanStack Router
├── stores/              # Zustand stores
├── styles/              # CSS modules y estilos globales
└── types/               # TypeScript types
```

## Configuracion de Auth

La autenticacion usa el backend FastAPI:

1. Configurar `VITE_API_URL` en `.env` para apuntar al backend.
2. Configurar `JWT_SECRET` y, opcionalmente, credenciales Google OAuth en el backend.
3. En produccion, definir `VITE_API_URL` y `VITE_MARTIN_URL` en Cloudflare Pages.

## Comandos

| Comando | Descripcion |
|---------|-------------|
| `npm install` | Instalar dependencias |
| `npm run dev` | Servidor de desarrollo (localhost:5173) |
| `npm run build` | Build de produccion |
| `npm run preview` | Preview del build |
| `npm test` | Ejecutar tests con Vitest |
| `npm run lint` | Linting con Biome |

## Deploy a Cloudflare Pages

Cloudflare Pages construye desde `consorcio-web` y publica `dist`.

Configuracion recomendada:

| Setting | Valor |
|---------|-------|
| Framework preset | Vite |
| Build command | `npm run build` |
| Build output directory | `dist` |
| Root directory | `consorcio-web` |

Archivos relevantes:

- `public/_headers`: headers de seguridad, CSP y cache.
- `public/_redirects`: fallback SPA hacia `index.html`.

## Integracion con GEE Backend

El backend de Google Earth Engine proporciona:
- Deteccion de inundaciones con Sentinel-1 SAR
- Exploracion de imagenes satelitales
- Clasificacion supervisada de cobertura
- Capas vectoriales (cuencas, caminos, zona)
