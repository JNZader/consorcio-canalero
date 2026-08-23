from __future__ import annotations

import math
import tempfile
from pathlib import Path
from typing import Any, Optional

import numpy as np
from shapely.geometry import LineString, mapping

#: WBT's D8 pointer codes as **array-space** ``(Δrow, Δcol)`` offsets.
#:
#: Extracted from the function-local dict that used to live inside
#: ``simular_escorrentia_impl`` so both readers share ONE definition. The values
#: are unchanged.
#:
#: These are array offsets, **not compass directions**. Turning one into an
#: azimuth is only the familiar ``1=E, 2=NE, 4=N, …`` when the raster is
#: north-up; on a rotated or south-up transform the same table silently rotates
#: every direction reported. Use :func:`azimut_desde_transform`, never this dict
#: plus a remembered compass table.
D8_OFFSETS: dict[int, tuple[int, int]] = {
    1: (0, 1),
    2: (-1, 1),
    4: (-1, 0),
    8: (-1, -1),
    16: (0, -1),
    32: (1, -1),
    64: (1, 0),
    128: (1, 1),
}


class CruceDerivationError(RuntimeError):
    """The road-crossing derivation refuses to guess.

    Raised for conditions where continuing would produce a confident wrong
    answer rather than no answer: a raster whose transform is not north-up (every
    reported azimuth would be silently rotated), and an intersection geometry
    neither this design nor PostGIS's documented return set anticipated.
    """


def azimut_desde_transform(pointer_value: Any, transform) -> Optional[float]:
    """Compass azimuth of a D8 pointer code, derived FROM the raster transform.

    The offset is turned into a world-space displacement
    ``(Δx, Δy) = (t.a·Δcol + t.b·Δrow, t.d·Δcol + t.e·Δrow)`` and the azimuth is
    ``degrees(atan2(Δx, Δy)) mod 360`` — correct for any affine, rather than
    correct for the one affine somebody had in mind.

    The north-up assertion is nonetheless kept and is deliberately a **refusal**:
    the pipeline's own reprojection produces north-up UTM
    (``tasks_dem_support.py:608``), so a rotated DEM means the whole pipeline's
    raster assumptions need review, not just this reader's. Stopping beats
    reporting wrong directions confidently.

    Returns ``None`` — never ``0.0`` — when the cell carries nodata or a value
    absent from :data:`D8_OFFSETS`. Zero is a direction (due north), so a
    zero-filled "unknown" is a fabricated finding; the caller turns ``None`` into
    an ``excluidos`` entry.
    """
    if not (transform.b == 0 and transform.d == 0 and transform.e < 0):
        raise CruceDerivationError(
            "the drainage raster is not north-up "
            f"(b={transform.b}, d={transform.d}, e={transform.e}); "
            "every reported azimuth would be silently rotated"
        )
    try:
        code = int(pointer_value)
    except (TypeError, ValueError):
        return None
    offset = D8_OFFSETS.get(code)
    if offset is None:
        return None
    d_row, d_col = offset
    dx = transform.a * d_col + transform.b * d_row
    dy = transform.d * d_col + transform.e * d_row
    return math.degrees(math.atan2(dx, dy)) % 360.0


def calcular_indice_criticidad_hidrica_impl(
    pendiente: float,
    acumulacion: float,
    twi: float,
    dist_canal: float,
    hist_inundacion: float,
    *,
    pesos: Optional[dict[str, float]],
    default_weights: dict[str, float],
    round_score,
) -> float:
    w = pesos if pesos is not None else default_weights
    return round_score(
        (
            w["pendiente"] * pendiente
            + w["acumulacion"] * acumulacion
            + w["twi"] * twi
            + w["dist_canal"] * dist_canal
            + w["hist_inundacion"] * hist_inundacion
        )
        * 100.0
    )


def clasificar_nivel_riesgo_impl(indice: float) -> str:
    return (
        "critico"
        if indice >= 75
        else "alto"
        if indice >= 50
        else "medio"
        if indice >= 25
        else "bajo"
    )


def clasificar_severidad_conflicto_impl(acumulacion: float, pendiente: float) -> str:
    return (
        "alta"
        if acumulacion > 5000 or pendiente < 0.5
        else "media"
        if acumulacion > 2000 or pendiente < 2.0
        else "baja"
    )


