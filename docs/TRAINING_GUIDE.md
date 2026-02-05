# Guia de Entrenamiento - Clasificacion Supervisada

Esta guia te explica como entrenar el modelo de clasificacion
para que sea mas preciso en tu zona especifica.

---

## Que es la Clasificacion Supervisada?

Es un metodo de Machine Learning donde:

1. **Tu le ensenas al modelo** mostrandole ejemplos de cada tipo de terreno
2. **El modelo aprende** los patrones espectrales de cada clase
3. **El modelo clasifica** areas nuevas basandose en lo aprendido

```
Tu marcas ejemplos          El modelo aprende          Clasifica todo
      |                           |                          |
   [Esto es                  [Cultivo sano               [Mapa con
    cultivo]                  tiene NDVI alto]            todas las
   [Esto es                  [Agua tiene                  areas
    agua]                     NDWI alto]                  clasificadas]
```

---

## Por que entrenar?

**Sin entrenamiento (umbrales fijos):**
- Usa reglas genericas (NDVI > 0.5 = cultivo sano)
- Puede no funcionar bien en tu zona especifica
- Rapido pero menos preciso

**Con entrenamiento (supervisado):**
- Aprende de ejemplos de TU zona
- Se adapta a las condiciones locales
- Mas trabajo inicial pero mas preciso

---

## Clases disponibles

| ID | Nombre | Color | Descripcion |
|----|--------|-------|-------------|
| 0 | Cultivo Sano | Verde | Vegetacion activa, cultivos en buen estado |
| 1 | Rastrojo | Naranja | Restos de cosecha, suelo con poca cobertura |
| 2 | Agua en Superficie | Azul | Canales, lagunas, cuerpos de agua |
| 3 | Lote Anegado | Rojo | Campos con exceso de agua, encharcamiento |
| 4 | Suelo Desnudo | Gris | Sin vegetacion ni agua (opcional) |
| 5 | Vegetacion Natural | Verde oscuro | Montes, pastizales naturales (opcional) |

**Nota**: Las clases 4 y 5 son opcionales. Usa solo las que necesites.

---

# PASO 1: Preparar muestras de entrenamiento

## 1.1 Que necesitas

- Acceso al mapa de tu zona
- Conocimiento del terreno (o fotos/visitas recientes)
- Al menos 20 muestras por clase (minimo 50 en total)

## 1.2 Como identificar cada clase en el terreno

### Cultivo Sano (clase 0)
- Campos con cultivos verdes y vigorosos
- Vegetacion uniforme y densa
- Sin senales de estres hidrico

**En imagen satelital**: Tonos verdes brillantes

### Rastrojo (clase 1)
- Campos cosechados con restos de cultivo
- Suelo con poca cobertura vegetal
- Color marron/amarillento

**En imagen satelital**: Tonos marrones, amarillos palidos

### Agua en Superficie (clase 2)
- Canales con agua
- Lagunas o reservorios
- Agua clara visible

**En imagen satelital**: Tonos azules/negros, muy oscuro

### Lote Anegado (clase 3)
- Campos con agua estancada
- Mezcla de vegetacion y agua
- Cultivos afectados por exceso hidrico

**En imagen satelital**: Tonos oscuros con algo de verde, patrones irregulares

---

# PASO 2: Recolectar muestras

## 2.1 Usar Google Earth Engine Code Editor

La forma mas facil de recolectar muestras:

1. Ve a: **https://code.earthengine.google.com**

2. Crea un nuevo script

3. Carga una imagen de tu zona:

```javascript
// Cargar imagen Sentinel-2 de tu zona
var zona = ee.Geometry.Rectangle([-60.8, -33.5, -60.3, -33.1]);

var imagen = ee.ImageCollection('COPERNICUS/S2_SR_HARMONIZED')
  .filterBounds(zona)
  .filterDate('2024-01-01', '2024-01-31')
  .filter(ee.Filter.lt('CLOUDY_PIXEL_PERCENTAGE', 20))
  .median();

// Visualizar en color real
Map.addLayer(imagen, {bands: ['B4', 'B3', 'B2'], min: 0, max: 3000}, 'Imagen');
Map.centerObject(zona, 12);
```

4. Usa las herramientas de dibujo (arriba a la izquierda) para marcar puntos:
   - Selecciona "Add a marker" o "Draw a polygon"
   - Haz clic en areas que conozcas bien
   - Renombra cada grupo de marcadores (ej: "cultivo_sano", "rastrojo", etc.)

5. Exporta las geometrias:
```javascript
// Exportar como GeoJSON
print('Cultivo Sano:', cultivo_sano);  // Click en el link para copiar
```

## 2.2 Usar QGIS

