/**
 * Martin MVT layer utilities for MapLibre GL.
 *
 * Martin auto-publishes all PostGIS tables with geometry columns as MVT.
 */

const MARTIN_URL = import.meta.env.VITE_MARTIN_URL || 'http://localhost:3000';

// ─── Source definitions ──────────────────────────────────────────────────────

/** Paint properties for a Martin MVT source (used for MapLibre GL rendering). */
export interface MartinSourceStyle {
  /** Stroke / circle stroke color */
  color: string;
  /** Fill / circle fill color */
  fillColor: string;
  /** Fill opacity (0–1) */
  fillOpacity: number;
  /** Line or circle stroke width */
  weight: number;
  /** Line or circle stroke opacity (0–1) */
  opacity: number;
  /** Circle radius in pixels (point layers only) */
  radius?: number;
}

export interface MartinSource {
  /** Martin table/view name — must match what's auto-published */
  table: string;
  label: string;
  defaultVisible: boolean;
  /** Paint properties for this source */
  style: MartinSourceStyle;
}

export const MARTIN_SOURCES: Record<string, MartinSource> = {
  puntos_conflicto: {
    table: 'puntos_conflicto',
    label: 'Puntos de Conflicto',
    defaultVisible: false,
    style: {
      color: '#b91c1c',
      fillColor: '#ef4444',
      fillOpacity: 0.85,
      weight: 1,
      opacity: 1,
      radius: 5,
    },
  },
};

/** Build a Martin MVT tile URL template for a given table name. */
export function getMartinTileUrl(table: string): string {
  return `${MARTIN_URL}/${table}/{z}/{x}/{y}`;
}
