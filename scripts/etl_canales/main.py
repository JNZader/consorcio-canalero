"""Orchestrator — unzip KMZs, parse names, compute longitud, emit 3 static files.

Contract
--------
- **All-or-nothing writes**: when inputs are missing, or when the parse-failure
  rate exceeds ``PARSE_WARN_THRESHOLD_PCT``, NO output files are written and
  the process exits with a non-zero code.
- **Exit codes** (mirrors ``etl_pilar_verde``):
  - ``0`` — OK, 3 files written.
  - ``1`` — data-quality failure (reserved for future zero-feature gates).
  - ``2`` — parse-failure rate exceeded threshold (``EXIT_PARSE_FAILED``).
  - ``3`` — required input KMZ missing (``EXIT_INPUT_MISSING``).
  - ``4`` — unexpected error (``EXIT_UNEXPECTED``).
- **Idempotent**: same inputs + same ``ETL_GENERATED_AT`` → byte-identical
  outputs.  Used for testing and deterministic diff review.
- **Polygons are skipped** with an INFO log (the Pilar Azul v1 scope is
  LineStrings only — per proposal #2038 the polygon "Las Tres del Norte"
  was explicitly discarded).
- **Slug collisions** are resolved deterministically via
  ``slugify_with_suffix(base, folder, idx)`` where ``idx`` is a per-folder
  0-indexed counter that follows KML document order — this is what keeps
  slugs stable across re-runs even though 7 relevados share the same base
  name in the real KMZ.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import Literal

from scripts.etl_canales.kmz import RawPlacemark, extract_placemarks
from scripts.etl_canales.longitud import compute_longitud_m
from scripts.etl_canales.parse_name import ParsedName, parse_name
from scripts.etl_canales.slugify import slugify, slugify_with_suffix
from scripts.etl_canales.writers import (
    CanalFeature,
    IndexMeta,
    write_geojson_canales,
    write_index_json,
)

logger = logging.getLogger("etl_canales")

# ---------------------------------------------------------------------------
# Constants (hardcoded v1 per proposal — user-locked)
# ---------------------------------------------------------------------------

RELEVADOS_KMZ: Path = Path("/home/javier/Descargas/Canales_existentes_v3.kmz")
PROPUESTAS_KMZ: Path = Path("/home/javier/Descargas/Propuestas_v3.kmz")

# Repo root resolved from this file's path: etl_canales/main.py -> etl_canales/ -> scripts/ -> <repo>.
REPO_ROOT: Path = Path(__file__).resolve().parents[2]
OUTPUT_DIR: Path = REPO_ROOT / "consorcio-web" / "public" / "capas" / "canales"

# If > this percentage of features fail to parse ANY structured metadata
# (codigo, longitud_declarada_m, or prioridad), we abort without writing.
PARSE_WARN_THRESHOLD_PCT: float = 10.0

EXIT_OK: int = 0
EXIT_DATA_QUALITY: int = 1
EXIT_PARSE_FAILED: int = 2
EXIT_INPUT_MISSING: int = 3
EXIT_UNEXPECTED: int = 4


def _configure_logging(level: int = logging.INFO) -> None:
    """One-line structured log format, mirrors ``etl_pilar_verde``."""
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)5s] %(name)s: %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
    )


def _build_canal_feature(
    placemark: RawPlacemark,
    parsed: ParsedName,
    feature_id: str,
    estado: Literal["relevado", "propuesto"],
) -> CanalFeature:
    """Combine a RawPlacemark + ParsedName into a writable CanalFeature.

    Computes the geodesic longitud from the placemark's coords, wires the
    ``estado`` discriminant, and wires the ``tramo_folder`` from the LAST
    segment of the folder_path (the UI wants the immediate parent folder
    name, not the full path).
    """
    longitud_m = compute_longitud_m(placemark.coords) if placemark.coords else 0.0
    # The "tramo" shown in UI is the innermost folder name, NOT the full
    # folder path — that tends to be redundant ("Canales existentes/Canal Norte"
    # → just "Canal Norte").  Fall back to None when the placemark is at the
    # top of a root folder.
    segments = [s for s in placemark.folder_path.split("/") if s]
    tramo_folder: str | None = segments[-1] if segments else None

    # Nombre shown in UI: prefer the parsed descripcion (human-readable chunk
    # without the metadata) when the parser extracted one; fall back to the
    # raw name so we never show an empty label.
    nombre = parsed.descripcion.strip() if parsed.descripcion.strip() else placemark.name

    return CanalFeature(
        id=feature_id,
        codigo=parsed.codigo,
        nombre=nombre,
        descripcion=parsed.descripcion if parsed.descripcion != nombre else None,
        estado=estado,
        longitud_m=longitud_m,
        longitud_declarada_m=parsed.longitud_declarada_m,
        # RELEVADOS never have prioridad (per spec); force None defensively.
        prioridad=parsed.prioridad if estado == "propuesto" else None,
        featured=parsed.featured,
        tramo_folder=tramo_folder,
        source_style=placemark.style_url,
        coords=list(placemark.coords),
    )


def _process_kmz(
    kmz_path: Path,
    estado: Literal["relevado", "propuesto"],
) -> tuple[list[CanalFeature], int, int]:
    """Parse a KMZ and build CanalFeatures.

    Returns ``(features, total_linestrings, parse_failures)`` where
    ``parse_failures`` is the count of placemarks whose parsed name produced
    NO structured metadata (no codigo, no longitud declarada, no prioridad).
    """
    placemarks = extract_placemarks(kmz_path)
    features: list[CanalFeature] = []
    parse_failures = 0
    total_linestrings = 0

    # Per-folder counters drive deterministic collision resolution.  Key is
    # ``(base_slug, folder_slug)`` so two folders with identical base slugs
    # each start their own 0-index run.
    base_slug_counter: dict[str, int] = {}
    base_seen: set[str] = set()

    for idx, pm in enumerate(placemarks):
        if pm.geometry_type != "LineString":
            logger.info(
                "canales.etl: skipping non-LineString placemark %r (type=%s)",
                pm.name,
                pm.geometry_type,
            )
            continue

        total_linestrings += 1
        parsed = parse_name(pm.name)

        # Detect parse failures — a name whose STRUCTURE implies the author
        # intended structured metadata (has a ``·`` separator) but where the
        # parser recovered NOTHING.  Names without ``·`` are informational
        # labels (e.g. "Canal NE (sin intervención)") and are NOT failures —
        # they're legitimate relevado entries without metadata.
        had_structured_intent = "\u00b7" in pm.name
        recovered_nothing = (
            parsed.codigo is None
            and parsed.longitud_declarada_m is None
            and parsed.prioridad is None
        )
        if had_structured_intent and recovered_nothing:
            parse_failures += 1

        # Build the base slug: prefer codigo-prefixed when present.
        base_parts: list[str] = []
        if parsed.codigo:
            base_parts.append(slugify(parsed.codigo))
        nombre_slug = slugify(parsed.descripcion) if parsed.descripcion else slugify(pm.name)
        if nombre_slug:
            base_parts.append(nombre_slug)
        base_slug = "-".join(p for p in base_parts if p)
        if not base_slug:
            # Last-ditch fallback so we NEVER emit a feature with an empty id.
            base_slug = f"canal-{idx}"

        # Collision resolution: first occurrence keeps the base slug; each
        # subsequent occurrence gets a ``-{folder-slug}-{idx}`` suffix where
        # idx is the per-base-slug 0-indexed counter.
        if base_slug in base_seen:
            next_idx = base_slug_counter.get(base_slug, 0)
            candidate_id = slugify_with_suffix(base_slug, pm.folder_path, next_idx)
            base_slug_counter[base_slug] = next_idx + 1
            # Extremely defensive: if the suffix-ed id somehow collides too,
            # keep bumping.
            while candidate_id in base_seen:
                next_idx += 1
                candidate_id = slugify_with_suffix(base_slug, pm.folder_path, next_idx)
                base_slug_counter[base_slug] = next_idx + 1
            feature_id = candidate_id
        else:
            feature_id = base_slug

        base_seen.add(feature_id)

        feature = _build_canal_feature(pm, parsed, feature_id, estado)
        features.append(feature)

    return features, total_linestrings, parse_failures


def _features_to_index(features: list[CanalFeature]) -> list[IndexMeta]:
    """Derive the per-canal ``index.json`` row list from CanalFeatures."""
    return [
        IndexMeta(
            id=f.id,
            nombre=f.nombre,
            codigo=f.codigo,
            prioridad=f.prioridad,
            longitud_m=round(f.longitud_m, 1),
            featured=f.featured,
            estado=f.estado,
        )
        for f in features
    ]


def run_etl(
    *,
    relevados_kmz: Path = RELEVADOS_KMZ,
    propuestas_kmz: Path = PROPUESTAS_KMZ,
    output_dir: Path = OUTPUT_DIR,
    generated_at: str | None = None,
) -> int:
    """Run the full ETL.  Returns a process exit code (0 = success)."""
    # 1. Input-presence gate.
    if not Path(relevados_kmz).exists():
        logger.error("RELEVADOS KMZ missing: %s", relevados_kmz)
        return EXIT_INPUT_MISSING
    if not Path(propuestas_kmz).exists():
        logger.error("PROPUESTAS KMZ missing: %s", propuestas_kmz)
        return EXIT_INPUT_MISSING

    # 2. Parse + build features (all in memory — writes happen last so we
    #    can enforce the all-or-nothing parse-quality gate).
    try:
        relevados, rel_line_count, rel_failures = _process_kmz(
            Path(relevados_kmz), "relevado"
        )
        propuestas, prop_line_count, prop_failures = _process_kmz(
            Path(propuestas_kmz), "propuesto"
        )
    except Exception:  # noqa: BLE001 — catch-all to get clean exit code
        logger.exception("canales.etl: unexpected parse error")
        return EXIT_UNEXPECTED

    logger.info(
        "canales.etl: parsed relevados=%d propuestas=%d "
        "(parse_failures relevados=%d propuestas=%d)",
        len(relevados),
        len(propuestas),
        rel_failures,
        prop_failures,
    )

    # 3. Parse-failure threshold gate.
    total_lines = rel_line_count + prop_line_count
    total_failures = rel_failures + prop_failures
    if total_lines > 0:
        failure_pct = (total_failures / total_lines) * 100.0
        if failure_pct > PARSE_WARN_THRESHOLD_PCT:
            logger.error(
                "canales.etl: parse-failure rate %.1f%% exceeds threshold %.1f%% "
                "(failures=%d/%d) — aborting without writing",
                failure_pct,
                PARSE_WARN_THRESHOLD_PCT,
                total_failures,
                total_lines,
            )
            return EXIT_PARSE_FAILED

    # 4. Write outputs.
    try:
        out_dir = Path(output_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        write_geojson_canales(
            relevados, out_dir / "relevados.geojson", generated_at=generated_at
        )
        write_geojson_canales(
            propuestas, out_dir / "propuestas.geojson", generated_at=generated_at
        )
        write_index_json(
            _features_to_index(relevados),
            _features_to_index(propuestas),
            out_dir / "index.json",
            generated_at=generated_at,
        )
    except Exception:  # noqa: BLE001
        logger.exception("canales.etl: unexpected write error")
        return EXIT_UNEXPECTED

    logger.info(
        "canales.etl: OK — wrote %d relevados + %d propuestas to %s",
        len(relevados),
        len(propuestas),
        out_dir,
    )
    return EXIT_OK


def main(argv: list[str] | None = None) -> int:  # noqa: ARG001 — reserved for CLI flags
    """CLI entry point.  No args needed; paths are hardcoded in constants."""
    _configure_logging()
    import os

    generated_at = os.environ.get("ETL_GENERATED_AT")
    return run_etl(generated_at=generated_at)


if __name__ == "__main__":
    sys.exit(main())
