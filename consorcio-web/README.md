# Consorcio Canalero 10 de Mayo - Web

Sistema web para el monitoreo de cuencas hidricas del Consorcio Canalero 10 de Mayo, Bell Ville, Cordoba.

## Stack Tecnologico

- **Framework:** React 19 + Vite 6
- **Routing:** TanStack Router
- **State:** Zustand + TanStack Query
- **UI:** Mantine v7
- **Mapas:** Leaflet + react-leaflet
- **Backend:** FastAPI + Google Earth Engine
- **Auth:** Supabase Auth
- **Hosting:** Vercel

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
# - VITE_SUPABASE_URL
# - VITE_SUPABASE_ANON_KEY
# - VITE_GEE_API_URL

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
│   ├── supabase.ts      # Cliente Supabase
│   └── query.ts         # TanStack Query client
├── routes/              # Rutas TanStack Router
├── stores/              # Zustand stores
├── styles/              # CSS modules y estilos globales
└── types/               # TypeScript types
```

## Configuracion de Supabase

1. Crear proyecto en [supabase.com](https://supabase.com)
2. Ejecutar el SQL de `supabase/schema.sql`
3. Configurar Auth providers
4. Copiar URL y anon key al `.env`

## Comandos

| Comando | Descripcion |
|---------|-------------|
| `npm install` | Instalar dependencias |
| `npm run dev` | Servidor de desarrollo (localhost:5173) |
| `npm run build` | Build de produccion |
| `npm run preview` | Preview del build |
| `npm test` | Ejecutar tests con Vitest |
| `npm run lint` | Linting con Biome |

## Deploy a Vercel

```bash
# Build
npm run build

# Deploy
npx vercel
```

## Integracion con GEE Backend

El backend de Google Earth Engine proporciona:
- Deteccion de inundaciones con Sentinel-1 SAR
- Exploracion de imagenes satelitales
- Clasificacion supervisada de cobertura
- Capas vectoriales (cuencas, caminos, zona)
