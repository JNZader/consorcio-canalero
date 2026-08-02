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
 *   - result   → one table per dataset (tables are the contract, JD-A-012),
 *                plus the monthly precipitation chart + table (`PrecipChart`);
 *   - the per-dataset `sin_cobertura` / low-confidence handling lives inside the
 *     dataset components.
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
import { memo, useEffect, useState } from 'react';

import type { FichaOverlayDataset, FichaResponse, FichaTipo } from '../../lib/api/ficha';
import { FichaApiError } from '../../lib/api/ficha';
import type { BpaEnrichedFile } from '../../types/pilarVerde';
import styles from '../../styles/components/map.module.css';
import { CanalBufferControl } from './CanalBufferControl';
import { FichaResumen } from './FichaResumen';
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
   * Which dataset the overlay paints, clipped, one at a time. When the toggle is
   * on a segmented control lets the user switch between soils, flood risk and
   * drainage need; switching refetches + repaints. Optional, defaults to soils.
   */
  readonly overlayDataset?: FichaOverlayDataset;
  readonly onChangeOverlayDataset?: (dataset: FichaOverlayDataset) => void;
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
}

/** Overlay dataset options for the picker (label ⇄ wire value). */
const OVERLAY_DATASET_OPTIONS: ReadonlyArray<{
  value: FichaOverlayDataset;
  label: string;
}> = [
  { value: 'suelos', label: 'Suelos' },
  { value: 'flood_risk', label: 'Riesgo hídrico' },
  { value: 'drainage_need', label: 'Necesidad de drenaje' },
];

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
  onRetry,
  isRetrying = false,
}: {
  readonly error: FichaApiError | Error | null;
  readonly onRetry?: () => void;
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

  return (
    <Alert
      color="red"
      variant="light"
      title={isRateLimited ? 'Demasiados pedidos' : 'No disponible'}
      data-testid="ficha-error"
    >
      <Stack gap="xs">
        <Text size="sm">{errorMessage(error)}</Text>
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
}: Omit<FichaTerritorialPanelProps, 'active' | 'onClose' | 'parcelaProps'>) {
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
    return <FichaErrorAlert error={error ?? null} onRetry={onRetry} isRetrying={isFetching} />;
  }

  return (
    <Stack gap="sm" data-testid="ficha-result">
      <FichaResumen ficha={data} />
      <Divider />
      <SuelosBreakdown dataset={data.suelos} />
      <Divider />
      <RiesgoBins
        label="Riesgo de inundación"
        dataset={data.flood_risk}
        testId="ficha-flood-risk"
      />
      <Divider />
      <RiesgoBins
        label="Necesidad de drenaje"
        dataset={data.drainage_need}
        testId="ficha-drainage-need"
      />
      <Divider />
      <PrecipChart dataset={data.precipitacion_mensual} />
      <Divider />
      <PilarVerdeBadges tipo={tipo} nroCuenta={nroCuenta} bpaEnriched={bpaEnriched} />
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
  bpaEnriched,
  isLoading,
  isFetching,
  isError,
  error,
  data,
  onClose,
  overlayVisible,
  onToggleOverlay,
  overlayDataset = 'suelos',
  onChangeOverlayDataset,
  canalNombre,
  canalAnalysisMode = 'buffer',
  onCanalAnalysisModeChange,
  canalBufferM,
  canalMaxBufferM,
  onCanalBufferChange,
  onRetry,
}: FichaTerritorialPanelProps) {
  if (!active) return null;

  // The overlay toggle only makes sense once there is a result to clip on the
  // map, and only when the container wired the handler in.
  const showOverlayToggle = !!onToggleOverlay && !isLoading && !isError && !!data;

  // Identity header (bug-3 combine): a clicked parcel's account/identity fields
  // sit at the top of this single panel, replacing the old InfoPanel catastro
  // card. Only for `tipo=parcela`; other tipos (poligono/canal) have no parcel.
  const showParcelaHeader = tipo === 'parcela' && !!parcelaProps;

  // Canal analysis header (A6 + A7): the influence-strip vs catchment control now
  // lives inside this panel instead of a separate floating card. Rendered above
  // the analysis body for canal tipos so the toggle stays reachable while the
  // ficha is loading or erroring (e.g. `cuenca_no_computada`). The full prop set
  // is asserted inline in the JSX so TypeScript narrows the optional handlers.
  const isCanalTipo = tipo === 'canal_buffer' || tipo === 'canal_cuenca';

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
      {showParcelaHeader && parcelaProps && (
        <>
          <ParcelaIdentityHeader props={parcelaProps} />
          <Divider mb="xs" />
        </>
      )}
      <PanelBody
        tipo={tipo}
        nroCuenta={nroCuenta}
        bpaEnriched={bpaEnriched}
        isLoading={isLoading}
        isFetching={isFetching}
        isError={isError}
        error={error}
        data={data}
        onRetry={onRetry}
      />
      {showOverlayToggle && (
        <>
          <Divider my="xs" />
          <Switch
            size="xs"
            checked={!!overlayVisible}
            onChange={(event) => onToggleOverlay?.(event.currentTarget.checked)}
            label="Ver recortado en el mapa"
            data-testid="ficha-overlay-toggle"
          />
          {overlayVisible && onChangeOverlayDataset && (
            <SegmentedControl
              size="xs"
              fullWidth
              mt="xs"
              value={overlayDataset}
              onChange={(value) => onChangeOverlayDataset(value as FichaOverlayDataset)}
              data={
                OVERLAY_DATASET_OPTIONS as unknown as {
                  value: string;
                  label: string;
                }[]
              }
              data-testid="ficha-overlay-dataset"
            />
          )}
        </>
      )}
    </MapPanelShell>
  );
});
