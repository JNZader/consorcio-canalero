/**
 * FichaTerritorialPanel.tsx
 *
 * Sibling floating panel to `InfoPanel` that renders the ficha territorial. It
 * is PURE presentational: the container (`MapaMapLibre`) owns the fetch via
 * `useFichaTerritorial` and threads the query state down as props (design §6).
 *
 * Four honest states (spec "Loading, error and no-coverage states"):
 *   - loading  → a spinner, never a stale previous result presented as current;
 *   - error    → the server's actionable Spanish message (404/422/429/503),
 *                not a generic failure;
 *   - result   → the identity/summary header, then a DATASET SELECTOR and the
 *                table of the selected dataset only (tables are still the
 *                contract, JD-A-012 — one at a time instead of four stacked);
 *   - the per-dataset `sin_cobertura` / low-confidence handling lives inside the
 *     dataset components.
 *
 * TABS (T3b). The body used to stack all four dataset blocks, so the panel was a
 * sheet the owner had to scroll through to reach anything, and the overlay had
 * its OWN dataset picker further down — two controls answering the same question
 * ("which dataset am I looking at?") that could disagree. There is now ONE
 * segmented control at the top of the body: it picks the visible table AND the
 * dataset the map paints. The visible table is, literally, the legend of what is
 * painted.
 */

import {
  Alert,
  Badge,
  Button,
  CloseButton,
  Divider,
  Group,
  Loader,
  SegmentedControl,
  Stack,
  Switch,
  Text,
  Title,
} from '@mantine/core';
import { type ReactNode, memo, useEffect, useState } from 'react';

import type { FichaOverlayDataset, FichaResponse, FichaTipo } from '../../lib/api/ficha';
import { FichaApiError } from '../../lib/api/ficha';
import type { BpaEnrichedFile } from '../../types/pilarVerde';
import styles from '../../styles/components/map.module.css';
import { CanalBufferControl } from './CanalBufferControl';
import { FichaResumen } from './FichaResumen';
import { fmtHa } from './fichaShared';
import { MapPanelShell } from './MapPanelShell';
import type { CanalAnalysisMode } from './useFichaInteraction';
import type { ParcelaDisplayProps } from './useMapInteractionEffects';
import { PilarVerdeBadges } from './PilarVerdeBadges';
import { PrecipChart } from './PrecipChart';
import { RiesgoBins } from './RiesgoBins';
import { SuelosBreakdown } from './SuelosBreakdown';

