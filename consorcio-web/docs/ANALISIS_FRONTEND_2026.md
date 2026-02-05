# Análisis Completo del Frontend - Consorcio Canalero v1

> **NOTA HISTÓRICA:** Este análisis se realizó cuando la aplicación usaba Astro.
> La arquitectura fue migrada a React + Vite + TanStack Router en enero 2026.
> Algunos problemas mencionados ya fueron resueltos durante la migración.

**Fecha:** 2026-01-08
**Versión:** 1.0
**Analizado por:** Claude Code (5 agentes especializados)

---

## Resumen Ejecutivo

Este documento presenta un análisis exhaustivo de la aplicación web del Consorcio Canalero, identificando problemas críticos, inconsistencias, oportunidades de mejora y paridad de funcionalidades entre frontend y backend.

**Estadísticas del Codebase:**
- ~19,066 líneas de TypeScript/TSX
- 58 componentes React
- 16 rutas Astro
- 12 módulos de utilidades
- 4 custom hooks
- 60+ endpoints API integrados

---

## Tabla de Contenidos

1. [Arquitectura](#1-arquitectura)
2. [Problemas Críticos](#2-problemas-críticos)
3. [Problemas Importantes](#3-problemas-importantes)
4. [Paridad Frontend-Backend](#4-paridad-frontend-backend)
5. [Inconsistencias UI/UX](#5-inconsistencias-uiux)
6. [Seguridad](#6-seguridad)
7. [Performance](#7-performance)
8. [Accesibilidad](#8-accesibilidad)
9. [Aspectos Positivos](#9-aspectos-positivos)
10. [Plan de Correcciones](#10-plan-de-correcciones)

---

## 1. Arquitectura

### 1.1 Stack Tecnológico

| Capa | Tecnología | Versión |
|------|------------|---------|
| Meta Framework | Astro | 5.16.6 |
| UI Framework | React | 19.2.3 |
| Component Library | Mantine UI | 8.3.11 |
| State Management | Zustand | 5.0.0 |
| Server State | TanStack Query | 5.62.0 |
| Server State (Legacy) | SWR | 2.3.8 |
| Maps | Leaflet + react-leaflet | 1.9.4 / 5.0.0 |
| Auth | Supabase | - |
| Backend | Python FastAPI | - |

### 1.2 Estructura de Directorios

```
src/
├── components/          (58 archivos TSX)
│   ├── admin/          (Componentes administrativos)
│   │   ├── analysis/   (Panel de análisis)
│   │   ├── caminos/    (Caminos afectados)
│   │   ├── layers/     (Gestión de capas)
│   │   ├── monitoring/ (Monitoreo satelital)
│   │   ├── reports/    (Gestión de denuncias)
│   │   ├── stats/      (Estadísticas)
│   │   └── sugerencias/(Sugerencias ciudadanas)
│   ├── map/            (Componentes de mapa)
│   ├── ui/             (Componentes reutilizables)
│   ├── verification/   (Verificación de contacto)
│   └── training/       (Clasificación ML)
├── pages/              (16 rutas Astro)
├── layouts/            (Layouts Astro)
├── hooks/              (4 custom hooks)
├── stores/             (Zustand stores)
├── lib/                (12 módulos utilitarios)
├── types/              (Definiciones TypeScript)
├── constants/          (Constantes compartidas)
└── styles/             (CSS modules + global)
```

### 1.3 Patrones de Arquitectura

#### Patrón Islands (Astro)
- Componentes React hydratados con `client:load`
- Cada island necesita su propio MantineProvider
- Wrapper pattern: `ComponentContent` + `Component` (con providers)

#### Patrón de Estado
- **Auth:** Zustand con persistencia (localStorage)
- **Server State:** TanStack Query para cache/revalidación
- **Local State:** useState para UI transiente

---

## 2. Problemas Críticos

### 2.1 Dos Sistemas de Data Fetching Compitiendo

**Severidad:** CRÍTICA
**Archivos Afectados:**
- `src/lib/swr.ts` (307 líneas)
- `src/lib/query.ts` (369 líneas)

**Descripción:**
Ambos archivos definen hooks idénticos para obtener datos:
- `useDashboardStats`
- `useReports`
- `useAnalysisHistory`
- `useLayers`

**Impacto:**
- Confusión sobre cuál sistema usar
- Posible inconsistencia de cache
- ~200 líneas de código duplicado
- Mayor bundle size

**Solución:**
Eliminar SWR completamente, usar solo TanStack Query.

---

### 2.2 Número de Teléfono Placeholder en Producción

**Severidad:** CRÍTICA
**Archivo:** `src/components/DenunciasPage.tsx:47`

**Código Problemático:**
```tsx
<Button component="a" href="tel:+543534XXXXXX" color="red" variant="light" fullWidth>
```

**Impacto:**
Los usuarios no pueden contactar soporte por teléfono.

**Solución:**
Usar variable de entorno `PUBLIC_SUPPORT_PHONE`.

---

### 2.3 File Uploads Sin Token de Autenticación

**Severidad:** CRÍTICA
**Archivos Afectados:**
- `src/lib/api.ts:311-342` (layers/upload)
- `src/lib/api.ts:559-587` (public/upload-photo)

**Código Problemático:**
```typescript
const response = await fetch(`${API_URL}${API_PREFIX}/layers/upload`, {
  method: 'POST',
  body: formData,
  signal: controller.signal,
  // ❌ NO Authorization header!
});
```

**Impacto:**
Si el backend requiere autenticación, los uploads fallan silenciosamente.

**Solución:**
Agregar header de autorización como en `apiFetch()`.

---

### 2.4 Array Index como React Key

**Severidad:** CRÍTICA
**Archivo:** `src/components/admin/monitoring/MonitoringDashboard.tsx:174`

**Código Problemático:**
```tsx
{alertas.slice(0, 3).map((alerta, idx) => (
  <Alert key={idx} ...>  // ❌ Anti-pattern
```

**Impacto:**
Si la lista se reordena/filtra, React asocia estados incorrectos a elementos.

**Nota:** `biome.json` tiene `"noArrayIndexKey": "off"` deshabilitando esta regla.

**Solución:**
Usar `key={alerta.id || \`alert-${alerta.tipo}-${idx}\`}`.

---

## 3. Problemas Importantes

### 3.1 Token de Auth Obtenido en Cada Request

**Severidad:** ALTA
**Archivo:** `src/lib/api.ts:36-66`

**Código Problemático:**
```typescript
async function getAuthToken(): Promise<string | null> {
  const { data: { session } } = await getSupabaseClient().auth.getSession();
  return session?.access_token || null;
}

// Llamado en CADA petición:
const token = await getAuthToken();
```

**Impacto:**
- Latencia multiplicada
- Carga innecesaria al servicio Supabase
- Posible throttling

**Solución:**
Cachear token con TTL y refresh automático.

---

### 3.2 Sin Deduplicación de Requests

**Severidad:** ALTA
**Archivo:** `src/lib/api.ts`

**Descripción:**
No hay deduplicación de requests en vuelo. Si 2 componentes montan simultáneamente y solicitan los mismos datos, se ejecutan 2 llamadas API.

**Solución:**
Implementar cache de requests en vuelo.

---

### 3.3 Error Handling Inconsistente

**Severidad:** ALTA
**Archivos Afectados:** Múltiples

**Patrones Encontrados:**
1. `try/catch` con `console.error` (60+ instancias)
2. Uso del logger centralizado (pocos casos)
3. `handleError()` de errorHandler.ts (inconsistente)

**Solución:**
Estandarizar en `src/lib/logger.ts` para todo logging.

---

### 3.4 Tipos `unknown` en Respuestas API

**Severidad:** MEDIA
**Archivo:** `src/lib/api.ts:198-225`

**Endpoints Afectados:**
- `getPrecipitation`: `Promise<unknown>`
- `getPrecipitationMonthly`: `Promise<unknown>`
- `getFloodTimeSeries`: `Promise<unknown>`
- `getStatsByPolygon`: `Promise<unknown>`

**Impacto:**
Pierde type safety, consumidores deben castear.

**Solución:**
Definir interfaces para todas las respuestas.

---

### 3.5 Sin Route Guards a Nivel Astro

**Severidad:** MEDIA
**Archivos:** `src/pages/admin/*.astro`

**Descripción:**
Las páginas admin renderizan componentes directamente sin verificación de auth a nivel de página.

**Impacto:**
Si el componente falla antes del check de auth, el UI admin podría mostrarse brevemente.

**Solución:**
Agregar middleware o guards en páginas Astro.

---

### 3.6 Memory Leak en Auth Listener

**Severidad:** MEDIA
**Archivo:** `src/stores/authStore.ts:184-215`

**Descripción:**
El auth state change listener se registra globalmente pero no se limpia en `reset()`.

**Impacto:**
En HMR o tests, los listeners se acumulan.

---

## 4. Paridad Frontend-Backend

### 4.1 Endpoints NO Implementados en Frontend

| Endpoint | Método | Propósito | Estado |
|----------|--------|-----------|--------|
| `/analysis/flood/compare-periods` | POST | Comparar 2 períodos | ❌ No implementado |
| `/analysis/precipitation/by-cuenca` | POST | Precipitación por cuenca | ❌ No encontrado |
| `/monitoring/tiles/{layer_name}` | GET | Tiles de clasificación | ❌ No implementado |
| `/whatsapp/sessions` | GET | Sesiones WhatsApp | ❌ No implementado |
| `/whatsapp/messages` | GET | Historial mensajes | ❌ No implementado |
| `/whatsapp/send-test` | POST | Mensaje de prueba | ❌ No implementado |
| `/config/analysis-defaults` | GET | Config por defecto | ❌ No usado |

### 4.2 Endpoints Parcialmente Implementados

| Endpoint | Problema |
|----------|----------|
| `/analysis/flood-detection-optical` | Tipo `unknown` |
| `/analysis/flood-detection-fusion` | Tipo `unknown` |
| `/analysis/flood/time-series` | Tipo `unknown` |
| `/analysis/precipitation/monthly` | Tipo `unknown` |
| `/monitoring/supervised/clasificar` | Timeout 120s excesivo |

### 4.3 Capacidades Backend No Expuestas

1. **Modelos de Clasificación:**
   - Backend soporta: `random_forest`, `svm`, `cart`, `minimum_distance`
   - Frontend solo usa `random_forest`

2. **Exportación:**
   - Backend soporta: CSV, XLSX, PDF
   - Frontend solo implementa CSV para caminos

3. **Alertas Configurables:**
   - Backend tiene umbrales configurables
   - Frontend no permite configurar

---

## 5. Inconsistencias UI/UX

### 5.1 Loading States

| Componente | Implementación | Debería Usar |
|------------|----------------|--------------|
| AdminDashboard.tsx | `<Loader>` raw | `<LoadingState>` |
| FormularioDenuncia.tsx | Skeleton inline | `<LoadingState variant="skeleton">` |
| StatsPanel.tsx | `<Loader>` raw | `<LoadingState>` |
| ReportsPanel.tsx | ✅ `<LoadingState>` | - |

### 5.2 Form Validation

| Componente | Patrón | Inconsistencia |
|------------|--------|----------------|
| FormularioDenuncia | Custom error Text | No usa `AccessibleError` |
| FormularioSugerencia | Notifications post-submit | No inline errors |
| LoginForm | Mantine form errors | ✅ Correcto |

### 5.3 Spacing/Padding

| Ubicación | Valor | Debería Ser |
|-----------|-------|-------------|
| FormularioDenuncia Stack | `gap="lg"` | Estandarizar |
| FormularioSugerencia Stack | `gap="md"` | Estandarizar |
| AdminDashboard Paper | `p="md"` | Estandarizar |
| StatsPanel Card | `padding="lg"` | Usar `p=` |

### 5.4 Empty States

- ✅ `EmptyState` component existe
- ❌ No usado consistentemente
- AdminDashboard usa `<Text>` simple

### 5.5 Confirmaciones Faltantes

| Acción | Tiene Confirmación |
|--------|-------------------|
| Delete capa | ✅ Sí |
| Cambio estado denuncia | ❌ No |
| Reset formulario | ❌ No |
| Submit formulario | ❌ No (sin preview) |

---

## 6. Seguridad

### 6.1 Problemas Identificados

1. **Rate Limit Info Expuesta:**
   - `src/lib/api.ts:690-695` expone detalles de rate limiting
   - Podría ayudar a atacantes a optimizar ataques

2. **Role Check sin Validación:**
   - `src/components/admin/ProtectedRoute.tsx:255`
   - Type assertion sin validar: `profile.rol as UserRole`

3. **Leaflet Icons desde CDN Externo:**
   - `src/components/FormularioDenuncia.tsx:53-61`
   - Dependencia de unpkg.com para iconos críticos

### 6.2 Aspectos Positivos

- ✅ JWT tokens manejados correctamente
- ✅ No hay secrets expuestos en código
- ✅ Supabase RLS (Row Level Security) probablemente configurado

---

## 7. Performance

### 7.1 Problemas

1. **Bundle Size:**
   - SWR + TanStack Query ambos incluidos
   - Leaflet cargado sync en formulario

2. **Re-renders Innecesarios:**
   - Token fetching en cada request
   - Sin memoization en algunos componentes

3. **Timeouts Excesivos:**
   - Clasificación supervisada: 120s
   - Debería ser 60s con feedback progresivo

### 7.2 Optimizaciones Existentes

- ✅ Lazy loading de componentes pesados
- ✅ Chunking manual en astro.config.mjs
- ✅ Memoization en componentes críticos

---

## 8. Accesibilidad

### 8.1 Implementaciones Excelentes

- ✅ `LiveRegionProvider` para anuncios
- ✅ Skip links para navegación
- ✅ `AccessibleRadioGroup` con keyboard nav
- ✅ Focus trap en modales
- ✅ ARIA labels extensivos
- ✅ `usePrefersReducedMotion` hook
- ✅ Contraste WCAG AA

### 8.2 Áreas de Mejora

- ⚠️ Algunas imágenes sin alt text
- ⚠️ Focus management en modales de delete
- ⚠️ Skip links posicionamiento podría cortarse

---

## 9. Aspectos Positivos

### Arquitectura
- ✅ Islands architecture bien implementado
- ✅ Separación clara de concerns
- ✅ TypeScript estricto

### Código
- ✅ Constantes centralizadas
- ✅ Theme institucional consistente
- ✅ CSS Modules para scoped styling

### UX
- ✅ Mensajes de error en español
- ✅ Responsive design completo
- ✅ Estados vacíos definidos

### DevEx
- ✅ Biome linting configurado
- ✅ Tests estructurados
- ✅ Hot reloading funcional

---

## 10. Plan de Correcciones

### Fase 1: Críticos (Inmediato)

| # | Tarea | Archivo(s) | Esfuerzo |
|---|-------|------------|----------|
| 1 | Eliminar SWR | `src/lib/swr.ts`, imports | 30 min |
| 2 | Auth headers en uploads | `src/lib/api.ts` | 15 min |
| 3 | Reemplazar teléfono placeholder | `DenunciasPage.tsx` | 5 min |
| 4 | Arreglar React keys | `MonitoringDashboard.tsx` | 10 min |

### Fase 2: Importantes (Esta semana)

| # | Tarea | Archivo(s) | Esfuerzo |
|---|-------|------------|----------|
| 5 | Cachear auth token | `src/lib/api.ts` | 45 min |
| 6 | Estandarizar error handling | Múltiples | 1 hora |
| 7 | Route guards Astro | `src/pages/admin/*.astro` | 30 min |
| 8 | Tipar respuestas unknown | `src/lib/api.ts`, `types/` | 1 hora |

### Fase 3: Mejoras (Este mes)

| # | Tarea | Archivo(s) | Esfuerzo |
|---|-------|------------|----------|
| 9 | Implementar endpoints faltantes | `src/lib/api.ts` | 2 horas |
| 10 | Unificar loading states | Componentes | 1 hora |
| 11 | Agregar confirmaciones | Componentes admin | 1 hora |
| 12 | Implementar breadcrumbs | Layout admin | 30 min |

---

## Apéndice A: Endpoints Backend Completos

Ver archivo separado: `BACKEND_API_REFERENCE.md`

## Apéndice B: Comandos de Verificación

```bash
# Verificar tipos TypeScript
npx tsc --noEmit

# Ejecutar linting
npx biome check src/

# Ejecutar tests
npm run test

# Build de producción
npm run build
```

---

*Documento generado automáticamente por análisis de Claude Code.*