Si prefieres QGIS:

1. Carga una imagen satelital de tu zona (puedes usar Google Satellite como base)

2. Crea una capa de puntos nueva:
   - Layer > Create Layer > New Shapefile Layer
   - Tipo: Point
   - Agrega un campo "clase" (Integer)

3. Activa el modo edicion y dibuja puntos

4. Asigna la clase a cada punto en la tabla de atributos

5. Exporta como GeoJSON

## 2.3 Usar el mapa del frontend (proximamente)

Estamos trabajando en una herramienta integrada en el sitio web
para dibujar muestras directamente.

---

# PASO 3: Preparar los datos

## 3.1 Formato requerido

Las muestras deben estar en formato GeoJSON, organizadas por clase:

```json
{
  "0": [
    {"type": "Point", "coordinates": [-60.5123, -33.2456]},
    {"type": "Point", "coordinates": [-60.5234, -33.2567]},
    {"type": "Point", "coordinates": [-60.5345, -33.2678]}
  ],
  "1": [
    {"type": "Point", "coordinates": [-60.6123, -33.3456]},
    {"type": "Point", "coordinates": [-60.6234, -33.3567]}
  ],
  "2": [
    {"type": "Point", "coordinates": [-60.7123, -33.4456]}
  ],
  "3": [
    {"type": "Point", "coordinates": [-60.8123, -33.5456]}
  ]
}
```

## 3.2 Tambien puedes usar poligonos

Para areas homogeneas, los poligonos son mejores:

```json
{
  "0": [
    {
      "type": "Polygon",
      "coordinates": [[
        [-60.53, -33.26],
        [-60.54, -33.26],
        [-60.54, -33.27],
        [-60.53, -33.27],
        [-60.53, -33.26]
      ]]
    }
  ]
}
```

## 3.3 Recomendaciones

- **Minimo 20 muestras por clase** (mejor 50+)
- **Distribuye las muestras** por toda el area
- **Evita bordes** entre clases (zonas de transicion)
- **Incluye variabilidad** - no todas las muestras del mismo lugar
- **Balance** - intenta tener cantidades similares por clase

---

# PASO 4: Validar las muestras

Antes de entrenar, valida que tus muestras son suficientes:

## 4.1 Usando la API

```bash
curl -X POST "http://localhost:8000/api/v1/monitoring/supervised/validar-muestras" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer TU_TOKEN" \
  -d '{
    "muestras_por_clase": {
      "0": [...],
      "1": [...],
      "2": [...],
      "3": [...]
    }
  }'
```

## 4.2 Respuesta esperada

```json
{
  "valido": true,
  "total_muestras": 85,
  "muestras_por_clase": {
    "0": 25,
    "1": 22,
    "2": 18,
    "3": 20
  },
  "problemas": [],
  "sugerencias": [
    "Clase 2: mejor precision con 20+ muestras"
  ]
}
```

Si `valido: false`, sigue las sugerencias para mejorar.

---

# PASO 5: Entrenar y clasificar

## 5.1 Llamar al endpoint de clasificacion

```bash
curl -X POST "http://localhost:8000/api/v1/monitoring/supervised/clasificar" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer TU_TOKEN" \
  -d '{
    "start_date": "2024-06-01",
    "end_date": "2024-06-30",
    "layer_name": "zona",
    "modelo_tipo": "random_forest",
    "n_trees": 100,
    "muestras_por_clase": {
      "0": [
        {"type": "Point", "coordinates": [-60.5123, -33.2456]},
        ...
      ],
      "1": [...],
      "2": [...],
      "3": [...]
    }
  }'
```

## 5.2 Respuesta

```json
{
  "metodo": "clasificacion_supervisada",
  "modelo": {
    "tipo": "random_forest",
    "accuracy": 87.5,
    "kappa": 0.82,
    "n_muestras": 85
  },
  "area_total_ha": 15234.56,
  "clases": {
    "0": {"hectareas": 8500.23, "porcentaje": 55.8, "nombre": "Cultivo Sano"},
    "1": {"hectareas": 3200.45, "porcentaje": 21.0, "nombre": "Rastrojo"},
    "2": {"hectareas": 534.12, "porcentaje": 3.5, "nombre": "Agua en Superficie"},
    "3": {"hectareas": 3000.76, "porcentaje": 19.7, "nombre": "Lote Anegado"}
  },
  "metricas_modelo": {
    "accuracy": 0.875,
    "kappa": 0.82,
    "matriz_confusion": [[20, 2, 0, 1], [1, 18, 0, 2], ...]
  },
  "geojson": {...}
}
```

## 5.3 Interpretar las metricas