export interface FichaTerritorialPanelProps {
  /** Whether an area of interest is currently selected. When false, nothing renders. */
  readonly active: boolean;
  /**
   * True when the InfoPanel is open at the same time. Caps this panel's height
   * so both panels share the right-hand column instead of overlapping (see
   * `.fichaPanelCompact` in `map.module.css` for the budget derivation).
   */
  readonly compact?: boolean;
  /**
   * Narrow viewports (<= 62em): render as a bottom sheet anchored to the map's
   * bottom edge instead of a floating card (map-fluidity T2, fix 1). `compact`
   * is ignored in sheet mode — only ONE sheet is ever rendered at a time.
   */
  readonly sheet?: boolean;
  readonly tipo: FichaTipo;
  /** Clicked parcel account, for the client-side BPA join. `null` for other tipos. */
  readonly nroCuenta: string | null;
  /**
   * Display-only identity props of the clicked parcel (nro_cuenta, designación,
   * superficie, …). Rendered as a compact header above the analysis when the
   * ficha is `tipo=parcela`. `null` for non-parcel tipos or when unavailable.
   */
  readonly parcelaProps?: ParcelaDisplayProps | null;
  /**
   * Size of the multi-parcel selection (T4). Only meaningful for
   * `tipo=parcelas`, where it REPLACES the per-parcel identity header: a union of
   * N parcels has no single nomenclatura, account or designación, and showing one
   * parcel's fields next to N parcels' hectares would misattribute the analysis.
   */
  readonly parcelasCount?: number;
  /**
   * Drop parcels from the current multi-parcel selection (T4 fix round).
   *
   * The error state's recovery path for a 404 `parcela_no_encontrada`: the
   * server already names the nomenclaturas it could not resolve, and a parcel
   * that is no longer in the catastro cannot be ctrl-clicked away because it is
   * not on the map — without this, one stale parcel means rebuilding the whole
   * selection by hand. Omit it and the error state stays informative-only.
   */
  readonly onRemoveParcelas?: (nomenclaturas: readonly string[]) => void;
  readonly bpaEnriched: BpaEnrichedFile | null | undefined;
  readonly isLoading: boolean;
  /** In-flight signal incl. retry-over-cached-data (see FichaErrorAlert). */
  readonly isFetching?: boolean;
  readonly isError: boolean;
  readonly error: FichaApiError | Error | null;
  readonly data: FichaResponse | undefined;
  readonly onClose: () => void;
  /**
   * On-map overlay toggle (A(b) slice 1). When present, a "Ver recortado en el
   * mapa" switch renders once the ficha has a result; flipping it paints the
   * soils analysis clipped to the analyzed zone on the map. Optional so the
   * panel stays usable without the overlay wiring.
   */
  readonly overlayVisible?: boolean;
  readonly onToggleOverlay?: (visible: boolean) => void;
  /**
   * Selected dataset tab (T3b). It picks BOTH the table rendered in the body and
   * the dataset the overlay paints — there is no second overlay-only picker. The
   * container owns the value because it also owns the overlay query key.
   * Uncontrolled callers get the soils tab; without `onChangeTab` the selector
   * still renders but cannot move, so panels are always wired in practice.
   */
  readonly tab?: FichaPanelTab;
  readonly onChangeTab?: (tab: FichaPanelTab) => void;
  /**
   * Class labels of the SELECTED dataset that are currently hidden from the
   * painted overlay (T3b). Their table rows render dimmed with a hollow chip.
   */
  readonly hiddenClases?: readonly string[];
  /**
   * Toggles one class of the selected dataset on the map. The container both
   * flips the filter and, when the overlay is off, turns it on — clicking a
   * class is an unambiguous "show me this on the map".
   */
  readonly onToggleClase?: (clase: string) => void;
  /**
   * Canal analysis header (A6 + A7). When the analyzed tipo is `canal_buffer` or
   * `canal_cuenca` and these are wired, a header section renders at the TOP of
   * the panel (like `ParcelaIdentityHeader` for a parcel): the canal name, the
   * "Zona de influencia / Cuenca" segmented control and — in buffer mode — the
   * influence-distance input. It lives inside the card (not a separate floating
   * control) so the mode toggle stays reachable in loading and error states,
   * including the `cuenca_no_computada` 503, letting the user switch back to
   * buffer. Optional so parcel/polígono fichas render without any canal wiring.
   */
  readonly canalNombre?: string | null;
  readonly canalAnalysisMode?: CanalAnalysisMode;
  readonly onCanalAnalysisModeChange?: (mode: CanalAnalysisMode) => void;
  readonly canalBufferM?: number;
  readonly canalMaxBufferM?: number;
  readonly onCanalBufferChange?: (bufferM: number) => void;
  /**
   * Re-run the ficha query (map-fluidity T2, fix 4). Wired to the TanStack
   * `refetch` by the container. When present the error state offers a
   * "Reintentar" button for retryable failures — a 429 gates it behind a live
   * countdown derived from the server's `retry_after`. Omit it and the error
   * state stays informative-only (previous behaviour).
   */
  readonly onRetry?: () => void;
  /**
   * Overlay fetch feedback (T3a, fix 4). Flipping "Ver recortado en el mapa" used
   * to be a silent action: the request could be in flight or already failed and
   * the panel showed nothing, so a slow or broken overlay was indistinguishable
   * from "the map simply has nothing to paint here".
   */
  readonly overlayLoading?: boolean;
  readonly overlayError?: boolean;
  /**
   * Minimize-to-pill (T3a, fix 2). Owned by `MapUiPanels` because the map drives
   * it too (dragging auto-minimizes). When `onToggleMinimize` is absent the
   * affordance is not rendered at all.
   */
  readonly minimized?: boolean;
  readonly onToggleMinimize?: () => void;
  /** Opaque selection marker — a change reopens the mobile sheet at `peek`. */
  readonly resetKey?: unknown;
}

