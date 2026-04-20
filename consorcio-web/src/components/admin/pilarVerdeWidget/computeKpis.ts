/**
 * computeKpis.ts
 *
 * PURE helpers that project `aggregates.json` slices into widget-ready KPI
 * objects. No React, no I/O, no globals — ideal Stryker target (≥85%).
 *
 * Why separate helpers:
 *   - The widget stays a thin layout shell (layout + `fmt()` calls).
 *   - Tests read from the pinned fixture directly, no RTL needed for logic.
 *   - Future AI / PDF consumers of the same aggregates can reuse these.
 *
 * Null-safe by design:
 *   - Every helper accepts `null | undefined` and returns a "sentinel shape"
 *     where numeric fields are `null` (never NaN). The caller passes the sentinel
 *     through `fmt()` which renders "—".
 *
 * @see spec `sdd/pilar-verde-bpa-agroforestal/spec` § "AdminDashboard Pilar Verde Widget"
 * @see design `sdd/pilar-verde-bpa-agroforestal/design` § 5 AdminDashboard Widget
 */

import type {
  AggregatesBpa,
  AggregatesLeyForestal,
  BpaYear,
} from '../../../types/pilarVerde';

// ---------------------------------------------------------------------------
// Shared types
// ---------------------------------------------------------------------------

/** A (count, hectares) pair used by the two-track ley_forestal card. */
export interface KpiPair {
  readonly parcelas: number | null;
  readonly superficie_ha: number | null;
}

// ---------------------------------------------------------------------------
// computeLeyForestalKpis
// ---------------------------------------------------------------------------

export interface LeyForestalKpis {
  readonly cumplen: KpiPair;
  readonly noCumplen: KpiPair;
  readonly pctParcelas: number | null;
  readonly pctSuperficie: number | null;
}

const EMPTY_PAIR: KpiPair = { parcelas: null, superficie_ha: null };

const EMPTY_LEY_FORESTAL: LeyForestalKpis = {
  cumplen: EMPTY_PAIR,
  noCumplen: EMPTY_PAIR,
  pctParcelas: null,
  pctSuperficie: null,
};

export function computeLeyForestalKpis(
  slice: AggregatesLeyForestal | null | undefined
): LeyForestalKpis {
  if (!slice) return EMPTY_LEY_FORESTAL;
  return {
    cumplen: {
      parcelas: slice.aceptada_count,
      superficie_ha: slice.aceptada_superficie_ha,
    },
    noCumplen: {
      parcelas: slice.presentada_count,
      superficie_ha: slice.presentada_superficie_ha,
    },
    pctParcelas: slice.cumplimiento_pct_parcelas,
    pctSuperficie: slice.cumplimiento_pct_superficie,
  };
}

// ---------------------------------------------------------------------------
// computeBpaKpis
// ---------------------------------------------------------------------------

export interface BpaKpis {
  readonly activas: number | null;
  readonly superficieHa: number | null;
}

const EMPTY_BPA: BpaKpis = {
  activas: null,
  superficieHa: null,
};

export function computeBpaKpis(slice: AggregatesBpa | null | undefined): BpaKpis {
  if (!slice) return EMPTY_BPA;
  return {
    activas: slice.explotaciones_activas,
    superficieHa: slice.superficie_total_ha,
  };
}

// ---------------------------------------------------------------------------
// computeHistoricalKpis
// ---------------------------------------------------------------------------

/** Evolucion entry — year literal + count. */
export interface EvolucionEntry {
  readonly year: BpaYear;
  readonly count: number;
}

export interface HistoricalKpis {
  readonly historicaCount: number | null;
  readonly historicaPct: number | null;
  readonly abandonaronCount: number | null;
  readonly abandonaronPct: number | null;
  readonly nuncaCount: number | null;
  readonly evolucion: readonly EvolucionEntry[];
}

const EMPTY_HISTORICAL: HistoricalKpis = {
  historicaCount: null,
  historicaPct: null,
  abandonaronCount: null,
  abandonaronPct: null,
  nuncaCount: null,
  evolucion: [],
};

const EVOLUCION_YEARS: readonly BpaYear[] = [
  '2019',
  '2020',
  '2021',
  '2022',
  '2023',
  '2024',
  '2025',
];

export function computeHistoricalKpis(slice: AggregatesBpa | null | undefined): HistoricalKpis {
  if (!slice) return EMPTY_HISTORICAL;
  const evolucion: EvolucionEntry[] = EVOLUCION_YEARS.map((year) => ({
    year,
    count: slice.evolucion_anual[year] ?? 0,
  }));
  return {
    historicaCount: slice.cobertura_historica_count,
    historicaPct: slice.cobertura_historica_pct,
    abandonaronCount: slice.abandonaron_count,
    abandonaronPct: slice.abandonaron_pct,
    nuncaCount: slice.nunca_count,
    evolucion,
  };
}

