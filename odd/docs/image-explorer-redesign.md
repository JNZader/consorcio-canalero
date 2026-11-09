# Rediseño: Explorador de Imágenes (`/admin/images`)

**Estado:** propuesta (2026-11-09)  
**Contexto:** #690 productizó detección GEE flood en esta vista; en uso real la página se siente como un panel de API, no como herramienta de operador.  
**Alcance:** rediseño de **toda** la superficie de `/admin/images`, no solo la card de inundación.  
**Fuera de alcance:** cambios de contratos GEE/backend salvo los que el UX exija (p. ej. prefill de fechas desde un evento). Deploy de box y Pages no forman parte de las oleadas de UI.

---

## 1. Problema

Hoy `/admin/images` es un **taller de composición** que:

1. Mezcla tres trabajos distintos en una sola columna scroll (calendario + eventos CHIRPS + formulario GEE).
2. Tiene **tres UIs de fecha** desconectadas (día del calendario, fechas del evento, crecida/referencia del job).
3. Publica a stores compartidos (`useSelectedImage` / `useImageComparison`) pero **no lleva al mapa**: el éxito es un toast «Abrí /mapa».
4. Distingue mal **preview** (tile en el mapa chico) de **publicado** («Usar esta imagen» / Izquierda–Derecha).
5. Entierra acciones útiles (máscara de agua, Δ ha, shortlists) dentro de cards de evento con scroll de 480px.

Inventario actual (resumen): sensor + visualización + nubes/L7 → calendario → eventos extremos (shortlist, Δ agua, máscara, buscar imagen) → detección GEE suelta → preview MapLibre → barra de resultado (Usar / Izquierda / Derecha) → escenas L7 → banners de activo → leyenda.

---

## 2. Principios de diseño

1. **Un trabajo a la vez.** El operador elige modo; el resto no compite visualmente.
2. **Una selección de fechas compartida.** Calendario, evento y detección leen/escriben el mismo contexto (`contextoImagen`).
3. **Preview ≠ publicado.** El mapa de la derecha es borrador hasta que hay CTA explícito.
4. **El éxito navega.** Tras publicar imagen o par, CTA primario **«Abrir en mapa»** → `/mapa` en el `viewMode` correcto (`imagen` | `comparar`).
5. **Evento = atajo, no segundo producto.** Una crecida CHIRPS rellena fechas y ofrece acciones; no abre otro mini-explorador paralelo.
6. **Cero jerga de API en la UI.** Nada de `start_date` / `end_date` / enums crudos; copy en español de operador.

---

## 3. Modelo mental: tres trabajos

| Trabajo | Pregunta del operador | Resultado en `/mapa` |
|--------|------------------------|------------------------|
| **A. Elegir escena** | «¿Qué imagen pongo de fondo?» | Vista **Imagen** |
| **B. Comparar dos fechas** | «¿Qué cambió entre antes y después?» | Vista **Comparar** (slider) |
| **C. Detectar inundación** | «¿Dónde hubo agua entre crecida y normal?» | Vista **Comparar** con tiles de detección |

Los tres comparten: sensor/visualización cuando aplica, preview, y la **bandeja de publicación**.

---

## 4. Layout propuesto

```
┌─ Cabecera fija ─────────────────────────────────────────────┐
│ Título · tabs [Escena | Comparar | Detectar] · sensor/viz   │
│ Bandeja: Imagen activa | Par L/R | [Abrir en mapa] [Limpiar]│
└─────────────────────────────────────────────────────────────┘
┌─ Columna trabajo (≈40%) ──────┬─ Preview (≈60%) ────────────┐
│ Controles del tab activo      │ Mapa MapLibre + zona        │
│ + panel «Eventos» colapsable  │ Estado: borrador / publicado│
│                               │ Acciones contextuales       │
└───────────────────────────────┴─────────────────────────────┘
```

- **Tabs** reemplazan el stack vertical infinito.
- **Bandeja** siempre visible: es el contrato con `/mapa`.
- **Eventos de lluvia extrema** pasan a un drawer/acordeón lateral reutilizable desde los tres tabs (no solo abajo del calendario).

### 4.1 Tab Escena (trabajo A)

- Calendario de disponibilidad (como hoy).
- Click día → preview.
- Escenas individuales L7 debajo del preview o en un subpanel del tab.
- CTA: **«Usar esta imagen»** → llena bandeja imagen → habilita **Abrir en mapa**.

### 4.2 Tab Comparar (trabajo B)

- Dos slots: **Antes** y **Después** (nombres de operador; internamente left/right).
- Cada slot: elegir desde calendario, desde evento (Antes/Después shortlist), o «usar preview actual».
- CTA: **«Publicar comparación»** cuando ambos slots tienen tile → bandeja par → **Abrir en mapa** con `viewMode=comparar`.
- Eliminar botones opacos «Izquierda» / «Derecha» de la barra de resultado genérica.

### 4.3 Tab Detectar (trabajo C)

- Flujo guiado de 3 pasos en la misma columna:
  1. **Crecida** (fecha o «usar evento seleccionado»)
  2. **Referencia** (≥ 1 día después; default sugerido = crecida + 1 o post del evento)
  3. **Método** en lenguaje humano: «Fusión (recomendado)» / «Solo radar» / «Solo óptico»
