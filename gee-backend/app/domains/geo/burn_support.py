"""Stream burning: grabar la red de canales en el DEM antes del analisis.

Los canales del consorcio miden metros de ancho; el DEM (Copernicus GLO-30,
celda de 30 m) no los ve. Sin este paso, ``flow_accumulation`` calcula por
donde iria el agua SIN el sistema de canales — exactamente la informacion
equivocada para un consorcio canalero. "Quemar" la red (bajar la cota del DEM
a lo largo de las trazas de ``canal_network``) fuerza al modelo hidrologico a
respetar el drenaje real. Es la tecnica estandar para drenaje antropico
(Saunders 1999; metodo AGREE).

Dos decisiones deliberadas que el consumidor de este modulo debe respetar:

- El DEM quemado es FICCION deliberada: solo debe alimentar los derivados
  hidrologicos (flow_dir, flow_acc, TWI). Pendiente, aspecto, hillshade y el
  visor 3D deben seguir usando el DEM sin quemar, o mostraran zanjas de
  ``burn_depth_m`` metros que no existen.
- La celda sigue siendo de 30 m: la zanja quemada es de una celda de ancho
  aunque el canal real mida 3 m. Esto corrige el "hacia donde" del agua, no
  sirve para hidraulica (caudales, velocidades).

Modulo puro al estilo del resto de ``geo``: sin acceso a base de datos ni a
Celery. El llamador provee las geometrias (GeoJSON, EPSG:4326) y las rutas.
"""

from __future__ import annotations

import json
from typing import Any

DEFAULT_BURN_DEPTH_M = 10.0
"""Profundidad por defecto del quemado, en metros.

No hay valor "correcto": poco no captura el canal frente al ruido del DEM
(el error vertical del GLO-30 es de ~2-4 m), demasiado crea drenajes
paralelos artificiales en los bordes de la zanja. 10 m es el rango
conservador habitual para condicionamiento en llanura. Queda registrado en
los parametros del job para que cada corrida sea trazable.
"""


def burn_canals_impl(
    *,
    dem_path: str,
    canal_geojsons: list[str],
    output_path: str,
    burn_depth_m: float = DEFAULT_BURN_DEPTH_M,
) -> str | None:
    """Baja ``burn_depth_m`` la cota del DEM a lo largo de las trazas.

    Devuelve ``output_path`` con el DEM quemado, o ``None`` cuando no hay
    canales — el pipeline debe seguir con el DEM original, no fallar: un area
    sin red digitalizada es un caso normal, no un error.
    """
    if not canal_geojsons:
        return None
    if burn_depth_m <= 0:
        raise ValueError(f"burn_depth_m debe ser positivo, llego {burn_depth_m}")

    # Import diferido: rasterio vive en la imagen del geo-worker; el resto del
    # backend importa este modulo sin pagar (ni requerir) la dependencia.
    import rasterio
    from rasterio.features import geometry_mask
    from rasterio.warp import transform_geom

    geometrias: list[dict[str, Any]] = [json.loads(g) for g in canal_geojsons]

    with rasterio.open(dem_path) as src:
        dem = src.read(1, masked=True)
        perfil = src.profile

        # Las trazas llegan en EPSG:4326 (asi viven en canal_network). Si el
        # DEM esta en otro CRS, reproyectar la geometria — no el raster.
        if src.crs is not None and src.crs.to_epsg() != 4326:
            geometrias = [transform_geom("EPSG:4326", src.crs, g) for g in geometrias]

        # all_touched: una traza que cruza la esquina de una celda tambien la
        # quema. Con lineas de un pixel de ancho, perder celdas corta la zanja
        # y el fill posterior la rellena — el canal desaparece del modelo.
        mascara = geometry_mask(
            geometrias,
            out_shape=dem.shape,
            transform=src.transform,
            invert=True,
            all_touched=True,
        )

    quemado = dem.astype("float32")
    quemado[mascara] = quemado[mascara] - burn_depth_m

    perfil.update(dtype="float32")
    # Un DEM de entrada tileado (COG) arrastra blockxsize/blockysize en el
    # perfil; escribir un GTiff plano con esos campos y sin TILED=YES hace que
    # GDAL los ignore CON warning. Mejor no arrastrarlos.
    if not perfil.get("tiled"):
        perfil.pop("blockxsize", None)
        perfil.pop("blockysize", None)
    with rasterio.open(output_path, "w", **perfil) as dst:
        dst.write(quemado.filled(perfil.get("nodata") or -9999.0), 1)

    return output_path
