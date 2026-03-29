#!/usr/bin/env python3
"""Download water body geometries from OpenStreetMap Overpass API."""

import json
import urllib.request
import urllib.parse
import sys
import time

OVERPASS_URL = "https://overpass-api.de/api/interpreter"
OUTPUT_DIR = "/home/javier/programacion/consorcio-canalero/gee-backend/data/waterways"

WATERWAYS = [
    {
        "name": "Rio Tercero",
        "filename": "rio_tercero.geojson",
        "query": '[out:json];(way["waterway"]["name"~"Tercero|Ctalamochita",i](-33.0,-63.2,-32.2,-62.0););out geom;',
    },
    {
        "name": "Canal Desviador",
        "filename": "canal_desviador.geojson",
        "query": '[out:json];(way["waterway"]["name"~"desviador",i](-33.0,-63.2,-32.2,-62.0););out geom;',
    },
    {
        "name": "Canal Litin Tortugas",
        "filename": "canal_litin_tortugas.geojson",
        "query": '[out:json];(way["waterway"]["name"~"Litin|Tortugas",i](-33.0,-63.2,-32.2,-62.0););out geom;',
    },
    {
        "name": "Arroyo Algodon",
        "filename": "arroyo_algodon.geojson",
        "queries": [
            '[out:json];relation(13508662);way(r);out geom;',
            '[out:json];(way["waterway"]["name"~"Algod",i](-33.0,-63.2,-32.2,-62.0););out geom;',
        ],
    },
]


def fetch_overpass(query):
    """Query Overpass API and return JSON response."""
    encoded = urllib.parse.urlencode({"data": query})
    url = f"{OVERPASS_URL}?{encoded}"
    print(f"  Fetching: {query[:80]}...")
    req = urllib.request.Request(url, headers={"User-Agent": "consorcio-canalero/1.0"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.loads(resp.read().decode("utf-8"))


def overpass_to_geojson(overpass_data, name):
    """Convert Overpass JSON to GeoJSON FeatureCollection."""
    features = []
    for element in overpass_data.get("elements", []):
        if element["type"] == "way" and "geometry" in element:
            coords = [[node["lon"], node["lat"]] for node in element["geometry"]]
            feature = {
                "type": "Feature",
                "properties": {
                    "osm_id": element["id"],
                    "name": element.get("tags", {}).get("name", name),
                    "waterway": element.get("tags", {}).get("waterway", "unknown"),
                },
                "geometry": {"type": "LineString", "coordinates": coords},
            }
            features.append(feature)
    return {"type": "FeatureCollection", "features": features}


def get_extent(geojson):
    """Calculate bounding box of a GeoJSON FeatureCollection."""
    lons, lats = [], []
    for feat in geojson["features"]:
        for coord in feat["geometry"]["coordinates"]:
            lons.append(coord[0])
            lats.append(coord[1])
    if not lons:
        return None
    return {
        "min_lon": min(lons),
        "max_lon": max(lons),
        "min_lat": min(lats),
        "max_lat": max(lats),
    }


def main():
    results = []
    for i, ww in enumerate(WATERWAYS):
        print(f"\n[{i+1}/{len(WATERWAYS)}] Downloading: {ww['name']}")
        queries = ww.get("queries", [ww.get("query")])

        data = None
        for q in queries:
            try:
                data = fetch_overpass(q)
                if data.get("elements"):
                    print(f"  Got {len(data['elements'])} elements")
                    break
                else:
                    print("  No elements found, trying next query...")
            except Exception as e:
                print(f"  Query failed: {e}, trying next...")

        if not data or not data.get("elements"):
            print(f"  WARNING: No data found for {ww['name']}")
            results.append({"name": ww["name"], "features": 0, "error": "no data"})
            continue

        geojson = overpass_to_geojson(data, ww["name"])
        output_path = f"{OUTPUT_DIR}/{ww['filename']}"

        with open(output_path, "w") as f:
            json.dump(geojson, f, indent=2)

        extent = get_extent(geojson)
        n_features = len(geojson["features"])
        print(f"  Saved {n_features} features to {output_path}")
        if extent:
            print(f"  Extent: lon [{extent['min_lon']:.4f}, {extent['max_lon']:.4f}] lat [{extent['min_lat']:.4f}, {extent['max_lat']:.4f}]")

        results.append({
            "name": ww["name"],
            "file": ww["filename"],
            "features": n_features,
            "extent": extent,
        })

        # Be polite to the API
        if i < len(WATERWAYS) - 1:
            time.sleep(2)

    print("\n=== SUMMARY ===")
    for r in results:
        status = f"{r['features']} features" if r["features"] > 0 else "FAILED"
        print(f"  {r['name']}: {status}")
        if r.get("extent"):
            e = r["extent"]
            print(f"    Center: ({(e['min_lat']+e['max_lat'])/2:.4f}, {(e['min_lon']+e['max_lon'])/2:.4f})")


if __name__ == "__main__":
    main()
