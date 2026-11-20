"""Calibración del riesgo hídrico: agua observada vs clases flood_risk (PR 5).

What this ETL answers (plan S1): *qué parte de cada clase de ``flood_risk``
estuvo con agua en los eventos ancla (2015, 2017, 2025) y con cuánta lluvia.*

Per anchor event (``rainfall_extreme_event`` provenance='curated', the three
rows ``lluvia_ext_002`` seeded):

1. **Escena** — the rank-1 ``rainfall_event_imagery_candidate`` (slot='ranked'),
   the same choice the informe's section 8 miniatures make. No candidate →
   the event is skipped and REPORTED, never fabricated.
2. **Agua** — MNDWI ≥ 0,1 exactly like ``water_delta.py`` (its ``MNDWI_WATER``
   constant is imported, not retyped) over the chosen scene, requested as a
   GeoTIFF on the LOCAL flood_risk raster's own 30 m grid, so the class
   intersection is a plain numpy ``&`` — no resampling, no reprojection of the
   classes. Sentinel-1 candidates (S5: "si no hay óptica") use VH < -18 dB and
   are marked apart by ``sensor='sentinel1'`` in every row they produce.
3. **Lluvia** — CHIRPS daily summed over the 30 days before the event date,
   over the same zone geometry the rainfall domain uses
   (``zona_cc_ampliada``), via the same collection the informe's section 6
   normals come from (``UCSB-CHG/CHIRPS/DAILY``).
4. **Tabla** — one ``riesgo_validacion_evento`` row per (event, legend class)
   for the WHOLE zone. Idempotent: an event's rows are replaced on re-run, so
   the same scene + raster re-produces the same rows.

S8 risks are accepted and reported, not hidden: clouds are not masked (a
cloudy scene under-counts water; the candidate's ``cloud_pct`` travels in the
catalog), the scene may post-date the peak (water that already drained
under-counts), and MNDWI cannot tell a flood from a rice paddy or a permanent
lagoon (the arroz/clase-9 confusion — why per-class producer phrases stay
gated on the S7 monotonicity verdict).

Entry point: ``python -m app.domains.geo.calibracion_riesgo``.
"""

from __future__ import annotations

import sys
import uuid
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Any, Callable, Sequence

import structlog
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.domains.geo.class_breaks import RANGE_CONFIGS
from app.domains.geo.gee_service_analytics_support import CHIRPS_COLLECTION_ID
from app.domains.geo.rainfall.water_delta import MNDWI_WATER, optical_spec

logger = structlog.get_logger(__name__)

#: S5 verbatim: "cruce con las clases de flood_risk a 30 m".
ESCALA_M = 30

#: S5 verbatim: "CHIRPS diario sumado 30 días antes de la fecha del evento".
LLUVIA_VENTANA_DIAS = 30

#: CHIRPS daily collection — the SAME product the informe's section 6 normals
#: are generated from (``gee_service_analytics_support.CHIRPS_COLLECTION_ID``),
#: so the validation table and the report's rainfall never cite two different
#: CHIRPS families.

#: Sentinel-1 fallback (S5): open water (specular) reads VH well below
#: vegetation's -12..-8 dB; -18 dB is the conventional simple-flood edge.
#: Approximate and speckle-noisy by nature — every row it produces carries
#: ``sensor='sentinel1'`` so a reader can tell it apart from the MNDWI rows.
SAR_VH_UMBRAL_DB = -18.0

SAR_COLLECTION = "COPERNICUS/S1_GRD"

#: Curated anchor events (the three lluvia_ext_002 seeded) + their rank-1
#: imagery candidate — the informe's own queries, reused verbatim so the
#: validation table and section 8 miniatures can never disagree about scenes.
_EVENTOS_ANCLA_SQL = text(
    """
    SELECT event_key, start_date
    FROM rainfall_extreme_event
    WHERE provenance = 'curated'
    ORDER BY start_date
    """
)

_CANDIDATO_SQL = text(
    """
    SELECT DISTINCT ON (event_key)
           event_key, sensor, scene_id, scene_date, cloud_pct
    FROM rainfall_event_imagery_candidate
    WHERE slot = 'ranked'
    ORDER BY event_key, rank
    """
)

_FLOOD_LAYER_SQL = text(
    """
    SELECT id::text AS id, archivo_path
    FROM geo_layers
    WHERE tipo = 'flood_risk'
    ORDER BY created_at DESC, id DESC
    LIMIT 1
    """
)

BORRAR_EVENTO_SQL = text("DELETE FROM riesgo_validacion_evento WHERE evento_key = :evento_key")


@dataclass(frozen=True)
class GrillaRiesgo:
    """The local flood_risk raster's grid — the water mask is requested on it."""

    crs: str
    transform: tuple[float, float, float, float, float, float]
    width: int
    height: int


