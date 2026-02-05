# Fase 2: Modelado Hidrologico con GRASS GIS

## Vision General

La Fase 2 extiende las capacidades de la aplicacion agregando analisis hidrologico avanzado mediante GRASS GIS. Mientras que Google Earth Engine (Fase 1) proporciona imagenes satelitales y deteccion de agua en tiempo real, GRASS GIS agrega modelado de terreno, simulacion de flujos y prediccion de inundaciones.

### Diferencia clave

| Aspecto | GEE (Fase 1) | GRASS GIS (Fase 2) |
|---------|--------------|---------------------|
| **Enfoque** | "Que esta pasando ahora" | "Por que pasa y que pasara" |
| **Datos** | Imagenes satelitales | Modelos de elevacion (DEM) |
| **Salida** | Mapas de agua/vegetacion | Cuencas, flujos, predicciones |
| **Procesamiento** | Cloud (servidores Google) | Local (contenedor Docker) |

---

## Por que GRASS GIS

1. **Open Source y maduro**: 40+ anos de desarrollo, usado por agencias gubernamentales
2. **Completa suite hidrologica**: r.watershed, r.drain, r.terraflow
3. **Integracion Python**: API completa via `grass.script`
4. **Reproducible**: Resultados consistentes, sin limites de uso
5. **Offline**: Funciona sin conexion a internet

### Alternativas consideradas

- **QGIS**: Excelente como GUI, pero GRASS tiene mejor API para automatizacion
- **WhiteboxTools**: Rapido pero menos completo en hidrologia
- **TauDEM**: Solo flujos, no tiene analisis de cuencas completo

---

## Arquitectura Propuesta

```
                    +------------------+
                    |   consorcio-web  |
                    |   (Astro/React)  |
                    +--------+---------+
                             |
                             v
                    +--------+---------+
                    |   gee-backend    |
                    |    (FastAPI)     |
                    +--------+---------+
                             |
              +--------------+--------------+
              |                             |
              v                             v
    +---------+----------+       +----------+---------+
    |   GEE Service      |       |   GRASS Service    |
    | (Imagenes, NDWI)   |       | (Hidrologia, DEM)  |
    +--------------------+       +--------------------+
              |                             |
              v                             v
    +---------+----------+       +----------+---------+
    |  Google Earth      |       |   GRASS GIS        |
    |     Engine         |       |   (Docker)         |
    +--------------------+       +--------------------+
```

### Nuevo contenedor: grass-processor

```yaml
# docker-compose.yml (extension)
services:
  grass-processor:
    build:
      context: ./grass-processor
      dockerfile: Dockerfile
    volumes:
      - ./data/dem:/data/dem:ro           # DEMs de entrada
      - ./data/outputs:/data/outputs      # Resultados
      - grass-db:/grassdb                 # Base de datos GRASS
    environment:
      - GRASS_BATCH_JOB=1
    networks:
      - consorcio-network

volumes:
  grass-db:
```

### Dockerfile para GRASS GIS

```dockerfile
FROM mundialis/grass-py3-pdal:8.4-ubuntu

# Dependencias adicionales
RUN apt-get update && apt-get install -y \
    python3-pip \
    gdal-bin \
    && rm -rf /var/lib/apt/lists/*

# Paquetes Python
RUN pip3 install \
    fastapi \
    uvicorn \
    rasterio \
    geopandas \
    shapely

# Scripts de procesamiento
COPY scripts/ /app/scripts/
COPY api/ /app/api/

WORKDIR /app

EXPOSE 8001

CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8001"]
```

---

## Funcionalidades de Fase 2

### 1. Delimitacion de Cuencas (Watershed Delineation)

**Objetivo**: Calcular automaticamente los limites de las cuencas hidrograficas.

