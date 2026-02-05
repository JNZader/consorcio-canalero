# Backend API Reference - Consorcio Canalero v1

**Base URL:** `http://localhost:8000/api/v1`
**Authentication:** JWT Bearer Token (Supabase)

---

## Autenticación

### Roles de Usuario
- `ciudadano` - Ciudadano (default)
- `operador` - Operador/Staff
- `admin` - Administrador

### Headers Requeridos
```http
Authorization: Bearer <jwt_token>
Content-Type: application/json
```

---

## Endpoints por Módulo

### 1. Public (Sin Autenticación)

#### POST `/public/reports`
Crear denuncia ciudadana.

**Request:**
```json
{
  "tipo": "alcantarilla_tapada|desborde|camino_danado|otro",
  "descripcion": "string (10-2000 chars)",
  "latitud": -90 to 90,
  "longitud": -180 to 180,
  "cuenca": "string (optional)",
  "foto_url": "string (optional)"
}
```

**Response:**
```json
{
  "id": "uuid",
  "message": "Denuncia creada exitosamente",
  "estado": "pendiente"
}
```

#### POST `/public/upload-photo`
Subir foto de denuncia (max 5MB, JPEG/PNG/WebP).

**Response:**
```json
{
  "photo_url": "https://...",
  "filename": "uuid.jpg"
}
```

#### POST `/public/verify/send`
Enviar código de verificación por email.

#### POST `/public/verify/check`
Verificar código recibido.

---

### 2. Analysis (Requiere Auth: operador/admin)

#### POST `/analysis/flood-detection`
Iniciar detección SAR (Sentinel-1).

**Request:**
```json
{
  "start_date": "YYYY-MM-DD",
  "end_date": "YYYY-MM-DD",
  "cuencas": ["candil", "ml", "noroeste", "norte"],
  "threshold": -15.0
}
```

**Response:**
```json
{
  "job_id": "uuid",
  "status": "queued",
  "message": "string"
}
```

#### POST `/analysis/flood-detection-optical`
Detección óptica (Sentinel-2, NDWI/MNDWI).

#### POST `/analysis/flood-detection-fusion`
Fusión SAR + Óptico.

**Modos de fusión:** `union`, `intersection`, `weighted`

#### GET `/analysis/{job_id}/status`
Estado del job.

**Response:**
```json
{
  "job_id": "uuid",
  "status": "queued|processing|completed|failed",
  "progress": 0-100,
  "message": "string",
  "result": {},
  "error": "string"
}
```

#### GET `/analysis/{job_id}/result`
Resultado completo del análisis.

#### GET `/analysis/history`
Historial de análisis (paginado).

#### POST `/analysis/stats-by-polygon`
Estadísticas dentro de polígono dibujado.

#### POST `/analysis/supervised-classification`
Clasificación ML supervisada (4 clases).

**Clases:** Agua, Anegado, Cultivo Sano, Suelo Desnudo

#### POST `/analysis/precipitation`
Precipitación acumulada (CHIRPS).

#### POST `/analysis/precipitation/monthly`
Precipitación mensual histórica.

#### POST `/analysis/precipitation/by-cuenca`
Comparar precipitación entre cuencas.

#### POST `/analysis/flood/compare-periods`
Comparar extensión de inundación entre dos períodos.

#### POST `/analysis/flood/time-series`
Serie temporal de un mes específico.

#### POST `/analysis/available-dates`
Fechas con imágenes satelitales disponibles.

---

### 3. Layers (Capas)

#### GET `/layers`
Listar todas las capas.

#### GET `/layers/{id}`
Obtener capa específica.

#### POST `/layers` (admin)
Crear nueva capa.

#### POST `/layers/upload` (admin)
Subir GeoJSON y crear capa.

#### PUT `/layers/{id}` (admin)
Actualizar capa.

#### DELETE `/layers/{id}` (admin)
Eliminar capa.

#### POST `/layers/reorder` (operador/admin)
Reordenar capas.

---

### 4. Reports (Denuncias)

#### GET `/reports`
Listar denuncias con filtros.

**Query Params:**
- `page`, `limit`
- `status`: pendiente|en_revision|resuelto|rechazado
- `cuenca`, `tipo`, `assigned_to`

#### GET `/reports/{id}`
Detalle con historial.

#### PUT `/reports/{id}` (operador/admin)
Actualizar denuncia.