@dataclass(frozen=True)
class FilaClase:
    """One (event, class) measurement, before persistence."""

    clase: str
    ha_clase: float
    ha_con_agua: float
    pct_con_agua: float


# ── local geometry: class × water intersection ───────────────────────────────


def leer_grilla_riesgo(flood_path: str) -> GrillaRiesgo:
    """Read the flood_risk raster's CRS/transform/shape (its download target)."""
    import rasterio

    with rasterio.open(flood_path) as src:
        t = src.transform
        return GrillaRiesgo(
            crs=str(src.crs) if src.crs else "EPSG:4326",
            transform=(t.a, t.b, t.c, t.d, t.e, t.f),
            width=src.width,
            height=src.height,
        )


def clasificar_agua_por_clase(flood_path: str, agua_tif: bytes) -> list[FilaClase]:
    """Intersect a water GeoTIFF with the flood_risk classes, per class.

    ``agua_tif`` MUST already be on the flood raster's grid (the GEE request
    pins ``crs``/``crsTransform``/``dimensions`` to it); a shape mismatch is a
    hard ``ValueError`` — silently resampling one side onto the other is how a
    validation table ends up measuring nothing.
    """
    import numpy as np
    import rasterio
    from io import BytesIO

    from app.domains.geo.composites import _pixel_area  # noqa: SLF001 — PR 1 reuse

    with rasterio.open(flood_path) as src:
        clases_raster = src.read(1)
        nodata = src.nodata
        _, pixel_ha = _pixel_area(src)

    with rasterio.open(BytesIO(agua_tif)) as agua:
        if agua.width != clases_raster.shape[1] or agua.height != clases_raster.shape[0]:
            raise ValueError(
                f"grilla de agua ({agua.width}x{agua.height}) no coincide con la del "
                f"raster de riesgo ({clases_raster.shape[1]}x{clases_raster.shape[0]})"
            )
        agua_arr = agua.read(1)

    datos = clases_raster.astype(np.float64, copy=False)
    valido = ~np.isnan(datos)
    if nodata is not None:
        valido &= datos != nodata
    con_agua = agua_arr > 0

    filas: list[FilaClase] = []
    ultimo = len(RANGE_CONFIGS["flood_risk"]) - 1
    for indice, cfg in enumerate(RANGE_CONFIGS["flood_risk"]):
        minimo, maximo = float(cfg["min"]), float(cfg["max"])
        if indice == ultimo:
            miembro = (datos >= minimo) & (datos <= maximo)
        else:
            miembro = (datos >= minimo) & (datos < maximo)
        pixels = int(np.count_nonzero(miembro & valido))
        mojados = int(np.count_nonzero(miembro & valido & con_agua))
        filas.append(
            FilaClase(
                clase=str(cfg["label"]),
                ha_clase=round(pixels * pixel_ha, 4),
                ha_con_agua=round(mojados * pixel_ha, 4),
                pct_con_agua=round(mojados / pixels * 100.0, 2) if pixels else 0.0,
            )
        )
    return filas


def veredicto_monotonia(filas: Sequence[FilaClase]) -> dict[str, Any]:
    """S7 acceptance: does % con agua grow from Bajo to Crítico?

    Weak monotonicity (``<=``): ties are tolerated — the plan's gate is
    "crece", not "crece estrictamente". The verdict gates the S11 per-class
    phrases: if this is False on the REAL data, no phrases ship and Javier
    gets told before any publication.
    """
    orden = [str(cfg["label"]) for cfg in RANGE_CONFIGS["flood_risk"]]
    por_clase = {fila.clase: fila.pct_con_agua for fila in filas}
    serie = [por_clase.get(clase) for clase in orden]
    if any(valor is None for valor in serie):
        return {"monotonico": False, "pcts": por_clase, "motivo": "clases ausentes"}
    valores = [float(v) for v in serie if v is not None]
    monotonico = all(valores[i] <= valores[i + 1] for i in range(len(valores) - 1))
    return {"monotonico": monotonico, "pcts": por_clase, "motivo": None}


# ── GEE fetchers (seams: tests inject fakes; CI never touches the network) ───


def _descarga_gee(imagen, grilla: GrillaRiesgo, requests_module) -> bytes:
    """Download one band as a GeoTIFF EXACTLY on the local risk grid."""
    url = imagen.getDownloadURL(
        {
            "format": "GEO_TIFF",
            "crs": grilla.crs,
            "crsTransform": list(grilla.transform),
            # GEE espera "WxH" (string) o [W, H] — un dict {width, height}
            # produce "Invalid dimensions" en el servidor (cazado en el box
            # 2026-11-19; los mocks locales no ejercitan la API real).
            "dimensions": [grilla.width, grilla.height],
        }
    )
    respuesta = requests_module.get(url, timeout=180)
    respuesta.raise_for_status()
    return respuesta.content


