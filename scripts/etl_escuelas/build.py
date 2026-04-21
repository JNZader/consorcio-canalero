"""Orchestrator — read an Escuelas KMZ and emit a GeoJSON FeatureCollection.

Design decisions (locked by engram ``sdd/escuelas-rurales/design`` #2059):

- The KMZ placemark extractor is REUSED AS-IS from ``scripts.etl_canales.kmz``
  — it already supports Point geometry (see ``etl_canales/kmz.py`` lines
  133-142) for ``<name>`` + ``<styleUrl>`` + geometry coordinates.  We only
  filter ``geometry_type == "Point"`` at the caller layer.
- ``RawPlacemark`` is a frozen dataclass that deliberately omits
  ``<description>`` (the canales ETL parses metadata from ``<name>`` and
  never touches description).  Rather than fork that module, we do a
  lightweight secondary pass over the KMZ to build a ``name → description``
  map.  One extra unzip for 7 placemarks is negligible and keeps the
  canales reuse boundary pristine.
- The CDATA parser whitelists ONLY 3 labels (``localidad``, ``ambito``,
  ``nivel``).  NO PII leaves this module — confirmed by grep gates in the
  test suite and in the verify phase.
- Feature ids are deterministic: ``slug(nombre)`` with ``-2``, ``-3``, …
  collision suffixes in KML document order so re-runs produce byte-identical
  output.
- The ``properties`` writer enforces EXACTLY 4 keys via a whitelisted
  assembly (``_build_properties``) — any extra key the parser might return
  in the future is dropped at the emission boundary.
- ``metadata.generated_at`` honours the ``ETL_GENERATED_AT`` env var (same
  convention as ``etl_canales.writers``) for byte-idempotent test assertions.
"""

from __future__ import annotations

import json
import os
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Final
from xml.etree import ElementTree as ET

from scripts.etl_canales.kmz import extract_placemarks
from scripts.etl_escuelas.parse import parse_description, slug, slug_with_counter

# Hard schema — the 4 keys the public asset is allowed to expose.  Dict
# insertion order is the JSON emission order, so keeping this tuple authoritative
# also keeps the on-disk byte layout stable across Python versions.
ALLOWED_PROPERTY_KEYS: Final[tuple[str, ...]] = ("nombre", "localidad", "ambito", "nivel")

_KML_NS: Final[str] = "{http://www.opengis.net/kml/2.2}"


def _now_iso() -> str:
    """Return the current UTC timestamp in ISO-8601 with a trailing ``Z``.

    Honours the ``ETL_GENERATED_AT`` env var so tests can pin the value for
    golden-file comparisons (same convention as ``etl_canales.writers``).
    """
    override = os.environ.get("ETL_GENERATED_AT")
    if override:
        return override
    now = datetime.now(tz=timezone.utc).replace(microsecond=0)
    return now.isoformat().replace("+00:00", "Z")


def _read_descriptions(kmz_path: Path) -> dict[str, str]:
    """Return a ``name → description-cdata`` map for one KMZ.

    Uses stdlib ``zipfile`` + ``xml.etree.ElementTree`` — same dependency
    surface as ``etl_canales.kmz``.  We index by ``<name>`` because the
    Escuelas KMZ currently has 7 unique names; the SLUG-level collision
    counter handles the (synthetic) duplicate-name case by document order
    without needing the cache to be position-aware.
    """
    with zipfile.ZipFile(kmz_path, "r") as zf:
        kml_bytes = zf.read("doc.kml")
    root = ET.fromstring(kml_bytes)

    out: dict[str, str] = {}
    # ``iter`` descends into <Document>/<Folder> without manual recursion.
    for placemark in root.iter(f"{_KML_NS}Placemark"):
        name_el = placemark.find(f"{_KML_NS}name")
        desc_el = placemark.find(f"{_KML_NS}description")
        name = (name_el.text or "").strip() if name_el is not None else ""
        desc = desc_el.text if desc_el is not None else None
        if name:
            # First-win: if two placemarks share a name, the first's
            # description wins.  In the real KMZ all 7 names are unique so
            # this is a defensive tie-break only.
            out.setdefault(name, desc or "")
    return out


def _build_properties(nombre: str, parsed: dict[str, str]) -> dict[str, str]:
    """Assemble the 4-key properties dict in the locked emission order.

    Any key that is NOT in ``ALLOWED_PROPERTY_KEYS`` is dropped defensively —
    even if the parser returns extra keys in the future they can never reach
    the public asset.  Missing required labels default to ``""`` so the
    downstream consumer (React card) never has to branch on ``None``.
    """
    return {
        "nombre": nombre,
        "localidad": parsed.get("localidad", ""),
        "ambito": parsed.get("ambito", ""),
        "nivel": parsed.get("nivel", ""),
    }


def build_geojson(kmz_path: str | Path) -> dict[str, Any]:
    """Read an Escuelas KMZ and return a GeoJSON FeatureCollection dict.

    Args:
        kmz_path: Absolute or relative path to the Escuelas Rurales KMZ.

    Returns:
        A FeatureCollection dict with one Point feature per Placemark in KML
        document order.  Each feature has:

            * ``type``: ``"Feature"``
            * ``id``: the deterministic slug (with ``-N`` suffix on collisions)
            * ``geometry``: ``{type: "Point", coordinates: [lon, lat]}``
            * ``properties``: ``{nombre, localidad, ambito, nivel}`` —
              EXACTLY these 4 keys, no PII.

    Notes:
        * Non-Point placemarks are silently filtered — the Escuelas KMZ v1
          contract is Points-only.
        * The ``metadata.generated_at`` timestamp respects ``ETL_GENERATED_AT``
          for deterministic diffs in tests and CI.
    """
    path = Path(kmz_path)
    placemarks = extract_placemarks(path)
    descriptions = _read_descriptions(path)

    seen: dict[str, int] = {}
    features: list[dict[str, Any]] = []

    for placemark in placemarks:
        if placemark.geometry_type != "Point":
            continue  # Escuelas v1 is Points-only
        if not placemark.coords:
            continue  # defensive — missing coords = unmappable feature

        lon, lat = placemark.coords[0]
        nombre = placemark.name
        parsed = parse_description(descriptions.get(nombre, ""))

        base_slug = slug(nombre)
        if not base_slug:
            # Last-ditch fallback so we NEVER emit a feature with an empty id.
            base_slug = f"escuela-{len(features)}"
        feature_id = slug_with_counter(base_slug, seen)

        features.append(
            {
                "type": "Feature",
                "id": feature_id,
                "geometry": {"type": "Point", "coordinates": [lon, lat]},
                "properties": _build_properties(nombre, parsed),
            }
        )

    return {
        "type": "FeatureCollection",
        "metadata": {"generated_at": _now_iso()},
        "features": features,
    }


def serialize_feature_collection(fc: dict[str, Any], out_path: Path) -> None:
    """Write a FeatureCollection to disk with deterministic JSON formatting.

    Compact separators + ``ensure_ascii=False`` + trailing newline — matches
    the canales ETL's serialization so the two static assets live in the
    same style on disk.
    """
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps(fc, ensure_ascii=False, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )
