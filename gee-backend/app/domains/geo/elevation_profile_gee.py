"""Optional GEE DEM samples on the same vertices as the GLO-30 profile.

GLO-30 stays the product series. AW3D30 and NASADEM are consistency checks.
A GEE failure is a no-op: the local profile still returns.
"""

from __future__ import annotations

from typing import Any, Callable, Optional, Sequence

MAX_GEE_SAMPLES = 400
AW3D30_DISCLAIMER = (
    "AW3D30 v4.1 (JAXA, DSM óptico). GEE ≤400 muestras, el resto interpolado. "
    "Algunas teselas se rellenan con GLO-30."
)
NASADEM_DISCLAIMER = (
    "NASADEM (SRTM 2000, EGM96). GEE ≤400 muestras, el resto interpolado. No es cota de proyecto."
)


def indices_submuestreo(n: int, cap: int = MAX_GEE_SAMPLES) -> list[int]:
    """First, last, and evenly spaced indices. Cap GEE round-trips."""
    if n <= 0:
        return []
    if n <= cap:
        return list(range(n))
    step = (n - 1) / (cap - 1)
    return sorted({round(i * step) for i in range(cap)})


def interpolar_serie(
    distancias: Sequence[float], valores: Sequence[Optional[float]]
) -> list[Optional[float]]:
    """Linear in chainage between known samples. No extrapolation."""
    if len(distancias) != len(valores):
        raise ValueError("distancias y valores desalineados")
    known = [
        (index, distancias[index], valores[index])
        for index in range(len(valores))
        if valores[index] is not None
    ]
    filled: list[Optional[float]] = [None] * len(valores)
    if not known:
        return filled
    for index, _distance, value in known:
        filled[index] = value
    for left, right in zip(known, known[1:]):
        i0, d0, v0 = left
        i1, d1, v1 = right
        span = d1 - d0
        for index in range(i0 + 1, i1):
            if span == 0:
                filled[index] = v0
                continue
            t = (distancias[index] - d0) / span
            filled[index] = v0 + t * (v1 - v0)
    return filled


def aplicar_gee_dems(
    payload: dict[str, Any],
    *,
    sampler: Callable[
        [Sequence[tuple[float, float]]],
        tuple[list[Optional[float]], list[Optional[float]]],
    ]
    | None = None,
) -> dict[str, Any]:
    """Attach ``elevation_aw3d30`` / ``elevation_nasadem`` when GEE answers."""
    puntos = payload.get("puntos")
    if not isinstance(puntos, list) or not puntos:
        return payload
    lonlats: list[tuple[float, float]] = []
    for punto in puntos:
        lon = punto.get("lon")
        lat = punto.get("lat")
        if not isinstance(lon, (int, float)) or not isinstance(lat, (int, float)):
            return payload
        lonlats.append((float(lon), float(lat)))
    pick = indices_submuestreo(len(lonlats))
    subset = [lonlats[i] for i in pick]
    try:
        sample = sampler or _sample_aw3d30_nasadem
        aw_vals, nasa_vals = sample(subset)
    except Exception:
        return payload
    if len(aw_vals) != len(pick) or len(nasa_vals) != len(pick):
        return payload
    distancias = [float(punto["distance_m"]) for punto in puntos]
    aw_sparse: list[Optional[float]] = [None] * len(puntos)
    nasa_sparse: list[Optional[float]] = [None] * len(puntos)
    for index, aw_val, nasa_val in zip(pick, aw_vals, nasa_vals):
        aw_sparse[index] = aw_val
        nasa_sparse[index] = nasa_val
    aw_filled = interpolar_serie(distancias, aw_sparse)
    nasa_filled = interpolar_serie(distancias, nasa_sparse)
    for punto, aw_val, nasa_val in zip(puntos, aw_filled, nasa_filled):
        punto["elevation_aw3d30"] = aw_val
        punto["elevation_nasadem"] = nasa_val
    payload["aw3d30_disclaimer"] = AW3D30_DISCLAIMER
    payload["nasadem_disclaimer"] = NASADEM_DISCLAIMER
    return payload


def _finite_or_none(value: Any) -> Optional[float]:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if number != number:
        return None
    return number


def _sample_aw3d30_nasadem(
    lonlats: Sequence[tuple[float, float]],
) -> tuple[list[Optional[float]], list[Optional[float]]]:
    if not lonlats:
        return [], []
    from app.domains.geo.gee_service import _ensure_initialized
    import ee

    _ensure_initialized()
    features = [
        ee.Feature(ee.Geometry.Point(lon, lat), {"i": index})
        for index, (lon, lat) in enumerate(lonlats)
    ]
    stacked = (
        ee.ImageCollection("JAXA/ALOS/AW3D30/V4_1")
        .mosaic()
        .select(["DSM"], ["aw3d30"])
        .addBands(ee.Image("NASA/NASADEM_HGT/001").select(["elevation"], ["nasadem"]))
    )
    sampled = stacked.reduceRegions(
        collection=ee.FeatureCollection(features),
        reducer=ee.Reducer.first(),
        scale=30,
    )
    raw = sampled.getInfo()
    props_by_i: dict[int, dict[str, Any]] = {}
    for feature in raw.get("features") or []:
        props = feature.get("properties") or {}
        index = props.get("i")
        if isinstance(index, int):
            props_by_i[index] = props
    aw: list[Optional[float]] = []
    nasa: list[Optional[float]] = []
    for index in range(len(lonlats)):
        props = props_by_i.get(index, {})
        aw.append(_finite_or_none(props.get("aw3d30")))
        nasa.append(_finite_or_none(props.get("nasadem")))
    return aw, nasa
