/**
 * Layer provenance registry (Batch 1 — "datos honestos").
 *
 * Mirror of `layerAttributions.ts`, one level deeper: attributions answer WHO
 * produced the data, provenance answers WHEN. The panel renders one dimmed line
 * ("Datos al 20/4/2026") at the foot of a family's accordion panel — zero
 * pixels over the canvas.
 *
 * ONLY TWO FAMILIES ARE LISTED, ON PURPOSE:
 *   - `canales`     → `index.json:generated_at` (one ETL run covers relevados
 *                     AND propuestas, so a single date is honest for both);
 *   - `pilar_verde` → `aggregates.json:generated_at` (eager group, always there
 *                     once the family is visible).
 * Hidrografía, cuencas, suelos and catastro ship NO real `generated_at`.
 * Inventing or approximating one would be exactly the dishonesty this batch
 * exists to remove — a wrong date is worse than no date. Escuelas is left out
 * until its `metadata.generated_at` is actually typed (follow-up).
 */

import { formatDate } from '../../lib/formatters';
import type { LayerCategory } from './map2dDerived';
import { LAYER_CATEGORY } from './map2dDerived';

export interface LayerProvenanceInputs {
  /** `useCanales().index?.generated_at` — ISO 8601. */
  readonly canalesGeneratedAt?: string | null;
  /** `usePilarVerde().data?.aggregates?.generated_at` — ISO 8601. */
  readonly pilarVerdeGeneratedAt?: string | null;
}

/** Prefix of every provenance line. Kept here so the copy has one home. */
export const PROVENANCE_PREFIX = 'Datos al';

/**
 * `formatDate` already returns its fallback (`'-'`) for a missing or
 * unparseable date; we treat that as "no honest date" and omit the key rather
 * than render "Datos al -".
 */
function provenanceLine(iso: string | null | undefined): string | null {
  if (!iso) return null;
  const formatted = formatDate(iso, { format: 'short' });
  if (formatted === '-') return null;
  return `${PROVENANCE_PREFIX} ${formatted}`;
}

export function buildLayerProvenance(
  inputs: LayerProvenanceInputs = {}
): Partial<Record<LayerCategory, string>> {
  const out: Partial<Record<LayerCategory, string>> = {};

  const canales = provenanceLine(inputs.canalesGeneratedAt);
  if (canales) out[LAYER_CATEGORY.CANALES] = canales;

  const pilarVerde = provenanceLine(inputs.pilarVerdeGeneratedAt);
  if (pilarVerde) out[LAYER_CATEGORY.PILAR_VERDE] = pilarVerde;

  return out;
}
