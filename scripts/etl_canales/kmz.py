"""KMZ unzipper + KML Placemark extractor (stdlib-only).

Why stdlib
----------
A KMZ is a zip archive with a canonical ``doc.kml`` entry.  Python's
``zipfile`` + ``xml.etree.ElementTree`` are enough — we deliberately avoid
heavyweight KML parsers (``fastkml``, ``pykml``, ``fiona``) because:

1. The KML dialect produced by Google Earth Pro for these two files is
   narrow and known-ahead — we only care about ``<Placemark>`` with either
   ``<LineString>`` or ``<Polygon>`` children.
2. Zero new dependencies keep the ETL reproducible across machines that
   already run ``etl_pilar_verde`` (same venv, same deps).
3. Stdlib parsing is ~30 LOC and trivial to unit-test against fixtures.

Output shape
------------
``extract_placemarks(kmz_path) -> list[RawPlacemark]`` returns ONE entry per
``<Placemark>`` in document order.  The caller downstream decides what to do
with Polygon/Point placemarks (the orchestrator logs + skips them; the tests
assert they're still present so future tooling can render them if needed).
"""

from __future__ import annotations

import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Literal
from xml.etree import ElementTree as ET

KML_NS: str = "{http://www.opengis.net/kml/2.2}"


@dataclass(frozen=True)
class RawPlacemark:
    """One Placemark from the KMZ — un-interpreted, ready for downstream.

    ``coords`` are ``(lon, lat)`` tuples (GeoJSON convention).  Altitudes are
    discarded — the map is 2-D and altitude was 0 in every source record we
    inspected.
    """

    name: str
    style_url: str | None
    folder_path: str
    geometry_type: Literal["LineString", "Polygon", "Point"]
    coords: list[tuple[float, float]]


def _parse_coords(text: str) -> list[tuple[float, float]]:
    """Parse a KML ``<coordinates>`` blob into ``(lon, lat)`` tuples.

    KML format: whitespace-separated ``lon,lat[,alt]`` triples.  We tolerate
    commas inside decimal numbers (they never appear in KMLs but the parser
    stays forgiving) and drop any altitude if present.
    """
    out: list[tuple[float, float]] = []
    for token in text.split():
        parts = token.split(",")
        if len(parts) < 2:
            continue
        lon = float(parts[0])
        lat = float(parts[1])
        out.append((lon, lat))
    return out


def _style_url_clean(raw: str | None) -> str | None:
    """Strip the leading ``#`` from a styleUrl reference, or return ``None``."""
    if raw is None:
        return None
    return raw.lstrip("#") or None


def _walk(
    element: ET.Element,
    current_path: list[str],
    out: list[RawPlacemark],
) -> None:
    """Recursively descend Folders + emit Placemarks with their folder path."""
    for child in element:
        tag = child.tag
        if tag == f"{KML_NS}Folder":
            name_el = child.find(f"{KML_NS}name")
            folder_name = name_el.text.strip() if name_el is not None and name_el.text else ""
            new_path = current_path + [folder_name] if folder_name else current_path
            _walk(child, new_path, out)
        elif tag == f"{KML_NS}Placemark":
            pm = _parse_placemark(child, current_path)
            if pm is not None:
                out.append(pm)
        elif tag == f"{KML_NS}Document":
            # Nested Document element — walk its children too.
            _walk(child, current_path, out)


def _parse_placemark(
    placemark: ET.Element,
    folder_stack: list[str],
) -> RawPlacemark | None:
    """Extract a single Placemark.  Returns ``None`` when the geometry is missing."""
    name_el = placemark.find(f"{KML_NS}name")
    style_el = placemark.find(f"{KML_NS}styleUrl")
    name = name_el.text.strip() if name_el is not None and name_el.text else ""
    style_url = _style_url_clean(style_el.text if style_el is not None else None)
    folder_path = "/".join(folder_stack)

    # LineString FIRST — most common case.
    line = placemark.find(f"{KML_NS}LineString/{KML_NS}coordinates")
    if line is not None and line.text:
        return RawPlacemark(
            name=name,
            style_url=style_url,
            folder_path=folder_path,
            geometry_type="LineString",
            coords=_parse_coords(line.text),
        )

    # Polygon — use the outer boundary's LinearRing coordinates.
    polygon_ring = placemark.find(
        f"{KML_NS}Polygon/{KML_NS}outerBoundaryIs/{KML_NS}LinearRing/{KML_NS}coordinates"
    )
    if polygon_ring is not None and polygon_ring.text:
        return RawPlacemark(
            name=name,
            style_url=style_url,
            folder_path=folder_path,
            geometry_type="Polygon",
            coords=_parse_coords(polygon_ring.text),
        )

    # Point — rarely used in our KMZs but harmless to support.
    point = placemark.find(f"{KML_NS}Point/{KML_NS}coordinates")
    if point is not None and point.text:
        return RawPlacemark(
            name=name,
            style_url=style_url,
            folder_path=folder_path,
            geometry_type="Point",
            coords=_parse_coords(point.text),
        )

    return None


def extract_placemarks(kmz_path: Path) -> list[RawPlacemark]:
    """Open a KMZ, read its ``doc.kml``, and return every ``<Placemark>``.

    Raises:
        FileNotFoundError: when the KMZ file or its ``doc.kml`` entry is
            missing.
    """
    path = Path(kmz_path)
    if not path.exists():
        raise FileNotFoundError(f"KMZ file not found: {path}")

    with zipfile.ZipFile(path, "r") as zf:
        try:
            kml_bytes = zf.read("doc.kml")
        except KeyError as exc:
            raise FileNotFoundError(
                f"KMZ at {path} does not contain a doc.kml entry"
            ) from exc

    root = ET.fromstring(kml_bytes)
    out: list[RawPlacemark] = []
    _walk(root, current_path=[], out=out)
    return out
