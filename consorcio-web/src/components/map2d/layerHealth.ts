/**
 * Layer health registry (Batch 1 — "datos honestos").
 *
 * A DERIVED registry, not a store: every render folds the map's data hooks into
 * one flat list of per-FAMILY entries so the UI can say WHICH layer family is
 * broken and offer a retry, instead of leaving a toggled-on layer silently
 * empty. There is no state here — the hooks remain the single source of truth.
 *
 * Contract:
 *   - ONE entry per layer FAMILY (`LayerHealthKey`), never one per file/slot.
 *   - `failed` is the subset the banner counts: `error` + `degradado`. A family
 *     still `cargando` is NOT a failure — it has not failed yet.
 *   - `byCategory` maps an accordion family (`LayerCategory`) to the FIRST
 *     failed entry belonging to it, so the panel can render an inline row.
 *   - `retryAll()` only calls `reload` on FAILED entries that expose one.
 *
 * GATES (load-bearing, do not "simplify"):
 * A lazy family whose gate is CLOSED produces NO entry at all. Two reasons:
 *   1. Falsos positivos — `useGeoLayers` is gated on auth, so an anonymous
 *      visitor would otherwise see "Capas DEM no cargaron" for a fetch that
 *      never ran on their behalf.
 *   2. `retryAll()` calls `refetch()`, and TanStack v5's `refetch()` IGNORES
 *      `enabled`. Reporting a gated-off family would let one click on the
 *      banner pull down the multi-MB soil/catastro GeoJSON the gate exists to
 *      defer.
 */

import { SOURCE_IDS } from './map2dConfig';
import type { LayerCategory } from './map2dDerived';
import { LAYER_CATEGORY } from './map2dDerived';

export type LayerHealthStatus = 'ok' | 'cargando' | 'error' | 'degradado';

export type LayerHealthKey =
  | 'caminos'
  | 'basins'
  | 'waterways'
  | 'geo_layers'
  | 'soil'
  | 'catastro'
  | 'canales'
  | 'escuelas'
  | 'pilar_verde'
  | 'ign_overlay'
  | 'raster_tiles';

export interface LayerHealthEntry {
  readonly key: LayerHealthKey;
  /** User-facing family name (Spanish) used by log lines and copy. */
  readonly label: string;
  /**
   * Accordion family this entry belongs to, or `null` when the family has no
   * accordion home (raster tiles are a cross-cutting transport failure).
   */
  readonly category: LayerCategory | null;
  readonly status: LayerHealthStatus;
  /**
   * CURATED user-facing copy (Rioplatense Spanish), never the raw `Error`
   * message from the slot. The underlying hooks surface technical English
   * strings with internal paths ("Error fetching soil map: 404") which are fine
   * for the logs and unacceptable on screen beside the hand-written copy of the
   * other families. The raw string stays in the console; this is what the user
   * reads. `null` when the family is healthy.
   */
  readonly message: string | null;
  readonly reload: (() => void) | null;
}

export interface LayerHealth {
  readonly entries: readonly LayerHealthEntry[];
  /** Entries whose status is `error` or `degradado`. Drives the banner count. */
  readonly failed: readonly LayerHealthEntry[];
  readonly byCategory: Partial<Record<LayerCategory, LayerHealthEntry>>;
  readonly retryAll: () => void;
}

/** One data hook's health, flattened to the three fields the registry reads. */
export interface LayerHealthSlot {
  readonly error?: string | null;
  readonly loading?: boolean;
  readonly reload?: (() => void) | null;
}

/**
 * Raster tiles are NOT a query: there is no error string and no refetch, only
 * a rolling count of failing tile sources produced by `useRasterTileHealth`.
 *
 * Pass the WHOLE list; ids that have a dedicated entry (see
 * `DEDICATED_SOURCE_ENTRIES`) are subtracted here, so the container never has to
 * know which sources got promoted out of the aggregate.
 */
export interface RasterTilesHealthSlot {
  readonly degradedSourceIds?: readonly string[];
}

/**
 * Gates of the LAZY families. `true` (default) = the family's fetch is allowed
 * to run, so its health is meaningful. `false` = no entry at all.
 */
