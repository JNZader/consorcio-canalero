export interface TerrainExaggerationPreset {
  readonly value: number;
  readonly label: string;
  readonly tooltip: string;
}

/** Audit v5 3D-02 — pampa first impression; ×200 remains a preset, not the default. */
export const TERRAIN_DEFAULT_EXAGGERATION = 20;

const TERRAIN_DEFAULT_PITCH = 60;
const TERRAIN_INHERITED_PITCH_MIN = 5;

/** Audit v5 3D-01 — 2D publishes pitch 0; treat nadir as "no 3D camera". */
export function resolveTerrainStartPitch(pitch: number | undefined): number {
  return pitch !== undefined && pitch > TERRAIN_INHERITED_PITCH_MIN ? pitch : TERRAIN_DEFAULT_PITCH;
}

/** UX PDF T2 — ETH/Esri ranges. */
export const TERRAIN_EXAGGERATION_PRESETS: readonly TerrainExaggerationPreset[] = [
  { value: 1, label: '×1', tooltip: 'Altura real. Sin distorsión.' },
  { value: 20, label: '×20', tooltip: 'Relieve visible en terreno suave.' },
  { value: 50, label: '×50', tooltip: 'Pampa: líneas de escurrimiento, sin “lomas” falsas.' },
  { value: 100, label: '×100', tooltip: 'Globo de relieve. Distorsiona la forma.' },
  { value: 200, label: '×200', tooltip: 'Máximo. Sirve para ver escurrimiento; no son lomas reales.' },
];

export function formatExaggerationMultiplier(value: number): string {
  return `×${value}`;
}

export function exaggerationCanvasLabel(value: number): string {
  return `Relieve exagerado ${formatExaggerationMultiplier(value)}`;
}
