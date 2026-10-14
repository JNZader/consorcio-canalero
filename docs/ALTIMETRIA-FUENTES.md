# Altimetría: fuentes y perfiles longitudinales

Contrato de la serie de elevación que alimenta el perfil longitudinal (mapa 2D/3D,
público y operador) y **procedimiento para cuando entra una fuente nueva**.

## 1. Qué manda hoy

| Rol | Fuente | Dónde vive | Quién la ve |
| --- | --- | --- | --- |
| Serie producto | `dem_filled.tif` (Copernicus GLO-30, ~30 m) | disco, salida de la corrida DEM | público y operador |
| Chequeo local | `mde_ar.tif` (IGN, SRVN16), hermano del `dem_filled.tif` | disco, mosaico propio | público y operador |
| Chequeo GEE | AW3D30 v4.1 (JAXA) y NASADEM | Earth Engine, ≤400 muestras | **solo operador** |

Reglas duras:

- **Nunca** una superficie quemada, hidro-rellenada o simulada (`dem_filled_hydro.tif`,
  `dem_filled_escenario.tif`): `resolver_dem_filled` es el portero y rechaza cualquier
  nombre que no sea `dem_filled.tif`.
- GLO-30 es una superficie de ~30 m: **no es cota de proyecto** ni sección de canal.
  El disclaimer viaja en la respuesta (`disclaimer`) y la UI lo muestra siempre.
- MDE-Ar es SRVN16 y GLO-30 es EGM: **el delta entre ambos no es altura verdadera**.
- GEE nunca entra en la ruta pública (ver §3).
- Topes vigentes: 200 km de traza, 2000 puntos muestreados, nodata queda `null`
  (un hueco es un hueco, no cero).

## 2. Cómo se cachea y qué lo invalida

El perfil se guarda en Postgres (`elevation_profile_cache`) con la clave:

```
sha256( geometry_canónico + "|" + source_identity )

source_identity = series:v1 | dem_filled:<size>:<mtime_ns> | mde_ar:<size>:<mtime_ns>
                  (o mde_ar:absent)
```

Consecuencias, que son el contrato:

- Si **cambia el raster** (nueva corrida DEM, re-mosaico de MDE-Ar, borrar/agregar
  `mde_ar.tif`), cambia `size`/`mtime` → cambia la clave → **se recalcula**. No hay
  caché que pueda quedar apuntando a otra superficie.
- Si cambia la **lógica de muestreo** (paso de densificado, desplegado del retrazado,
  topes), se sube `SERIES_VERSION` en `app/domains/geo/elevation_profile_cache.py`
  y todo lo viejo queda invalidado.
- La geometría se hashea **sin redondear**: una traza distinta nunca pega en la clave
  de otra. No hay tolerancia.
- Solo se cachea la serie simple (`compare_dems=False`). La comparación GEE del
  operador **no se cachea** (jamás servir AW3D30/NASADEM desde un payload de GLO-30).
- Retención: al escribir se borran filas de más de 90 días. Las corridas DEM viejas
  dejan de pedirse y se vencen solas.
- La respuesta trae `cache: "hit" | "miss"` para diagnosticar sin mirar la base.

## 3. Qué hacer cuando entra una fuente nueva

Aplica a cualquier superficie nueva (un DEM regional mejor, un mosaico propio de
AW3D30/NASADEM, LiDAR, FABDEM si la licencia se lee y se acepta, etc.).

**Antes de tocar código**, contestá estas cuatro:

1. ¿Reemplaza a GLO-30 como serie producto, o entra como chequeo adicional?
   (Si reemplaza, el disclaimer y el texto de la UI cambian.)
2. ¿Cuál es su datum/vertical y su resolución real? Si el datum no es el mismo,
   el delta **no** se publica como altura verdadera.
3. ¿Se puede servir sin GEE (raster local) o depende de Earth Engine?
   Si depende de GEE: queda **solo operador**, detrás de `compare_dems`.
4. ¿La licencia permite redistribuir el producto derivado?

**Los 3 pasos técnicos:**

1. **Sumarla a la serie** en `perfil_de_geojson` / `adjuntar_series_opcionales`
   (nuevo sampler o raster local) y exponer su campo en la respuesta
   (`elevation_<fuente>` + `_disclaimer`), y en el tipo TS
   (`consorcio-web/src/lib/api/elevationProfile.ts`).
2. **Incluirla en `source_identity`** (`build_source_identity`): `size` + `mtime_ns`
   del archivo, o su identificador propio. **Si no entra en la clave, es un bug**:
   la caché seguiría sirviendo el perfil viejo con la fuente nueva ya disponible.
3. **Subir `SERIES_VERSION`** si además cambió cómo se muestrea (no si solo se
   agregó una columna al payload).

**Verificación mínima antes de dar por cerrada la fuente nueva:**

```bash
# 1. El perfil público responde y trae la fuente
curl -s -X POST https://cc10demayo-api.javierzader.com/api/v2/public/map/elevation-profile \
  -H 'Content-Type: application/json' \
  -d '{"geometry":{"type":"LineString","coordinates":[[-62.7,-32.6],[-62.702,-32.6]]}}' \
  | python3 -c 'import json,sys; d=json.load(sys.stdin); print(sorted(k for k in d if "disclaimer" in k), d.get("cache"))'

# 2. Repetir la MISMA traza: debe dar cache:"hit" y bajar de ~1 s a milisegundos
# 3. Cambiar el raster (o tocarlo) y repetir: debe volver a cache:"miss"
```

Y actualizar, en el mismo PR: esta tabla (§1), el disclaimer en la UI si cambió, y
el test que fija la clave (`tests/unit/test_elevation_profile_cache_key.py`).

## 4. Qué no hacer

- No agregar una fuente a la respuesta **sin** meterla en `source_identity`.
- No cachear la comparación GEE ni exponerla en la ruta pública.
- No extrapolar fuera de los datos: `interpolar_serie` solo interpola entre muestras.
- No mezclar datums y publicar el delta como cota.
- No reemplazar `dem_filled.tif` por una variante rellenada/quemada "para que se vea
  mejor".
