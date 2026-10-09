import { MAP_PRESET_IDS, type MapPresetId } from './mapPresets';

export interface MapPermalink {
  lat?: number;
  lng?: number;
  zoom?: number;
  preset?: MapPresetId;
  /** Catalog ids to turn on. `[]` means all off (`l=none`). Omit = do not apply. */
  layers?: string[];
  rasterTipo?: string;
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

  setOrDelete('lat', next.lat !== undefined ? next.lat.toFixed(5) : undefined);
  setOrDelete('lng', next.lng !== undefined ? next.lng.toFixed(5) : undefined);
  setOrDelete('zoom', next.zoom !== undefined ? next.zoom.toFixed(2) : undefined);
  setOrDelete('preset', next.preset);

  if (next.layers === undefined) {
    params.delete('l');
  } else if (next.layers.length === 0) {
    params.set('l', 'none');
  } else {
    params.set('l', next.layers.filter((id) => catalog.has(id)).join(','));
  }

  setOrDelete('r', next.rasterTipo);

  const qs = params.toString();
  return qs ? `?${qs}` : '';
}
