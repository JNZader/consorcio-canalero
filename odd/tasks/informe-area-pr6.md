# Informe de área — PR 6: KMZ y mapa de campo sin señal

Objetivo: PR 6 del plan — el ÚLTIMO. Branch: `feat/informe-area-pr6`. Base:
PRs 0-5 mergeados (`721885bd`). Fuente: plan auditado.

## Specs

- S1 (plan, verbatim): "Como en GeoCuenca: un KMZ para Google Earth y un QR
  en la portada del PDF que abre un mapa en el celular con GPS, dice en
  qué clase estás parado y funciona sin señal."
- S2 (alcance, plan): "KMZ del informe, paquete de campo por informe, ruta
  `/campo/:token` con MapLibre, service worker, QR en el PDF." Fuera:
  "Edición de datos en el campo, fotos o notas georreferenciadas."
- S3 (KMZ, plan verbatim): "Límite del área, subcuencas y una carpeta por
  tema (riesgo, drenaje, suelos, imágenes 2015/2017/2025) como overlays
  PNG georreferenciados o poligonos de `vectorize_zonal_classes`; solo un
  tema visible a la vez (`radioFolder`). Con `zipfile` y XML a mano; sin
  dependencias nuevas."
- S4 (paquete, plan): "Para áreas chicas: un JSON con clases vectorizadas
  (`vectorize_zonal_classes`), límites, leyenda y una imagen Sentinel-2 de
  fondo con sus bounds. Para áreas grandes: un PMTiles del recorte
  (decidí la herramienta; `tippecanoe` hoy se usa solo en el front por
  `npm run gen:pmtiles`). Tamaño objetivo menor a 15 MB."
- S5 (ruta, plan verbatim): "`/campo/:token` carga el paquete por
  `token_publico` (sin datos personales en la URL), lo guarda en Cache
  Storage al primer uso con una regla en `vite-plugin-pwa` (ver
  `pwaPrecachePolicy.ts`), y anda sin red."
- S6 (UI campo, plan): "MapLibre a pantalla completa;
  `navigator.geolocation.watchPosition` con alta precisión; punto azul y
  círculo de precisión; panel inferior con 'Tu posición: Alto · sector
  bajo…'; si la distancia al borde de la clase es menor que la precisión,
  aviso 'Estás en el límite entre Medio y Alto'. Tocar el mapa consulta
  ese punto con `queryRenderedFeatures`. Botón 'Centrar en mí'. Chips 'Sin
  señal · funciona igual'."
- S7 (QR, plan): "En la portada del PDF con
  `reportlab.graphics.barcode.qr` (ya viene con ReportLab); en pantalla,
  `qrcode` del front." La URL lleva el `token_publico` con vencimiento y
  revocación (PR 2: 90 días).
- S8 (tests, plan verbatim): "Playwright con geolocalización simulada y
  modo sin red: el panel muestra la clase correcta en tres puntos
  conocidos y el aviso de límite cerca de un borde. KMZ abre en Google
  Earth (prueba manual documentada) y pasa validación XML."
- S9 (aceptación, plan verbatim): "Con el teléfono en modo avión, después
  de un primer uso, el mapa abre en menos de 3 s y responde a la posición;
  paquete de una subcuenca menor a 15 MB."
- S10 (riesgos, plan): "Permisos de ubicación en iOS; tamaño de los
  paquetes; tokens públicos que nunca vencen (definí vencimiento y
  revocación)" — PR 2 ya definió 90 días; el token del campo hereda eso.

## Tasks

- T1 — Backend: KMZ (S3), paquete de campo (S4), token público (S5
  server), QR en PDF (S7). Route: delegated.
- T2 — Front: ruta `/campo/:token` + service worker + UI GPS (S5/S6).
  Route: delegated.
- T3 — Tests e2e S8 + medición S9 + cierre del plan. Route: parent.

## Log

- L1 (2026-11-19, Javier): maratón "hasta terminar todo" — PR 6 tras
  merge #749.
