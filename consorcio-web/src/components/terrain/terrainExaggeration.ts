export interface TerrainExaggerationPreset {
  readonly value: number;
  readonly label: string;
  readonly tooltip: string;
}

/** UX PDF T2 — ETH/Esri ranges; ×200 stays the pampa default. */
export const TERRAIN_EXAGGERATION_PRESETS: readonly TerrainExaggerationPreset[] = [
  { value: 1, label: '×1', tooltip: 'Altura real. Sin distorsión.' },
  { value: 20, label: '×20', tooltip: 'Relieve visible en terreno suave.' },
  { value: 50, label: '×50', tooltip: 'Pampa: líneas de escurrimiento, sin “lomas” falsas.' },
  { value: 100, label: '×100', tooltip: 'Globo de relieve. Distorsiona la forma.' },
  { value: 200, label: '×200', tooltip: 'Máximo. Sirve para ver escurrimiento; no son lomas reales.' },
];

export function exaggerationCanvasLabel(value: number): string {
  return `Relieve exagerado ×${value}`;
}
