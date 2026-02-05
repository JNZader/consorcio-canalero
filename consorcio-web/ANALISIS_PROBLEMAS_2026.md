# Analisis de Problemas - Consorcio Canalero Web

> **NOTA HISTORICA:** Este analisis se realizo cuando la aplicacion usaba Astro.
> La arquitectura fue migrada a React + Vite + TanStack Router en enero 2026.
> Algunos problemas mencionados ya fueron resueltos durante la migracion.

**Fecha:** 2026-01-08
**Version:** 1.0
**Analistas:** 5 agentes especializados (Frontend, Backend Parity, Code Quality, UI/UX, Performance)

---

## Resumen Ejecutivo

Se identificaron **19 problemas** en la aplicacion web del Consorcio Canalero, clasificados en 5 categorias de severidad. Este documento detalla cada problema, su ubicacion, impacto y solucion propuesta.

### Distribucion por Severidad

| Severidad | Cantidad | Descripcion |
|-----------|----------|-------------|
| Critica   | 5        | Afectan funcionalidad core o UX critica |
| Importante| 8        | Impactan calidad de codigo o mantenibilidad |
| Menor     | 6        | Mejoras de consistencia y accesibilidad |

---

## Problemas Criticos (5)

### 1. Debounce faltante en busqueda de denuncias

**Archivo:** `src/components/admin/reports/ReportsPanel.tsx:339`

**Problema:** El input de busqueda dispara una peticion al servidor en cada keystroke sin debounce, causando:
- Sobrecarga innecesaria del servidor
- Flicker en la UI
- Posibles race conditions en respuestas

**Codigo actual:**
```tsx
onChange={(e) => setSearchQuery(e.target.value)} // Sin debounce
```

**Solucion:** Implementar useDebouncedCallback de @mantine/hooks con 300ms de delay.

---

### 2. geeApi faltante para endpoints de Google Earth Engine

**Archivo:** `src/lib/api.ts`

**Problema:** El backend expone endpoints para capas GEE que no estan implementados en el frontend:
- `GET /api/gee/layers` - Listar capas GEE disponibles
- `GET /api/gee/layers/{name}` - Obtener capa especifica
- `POST /api/gee/layers` - Crear nueva capa

**Impacto:** Funcionalidad de capas GEE no disponible para administradores.

**Solucion:** Crear objeto geeApi en api.ts con todos los endpoints.

---

### 3. Filtro assigned_to faltante en reportsApi

**Archivo:** `src/lib/api.ts` - reportsApi.list()

**Problema:** El backend soporta filtrar denuncias por operador asignado (`assigned_to`), pero el frontend no expone este filtro.

**Backend soporta:**
```
GET /api/reports?assigned_to={user_id}
```

**Frontend actual:**
```typescript
interface ReportsFilter {
  page?: number;
  limit?: number;
  status?: EstadoDenuncia;
  cuenca?: CuencaId;
  tipo?: TipoDenuncia;
  // Falta: assigned_to
}
```

**Solucion:** Agregar `assigned_to?: string` al interface y al query string.

---

### 4. Colores duplicados y hardcodeados

**Archivos afectados:**
- `src/components/map/DrawControl.tsx` - `#3b82f6`
- `src/components/MapaLeaflet.tsx` - `#FF0000`, `#2196F3`, `#4CAF50`
- `src/components/map/MapaAnalisis.tsx` - colores duplicados
- `src/components/training/TrainingMap.tsx` - `#2ECC71`, `#F39C12`
- `src/components/training/TrainingPanel.tsx` - colores de clasificacion
- `src/components/admin/monitoring/MonitoringDashboard.tsx` - colores repetidos

**Problema:** Colores hardcodeados en multiples archivos dificultan:
- Cambios de tema
- Consistencia visual
- Mantenimiento

**Solucion:** Centralizar en `src/constants/colors.ts` y reutilizar.

---

### 5. Uso de console.error en lugar de logger

**Instancias encontradas:** 56

**Archivos principales:**
- `src/hooks/useContactVerification.ts`
- `src/hooks/useFloodAnalysis.ts`
- `src/stores/authStore.ts`
- `src/lib/auth.ts`
- `src/components/ErrorBoundary.tsx`
- `src/components/FormularioDenuncia.tsx`
- `src/components/admin/sugerencias/SugerenciasPanel.tsx`
- `src/components/admin/layers/LayersPanel.tsx`

**Problema:** console.error:
- No se puede deshabilitar en produccion
- No tiene niveles de severidad
- No se integra con sistemas de monitoreo

