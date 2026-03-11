# Roadmap de Mejoras - Consorcio Canalero Web

> **NOTA:** Este roadmap fue completado antes de la migración de Astro a React + Vite + TanStack Router (enero 2026).
> Todas las mejoras documentadas aquí siguen vigentes en la nueva arquitectura.

**Fecha de inicio:** 2026-01-06
**Fecha de finalización:** 2026-01-07
**Estado:** ✅ Completado
**Total de mejoras:** 25 (todas implementadas)

---

## Resumen de Sprints

| Sprint | Enfoque | Tareas | Estado |
|--------|---------|--------|--------|
| Sprint 1 | Critico (Seguridad + Testing + A11y) | 7 | ✅ Completado |
| Sprint 2 | Alto (Rendimiento + Codigo) | 8 | ✅ Completado |
| Sprint 3 | Medio (A11y + Arquitectura + Testing) | 10 | ✅ Completado |

---

## Sprint 1 - Mejoras Criticas

### 1.1 Seguridad: Corregir CSP en vercel.json
- **Archivo:** `vercel.json`
- **Problema:** CSP con 'unsafe-inline' y 'unsafe-eval' anula proteccion XSS
- **Solucion:** Eliminar directivas inseguras de script-src
- **Estado:** [x] Completado
- **Fecha completado:** 2026-01-06
- **Nota:** Se mantiene 'unsafe-inline' en style-src (requerido por Mantine CSS-in-JS)

### 1.2 Testing: Crear archivo setup.ts
- **Archivo:** `tests/setup.ts`
- **Problema:** Archivo ya existia pero faltaban mocks criticos
- **Solucion:** Agregado mock de geolocation y import.meta.env
- **Estado:** [x] Completado
- **Fecha completado:** 2026-01-06
- **Nota:** Ya existia con matchMedia, ResizeObserver, etc. Se agregaron geolocation y env vars

### 1.3 Accesibilidad: Agregar LiveRegionProvider a FormularioSugerencia
- **Archivo:** `src/components/FormularioSugerencia.tsx`
- **Problema:** No anuncia cambios a screen readers (WCAG 4.1.3)
- **Solucion:** Envolver en LiveRegionProvider como FormularioDenuncia
- **Estado:** [x] Completado
- **Fecha completado:** 2026-01-06
- **Nota:** Agregado import y wrapper LiveRegionProvider al componente exportado

### 1.4 Accesibilidad: Corregir role="menubar" en Header
- **Archivo:** `src/components/Header.tsx`
- **Problema:** Uso incorrecto de roles ARIA (WCAG 4.1.2)
- **Solucion:** Remover role="menubar" y role="menuitem"
- **Estado:** [x] Completado
- **Fecha completado:** 2026-01-06
- **Nota:** Removidos role="menubar", role="menu" y role="menuitem" de navegacion desktop y movil

### 1.5 Accesibilidad: Agregar aria-labelledby a SegmentedControl
- **Archivo:** `src/components/FormularioSugerencia.tsx`
- **Problema:** SegmentedControl sin label asociado (WCAG 1.3.1)
- **Solucion:** Agregar id al label y aria-labelledby al control
- **Estado:** [x] Completado
- **Fecha completado:** 2026-01-06
- **Nota:** Agregado id="metodo-verificacion-label" y aria-labelledby correspondiente

### 1.6 Accesibilidad: Corregir LoadingState
- **Archivo:** `src/components/ui/LoadingState.tsx`
- **Problema:** Loader sin role="status" ni aria-busy (WCAG 4.1.3)
- **Solucion:** Agregar atributos ARIA apropiados
- **Estado:** [x] Completado
- **Fecha completado:** 2026-01-06
- **Nota:** Agregado role="status", aria-busy, aria-label a ambas variantes (spinner y skeleton)

### 1.7 Seguridad: Agregar header HSTS
- **Archivo:** `vercel.json`
- **Problema:** Falta Strict-Transport-Security
- **Solucion:** Agregar header HSTS con preload
- **Estado:** [x] Completado
- **Fecha completado:** 2026-01-06
- **Nota:** Incluido en tarea 1.1