def detectar_puntos_conflicto_impl(
    canales_gdf,
    caminos_gdf,
    drenajes_gdf,
    flow_acc_path: str,
    slope_path: str,
    *,
    buffer_m: float,
    flow_acc_threshold: float,
    slope_threshold: float,
    classify_severity,
    build_empty_geojson,
):
    import geopandas as gpd
    import rasterio
    from rasterio.transform import rowcol

    conflicts: list[dict[str, Any]] = []
    for tipo, gdf_a, gdf_b in [
        ("canal_camino", canales_gdf, caminos_gdf),
        ("canal_drenaje", canales_gdf, drenajes_gdf),
        ("camino_drenaje", caminos_gdf, drenajes_gdf),
    ]:
        if gdf_a.empty or gdf_b.empty:
            continue
        with (
            rasterio.open(flow_acc_path) as fa_src,
            rasterio.open(slope_path) as sl_src,
        ):
            fa_data, sl_data = fa_src.read(1), sl_src.read(1)
            fa_transform, sl_transform = fa_src.transform, sl_src.transform
            buffered = gdf_a.copy()
            buffered["geometry"] = buffered.geometry.buffer(buffer_m)
            for _, row in gpd.overlay(
                buffered, gdf_b, how="intersection", keep_geom_type=False
            ).iterrows():
                centroid = row.geometry.centroid
                try:
                    fa_row, fa_col = rowcol(fa_transform, centroid.x, centroid.y)
                    sl_row, sl_col = rowcol(sl_transform, centroid.x, centroid.y)
                    fa_val = (
                        float(fa_data[fa_row, fa_col])
                        if 0 <= fa_row < fa_data.shape[0] and 0 <= fa_col < fa_data.shape[1]
                        else 0.0
                    )
                    sl_val = (
                        float(sl_data[sl_row, sl_col])
                        if 0 <= sl_row < sl_data.shape[0] and 0 <= sl_col < sl_data.shape[1]
                        else 0.0
                    )
                except Exception:
                    fa_val = sl_val = 0.0
                if fa_val > flow_acc_threshold and sl_val < slope_threshold:
                    conflicts.append(
                        {
                            "tipo": tipo,
                            "geometry": centroid,
                            "descripcion": f"Cruce {tipo.replace('_', '/')} — acum={fa_val:.0f}, pend={sl_val:.1f}°",
                            "severidad": classify_severity(fa_val, sl_val),
                            "acumulacion_valor": fa_val,
                            "pendiente_valor": sl_val,
                        }
                    )
    return (
        gpd.GeoDataFrame(conflicts, geometry="geometry", crs="EPSG:4326")
        if conflicts
        else build_empty_geojson(
            [
                "tipo",
                "geometry",
                "descripcion",
                "severidad",
                "acumulacion_valor",
                "pendiente_valor",
            ]
        )
    )


# ---------------------------------------------------------------------------
# Road × flow crossings — a SIBLING of detectar_puntos_conflicto_impl, not an
# extension of it (design D3)
# ---------------------------------------------------------------------------

#: The closed set of reasons a `flujo_natural` candidate is not stored. Closed on
#: purpose: `excluidos` is the run's own account of what it decided not to keep,
#: and an open-ended motivo string is an account nobody can read.
MOTIVOS_EXCLUSION: frozenset[str] = frozenset(
    {
        "sin_direccion",
        "flujo_paralelo",
        "suprimido_por_separacion",
        "maximo_en_extremo",
    }
)

#: The frame this derivation returns, in order. No `severidad`, no
#: `acumulacion_valor`, no `pendiente_valor` — this capability derives a
#: direction, an area and a relative rank, and a column that would have to be
#: invented to be filled does not belong on it (design D1).
CRUCE_COLUMNS: tuple[str, ...] = (
    "tipo",
    "geometry",
    "tramo_ref",
    "canal_ref",
    "direccion_flujo_deg",
    "rumbo_camino_deg",
    "lado_cruce",
    "area_aporte_ha",
    "orden_ranking",
    "confianza",
    "nota",
)


def _traversal_cells(line, transform, shape) -> list[tuple[int, int]]:
    """The ordered cell traversal of a polyline, in along-road order.

    Bresenham-style: the cells the road actually passes through, deduplicated,
    keeping the first visit of each. Cells outside the raster footprint are
    **skipped**, not excluded — a road that leaves the DEM is still in scope for
    the part of it that does not (design D3, "spatial pre-filter — scope, not
    exclusion").
    """
    from rasterio.transform import rowcol

    height, width = shape
    cells: list[tuple[int, int]] = []
    seen: set[tuple[int, int]] = set()
    coords = list(line.coords)
    # Step along each chord at a third of a cell so no cell is stepped over.
    step = min(abs(transform.a), abs(transform.e)) / 3.0
    for (x0, y0), (x1, y1) in zip(coords, coords[1:]):
        span = math.hypot(x1 - x0, y1 - y0)
        samples = max(int(span / step) + 1, 2)
        for i in range(samples + 1):
            t = i / samples
            x, y = x0 + (x1 - x0) * t, y0 + (y1 - y0) * t
            row, col = rowcol(transform, x, y)
            row, col = int(row), int(col)
            if (row, col) in seen:
                continue
            seen.add((row, col))
            if 0 <= row < height and 0 <= col < width:
                cells.append((row, col))
    return cells


def _cell_center(transform, row: int, col: int) -> tuple[float, float]:
    return transform * (col + 0.5, row + 0.5)


def _local_bearing(
    cells: list[tuple[int, int]], index: int, transform, bearing_window_m: float
) -> float:
    """Compass azimuth of the road at ``index``, over a ±``bearing_window_m`` chord.

    Taken from the chord between the traversal cells that far along the road in
    each direction, so a single jagged rasterization step cannot dominate the
    angle test. Near a segment end it falls back to the nearest available cells.
    """
    cell_size = min(abs(transform.a), abs(transform.e))
    span = max(int(round(bearing_window_m / cell_size)), 1)
    lo = max(index - span, 0)
    hi = min(index + span, len(cells) - 1)
    if lo == hi:
        lo, hi = 0, len(cells) - 1
    x0, y0 = _cell_center(transform, *cells[lo])
    x1, y1 = _cell_center(transform, *cells[hi])
    return math.degrees(math.atan2(x1 - x0, y1 - y0)) % 360.0


