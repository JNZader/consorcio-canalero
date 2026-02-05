# Analisis Pendientes - Consorcio Canalero

Este documento detalla los analisis que quedaron pendientes de implementar
y los requisitos necesarios para completarlos.

---

## 1. Analisis de Riesgo por Establecimiento

### Descripcion
Analisis que permite identificar que establecimientos agropecuarios estan
afectados por inundacion/anegamiento, diferenciando entre ganaderos y agricolas.

### Datos Requeridos

#### 1.1 Catastro Rural
- **Fuente**: Direccion de Catastro de Cordoba o ARBA provincial
- **Formato esperado**: Shapefile o GeoJSON con poligonos de parcelas
- **Campos necesarios**:
  - `nomenclatura` o `partida`: Identificador unico de la parcela
  - `titular`: Nombre del propietario (opcional)
  - `superficie_ha`: Area de la parcela
  - `geometry`: Poligono de la parcela

#### 1.2 RENSPA (Registro Nacional Sanitario de Productores Agropecuarios)
- **Fuente**: SENASA
- **URL**: https://www.argentina.gob.ar/senasa/renspa
- **Formato esperado**: CSV o JSON
- **Campos necesarios**:
  - `renspa`: Codigo RENSPA del establecimiento
  - `actividad`: Tipo de actividad (ganaderia, agricultura, mixto)
  - `especies`: Para ganaderos, especies principales (bovino, porcino, etc.)
  - `coordenadas` o `nomenclatura`: Para vincular con catastro

### Implementacion Propuesta

#### Paso 1: Cargar datos como assets en GEE
```javascript
// En Google Earth Engine Code Editor
// Subir los shapefiles como assets

var catastro = ee.FeatureCollection('projects/cc10demayo/assets/catastro');
var renspa = ee.FeatureCollection('projects/cc10demayo/assets/renspa');

// Si RENSPA no tiene geometria, hacer join con catastro
var establecimientosConRiesgo = catastro.map(function(parcela) {
  // Buscar si tiene RENSPA asociado
  var renspaInfo = renspa.filter(
    ee.Filter.eq('nomenclatura', parcela.get('nomenclatura'))
  ).first();

  // Determinar tipo de establecimiento
  var tipo = ee.Algorithms.If(renspaInfo,
    renspaInfo.get('actividad'),
    'sin_clasificar'
  );

  return parcela.set('tipo_establecimiento', tipo);
});
```

#### Paso 2: Backend Python (gee_service.py)
```python
def analyze_establishments(
    self,
    start_date: date,
    end_date: date,
    establishment_type: Optional[str] = None,  # 'ganadero', 'agricola', 'todos'
) -> Dict[str, Any]:
    """
    Analizar establecimientos afectados por inundacion/anegamiento.

    Args:
        start_date: Fecha inicio
        end_date: Fecha fin
        establishment_type: Filtrar por tipo de establecimiento

    Returns:
        Lista de establecimientos afectados con estadisticas
    """
    # Cargar assets
    catastro = ee.FeatureCollection(self.ASSETS_BASE + '/catastro')

    # Filtrar por tipo si se especifica
    if establishment_type and establishment_type != 'todos':
        catastro = catastro.filter(
            ee.Filter.eq('tipo_establecimiento', establishment_type)
        )

    # Obtener clasificacion de inundacion
    clasificacion = self._get_classification(start_date, end_date)

    # Para cada establecimiento, calcular area afectada
    def calcular_afectacion(establecimiento):
        geom = establecimiento.geometry()

        # Area total
        area_total = geom.area()

        # Area afectada (clases 0 y 1: agua y anegado)
        afectado = clasificacion.lte(1)
        area_afectada = afectado.multiply(ee.Image.pixelArea()).reduceRegion(
            reducer=ee.Reducer.sum(),
            geometry=geom,
            scale=10,
            maxPixels=1e9
        ).values().get(0)

        porcentaje = ee.Number(area_afectada).divide(area_total).multiply(100)

        return establecimiento.set({
            'area_afectada_ha': ee.Number(area_afectada).divide(10000),
            'porcentaje_afectado': porcentaje,
            'esta_afectado': porcentaje.gt(10)  # >10% se considera afectado
        })

    establecimientos_analizados = catastro.map(calcular_afectacion)

    # Filtrar solo afectados
    afectados = establecimientos_analizados.filter(
        ee.Filter.eq('esta_afectado', True)
    )

    # Contar por tipo
    stats = {
        'total_analizados': catastro.size().getInfo(),
        'total_afectados': afectados.size().getInfo(),
        'ganaderos_afectados': afectados.filter(
            ee.Filter.eq('tipo_establecimiento', 'ganaderia')
        ).size().getInfo(),
        'agricolas_afectados': afectados.filter(
            ee.Filter.eq('tipo_establecimiento', 'agricultura')
        ).size().getInfo(),
    }

    # Lista de afectados (top 50 por porcentaje)
    lista_afectados = afectados.sort('porcentaje_afectado', False).limit(50)

    return {
        'estadisticas': stats,
        'establecimientos_afectados': lista_afectados.getInfo()['features'],
        'parametros': {
            'start_date': start_date.isoformat(),
            'end_date': end_date.isoformat(),
            'tipo_filtrado': establishment_type,
        }
    }
```

