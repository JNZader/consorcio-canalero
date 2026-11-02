import type { Feature } from 'geojson';
import { MAP_PRESET_IDS, type MapPresetId } from './mapPresets';

/** Stable token for the feature the operator is reading, when one exists. */
export function selectionPermalinkToken(feature: Feature | null | undefined): string | undefined {
  if (!feature) return undefined;
  const props = (feature.properties ?? {}) as Record<string, unknown>;
  const cuenta = props.nro_cuenta ?? props.Nro_Cuenta ?? props.cuenta;
  if (typeof cuenta === 'string' && /^[\w./-]{1,40}$/.test(cuenta.trim())) {
    return `cuenta:${cuenta.trim()}`;
  }
  if (typeof cuenta === 'number' && Number.isFinite(cuenta)) return `cuenta:${cuenta}`;
  const id = props.id;
  const layer = (feature as Feature & { layer?: { id?: string } }).layer?.id ?? '';
  if (typeof id === 'string' && /^[a-z0-9-]{1,80}$/.test(id) && layer.includes('canal')) {
    return `canal:${id}`;
  }
  if (typeof id === 'string' && /^[a-z0-9-]{1,80}$/.test(id)) return `canal:${id}`;
  return undefined;
}

export interface MapPermalink {
  lat?: number;
  lng?: number;
  zoom?: number;
  preset?: MapPresetId;
  /** Catalog ids to turn on. `[]` means all off (`l=none`). Omit = do not apply. */
  layers?: string[];
  rasterTipo?: string;
  /** Canal slug whose elevation profile should open. Omit = do not change. */
  perfil?: string;
  /** `canal:<slug>` or `cuenta:<nro>`. Omit = do not change the selection. */
  sel?: string;
}

const PRESET_SET = new Set<string>(MAP_PRESET_IDS);

export function parseMapPermalink(search: string): MapPermalink {
  const raw = search.startsWith('?') ? search.slice(1) : search;
  const params = new URLSearchParams(raw);
  const out: MapPermalink = {};

  const lat = Number.parseFloat(params.get('lat') ?? '');
  const lng = Number.parseFloat(params.get('lng') ?? '');
  const zoom = Number.parseFloat(params.get('zoom') ?? '');
  if (Number.isFinite(lat) && lat >= -90 && lat <= 90) out.lat = lat;
  if (Number.isFinite(lng) && lng >= -180 && lng <= 180) out.lng = lng;
  if (Number.isFinite(zoom) && zoom > 0 && zoom <= 24) out.zoom = zoom;

  const preset = params.get('preset');
  if (preset && PRESET_SET.has(preset)) out.preset = preset as MapPresetId;

  const layersRaw = params.get('l');
  if (layersRaw === 'none') out.layers = [];
  else if (layersRaw !== null && layersRaw.length > 0) {
    out.layers = layersRaw
      .split(',')
      .map((id) => id.trim())
      .filter((id) => id.length > 0 && !id.startsWith('canal_'));
  }

  const rasterTipo = params.get('r');
  if (rasterTipo) out.rasterTipo = rasterTipo;

  const perfil = params.get('perfil');
  if (perfil && /^[a-z0-9-]{1,80}$/.test(perfil)) out.perfil = perfil;

  const sel = params.get('sel');
  if (sel && /^(canal:[a-z0-9-]{1,80}|cuenta:[\w./-]{1,40})$/.test(sel)) out.sel = sel;

  return out;
}

export function serializeMapPermalink(
  currentSearch: string,
  next: MapPermalink,
  catalogIds: readonly string[]
): string {
  const raw = currentSearch.startsWith('?') ? currentSearch.slice(1) : currentSearch;
  const params = new URLSearchParams(raw);
  const catalog = new Set(catalogIds);

  const setOrDelete = (key: string, value: string | undefined) => {
    if (value === undefined || value === '') params.delete(key);
    else params.set(key, value);
  };

  // UX-03: camera lives in `#v=`. Drop leftover query camera keys.
  params.delete('lat');
  params.delete('lng');
  params.delete('zoom');
  setOrDelete('preset', next.preset);

  if (next.layers === undefined) {
    params.delete('l');
  } else if (next.layers.length === 0) {
    params.set('l', 'none');
  } else {
    params.set('l', next.layers.filter((id) => catalog.has(id)).join(','));
  }

  setOrDelete('r', next.rasterTipo);
  setOrDelete('perfil', next.perfil);
  setOrDelete('sel', next.sel);

  const qs = params.toString();
  return qs ? `?${qs}` : '';
}
