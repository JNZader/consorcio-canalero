# Auditoría + Propuesta — Design System, Componentes y UX

Fecha: 2026-11-08
HEAD analizado: `318e7ab8` (`origin/main`, post-#679)
Contexto: checkpoint limpio — los 3 CRITICALs de la auditoría #2 cerrados (#663/#664/#665), Río limpio aterrizada (#661/#666), 13 DOM de octubre liquidados (#673), cero PRs abiertos.
Método: 3 auditorías paralelas con **mandato de propuesta** (no de bugs): evolución del DS, componentes/UX, y journeys de usuario. Cada una con evidencia path:line.
Entregable: **los cambios propuestos**, rankeados y organizados en olas de ejecución.

---

## Resumen ejecutivo

El DS está sano y recién renovado (Río limpio, tokens `--cc-*`, hex-gate como ratchet) — la propuesta es **terminar la renovación**, no redo it. En componentes, la deuda es de primitivas faltantes (filtros, jerarquía de fichas, sorting, bulk) en paneles que ya hacen lo básico bien. En journeys, el hallazgo estructural: **el producto tiene capacidades medio-construidas** (asignación sin UI, email sin feedback loop, locate-me sin marcador, identify sin padrón) y **una promesa falsa de notificación** que es deuda de confianza. La costura estratégica: unir mapa y denuncia ("reportar desde donde estás parado") es la base del producto caminero del strategy doc.

**Cifras**: 1 defecto AA medido (semánticos en claro), 15 fricciones de componentes, 14 gaps de journey, **23 propuestas** condensadas en 4 olas.

---

## Parte 1 — Design System: terminar la renovación

### Estado (métricas)

- Adopción de tokens: `dimmed` sano (289 usos); **154 props crudos** de paleta base restantes (admin y map2d son las zonas sucias — 46 archivos); `--cc-*` nascente (13 tsx); hex en ts/tsx **casi cero** (gate funciona) pero **24 hex en `.css` fuera del gate**.
- El modelo `cssVariablesResolver` (alias `--cc-*` → `--mantine-*`, cero duplicación) es correcto y está testeado — **no tocar**.

### El defecto: AA falla en semánticos claros (medido WCAG)

`exito-6` 2.79:1, `alerta-6` 3.81:1, `orange-6` 2.23:1 sobre blanco — `theme.ts` oscureció blue/red [6-9] pero dejó estos. `StatusBadge` pinta texto con ellos → **AA small-text falla en modo claro**. En oscuro está sano (7.3–8.8:1). Fix: mismo tratamiento que blue/red (S).

### Propuestas DS (rankeadas)

| # | Propuesta | Esfuerzo | Unlock |
|---|---|---|---|
| DS-1 | Arreglar AA de exito/alerta/orange [6-7] en claro | S | Semánticos usables como texto/filled; estabilidad visual tests |
| DS-2 | `createVirtualColors` (success/danger/warning/info) — un idiom type-safe que reemplaza los 154 props crudos y el color-mix hand-rolled | M | Status consistente en Badge/Button/Alert/Chart; base para limpiar admin+map2d |
| DS-3 | Terminar dark del cromo del mapa: `rgba(36,36,36,…)` → `dark-6/7` verdoso + `popupSurface/popupText/popupClose` en mapChromeVars (cierra D5) | S-M | Mapa oscuro tan Río limpio como el resto |
| DS-4 | Tokens de motion + focus-ring (`--cc-duration/ease/focus-ring`) — hoy 4 duraciones de fly-to, focus azul hardcodeado sin decisión | S | Coherencia percibida; reduced-motion centralizado |
| DS-5 | Single source de status (fusionar STATUS_CONFIG + STATUS_COLOR_VAR + legacy) | S | Un estado nuevo = un archivo |
| DS-6 | Extender hex-gate a `.css` (24 hex, puerta trasera) | S | El ratchet cierra del todo |
| DS-7 | Decisión charts: volver a @mantine/charts para los 4 gráficos o documentar la receta recharts+clase (el drift actual es peor que ambas) | M | Sin workaround fill por caso |

### Ya está bien (no churn)

Hex-gate ratchet · resolver aliasing · CSS por componente con tests que pinean tokens (`designTokens.test.ts`).

---

## Parte 2 — Componentes: las primitivas que faltan

### Fricciones principales (de 15, las top)

- **F1/F2**: filtros duplicados a mano en las dos bandejas + **no viven en la URL** (refresh pierde todo; "denuncias abiertas de X" no es compartible — irónico: el mapa ya tiene permalink+QR).
- **F3**: cero bulk actions — 30 denuncias pendientes = 30 veces (abrir modal → select → registrar).
- **F5**: fichas móviles sin jerarquía (todas las columnas como pares iguales) ni tap completo — el patrón correcto ya existe en MyReportsSection.
- **F6/F7**: cero columnas ordenables; navegación por teclado solo cuando virtualiza.
- **F8**: el import de subcuencas del dashboard REEMPLAZA datos operativos sin ConfirmDialog.
- **F14**: forms admin sin guard de cierre (la denuncia ciudadana tiene draft — el estándar existe).

### Propuestas componentes (rankeadas por payoff÷esfuerzo)

| # | Propuesta | Esfuerzo | Beneficia |
|---|---|---|---|
| CP-1 | **`FilterBar` primitiva + sync URL** (search debounceado + selects, serializado a searchParams) — reemplaza las 3 implementaciones | S-M | Operador/admin — vistas compartibles = feature nueva |
| CP-2 | Fichas con jerarquía en ResponsiveRecordList (`cardFields`: línea primaria/estado/fecha; ficha entera tapable) | S | Operador móvil |
| CP-3 | Columnas ordenables (`sortable` en columns + `aria-sort`; server-side en bandejas, client en padrón) | S/M | Operador |
| CP-4 | **Bulk triage** (checkboxes + BulkActionBar flotante) | M | Operador — el gap de capacidad más grande del admin |
| CP-5 | Cerrar arco destructivo (ConfirmDialog en import; guard al cerrar forms sucios) | S | Admin |
| CP-6 | Vocab de stats unificado entre bandejas hermanas (hoy: Badges vs StatsCard) | S | Operador |
| CP-7 | Teclado siempre en listas (desacoplar del gate de virtualización) | S | A11y/operador |
| CP-8 | "Ver en mapa" en sugerencias (paridad con reports) | S | Operador |
| CP-9 | Migrar 27 Loaders crudos a LoadingState | S | Todos |
| CP-10 | Export CSV por bandeja (el dashboard ya exporta JSON) | M | Admin |

### Patrones ejemplares (no tocar)

`MapPanelShell` (el modelo documentado de primitiva) · permalink+QR del mapa · form de denuncia (estándar de resiliencia).

---

## Parte 3 — Journeys: capacidades medio-construidas y la costura estratégica

### J1 Ciudadano reporta (phone-first)

Flujo sólido post-#653 (2 pasos, GPS, cámara, tap-to-pin validado, idempotency, offline retry). Gaps: **sin tracking sin cuenta** (el route público está deprecado; hay que re-entrar con Google y saber ir a /perfil), **promesa de notificación falsa** (FAQ + alert lo prometen; `send_email` jamás dispara en denuncias), post-submit sin link a la denuncia creada.

### J2 Operador triagea (daily driver)

Bandeja funcional post-#663. Gaps: "Ver en el mapa" navega en la MISMA pestaña (pierde bandeja/filtros/página), **sin aging/SLA** (fecha absoluta, sin "hace X días", sin orden por antigüedad — pese a que la UI pública promete 24-48h), **asignación: API existe, UI cero**, fotos a 100px sin zoom.

### J3 Operador en campo (la estratégica)

**Ya existe más de lo esperado**: locate-me (flyTo), tap-to-identify con chips por entidad, búsqueda local de canales/parcelas, TramoSurveySheet como precedente de relevamiento. Gaps: **crear denuncia desde el mapa NO EXISTE** (dos apps separadas), `/mapa` no abre offline (NetworkOnly post-#667 — justo donde no hay señal), locate-me sin marcador persistente, parcela→padrón sin join.

### Cross-journey

Notificaciones: solo toasts; email existe como infra pero solo auth/invitaciones. **White-label**: branding sirve centro/zoom/cuencas PERO wordmark/title/hero hardcodeados — un consorcio nuevo = fork de código.

### Propuestas journey (top-6)

| # | Propuesta | Capacidad nueva | Esfuerzo |
|---|---|---|---|
| JR-1 | Columna "hace Xd" + color por vejez + sort por antigüedad | Gestión de SLA | Bajo |
| JR-2 | **Notificación real de cambio de estado** (email + respuesta) | Feedback loop ciudadano — corrige la promesa falsa | Bajo |
| JR-3 | **"Reportar desde el mapa"** (FAB → form con lat/lng prefill) | Denuncia in-situ — base del producto caminero (§B strategy) | Bajo-M |
| JR-4 | Código de seguimiento público (`/seguimiento?code=` anti-enumeración) | Recuperar denuncia sin cuenta | Medio |
| JR-5 | Mapa de la cola en la bandeja (pins + drawer, sin abandonar filtros) | Triage geográfico | Medio |
| JR-6 | Field-kit offline (basemap AOI + Background Sync + cola denuncias) | Operaciones sin señal — EL diferenciador vs Excel/WhatsApp para 285 consorcios | Alto |
| (+) | Locate-me persistente · tap→padrón (join Nro_Cuenta) · asignación UI · white-label externalization | Campo/accountability/multi-consorcio | Bajos/M |

---

## EL PLAN — 4 olas de ejecución

**Ola A — Quick wins (~1-2 semanas, todo S)**: DS-1 (AA) · JR-1 (aging/SLA) · JR-2 (email notificación — deuda de confianza) · CP-5 (destructivos) · CP-6 (stats) · CP-7 (teclado) · CP-8 (ver-en-mapa) · CP-9 (loaders) · DS-4 (motion/focus) · DS-5 (status single-source) · DS-6 (hex-gate CSS) · locate-me persistente.

**Ola B — Primitivas (~2-3 semanas)**: CP-1 FilterBar+URL · CP-2 fichas con jerarquía · CP-3 sorting · DS-3 (dark cromo mapa) · DS-7 (decisión charts). Cada una una PR con red-check visual (la suite #650 existe para esto).

**Ola C — Capacidades (~4-6 semanas)**: JR-3 reportar-desde-mapa (la costura) · JR-4 código seguimiento · JR-5 mapa de la cola · CP-4 bulk triage · asignación UI · tap→padrón · DS-2 virtual colors (acompaña la limpieza admin/map2d).

**Ola D — Diferenciadores (trimestre)**: JR-6 field-kit offline (generaliza draft+retry; cierra D6 de TramoSurvey) · white-label externalization (producto A multi-consorcio) · export CSV.

**Qué NO hacer**: migrar de Mantine (re-validado) · reescribir MapPanelShell/permalink/form-denuncia · agregar segunda lib de estilos · tokenizar mapColorTokens cartográficos (decisión documentada correcta).

---

*Evidencia completa en los reports de los 3 auditores (in-line en este documento). Verificado en 318e7ab8 sin modificaciones de código.*