#### POST `/reports/{id}/assign` (operador/admin)
Asignar a operador.

#### POST `/reports/{id}/resolve` (operador/admin)
Marcar como resuelto.

---

### 5. Stats (Estadísticas)

#### GET `/stats/dashboard`
Estadísticas del dashboard.

#### GET `/stats/by-cuenca`
Desglose por cuenca.

#### GET `/stats/historical`
Datos históricos para tendencias.

#### POST `/stats/export`
Exportar a CSV/XLSX/PDF.

#### GET `/stats/summary`
Resumen rápido del sistema.

---

### 6. Sugerencias

#### POST `/sugerencias/public`
Crear sugerencia pública (rate limited: 3/día).

#### GET `/sugerencias/public/limit`
Verificar límite diario.

#### GET `/sugerencias` (auth)
Listar sugerencias con filtros.

#### POST `/sugerencias/interna` (operador/admin)
Crear tema interno.

#### PUT `/sugerencias/{id}` (operador/admin)
Actualizar sugerencia.

#### POST `/sugerencias/{id}/agendar` (operador/admin)
Agendar para reunión.

#### POST `/sugerencias/{id}/resolver` (operador/admin)
Marcar como resuelto.

---

### 7. Caminos Afectados

#### GET `/caminos`
Listar caminos afectados con filtros.

#### GET `/caminos/stats`
Estadísticas de caminos.

#### GET `/caminos/filtros`
Opciones de filtro disponibles.

#### GET `/caminos/exportar`
Exportar JSON/CSV.

---

### 8. Monitoring

#### GET `/monitoring/dashboard`
Dashboard de monitoreo.

#### GET `/monitoring/summary`
Resumen de monitoreo.

#### GET `/monitoring/alerts/current`
Alertas activas.

#### POST `/monitoring/classify-parcels`
Clasificar parcelas (4 clases).

#### POST `/monitoring/classify-parcels/custom`
Clasificar con umbrales personalizados.

#### POST `/monitoring/detect-changes`
Detectar cambios entre períodos.

#### POST `/monitoring/alerts`
Generar alertas automáticas.

#### GET `/monitoring/tiles/{layer_name}`
Tiles de clasificación para mapa.

---

### 9. Supervised Classification

#### GET `/monitoring/supervised/clases`
Clases disponibles para clasificación.

#### POST `/monitoring/supervised/validar-muestras`
Validar muestras de entrenamiento.

#### POST `/monitoring/supervised/clasificar`
Entrenar modelo y clasificar.

**Modelos:** `random_forest`, `svm`, `cart`, `minimum_distance`

#### GET `/monitoring/supervised/ejemplo-muestras`
Ejemplos de formato de muestras.

---

### 10. GEE Layers

#### GET `/gee/layers`
Listar capas GEE disponibles.

#### GET `/gee/layers/{layer_name}`
Obtener GeoJSON de capa.

**Capas:** zona, candil, ml, noroeste, norte, caminos

#### GET `/gee/layers/tiles/sentinel2`
Tiles RGB Sentinel-2.

---

### 11. Configuration

#### GET `/config/system`
Configuración completa del sistema.

#### GET `/config/cuencas`
Lista de cuencas.

#### GET `/config/map`
Configuración del mapa.

#### GET `/config/analysis-defaults`
Valores por defecto para análisis.

---

## Health Check

#### GET `/health`
```json
{
  "status": "healthy|degraded",
  "services": {
    "supabase": {"status": "healthy|unhealthy"},
    "redis": {"status": "healthy|unavailable"},
    "gee": {"status": "healthy|not_initialized"}
  }
}
```

---

## Códigos de Error

| Código | Significado |
|--------|-------------|
| 400 | Bad Request - Datos inválidos |
| 401 | Unauthorized - Sin token |
| 403 | Forbidden - Sin permisos |
| 404 | Not Found |
| 413 | Payload Too Large |
| 415 | Unsupported Media Type |
| 429 | Rate Limit Exceeded |
| 500 | Server Error |
| 503 | Service Unavailable |

---

## Cuencas Disponibles

| ID | Nombre | Área (ha) | Color |
|----|--------|-----------|-------|
| candil | Candil | 18,800 | #2196F3 |
| ml | ML | 18,900 | #4CAF50 |
| noroeste | Noroeste | 18,500 | #FF9800 |
| norte | Norte | 18,300 | #9C27B0 |

**Total Consorcio:** 75,000 ha