export interface LayerHealthGates {
  /** `useGeoLayers` is gated on auth init — closed while auth is resolving. */
  readonly geoLayers?: boolean;
  /** `useSoilMap` only fetches while the soil layer is visible. */
  readonly soil?: boolean;
  /** `useCatastroMap` only fetches once export intent latched. */
  readonly catastro?: boolean;
  /**
   * `usePilarVerde({ layers })` only fetches the ~1.0 MB render group while a
   * `pilar_verde_*` toggle is ON. Without this gate a failure SURVIVED the user
   * turning the layer back off (`staleTime: Infinity` + a mounted observer keep
   * `layersError` set), leaving a permanent, undismissable banner whose
   * "Reintentar" re-downloaded ~1 MB for a family nobody is looking at.
   */
  readonly pilarVerde?: boolean;
  /**
   * The IGN altimetry overlay is only MOUNTED once the user turns it on
   * (`syncIgnLayer` is lazy by contract — the ~1.5 MB WebP is not downloaded
   * before that), so with the layer off there is nothing to report and nothing
   * to retry.
   */
  readonly ignOverlay?: boolean;
}

export interface LayerHealthInputs {
  readonly caminos?: LayerHealthSlot;
  readonly basins?: LayerHealthSlot;
  readonly waterways?: LayerHealthSlot;
  readonly geo_layers?: LayerHealthSlot;
  readonly soil?: LayerHealthSlot;
  readonly catastro?: LayerHealthSlot;
  readonly canales?: LayerHealthSlot;
  readonly escuelas?: LayerHealthSlot;
  readonly pilar_verde?: LayerHealthSlot;
  /**
   * The IGN altimetry image source. `error` is set from
   * `degradedSourceIds.includes(SOURCE_IDS.IGN)`, and `reload` MUST be the real
   * re-download (`reloadIgnSource` + `clearSource`) — this is the one degraded
   * source in the app that can actually be retried.
   */
  readonly ign_overlay?: LayerHealthSlot;
  readonly raster_tiles?: RasterTilesHealthSlot;
  readonly gates?: LayerHealthGates;
}

interface LayerHealthDef {
  readonly key: Exclude<LayerHealthKey, 'raster_tiles'>;
  readonly label: string;
  readonly category: LayerCategory | null;
  /** Gate name; `null` when the family is eager and always reportable. */
  readonly gate: keyof LayerHealthGates | null;
  /** Canonical es-AR failure copy. See `LayerHealthEntry.message`. */
  readonly errorMessage: string;
}

/**
 * Registry order = the order entries appear in `entries`/`failed`, which is the
 * order a future list UI would show them in. Raster tiles are appended last by
 * `buildLayerHealth` (they are a transport failure, not an accordion family).
 */
const LAYER_HEALTH_DEFS: readonly LayerHealthDef[] = [
  {
    key: 'caminos',
    label: 'Red vial',
    category: LAYER_CATEGORY.TERRITORIO,
    gate: null,
    errorMessage: 'No se pudo cargar la red vial',
  },
  {
    key: 'basins',
    label: 'Subcuencas',
    category: LAYER_CATEGORY.HIDROGRAFIA,
    gate: null,
    errorMessage: 'No se pudieron cargar las subcuencas',
  },
  {
    key: 'waterways',
    label: 'Hidrografía',
    category: LAYER_CATEGORY.HIDROGRAFIA,
    gate: null,
    errorMessage: 'No se pudieron cargar las capas hidrográficas',
  },
  {
    key: 'geo_layers',
    label: 'Capas DEM',
    category: LAYER_CATEGORY.BASE,
    gate: 'geoLayers',
    errorMessage: 'No se pudieron cargar las capas DEM',
  },
  {
    key: 'soil',
    label: 'Suelos',
    category: LAYER_CATEGORY.TERRITORIO,
    gate: 'soil',
    errorMessage: 'No se pudo cargar la capa de suelos',
  },
  {
    key: 'catastro',
    label: 'Catastro rural',
    category: LAYER_CATEGORY.TERRITORIO,
    gate: 'catastro',
    errorMessage: 'No se pudo cargar el catastro rural',
  },
  {
    key: 'canales',
    label: 'Canales',
    category: LAYER_CATEGORY.CANALES,
    gate: null,
    errorMessage: 'No se pudieron cargar los canales',
  },
  {
    key: 'escuelas',
    label: 'Escuelas rurales',
    category: LAYER_CATEGORY.TERRITORIO,
    gate: null,
    errorMessage: 'No se pudieron cargar las escuelas rurales',
  },
  {
    key: 'pilar_verde',
    label: 'Pilar Verde',
    category: LAYER_CATEGORY.PILAR_VERDE,
    gate: 'pilarVerde',
    errorMessage: 'No se pudieron cargar las capas de Pilar Verde',
  },
  {
    // Its OWN entry, not a number inside `raster_tiles` (B4c fix round). The
    // aggregate is an anonymous transport counter with no retry ("los mosaicos
    // de N capas están fallando"); this is ONE nameable layer the user just
    // switched on, and it has a REAL retry (`reloadIgnSource` re-runs the single
    // request an `ImageSource` never repeats on its own). Folding it into the
    // aggregate would have offered the user a count they cannot act on and no
    // button, for the one failure here that is actually fixable.
    key: 'ign_overlay',
    label: 'Altimetría IGN',
    category: LAYER_CATEGORY.BASE,
    gate: 'ignOverlay',
    errorMessage: 'No se pudo cargar la altimetría IGN',
  },
];