/** Human label per ficha tipo, used by the minimized pill summary. */
const TIPO_PILL_LABELS: Record<FichaTipo, string> = {
  parcela: 'Parcela',
  // Overridden with the actual count when one is known (see `fichaPillLabel`);
  // this is the fallback for a pill built before the selection size is in hand.
  parcelas: 'Parcelas',
  poligono: 'Polígono',
  canal_buffer: 'Canal',
  canal_cuenca: 'Cuenca',
};

/**
 * Summary carried by the minimized pill: WHAT is analyzed plus its size, e.g.
 * "Ficha · Parcela 116.8 ha" or "Ficha · Canal Este". A canal ficha leads with
 * the canal name because that is how the user picked it. Everything is derived
 * from props already in hand — no extra lookup, no extra fetch.
 */
export function fichaPillLabel(params: {
  tipo: FichaTipo;
  canalNombre?: string | null;
  areaHa?: number | null;
  /** Size of a multi-parcel selection (T4), so the pill reads "3 parcelas". */
  parcelasCount?: number | null;
}): string {
  const { tipo, canalNombre, areaHa, parcelasCount } = params;
  const isCanal = tipo === 'canal_buffer' || tipo === 'canal_cuenca';
  const head =
    isCanal && canalNombre
      ? canalNombre
      : // A union has no name of its own; its COUNT is what identifies it to the
        // user, and it is the one fact the pill can state before the response
        // arrives.
        tipo === 'parcelas' && typeof parcelasCount === 'number' && parcelasCount > 0
        ? `${parcelasCount} parcelas`
        : TIPO_PILL_LABELS[tipo];
  // `fmtHa` — the SAME formatter the panel body uses for every hectare figure.
  // The pill used to hand-roll a comma decimal separator, so the minimized pill
  // and the card it restores disagreed on the format of the same number.
  const size = typeof areaHa === 'number' && Number.isFinite(areaHa) ? ` ${fmtHa(areaHa)}` : '';
  return `Ficha · ${head}${size}`;
}

/**
 * Tab of the ficha body (T3b). The three raster/vector datasets are exactly the
 * `FichaOverlayDataset` values — the tab IS the overlay dataset — plus rainfall,
 * which has monthly normals instead of classes and therefore no overlay.
 */
export const FICHA_PRECIP_TAB = 'precipitacion' as const;
export type FichaPanelTab = FichaOverlayDataset | typeof FICHA_PRECIP_TAB;

/** Tabs in display order (label ⇄ value). Short labels: the strip is narrow. */
const FICHA_TAB_OPTIONS: ReadonlyArray<{
  value: FichaPanelTab;
  label: string;
}> = [
  { value: 'suelos', label: 'Suelos' },
  { value: 'flood_risk', label: 'Riesgo' },
  { value: 'drainage_need', label: 'Drenaje' },
  { value: FICHA_PRECIP_TAB, label: 'Lluvia' },
];

/** The rainfall tab has no clipped overlay to paint (monthly means, not classes). */
export function fichaTabPaintsOverlay(tab: FichaPanelTab): tab is FichaOverlayDataset {
  return tab !== FICHA_PRECIP_TAB;
}

