# Guia de Entrenamiento - Interfaz Web

Esta guia explica como entrenar el modelo de clasificacion supervisada
usando la interfaz grafica del sistema.

---

## Acceso a la herramienta

1. Inicia sesion como **admin** u **operador**
2. Ve al panel de administracion: `/admin`
3. En el menu lateral, haz click en **"Entrenamiento ML"**

```
Menu Admin
├── Dashboard
├── Monitoreo de Cuenca
├── Analisis Satelital
├── Entrenamiento ML  <-- Aqui
├── Caminos Afectados
├── Capas
├── Denuncias
└── Sugerencias
```

---

## Pantalla de entrenamiento

La pantalla se divide en dos partes:

```
┌────────────────────┬─────────────────────────────────────┐
│                    │                                     │
│   Panel de         │        Mapa Interactivo             │
│   Control          │                                     │
│                    │     (Aqui dibujas las muestras)     │
│   - Clases         │                                     │
│   - Herramientas   │         🟢  🟢                      │
│   - Validacion     │      🟠        🔵                   │
│   - Entrenar       │         🔴  🟢                      │
│                    │                                     │
└────────────────────┴─────────────────────────────────────┘
```

---

## Paso 1: Entender las clases

El sistema tiene 4 clases principales (y 2 opcionales):

| Color | Clase | Descripcion | Que buscar en el mapa |
|-------|-------|-------------|----------------------|
| 🟢 Verde | Cultivo Sano | Vegetacion activa | Campos verdes brillantes |
| 🟠 Naranja | Rastrojo | Restos de cosecha | Campos marrones/amarillos |
| 🔵 Azul | Agua en Superficie | Canales, lagunas | Areas azul oscuro/negro |
| 🔴 Rojo | Lote Anegado | Campos inundados | Mezcla verde/oscuro irregular |
| ⚪ Gris | Suelo Desnudo | Sin vegetacion (opcional) | Areas grises uniformes |
| 🌲 Verde oscuro | Vegetacion Natural | Montes (opcional) | Verde oscuro, textura irregular |

---

## Paso 2: Seleccionar una clase

En el panel izquierdo, veras la lista de clases con sus colores.

1. **Haz click en una clase** para seleccionarla
2. La clase seleccionada se resalta con un borde de color
3. El contador muestra cuantas muestras tiene cada clase

```
┌─────────────────────────────────────┐
│  🟢 Cultivo Sano          [15]  🗑️ │  <- Seleccionada
│  🟠 Rastrojo              [12]  🗑️ │
│  🔵 Agua en Superficie    [ 8]  🗑️ │
│  🔴 Lote Anegado          [10]  🗑️ │
└─────────────────────────────────────┘
```

**Nota**: El icono 🗑️ elimina todas las muestras de esa clase.

---

## Paso 3: Dibujar muestras

Hay dos formas de marcar muestras:

### Opcion A: Puntos (mas facil)

1. Selecciona la clase
2. Click en boton **"Punto"**
3. Haz click en el mapa donde identificas esa clase
4. El punto aparece con el color de la clase

**Ideal para**: Marcar rapidamente multiples ubicaciones.

### Opcion B: Poligonos (mas preciso)

1. Selecciona la clase
2. Click en boton **"Poligono"**
3. Haz click en el mapa para crear vertices
4. **Doble click** para terminar el poligono

**Ideal para**: Areas grandes y homogeneas.

```
┌─────────────────────────────────────┐
│  Dibuja muestras de "Cultivo Sano" │
│                                     │
│  [ Punto ]  [ Poligono ]           │
│                                     │
│  ℹ️ Haz clic en el mapa para       │
│     agregar un punto                │
└─────────────────────────────────────┘
```

---

## Paso 4: Consejos para buenas muestras

### Cuantas muestras necesito?

| Cantidad | Calidad |
|----------|---------|
| < 10 | Insuficiente |
| 10-20 | Minimo |
| 20-50 | Bueno |
| 50+ | Excelente |

### Donde colocar las muestras?

**SI hacer:**
- Distribuir por toda el area de estudio
- Incluir variaciones (diferentes tonos de verde para cultivo)
- Marcar areas que conozcas bien
- Usar imagen satelite como referencia (cambiar capa base)