---

## Sprint 2 - Mejoras de Alta Prioridad

### 2.1 Rendimiento: Lazy loading para Leaflet
- **Archivos:** `src/components/MapaInteractivo.tsx`, `src/components/MapaLeaflet.tsx` (nuevo)
- **Problema:** Leaflet carga en bundle inicial
- **Solucion:** React.lazy() + Suspense
- **Estado:** [x] Completado
- **Fecha completado:** 2026-01-06
- **Nota:** Separado codigo Leaflet a MapaLeaflet.tsx, ahora carga en chunk separado via lazy()

### 2.2 Rendimiento: Usar hooks SWR en AdminDashboard
- **Archivo:** `src/components/admin/AdminDashboard.tsx`
- **Problema:** Usa useState/useEffect en lugar de hooks SWR existentes
- **Solucion:** Refactorizar a useDashboardStats()
- **Estado:** [x] Completado
- **Fecha completado:** 2026-01-06
- **Nota:** Reemplazado useState/useEffect por useDashboardStats() y useReports() de lib/swr.ts

### 2.3 Codigo: Unificar tipos duplicados
- **Archivos:** `src/lib/api.ts`, `src/lib/supabase.ts`, `src/types/index.ts`
- **Problema:** Interfaces duplicadas de types/index.ts
- **Solucion:** Eliminar duplicados, importar de types/
- **Estado:** [x] Completado
- **Fecha completado:** 2026-01-07
- **Nota:** api.ts ahora re-exporta tipos desde types/ para compatibilidad. supabase.ts importa Denuncia/Usuario de types/. Agregados campos contacto_* a PublicReportCreate.

### 2.4 Codigo: Centralizar STATUS_CONFIG
- **Archivos:** `src/components/ui/StatusBadge.tsx`, `src/components/admin/reports/ReportsPanel.tsx`
- **Problema:** STATUS_CONFIG duplicado en 3 lugares
- **Solucion:** Usar version de constants/index.ts
- **Estado:** [x] Completado
- **Fecha completado:** 2026-01-06
- **Nota:** StatusBadge ahora importa STATUS_CONFIG de constants/

### 2.5 Rendimiento: Centralizar imports CSS de Mantine
- **Archivos:** `src/components/AppProvider.tsx`, `src/components/MantineProvider.tsx`, `src/styles/mantine-imports.ts` (nuevo)
- **Problema:** CSS de Mantine importado multiples veces
- **Solucion:** Creado archivo central mantine-imports.ts, ambos providers importan desde ahi
- **Estado:** [x] Completado
- **Fecha completado:** 2026-01-06
- **Nota:** Consolidados 3 imports CSS en un solo archivo para evitar duplicacion

### 2.6 Codigo: Eliminar CUENCAS duplicado
- **Archivo:** `src/components/admin/analysis/AnalysisPanel.tsx`
- **Problema:** CUENCAS definido localmente, existe en constants/
- **Solucion:** Importar de constants/index.ts
- **Estado:** [x] Completado
- **Fecha completado:** 2026-01-06
- **Nota:** Eliminada definicion local, ahora importa CUENCAS desde constants/

### 2.7 Testing: Tests para formatters.ts
- **Archivo:** `tests/unit/formatters.test.ts`
- **Problema:** Tests existentes no coincidian con API actual (importaban funciones inexistentes)
- **Solucion:** Reescribir tests para coincidir con formatters.ts real
- **Estado:** [x] Completado
- **Fecha completado:** 2026-01-06
- **Nota:** Corregidos imports, actualizada API de formatDate, agregados tests para formatDateForInput

### 2.8 Testing: Tests para useContactVerification
- **Archivo:** `tests/hooks/useContactVerification.test.ts` (nuevo)
- **Problema:** Hook critico sin tests
- **Solucion:** Crear tests para validacion, timer, estados
- **Estado:** [x] Completado
- **Fecha completado:** 2026-01-06
- **Nota:** Tests completos para email, WhatsApp, timer, reset y estados