function errorMessage(error: FichaApiError | Error | null): string {
  // The server ships an actionable Spanish `detail` for every ficha failure;
  // `FichaApiError.message` IS that detail. A bare network error has none.
  if (error instanceof FichaApiError) return error.message;
  if (error instanceof Error && error.message) return error.message;
  return 'No se pudo completar el análisis. Reintentá en unos instantes.';
}

/**
 * Failures the user cannot recover from by retrying the SAME request:
 *   - 404 → the area has no coverage;
 *   - 413 / `cuenca_demasiado_grande` → the area exceeds the analysis cap;
 *   - 422 → the geometry itself is invalid;
 *   - `cuenca_no_computada` → a deliberate 503, the batch has not produced this
 *     canal's catchment yet, so a retry hits the same wall.
 * Everything else (5xx, network, 429 after its window) is worth a retry.
 */
const NON_RETRYABLE_STATUS: ReadonlySet<number> = new Set([404, 413, 422]);
const NON_RETRYABLE_CODIGOS: ReadonlySet<string> = new Set([
  'cuenca_no_computada',
  'cuenca_demasiado_grande',
]);

function isRetryableError(error: FichaApiError | Error | null): boolean {
  if (!(error instanceof FichaApiError)) return true; // network / parse failure
  if (NON_RETRYABLE_CODIGOS.has(error.codigo)) return false;
  return !NON_RETRYABLE_STATUS.has(error.status);
}

/**
 * The nomenclaturas a 404 `parcela_no_encontrada` named, or `null`.
 *
 * The backend answers the multi-parcel 404 with the SAME codigo as the single
 * one plus a plural `nomenclaturas` list (`ficha_errors.parcelas_no_encontradas`),
 * which lands in `FichaApiError.extra`. It was already on the wire and nothing
 * read it, so the user could see WHICH parcel was stale and still had no way to
 * drop it — the parcel is gone from the catastro, so it is not on the map to
 * ctrl-click away.
 */
function parcelasFaltantes(error: FichaApiError | Error | null): string[] | null {
  if (!(error instanceof FichaApiError) || error.codigo !== 'parcela_no_encontrada') return null;
  const raw = error.extra.nomenclaturas;
  if (!Array.isArray(raw)) return null;
  const nomenclaturas = raw.filter((n): n is string => typeof n === 'string' && n.length > 0);
  return nomenclaturas.length > 0 ? nomenclaturas : null;
}

/**
 * Extra line for the vertex cap over a multi-parcel selection.
 *
 * `ficha_max_vertices` is the ceiling a real selection hits first (the count cap
 * is generous, vertex-dense rural parcels are not), and the server's message can
 * only state the limit — it does not know the selection is a union the user can
 * shrink. Naming the ONE action that helps turns a dead end into a next step.
 */
function capVerticesSugerencia(
  error: FichaApiError | Error | null,
  tipo: FichaTipo
): string | null {
  if (tipo !== 'parcelas') return null;
  if (!(error instanceof FichaApiError) || error.codigo !== 'cap_excedido') return null;
  return error.extra.cap === 'vertices'
    ? 'Deseleccioná algunas parcelas para reducir el detalle de la selección.'
    : null;
}

/**
 * Upper bound for the 429 countdown. The value comes from the server, and an
 * absurd one (a misconfigured limiter answering `retry_after: 86400`) would lock
 * the panel's only recovery path for hours with no way out but a page reload.
 * Five minutes is well past any sane rate-limit window, so clamping there costs
 * a legitimate caller nothing.
 */
const MAX_RETRY_AFTER_SECONDS = 300;

/**
 * Seconds the server asked us to wait, from the 429's `retry_after`. The field
 * is already parsed into `FichaApiError.extra` but was never surfaced. Accepts a
 * number or a numeric string; anything else (or a non-429) yields 0 → the retry
 * button is enabled immediately. Capped at `MAX_RETRY_AFTER_SECONDS`.
 */