- Botón **«Correr detección»** + progreso inline (sin pedirle que lea el id del job).
- Al completar: llena slots Antes=normal / Después=flood_detection → misma bandeja que Comparar → **Abrir en mapa**.
- Si el job no trae par: mensaje accionable («faltó escena»; sugerir Solo radar o otra referencia).

### 4.4 Panel Eventos (compartido)

Para cada crecida CHIRPS:

| Acción | Efecto |
|--------|--------|
| Seleccionar evento | Setea fechas de contexto; resalta en lista |
| Probar escena ranqueada | Preview en tab Escena (cambia sensor si hace falta) |
| Usar par Antes/Después | Rellena tab Comparar |
| Medir Δ agua / máscara | Overlay en preview (queda en Detectar o Comparar según contexto) |
| Buscar compuesto histórico | Preview + opción de publicar |

La detección GEE **no** es un formulario hermano: desde el evento, CTA **«Detectar inundación»** abre tab Detectar con fechas prellenadas.

---

## 5. Mapeo capacidad actual → destino

| Hoy | Destino |
|-----|---------|
| SegmentedControl sensores + Visualización + Nubes + Modo L7 | Cabecera (visibilidad según tab/sensor) |
| Calendario | Tab Escena (+ slots de Comparar) |
| Eventos de lluvia extrema + shortlists + Δ + máscara + Buscar imagen | Panel Eventos compartido |
| Card Detección de inundación (GEE) | Tab Detectar (+ CTA desde evento) |
| Mapa preview + Ver zona completa | Columna preview |
| Usar esta imagen / Izquierda / Derecha | Bandeja + CTAs por tab |
| Escenas individuales | Subpanel Tab Escena (L7) |
| Banners «Imagen activa» / «Comparacion activa» + «Ve al Mapa» | Bandeja con **Abrir en mapa** real |
| Leyenda Visualizaciones | Footer colapsable del preview |

**Stores y APIs que se mantienen:** `useSelectedImage`, `useImageComparison`, `/geo/gee/images/*`, `POST/GET /geo/gee/analysis` tipo flood, shortlists, water-delta, historic-floods. Sin renombrar contratos en oleada 1.

---

## 6. Copy (español operador)

| Evitar | Preferir |
|--------|----------|
| Abrí /mapa con el slider | Abrir en mapa |
| Fecha de referencia (normal) + start_date | Fecha sin agua (después de la crecida) |
| Método fusion / sar_only | Fusión (recomendado) / Solo radar / Solo óptico |
| Izquierda / Derecha | Antes / Después |
| Comparacion activa (Ve al Mapa…) | Par listo · Abrir en mapa |
| Correr detección | Detectar inundación |

---

## 7. Oleadas de entrega

### Oleada 1 — Esqueleto IA + bandeja + navegación (PR1)

- Tabs Escena | Comparar | Detectar (Detectar puede ser shell que rehostea la card actual).
- Bandeja persistente + botón **Abrir en mapa** (`navigate` + set `viewMode`).
- Mover layout a cabecera / trabajo / preview; sin reescribir eventos todavía.
- Tests: bandeja refleja stores; CTA navega con mode correcto.
- **Éxito medible:** el operador ya no necesita recordar la URL `/mapa`.

### Oleada 2 — Eventos como panel de atajos (PR2)

- Extraer `ImageExplorerExtremeEvents` a panel compartido.
- Selección de evento escribe `contextoImagen`.
- CTAs: probar escena, usar par, detectar (deep-link a tab Detectar).
- Tests: prefill fechas; shortlist → preview.

### Oleada 3 — Detectar integrado + limpieza Comparar (PR3)

- Wizard 3 pasos; eliminar card API-shaped.
- Tab Comparar con slots Antes/Después; retirar Izquierda/Derecha genéricos.
- Copy final; empty/error states accionables.
- Tests: submit→poll→bandeja; span ≥1; fallos sin tiles.

Cada oleada: PR enfocado, squash-merge, Pages; **sin** deploy de box salvo que toque `gee-backend`.

---

## 8. Riesgos y no-negociables

- **Tiles GEE expiran:** `/mapa` ya regenera desde params; no guardar solo `tile_url` como verdad eterna.
- **Resets destructivos** (cambio de sensor/nubes limpia día): en tabs, confirmar o preservar slots del otro trabajo.
- **Permisos:** sigue siendo ruta operador+; no abrir detección a ciudadano.
- **Cuota GEE:** progreso y cancelación visibles; no disparar jobs al cambiar de tab.
- **Mobile:** tabs + preview apilados; bandeja sticky abajo.

---

## 9. Criterios de aceptación (producto)

1. Un operador nuevo puede publicar una escena al mapa en **≤3 clics** tras elegir el día (sin leer tooltips).
2. Un par antes/después se publica y **abre `/mapa` en Comparar** con un solo CTA.
3. Desde un evento CHIRPS se puede lanzar detección **sin retipear fechas**.
4. No queda visible ninguna etiqueta `start_date` / `end_date` / id de job truncado como UX primaria.
5. La card suelta «Detección de inundación (GEE)» deja de existir como bloque hermano del calendario.

---

## 10. Próximo paso

Aprobar esta propuesta → implementar **Oleada 1** en branch `feat/image-explorer-shell` (o nombre equivalente) desde `origin/main`.
