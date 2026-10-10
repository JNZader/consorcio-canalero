# Fuentes de datos complementarias (investigación 2026-10)

Inventario para **sumar fuentes**, no para reemplazar el stack. La altimetría a ~30 m **se duplica a propósito**: cruzar GLO-30 vs IGN vs JAXA vs lidar puntual. No es “otra NASA”; es consistencia.

Ámbito: Consorcio Canalero 10 de Mayo (pampa cordobesa). Fecha de pesquisa: 2026-10-10.

## Qué ya entra (no volver a comprar)

| Capa / dato | Origen actual |
|---|---|
| Óptico + NDVI | Sentinel-2 vía GEE |
| SAR inundación | Sentinel-1 vía GEE |
| DEM operativo + perfil | Copernicus **GLO-30** (`COPERNICUS/DEM/GLO30`), `dem_filled` |
| Lluvia histórica / normal | **CHIRPS** v3 (spec lluvia v2) |
| Lluvia operativa / fallback | **IMERG**, SQPE, PERSIANN (gated por validación) |
| Suelos, catastro, vial oficial | **IDECOR** WFS / overlays |
| Obras hídricas oficiales | **APRHI** FeatureServer (view-only) |
| Hillshade 2D/3D | Mismo `dem_raw` terrain-rgb |

## Decisión

1. **Sí duplicar DEM** (mismas ~30 m) para chequeo de consistencia.
2. **Sí** humedad SAOCOM (IDECOR) y cobertura provincial 2024–2025.
3. **No** visores (EO Browser, EarthExplorer, Earthdata UI, Bhuvan).
4. **Rusia:** no hay capa abierta usable. China entra por **CBERS/INPE**, no por Gaofen.

---

## 1. Altimetría (varias fuentes, misma resolución)

Objetivo: perfil / hillshade / “¿este Z es un artefacto?”. GLO-30 es DSM/superficie rellena; varios km a la misma Z **no se curan** con otro 30 m.

| Fuente | País | Res | Tipo | Abierto | Rol |
|---|---|---|---|---|---|
| **GLO-30** | Copernicus | ~30 m | Superficie / filled | Sí (GEE) | **Producto** actual |
| **MDE-Ar v2.1** | IGN AR | ~30 m | SRTM+ALOS, vertical **SRVN16** | Sí, IGN | Cota **oficial argentina**. A/B vs GLO-30 |
| **AW3D30 v4.1** | JAXA | ~30 m | DSM óptico ALOS PRISM 2006–2011 | Sí, GEE `JAXA/ALOS/AW3D30` | Tercera pata Asia |
| **FABDEM** | UK/Copernicus | ~30 m | GLO-30 menos bosque/edificios | Research / términos | Mejor para **escurrimiento** que el DSM crudo |
| **NASADEM** | NASA | ~30 m | SRTM reprocesado | Sí, GEE | Cuarta pata; más viejo |
| **SRTM v3** | NASA/NGA | ~30 m | DSM 2000 | Sí | Baseline histórico, no operativo |
| **TanDEM-X 90 m** | DLR (DE) | 90 m | DSM X-band | Sí (90 m) | Más grueso; solo control regional |
| **GLO-90** | Copernicus | 90 m | | Sí | No aporta a canales |
| **ASTER GDEM** | NASA/METI | 30 m | Ruidoso | Sí | **No usar** |
| **ICESat-2 ATL08** | NASA | huellas | Lidar terreno/canopia | Sí, NSIDC | **Puntos** de verdad, no ráster |
| **GEDI** | NASA | huellas | Lidar (ISS) | Sí | Igual: validar Z, no DEM de mapa |
| OpenTopography / LiDAR aéreo | — | 1–5 m | | No hay vuelo local | Vacío para 10 de Mayo |
| IGN MDE aero 5 m | IGN AR | 5 m | Solo donde hay vuelo | Parcial AR | Chequear si el recorte Córdoba pampa existe; si no, skip |

**Cómo usarlo en producto:** selector “fuente de cota” en el perfil (GLO-30 / MDE-Ar / AW3D30) + RMSE vs ICESat-2 en el bbox del consorcio. Hillshade puede seguir en GLO-30.

---

## 2. Lluvia / clima

Spec lluvia v2 ya exige validación antes de promover fuente.

| Fuente | Origen | vs stack |
|---|---|---|
| CHIRPS v3 | UCSB / USGS | **Histórico** (ya) |
| IMERG V07 | NASA GPM | Fallback (ya) |
| PERSIANN | UCI | Evaluado en spec |
| SQPE / SINARAME RQPE | AR | Radar; spec lo admite **después** de validación |
| **GSMaP** | **JAXA** | Mismo problema que IMERG: satélite horario. Candidato de **consistencia** Asia, no reemplazo |
| ERA5 / ERA5-Land | ECMWF | Reanálisis ~9–31 km. Clima, no evento de canal |
| WorldClim | — | Normal 1970–2000. Redundante con CHIRPS normal |
| SMN estaciones / alertas | AR | Puntos + texto. No capa de mapa. Banner aparte |
| INA API / CIRSA | AR | Sierras (San Roque). **Fuera** de esta pampa |

---

## 3. SAR / humedad / agua en superficie