function retryAfterSeconds(error: FichaApiError | Error | null): number {
  if (!(error instanceof FichaApiError) || error.status !== 429) return 0;
  const raw = error.extra.retry_after;
  const parsed = typeof raw === 'number' ? raw : Number(raw);
  if (!Number.isFinite(parsed) || parsed <= 0) return 0;
  return Math.min(Math.ceil(parsed), MAX_RETRY_AFTER_SECONDS);
}

/**
 * Actionable error state (map-fluidity T2, fix 4).
 *
 * TanStack never retries a client error, so before this the user's only recovery
 * was re-clicking the parcel. Now: a 429 shows a live countdown and enables
 * "Reintentar" when it reaches 0; other retryable failures offer the button
 * straight away; non-retryable ones stay informative-only.
 *
 * IN-FLIGHT FEEDBACK — deliberately NOT handled here. A retry always leaves the
 * ficha without `data`, and `query-core`'s `fetchState()` resets `status` to
 * `pending` (clearing `error`) whenever `data === undefined`. So pressing
 * "Reintentar" swaps this whole alert for the `ficha-loading` spinner in the
 * same commit: the acknowledgement is the spinner, and the button is unmounted
 * rather than merely disabled, which is what closes the double-tap window.
 */
function FichaErrorAlert({
  error,
  tipo,
  onRetry,
  onRemoveParcelas,
  isRetrying = false,
}: {
  readonly error: FichaApiError | Error | null;
  /** Tipo of the FAILED request — the multi-parcel recoveries only apply to `parcelas`. */
  readonly tipo: FichaTipo;
  readonly onRetry?: () => void;
  /** Drops the parcels the server could not resolve (see `parcelasFaltantes`). */
  readonly onRemoveParcelas?: (nomenclaturas: readonly string[]) => void;
  /**
   * In-flight signal for the CACHED-data path: when the query already holds
   * data, TanStack keeps `status: 'error'` across a refetch (it only resets to
   * pending when `data === undefined`), so this alert STAYS MOUNTED during the
   * retry. Without this flag the button reads enabled with zero feedback and
   * every extra tap cancels + re-issues the request (cancelRefetch default).
   */
  readonly isRetrying?: boolean;
}) {
  const isRateLimited = error instanceof FichaApiError && error.status === 429;
  // Lazy initial state so the first paint already shows the countdown instead of
  // a briefly-enabled button.
  const [remaining, setRemaining] = useState(() => retryAfterSeconds(error));

  // Keyed on the ERROR object, not on the parsed seconds: a second 429 carrying
  // the same `retry_after` must still re-arm the countdown. The cleanup tears
  // the interval down on unmount and on every error change, so nothing keeps
  // ticking against a dead panel.
  useEffect(() => {
    let left = retryAfterSeconds(error);
    setRemaining(left);
    if (left <= 0) return;
    const id = setInterval(() => {
      left -= 1;
      setRemaining(left);
      if (left <= 0) clearInterval(id);
    }, 1000);
    return () => clearInterval(id);
  }, [error]);

  const showRetry = !!onRetry && isRetryableError(error);
  const waiting = remaining > 0;

  // Multi-parcel recoveries. Both are actions the SERVER's message cannot offer
  // because only the client knows the failed area was a selection it can edit.
  const faltantes = tipo === 'parcelas' ? parcelasFaltantes(error) : null;
  const sugerenciaVertices = capVerticesSugerencia(error, tipo);

  return (
    <Alert
      color="red"
      variant="light"
      title={isRateLimited ? 'Demasiados pedidos' : 'No disponible'}
      data-testid="ficha-error"
    >
      <Stack gap="xs">
        <Text size="sm">{errorMessage(error)}</Text>
        {sugerenciaVertices && (
          <Text size="xs" c="dimmed" data-testid="ficha-error-vertices-hint">
            {sugerenciaVertices}
          </Text>
        )}
        {faltantes && onRemoveParcelas && (
          <Button
            size="xs"
            variant="light"
            color="red"
            onClick={() => onRemoveParcelas(faltantes)}
            data-testid="ficha-error-quitar-faltantes"
          >
            Quitar faltantes ({faltantes.length})
          </Button>
        )}
        {isRateLimited && waiting && (
          <Text size="xs" c="dimmed" data-testid="ficha-error-countdown">
            Reintentá en {remaining}s
          </Text>
        )}
        {showRetry && (
          <Button
            size="xs"
            variant="light"
            color="red"
            disabled={waiting || isRetrying}
            loading={isRetrying}
            onClick={onRetry}
            data-testid="ficha-error-retry"
          >
            {isRetrying ? 'Reintentando…' : 'Reintentar'}
          </Button>
        )}
      </Stack>
    </Alert>
  );
}