```python
# grass_service.py
import grass.script as gs

def delineate_watershed(dem_path: str, outlet_coords: tuple) -> dict:
    """
    Delimita cuenca desde un punto de salida.

    Args:
        dem_path: Ruta al DEM (GeoTIFF)
        outlet_coords: (lon, lat) del punto de salida

    Returns:
        GeoJSON de la cuenca delimitada
    """
    # Importar DEM
    gs.run_command('r.in.gdal', input=dem_path, output='dem', overwrite=True)

    # Calcular direccion de flujo y acumulacion
    gs.run_command('r.watershed',
        elevation='dem',
        drainage='flow_dir',
        accumulation='flow_acc',
        basin='basins',
        threshold=1000,
        overwrite=True
    )

    # Extraer cuenca desde punto de salida
    gs.run_command('r.water.outlet',
        input='flow_dir',
        output='watershed',
        coordinates=outlet_coords,
        overwrite=True
    )

    # Vectorizar y exportar
    gs.run_command('r.to.vect',
        input='watershed',
        output='watershed_vec',
        type='area',
        overwrite=True
    )

    return export_to_geojson('watershed_vec')
```

**Endpoint API**:
```
POST /api/v1/hydro/watershed
Body: { "outlet": [-62.68, -32.63] }
Response: { "geojson": {...}, "area_km2": 245.7 }
```

### 2. Direccion y Acumulacion de Flujo

**Objetivo**: Visualizar como fluye el agua sobre el terreno.

```python
def calculate_flow_network(dem_path: str, threshold: int = 500) -> dict:
    """
    Calcula red de drenaje.

    Args:
        dem_path: Ruta al DEM
        threshold: Celdas minimas para formar un canal

    Returns:
        GeoJSON de la red de drenaje
    """
    gs.run_command('r.in.gdal', input=dem_path, output='dem', overwrite=True)

    gs.run_command('r.watershed',
        elevation='dem',
        accumulation='flow_acc',
        stream='streams',
        threshold=threshold,
        overwrite=True
    )

    # Vectorizar streams
    gs.run_command('r.to.vect',
        input='streams',
        output='stream_network',
        type='line',
        overwrite=True
    )

    return export_to_geojson('stream_network')
```

**Endpoint API**:
```
GET /api/v1/hydro/flow-network?threshold=500
Response: { "geojson": {...}, "total_length_km": 127.3 }
```

### 3. Simulacion de Inundacion

**Objetivo**: Simular niveles de agua para diferentes escenarios.

```python
def simulate_flood(dem_path: str, water_level: float, origin: tuple = None) -> dict:
    """
    Simula inundacion por nivel de agua.

    Args:
        dem_path: Ruta al DEM
        water_level: Nivel de agua en metros (relativo al terreno mas bajo)
        origin: Punto de origen opcional

    Returns:
        GeoJSON de area inundada
    """
    gs.run_command('r.in.gdal', input=dem_path, output='dem', overwrite=True)

    # Obtener elevacion minima
    stats = gs.parse_command('r.univar', map='dem', flags='g')
    min_elev = float(stats['min'])

    # Crear superficie de agua
    flood_level = min_elev + water_level
    gs.mapcalc(f"flood_area = if(dem < {flood_level}, {flood_level} - dem, null())")

    # Vectorizar
    gs.run_command('r.to.vect',
        input='flood_area',
        output='flood_polygon',
        type='area',
        overwrite=True
    )

    # Calcular estadisticas
    stats = gs.parse_command('r.univar', map='flood_area', flags='g')

    return {
        "geojson": export_to_geojson('flood_polygon'),
        "area_km2": float(stats.get('n', 0)) * cell_resolution**2 / 1e6,
        "max_depth_m": float(stats.get('max', 0)),
        "avg_depth_m": float(stats.get('mean', 0))
    }
```

**Endpoint API**:
```
POST /api/v1/hydro/simulate-flood
Body: { "water_level": 2.5, "origin": [-62.68, -32.63] }
Response: {
  "geojson": {...},
  "area_km2": 45.2,
  "max_depth_m": 2.5,
  "avg_depth_m": 1.2
}
```

### 4. Analisis de Riesgo por Parcela

**Objetivo**: Evaluar riesgo de inundacion para cada parcela/lote.

