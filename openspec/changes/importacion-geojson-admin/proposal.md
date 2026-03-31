## Objetivo
Agregar en admin una interfaz para importar GeoJSON de `zonas_operativas` y de `zonificación aprobada` sin depender de scripts manuales en producción.

## Problema
Hoy producción quedó bloqueada porque faltan datos geoespaciales cargados en la base (`zonas_operativas`) y la única vía práctica para poblarlos es usando scripts/terminal. Eso es lento, frágil y difícil de repetir.

## Alcance
- Botón / panel admin para subir `zonas_operativas.geojson`
- Botón / panel admin para subir `zonificacion_aprobada.geojson`
- Validación backend básica de formato GeoJSON
- Importación controlada que reemplace los datos del tipo importado
- Feedback claro de cuántas features se importaron

## Fuera de alcance
- Importación genérica de cualquier capa arbitraria
- Versionado complejo de imports
- Merging inteligente entre geometrías nuevas y existentes

## Riesgos
- Reemplazar datos incorrectamente si el archivo subido no es el esperado
- Incompatibilidades entre propiedades de desarrollo y producción
- Geometrías inválidas o vacías

## Criterios de aceptación
- Un admin puede importar `zonas_operativas.geojson` desde la UI
- Un admin puede importar `zonificacion_aprobada.geojson` desde la UI
- El sistema valida que el archivo tenga `FeatureCollection`
- La importación devuelve resumen de filas/features afectadas
- Si no hay datos, el sistema falla de forma legible y no con 500 críptico
