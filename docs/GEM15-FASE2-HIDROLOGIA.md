# GEM-15 Fase 2 — Hidrología comparada contra GLO-30 y la red real

Issue #723. Los números que el paper de GEM-15 no tiene, generados con el
mismo pipeline sobre el mismo AOI. Deciden la Fase 3 (#724).

Fecha de corrida: 2026-11-17. AOI: `zona_cc_ampliada` (~46 × 33 km, llanura
pampeana, Córdoba). Grilla común: EPSG:32720, 30 m, 1751 × 1264 celdas.

## Cadena de procesamiento

1. **Descarga same-grid** (`etl/gem15_fase2_download.py`): GLO-30
   (`COPERNICUS/DEM/GLO30`) y GEM-15 (`projects/climate-and-sustainability/
   assets/gem-15_v1`, banda `dtm`) del mismo AOI, `scale=30`, EPSG:4326.
   GEM-15 viaja a 30 m deliberadamente (comparación, no producto).
2. **Datum** (`etl/gem15_fase2_geoid.py`): EGM96 → EGM2008 ANTES de comparar,
   con las grillas del CDN de PROJ (`us_nga_egm96_15.tif`,
   `us_nga_egm08_25.tif`, SHA256 pineado, muestreo bilinear point-registered).
   Corrección N96−N08 sobre el AOI: **−0,21 a −0,28 m** (variable espacialmente
   — es la ondulación que puede redirigir flujo; un offset constante se
   cancelaría en la pendiente).
3. **Debias regional** (`etl/gem15_fase2_debias.py`): mediana de
   (GEM-15@EGM2008 − GLO-30) sobre terreno estable (rango focal 3×3 < 2 m en
   ambos DEMs):

   | Métrica | Valor |
   |---|---|
   | Offset regional | **+2,62 m** |
   | MAD | 0,77 m |
   | Celdas estables | 1.904.043 de 2.056.320 (92,6 %) |

   El offset es grande y la dispersión (MAD 0,77 m) es del orden de la
   pendiente misma de la llanura — el régimen donde el flujo derivado diverge.
4. **Pipeline WBT idéntico** (`etl/gem15_fase2_wbt.py`): GEM-15 debiased
   reproyectado SOBRE la grilla UTM exacta del GLO-30; para ambos:
   `fill_depressions` → `d8_pointer` → `d8_flow_accumulation(cells, pntr)` →
   cauces a umbral 100 celdas.
5. **Métricas vs red real** (`etl/gem15_fase2_metrics.py`): 6.029 puntos
   muestreados cada 30 m a lo largo de los 41 canales relevados
   (`etl/data/relevados.geojson`); distancia al cauce derivado más cercano.

## Resultados

### Concentración de escorrentía

| | GLO-30 | GEM-15 |
|---|---|---|
| Acumulación máxima (celdas) | 1.165.617 | 3.689 |
| Celdas de cauce (≥100) | 179.563 (8,7 %) | 4.466 (0,2 %) |

El GEM-15 apenas organiza drenaje en esta llanura: su DTM estéreo de 15 m
reasampleado a 30 m no converge la escorrentía en red dendrítica bajo el mismo
pipeline que al GLO-30 le da una red completa.

### Contra la red real de canales (la métrica que decide)

| | GLO-30 | GEM-15 |
|---|---|---|
| Desvío mediano | **1,41 celdas ≈ 42 m** | 759 celdas ≈ 22,8 km |
| Desvío p90 | 5,83 celdas ≈ 175 m | 1.023 celdas ≈ 30,7 km |
| Cobertura (≤ 2 celdas) | **62,3 %** | 0,0 % |

## Veredicto para la Fase 3

**GEM-15 NO es usable para hidrología en este terreno con un pipeline
estándar.** Ningún punto de la red relevada tiene un cauce derivado del GEM-15
a menos de 60 m; el desvío mediano es de ~23 km — las líneas de flujo no
tienen ninguna relación con el drenaje real. GLO-30, con el mismo pipeline,
reproduce el 62 % de la red dentro de 60 m y un desvío mediano de 42 m.

El fracaso no es de datum ni de debias (ambos corregidos antes de derivar): es la
capacidad del DTM estéreo de 15 m de representar pendientes submétricas en
llanura. Para la Fase 3 (#724): GLO-30 sigue siendo la base hidrológica;
GEM-15 queda confinado al perfil altimétrico comparativo de la Fase 1.

## Limitaciones

- Umbral de cauces fijo (100 celdas) para ambos, sin calibrar por DEM. Un
  umbral menor para GEM-15 agrega celdas de cauce pero no mueve el desvío
  mediano de órdenes de magnitud.
- Bordes del AOI: 0,9 % de celdas nodata en el GEM-15 reproyectado (la huella
  4326 no cubre exactamente la grilla UTM del GLO-30). No explica la
  diferencia (0,2 % vs 8,7 % de cauces).
- Eventos de crecida: fuera de alcance por decisión explícita (L3 del feature
  doc) — no hay registro sistemático; el análisis SAR queda como anexo
  cualitativo futuro.
- Reproducir: `docker compose exec backend python -m app.domains.geo.etl.
  {gem15_fase2_download, gem15_fase2_geoid, gem15_fase2_debias,
  gem15_fase2_wbt}` y `docker compose exec geo-worker python -m
  app.domains.geo.etl.gem15_fase2_metrics` (scipy solo está en geo-worker/dev).

## Gotchas técnicos descubiertos (aplican al pipeline productivo)

1. **WhiteboxTools v2.4.0 exige `--pntr`** en `d8_flow_accumulation` cuando el
   input es un D8 pointer. Sin el flag interpreta el pointer como DEM y
   devuelve basura silenciosa (~34 celdas de máximo). El
   `compute_flow_accumulation_impl` del pipeline NO lo pasa: la próxima
   corrida productiva que descargue un binario nuevo producirá flow_acc
   inválido y cero cruces derivados. Fix pendiente (toca código compartido).
2. **El lector GeoTIFF de WhiteboxTools no soporta PREDICTOR=3** (panic de
   Rust tragado por el wrapper de python como exit 0). Escribir rasters para
   WBT con predictor 2 o sin predictor.
3. El binario de WhiteboxTools NO viene en las imágenes: el wrapper de python
   lo descarga del release más reciente al primer uso — el comportamiento del
   pipeline depende de qué binario sea el latest ese día (pin pendiente).