def _acute_angle(a: float, b: float) -> float:
    """The bearing-insensitive angle between two azimuths, in ``[0, 90]``.

    A flow at 170° to the road is running alongside it, not across it, so the
    angle is folded twice: once modulo 180 (direction of travel is irrelevant)
    and once about 90.
    """
    delta = abs(a - b) % 180.0
    return min(delta, 180.0 - delta)


def clasificar_banda_cruce(
    theta_deg: float, parallel_min_angle_deg: float, parallel_high_angle_deg: float
) -> Optional[str]:
    """The three-band crossing predicate. ``None`` means excluded as parallel.

    A binary cut claims a precision the inputs do not have: the D8 azimuth is
    **quantized to 45°** by construction (eight codes) and the road bearing is
    read off a rasterized polyline whose stair-steps leave roughly ±10° of error
    even over a ``BEARING_WINDOW_M`` chord. Their combined uncertainty is of the
    same order as the distance from a 30° cut to either neighbouring D8 step, so
    near the threshold a binary verdict is a coin toss dressed as a measurement.

    ==========================  ==========================================
    ``θ < 22.5``                excluded — below half a D8 step
    ``22.5 ≤ θ < 45``           kept, ``confianza='baja'`` — the
                                quantization band, where the true angle
                                could fall on either side of the cut
    ``θ ≥ 45``                  kept, ``confianza='alta'`` — a full D8 step
    ==========================  ==========================================

    Both edges belong to the band **above** them: excluding the whole middle band
    would throw away every genuinely oblique crossing, and including it silently
    would present a coin toss as a finding. This is a separate function precisely
    so both edges can be exercised at exactly 22.5 and exactly 45 — through the
    full derivation they cannot be, because the bearing is deliberately taken
    from the rasterized traversal rather than from the input line.
    """
    if theta_deg < parallel_min_angle_deg:
        return None
    return "baja" if theta_deg < parallel_high_angle_deg else "alta"


def _lado_cruce(flow_azimuth: float, road_bearing: float) -> str:
    """Which flank the water passes from, relative to the road's digitization.

    The sign of the cross product of the road vector and the flow vector. The
    reference frame is the *stored* direction of travel, which is why
    ``rumbo_camino_deg`` is persisted alongside: a left/right label whose
    reference direction is not stored is not a direction.
    """
    fr = math.radians(flow_azimuth)
    rr = math.radians(road_bearing)
    fx, fy = math.sin(fr), math.cos(fr)
    rx, ry = math.sin(rr), math.cos(rr)
    cross = rx * fy - ry * fx
    return "izq_a_der" if cross > 0 else "der_a_izq"


def _maxima_runs(profile: list[float]) -> list[tuple[int, int]]:
    """``(start, end)`` index bounds of every strict local maximum run.

    One entry per plateau; a single-cell maximum is ``(i, i)``. Endpoints are
    excluded per the rule above.
    """
    runs: list[tuple[int, int]] = []
    n = len(profile)
    i = 1
    while i < n - 1:
        j = i
        while j + 1 < n and profile[j + 1] == profile[i]:
            j += 1
        if j > n - 2:
            break
        if profile[i] > profile[i - 1] and profile[i] > profile[j + 1]:
            runs.append((i, j))
        i = j + 1
    return runs


def _plateau_pick(cells: list[tuple[int, int]], start: int, end: int) -> int:
    """The plateau's traversal index whose CELL is lexicographically smallest.

    A property of the cells, not of the order they were visited in, so it is
    invariant under a reversed digitization for **any** plateau length. The
    round-2 midpoint index ``floor((i+j)/2)`` is invariant only for odd-length
    runs, and a two-cell ridge crest — the common case — produced different
    points for the same road digitized in opposite directions. No tie-break is
    needed: no two distinct cells share a ``(row, col)`` pair.
    """
    return min(range(start, end + 1), key=lambda k: cells[k])


def _along_road_distances(cells: list[tuple[int, int]], transform) -> list[float]:
    """Cumulative along-road distance of each traversal cell, in metres."""
    distances = [0.0]
    for previous, current in zip(cells, cells[1:]):
        x0, y0 = _cell_center(transform, *previous)
        x1, y1 = _cell_center(transform, *current)
        distances.append(distances[-1] + math.hypot(x1 - x0, y1 - y0))
    return distances