**Accuracy (Precision):**
- > 90%: Excelente
- 80-90%: Bueno
- 70-80%: Aceptable
- < 70%: Necesita mas/mejores muestras

**Kappa:**
- > 0.8: Casi perfecto
- 0.6-0.8: Bueno
- 0.4-0.6: Moderado
- < 0.4: Pobre

**Matriz de Confusion:**
- Diagonal: clasificaciones correctas
- Fuera de diagonal: errores

---

# PASO 6: Mejorar el modelo

Si la precision es baja:

## 6.1 Agregar mas muestras

- Especialmente en clases con pocos ejemplos
- En areas donde el modelo se equivoca

## 6.2 Revisar muestras existentes

- Elimina muestras mal etiquetadas
- Verifica que las muestras sean representativas

## 6.3 Probar otros modelos

```json
{
  "modelo_tipo": "svm"  // Probar Support Vector Machine
}
```

Opciones:
- `random_forest`: Mejor para la mayoria de casos
- `svm`: Bueno con pocas muestras
- `cart`: Rapido, facil de interpretar
- `minimum_distance`: Baseline simple

## 6.4 Ajustar parametros

Para Random Forest:
```json
{
  "modelo_tipo": "random_forest",
  "n_trees": 200  // Mas arboles = mas precision (pero mas lento)
}
```

---

# Ejemplo completo

## Archivo de muestras (muestras.json)

```json
{
  "muestras_por_clase": {
    "0": [
      {"type": "Point", "coordinates": [-60.512, -33.245]},
      {"type": "Point", "coordinates": [-60.523, -33.256]},
      {"type": "Point", "coordinates": [-60.534, -33.267]},
      {"type": "Point", "coordinates": [-60.545, -33.278]},
      {"type": "Point", "coordinates": [-60.556, -33.289]},
      {"type": "Point", "coordinates": [-60.567, -33.290]},
      {"type": "Point", "coordinates": [-60.578, -33.301]},
      {"type": "Point", "coordinates": [-60.589, -33.312]},
      {"type": "Point", "coordinates": [-60.590, -33.323]},
      {"type": "Point", "coordinates": [-60.501, -33.334]},
      {"type": "Point", "coordinates": [-60.512, -33.345]},
      {"type": "Point", "coordinates": [-60.523, -33.356]},
      {"type": "Point", "coordinates": [-60.534, -33.367]},
      {"type": "Point", "coordinates": [-60.545, -33.378]},
      {"type": "Point", "coordinates": [-60.556, -33.389]},
      {"type": "Point", "coordinates": [-60.567, -33.390]},
      {"type": "Point", "coordinates": [-60.578, -33.401]},
      {"type": "Point", "coordinates": [-60.589, -33.412]},
      {"type": "Point", "coordinates": [-60.590, -33.423]},
      {"type": "Point", "coordinates": [-60.501, -33.434]}
    ],
    "1": [
      {"type": "Point", "coordinates": [-60.612, -33.345]},
      {"type": "Point", "coordinates": [-60.623, -33.356]},
      {"type": "Point", "coordinates": [-60.634, -33.367]},
      {"type": "Point", "coordinates": [-60.645, -33.378]},
      {"type": "Point", "coordinates": [-60.656, -33.389]},
      {"type": "Point", "coordinates": [-60.667, -33.390]},
      {"type": "Point", "coordinates": [-60.678, -33.401]},
      {"type": "Point", "coordinates": [-60.689, -33.412]},
      {"type": "Point", "coordinates": [-60.690, -33.423]},
      {"type": "Point", "coordinates": [-60.601, -33.434]},
      {"type": "Point", "coordinates": [-60.612, -33.445]},
      {"type": "Point", "coordinates": [-60.623, -33.456]},
      {"type": "Point", "coordinates": [-60.634, -33.467]},
      {"type": "Point", "coordinates": [-60.645, -33.478]},
      {"type": "Point", "coordinates": [-60.656, -33.489]},
      {"type": "Point", "coordinates": [-60.667, -33.490]},
      {"type": "Point", "coordinates": [-60.678, -33.501]},
      {"type": "Point", "coordinates": [-60.689, -33.512]},
      {"type": "Point", "coordinates": [-60.690, -33.523]},
      {"type": "Point", "coordinates": [-60.601, -33.534]}
    ],
    "2": [
      {"type": "Point", "coordinates": [-60.712, -33.445]},
      {"type": "Point", "coordinates": [-60.723, -33.456]},
      {"type": "Point", "coordinates": [-60.734, -33.467]},
      {"type": "Point", "coordinates": [-60.745, -33.478]},
      {"type": "Point", "coordinates": [-60.756, -33.489]},
      {"type": "Point", "coordinates": [-60.767, -33.490]},
      {"type": "Point", "coordinates": [-60.778, -33.501]},
      {"type": "Point", "coordinates": [-60.789, -33.512]},
      {"type": "Point", "coordinates": [-60.790, -33.523]},
      {"type": "Point", "coordinates": [-60.701, -33.534]},
      {"type": "Point", "coordinates": [-60.712, -33.545]},
      {"type": "Point", "coordinates": [-60.723, -33.556]},
      {"type": "Point", "coordinates": [-60.734, -33.567]},
      {"type": "Point", "coordinates": [-60.745, -33.578]},
      {"type": "Point", "coordinates": [-60.756, -33.589]},
      {"type": "Point", "coordinates": [-60.767, -33.590]},
      {"type": "Point", "coordinates": [-60.778, -33.601]},
      {"type": "Point", "coordinates": [-60.789, -33.612]},
      {"type": "Point", "coordinates": [-60.790, -33.623]},
      {"type": "Point", "coordinates": [-60.701, -33.634]}
    ],
    "3": [
      {"type": "Point", "coordinates": [-60.812, -33.545]},
      {"type": "Point", "coordinates": [-60.823, -33.556]},
      {"type": "Point", "coordinates": [-60.834, -33.567]},
      {"type": "Point", "coordinates": [-60.845, -33.578]},
      {"type": "Point", "coordinates": [-60.856, -33.589]},
      {"type": "Point", "coordinates": [-60.867, -33.590]},
      {"type": "Point", "coordinates": [-60.878, -33.601]},
      {"type": "Point", "coordinates": [-60.889, -33.612]},
      {"type": "Point", "coordinates": [-60.890, -33.623]},
      {"type": "Point", "coordinates": [-60.801, -33.634]},
      {"type": "Point", "coordinates": [-60.812, -33.645]},
      {"type": "Point", "coordinates": [-60.823, -33.656]},
      {"type": "Point", "coordinates": [-60.834, -33.667]},
      {"type": "Point", "coordinates": [-60.845, -33.678]},
      {"type": "Point", "coordinates": [-60.856, -33.689]},
      {"type": "Point", "coordinates": [-60.867, -33.690]},
      {"type": "Point", "coordinates": [-60.878, -33.701]},
      {"type": "Point", "coordinates": [-60.889, -33.712]},
      {"type": "Point", "coordinates": [-60.890, -33.723]},
      {"type": "Point", "coordinates": [-60.801, -33.734]}
    ]
  }
}
```

