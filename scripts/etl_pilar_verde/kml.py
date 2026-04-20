"""KML -> GeoJSON conversion for the ZONA CC AMPLIADA polygon.

The production KML has a single Placemark with a single Polygon / outerBoundaryIs
(no holes) — verified in the exploration.  We use pure stdlib (``xml.etree``)
instead of a full KML parser because:

1. Fiona is not available in this project's venv (verified).
2. The KML shape is known and extremely narrow.
3. Zero new dependency.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET

KML_NS = "{http://www.opengis.net/kml/2.2}"


def _parse_coords(text: str) -> list[list[float]]:
    """Parse a KML <coordinates> block into GeoJSON-style ``[[lon, lat], ...]``.

    KML coordinate tuples are ``lon,lat[,alt]`` and are whitespace-separated.
    GeoJSON drops the altitude and keeps ``[lon, lat]``.  The ring must close
    (first == last) — we enforce it here if the source forgot to.
    """
    ring: list[list[float]] = []
    for raw_tuple in text.split():
        parts = raw_tuple.split(",")
        if len(parts) < 2:
            continue
        lon = float(parts[0])
        lat = float(parts[1])
        ring.append([lon, lat])
    if ring and ring[0] != ring[-1]:
        ring.append([ring[0][0], ring[0][1]])
    return ring


def kml_to_geojson(kml_path: Path) -> dict[str, Any]:
    """Parse a single-polygon KML into a GeoJSON FeatureCollection.

    Raises ``FileNotFoundError`` if the KML file is missing.
    Raises ``ValueError`` if no polygon is found inside the KML.
    """
    path = Path(kml_path)
    if not path.exists():
        raise FileNotFoundError(f"KML file not found: {path}")

    tree = ET.parse(path)
    root = tree.getroot()

    features: list[dict[str, Any]] = []
    for placemark in root.iter(f"{KML_NS}Placemark"):
        for polygon in placemark.iter(f"{KML_NS}Polygon"):
            outer = polygon.find(f"{KML_NS}outerBoundaryIs/{KML_NS}LinearRing/{KML_NS}coordinates")
            if outer is None or outer.text is None:
                continue
            outer_ring = _parse_coords(outer.text)
            inner_rings: list[list[list[float]]] = []
            for inner in polygon.iterfind(
                f"{KML_NS}innerBoundaryIs/{KML_NS}LinearRing/{KML_NS}coordinates"
            ):
                if inner.text is None:
                    continue
                inner_rings.append(_parse_coords(inner.text))

            name_el = placemark.find(f"{KML_NS}name")
            name = name_el.text if name_el is not None else None

            features.append(
                {
                    "type": "Feature",
                    "properties": {"name": name} if name else {},
                    "geometry": {
                        "type": "Polygon",
                        "coordinates": [outer_ring, *inner_rings],
                    },
                }
            )

    if not features:
        raise ValueError(f"No polygon features found in {path}")

    return {"type": "FeatureCollection", "features": features}