def _suppress_by_separation(
    candidates: list[dict[str, Any]], min_separation_m: float
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Greedy min-separation suppression that RECORDS what it suppressed.

    Order: accumulation descending, ties on along-road index ascending — a total
    order, so the outcome is reproducible. Accept the head, suppress every
    candidate within ``min_separation_m`` along the road, repeat.

    Suppression is kept because without it one accumulation ridge registers as
    three or four adjacent cells, which is the far more common failure. But a
    watercourse that genuinely crosses the same road twice inside the window is a
    real, operationally meaningful pattern, so every candidate swallowed here is
    returned as an exclusion carrying its distance to the accepted point and its
    accumulation. The double crossing stays visible in the run record even though
    only one point is ranked.
    """
    ordered = sorted(candidates, key=lambda c: (-c["acumulacion"], c["indice"]))
    accepted: list[dict[str, Any]] = []
    suppressed: list[dict[str, Any]] = []
    taken: list[dict[str, Any]] = []
    for candidate in ordered:
        winner = next(
            (
                a
                for a in taken
                if a["tramo_ref"] == candidate["tramo_ref"]
                and abs(a["distancia"] - candidate["distancia"]) < min_separation_m
            ),
            None,
        )
        if winner is None:
            taken.append(candidate)
            accepted.append(candidate)
        else:
            suppressed.append(
                {
                    "tramo_ref": candidate["tramo_ref"],
                    "motivo": "suprimido_por_separacion",
                    "acumulacion": candidate["acumulacion"],
                    "distancia_m": abs(winner["distancia"] - candidate["distancia"]),
                }
            )
    return accepted, suppressed


def _decompose_intersection(geometry, road_id: str, canal_id: str) -> list[dict[str, Any]]:
    """Turn an arbitrary line×line intersection into Point rows.

    ``cruce_camino.geometria`` is ``geometry(Point, 4326)``, and
    ``ST_Intersection`` of two LineStrings does not always return a Point. A road
    built **along a canal bank** — common, since the spoil bank is the driest
    ground available — returns a LINESTRING overlap, and inserting one into a
    Point column aborts the whole area's run for a data pattern that is normal
    rather than exceptional.

    * ``POINT`` → one row.
    * ``MULTIPOINT`` / ``GEOMETRYCOLLECTION`` → dumped; every Point member is its
      own row (they are genuinely separate crossings), non-Point members fall
      through to the rule below rather than being discarded.
    * ``LINESTRING`` / ``MULTILINESTRING`` → ONE row per overlap component at its
      midpoint, ``confianza='baja'`` and a ``nota`` naming the shared length. A
      shared alignment is a real operational fact — it is where a bank collapse
      takes the road with it — so it is surfaced, but it is not a point crossing
      and the row says so.
    * anything else → a hard error naming BOTH ids, because at that point the
      geometry is something neither this design nor PostGIS's documented return
      set anticipated.
    """
    if geometry is None or geometry.is_empty:
        return []
    kind = geometry.geom_type
    if kind == "Point":
        return [{"geometry": geometry, "confianza": None, "nota": None}]
    if kind in ("MultiPoint", "GeometryCollection", "MultiLineString"):
        rows: list[dict[str, Any]] = []
        for member in geometry.geoms:
            rows.extend(_decompose_intersection(member, road_id, canal_id))
        return rows
    if kind == "LineString":
        midpoint = geometry.interpolate(0.5, normalized=True)
        shared = geometry.length
        return [
            {
                "geometry": midpoint,
                "confianza": "baja",
                "nota": (
                    f"el camino corre sobre el canal a lo largo de {shared:.0f} m; "
                    "el punto es el medio del tramo compartido, no un cruce puntual"
                ),
            }
        ]
    raise CruceDerivationError(
        f"unanticipated intersection geometry {kind!r} between road {road_id!r} "
        f"and canal {canal_id!r}"
    )


def detectar_cruces_camino_flujo_impl(
    red_vial_gdf,  # native segments, activo=true AND intersecting the raster bbox
    # (out-of-bbox segments are OUT OF SCOPE, not `excluidos`);
    # reprojected to the raster CRS internally
    canales_gdf,  # canal_consorcio LINES — crossings only, no profile, no depth
    flow_dir_path: Optional[str],  # natural_flow_dir_{area_id}; flow_dir_{area_id} ONLY
    # under verified no-burn
    flow_acc_path: Optional[str],  # natural_flow_acc_{area_id}; likewise
    *,
    acc_threshold_cells: float,  # recorded parameter, seeded 1000
    min_separation_m: float,  # recorded parameter, seeded 90
    parallel_min_angle_deg: float,  # recorded parameter, seeded 22.5 (lower band edge)
    parallel_high_angle_deg: float,  # recorded parameter, seeded 45 (upper band edge)
    bearing_window_m: float,  # recorded parameter, seeded 60
    build_empty_geojson,
):
    """Two derivations, NO drainage layer (it comes from the BURNED accumulation
    and is a polygonised cell mask — see design D3):

      tipo='canal'        : red_vial LINE  n  canal_consorcio LINE, in UTM.
                            UNCONDITIONAL — no raster dependency. Emitted even
                            when the DEM is absent, nodata, or the point falls
                            outside the raster footprint. direccion/lado/area
                            are NULL when unavailable; orden_ranking is ALWAYS
                            NULL. Never appears in `excluidos`. A non-Point
                            ST_Intersection is DECOMPOSED, never crashed on:
                            Points are extracted from a GeometryCollection, and
                            a LineString overlap (road running along the canal
                            bank) emits ONE row at its midpoint with
                            confianza='baja' and a descriptive `nota`.
      tipo='flujo_natural': rasterize each road trace to its ordered cell
                            traversal, read flow_acc along it, then, in order:
                              1. STRICT local maxima of the profile (a plateau
                                 yields ONE candidate: the plateau cell with the
                                 lexicographically smallest (row, col), which is
                                 digitization-direction invariant for ANY
                                 plateau length — the round-2 midpoint index was
                                 not, for even-length runs; profile endpoints
                                 are never candidates PER SEGMENT),
                              2. drop candidates below acc_threshold_cells,
                              3. CROSSING PREDICATE, three-band on the acute
                                 angle th between the D8 azimuth and the local
                                 road bearing (computed over +/-
                                 bearing_window_m):
                                   th <  parallel_min_angle_deg  -> excluded
                                                                    'flujo_paralelo'
                                   th <  parallel_high_angle_deg -> kept,
                                                                    confianza='baja'
                                   otherwise                     -> kept,
                                                                    confianza='alta'
                              4. greedy min_separation_m suppression; every
                                 suppressed above-threshold candidate is recorded
                                 as 'suprimido_por_separacion' so a genuine
                                 double crossing stays visible in the record.
                            The accepted cell IS the crossing point, so area is
                            read at the max-accumulation cell by construction —
                            never one cell off, no snapping.
                            A NETWORK-LEVEL JUNCTION PASS then runs over shared
                            endpoint nodes of abutting segments: each node is
                            evaluated once and emits AT MOST ONE row, attributed
                            to the lexicographically smallest incident segment
                            id, so 'maximo_en_extremo' is left meaning only a
                            true dead-end.

    Azimuths are derived FROM THE RASTER TRANSFORM, not from a hardcoded compass
    table: D8_OFFSETS is array-space (drow, dcol). The function ASSERTS a
    north-up transform (t.b == 0, t.d == 0, t.e < 0) and refuses a rotated one.

    All geometry work happens in the RASTER's UTM CRS; point geometry is
    reprojected to EPSG:4326 before return, while direccion_flujo_deg stays a
    UTM-grid azimuth. The CRS is never merely stamped (cf. the `crs=4326` trap
    at calculations_hydrology_support.py:120-122).

    NOTHING is dropped for being small — ranking is the filter. A flujo_natural
    candidate whose D8 pointer yields no direction is EXCLUDED and reported,
    never stored as a zero-area unranked point.

    Returns (gdf, excluidos, parametros).
      excluidos = [{tramo_ref, motivo, ...evidencia}, ...] with motivo in
        {'sin_direccion','flujo_paralelo','suprimido_por_separacion',
         'maximo_en_extremo'}; it is a task-result artifact persisted to
        geo_jobs.resultado, NOT a table.
      parametros records the five thresholds, the resolved raster variant
        (natural | relevado_equivale_natural) and the count of segments only
        partially covered by the raster.
    gdf columns: tipo, geometry, tramo_ref, canal_ref, direccion_flujo_deg,
                 rumbo_camino_deg, lado_cruce, area_aporte_ha, orden_ranking,
                 confianza, nota
                 (NO severidad, NO acumulacion_valor, NO pendiente_valor —
                  see D1 'excluded metrics')
    """
    import geopandas as gpd
    import rasterio

    parametros: dict[str, Any] = {
        "acc_threshold_cells": acc_threshold_cells,
        "min_separation_m": min_separation_m,
        "parallel_min_angle_deg": parallel_min_angle_deg,
        "parallel_high_angle_deg": parallel_high_angle_deg,
        "bearing_window_m": bearing_window_m,
        "variante": None,
        "segmentos_parcialmente_cubiertos": 0,
    }
    excluidos: list[dict[str, Any]] = []
    rows: list[dict[str, Any]] = []

    has_raster = bool(flow_dir_path) and bool(flow_acc_path)

    # ── The working CRS ──────────────────────────────────────────────────
    # Every metric operation happens in the raster's own UTM frame. Without a
    # raster the canal derivation still runs, so a metric CRS is still needed:
    # the roads' own UTM zone is the honest choice, and it is only used for the
    # line×line intersection, which is metric-frame-independent anyway.
    if has_raster:
        with rasterio.open(flow_dir_path) as fd_src:
            transform = fd_src.transform
            work_crs = fd_src.crs
            fd_data = fd_src.read(1)
            fd_nodata = fd_src.nodata
        with rasterio.open(flow_acc_path) as fa_src:
            fa_data = fa_src.read(1)
            fa_nodata = fa_src.nodata
        # Refuse a rotated raster HERE, at open time, so a rotated DEM stops the
        # run rather than reporting rotated directions confidently.
        azimut_desde_transform(4, transform)
        cell_area_m2 = abs(transform.a * transform.e)
    else:
        transform = None
        work_crs = red_vial_gdf.estimate_utm_crs() if len(red_vial_gdf) else 4326
        fd_data = fa_data = None
        fd_nodata = fa_nodata = None
        cell_area_m2 = 0.0

    roads = red_vial_gdf.to_crs(work_crs) if len(red_vial_gdf) else red_vial_gdf
    canals = canales_gdf.to_crs(work_crs) if len(canales_gdf) else canales_gdf

    # ── (a) Canal crossings — UNCONDITIONAL ──────────────────────────────
    # A canal that crosses a road crosses it whether or not a DEM exists. The
    # metrics below are opportunistic enrichment, never a precondition.
    for _, road in roads.iterrows():
        for _, canal in canals.iterrows():
            intersection = road.geometry.intersection(canal.geometry)
            for part in _decompose_intersection(intersection, str(road["id"]), str(canal["id"])):
                point = part["geometry"]
                direccion = area_ha = None
                lado = None
                if has_raster:
                    from rasterio.transform import rowcol

                    r, c = rowcol(transform, point.x, point.y)
                    r, c = int(r), int(c)
                    if 0 <= r < fd_data.shape[0] and 0 <= c < fd_data.shape[1]:
                        pointer = fd_data[r, c]
                        if fd_nodata is None or pointer != fd_nodata:
                            direccion = azimut_desde_transform(pointer, transform)
                        acc = float(fa_data[r, c])
                        if fa_nodata is None or acc != fa_nodata:
                            area_ha = acc * cell_area_m2 / 10_000
                rows.append(
                    {
                        "tipo": "canal",
                        "geometry": point,
                        "tramo_ref": str(road["id"]),
                        "canal_ref": str(canal["id"]),
                        "direccion_flujo_deg": direccion,
                        "rumbo_camino_deg": None,
                        "lado_cruce": lado,
                        "area_aporte_ha": area_ha,
                        # ALWAYS NULL. Ranking is defined over the natural-flow
                        # set; a populated area does not make this row a member
                        # of it (design D3, "ranking scope").
                        "orden_ranking": None,
                        "confianza": part["confianza"],
                        "nota": part["nota"],
                    }
                )

    # ── (b) Flow crossings ───────────────────────────────────────────────
    if has_raster and len(roads):
        height, width = fa_data.shape
        traversals: dict[str, list[tuple[int, int]]] = {}
        profiles: dict[str, list[float]] = {}
        distances: dict[str, list[float]] = {}
        candidates: list[dict[str, Any]] = []

        for _, road in roads.iterrows():
            tramo_ref = str(road["id"])
            cells = _traversal_cells(road.geometry, transform, (height, width))
            if len(cells) < 3:
                continue
            full = _traversal_cells(
                road.geometry, transform, (10**9, 10**9)
            )  # unclipped, to detect partial coverage
            if len(full) > len(cells):
                parametros["segmentos_parcialmente_cubiertos"] += 1
            traversals[tramo_ref] = cells
            profiles[tramo_ref] = [float(fa_data[r, c]) for r, c in cells]
            distances[tramo_ref] = _along_road_distances(cells, transform)

            for start, end in _maxima_runs(profiles[tramo_ref]):
                index = _plateau_pick(cells, start, end)
                candidates.append(
                    {
                        "tramo_ref": tramo_ref,
                        "indice": index,
                        "acumulacion": profiles[tramo_ref][index],
                        "distancia": distances[tramo_ref][index],
                        "cell": cells[index],
                    }
                )

            # An above-threshold maximum sitting AT a profile endpoint is
            # unverifiable from this segment alone. The junction pass below is
            # what keeps that honest where the endpoint is a shared node.
            for edge in (0, len(profiles[tramo_ref]) - 1):
                value = profiles[tramo_ref][edge]
                if value >= acc_threshold_cells and value == max(profiles[tramo_ref]):
                    excluidos.append(
                        {
                            "tramo_ref": tramo_ref,
                            "motivo": "maximo_en_extremo",
                            "acumulacion": value,
                        }
                    )

        # ── Junction pass ────────────────────────────────────────────────
        # The native segmentation splits a continuous road AT junctions, so a
        # real crossing landing on a shared node was dropped from BOTH abutting
        # segments. Evaluate each shared node once, over the STITCHED profile.
        nodes: dict[tuple[int, int], list[str]] = {}
        for tramo_ref, cells in traversals.items():
            for endpoint in (cells[0], cells[-1]):
                nodes.setdefault(endpoint, []).append(tramo_ref)
        for cell, incident in sorted(nodes.items()):
            if len(incident) < 2:
                continue
            value = float(fa_data[cell[0], cell[1]])
            if value < acc_threshold_cells:
                continue
            # The stitched profile: the incident segments' profiles concatenated
            # through the node. The strict local-maximum test is the same one the
            # per-segment pass applies — greater than its IMMEDIATE neighbours on
            # each side — except that here the neighbours come from two different
            # segments. A junction sitting on a monotone above-threshold ramp is
            # therefore rejected exactly as an in-segment ramp cell is, which is
            # what stops this pass from resurrecting the endpoint artefact the
            # per-segment rule exists to reject.
            flanks: list[float] = []
            for tramo_ref in sorted(incident):
                cells_i = traversals[tramo_ref]
                at = 0 if cells_i[0] == cell else len(cells_i) - 1
                neighbour_index = at + 1 if at == 0 else at - 1
                flanks.append(profiles[tramo_ref][neighbour_index])
            if not flanks or not all(value > f for f in flanks):
                continue
            owner = min(incident)
            candidates.append(
                {
                    "tramo_ref": owner,
                    # At most ONE row per node, never one per incident segment,
                    # attributed by a data-only rule so it reproduces across runs.
                    "indice": 0 if traversals[owner][0] == cell else len(traversals[owner]) - 1,
                    "acumulacion": value,
                    "distancia": (
                        0.0
                        if traversals[owner][0] == cell
                        else distances[owner][len(traversals[owner]) - 1]
                    ),
                    "cell": cell,
                    "junction_incidentes": sorted(incident),
                }
            )
            # It is no longer an honest dead-end exclusion.
            excluidos[:] = [
                e
                for e in excluidos
                if not (e["motivo"] == "maximo_en_extremo" and e["tramo_ref"] in incident)
            ]

        # ── Threshold, then the three-band predicate ─────────────────────
        surviving: list[dict[str, Any]] = []
        for candidate in candidates:
            if candidate["acumulacion"] < acc_threshold_cells:
                # A shallow rill is not a channel. Dropped silently — reporting
                # every sub-threshold cell individually would drown the record.
                continue
            row, col = candidate["cell"]
            pointer = fd_data[row, col]
            direccion = (
                None
                if (fd_nodata is not None and pointer == fd_nodata)
                else azimut_desde_transform(pointer, transform)
            )
            if direccion is None:
                excluidos.append(
                    {
                        "tramo_ref": candidate["tramo_ref"],
                        "motivo": "sin_direccion",
                        "acumulacion": candidate["acumulacion"],
                    }
                )
                continue

            if "junction_incidentes" in candidate:
                # The bearing stored is the incident one producing the largest
                # theta — the most transverse incidence.
                best = max(
                    (
                        _local_bearing(
                            traversals[t],
                            0 if traversals[t][0] == candidate["cell"] else len(traversals[t]) - 1,
                            transform,
                            bearing_window_m,
                        )
                        for t in candidate["junction_incidentes"]
                    ),
                    key=lambda b: _acute_angle(direccion, b),
                )
                bearing = best
            else:
                bearing = _local_bearing(
                    traversals[candidate["tramo_ref"]],
                    candidate["indice"],
                    transform,
                    bearing_window_m,
                )

            theta = _acute_angle(direccion, bearing)
            confianza = clasificar_banda_cruce(
                theta, parallel_min_angle_deg, parallel_high_angle_deg
            )
            if confianza is None:
                # Below half a D8 step. A drainage running alongside a road is
                # extremely common — roadside cunetas are exactly that — and its
                # maxima are not crossings at all. The exclusion carries θ, β and
                # φ so it is auditable rather than mysterious.
                excluidos.append(
                    {
                        "tramo_ref": candidate["tramo_ref"],
                        "motivo": "flujo_paralelo",
                        "theta_deg": theta,
                        "rumbo_camino_deg": bearing,
                        "direccion_flujo_deg": direccion,
                    }
                )
                continue

            nota = (
                (
                    f"incidencia oblicua ({theta:.1f} grados): dentro de la banda de "
                    "cuantizacion del puntero D8, la orientacion es de baja confianza"
                )
                if confianza == "baja"
                else None
            )

            candidate.update(
                {
                    "direccion": direccion,
                    "bearing": bearing,
                    "confianza": confianza,
                    "nota": nota,
                }
            )
            surviving.append(candidate)

        accepted, suppressed = _suppress_by_separation(surviving, min_separation_m)
        excluidos.extend(suppressed)

        for candidate in accepted:
            row, col = candidate["cell"]
            x, y = _cell_center(transform, row, col)
            from shapely.geometry import Point

            rows.append(
                {
                    "tipo": "flujo_natural",
                    "geometry": Point(x, y),
                    "tramo_ref": candidate["tramo_ref"],
                    "canal_ref": None,
                    "direccion_flujo_deg": candidate["direccion"],
                    "rumbo_camino_deg": candidate["bearing"],
                    "lado_cruce": _lado_cruce(candidate["direccion"], candidate["bearing"]),
                    # Read at the very cell whose accumulation selected it —
                    # never one cell off, never a rim cell.
                    "area_aporte_ha": candidate["acumulacion"] * cell_area_m2 / 10_000,
                    "orden_ranking": None,
                    "confianza": candidate["confianza"],
                    "nota": candidate["nota"],
                }
            )

    if not rows:
        return build_empty_geojson(list(CRUCE_COLUMNS)), excluidos, parametros

    gdf = gpd.GeoDataFrame(rows, geometry="geometry", crs=work_crs)

    # ── Ranking, over flujo_natural rows ONLY ────────────────────────────
    # ORDER BY area_aporte_ha DESC, tramo_ref ASC, X ASC, Y ASC — a total order,
    # every key data, so a re-run over unchanged inputs reproduces the same ranks
    # byte for byte. Ranking on area alone is NOT reproducible: two crossings
    # sharing an accumulation cell value tie, and a tie broken by frame iteration
    # order changes between runs.
    natural_mask = gdf["tipo"] == "flujo_natural"
    natural = gdf[natural_mask].copy()
    if len(natural):
        natural["_x"] = natural.geometry.x
        natural["_y"] = natural.geometry.y
        ordered = natural.sort_values(
            ["area_aporte_ha", "tramo_ref", "_x", "_y"],
            ascending=[False, True, True, True],
        )
        for rank, index in enumerate(ordered.index, start=1):
            gdf.loc[index, "orden_ranking"] = rank

    # ── CRS contract ─────────────────────────────────────────────────────
    # An EXPLICIT transform, not a stamp. A UTM point labelled 4326 lands in the
    # Gulf of Guinea; the azimuths above stay UTM-grid and are NOT reprojected.
    gdf = gdf.to_crs(4326)
    return gdf[list(CRUCE_COLUMNS)], excluidos, parametros


def empty_runoff_geojson_impl(
    punto: tuple[float, float], lluvia_mm: float, error: str
) -> dict[str, Any]:
    return {
        "type": "FeatureCollection",
        "features": [],
        "properties": {
            "punto_inicio": list(punto),
            "lluvia_mm": lluvia_mm,
            "error": error,
        },
    }


def simular_escorrentia_impl(
    flow_dir_path: str,
    flow_acc_path: str,
    punto_inicio: tuple[float, float],
    lluvia_mm: float,
    *,
    max_steps: int,
    rasterio_module,
    empty_geojson,
) -> dict[str, Any]:
    from rasterio.transform import rowcol

    # The module-level constant, not a re-typed copy: two definitions of the same
    # pointer table is one definition too many. Behaviour is unchanged — the
    # values are identical to the dict that used to live here.
    d8_offsets = D8_OFFSETS
    with rasterio_module.open(flow_dir_path) as fd_src:
        fd_data, fd_transform, fd_nodata = (
            fd_src.read(1),
            fd_src.transform,
            fd_src.nodata,
        )
    with rasterio_module.open(flow_acc_path) as fa_src:
        fa_data = fa_src.read(1)
    try:
        row, col = rowcol(fd_transform, *punto_inicio)
    except Exception:
        return empty_geojson(punto_inicio, lluvia_mm, "Punto fuera del raster")
    coords, accumulations, visited = [punto_inicio], [], set()
    for _ in range(max_steps):
        if (row, col) in visited or not (
            0 <= row < fd_data.shape[0] and 0 <= col < fd_data.shape[1]
        ):
            break
        visited.add((row, col))
        direction = int(fd_data[row, col])
        if fd_nodata is not None and direction == int(fd_nodata):
            break
        accumulations.append(
            float(fa_data[row, col]) * lluvia_mm
            if 0 <= row < fa_data.shape[0] and 0 <= col < fa_data.shape[1]
            else 0.0
        )
        offset = d8_offsets.get(direction)
        if offset is None:
            break
        row += offset[0]
        col += offset[1]
        coords.append(
            (
                fd_transform.c + col * fd_transform.a + row * fd_transform.b,
                fd_transform.f + col * fd_transform.d + row * fd_transform.e,
            )
        )
    if len(coords) < 2:
        return empty_geojson(punto_inicio, lluvia_mm, "No se pudo trazar flujo")
    line = LineString(coords)
    return {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "geometry": mapping(line),
                "properties": {
                    "punto_inicio": list(punto_inicio),
                    "lluvia_mm": lluvia_mm,
                    "longitud_m": len(coords),
                    "acumulacion_max": max(accumulations) if accumulations else 0.0,
                    "acumulacion_media": sum(accumulations) / len(accumulations)
                    if accumulations
                    else 0.0,
                    "pasos": len(coords),
                },
            }
        ],
    }


def generar_zonificacion_impl(
    dem_path: str,
    flow_acc_path: str,
    flow_dir_path: str,
    *,
    threshold: int,
    get_wbt,
    build_empty_geojson,
    rasterio_module: Any = None,
    shapes_fn: Any = None,
):
    """Delineate sub-basins by seeding WBT ``watershed`` with a D8 pointer.

    ``dem_path`` is kept for provenance/logging only — WBT ``watershed`` needs the
    **D8 flow-direction pointer** as its first argument (``d8_pntr``), NOT the DEM.
    Passing the DEM there was the historical A7 "D8 blocker": ``watershed``
    silently misread the elevation raster as a pointer. ``flow_dir_path`` is the
    real WBT-native D8 pointer the pipeline already produces
    (``wbt.d8_pointer`` → ``flow_dir*.tif``).

    ``rasterio_module``/``shapes_fn`` are injectable so tests can drive the whole
    routine with mocked raster I/O (mirroring ``generate_chirps_normals``);
    production passes nothing and gets the real ``rasterio`` + ``rasterio.features.shapes``.
    """
    import geopandas as gpd
    from shapely.geometry import shape

    if rasterio_module is None:
        import rasterio as rasterio_module  # noqa: PLC0415
    if shapes_fn is None:
        from rasterio.features import shapes as shapes_fn  # noqa: PLC0415

    rasterio = rasterio_module
    rasterio_shapes = shapes_fn

    with tempfile.TemporaryDirectory() as tmpdir:
        pour_points, basins = (
            str(Path(tmpdir) / "pour_points.tif"),
            str(Path(tmpdir) / "basins.tif"),
        )
        with rasterio.open(flow_acc_path) as src:
            fa, meta, nodata = src.read(1), src.meta.copy(), src.nodata
        pp = np.where(fa >= threshold, 1, 0).astype(np.int16)
        if nodata is not None:
            pp[fa == nodata] = 0
        meta.update({"dtype": "int16", "count": 1, "nodata": 0})
        with rasterio.open(pour_points, "w", **meta) as dst:
            dst.write(pp, 1)
        # D8 fix: the pointer (flow_dir_path), not the DEM, is watershed's arg 1.
        get_wbt().watershed(flow_dir_path, pour_points, basins)
        with rasterio.open(basins) as src:
            basin_data, basin_transform, basin_crs = src.read(1), src.transform, src.crs
        geometries, basin_ids = [], []
        for geom, value in rasterio_shapes(
            basin_data, mask=basin_data > 0, transform=basin_transform
        ):
            if value > 0:
                geometries.append(shape(geom))
                basin_ids.append(int(value))
    if not geometries:
        return build_empty_geojson(["basin_id", "geometry"])
    gdf = gpd.GeoDataFrame(
        {"basin_id": basin_ids, "geometry": geometries},
        geometry="geometry",
        crs=str(basin_crs) if basin_crs else "EPSG:4326",
    )
    try:
        gdf["superficie_ha"] = gdf.to_crs("EPSG:32720").geometry.area / 10_000
    except Exception:
        gdf["superficie_ha"] = 0.0
    return gdf