**NO hacer:**
- Poner todas las muestras juntas en un solo lugar
- Marcar bordes entre clases (zonas de transicion)
- Marcar areas con nubes o sombras
- Adivinar sin conocer el terreno

### Ejemplo visual de distribucion

```
Malo (todas juntas):          Bueno (distribuidas):

    🟢🟢🟢                      🟢      🟢
    🟢🟢🟢                   🟢    🟢
                                    🟢  🟢
                              🟢         🟢
```

---

## Paso 5: Cambiar la capa base

Para identificar mejor las clases, puedes cambiar entre:

1. **OpenStreetMap** - Mapa de calles (para ubicarte)
2. **Satelite** - Imagen satelital (para identificar clases)

Usa el control de capas en la esquina superior derecha del mapa.

```
┌─────────────────┐
│ ○ OpenStreetMap │
│ ● Satelite      │  <- Recomendado para entrenar
├─────────────────┤
│ ☑ zona          │
│ ☑ candil        │
│ ☑ ml            │
└─────────────────┘
```

---

## Paso 6: Importar/Exportar muestras

### Exportar (guardar tu trabajo)

1. Click en **"Exportar"**
2. Se descarga un archivo `.json`
3. Guardalo para usar despues

### Importar (cargar muestras previas)

1. Click en **"Importar"**
2. Selecciona el archivo `.json`
3. Las muestras se agregan al mapa

**Tip**: Exporta frecuentemente para no perder tu trabajo.

---

## Paso 7: Validar las muestras

Antes de entrenar, valida que tus muestras son suficientes:

1. Click en **"Validar muestras"**
2. El sistema verifica:
   - Cantidad minima por clase
   - Distribucion espacial
   - Balance entre clases

### Resultado de validacion

```
┌─────────────────────────────────────┐
│  Estado: ✅ Valido                  │
│                                     │
│  Total: 85 muestras                 │
│  - Cultivo Sano: 25                 │
│  - Rastrojo: 22                     │
│  - Agua: 18                         │
│  - Lote Anegado: 20                 │
│                                     │
│  Sugerencias:                       │
│  - Clase Agua: mejor con 20+        │
└─────────────────────────────────────┘
```

Si hay problemas, agrega mas muestras y vuelve a validar.

---

## Paso 8: Configurar el entrenamiento

### Seleccionar capa

Elige la capa/zona que quieres clasificar:
- zona (area completa)
- candil
- ml
- noroeste
- norte

### Seleccionar fechas

Elige el rango de fechas de las imagenes satelitales:
- **Fecha inicio**: Primera fecha del periodo
- **Fecha fin**: Ultima fecha del periodo

**Recomendacion**: Usa fechas recientes (ultimos 30 dias) para mejor precision.

### Seleccionar tipo de modelo

| Modelo | Cuando usarlo |
|--------|---------------|
| **Random Forest** | Recomendado para la mayoria de casos |
| **SVM** | Cuando tienes pocas muestras |
| **CART** | Cuando necesitas rapidez |
| **Distancia Minima** | Baseline simple |

---

## Paso 9: Entrenar y clasificar

1. Verifica que la validacion sea exitosa
2. Configura capa, fechas y modelo
3. Click en **"Entrenar y Clasificar"**
4. Espera el procesamiento (puede tardar 1-2 minutos)

---

## Paso 10: Interpretar resultados

### Metricas del modelo

```
┌─────────────────────────────────────┐
│  Precision: 87.5%                   │
│  Kappa: 0.82                        │
└─────────────────────────────────────┘
```

**Precision (Accuracy):**
- 90%+ = Excelente
- 80-90% = Bueno
- 70-80% = Aceptable
- <70% = Necesita mejoras

**Kappa:**
- 0.8+ = Casi perfecto
- 0.6-0.8 = Bueno
- 0.4-0.6 = Moderado
- <0.4 = Pobre

### Distribucion por clase

```
┌─────────────────────────────────────┐
│  Cultivo Sano                       │
│  ████████████████░░░░  8,500 ha 56% │
│                                     │
│  Rastrojo                           │
│  ██████░░░░░░░░░░░░░░  3,200 ha 21% │
│                                     │
│  Agua en Superficie                 │
│  █░░░░░░░░░░░░░░░░░░░    534 ha  4% │
│                                     │
│  Lote Anegado                       │
│  █████░░░░░░░░░░░░░░░  3,000 ha 19% │
└─────────────────────────────────────┘
```