def mascara_agua_gee(
    sensor: str,
    scene_id: str,
    grilla: GrillaRiesgo,
    *,
    ee_module: Any | None = None,
    requests_module: Any | None = None,
) -> bytes | None:
    """Water GeoTIFF (0/1) for one scene on ``grilla`` — the GEE seam.

    Optical sensors follow ``water_delta`` exactly: MNDWI (green-SWIR1)/(green+SWIR1)
    ≥ ``MNDWI_WATER`` over the scene's own collection. Sentinel-1 (no optical
    candidate) thresholds VH < -18 dB over S1_GRD — approximate, marked apart
    downstream by ``sensor``. Returns ``None`` when the scene cannot be
    resolved (missing id, unknown sensor) so the caller skips the event
    instead of storing a zero-water fiction.
    """
    import ee
    import requests

    ee_mod = ee_module if ee_module is not None else ee
    req_mod = requests_module if requests_module is not None else requests

    from app.domains.geo.gee_service import _ensure_initialized  # noqa: SLF001

    _ensure_initialized()
    if sensor == "sentinel1":
        coleccion = ee_mod.ImageCollection(SAR_COLLECTION).filter(
            ee_mod.Filter.eq("system:index", scene_id)
        )
        if int(coleccion.size().getInfo() or 0) == 0:
            return None
        agua = (
            coleccion.first().select("VH").lt(SAR_VH_UMBRAL_DB).unmask(0).toByte().rename("water")
        )
        return _descarga_gee(agua, grilla, req_mod)

    spec = optical_spec(sensor)
    if spec is None:
        logger.warning("calibracion.sensor_sin_espec", sensor=sensor, scene=scene_id)
        return None
    coleccion = ee_mod.ImageCollection(spec["collection"]).filter(
        ee_mod.Filter.eq("system:index", scene_id)
    )
    if int(coleccion.size().getInfo() or 0) == 0:
        return None
    imagen = coleccion.first()
    verde = imagen.select(spec["green"]).divide(spec["reflectance"])
    swir = imagen.select(spec["swir"]).divide(spec["reflectance"])
    mndwi = verde.subtract(swir).divide(verde.add(swir))
    agua = mndwi.gte(MNDWI_WATER).unmask(0).toByte().rename("water")
    return _descarga_gee(agua, grilla, req_mod)


def lluvia_30d_gee(
    fecha: date,
    *,
    zonal_series_fn: Callable[..., list[tuple[datetime, float | None]]] | None = None,
) -> float | None:
    """CHIRPS daily sum over [fecha-30, fecha), zone ``zona_cc_ampliada``.

    ``None`` when the series comes back empty (no coverage for the window) —
    the row stores NULL and the report prints «—», never a 0 mm that reads as
    "no llovió".
    """
    from app.domains.geo.rainfall.adapters.gee_client import GeeZonalClient

    cliente = GeeZonalClient()
    serie_fn = zonal_series_fn or cliente.zonal_series
    geometria = cliente.geometry(scope_kind="provider_asset", scope_id="zona_cc_ampliada")
    inicio = datetime(fecha.year, fecha.month, fecha.day, tzinfo=timezone.utc) - timedelta(
        days=LLUVIA_VENTANA_DIAS
    )
    fin = datetime(fecha.year, fecha.month, fecha.day, tzinfo=timezone.utc)
    serie = serie_fn(
        collection_id=CHIRPS_COLLECTION_ID,
        start=inicio,
        end=fin,
        geometry=geometria,
        band="precipitation",
    )
    valores = [valor for _momento, valor in serie if valor is not None]
    if not valores:
        return None
    return round(sum(valores), 2)


# ── orchestration ─────────────────────────────────────────────────────────────


