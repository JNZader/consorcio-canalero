## Requisitos

### 1. Importación de subcuencas operativas
El sistema DEBE permitir que un usuario administrador importe un archivo GeoJSON de `zonas_operativas`.

#### Escenario
- Dado un archivo `FeatureCollection` válido con geometrías de subcuencas
- Cuando el admin lo sube desde la interfaz
- Entonces el backend reemplaza las `zonas_operativas` actuales por las del archivo
- Y responde cantidad de features importadas

### 2. Importación de zonificación aprobada
El sistema DEBE permitir que un usuario administrador importe un archivo GeoJSON de zonificación aprobada.

#### Escenario
- Dado un archivo `FeatureCollection` válido de zonificación aprobada
- Cuando el admin lo sube desde la interfaz
- Entonces el backend reemplaza la zonificación aprobada activa
- Y responde cantidad de features importadas

### 3. Validación de formato
El sistema DEBE rechazar archivos que no sean GeoJSON `FeatureCollection`.

#### Escenario
- Dado un archivo inválido, vacío o con JSON no compatible
- Cuando se intenta importar
- Entonces el sistema responde 4xx con mensaje entendible

### 4. Feedback de importación
El sistema DEBE mostrar en admin el resultado de la importación.

#### Escenario
- Dado que la importación fue exitosa
- Cuando el backend responde
- Entonces la UI muestra confirmación y el conteo de features afectadas