/** Field order + labels for the parcel identity header (matches the fields the
 * old InfoPanel catastro card showed, now combined into this single panel). */
const IDENTITY_FIELDS: ReadonlyArray<{
  key: keyof ParcelaDisplayProps;
  label: string;
}> = [
  { key: 'nroCuenta', label: 'Nro. cuenta' },
  { key: 'desigOficial', label: 'Designación' },
  { key: 'nomenclatura', label: 'Nomenclatura' },
  { key: 'superficieHa', label: 'Superficie (ha)' },
  { key: 'departamento', label: 'Departamento' },
  { key: 'pedania', label: 'Pedanía' },
  { key: 'tipoParcela', label: 'Tipo' },
];

/** Compact identity header for a clicked parcel — one badge+value row per
 * present field. Renders nothing when no whitelisted field has a value. */
function ParcelaIdentityHeader({ props }: { readonly props: ParcelaDisplayProps }) {
  const rows = IDENTITY_FIELDS.filter(({ key }) => props[key]);
  if (rows.length === 0) return null;
  return (
    <Stack gap={2} mb="xs" data-testid="ficha-parcela-header">
      {rows.map(({ key, label }) => (
        <Group key={key} gap="xs" wrap="nowrap">
          <Badge size="xs" variant="light" color="gray">
            {label}
          </Badge>
          <Text size="xs" truncate>
            {props[key]}
          </Text>
        </Group>
      ))}
    </Stack>
  );
}

function PanelBody({
  tipo,
  nroCuenta,
  bpaEnriched,
  isLoading,
  isFetching,
  isError,
  error,
  data,
  onRetry,
  onRemoveParcelas,
  tab = 'suelos',
  onChangeTab,
  hiddenClases,
  onToggleClase,
  overlayControls,
}: Omit<FichaTerritorialPanelProps, 'active' | 'onClose' | 'parcelaProps'> & {
  /**
   * Overlay switch + feedback, built by the panel and injected here so it sits
   * directly under the selector that drives it instead of at the bottom of the
   * body, half a scroll away from the table it paints.
   */
  readonly overlayControls?: ReactNode;
}) {
  if (isLoading) {
    return (
      <Group gap="xs" data-testid="ficha-loading">
        <Loader size="sm" />
        <Text size="sm" c="dimmed">
          Analizando la zona…
        </Text>
      </Group>
    );
  }

  if (isError || !data) {
    return (
      <FichaErrorAlert
        error={error ?? null}
        tipo={tipo}
        onRetry={onRetry}
        onRemoveParcelas={onRemoveParcelas}
        isRetrying={isFetching}
      />
    );
  }

  return (
    <Stack gap="sm" data-testid="ficha-result">
      {/* Fixed header: WHAT was analyzed. It never scrolls out from under the
			    selector, so the numbers below always have their context. */}
      <FichaResumen ficha={data} />
      <PilarVerdeBadges tipo={tipo} nroCuenta={nroCuenta} bpaEnriched={bpaEnriched} compact />
      <Divider />
      <SegmentedControl
        size="xs"
        fullWidth
        value={tab}
        onChange={(value) => onChangeTab?.(value as FichaPanelTab)}
        data={FICHA_TAB_OPTIONS as unknown as { value: string; label: string }[]}
        data-testid="ficha-dataset-tabs"
        aria-label="Conjunto de datos"
      />
      {overlayControls}
      <Divider />
      {tab === 'suelos' && (
        <SuelosBreakdown
          dataset={data.suelos}
          hiddenClases={hiddenClases}
          onToggleClase={onToggleClase}
        />
      )}
      {tab === 'flood_risk' && (
        <RiesgoBins
          label="Riesgo de inundación"
          dataset={data.flood_risk}
          legendKey="flood_risk"
          testId="ficha-flood-risk"
          hiddenClases={hiddenClases}
          onToggleClase={onToggleClase}
        />
      )}
      {tab === 'drainage_need' && (
        <RiesgoBins
          label="Necesidad de drenaje"
          dataset={data.drainage_need}
          legendKey="drainage_need"
          testId="ficha-drainage-need"
          hiddenClases={hiddenClases}
          onToggleClase={onToggleClase}
        />
      )}
      {/* Rainfall is a 12-month series, not a class partition: nothing to
			    toggle and nothing to clip on the map. */}
      {tab === FICHA_PRECIP_TAB && <PrecipChart dataset={data.precipitacion_mensual} />}
    </Stack>
  );
}