/**
 * Degraded source ids that already have a DEDICATED entry, so the anonymous
 * `raster_tiles` aggregate must not count them twice.
 *
 * Applied only when that entry was actually produced (slot present + gate open)
 * — otherwise a caller that does not wire the slot would lose the signal
 * altogether, which is the failure mode this whole registry exists against.
 */
const DEDICATED_SOURCE_ENTRIES: Readonly<Record<string, Exclude<LayerHealthKey, 'raster_tiles'>>> =
  {
    [SOURCE_IDS.IGN]: 'ign_overlay',
  };

/** Copy for the raster-tile entry — singular/plural on the source count. */
export function rasterTilesMessage(count: number): string {
  return count === 1
    ? 'Los mosaicos de 1 capa están fallando'
    : `Los mosaicos de ${count} capas están fallando`;
}

function slotStatus(slot: LayerHealthSlot): LayerHealthStatus {
  if (slot.error) return 'error';
  if (slot.loading) return 'cargando';
  return 'ok';
}

/**
 * Copy for the aggregate banner. Lives beside the registry (and is unit-tested
 * there) because it encodes a distinction a bare count erases: a family that did
 * NOT LOAD is not the same as raster mosaics that are FAILING while still
 * painting whatever they already have. Returns `null` when nothing failed.
 */
export function buildHealthBannerText(failed: readonly LayerHealthEntry[]): string | null {
  if (failed.length === 0) return null;

  const parts: string[] = [];
  const errorCount = failed.filter((entry) => entry.status === 'error').length;
  if (errorCount > 0) {
    parts.push(errorCount === 1 ? '1 capa no cargó' : `${errorCount} capas no cargaron`);
  }
  for (const entry of failed) {
    // A degraded entry carries its own honest sentence ("Los mosaicos de …").
    if (entry.status === 'degradado' && entry.message) parts.push(entry.message);
  }
  return parts.join(' · ');
}

export function buildLayerHealth(inputs: LayerHealthInputs = {}): LayerHealth {
  const gates = inputs.gates ?? {};
  const entries: LayerHealthEntry[] = [];

  for (const def of LAYER_HEALTH_DEFS) {
    // Closed gate → the fetch never ran; reporting it would be a lie AND would
    // arm `retryAll` with a download the gate exists to defer.
    if (def.gate && gates[def.gate] === false) continue;

    const slot = inputs[def.key];
    if (!slot) continue;

    entries.push({
      key: def.key,
      label: def.label,
      category: def.category,
      status: slotStatus(slot),
      // Curated copy, NOT `slot.error` — see `LayerHealthEntry.message`.
      message: slot.error ? def.errorMessage : null,
      reload: slot.reload ?? null,
    });
  }

  // Sources with a dedicated entry above are NOT counted again in the anonymous
  // aggregate. Only for entries that were actually emitted — see
  // `DEDICATED_SOURCE_ENTRIES`.
  const emittedKeys = new Set(entries.map((entry) => entry.key));
  const degradedSourceIds = (inputs.raster_tiles?.degradedSourceIds ?? []).filter((sourceId) => {
    const dedicated = DEDICATED_SOURCE_ENTRIES[sourceId];
    return !(dedicated && emittedKeys.has(dedicated));
  });
  if (degradedSourceIds.length > 0) {
    entries.push({
      key: 'raster_tiles',
      label: 'Mosaicos raster',
      // No accordion home on purpose: it surfaces in the banner only.
      category: null,
      status: 'degradado',
      message: rasterTilesMessage(degradedSourceIds.length),
      // MOSAIC sources only, and those DO retry themselves on the next
      // pan/zoom — there is nothing to refetch here. (A source that fails as a
      // whole and never retries — the IGN image — is deliberately not in this
      // bucket: it gets its own entry with a real `reload`.)
      reload: null,
    });
  }

  const failed = entries.filter(
    (entry) => entry.status === 'error' || entry.status === 'degradado'
  );

  const byCategory: Partial<Record<LayerCategory, LayerHealthEntry>> = {};
  for (const entry of failed) {
    if (!entry.category) continue;
    // First failure wins: several families share one accordion category
    // (soil + catastro + escuelas + red vial are all "Territorio").
    if (!byCategory[entry.category]) byCategory[entry.category] = entry;
  }

  const retryAll = () => {
    for (const entry of failed) {
      entry.reload?.();
    }
  };

  return { entries, failed, byCategory, retryAll };
}