#### Paso 3: Endpoint API (analysis.py)
```python
class EstablishmentAnalysisRequest(BaseModel):
    start_date: date
    end_date: date
    establishment_type: Optional[str] = Field(
        default=None,
        description="Filtrar por tipo: ganadero, agricola, todos"
    )


@router.post("/establishments")
async def analyze_establishments(
    request: EstablishmentAnalysisRequest,
    user: User = Depends(require_admin_or_operator),
):
    """
    Analizar establecimientos afectados por inundacion.

    Requiere datos de catastro y RENSPA cargados como assets.
    """
    gee = get_gee_service()
    result = gee.analyze_establishments(
        start_date=request.start_date,
        end_date=request.end_date,
        establishment_type=request.establishment_type,
    )
    return result
```

### Salida Esperada

```json
{
  "estadisticas": {
    "total_analizados": 1250,
    "total_afectados": 87,
    "ganaderos_afectados": 52,
    "agricolas_afectados": 35
  },
  "establecimientos_afectados": [
    {
      "nomenclatura": "123-456-789",
      "titular": "Juan Perez",
      "tipo_establecimiento": "ganaderia",
      "superficie_ha": 150.5,
      "area_afectada_ha": 45.2,
      "porcentaje_afectado": 30.03
    },
    // ... mas establecimientos
  ]
}
```

### Casos de Uso

1. **Declaracion de Emergencia Agropecuaria**
   - Listar todos los establecimientos afectados con >30% de su superficie
   - Diferenciar entre ganaderos y agricolas para tipos de ayuda
   - Exportar lista para tramites provinciales

2. **Planificacion de Obras**
   - Identificar zonas con mayor concentracion de establecimientos afectados
   - Priorizar obras de drenaje

3. **Seguimiento Post-Evento**
   - Comparar afectacion entre eventos
   - Evaluar recuperacion de establecimientos

---

## 2. Otros Analisis Futuros Sugeridos

### 2.1 Monitoreo de Vegetacion en Canales
- Detectar vegetacion invasora usando NDVI
- Identificar tramos que requieren limpieza
- **Datos necesarios**: Capa de canales con geometria lineal

### 2.2 Estado de Cultivos (Stress Hidrico)
- Usar NDVI/EVI para detectar cultivos estresados
- Comparar con parcelas sanas de la misma zona
- **Datos necesarios**: Catastro con tipo de cultivo por parcela

### 2.3 Sedimentacion en Canales
- Analisis de cambio en seccion transversal
- Requiere datos LiDAR o batimetria
- **Datos necesarios**: Relevamiento topografico de canales

---

## Notas Tecnicas

### Formato de Assets en GEE

Para cargar datos en Google Earth Engine:

1. **Shapefile**:
   - Subir via Code Editor > Assets > NEW > Table Upload
   - Maximo 10MB por archivo

2. **GeoJSON**:
   - Convertir shapefile a GeoJSON si excede limite
   - `ogr2ogr -f GeoJSON output.geojson input.shp`

3. **CSV con coordenadas**:
   - Subir como tabla
   - Crear geometria en GEE: `ee.Geometry.Point([lon, lat])`

### Permisos
Los assets deben estar en `projects/cc10demayo/assets/` con permisos
de lectura para la cuenta de servicio del backend.

---

**Ultima actualizacion**: Enero 2026
**Autor**: Sistema de Gestion Consorcio Canalero