export const FichaTerritorialPanel = memo(function FichaTerritorialPanel({
  active,
  compact = false,
  sheet = false,
  tipo,
  nroCuenta,
  parcelaProps,
  parcelasCount,
  onRemoveParcelas,
  bpaEnriched,
  isLoading,
  isFetching,
  isError,
  error,
  data,
  onClose,
  overlayVisible,
  onToggleOverlay,
  tab = 'suelos',
  onChangeTab,
  hiddenClases,
  onToggleClase,
  canalNombre,
  canalAnalysisMode = 'buffer',
  onCanalAnalysisModeChange,
  canalBufferM,
  canalMaxBufferM,
  onCanalBufferChange,
  onRetry,
  overlayLoading = false,
  overlayError = false,
  minimized = false,
  onToggleMinimize,
  resetKey,
}: FichaTerritorialPanelProps) {
  if (!active) return null;

  // The overlay toggle only makes sense once there is a result to clip on the
  // map, and only when the container wired the handler in.
  //
  // LLUVIA TAB (T3b) — the toggle is HIDDEN, not disabled. There is no rainfall
  // overlay to paint, so a disabled switch would be a control the user has to
  // reason about ("why can't I?") in the tightest strip of the panel. Hiding it
  // says the same thing in zero pixels, and the user's ON/OFF intent is kept by
  // the container: switching back to a dataset tab repaints exactly as before.
  const showOverlayToggle =
    !!onToggleOverlay && !isLoading && !isError && !!data && fichaTabPaintsOverlay(tab);

  // Identity header (bug-3 combine): a clicked parcel's account/identity fields
  // sit at the top of this single panel, replacing the old InfoPanel catastro
  // card. Only for `tipo=parcela`; other tipos (poligono/canal) have no parcel.
  const showParcelaHeader = tipo === 'parcela' && !!parcelaProps;

  // T4 — a multi-parcel selection gets a COUNT header instead. It states the two
  // things that are true of a union ("N parcelas" and its hectares) and none of
  // the things that are not (one parcel's nomenclatura, account or designación).
  const showParcelasHeader = tipo === 'parcelas' && !!parcelasCount;

  // Canal analysis header (A6 + A7): the influence-strip vs catchment control now
  // lives inside this panel instead of a separate floating card. Rendered above
  // the analysis body for canal tipos so the toggle stays reachable while the
  // ficha is loading or erroring (e.g. `cuenca_no_computada`). The full prop set
  // is asserted inline in the JSX so TypeScript narrows the optional handlers.
  const isCanalTipo = tipo === 'canal_buffer' || tipo === 'canal_cuenca';

  // Built here (the panel owns the overlay props) and injected into the body so
  // it renders immediately under the selector that decides WHAT gets painted.
  const overlayControls = showOverlayToggle ? (
    <>
      <Group gap="xs" wrap="nowrap">
        <Switch
          size="xs"
          checked={!!overlayVisible}
          onChange={(event) => onToggleOverlay?.(event.currentTarget.checked)}
          label="Ver recortado en el mapa"
          data-testid="ficha-overlay-toggle"
        />
        {/* T3a, fix 4 — the overlay fetch used to be silent. No retry
				    button: toggling the switch off and on refetches. */}
        {overlayVisible && overlayLoading && (
          <Loader size="xs" data-testid="ficha-overlay-loading" />
        )}
      </Group>
      {overlayVisible && overlayError && !overlayLoading && (
        <Text size="xs" c="red" data-testid="ficha-overlay-error">
          No se pudo pintar el recorte
        </Text>
      )}
    </>
  ) : null;

  return (
    <MapPanelShell
      sheet={sheet}
      floatingClassName={
        compact ? `${styles.fichaPanel} ${styles.fichaPanelCompact}` : styles.fichaPanel
      }
      testId="ficha-territorial-panel"
      sheetLabel="ficha territorial"
      onClose={onClose}
      closeLabel="Cerrar ficha territorial"
      minimized={minimized}
      onToggleMinimize={onToggleMinimize}
      pillLabel={fichaPillLabel({
        tipo,
        canalNombre,
        areaHa: data?.area_ha ?? null,
        parcelasCount,
      })}
      pillClassName={styles.fichaPanelPill}
      resetKey={resetKey}
    >
      {/* In sheet mode the close button lives in the shell's PINNED header, so
          it stays reachable on a tall ficha; rendering it here too would
          duplicate the affordance. */}
      <Group justify="space-between" mb="xs">
        <Title order={5}>Ficha territorial</Title>
        {!sheet && (
          <CloseButton onClick={onClose} size="sm" aria-label="Cerrar ficha territorial" />
        )}
      </Group>
      <Divider mb="xs" />
      {isCanalTipo &&
        canalNombre &&
        onCanalAnalysisModeChange &&
        onCanalBufferChange &&
        typeof canalBufferM === 'number' &&
        typeof canalMaxBufferM === 'number' && (
          <>
            <CanalBufferControl
              canalNombre={canalNombre}
              analysisMode={canalAnalysisMode}
              onAnalysisModeChange={onCanalAnalysisModeChange}
              bufferM={canalBufferM}
              maxBufferM={canalMaxBufferM}
              onBufferChange={onCanalBufferChange}
            />
            <Divider my="xs" />
          </>
        )}
      {showParcelasHeader && (
        <>
          <Text size="xs" fw={600} data-testid="ficha-parcelas-header">
            {parcelasCount} parcelas
            {typeof data?.area_ha === 'number' ? ` · ${fmtHa(data.area_ha)}` : ''}
          </Text>
          <Divider my="xs" />
        </>
      )}
      {showParcelaHeader && parcelaProps && (
        <>
          <ParcelaIdentityHeader props={parcelaProps} />
          <Divider mb="xs" />
        </>
      )}
      <PanelBody
        tipo={tipo}
        onRemoveParcelas={onRemoveParcelas}
        nroCuenta={nroCuenta}
        bpaEnriched={bpaEnriched}
        isLoading={isLoading}
        isFetching={isFetching}
        isError={isError}
        error={error}
        data={data}
        onRetry={onRetry}
        tab={tab}
        onChangeTab={onChangeTab}
        hiddenClases={hiddenClases}
        onToggleClase={onToggleClase}
        overlayControls={overlayControls}
      />
    </MapPanelShell>
  );
});