---

## Mejorando el modelo

Si la precision es baja:

### 1. Revisar muestras mal etiquetadas

- Elimina muestras en zonas ambiguas
- Verifica que cada muestra este en la clase correcta

### 2. Agregar mas muestras

- Enfocate en clases con pocas muestras
- Agrega muestras en areas donde el modelo falla

### 3. Cambiar el modelo

- Si tienes pocas muestras, prueba SVM
- Si tienes muchas muestras, usa Random Forest con mas arboles

### 4. Ajustar fechas

- Usa fechas con poca nubosidad
- Evita periodos de transicion estacional

---

## Flujo de trabajo recomendado

```
1. Cambiar a vista Satelite
         ↓
2. Identificar areas conocidas
         ↓
3. Seleccionar clase → Dibujar muestras (20+ por clase)
         ↓
4. Repetir para cada clase
         ↓
5. Exportar muestras (backup)
         ↓
6. Validar muestras
         ↓
7. Configurar: capa + fechas + modelo
         ↓
8. Entrenar y clasificar
         ↓
9. Evaluar resultados
         ↓
10. Si precision < 80%: agregar muestras y repetir
```

---

## Atajos y tips

| Accion | Tip |
|--------|-----|
| Eliminar muestra | Click en la muestra en el mapa |
| Eliminar clase completa | Click en 🗑️ junto a la clase |
| Limpiar todo | Click en "Limpiar" |
| Cancelar dibujo | Click de nuevo en "Punto" o "Poligono" |
| Navegar mapa | Arrastrar con mouse |
| Zoom | Rueda del mouse o +/- |

---

## Problemas comunes

### "Muestras insuficientes"

**Causa**: Menos de 10 muestras totales o alguna clase vacia.

**Solucion**: Agrega mas muestras. Minimo 20 por clase.

### "Validacion falla"

**Causa**: Clases con muy pocas muestras o muestras muy concentradas.

**Solucion**: Distribuye mejor las muestras por toda el area.

### "Precision muy baja (<60%)"

**Causas posibles**:
- Muestras mal etiquetadas
- Clases muy similares espectralmente
- Pocas muestras
- Fechas con nubes

**Soluciones**:
- Revisa y corrige muestras
- Agrega mas muestras en areas problematicas
- Prueba diferentes fechas

### "El entrenamiento tarda mucho"

**Causa**: Muchas muestras o area muy grande.

**Solucion**: Es normal que tarde 1-2 minutos. Espera.

---

## Ejemplo practico

### Escenario: Clasificar la cuenca "zona" para Junio 2024

1. **Preparacion**
   - Acceder a `/admin/training`
   - Cambiar a vista Satelite
   - Activar capa "zona" en el control de capas

2. **Recoleccion de muestras**
   - Cultivo Sano: 25 puntos en campos verdes
   - Rastrojo: 22 puntos en campos cosechados
   - Agua: 20 puntos en canales y lagunas
   - Lote Anegado: 18 puntos en campos con agua estancada

3. **Validacion**
   - Click "Validar muestras"
   - Resultado: Valido (85 muestras)

4. **Entrenamiento**
   - Capa: zona
   - Fechas: 01/06/2024 - 30/06/2024
   - Modelo: Random Forest
   - Click "Entrenar y Clasificar"

5. **Resultados**
   - Precision: 87.5%
   - Kappa: 0.82
   - Clasificacion exitosa

---

## Resumen

| Paso | Accion |
|------|--------|
| 1 | Ir a `/admin/training` |
| 2 | Cambiar a vista Satelite |
| 3 | Seleccionar clase |
| 4 | Dibujar muestras (punto o poligono) |
| 5 | Repetir para cada clase (20+ muestras) |
| 6 | Validar muestras |
| 7 | Configurar capa, fechas, modelo |
| 8 | Entrenar y clasificar |
| 9 | Evaluar precision (objetivo: >80%) |
| 10 | Mejorar si es necesario |

---

**Precision esperada con buenas muestras: 80-90%**
