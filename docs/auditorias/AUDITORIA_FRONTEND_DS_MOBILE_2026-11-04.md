# Auditoría frontend — Design System & Mobile-First

Fecha: 2026-11-04
HEAD analizado: `0c443db6` (`origin/main`, post-#648)
Alcance: consorcio-web completo — sistema de diseño (inventario + coupling), readiness mobile-first superficie por superficie, y UX/a11y + arquitectura de acoplamiento para decisión de rediseño.
Método: 3 auditorías paralelas (design system, mobile, UX/coupling) sobre worktree limpio, read-only, evidencia path:line. Contexto de producto: `docs/strategy/exploracion-productos-2026-09.md` (expansión a consorcios camineros — operario de campo como usuario primario).
Precedente: no repite hallazgos de `AUDITORIA_CONSORCIO_CANALERO_2026-10-23.md` (cerrados); verifica su deuda residual.

---

## Resumen ejecutivo

Dos respuestas estratégicas, ambas con evidencia dura:

1. **El design system NO se cambia — se evoluciona in-place.** No hay sistema competidor que eliminar (cero tailwind/emotion/styled-components; un solo `theme.ts`, un solo punto de import CSS, 747 style-props homogéneos). Una migración paga ~156 archivos de churn + re-puentear 77 vars CSS del mapa para verse igual. El "look nuevo" se logra editando `theme.ts` (paletas, radius, tipografía, defaults) a una fracción del costo. La deuda real es chica y local (D1–D5 abajo).
2. **Mobile-first no es un rewrite — es cerrar gaps asimétricos.** El mapa 2D (superficie core) ya pasó pases móviles serios (bottom sheets, gestos cooperativos, endurecimiento 320px de #648, e2e con touch-targets medidos). Los gaps reales: el mapa embebido del formulario de denuncia (trampa de scroll en el flujo ciudadano core), foto camera-first, safe-areas, tablas sin virtualizar, e2e móvil fuera del mapa. Plan de 4 fases: **6–8 semanas**.

**Prerequisito transversal para CUALQUIER cambio visual mayor**: suite de regresión visual (`toHaveScreenshot`) — hoy NO existe. La red actual (537 assertions de comportamiento, 0 snapshots; matrix a11y de 4 engines) protege comportamiento, no apariencia.

---

## 1. Design system — inventario y veredicto

### Fortalezas (verificadas)

| Pieza | Estado | Evidencia |
|---|---|---|
| Theming | UNA fuente: `src/lib/theme.ts:17-325` (8 paletas "Tierra y Agua", rem tokens, defaults de 17 componentes) | `main.tsx:120-124` único provider |
| CSS | Un único punto de import (`styles/mantine-imports.ts`, decisión documentada); global.css 688 líneas con fallback fonts anti-CLS métrico-exactos, reduced-motion, print | — |
| Dark mode | Maduro: `auto` + manager custom con localStorage (`src/lib/mantine.ts:20-97`), overrides para Leaflet/inputs/scrollbars | Costo ya pagado |
| WCAG | AA con ratios medidos en comentarios (`theme.ts:114`, `global.css:216-218`) | — |
| Iconografía | Barrel central `ui/icons.tsx` ESM por-icon; 38 consumidores; 2 imports directos only | — |
| Idioma | es-AR voseo consistente: 18 marcadores voseo, 0 tuteo, 0 English en UI | — |
| Mapa | La superficie dura YA puenteada: `map.module.css` habla `var(--mantine-*)` (77 refs vs 6 hex crudos); controles nativos coherentes; `MapPanelShell` como shell único con contrato testeado | — |

### Split de styling (429 archivos src no-test)

- Mantine props API: ~36% (156 archivos) — approach dominante, casi puro props (0 `sx`, 10 `styles={{}}`)
- Inline styles: ~17% (concentrado en posicionamiento del mapa/z-index — legítimo)
- CSS Modules: ~6% (map.module.css 1855 líneas + header/footer/home/form)
- `mapColorTokens.ts` (179 hex, 65 consumidores): registro cartográfico deliberadamente separado de la paleta UI — deuda aceptada y documentada, no confundir con styling disperso

### Deuda del DS (ledger completo)

| # | Sev | Ubicación | Evidencia |
|---|---|---|---|
| D1 | MEDIA | `ui/SectionHeader.tsx`, `ui/StatCard.tsx`, `ui/PieChart.tsx` | Primitives con 0 consumidores; `sugerencias/StatsCard.tsx` duplica el concepto con otra API |
| D2 | MEDIA | `components/AppProvider.tsx` | Provider duplicado del árbol real (main.tsx); nadie lo importa; riesgo de drift |
| D3 | MEDIA | Finanzas/Tramites vs Reuniones/Padron panels | Mismo header visual con semántica distinta (`Title order={1}` vs `order={2}`); patrón copypaste sin primitive |
| D4 | BAJA | AdminDashboard.tsx:357,380,424; ReportsPanel.tsx:213 | 4-5 hex crudos de contraste — únicos fuera del dominio mapa |
| D5 | BAJA | useReportHighlight.ts:91 | Popup del mapa con DOM manual + fontSize inline, fuera de todo token |
| D6 | INFO | mapColorTokens.ts | Aceptada y documentada (dark mode de capas científicas es manual por diseño) |

### Veredicto DS

**Evolucionar in-place.** (1) No hay competitor que eliminar — migrar reescribe 196 imports/747 style-props/77 vars para verse igual. (2) El mapa (63 componentes + 1855 líneas CSS) ya está token-bridged a propósito — migrarlo es riesgo de regresión visual en la pantalla principal a cambio de cero mejora. (3) La deuda es de días, no de meses. Costo honesto de quedarse: CSS monolítico de Mantine (~30KB gzip, cacheado por SW) y el patch propio — ambos con trigger de revisión documentado.

---

## 2. Mobile-first — estado por superficie

### Lo que YA está (más de lo esperado)

- **PWA madura**: standalone, shortcuts `/mapa` + `/participacion`, SW autoUpdate con precache a dieta, tiles SWR con budget iOS 50MB, PII NetworkOnly (`vite.config.ts:118-409`)
- **Shell del mapa**: breakpoint único exportado + burger + overlay con rol dialog + focus mgmt + history-close (`MapWorkspace.tsx:221-256`); el complemento CSS 47.9375em resguardado por test
- **Bottom sheets ≤62em** con etapas peek/medio/alto + minimize-to-pill (`MapPanelShell.tsx:237-292`)
- **Gestos**: `cooperativeGestures` por pointer-type; floor táctil global 44px en coarse; inputs 16px anti-zoom iOS
- **Hazard móvil** con sheet propia + e2e; reflow landscape del mapa; mediciones/solera con toolbar inferior en coarse
- **#648 estableció EL patrón**: flex nowrap+truncate a 320px, regiones scrollables etiquetadas, floor táctil, semántica de headings — "endurecer lo existente, no agregar capas"

### Top-10 gaps (por impacto en operario de campo + ciudadano)

1. **Mapa embebido del denuncia** — SIN arbitraje táctil (trampa de scroll), 400px fijos, sin attribution (`report-form/LocationSection.tsx:128-146`) — EL flujo ciudadano core (M)
2. **Foto camera-first** — copy desktop-first ("Arrastrá una foto"), sin `capture` (S)
3. **`viewport-fit=cover` + safe-areas** — `env(safe-area-*)` hoy INERTO (0px); controles conviven con el home indicator iOS (S-M)
4. **Tablas sin virtualizar** (padrón/finanzas/reports) — jank en teléfonos; sin cards-on-mobile (L)
5. **E2e móvil fuera del mapa** — config general chromium desktop only; login/denuncia/admin sin 360px (M)
6. **Zoo de breakpoints** — 48em/62em/768px literal/47.9375em/30em en 3 sistemas; consolidar tokens (M)
7. **TerrainViewer3D sin pass móvil** — única superficie WebGL no auditada en touch (M)
8. **Install prompt PWA** — `beforeinstallprompt` Android sin capturar (S)
9. **Ergonomía ActiveLayers** — rows `xs` con iconos 12px en drawer móvil (S)
10. **Offline del submit** — SW 503 en POST offline; sin queue-and-retry ni estado visible (M)

### Plan por fases (total ~6–8 semanas)

| Fase | Contenido | Esfuerzo |
|---|---|---|
| 1. Fundación | viewport-fit=cover + re-audit anclados; foto capture+copy; install prompt; overscroll-behavior en canvas | ~1 sem (S) |
| 2. Flujo ciudadano | LocationSection (gestos+altura+attribution); e2e móvil /participacion + /login; estado offline submit | ~2 sem (M) — **ROI más alto** |
| 3. Operador/admin | Cards móviles reports/tramites; virtualización padrón; smoke admin 360px; fix 768px literal | ~2-3 sem (L) |
| 4. Pulido mapa | pass 3D; ergonomía ActiveLayers; tokens de breakpoints exportados | ~1-2 sem (M) |

---

## 3. UX/a11y + coupling

### Lo que #648 cerró (inventario)

11 clases de defecto: footer touch targets, jerarquía h1 por página (5 páginas), `RouterErrorFallback` role=alert, header admin móvil, landmark `main` duplicado, regiones scrollables, guards 320px, anti-zoom iOS, contraste placeholders, 2 fixes de color.

### Gaps a11y/UX restantes

| # | Sev | Hallazgo | Evidencia |
|---|---|---|---|
| A1 | MEDIA | Sidebar móvil del mapa `role="dialog" aria-modal` SIN focus trap ni fondo inert | `MapWorkspace.tsx:254` |
| A2 | MEDIA | Tres patrones de confirmación destructiva: POI delete SIN confirmación; reuniones/padrón con `window.confirm` nativo | — |
| A3 | MEDIA | 4 vocabularios de loading (Loader 31 / Skeleton 17 / wrapper 9 / Overlay 4) | — |
| A4 | BAJA | 76/90 toasts bypaslean `lib/notifications.ts` | — |
| A5 | INFO | Matrix a11y: salta 7/12 rutas admin; no ejercita pan de mapa con flechas | `tests/accessibility/a11y.spec.ts` |

### Coupling para rediseño

- 156/429 archivos importan Mantine (36%); top: Text 120, Stack 93, Group 87, Button 68 — la superficie de migración son LOS layout primitives
- Wrapper layer PARCIAL: `ui/` centraliza loading/empty/a11y, pero el substrato de layout es Mantine crudo en 150+ archivos
- **Deuda de octubre que SIGUE en pie (4/4)**: admin sin React Query (46 archivos hand-rolled), AppProvider muerto (D2), routeTree.gen manual, role en localStorage
- Red de regresión: fuerte en comportamiento (537 role/userEvent, 0 snapshots), **CERO regresión visual**

### Veredicto coupling

Posicionado mejor que el promedio para cambio a nivel TOKEN (theme centralizado, API de props pura, tests de comportamiento, gate a11y 4 engines). Migración a nivel COMPONENTE = 156 archivos sin colchón de wrappers y sin red visual. **Construir la suite visual y completar la capa de wrappers ANTES de cualquier rediseño estructural.**

---

## 4. Recomendación estratégica combinada

**Evolución en 3 movimientos (no migración):**

1. **Red de seguridad primero**: suite `toHaveScreenshot` (rutas clave × viewport 360/768/1280 × light/dark) + completar wrappers (PageHeader compartido que mata D3, LoadingState único que mata A3, toasts vía helpers que mata A4, borrar D1/D2). *Sin esto, ningún cambio visual es seguro.*
2. **El look se cambia en `theme.ts`**: si el objetivo de "cambiar el DS" es renovación estética (paleta Tierra y Agua → siguiente, radius, tipografía), es un ejercicio de theme + screenshot review, no de arquitectura. Incluye branding dinámico (hoy 100% estático — `Header.tsx:104-116`) como candidato natural si cada consorcio quiere su identidad.
3. **Mobile-first por las 4 fases** del §2, en orden — Fase 2 (flujo ciudadano) es el ROI más alto y conecta con la estrategia de producto: el operario del consorcio caminero (expansión 2026-09) trabaja desde el teléfono; mobile-first es canal de distribución, no cosmética.

**Lo que NO hacer**: migrar de lib de componentes (churn de 156 archivos, riesgo visual en el mapa, cero ganancia de usuario); agregar una segunda lib de estilos alongside Mantine; reescribir el shell del mapa (ya es el patrón de referencia).

---

## Ledger resumen

| Área | Cantidad | Destacados |
|---|---|---|
| DS debt | 6 (D1-D6) | primitives muertos, AppProvider dup, headers, 5 hex, popup |
| Mobile gaps | 10 (M1-M10) | denuncia map, camera-first, safe-areas, tablas, e2e, breakpoints, 3D, prompt, layers, offline |
| A11y/UX | 5 (A1-A5) | focus trap, destructivos, loading vocab, toasts, matrix gaps |
| Deuda previa vigente | 4 | admin sin RQ, AppProvider, routeTree, role storage |
| Prerequisito | 1 | suite de regresión visual (no existe) |

*Verificado en 0c443db6. Sin modificaciones de código durante la auditoría.*