**Solucion:** Migrar a `src/lib/logger.ts` ya existente.

---

## Problemas Importantes (8)

### 6. LoadingState no usado consistentemente

**Componentes con Loader raw (12):**
- `ProfilePanel.tsx:135`
- `admin/analysis/AnalysisPanel.tsx:244`
- `admin/caminos/CaminosAfectadosPanel.tsx:72`
- `admin/layers/LayersPanel.tsx:135,469`
- `admin/monitoring/MonitoringDashboard.tsx:120`
- `admin/reports/ReportDetailModal.tsx:44`
- `admin/reports/ReportsPanel.tsx:393`
- `admin/stats/StatsPanel.tsx:103`
- `admin/sugerencias/SugerenciasPanel.tsx:123`
- `admin/users/UsersPanel.tsx:84`
- `training/TrainingPanel.tsx:180`

**Problema:** Existe `LoadingState` centralizado pero no se usa consistentemente.

**Solucion:** Reemplazar `<Center><Loader /></Center>` con `<LoadingState message="..." />`.

---

### 7. EmptyState no usado donde corresponde

**Componentes que muestran texto plano en lugar de EmptyState (5):**
- `admin/reports/ReportsPanel.tsx` - "No hay denuncias"
- `admin/layers/LayersPanel.tsx` - "No hay capas"
- `admin/analysis/AnalysisPanel.tsx` - "No hay analisis"
- `admin/users/UsersPanel.tsx` - "No hay usuarios"
- `admin/caminos/CaminosAfectadosPanel.tsx` - "No hay datos"

**Solucion:** Usar componente EmptyState existente para mensajes vacios.

---

### 8. Importacion directa de iconos @tabler

**Archivos afectados (4):**
- `src/components/training/TrainingPanel.tsx:19-30`
- `src/components/admin/AdminMonitoringPage.tsx:2`
- `src/components/admin/monitoring/ClassificationMap.tsx:16-20`
- `src/components/admin/monitoring/MonitoringDashboard.tsx:17-23`

**Problema:** Se importa directamente de `@tabler/icons-react` en lugar de usar el re-export centralizado de `src/components/ui/icons.tsx`.

**Solucion:** Agregar iconos faltantes a `ui/icons.tsx` e importar desde ahi.

---

### 9. fusion_mode no expuesto en UI

**Archivo backend:** `POST /api/flood-detection`

**Problema:** El backend soporta parametro `fusion_mode` para seleccionar algoritmo de fusion de imagenes:
- `mean` - Promedio
- `median` - Mediana
- `max` - Maximo
- `min` - Minimo

El frontend no expone esta opcion al usuario.

**Solucion:** Agregar Select en AnalysisPanel para elegir modo de fusion.

---

### 10. Panel de administracion WhatsApp faltante

**Backend endpoints disponibles:**
- `GET /api/whatsapp/sessions` - Listar sesiones
- `GET /api/whatsapp/sessions/{phone}/status` - Estado de sesion
- `POST /api/whatsapp/sessions/{phone}/start` - Iniciar sesion
- `DELETE /api/whatsapp/sessions/{phone}/stop` - Detener sesion
- `POST /api/whatsapp/send` - Enviar mensaje

**Problema:** No existe panel en el frontend para gestionar el bot de WhatsApp.

**Solucion:** Crear `src/components/admin/whatsapp/WhatsAppPanel.tsx`.

---

### 11. useEffect sin cleanup en 6 componentes

**Archivos afectados:**
- `src/hooks/useFloodAnalysis.ts` - polling sin cleanup
- `src/components/MapaLeaflet.tsx` - listeners sin cleanup
- `src/components/map/MapaAnalisis.tsx` - map instance
- `src/components/training/TrainingMap.tsx` - drawing handlers
- `src/components/admin/monitoring/ClassificationMap.tsx` - layers
- `src/components/FormularioDenuncia.tsx` - geolocation

**Problema:** Memory leaks potenciales al no limpiar efectos.

**Solucion:** Agregar funciones de cleanup que retornen en useEffect.

---

### 12. api.ts demasiado grande (1287 lineas)

**Archivo:** `src/lib/api.ts`

**Problema:** Un solo archivo maneja todos los endpoints, dificultando:
- Navegacion del codigo
- Testing individual
- Colaboracion en equipo