---

## Sprint 3 - Mejoras de Prioridad Media

### 3.1 Accesibilidad: Soporte teclado en MapaInteractivo
- **Archivo:** `src/components/MapaLeaflet.tsx`
- **Problema:** Features solo responden a mouse (WCAG 2.1.1)
- **Solucion:** Agregados handlers para focus/blur/keydown en features GeoJSON
- **Estado:** [x] Completado
- **Fecha completado:** 2026-01-06
- **Nota:** Features ahora focusables con tabindex, role=button, aria-label y Enter/Space

### 3.2 Accesibilidad: Usar AccessibleRadioGroup en FormularioDenuncia
- **Archivo:** `src/components/FormularioDenuncia.tsx`
- **Problema:** Radio buttons custom sin navegacion por flechas
- **Solucion:** Usar AccessibleRadioGroup de accessibility.tsx
- **Estado:** [x] Completado
- **Fecha completado:** 2026-01-06
- **Nota:** Reemplazado SimpleGrid+UnstyledButton por AccessibleRadioGroup, navegacion con flechas funcional

### 3.3 Accesibilidad: Mejorar aria-label de ThemeToggle
- **Archivo:** `src/components/ThemeToggle.tsx`
- **Problema:** Label estatico no indica estado actual
- **Solucion:** "Cambiar a modo claro/oscuro" segun estado
- **Estado:** [x] Completado
- **Fecha completado:** 2026-01-06
- **Nota:** aria-label ahora dinamico, placeholder indica "Cargando preferencia de tema"

### 3.4 Accesibilidad: Agregar aria-hidden a iconos decorativos
- **Archivo:** `src/components/ui/EmptyState.tsx`
- **Problema:** Iconos decorativos sin aria-hidden
- **Solucion:** Agregar aria-hidden="true"
- **Estado:** [x] Completado
- **Fecha completado:** 2026-01-06
- **Nota:** aria-hidden agregado al ThemeIcon contenedor

### 3.5 Accesibilidad: Envolver enlaces footer en nav
- **Archivo:** `src/components/Footer.tsx`
- **Problema:** Enlaces sin landmark nav
- **Solucion:** Agregar <nav aria-label="...">
- **Estado:** [x] Completado
- **Fecha completado:** 2026-01-06
- **Nota:** Agregado nav con aria-label="Enlaces del sitio" alrededor de los enlaces

### 3.6 Arquitectura: Extraer hook useFloodAnalysis
- **Archivos:** `src/hooks/useFloodAnalysis.ts` (nuevo), `src/components/admin/analysis/AnalysisPanel.tsx`
- **Problema:** Logica compleja mezclada con UI
- **Solucion:** Extraer a hook dedicado
- **Estado:** [x] Completado
- **Fecha completado:** 2026-01-06
- **Nota:** Hook creado con 180 lineas, AnalysisPanel reducido de 450+ a ~400 lineas enfocadas en UI

### 3.7 Testing: Crear mocks de Supabase
- **Archivo:** `tests/__mocks__/supabase.ts` (nuevo)
- **Problema:** No hay mocks para tests de auth
- **Solucion:** Crear mock completo del cliente
- **Estado:** [x] Completado
- **Fecha completado:** 2026-01-06
- **Nota:** Mock completo con auth, queries, storage, helpers para tests (190 lineas)

### 3.8 Testing: Tests de integracion LoginForm
- **Archivo:** `tests/components/LoginForm.test.tsx` (nuevo)
- **Problema:** Componente critico sin tests
- **Solucion:** Tests de validacion, submit, modos
- **Estado:** [x] Completado
- **Fecha completado:** 2026-01-06
- **Nota:** 18 tests cubriendo render, validacion, login, registro, OAuth, loading states

