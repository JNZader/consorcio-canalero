"""Geodesic line-length helper — single source of truth for canal longitud.

Why geodesic on WGS84
---------------------
The KMZ uses EPSG:4326 (lon/lat on WGS84).  Euclidean distance on raw
degrees is wrong by the cosine of the latitude (significant at Córdoba's
~-32.5° latitude); simple haversine on a sphere is wrong by tens of metres
across the zona's ~30 km spans because the Earth isn't a sphere.  The WGS84
ellipsoid via ``pyproj.Geod(ellps='WGS84').inv(...)`` returns the true
ellipsoidal geodesic length in metres and is the industry standard for this
kind of precision.

The ETL computes longitud once and writes it to the GeoJSON; the frontend
never needs ``@turf/length`` — there is ONE source of truth.
"""

from __future__ import annotations

from pyproj import Geod

# Re-used singleton.  ``pyproj.Geod`` is cheap to instantiate but creating it
# once per process keeps the wrapper branchless and obvious.
_GEOD: Geod = Geod(ellps="WGS84")


def compute_longitud_m(coords: list[tuple[float, float]]) -> float:
    """Sum per-segment ellipsoidal geodesic distances on WGS84.

    Args:
        coords: A list of ``(lon, lat)`` tuples in EPSG:4326.  A list with a
            single vertex returns 0.0; an empty or ``None`` list raises
            ``ValueError`` so the caller spots malformed input loudly.

    Returns:
        The summed geodesic length, in metres, as a ``float``.
    """
    if coords is None or len(coords) == 0:
        raise ValueError("compute_longitud_m requires at least one coordinate")
    if len(coords) == 1:
        return 0.0

    total = 0.0
    for (lng1, lat1), (lng2, lat2) in zip(coords[:-1], coords[1:]):
        _, _, segment = _GEOD.inv(lng1, lat1, lng2, lat2)
        total += segment
    return total