def run_calibracion(
    db: Session,
    *,
    fetch_agua: Callable[[str, str, GrillaRiesgo], bytes | None],
    fetch_lluvia: Callable[[date], float | None],
    flood_path: str | None = None,
    version_flood_risk: str | None = None,
) -> dict[str, Any]:
    """Fill ``riesgo_validacion_evento`` for every anchor event. Idempotent.

    Per-event isolation: one event's GEE failure (scene gone, sensor unknown,
    download error) skips THAT event with a ``motivo`` in the summary — the
    other events still load, because a validation table with 2 of 3 events is
    strictly better than no table at all.

    Flushes but does NOT commit; the CLI (and only the CLI) commits, so tests
    run inside their rollback session untouched.
    """
    from app.domains.geo.intelligence.models import RiesgoValidacionEvento

    if flood_path is None or version_flood_risk is None:
        capa = db.execute(_FLOOD_LAYER_SQL).first()
        if capa is None:
            return {"status": "skipped", "reason": "no hay raster flood_risk registrado"}
        flood_path = flood_path or capa.archivo_path
        version_flood_risk = version_flood_risk or capa.id

    grilla = leer_grilla_riesgo(flood_path)

    try:
        with db.begin_nested():
            eventos = db.execute(_EVENTOS_ANCLA_SQL).all()
            candidatos = {str(fila.event_key): fila for fila in db.execute(_CANDIDATO_SQL).all()}
    except SQLAlchemyError:
        logger.warning("calibracion.eventos_no_disponibles", exc_info=True)
        return {"status": "skipped", "reason": "catálogo de eventos no disponible"}

    detalle: list[dict[str, Any]] = []
    for evento in eventos:
        clave = str(evento.event_key)
        fecha = evento.start_date
        entrada: dict[str, Any] = {
            "evento_key": clave,
            "fecha": fecha.isoformat(),
            "filas": 0,
            "monotonia": None,
            "motivo": None,
        }
        candidato = candidatos.get(clave)
        if candidato is None:
            entrada["motivo"] = "sin candidata de imagen"
            detalle.append(entrada)
            continue
        try:
            agua_tif = fetch_agua(str(candidato.sensor), str(candidato.scene_id), grilla)
            if agua_tif is None:
                entrada["motivo"] = f"escena no resoluble ({candidato.scene_id})"
                detalle.append(entrada)
                continue
            filas = clasificar_agua_por_clase(flood_path, agua_tif)
            lluvia = fetch_lluvia(fecha)
            db.execute(BORRAR_EVENTO_SQL, {"evento_key": clave})
            db.add_all(
                [
                    RiesgoValidacionEvento(
                        id=uuid.uuid4(),
                        evento_key=clave,
                        fecha=fecha,
                        clase=fila.clase,
                        ha_clase=fila.ha_clase,
                        ha_con_agua=fila.ha_con_agua,
                        pct_con_agua=fila.pct_con_agua,
                        lluvia_30d_mm=lluvia,
                        sensor=str(candidato.sensor),
                        escena_id=str(candidato.scene_id),
                        version_flood_risk=str(version_flood_risk),
                    )
                    for fila in filas
                ]
            )
            db.flush()
            entrada["filas"] = len(filas)
            entrada["lluvia_30d_mm"] = lluvia
            entrada["sensor"] = str(candidato.sensor)
            entrada["escena"] = str(candidato.scene_id)
            entrada["monotonia"] = veredicto_monotonia(filas)
        except Exception as exc:  # noqa: BLE001 — per-event isolation (S8)
            entrada["motivo"] = f"{type(exc).__name__}: {exc}"
            logger.warning("calibracion.evento_fallo", evento_key=clave, error=str(exc))
        detalle.append(entrada)

    cargados = sum(1 for entrada in detalle if entrada["filas"])
    monotonia_global = (
        all(entrada["monotonia"] and entrada["monotonia"]["monotonico"] for entrada in detalle)
        if cargados
        else None
    )
    resultado = {
        "status": "completed" if cargados else "skipped",
        "eventos_cargados": cargados,
        "version_flood_risk": str(version_flood_risk),
        "monotonia": monotonia_global,
        "eventos": detalle,
    }
    logger.info(
        "calibracion.lista",
        eventos=cargados,
        monotonia=monotonia_global,
        version=str(version_flood_risk),
    )
    return resultado


# ── CLI (module entry point — the container ships only ``app/``) ─────────────


def main(argv: Sequence[str] | None = None) -> int:  # pragma: no cover — network/CLI
    import argparse

    parser = argparse.ArgumentParser(
        prog="python -m app.domains.geo.calibracion_riesgo",
        description="Carga riesgo_validacion_evento: agua MNDWI/SAR por clase de "
        "flood_risk en los eventos ancla + CHIRPS 30 días (idempotente).",
    )
    parser.parse_args(argv)

    from app.db.session import SessionLocal

    try:
        with SessionLocal() as db:
            resultado = run_calibracion(
                db,
                fetch_agua=mascara_agua_gee,
                fetch_lluvia=lluvia_30d_gee,
            )
            db.commit()
    except SQLAlchemyError as exc:
        print(f"ERROR DE BASE DE DATOS: {exc}", file=sys.stderr)
        return 1

    for evento in resultado.get("eventos", []):
        motivo = f" — {evento['motivo']}" if evento.get("motivo") else ""
        print(f"  {evento['evento_key']} ({evento['fecha']}): {evento['filas']} filas{motivo}")
    print(
        f"Calibración: {resultado.get('eventos_cargados', 0)} eventos cargados, "
        f"monotonía Bajo→Crítico: {resultado.get('monotonia')}"
    )
    return 0


if __name__ == "__main__":  # pragma: no cover — module entry point
    raise SystemExit(main())
