/**
 * kmzBuilder
 *
 * Phase 3 entry point for the `kmz-export-all-layers` change.
 * Assembles a Google-Earth-compatible `.kmz` blob from the currently
 * visible GeoJSON layers:
 *
 *   1. Filter `KMZ_LAYER_REGISTRY` by visibility + exclusion list + data
 *      presence. YPF is always-on (no toggle in `defaultVisibleVectors`).
 *   2. Emit `<Style>` blocks for the INCLUDED layers only (no dead styles).
 *   3. Emit one `<Folder>` per included layer containing one `<Placemark>`
 *      per feature via the placemark emitter (see `./kmzPlacemarks.ts`).
 *   4. Wrap with `<kml xmlns="http://www.opengis.net/kml/2.2"><Document>…
 *      </Document></kml>` and zip to `doc.kml` using JSZip.
 *   5. Return the Blob tagged with `application/vnd.google-earth.kmz`.
 *
 * Feature filters applied at the builder level:
 *   - `canales_propuestos` → filter by `propuestasEtapasVisibility` (Pair 4).
 *
 * Feature→Placemark transforms live in `./kmzPlacemarks.ts` so they can be
 * tested in isolation (the builder is already a fat integration contract).
 */

import JSZip from 'jszip';
import type { FeatureCollection } from 'geojson';

import { buildPlacemark } from './kmzPlacemarks';
import {
  KMZ_EXCLUDED_LAYER_KEYS,
  KMZ_LAYER_REGISTRY,
  type KmzLayerEntry,
} from './kmzLayerRegistry';
import { buildKmzStyles } from './kmzStyles';

// ---------------------------------------------------------------------------
// Public input contract.
// ---------------------------------------------------------------------------

export interface BuildKmzInput {
  /** Map of layer key → boolean visibility. Excluded keys are IGNORED
   *  regardless of value. YPF is always-on regardless of this map. */
  visibleLayers: Record<string, boolean>;
  /** Map of layer key → FeatureCollection | null. Missing or null entries
   *  are SKIPPED silently (even when `visibleLayers[key] === true`). */
  data: Record<string, FeatureCollection | null>;
  /** Optional etapas filter for `canales_propuestos`. When absent or
   *  empty-object, ALL etapas are included (permissive default). */
  propuestasEtapasVisibility?: Record<string, boolean>;
  /** Timestamp for `<Document><name>`. Defaults to `new Date()`. */
  timestamp?: Date;
}

// ---------------------------------------------------------------------------
// Constants + helpers.
// ---------------------------------------------------------------------------

/** Key that is ALWAYS included when data is present, regardless of the
 *  visibility map. Mirrors the in-app always-on YPF pin. */
const ALWAYS_ON_KEYS = new Set<string>(['ypf-estacion-bombeo']);

const EXCLUDED_SET = new Set<string>(KMZ_EXCLUDED_LAYER_KEYS);

const KMZ_MIME_TYPE = 'application/vnd.google-earth.kmz';
const KML_XML_DECLARATION = '<?xml version="1.0" encoding="UTF-8"?>';
const KML_ROOT_OPEN = '<kml xmlns="http://www.opengis.net/kml/2.2">';
const KML_ROOT_CLOSE = '</kml>';

/** Format a Date as ISO-local YYYY-MM-DD (no time). Used for the
 *  `<Document><name>` and the download filename. */
function formatDocumentDate(ts: Date): string {
  const yyyy = ts.getFullYear();
  const mm = String(ts.getMonth() + 1).padStart(2, '0');
  const dd = String(ts.getDate()).padStart(2, '0');
  return `${yyyy}-${mm}-${dd}`;
}

/**
 * Decide if a registry entry should be emitted.
 *   - Excluded keys → NEVER (defense-in-depth; the registry shouldn't list
 *     them, but we re-check in case a future edit accidentally adds one).
 *   - No data / empty features array → SKIP silently.
 *   - Always-on keys → include when data is present.
 *   - Otherwise → include only when `visibleLayers[key] === true`.
 */
function shouldIncludeLayer(
  entry: KmzLayerEntry,
  visibleLayers: Record<string, boolean>,
  data: Record<string, FeatureCollection | null>,
): boolean {
  if (EXCLUDED_SET.has(entry.key)) return false;
  const fc = data[entry.key];
  if (!fc || !fc.features || fc.features.length === 0) return false;
  if (ALWAYS_ON_KEYS.has(entry.key)) return true;
  return visibleLayers[entry.key] === true;
}

// Pair 4 extends this with an etapas filter for `canales_propuestos`.

// ---------------------------------------------------------------------------
// Main assembler.
// ---------------------------------------------------------------------------

/**
 * Build a KMZ blob from the current layer visibility + data snapshot.
 *
 * Pure function: the Blob it returns is self-contained — no external
 * references, no network calls. Caller is responsible for the download
 * trigger (see Phase 4).
 */
export async function buildKmz(input: BuildKmzInput): Promise<Blob> {
  const { visibleLayers, data, timestamp } = input;
  const dateLabel = formatDocumentDate(timestamp ?? new Date());

  // 1. Filter + resolve the registry to the "included" shortlist.
  const includedEntries = KMZ_LAYER_REGISTRY.filter((entry) =>
    shouldIncludeLayer(entry, visibleLayers, data),
  );

  // 2. Emit the style block for the included entries only.
  const stylesBlock = buildKmzStyles(includedEntries);

  // 3. Emit one Folder per included entry.
  //    Pair 4 layers an etapas filter on top of this loop for
  //    `canales_propuestos`.
  const foldersBlock = includedEntries
    .map((entry) => {
      const rawFeatures = data[entry.key]?.features ?? [];
      const placemarks = rawFeatures
        .map((feature, index) => buildPlacemark(feature, entry, index))
        .join('');
      return `<Folder><name>${escapeXml(entry.label)}</name>${placemarks}</Folder>`;
    })
    .join('');

  // 4. Wrap in the KML document.
  const documentBlock =
    `<Document>` +
    `<name>Consorcio Canalero — ${dateLabel}</name>` +
    stylesBlock +
    foldersBlock +
    `</Document>`;

  const kmlString =
    KML_XML_DECLARATION + KML_ROOT_OPEN + documentBlock + KML_ROOT_CLOSE;

  // 5. Package into the KMZ (zip with a single `doc.kml` entry).
  const zip = new JSZip();
  zip.file('doc.kml', kmlString);
  const blob = await zip.generateAsync({
    type: 'blob',
    mimeType: KMZ_MIME_TYPE,
    compression: 'DEFLATE',
    compressionOptions: { level: 6 },
  });

  return blob;
}

// ---------------------------------------------------------------------------
// XML escape (local — the placemark emitter re-exports its own).
// ---------------------------------------------------------------------------

/**
 * Escape the 5 XML entities in text content. Duplicated here (small) to
 * keep the builder's `<Folder><name>…</name>` safe without importing
 * from `kmzPlacemarks.ts` just for this one site.
 */
function escapeXml(s: string): string {
  return s
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&apos;');
}
