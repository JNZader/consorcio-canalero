import { srPaFeatureId } from './aprhiSrPa';

export const CANAL_HIT_LAYER = {
  KMZ: 'kmz',
  SR_PA: 'sr_pa',
  EXISTENTES: 'existentes',
} as const;

export type CanalHitLayer = (typeof CANAL_HIT_LAYER)[keyof typeof CANAL_HIT_LAYER];

export const ADMIN_CANAL_LINE_LAYER_ID = {
  KMZ: 'pub-cons-line',
  SR_PA: 'pub-aprhi-sr-line',
  EXISTENTES: 'pub-existentes-line',
} as const;

export const OVERLAP_CLICK_PAD_PX = 8;
export const OVERLAP_OFFSET_PX = 8;
export const OVERLAY_DIM_OPACITY = 0.45;

export interface CanalHit {
  readonly id: string;
  readonly layer: CanalHitLayer;
  readonly label: string;
}

export interface CanalHitFeature {
  readonly layerId: string;
  readonly properties: Record<string, unknown> | null;
}

export interface ClickPoint {
  readonly x: number;
  readonly y: number;
}

const LAYER_BY_ADMIN_ID: Record<string, CanalHitLayer> = {
  [ADMIN_CANAL_LINE_LAYER_ID.KMZ]: CANAL_HIT_LAYER.KMZ,
  [ADMIN_CANAL_LINE_LAYER_ID.SR_PA]: CANAL_HIT_LAYER.SR_PA,
  [ADMIN_CANAL_LINE_LAYER_ID.EXISTENTES]: CANAL_HIT_LAYER.EXISTENTES,
};

function readString(value: unknown): string {
  return typeof value === 'string' ? value.trim() : '';
}

function readLabelPart(value: unknown): string {
  if (typeof value === 'string') return value.trim();
  if (typeof value === 'number' && Number.isFinite(value)) return String(value);
  return '';
}

export function kmzGroupVisible(showRelevados: boolean, showPropuestas: boolean): boolean {
  return showRelevados || showPropuestas;
}

export function overlayLineOffsetPx(layer: CanalHitLayer, kmzVisible: boolean): number {
  if (!kmzVisible || layer === CANAL_HIT_LAYER.KMZ) return 0;
  if (layer === CANAL_HIT_LAYER.SR_PA) return -OVERLAP_OFFSET_PX;
  return OVERLAP_OFFSET_PX;
}

export function overlayLineOpacity(kmzVisible: boolean, selected: boolean): number {
  if (selected) return 1;
  if (kmzVisible) return OVERLAY_DIM_OPACITY;
  return 0.9;
}

export function overlayLabelsVisible(overlayOn: boolean, kmzVisible: boolean): boolean {
  return overlayOn && !kmzVisible;
}

export function clickBbox(
  point: ClickPoint,
  pad = OVERLAP_CLICK_PAD_PX
): [[number, number], [number, number]] {
  return [
    [point.x - pad, point.y - pad],
    [point.x + pad, point.y + pad],
  ];
}

function hitFromFeature(feature: CanalHitFeature): CanalHit | null {
  const layer = LAYER_BY_ADMIN_ID[feature.layerId];
  if (!layer) return null;
  const properties = feature.properties ?? {};
  if (layer === CANAL_HIT_LAYER.SR_PA) {
    const id = readString(properties.list_id) || srPaFeatureId(properties);
    if (!id) return null;
    const label =
      [readLabelPart(properties.Identificador), readLabelPart(properties.Nombre_Obra)]
        .filter(Boolean)
        .join(' · ') || id;
    return { id, layer, label };
  }
  const id = readString(properties.id);
  if (!id) return null;
  return { id, layer, label: readString(properties.nombre_publico) || id };
}

export function collectCanalHits(features: CanalHitFeature[]): CanalHit[] {
  const seen = new Set<string>();
  const hits: CanalHit[] = [];
  for (const feature of features) {
    const hit = hitFromFeature(feature);
    if (!hit || seen.has(hit.id)) continue;
    seen.add(hit.id);
    hits.push(hit);
  }
  return hits;
}

export function pickDefaultHit(hits: readonly CanalHit[]): CanalHit | null {
  return (
    hits.find((hit) => hit.layer === CANAL_HIT_LAYER.KMZ) ??
    hits.find((hit) => hit.layer === CANAL_HIT_LAYER.SR_PA) ??
    hits[0] ??
    null
  );
}
