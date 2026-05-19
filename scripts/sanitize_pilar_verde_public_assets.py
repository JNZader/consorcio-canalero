"""One-shot PII strip for already-published Pilar Verde assets.

The ETL was fixed to drop producer-identifying fields, but the static
files already committed under ``consorcio-web/public/`` still carried
them. Rerunning the full ETL needs live access to IDECor WFS, which
isn't always available — this script walks the published files and
removes the PII in place so we can ship the fix today without waiting
on the next ETL run.

What it strips
--------------
- ``bpa_2025.geojson`` properties: ``n_explotacion``, ``id_explotacion``.
  Geometry and aggregate BPA fields (ejes, prácticas, ``activa``,
  ``bpa_total``, ``superficie*``, ``cuenta``) are kept.
- ``bpa_enriched.json`` parcels: drop ``valuacion``; inside
  ``bpa_2025``, drop ``n_explotacion`` and ``id_explotacion``; rewrite
  ``bpa_historico`` from ``{year: name}`` to ``{year: True}``.
- ``bpa_history.json`` history: rewrite ``{cuenta: {year: name}}`` to
  ``{cuenta: {year: True}}``.
- ``bpa_historico.geojson`` features: drop ``n_explotacion_ultima``.

Run from the repo root:
    python scripts/sanitize_pilar_verde_public_assets.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
PUBLIC_CAPAS = REPO_ROOT / "consorcio-web" / "public" / "capas" / "pilar-verde"
PUBLIC_DATA = REPO_ROOT / "consorcio-web" / "public" / "data" / "pilar-verde"

# Fields we delete on contact wherever they appear.
PII_PROP_NAMES = frozenset({"n_explotacion", "id_explotacion", "valuacion"})


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json_compact(path: Path, payload: Any) -> None:
    """Match the ETL's compact GeoJSON output (no spaces, trailing newline)."""
    path.write_text(
        json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )


def _write_json_indented(path: Path, payload: Any) -> None:
    """Match the ETL's JSON-with-metadata output (indent=2)."""
    path.write_text(
        json.dumps(payload, ensure_ascii=False, separators=(",", ":"), indent=2)
        + "\n",
        encoding="utf-8",
    )


def sanitize_bpa_2025(path: Path) -> int:
    """Strip n_explotacion / id_explotacion from bpa_2025.geojson properties."""
    payload = _read_json(path)
    features = payload.get("features") or []
    changes = 0
    for feat in features:
        props = feat.get("properties") or {}
        for pii in PII_PROP_NAMES:
            if pii in props:
                props.pop(pii, None)
                changes += 1
        feat["properties"] = props
    _write_json_compact(path, payload)
    return changes


def sanitize_bpa_enriched(path: Path) -> int:
    """Strip valuacion + nested BPA name fields, rewrite historico to bool."""
    payload = _read_json(path)
    parcels = payload.get("parcels") or []
    changes = 0
    for parcel in parcels:
        if "valuacion" in parcel:
            parcel.pop("valuacion", None)
            changes += 1
        bpa = parcel.get("bpa_2025")
        if isinstance(bpa, dict):
            for pii in PII_PROP_NAMES:
                if pii in bpa:
                    bpa.pop(pii, None)
                    changes += 1
        historico = parcel.get("bpa_historico")
        if isinstance(historico, dict) and historico:
            # Replace any string value with True; keep keys as-is.
            parcel["bpa_historico"] = {year: True for year in historico}
            changes += 1
    _write_json_indented(path, payload)
    return changes


def sanitize_bpa_history(path: Path) -> int:
    """Rewrite {cuenta: {year: name}} → {cuenta: {year: True}}."""
    payload = _read_json(path)
    history = payload.get("history") or {}
    changes = 0
    for cuenta, years in list(history.items()):
        if not isinstance(years, dict):
            continue
        history[cuenta] = {year: True for year in years}
        changes += 1
    payload["history"] = history
    _write_json_indented(path, payload)
    return changes


def sanitize_bpa_historico_geojson(path: Path) -> int:
    """Strip n_explotacion_ultima from bpa_historico.geojson properties."""
    payload = _read_json(path)
    features = payload.get("features") or []
    changes = 0
    for feat in features:
        props = feat.get("properties") or {}
        if "n_explotacion_ultima" in props:
            props.pop("n_explotacion_ultima", None)
            changes += 1
        feat["properties"] = props
    _write_json_compact(path, payload)
    return changes


def main() -> int:
    targets = [
        (PUBLIC_CAPAS / "bpa_2025.geojson", sanitize_bpa_2025),
        (PUBLIC_DATA / "bpa_enriched.json", sanitize_bpa_enriched),
        (PUBLIC_DATA / "bpa_history.json", sanitize_bpa_history),
        (PUBLIC_CAPAS / "bpa_historico.geojson", sanitize_bpa_historico_geojson),
    ]

    missing = [path for path, _ in targets if not path.exists()]
    if missing:
        print("MISSING:")
        for path in missing:
            print(f"  {path}")
        print("Run the Pilar Verde ETL first, or skip them.")

    total = 0
    for path, sanitizer in targets:
        if not path.exists():
            continue
        changes = sanitizer(path)
        total += changes
        print(f"  {path.relative_to(REPO_ROOT)}: {changes} PII field deletions")

    print(f"\nDone. Total field deletions: {total}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