```python
def analyze_parcel_risk(dem_path: str, parcels_geojson: dict) -> list:
    """
    Analiza riesgo de inundacion por parcela.

    Returns:
        Lista de parcelas con metricas de riesgo
    """
    results = []

    for feature in parcels_geojson['features']:
        parcel_id = feature['properties']['id']

        # Estadisticas de elevacion en la parcela
        # ... (codigo de analisis zonal)

        results.append({
            "parcel_id": parcel_id,
            "min_elevation_m": min_elev,
            "avg_elevation_m": avg_elev,
            "flow_accumulation_max": max_acc,
            "risk_score": calculate_risk_score(...),
            "risk_level": "alto" | "medio" | "bajo"
        })

    return results
```

**Endpoint API**:
```
POST /api/v1/hydro/parcel-risk
Body: { "parcels": <GeoJSON> }
Response: [
  { "parcel_id": "P001", "risk_level": "alto", "risk_score": 0.85 },
  { "parcel_id": "P002", "risk_level": "bajo", "risk_score": 0.15 }
]
```

### 5. Perfil de Elevacion

**Objetivo**: Visualizar perfil topografico a lo largo de un transecto.

```python
def get_elevation_profile(dem_path: str, start: tuple, end: tuple) -> dict:
    """
    Extrae perfil de elevacion entre dos puntos.
    """
    gs.run_command('r.in.gdal', input=dem_path, output='dem', overwrite=True)

    # Crear linea de transecto
    gs.run_command('v.in.lines',
        input=f"{start[0]},{start[1]}|{end[0]},{end[1]}",
        output='transect',
        overwrite=True
    )

    # Extraer perfil
    profile_data = gs.read_command('r.profile',
        input='dem',
        coordinates=f"{start[0]},{start[1]},{end[0]},{end[1]}",
        null_value='*'
    )

    return parse_profile_data(profile_data)
```

**Endpoint API**:
```
POST /api/v1/hydro/elevation-profile
Body: { "start": [-62.70, -32.62], "end": [-62.65, -32.65] }
Response: {
  "distance_m": [0, 100, 200, ...],
  "elevation_m": [125.3, 124.8, 123.2, ...],
  "min_elevation": 120.5,
  "max_elevation": 128.7
}
```

---

## Integracion con Fase 1 (GEE)

### Flujo combinado: Analisis de inundacion completo

```
1. Usuario selecciona fecha de inundacion
        |
        v
2. GEE: Obtener imagen satelital (Sentinel-2 o SAR)
        |
        v
3. GEE: Detectar agua con MNDWI/NDWI
        |
        v
4. GRASS: Comparar con modelo de flujo
        |
        v
5. GRASS: Identificar areas de acumulacion
        |
        v
6. Resultado: Mapa combinado con:
   - Agua detectada (satelite)
   - Prediccion de flujo (modelo)
   - Parcelas en riesgo
```

### Nuevo componente: FloodAnalysisPanel

```typescript
// components/analysis/FloodAnalysisPanel.tsx
import { useState } from 'react';
import { useMutation, useQuery } from '@tanstack/react-query';

export function FloodAnalysisPanel() {
  const [selectedDate, setSelectedDate] = useState<Date | null>(null);
  const [waterLevel, setWaterLevel] = useState(1.0);

  // Obtener imagen satelital (GEE)
  const satelliteImage = useQuery({
    queryKey: ['satellite', selectedDate],
    queryFn: () => fetchSatelliteImage(selectedDate),
    enabled: !!selectedDate
  });

  // Simular inundacion (GRASS)
  const floodSimulation = useMutation({
    mutationFn: (level: number) => simulateFlood(level)
  });

  // Analizar parcelas (combinado)
  const parcelAnalysis = useMutation({
    mutationFn: () => analyzeParcelRisk({
      observed_water: satelliteImage.data?.water_mask,
      simulated_flood: floodSimulation.data?.geojson
    })
  });

  return (
    <Panel>
      <DatePicker value={selectedDate} onChange={setSelectedDate} />

      <Slider
        label="Nivel de agua (m)"
        value={waterLevel}
        onChange={setWaterLevel}
        min={0.5}
        max={5}
        step={0.5}
      />

      <Button onClick={() => floodSimulation.mutate(waterLevel)}>
        Simular Inundacion
      </Button>

      <ResultsDisplay
        satelliteData={satelliteImage.data}
        floodData={floodSimulation.data}
        parcelRisk={parcelAnalysis.data}
      />
    </Panel>
  );
}
```