### 3.9 Rendimiento: Memoizar HomePage
- **Archivo:** `src/components/HomePage.tsx`
- **Problema:** Componente estatico sin memo
- **Solucion:** Envolver en React.memo()
- **Estado:** [x] Completado
- **Fecha completado:** 2026-01-06
- **Nota:** HomeContent ahora memoizado para evitar re-renders innecesarios

### 3.10 Codigo: Usar useLiveRegion en ReportsPanel
- **Archivo:** `src/components/admin/reports/ReportsPanel.tsx`
- **Problema:** Live region implementado manualmente
- **Solucion:** Usar hook existente de accessibility.tsx
- **Estado:** [x] Completado
- **Fecha completado:** 2026-01-06
- **Nota:** Reemplazado useRef+announceChange manual por useLiveRegion hook, envuelto en LiveRegionProvider

---

## Registro de Cambios

| Fecha | Tarea | Archivo(s) | Commit |
|-------|-------|------------|--------|
| 2026-01-06 | Documento creado | ROADMAP_MEJORAS.md | - |
| 2026-01-06 | 1.1 + 1.7: CSP corregido + HSTS agregado | vercel.json | - |
| 2026-01-06 | 1.2: Mejorado setup.ts con mocks adicionales | tests/setup.ts | - |
| 2026-01-06 | 1.3: LiveRegionProvider agregado | FormularioSugerencia.tsx | - |
| 2026-01-06 | 1.4: Roles ARIA incorrectos removidos | Header.tsx | - |
| 2026-01-06 | 1.5: aria-labelledby agregado a SegmentedControl | FormularioSugerencia.tsx | - |
| 2026-01-06 | 1.6: Atributos ARIA agregados a LoadingState | LoadingState.tsx | - |
| 2026-01-06 | 2.1: Lazy loading implementado para Leaflet | MapaInteractivo.tsx, MapaLeaflet.tsx | - |
| 2026-01-06 | 2.2: Refactorizado a hooks SWR | AdminDashboard.tsx | - |
| 2026-01-06 | 2.4: STATUS_CONFIG centralizado | StatusBadge.tsx | - |
| 2026-01-06 | 2.5: CSS imports centralizados | mantine-imports.ts, AppProvider.tsx, MantineProvider.tsx | - |
| 2026-01-06 | 2.6: CUENCAS duplicado eliminado | AnalysisPanel.tsx | - |
| 2026-01-06 | 2.7: Tests formatters corregidos | formatters.test.ts | - |
| 2026-01-06 | 2.8: Tests useContactVerification creados | useContactVerification.test.ts | - |
| 2026-01-06 | 3.1: Soporte teclado en mapa | MapaLeaflet.tsx | - |
| 2026-01-06 | 3.2: AccessibleRadioGroup implementado | FormularioDenuncia.tsx | - |
| 2026-01-06 | 3.3: aria-label dinamico en ThemeToggle | ThemeToggle.tsx | - |
| 2026-01-06 | 3.4: aria-hidden en EmptyState | EmptyState.tsx | - |
| 2026-01-06 | 3.5: nav landmark en Footer | Footer.tsx | - |
| 2026-01-06 | 3.6: useFloodAnalysis hook creado | useFloodAnalysis.ts, AnalysisPanel.tsx | - |
| 2026-01-06 | 3.7: Mocks de Supabase creados | __mocks__/supabase.ts | - |
| 2026-01-06 | 3.8: Tests LoginForm creados | LoginForm.test.tsx | - |
| 2026-01-06 | 3.9: HomePage memoizado | HomePage.tsx | - |
| 2026-01-06 | 3.10: useLiveRegion en ReportsPanel | ReportsPanel.tsx | - |
| 2026-01-07 | 2.3: Tipos unificados | api.ts, supabase.ts, types/index.ts | - |

---

## Notas

- Cada tarea se implementa individualmente
- Se documenta el avance antes de pasar a la siguiente
- Los tests se ejecutan despues de cada cambio
- Se mantiene compatibilidad hacia atras
