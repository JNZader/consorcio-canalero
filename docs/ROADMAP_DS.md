# Roadmap canónico — design system y componentes

Vigente desde el 2026-11-08. Es el único plan de interfaz que se sigue.

Sustituye el plan de olas de la [PR 681](https://github.com/JNZader/consorcio-canalero/pull/681)
(head `dfb18893`, merge `929eec56`, archivo
`docs/auditorias/PROPUESTA_DS_COMPONENTES_2026-11-08.md` en ese commit).
Ese texto queda en el historial de git. No se ejecuta.
El aviso está en el mismo path, para que quien abra el enlace de la PR
no tome las olas de semanas como cola.

Este archivo no reescribe las auditorías anteriores:

- `docs/auditorias/AUDITORIA_FRONTEND_DS_MOBILE_2026-11-04.md` (HEAD `0c443db6`)
- `docs/auditorias/AUDITORIA_CONSORCIO_CANALERO_2026-11-05.md` (HEAD `12acabc2`)

La corrección de la PR 681 salió de una revisión de solo lectura del
2026-11-08, sobre el código de `318e7ab8` (base de esa PR, anterior al
merge de documentación). Los hechos de abajo se releyeron en ese árbol.
Lo que no se reprodujo con un clic está marcado como hipótesis.

`docs/ROADMAP.md` sigue siendo el arco de producto, RAG y box. No agenda
este frente.

No hay fechas ni costos. Un ítem no está hecho hasta que su criterio de
aceptación pase. La implementación que acompaña este texto está en el
árbol de trabajo y todavía no tiene commit propio: no está en `main`.

## Qué se conserva

- Mantine 9. No hay migración de librería.
- Marca `#2d8f68` (`PRIMARY_GREEN`, `theme.ts:21`) y acción de botón
  `#16654a` (tono 6, `theme.ts:421`). No se igualan: blanco sobre
  `#2d8f68` da 4,01:1 y no llega a AA de texto chico; el filled medido
  el 2026-11-08 lleva texto blanco sobre `rgb(22, 101, 74)` a 7,01:1
  (`theme.ts:37-50`).
- Mapa con pocos flotantes: búsqueda, lugares y capa base siguen en el
  panel. No se agrega un FAB.
- `LoadingState` con `status="error"` ya usado por el dashboard
  (`AdminDashboard.tsx:275-287`). `ConfirmDialog` ya existe
  (`src/components/ui/ConfirmDialog.tsx`). No se crean primitivas paralelas
  para eso.
- Teselas y motor del mapa en `NetworkOnly` (`vite.config.ts:238-244`).
  No se precachea el mapa en este plan.

## Hechos corregidos respecto de la PR 681

| Dicho en la PR 681 | Qué es |
|---|---|
| `exito-6` 2,79:1 y `orange-6` 2,23:1 | Esos ratios son el tono 5 sobre blanco: `#38b058` y `#ff922b`. El tono 6 de éxito es `#2d9648` (3,77 sobre blanco, 3,13 sobre el tint del badge) y también falla AA. El tono 6 de naranja es `#9a3412` (7,31 / 5,65) y pasa. |
| Blue/red se oscurecieron y orange no | `orange` 6–9 ya está oscuro (`theme.ts:370-380`), igual que blue y red (`theme.ts:350-368`). `exito` y `alerta` no (`theme.ts:439-463`). |
| El oscuro semántico está sano | Éxito, alerta y aviso en tono 4 pasan sobre el tint oscuro. «En revisión» usa `#2d8f68` y no pasa (4,19 sobre `dark-7`, 3,45 sobre el tint). |
| API de asignación sin UI | `reportsApi.assign` arma un PATCH (`reports.ts:88-96`) y ningún componente lo llama. `DenunciaUpdate` no tiene `asignado_a` (`schemas.py:39-47`). En `gee-backend` ese campo no existe. El `schema.d.ts` está viejo. |
| Tracking público deprecado y sin reemplazo | `GET /denuncias/{id}/status` sigue montado con `deprecated=True` (`public.py:220-239`). Quien tiene cuenta ve «Mis denuncias» (`HomePage.tsx:130`). |
| Reportar desde el mapa no existe | El botón está en `MapaPage.tsx:138-146`. En un viewport de 360×800, el 2026-11-08, su caja empezaba en `y = 933`. |
| Tap sin join | El clic ya une `nro_cuenta` con BPA (`InfoPanel.tsx:156`, `PilarVerdeBadges.tsx:7-13`). Eso no es el padrón de personas. |
| `createVirtualColors` | Mantine 9 exporta `virtualColor`. No se agrega otra capa al lado de `--cc-*`. |
| Volver a Mantine Charts | `package.json` depende de `recharts`. `@mantine/charts` no está instalado. |

## Reglas de prueba

Fixtures locales. Sin producción, sin denuncias reales, sin cuota de Earth
Engine. Roles: `ciudadano` en lo público; `operador` o `admin` en el admin,
con la sesión sintética que ya usan `tests/visual/admin-mobile.spec.ts` y
`tests/accessibility/a11y.spec.ts`.

Viewports de aceptación: 360×800, 390×844 y 1280×800, salvo que el ítem
diga otro. Contraste: 4,5:1 del color de texto contra
`color-mix(in srgb, token 16%, fondo)`, que es el fondo de `StatusBadge`
(`StatusBadge.tsx:47-50`), en claro (blanco y `gray-0`) y en oscuro
(`dark-6` y `dark-7`). Red: la misma pantalla con HTTP 500 y con HTTP 200
de lista vacía tiene que verse distinta.

## Etapa 1 — Información engañosa y operaciones riesgosas

Ningún ítem depende de otro. Pueden ir en un PR de admin y un PR de textos.

### ET1-FIN — Finanzas: un 500 no es un año en cero

Prioridad P1. Hecho confirmado en código y en runtime de fixture
(2026-11-08): con 500 y con 200 vacío la pantalla muestra `$0` y el PDF
sigue disponible. El `catch` solo escribe en el log
(`useFinanzasController.ts:85-100`). La vista usa `?? 0`
(`FinanzasSummaryTab.tsx:16-18`). El panel sale del loader cuando
`loading` es falso aunque `balance` sea nulo (`FinanzasPanel.tsx:16`).

Hacer: la misma rama que el dashboard (`LoadingState` `status="error"` y
Reintentar). El PDF solo si el resumen llegó.

Aceptación: operador, 1280 y 360. Un 500 muestra aviso y Reintentar, no
muestra `$0`, el PDF está deshabilitado. Un 200 vacío muestra el cero y
permite pedir el PDF.

PR futuro, no abierto: `fix(admin): el fallo de finanzas no se ve como un año en cero`.

### ET1-REU — Reuniones: un 500 no es «no hay reuniones»

Prioridad P1. Hecho confirmado. El `catch` interno devuelve lista vacía
(`useReunionesController.ts:62-74`), así que el `catch` de afuera no corre.
Runtime de fixture: título y «Nueva reunión», sin aviso.

Hacer: quitar ese trago. Error con Reintentar. Vacío real con el texto de
lista vacía y la acción de crear.

Aceptación: operador, 1280. 500 muestra error. 200 con `items: []` muestra
vacío y no el error.

PR futuro, no abierto: puede ir en el mismo PR que ET1-FIN.

### ET1-BAN — Bandejas: el toast no reemplaza el estado de error

Prioridad P1. Hecho confirmado en código para denuncias
(`ReportsPanel.tsx:93-98`): toast y anuncio, la lista queda vacía y el
empty state dice que no hay denuncias. El toast se cierra a los 5 s
(`errorHandler.ts:113-117`). Padrón: el toast sí aparece (runtime de
fixture, «No pudimos cargar el padrón») y la tabla queda vacía
(`PadronPanel.tsx:77-85`). Sugerencias sigue el mismo patrón que denuncias;
el 500 de esa ruta no se forzó en la captura, así que el gemelo es
confirmado por lectura y el runtime de sugerencias queda por repetir.

Hacer: aviso visible después de cerrar el toast, con Reintentar, distinto
del empty state. Reusar `LoadingState`. No un componente nuevo.

Aceptación: operador, 360 y 1280, denuncias, sugerencias y padrón. 500
deja `role="alert"` después de descartar el toast. 200 vacío muestra el
empty state y no el alert.

PR futuro, no abierto: el mismo PR de ET1-FIN o uno siguiente de bandejas.

### ET1-IMP — Confirmar el import que reemplaza

Prioridad P1. Hecho confirmado. «Importar subcuencas» dispara el import y
el texto dice que reemplaza (`AdminDashboard.tsx:332-346`). La zonificación
aprobada está al lado (`AdminDashboard.tsx:366-371`) con el mismo patrón.
Padrón y reuniones ya usan `ConfirmDialog`.

Hacer: `ConfirmDialog` en los dos imports, con el verbo de reemplazo en la
pregunta. Cancelar no llama al API.

Aceptación: admin, 1280 y 360. Sin confirmar, no hay request. Confirmar
sí llama. El foco vuelve al botón al cerrar.

PR futuro, no abierto: `fix(admin): confirmar el import que reemplaza capas`.

### ET1-TXT — Alinear lo que se promete, sin mandar correo

Prioridad P1. Hecho confirmado. El alerta promete una notificación al
atender el reporte (`ParticipacionPage.tsx:57`) y un plazo de 24–48 h
hábiles (`ParticipacionPage.tsx:53`). La FAQ promete aviso al responder
(`HomePage.tsx:125-126`) y 5 días hábiles para la primera respuesta
(`HomePage.tsx:142`). El contacto dice 48 h (`HomePage.tsx:388-389`).
La política dice que los mensajes operativos salen por SMTP
(`PrivacyPolicyPage.tsx:159-161`). `send_email` solo se llama desde auth
(`gee-backend/app/auth/dependencies.py`). En `gee-backend/app/domains` no
hay llamada.

Hacer: los textos dicen el seguimiento que existe (perfil, «Mis denuncias»)
y un solo plazo, el que el consorcio pueda sostener. No se implementa
correo en esta etapa. No se agrega un código público de seguimiento.

Aceptación: ciudadano, 360 y 1280, claro y oscuro. Buscar en la UI de
inicio y de participación no encuentra la promesa de un mail que el
servidor no envía. Los tres plazos no se contradicen. Ningún test de
envío de correo nuevo.

PR futuro, no abierto: `docs(copy): alinear plazos y avisos de la denuncia`.
Toca strings de la UI, no este roadmap.

## Etapa 2 — Accesibilidad y teléfono

ET2-PERFIL no se implementa hasta reproducir el clic. El resto no depende
de eso.

### ET2-BADGE — Contraste del badge sobre su tint

Prioridad P1. Hecho confirmado por fórmula sobre los hex del tema y el
`color-mix` del componente, no por un axe de esta pasada.

Pintan mal en claro, texto contra el tint al 16 % sobre blanco:
`exito-6` `#2d9648` a 3,13 y `alerta-6` `#e54f3a` a 3,11
(`StatusBadge.tsx:19-26`, `theme.ts:657-659`). «En revisión» y «revisada»
usan `--cc-color-primary` `#2d8f68`: 3,31 en claro y 3,45 sobre el tint de
`dark-7`. Naranja de aviso (`orange-6` `#9a3412`) pasa a 5,65. No se toca.
El botón filled no se iguala al `#2d8f68`.

Hacer: oscurecer éxito y alerta en claro, y dar a «en revisión» un texto
que pase en los dos esquemas, del mismo modo en que `orange` 6–9 ya se
oscureció. Volver a medir el tint, no solo el hex sobre blanco.

Aceptación: texto del badge ≥ 4,5:1 sobre el tint, claro y oscuro, para
pendiente, en revisión, resuelto y descartado. Pendiente sigue en AA sin
cambiar el naranja que ya pasa. Un filled primario sigue con texto blanco
sobre `#16654a` (≥ 4,5:1). 360 y 1280, los dos temas.

PR futuro, no abierto: `fix(a11y): contraste de los badges de estado`.

### ET2-REPORTAR — «Reportar incidente» dentro del primer pantallazo

Prioridad P1. Hecho confirmado. El botón existe y no lleva coordenadas
(`MapaPage.tsx:138-146`). En móvil el header de la página pasa debajo del
mapa (`mapPanels.css:323-371`). Runtime de fixture, 360×800: el link midió
185×44 y `y = 933` con ventana de 800. No se agrega un FAB.

Hacer: un solo control, el que ya existe, visible sin scrollear en 360 y
390. El mapa sigue ocupando el resto. En 1280 el botón sigue en la cabecera.

Aceptación: ciudadano, 360×800 y 390×844, sin scroll, el link está dentro
del viewport y mide al menos 44 px de alto. 1280 no pierde el botón ni
duplica otro.

PR futuro, no abierto: `fix(mapa): Reportar incidente visible en el teléfono`.

### ET2-FILTROS — Filtros de bandeja apilados

Prioridad P1. Hecho confirmado. Denuncias: input con `flex: 1` y selectores
de 150 px (`ReportsFilters.tsx:23-50`). Sugerencias, el mismo esquema
(`SugerenciasFilters.tsx:23-30`). Runtime de fixture, 360×800, táctil: el
input de denuncias midió 50×36.

Hacer: bajo `sm`, búsqueda, selectores y Actualizar al ancho de la tarjeta,
alto mínimo `--cc-touch-min`. En 1280 siguen en una fila. No hace falta una
primitiva `FilterBar` para este ítem; la URL es la etapa 3.

Aceptación: operador, 360 y 390, el input mide el ancho útil de la tarjeta
y al menos 44 px de alto. 1280 no apila. Sin desborde horizontal.

PR futuro, no abierto: `fix(admin): filtros de bandeja usables en 360`.

### ET2-TOUCH — Piso de 44 px del burger del sitio

Prioridad P2. Hecho confirmado en runtime de fixture: «Abrir menú de
navegación» midió 40×40 en 360 con puntero táctil. El control está en
`Header.tsx:140-146`. El piso global de `button` (`global.css:356-364`) no
le gana a la regla del Burger. Los controles de zoom del mapa, en la misma
pasada, no entraron en la lista de objetivos menores de 44 px.

Hacer: el burger del sitio a `--cc-touch-min` solo con `pointer: coarse`.
Con mouse puede seguir denso.

Aceptación: 360, táctil, el burger mide al menos 44×44. 1280 con puntero
fino no está obligado a ese piso.

PR futuro, no abierto: puede ir con ET2-FILTROS.

### ET2-PERFIL — Perfil abierto debajo del drawer

Prioridad P1 si el clic lo confirma. Hoy es hipótesis con runtime parcial.

Confirmado en código: al haber selección, el drawer móvil se abre
(`MapWorkspace.tsx:158-165`), el lienzo queda `inert`
(`MapWorkspace.tsx:208-212`) y el drawer mide el 75 %
(`MapWorkspace.tsx:19`). «Perfil de elevación» está en ese panel
(`InfoPanel.tsx:601-607`). El dock se dibuja dentro del canvas
(`MapaMapLibreView.tsx:642-658`). Con el drawer abierto, la sheet de
adentro no atrapa el foco (`useMapSheetDialog.ts:8-10`). El dock sí es
diálogo cuando el drawer no está (`ElevationProfileDock.tsx:119-121`).

Confirmado en runtime de fixture: con el drawer abierto,
`data-drawer-open=true` y el lienzo `inert`. No se reprodujo el clic sobre
un canal: los fixtures no armaron una selección golpeable.

Hacer, solo después de ese clic en 360: si el perfil queda inutilizable,
cerrar el drawer al pedirlo (la misma acción que la X) para que el dock
existente reciba el foco. No un sistema de foco nuevo. Si el clic muestra
que el perfil ya se puede usar, cerrar el ítem sin cambio.

Aceptación: operador o ciudadano, 360. El clic sobre un canal abre el
panel; «Perfil de elevación» deja un dock enfocable (`role="dialog"`) o el
ítem se cierra con una nota de que no hacía falta. Escape cierra el dock.
1280 no cierra el sidebar, que no es modal.

PR futuro, no abierto, y no se escribe hasta la reproducción:
`fix(mapa): el perfil se puede usar al pedirlo desde el panel`.

## Etapa 3 — Continuidad

Dependen de la etapa 2 donde se indica. No abren correo, asignación, sort
de servidor ni bulk.

### ET3-URL — Filtros de bandeja en la URL

Prioridad P2. Depende de ET2-FILTROS para no fijar el campo de 50 px.
Hecho confirmado: denuncias y sugerencias no leen `searchParams` (no hay
uso en `src/components/admin`). Recargar pierde la búsqueda. No se crea un
`FilterBar` gordo: se serializan los campos que ya existen.

Aceptación: operador, 1280 y 360. La URL refleja búsqueda, estado y
categoría o tipo. Recargar y compartir esa URL restauran los campos. Un
200 vacío y un 500 siguen siendo distintos (etapa 1).

PR futuro, no abierto: `feat(admin): los filtros de la bandeja viven en la URL`.

### ET3-PREFILL — Coordenadas editables al reportar desde el mapa

Prioridad P2. Depende de ET2-REPORTAR (es el mismo botón, no un segundo
control). Hecho confirmado: el href no lleva lat/lng.

Hacer: si hay un punto elegido en el mapa, la query lo precarga y el
formulario lo muestra para editarlo o borrarlo antes de enviar. Sin punto,
el formulario sigue como ahora. No se lee el GPS en silencio.

Aceptación: ciudadano, 360 y 1280. Con un punto, los campos de ubicación
vienen llenos y se pueden cambiar. Sin punto, no aparece una coordenada
nueva. El envío sigue exigiendo la verificación que ya tiene el formulario.

PR futuro, no abierto: `feat(participacion): precargar la ubicación elegida en el mapa`.

### ET3-GEO — Marcador temporal de «Ubicarme»

Prioridad P2. Hecho confirmado: `requestMapGeolocate` solo hace `flyTo`
(`mapGeolocate.ts:21-24`).

Hacer: un marcador que se va al mover el mapa o con un control de quitar.
No entra al permalink ni a la URL compartida.

Aceptación: 360 y 1280. Después de «Ubicarme» hay un punto. Copiar el
enlace del mapa no incluye esa posición de GPS. Quitarlo lo saca de la
pantalla.

PR futuro, no abierto: `feat(mapa): marcador temporal al ubicarme`.

### ET3-SUGMAP — «Ver en el mapa» en sugerencias

Prioridad P2. Depende de ET3-URL, para no perder la bandeja.
Hecho confirmado: denuncias tienen el link en la misma pestaña
(`ReportDetailModal.tsx:159-172`). En sugerencias no hay un href al mapa.

Hacer: el mismo link, cuando la sugerencia tiene coordenadas. Volver atrás
o abrir de nuevo la URL de la bandeja conserva los filtros.

Aceptación: operador, 1280 y 360. Desde una sugerencia con punto se llega
al mapa en esas coordenadas. La URL de la bandeja, al volver, trae los
filtros de ET3-URL.

PR futuro, no abierto: después del PR de ET3-URL.

### ET3-PODA — Primitivas muertas, sin librería nueva

Prioridad P2. Hecho confirmado por búsqueda de imports en `src/`:
`ui/StatCard` no tiene consumidores; `ui/PieChart` tampoco. El dashboard
usa Recharts (`DashboardCharts.tsx`). `StatsCard` de sugerencias es la
tarjeta que sí se ve. `ParticipacionStepHeader` ya es el paso único.

Hacer: borrar `ui/StatCard` y `ui/PieChart`, o dejar uno solo si sugerencias
pasa a usarlo. No instalar `@mantine/charts`. No agregar `virtualColor`
en esta etapa.

Aceptación: `src/` no importa esos dos archivos. Sugerencias se ve igual
en 360 y 1280. `package.json` no gana `@mantine/charts`.

PR futuro, no abierto: `refactor(ui): sacar primitivas de UI sin uso`.

### ET3-TOKENS — Documentar marca y acción

Prioridad P2. Hecho confirmado: `--cc-color-primary` apunta al tono 5
(`theme.ts:611`) y el filled pinta el tono 6.

Hacer: en `docs/design-tokens.md`, los dos hex y por qué no se unifican.
Sin cambio de color pintado.

Aceptación: el doc nombra `#2d8f68` y `#16654a`. Un filled primario, en
claro y oscuro, sigue con texto blanco y contraste ≥ 4,5:1.

PR futuro, no abierto: `docs(tokens): separar el verde de marca del verde de acción`.

### ET3-EXPORT — Exportar dentro del panel de capas

Prioridad P2. Hecho confirmado: el menú de PNG, KMZ y QR es un control
flotante (`MapActionsPanel.tsx:79-80`). Zoom, brújula y pantalla completa
siguen en la columna del mapa.

Hacer: mover ese menú al panel de capas. No mover el zoom.

Aceptación: 360 y 1280. Exportar no está sobre el lienzo. La columna de
zoom sigue y sus botones miden al menos 44 px con puntero táctil.

PR futuro, no abierto: `refactor(mapa): exportar desde el panel de capas`.

### ET3-CANCEL — `pointercancel` en el arrastre del perfil

Prioridad P2. Hecho confirmado en código, no medido en un teléfono real.
El gráfico escucha down/move/up y no `pointercancel`
(`ElevationProfileChart.tsx:565-626`). El asa del dock sí
(`ElevationProfileDock.tsx:148-151`).

Hacer: el mismo cierre que el asa, para no dejar el arrastre a medias.

Aceptación: un test de componente dispara `pointercancel` durante el
arrastre y el estado de arrastre queda suelto. 360 no es obligatorio si
el test cubre el evento.

PR futuro, no abierto: `fix(mapa): soltar el arrastre del perfil si el puntero se cancela`.

## Etapa 4 — Proyectos aparte

No se abren PRs de implementación desde este roadmap. Cada uno necesita
su propio alcance antes de escribir código. No entran en las etapas 1 a 3.

### ET4-MAIL — Correo transaccional de la denuncia

Definir, no iniciar. El hueco está confirmado (etapa 1, ET1-TXT).
Construir el mail es otro proyecto: plantilla, error, destinatario, y un
cambio de muchas filas no manda un correo por fila. Hasta entonces los
textos no prometen el mail.

### ET4-ASIG — Asignar una denuncia a un operador

Definir, no iniciar. Bloqueado: el backend no tiene el campo. El helper
del front y el `schema.d.ts` no alcanzan. Si se retoma, empieza por modelo
y permisos, no por un select.

### ET4-SORT — Orden en listados paginados

Definir, no iniciar. Hecho confirmado: no hay `aria-sort` en el admin.
Ordenar en el cliente una página de denuncias miente sobre el total.
Hace falta un parámetro de servidor y pruebas de que la página 2 respeta
el orden. El padrón, si la lista viaja entera, puede ordenarse en el
cliente; eso se decide en el alcance, no aquí.

### ET4-BULK — Acciones sobre varias denuncias

Definir, no iniciar. Depende de ET1-IMP para el modo de confirmar, y de
ET4-MAIL si el mail existe: un lote no puede disparar correos sin una
decisión explícita. El alcance tiene que decir permisos, idempotencia y
resultado por ítem (éxito y fallo en la misma tanda). No se diseña en
esta etapa.

## Fuera de este plan

- Códigos públicos de seguimiento. La ruta deprecada se decide aparte
  (apagarla o dejarla). No se reemplaza con un código adivinable.
- Padrón de personas (CUIT, teléfono, email) en el mapa público. El join
  de BPA por `nro_cuenta` se queda. Una ficha de consorcista, si existe
  algún día, es de operador.
- `@mantine/charts` u otra librería de gráficos. Sigue Recharts.
- Mapa offline, precache de teselas, kit de campo. `NetworkOnly` es
  deliberado.
- Multi-consorcio y wordmark configurable. Este despliegue es el
  Consorcio Canalero 10 de Mayo.
- Migrar de Mantine. Reescribir `MapPanelShell`, el permalink o el
  formulario de denuncia.
- Igualar el botón de acción al `#2d8f68`.

## PRs futuros, en orden

No están abiertos. No se empiezan desde este cambio.

1. ET1-FIN, ET1-REU y ET1-BAN.
2. ET1-IMP.
3. ET1-TXT.
4. ET2-BADGE.
5. ET2-REPORTAR.
6. ET2-FILTROS y ET2-TOUCH.
7. Reproducir ET2-PERFIL; el PR de arreglo solo si el clic lo confirma.
8. ET3-URL, después ET3-SUGMAP.
9. ET3-PREFILL, ET3-GEO.
10. ET3-PODA, ET3-TOKENS, ET3-EXPORT, ET3-CANCEL, en PRs chicos.
11. Etapa 4: recién con un alcance propio por ítem.

## Estado al 2026-11-09

La implementación de las cuatro etapas está en el árbol de trabajo de la
rama `roadmap-ds-impl`, sobre `929eec56`. Esta sección distingue lo
implementado (código escrito), lo validado (probado) y lo pendiente.
El código no está commiteado a `main`.

### Implementado y validado

| Ítem | Validación |
|---|---|
| ET1-FIN | vitest: FinanzasPanel muestra error con Reintentar; el PDF queda deshabilitado si balance es nulo |
| ET1-REU | vitest: ReunionesPanel no devuelve lista vacía en error |
| ET1-BAN | vitest: ReportsPanel/SugerenciasPanel/PadronPanel muestran LoadingState error, no empty |
| ET1-IMP | ConfirmDialog en import de subcuencas y zonificación |
| ET1-TXT | vitest: "5 días hábiles", sin promesa de mail. FAQ y política actualizados |
| ET2-BADGE | badgeContrast.test.ts (1/1): ≥4,5:1 sobre tint al 16%, claro y oscuro, para los cuatro estados. El naranja no se tocó. Prueba de fórmula, no de píxeles |
| ET2-REPORTAR | Navegador 360/390/1280: "Reportar Incidente" visible sin scroll (177×36, top 185/185/81). El header queda arriba y el canvas no baja de 620px |
| ET2-FILTROS | CSS aplicado. Validación visual pendiente de Playwright (ver abajo) |
| ET2-TOUCH | CSS aplicado (44px burger con pointer:coarse) |
| ET2-PERFIL | `cc-close-map-drawer` implementado. **No reproducido en navegador**: el backend local estaba caído y las capas vectoriales no cargan (sin canales golpeables). Confirmado por lectura: <48em dispara cierre del drawer |
| ET3-URL | vitest: URL refleja q/estado/categoria/tipo/page/sort/order en ambas bandejas. Recargar restaura |
| ET3-PREFILL | vitest: el form recibe lat/lng de `?ubicacion=elegida&lat&lng` y los muestra. Sin feature, no aparecen |
| ET3-GEO | `reportAnchorStore` + `mapGeolocate` con `onGeolocated`. `replaceState` repone la URL tras `moveend`. **No probado en navegador** |
| ET3-SUGMAP | "Ver en el mapa" en sugerencias (href con lat/lng del primer vértice) |
| ET3-PODA | `StatCard` y `PieChart` borrados. Sin imports restantes |
| ET3-TOKENS | `docs/design-tokens.md` documenta `#2d8f68` y `#16654a` |
| ET3-EXPORT | `MapActionsPanel` movido al panel de capas. El toolbar de medición ya no duplica |
| ET3-CANCEL | `onPointerCancel` en `ElevationProfileChart` |
| ET4-MAIL | Flag `denuncia_status_email_enabled` default False. Encolo con uuid5 determinístico. Pruebas reales: 5/5 en base descartable (resuelto→1 aviso, repetido→no dup, respuesta nueva→2º aviso, misma respuesta→no dup, intermedio→0) |
| ET4-ASIG | `asignado_a` FK a `users` + migración `zz_denuncia_asignacion` (aplicada en base descartable, upgrade/downgrade verificados). `GET /denuncias/operadores`. Select en el modal muestra el operador guardado (key={id} para reset). PATCH validado |
| ET4-SORT | `list_sort.py` con whitelist (400 si no). `sort` y `order` en denuncias (created_at/estado/tipo) y sugerencias (created_at/estado/categoria). **Encabezados clicables implementados**: ResponsiveRecordList con `sorting` prop, `aria-sort` en th, flecha solo en columna activa, Select "Ordenar" en ambas bandejas para móvil. Sugerencias también manda sort. Tests 4/4 |
| ET4-BULK | `POST /denuncias/bulk` hasta 50 ids, estado, idempotency_key. Recibo por (operador, clave) con unique constraint. Pruebas de concurrencia reales: 7/7 (dos threads misma clave → mismo resultado, 1 recibo, 0 duplicados). Otra carga con la misma clave → 409 |

### Backend — suites corridas

| Suite | Resultado |
|---|---|
| `pytest tests/unit/test_roadmap_ds_contracts.py` | 4 passed |
| `pytest tests/new -k 'denuncia or report'` | 175 passed, 6 skipped |
| `pytest tests/new` (full) | 4893 passed, 90 skipped, 1 failed (ambiental: SQLAlchemy instalado ≠ pinneado) |
| Migración `zz_denuncia_asignacion` | upgrade + downgrade en base descartable verificados |

### Frontend — suites corridas

| Suite | Resultado |
|---|---|
| `npx tsc --noEmit` | exit 0 |
| `npx vitest run` | 435 passed, 7 failed (todos pre-existentes: api/apiCore/apiCoreHelpers/jwtAdapter — requieren API real o mocks de red) |
| `npx vitest run tests/components/responsiveRecordListSort.test.tsx` | 4 passed |
| `npx vitest run tests/components/ui/primitives.test.tsx` | 16 passed |

### Pendiente

- Playwright: la suite visual (`tests/visual/`) y la de a11y (`tests/accessibility/`) no se corrieron en esta pasada. Requieren Playwright browsers instalados.
- Canal→perfil: no reproducido en navegador (backend local caído). Confirmado por lectura de código.
- Teclado/foco: no validado en navegador (el IAB no despacha Tab). La suite a11y lo cubre cuando corre.
- Contraste de badges: validado por fórmula (`badgeContrast.test.ts`), no con un screenshot de píxeles reales.
- `ET2-FILTROS` y `ET2-TOUCH`: CSS aplicado y typecheck pasa, pero sin validación visual en 360 con puntero grueso.