**Solucion propuesta:** Dividir en modulos:
```
src/lib/api/
  index.ts        - Re-exports
  client.ts       - Base client y helpers
  reports.ts      - reportsApi
  analysis.ts     - analysisApi
  layers.ts       - layersApi
  stats.ts        - statsApi
  users.ts        - usersApi
  gee.ts          - geeApi (nuevo)
  whatsapp.ts     - whatsappApi (nuevo)
```

---

### 13. Type assertions sin validacion

**Ejemplos encontrados:**
```typescript
// api.ts:156
return data as DashboardStats;

// api.ts:203
return data as AnalysisHistory;

// StatsPanel.tsx:278
const cuencaData = data as { hectareas: number; porcentaje: number };
```

**Problema:** `as` bypasses TypeScript sin validar que los datos sean correctos.

**Solucion:** Usar type guards o Zod para validacion runtime en boundaries.

---

## Problemas Menores (6)

### 14. Spacing inconsistente

**Observaciones:**
- Algunos componentes usan `gap="md"`, otros `gap={16}`
- Mezcla de valores numericos y tokens de Mantine
- `mb="xl"` vs `mb={24}` en diferentes archivos

**Solucion:** Estandarizar usando solo tokens de Mantine (`xs`, `sm`, `md`, `lg`, `xl`).

---

### 15. Padding inconsistente

**Observaciones:**
- Cards con `padding="lg"` y `padding="md"` mezclados
- Papers con `p="md"` y `p="lg"` sin patron claro
- Containers con `py="md"` y `py="xl"` arbitrarios

**Solucion:** Definir guia de espaciado y aplicar consistentemente.

---

### 16. Logica de auth duplicada

**Archivos con logica similar:**
- `src/lib/auth.ts` - funciones de utilidad
- `src/stores/authStore.ts` - store principal
- `src/hooks/useAuth.ts` (si existe) - hook wrapper

**Problema:** Duplicacion de chequeos de roles y permisos.

**Solucion:** Centralizar toda la logica en authStore con selectores.

---

### 17. Helpers duplicados

**Funciones encontradas en multiples lugares:**
- Formateo de fechas
- Validacion de coordenadas
- Parsing de respuestas API
- Manejo de errores

**Solucion:** Centralizar en `src/lib/utils/` con modulos especificos.

---

### 18. aria-labels faltantes en controles del mapa

**Controles sin accesibilidad:**
- Botones de zoom
- Controles de dibujo
- Selector de capas
- Boton de geolocalizacion

**Problema:** Usuarios con lectores de pantalla no pueden usar el mapa.

**Solucion:** Agregar `aria-label` descriptivos a todos los controles interactivos.

---

### 19. TODO pendiente en ErrorBoundary

**Archivo:** `src/components/ErrorBoundary.tsx`

**Codigo:**
```typescript
// TODO: Integrar con servicio de monitoreo de errores (Sentry, etc.)
```

**Solucion:** Implementar integracion con Sentry o similar, o remover TODO si no es prioritario.

---

## Aspectos Positivos Identificados

Durante el analisis tambien se identificaron buenas practicas:

1. **Arquitectura solida** - Astro + React Islands bien implementado
2. **Bundle optimization** - Code splitting efectivo
3. **TanStack Query** - Configuracion correcta de staleTime y caching
4. **Zustand** - Store de auth con persistencia bien diseñado
5. **Tipos centralizados** - `src/types/index.ts` bien organizado
6. **Constantes** - `src/constants/index.ts` con valores reutilizables
7. **Componentes UI** - Sistema de componentes consistente con Mantine

---

## Plan de Implementacion

### Fase 1 - Criticos (Prioridad Alta)
1. Debounce en busqueda
2. geeApi endpoints
3. Filtro assigned_to
4. Consolidar colores
5. Migrar a logger

### Fase 2 - Importantes (Prioridad Media)
6. LoadingState consistente
7. EmptyState consistente
8. Centralizar iconos
9. Exponer fusion_mode
10. Panel WhatsApp
11. Cleanup useEffects
12. Dividir api.ts
13. Validacion de tipos

### Fase 3 - Menores (Prioridad Baja)
14. Spacing tokens
15. Padding tokens
16. Centralizar auth
17. Centralizar helpers
18. Aria-labels
19. TODO ErrorBoundary

---

## Metricas de Exito

| Metrica | Antes | Objetivo |
|---------|-------|----------|
| console.error instances | 56 | 0 |
| Componentes con Loader raw | 12 | 0 |
| Archivos con iconos directos | 4 | 0 |
| Endpoints backend sin frontend | 8+ | 0 |
| useEffects sin cleanup | 6 | 0 |

---

*Documento generado automaticamente por analisis de agentes especializados.*
