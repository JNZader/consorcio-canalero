# Informe de área — PR 3: dibujo y KML/KMZ en la selección

Objetivo: PR 3 del plan de informes. Branch: `feat/informe-area-pr3`. Base:
PR 2 mergeado (`754963c1`). Fuente: plan auditado (specs citadas verbatim).

## Specs

- S1 (plan, verbatim): "Sumar a la misma selección un polígono dibujado o un
  KML/KMZ, mezclado con subcuencas."
- S2 (alcance): "Pestañas Dibujar y Archivo en el paso Elegir; lectura del
  archivo en el navegador; aviso de partes fuera de zona y de polígonos
  separados." Fuera: "Shapefile, GPX o coordenadas sueltas (podés dejarlo
  anotado para después)."
- S3 (archivos, plan): crear `informeArea/SeleccionDibujo.tsx` (reusa
  `src/components/map/DrawControl.tsx`), `informeArea/SeleccionArchivo.tsx`,
  `src/lib/geo/leerKml.ts` y un web worker `leerKml.worker.ts`;
  **dependencia nueva `@tmcw/togeojson` (MIT)** — la única autorizada por el
  plan. Backend: "geometrías ya entra por el contrato del PR 1; solo
  validación extra" — el informe debe aceptar `zona_ids` + `geometrias`
  mezclados en el create (extender schemas/service del PR 2).
- S4 (parseo, plan verbatim): "KMZ: `jszip` abre y toma el primer `.kml`.
  KML a GeoJSON en el worker; quedarse con Polygon y MultiPolygon, sacar Z,
  cerrar anillos. Si son varios, `Checkbox` por polígono con su ha
  (`@turf/area`) para elegir cuáles. Tamaño máximo 10 MB y 20.000 vértices.
  El backend repara con `ST_MakeValid` y avisa cuánto quedó fuera de la
  zona del consorcio (`zona_cc_ampliada`)."
- S5 (UI): "`Dropzone` de `@mantine/dropzone` con texto 'Arrastrá un KML o
  KMZ, o tocá para elegirlo'; en el celular, botón que abre el selector de
  archivos. Error claro si no hay polígonos ('El archivo tiene solo puntos
  o líneas')."
- S6 (tests, plan verbatim): "Vitest con KML de prueba: uno simple, uno con
  varios polígonos, uno con huecos, un KMZ, uno sin polígonos y uno con
  coordenadas Z. Usá como prueba `campo_prueba_bellville.kml` u otro del
  consorcio. Pytest: polígono autointersectado se repara y mide bien."
- S7 (aceptación, plan verbatim): "Un KML de 5 MB se lee en menos de 2 s
  sin congelar la página; área del KML contra la vista previa con
  diferencia menor a 0,5 %."
- S8 (riesgos, plan): "KML de Google Earth con estilos raros o
  `MultiGeometry` anidado; archivos maliciosos (no evalúes nada, solo
  parseá XML)." OJO #741: el primer armado del DrawControl lazy no dibuja
  — reusa el recovery "Otro" o arregla #741 si el writer lo tiene a mano
  dentro de superficie.
- S9 (título, plan): `feat(informes): dibujo y carga de KML/KMZ en la
  selección de área`.

## Tasks

- T1 — Todo el PR en un writer: front (pestañas, worker, parseo, checkboxes
  ha, dropzone) + backend (create con geometrias mezcladas + ST_MakeValid +
  aviso fuera de zona) + tests S6 + medición S7. Route: delegated.

## Log

- L1 (2026-11-19, Javier): "dale....y prosigue hasta terminar todo" —
  maratón PR 3→6 tras merge #744.