## Script Python para entrenar

```python
import requests
import json

# Cargar muestras
with open('muestras.json') as f:
    muestras = json.load(f)

# Configurar request
url = "http://localhost:8000/api/v1/monitoring/supervised/clasificar"
headers = {
    "Content-Type": "application/json",
    "Authorization": "Bearer TU_TOKEN_AQUI"
}

payload = {
    "start_date": "2024-06-01",
    "end_date": "2024-06-30",
    "layer_name": "zona",
    "modelo_tipo": "random_forest",
    "n_trees": 100,
    **muestras
}

# Enviar
response = requests.post(url, headers=headers, json=payload)
result = response.json()

# Mostrar resultados
print(f"Accuracy: {result['modelo']['accuracy']}%")
print(f"Kappa: {result['modelo']['kappa']}")
print("\nClases:")
for clase, datos in result['clases'].items():
    print(f"  {datos['nombre']}: {datos['hectareas']} ha ({datos['porcentaje']}%)")
```

---

# Resumen

1. **Recolecta muestras** (20+ por clase) usando GEE Code Editor o QGIS
2. **Formatea como JSON** con estructura `{clase: [geometrias]}`
3. **Valida** con `/supervised/validar-muestras`
4. **Entrena** con `/supervised/clasificar`
5. **Evalua** metricas (accuracy, kappa)
6. **Mejora** agregando muestras si es necesario

**Precision esperada**: 80-90% con buenas muestras.

---

# Preguntas frecuentes

**P: Cuantas muestras necesito?**
R: Minimo 20 por clase, idealmente 50+. Mas muestras = mejor precision.

**P: Puntos o poligonos?**
R: Puntos son mas faciles. Poligonos son mejores para areas homogeneas grandes.

**P: Que pasa si una clase tiene pocas muestras?**
R: El modelo tendra menos precision para esa clase. Agrega mas muestras.

**P: Puedo reusar las muestras para otras fechas?**
R: Si, las muestras representan ubicaciones. Puedes re-entrenar con diferentes fechas.

**P: Como se cual modelo usar?**
R: Empieza con `random_forest`. Si tienes pocas muestras, prueba `svm`.