| Fuente | Origen | vs stack |
|---|---|---|
| Sentinel-1 | ESA | **Operativo** inundación (ya) |
| **SAOCOM** humedad | CONAE + **IDECOR mapa 87** | **Mejor candidato de capa nueva.** L-band AR, 7 días en Mapas Córdoba |
| PALSAR / PALSAR-2 mosaico anual | JAXA, GEE 25 m 2015–2024 | Histórico L-band, no “esta semana” |
| **NISAR** L-band | ISRO+NASA | Público **jul-2026** (ASF). Provisional. Misma física que SAOCOM |
| NISAR S-band | ISRO Bhoonidhi | Sample. No producción |
| JRC Global Surface Water | JRC/Copernicus | Ocurrencia 1984–2021 (Landsat). Complementa S1 (historia vs evento) |
| GloFAS | Copernicus EMS | ~11 km. Semáforo, no mapa de tramo |
| GFM (Copernicus flood) | EMS | Eventos globales; overlap con S1 propio |

---

## 4. Óptico / cobertura

| Fuente | Origen | vs stack |
|---|---|---|
| Sentinel-2 | ESA | **Default** (ya) |
| Landsat 8/9 | USGS | Más grueso; backup |
| **CBERS-4/4A + Amazônia-1** | China–Brasil, INPE STAC | ~16 m, ~31 días. **Peor que S2.** Backup no-GEE |
| Gaofen / Jilin | CN | No abierto |
| Resurs / Kanopus | RU | No abierto |
| Bhuvan / Cartosat | IN | India, no Córdoba |
| **Cobertura y uso suelo 2024–2025** | IDECOR + UNC | UMM 0,5 ha. **Provincial, mejor que cualquier global** |
| ESA WorldCover 10 m | ESA 2020/2021 | Global; peor que IDECOR acá |
| Dynamic World | Google/NRT 10 m | Casi-tiempo-real; ruidoso vs carta provincial |
| Globeland30 | China | 30 m. No gana a IDECOR |

---

## 5. Hidrografía / suelos / catastro (vector)

| Fuente | Origen | vs stack |
|---|---|---|
| Canales + cuencas propias | PostGIS / GEE basins | **Producto** |
| APRHI FeatureServer | Córdoba | Overlay obras (ya). Dataset datosabiertos.cba **404** en 2026-10-10 |
| IDECOR suelos 1:50k + agua disponible 1,5 m | Córdoba | Carta ya; **atributo** CAD nuevo (nov-2025) |
| SoilGrids | ISRIC 250 m | Global. No para parcela |
| IGN ANIDA hidrografía 1:250k | AR | Muy grueso vs red del consorcio |
| HydroSHEDS / HydroRIVERS | WWF | Global; no pisa el grafo local |
| OSM / IGN terciaria | ya overlays staff | Huecos de camino (ya) |

---

## 6. Asia / Rusia / India (cierre)

| | Abierto para Córdoba | Acción |
|---|---|---|
| **Japón** | AW3D30, PALSAR mosaico, GSMaP | Sí: DEM-B, lluvia-B, SAR histórico |
| **India** | NISAR L (ASF, 2026); S-band sample | Watch list, no UI ahora |
| **China–Brasil** | CBERS / Amazônia-1 INPE | Backup óptico |
| **China solo** | Gaofen, Fengyun | No / clima grueso |
| **Rusia** | — | Nada operativo |

---

## Prioridad de producto (si se implementa)

1. **Perfil multi-DEM:** GLO-30 + MDE-Ar + AW3D30 (mismo tramo, tres Z).
2. **SAOCOM humedad** WMS IDECOR, opt-in, con fecha.
3. **Cobertura IDECOR 2024–2025** WFS, opt-in.
4. **JRC water occurrence** como contexto de “dónde suele haber agua”.
5. **GSMaP** solo si entra al *source-resolution* de lluvia v2 (no un tercer gráfico suelto).
6. ICESat-2/GEDI: script de RMSE, no capa de mapa.
7. NISAR: reevaluar cuando deje de ser provisional.

## No hacer

Visores (EO Browser, EarthExplorer, Earthdata, Bhuvan). WorldClim. SoilGrids en ficha. GloFAS como capa de canales. ASTER GDEM. Satélites rusos. Gaofen.

## Referencias (consulta 2026-10-10)

- GLO-30 en producto: `README.md` (Copernicus DEM), pipeline DEM.
- Lluvia v2: `openspec/specs/rainfall-analysis/spec.md` (CHIRPS, IMERG, PERSIANN, SQPE/SINARAME).
- IDECOR cobertura 2024–2025: <https://www.idecor.gob.ar/cobertura-y-uso-del-suelo-de-la-provincia-de-cordoba-nuevo-mapa-2024-2025/>
- SAOCOM + IDECOR: <https://www.idecor.gob.ar/saocom-idecor-nuevo-mapa-de-humedad-de-suelo-en-cordoba/> mapa 87 Mapas Córdoba.
- MDE-Ar: <https://www.ign.gob.ar/NuestrasActividades/Geodesia/ModeloDigitalElevaciones/Introduccion>
- AW3D30: GEE `JAXA/ALOS/AW3D30/V4_1`; JAXA EORC.
- PALSAR yearly: GEE `JAXA/ALOS/PALSAR/YEARLY/SAR_EPOCH`.
- NISAR L público jul-2026: ASF DAAC / NASA Earthdata.
- CBERS: INPE STAC <https://data.inpe.br/stac/browser/>
- JRC GSW: GEE `JRC/GSW1_4/GlobalSurfaceWater`
- Exploración de producto (no repetir): `docs/strategy/exploracion-productos-2026-09.md`