---

## Datos Requeridos

### 1. Modelo Digital de Elevacion (DEM)

**Fuentes gratuitas**:
- **SRTM 30m**: Cobertura global, resolucion 30m
- **ALOS PALSAR**: Mejor para areas planas, 12.5m
- **Copernicus DEM**: 30m global, actualizacion reciente

**Obtencion via GEE**:
```python
# Exportar DEM desde GEE (una sola vez)
dem = ee.Image("USGS/SRTMGL1_003")
zona = ee.Geometry.Polygon([...])  # Area del consorcio

task = ee.batch.Export.image.toDrive(
    image=dem.clip(zona),
    description='consorcio_dem',
    folder='consorcio_gis',
    region=zona,
    scale=30,
    crs='EPSG:4326'
)
task.start()
```

### 2. Red de caminos y canales

Ya disponible en Fase 1 via GEE layers (`caminos`).

### 3. Limites de parcelas

Opcional: Shapefile de parcelas rurales para analisis por lote.

---

## Plan de Implementacion Modular

### Modulo 1: Infraestructura GRASS
- [ ] Crear Dockerfile para GRASS GIS
- [ ] Configurar volumen para DEM
- [ ] API basica FastAPI
- [ ] Health check endpoint

### Modulo 2: Analisis de Cuencas
- [ ] Endpoint watershed delineation
- [ ] Endpoint flow network
- [ ] Visualizacion en frontend

### Modulo 3: Simulacion de Inundacion
- [ ] Endpoint simulate-flood
- [ ] Slider de nivel de agua en UI
- [ ] Overlay en mapa Leaflet

### Modulo 4: Analisis de Riesgo
- [ ] Endpoint parcel-risk
- [ ] Tabla de resultados
- [ ] Exportacion a Excel/PDF

### Modulo 5: Integracion GEE + GRASS
- [ ] Combinar agua observada + simulada
- [ ] Panel unificado de analisis
- [ ] Reportes comparativos

---

## Consideraciones Tecnicas

### Performance

- **DEM grande**: Procesar por tiles si >1GB
- **Cache**: Guardar resultados de watershed (no cambian)
- **Async**: Usar Celery para procesos largos

### Escalabilidad

```python
# Procesar en background con Celery
@celery.task
def process_watershed_async(dem_path, outlet):
    result = delineate_watershed(dem_path, outlet)
    save_to_cache(result)
    notify_frontend(result)
```

### Errores comunes

1. **DEM con huecos**: Rellenar con `r.fillnulls`
2. **Coordenadas incorrectas**: Verificar CRS (EPSG:4326 vs UTM)
3. **Memoria**: GRASS puede consumir mucha RAM con DEMs grandes

---

## Recursos

- [Documentacion GRASS GIS](https://grass.osgeo.org/grass-stable/manuals/)
- [r.watershed](https://grass.osgeo.org/grass-stable/manuals/r.watershed.html)
- [Docker GRASS](https://hub.docker.com/r/mundialis/grass-py3-pdal)
- [PyGRASS](https://grass.osgeo.org/grass-stable/manuals/libpython/pygrass_index.html)

---

## Resumen

La Fase 2 transforma la aplicacion de un **visor de estado actual** a una **herramienta predictiva**:

| Pregunta | Fase 1 (GEE) | Fase 2 (+ GRASS) |
|----------|--------------|-------------------|
| Hay agua ahora? | Si | Si |
| Donde se acumulara el agua? | No | Si |
| Cuales parcelas estan en riesgo? | Parcial | Completo |
| Que pasa si sube el nivel 2m? | No | Si |
| Cual es la cuenca de cada punto? | No | Si |

La integracion mantiene el backend unificado (FastAPI) y agrega un contenedor especializado para procesamiento GRASS, permitiendo escalar de forma independiente.
