"""ETL orchestrator — fetch → clip → join → aggregate → write.

Contract:
- All-or-nothing writes: if any required layer (bpa_2025, agro_aceptada,
  agro_presentada) returns 0 features inside zona, the ETL exits 1 with NO
  files created or updated.
- Exit codes follow ``constants.EXIT_*``.
- Structured logging — one per fetch with ``{layer, features_count, elapsed_ms}``.
- Idempotent: same inputs → byte-identical outputs (given a fixed
  ``generated_at`` override via env var for reproducibility in tests).
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
from pathlib import Path
from typing import Any

import pyproj
import requests
from shapely.geometry import shape
from shapely.ops import transform

from scripts.etl_pilar_verde.aggregates import (
    compute_bpa_kpis,
    compute_grilla_aggregates,
    compute_ley_forestal,
    compute_zonas_agroforestales_intersect,
)
from scripts.etl_pilar_verde.clip import clip_to_zona
from scripts.etl_pilar_verde.constants import (
    AGGREGATES_SCHEMA_VERSION,
    AGRO_ACEPTADA,
    AGRO_GRILLA,
    AGRO_PRESENTADA,
    AGRO_ZONAS,
    AGRO_ZONAS_SIMPLIFY_TOLERANCE,
    BPA_ENRICHED_SCHEMA_VERSION,
    BPA_LAYERS,
    CATASTRO_SOURCE,
    CRS_IDECOR,
    CRS_LATLON,
    EXIT_IDECOR_UNREACHABLE,
    EXIT_KML_PARSE_FAILURE,
    EXIT_OK,
    EXIT_REQUIRED_LAYER_EMPTY,
    EXIT_ZONA_MISSING,
    FORESTACION,
    KML_SOURCE,
    OUTPUT_FILES,
    REQUIRED_LAYERS,
    SCHEMA_VERSION,
)
from scripts.etl_pilar_verde.join import build_bpa_history, join_bpa
from scripts.etl_pilar_verde.kml import kml_to_geojson
from scripts.etl_pilar_verde.wfs import fetch_layer
from scripts.etl_pilar_verde.writers import (
    build_bpa_historico_features,
    geojson_bbox,
    simplify_features,
    thin_properties,
    write_geojson,
    write_json,
)

logger = logging.getLogger("etl_pilar_verde")


def _configure_logging(level: int = logging.INFO) -> None:
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)5s] %(name)s: %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
    )


def _load_zona(kml_path: Path) -> dict[str, Any]:
    if not kml_path.exists():
        raise FileNotFoundError(f"zona KML missing: {kml_path}")
    return kml_to_geojson(kml_path)


def _project_bbox_to_22174(
    zona_latlon: dict[str, Any],
) -> tuple[float, float, float, float]:
    """Project the zona bbox from EPSG:4326 to EPSG:22174 for the CQL filter."""
    transformer = pyproj.Transformer.from_crs(CRS_LATLON, CRS_IDECOR, always_xy=True)
    geom_latlon = shape(zona_latlon["features"][0]["geometry"])
    geom_22174 = transform(transformer.transform, geom_latlon)
    return geom_22174.bounds


def _fetch_and_clip(
    type_names: str,
    bbox_22174: tuple[float, float, float, float],
    zona: dict[str, Any],
) -> list[dict[str, Any]]:
    payload = fetch_layer(type_names, bbox_22174)
    features = payload.get("features") or []
    return clip_to_zona(features, zona_polygon_feature=zona)


def _zona_area_ha(zona_latlon: dict[str, Any]) -> float:
    transformer = pyproj.Transformer.from_crs(CRS_LATLON, CRS_IDECOR, always_xy=True)
    geom_latlon = shape(zona_latlon["features"][0]["geometry"])
    geom_m = transform(transformer.transform, geom_latlon)
    return round(geom_m.area / 10000.0, 1)


def run_etl(
    *,
    kml_path: Path = KML_SOURCE,
    catastro_path: Path = CATASTRO_SOURCE,
    output_files: dict[str, Path] | None = None,
    fetch_historical_bpa: bool = True,
    fetch_zonas_agroforestales: bool = True,
    fetch_forestacion: bool = True,
    # Phase 0 addendum (anomaly #2): grilla is Tier-2 contextual, fetch by
    # default so grilla_aggregates gets populated.  Disable in fast/partial
    # runs (e.g. some test fixtures) via ``fetch_grilla=False``.
    fetch_grilla: bool = True,
    generated_at: str | None = None,
) -> int:
    """Run the full ETL.  Returns an exit code (0 success, >0 failure).

    Split out from ``main()`` so tests can pass stubbed layer fetchers via
    monkeypatching ``fetch_layer`` and still exercise the full orchestrator.
    """
    outputs = output_files or OUTPUT_FILES
    start = time.monotonic()

    # 1. Zona — fail fast if missing or unparseable.
    try:
        zona = _load_zona(kml_path)
    except FileNotFoundError as exc:
        logger.error("zona missing: %s", exc)
        return EXIT_ZONA_MISSING
    except Exception as exc:  # noqa: BLE001 — narrow is hard for xml.etree here
        logger.error("zona KML parse failure: %s", exc)
        return EXIT_KML_PARSE_FAILURE

    bbox_22174 = _project_bbox_to_22174(zona)
    zona_ha = _zona_area_ha(zona)
    logger.info("zona loaded area_ha=%.1f bbox_22174=%s", zona_ha, bbox_22174)

    # 2. Fetch layers — everything into a staging dict first, so we can enforce
    #    "all-or-nothing" writes if any REQUIRED layer is empty.
    staging: dict[str, list[dict[str, Any]]] = {}

    try:
        staging["bpa_2025"] = _fetch_and_clip(BPA_LAYERS[2025], bbox_22174, zona)
        staging["agro_aceptada"] = _fetch_and_clip(AGRO_ACEPTADA, bbox_22174, zona)
        staging["agro_presentada"] = _fetch_and_clip(AGRO_PRESENTADA, bbox_22174, zona)
        if fetch_zonas_agroforestales:
            staging["agro_zonas"] = _fetch_and_clip(AGRO_ZONAS, bbox_22174, zona)
        else:
            staging["agro_zonas"] = []
        if fetch_forestacion:
            staging["porcentaje_forestacion"] = _fetch_and_clip(
                FORESTACION, bbox_22174, zona
            )
        else:
            staging["porcentaje_forestacion"] = []

        if fetch_grilla:
            # Tier-2 contextual — we ship aggregates (mean altura/pendiente, dist),
            # not the 6k+ cell geometry.  Keep the same clip gate semantics.
            staging["agro_grilla"] = _fetch_and_clip(AGRO_GRILLA, bbox_22174, zona)
        else:
            staging["agro_grilla"] = []

        historical: dict[int, list[dict[str, Any]]] = {}
        if fetch_historical_bpa:
            for year, type_names in BPA_LAYERS.items():
                if year == 2025:
                    continue
                try:
                    historical[year] = _fetch_and_clip(type_names, bbox_22174, zona)
                except requests.HTTPError as exc:
                    logger.warning(
                        "historical BPA layer unavailable year=%d err=%s — skipping",
                        year,
                        exc,
                    )
                    historical[year] = []
    except requests.RequestException as exc:
        logger.error("IDECor unreachable after retries: %s", exc)
        return EXIT_IDECOR_UNREACHABLE

    # 3. Data-quality gate — REQUIRED layers must have at least one feature.
    layer_key_by_typename = {
        BPA_LAYERS[2025]: "bpa_2025",
        AGRO_ACEPTADA: "agro_aceptada",
        AGRO_PRESENTADA: "agro_presentada",
    }
    for type_names in REQUIRED_LAYERS:
        key = layer_key_by_typename[type_names]
        if not staging[key]:
            logger.error(
                "REQUIRED layer %s returned 0 features — data quality alarm",
                type_names,
            )
            return EXIT_REQUIRED_LAYER_EMPTY

    # 4. Load catastro (static, local file — not a WFS fetch).
    if not catastro_path.exists():
        logger.error("catastro source missing: %s", catastro_path)
        return EXIT_ZONA_MISSING  # reuse — resource missing is resource missing
    catastro_payload = json.loads(catastro_path.read_text())
    catastro_features = catastro_payload.get("features") or []

    # 5. Join + aggregates.
    enriched_parcels = join_bpa(
        catastro_features,
        staging["bpa_2025"],
        staging["agro_aceptada"],
        staging["agro_presentada"],
        history_by_year=historical,
    )
    history = build_bpa_history(historical)

    ley_forestal_block = compute_ley_forestal(enriched_parcels)
    bpa_block = compute_bpa_kpis(enriched_parcels, zona_superficie_ha=zona_ha)
    # Use whatever the fetch phase staged (may be [] if fetch_grilla=False).
    grilla_block = compute_grilla_aggregates(staging.get("agro_grilla") or None)
    zonas_block = compute_zonas_agroforestales_intersect(
        staging["agro_zonas"], zona
    )

    aggregates_payload = {
        "zona": {"nombre": "CC 10 de Mayo Ampliada", "superficie_ha": zona_ha},
        "ley_forestal": ley_forestal_block,
        "bpa": bpa_block,
        "grilla_aggregates": grilla_block,
        "zonas_agroforestales": zonas_block,
    }

    # 6. Simplify / thin per spec.
    agro_zonas_simplified = simplify_features(
        staging["agro_zonas"], tolerance=AGRO_ZONAS_SIMPLIFY_TOLERANCE
    )
    forestacion_thinned = thin_properties(staging["porcentaje_forestacion"])

    # 7. Write outputs — ONLY after all gates passed.
    # Zona ampliada also needs writing (target 9 files).
    write_geojson(
        outputs["zona_ampliada"],
        zona.get("features") or [],
        source="KML: gee/zona_cc_ampliada/CC 10 de mayo ampliado2.kml",
        generated_at=generated_at,
    )
    write_geojson(
        outputs["bpa_2025"],
        staging["bpa_2025"],
        source=f"IDECor WFS {BPA_LAYERS[2025]}",
        generated_at=generated_at,
    )
    write_geojson(
        outputs["agro_aceptada"],
        staging["agro_aceptada"],
        source=f"IDECor WFS {AGRO_ACEPTADA}",
        generated_at=generated_at,
    )
    write_geojson(
        outputs["agro_presentada"],
        staging["agro_presentada"],
        source=f"IDECor WFS {AGRO_PRESENTADA}",
        generated_at=generated_at,
    )
    write_geojson(
        outputs["agro_zonas"],
        agro_zonas_simplified,
        source=f"IDECor WFS {AGRO_ZONAS} (simplified tol={AGRO_ZONAS_SIMPLIFY_TOLERANCE})",
        generated_at=generated_at,
    )
    write_geojson(
        outputs["porcentaje_forestacion"],
        forestacion_thinned,
        source=f"IDECor WFS {FORESTACION} (thinned to {{nro_cuenta, forest_obligatoria}})",
        generated_at=generated_at,
    )
    write_json(
        outputs["bpa_enriched"],
        {
            "source": (
                f"IDECor WFS bpa_2025 + {AGRO_ACEPTADA} + {AGRO_PRESENTADA} + catastro_rural_cu"
            ),
            "parcels": enriched_parcels,
        },
        schema_version=BPA_ENRICHED_SCHEMA_VERSION,
        generated_at=generated_at,
    )
    write_json(
        outputs["bpa_history"],
        {"history": history},
        generated_at=generated_at,
    )
    write_json(
        outputs["aggregates"],
        aggregates_payload,
        schema_version=AGGREGATES_SCHEMA_VERSION,
        generated_at=generated_at,
    )

    # Phase 7 — unified historical BPA layer (one feature per parcel with
    # años_bpa >= 1, colored by commitment depth on the map).
    bpa_historico = build_bpa_historico_features(enriched_parcels, catastro_features)
    write_geojson(
        outputs["bpa_historico"],
        bpa_historico.get("features") or [],
        source=(
            "Catastro rural + bpa_2025 + bpa historical series (2019-2024) — joined"
        ),
        generated_at=generated_at,
    )

    elapsed = time.monotonic() - start

    print("\n=== Pilar Verde ETL summary ===")
    for key, path in outputs.items():
        if not path.exists():
            print(f"  {key:24s} MISSING")
            continue
        size_kb = path.stat().st_size / 1024
        print(f"  {key:24s} {size_kb:>10.1f} KB  {path.relative_to(path.parents[3])}")
    print(
        f"wall_time: {elapsed:.1f}s schema_version(generic)={SCHEMA_VERSION} "
        f"aggregates_schema_version={AGGREGATES_SCHEMA_VERSION}\n"
    )

    return EXIT_OK


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="etl_pilar_verde",
        description="ETL — Pilar Verde (BPA + Plan Provincial Agroforestal)",
    )
    parser.add_argument(
        "--skip-historical-bpa",
        action="store_true",
        help="Do not fetch BPA 2019-2024 (faster; bpa_history.json will be empty).",
    )
    parser.add_argument(
        "--skip-zonas-agroforestales",
        action="store_true",
        help="Do not fetch idecor:agricultura_agro_zonas (agro_zonas.geojson will be empty).",
    )
    parser.add_argument(
        "--skip-forestacion",
        action="store_true",
        help="Do not fetch idecor:agricultura_agro_porcentaje_forestacion (file will be empty).",
    )
    parser.add_argument(
        "--skip-grilla",
        action="store_true",
        help="Do not fetch idecor:agro_grilla_dist5 (grilla_aggregates will be all zeros).",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Enable DEBUG-level logging.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    _configure_logging(level=logging.DEBUG if args.verbose else logging.INFO)
    generated_at = os.environ.get("ETL_GENERATED_AT")
    return run_etl(
        fetch_historical_bpa=not args.skip_historical_bpa,
        fetch_zonas_agroforestales=not args.skip_zonas_agroforestales,
        fetch_forestacion=not args.skip_forestacion,
        fetch_grilla=not args.skip_grilla,
        generated_at=generated_at,
    )


if __name__ == "__main__":
    sys.exit(main())
