"""Fetch the IDECOR hydro layers for the consortium zona and write GeoJSON.

Uses the same WFS client as the Pilar Verde ETL (dual host, bbox in
EPSG:22174, output in EPSG:4326). Load the files into PostGIS with
``scripts/sql/idecor_hidrografia.sql`` and ogr2ogr before restarting Martin.
"""

from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path

from scripts.etl_idecor_capas.layers import IDECOR_LAYER_NAMES, public_feature
from scripts.etl_pilar_verde.main import _fetch_and_clip, _load_zona, _project_bbox_to_22174
from scripts.etl_pilar_verde.constants import KML_SOURCE

logger = logging.getLogger("etl_idecor_capas")


def fetch_layers(zona_path: Path) -> dict[str, dict]:
    zona = _load_zona(zona_path)
    bbox = _project_bbox_to_22174(zona)
    collections: dict[str, dict] = {}
    for key, type_name in IDECOR_LAYER_NAMES.items():
        features = _fetch_and_clip(type_name, bbox, zona)
        collections[key] = {
            "type": "FeatureCollection",
            "features": [public_feature(feature) for feature in features],
        }
        logger.info("%s features=%s", type_name, len(collections[key]["features"]))
    return collections


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    parser = argparse.ArgumentParser(description="Fetch IDECOR hydro layers clipped to the zona")
    parser.add_argument("--zona", type=Path, default=KML_SOURCE)
    parser.add_argument("--out", type=Path, default=Path("data/idecor"))
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    for key, collection in fetch_layers(args.zona).items():
        target = args.out / f"{key}.geojson"
        target.write_text(json.dumps(collection), encoding="utf-8")
        logger.info("wrote %s", target)


if __name__ == "__main__":
    main()
