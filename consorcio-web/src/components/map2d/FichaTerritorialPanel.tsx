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
  CloseButton,
  Divider,
  Group,
  Loader,
  Paper,
  Stack,
  Switch,
  Text,
  Title,
} from '@mantine/core';
import { memo } from 'react';

import type { FichaResponse, FichaTipo } from '../../lib/api/ficha';
import { FichaApiError } from '../../lib/api/ficha';
import type { BpaEnrichedFile } from '../../types/pilarVerde';
import styles from '../../styles/components/map.module.css';
import { FichaResumen } from './FichaResumen';
import type { ParcelaDisplayProps } from './useMapInteractionEffects';
import { PilarVerdeBadges } from './PilarVerdeBadges';
import { PrecipChart } from './PrecipChart';
import { RiesgoBins } from './RiesgoBins';
import { SuelosBreakdown } from './SuelosBreakdown';

export interface FichaTerritorialPanelProps {
  /** Whether an area of interest is currently selected. When false, nothing renders. */
  readonly active: boolean;
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
}

function errorMessage(error: FichaApiError | Error | null): string {
  // The server ships an actionable Spanish `detail` for every ficha failure;
  // `FichaApiError.message` IS that detail. A bare network error has none.
  if (error instanceof FichaApiError) return error.message;
  if (error instanceof Error && error.message) return error.message;
  return 'No se pudo completar el análisis. Reintentá en unos instantes.';
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
  isError,
  error,
  data,
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
    return (
      <Alert color="red" variant="light" title="No disponible" data-testid="ficha-error">
        {errorMessage(error)}
      </Alert>
    );
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
  tipo,
  nroCuenta,
  parcelaProps,
  bpaEnriched,
  isLoading,
  isError,
  error,
  data,
  onClose,
  overlayVisible,
  onToggleOverlay,
}: FichaTerritorialPanelProps) {
  if (!active) return null;

  // The overlay toggle only makes sense once there is a result to clip on the
  // map, and only when the container wired the handler in.
  const showOverlayToggle = !!onToggleOverlay && !isLoading && !isError && !!data;

  // Identity header (bug-3 combine): a clicked parcel's account/identity fields
  // sit at the top of this single panel, replacing the old InfoPanel catastro
  // card. Only for `tipo=parcela`; other tipos (poligono/canal) have no parcel.
  const showParcelaHeader = tipo === 'parcela' && !!parcelaProps;

  return (
    <Paper
      shadow="md"
      p="md"
      radius="md"
      className={styles.fichaPanel}
      data-testid="ficha-territorial-panel"
    >
      <Group justify="space-between" mb="xs">
        <Title order={5}>Ficha territorial</Title>
        <CloseButton onClick={onClose} size="sm" aria-label="Cerrar ficha territorial" />
      </Group>
      <Divider mb="xs" />
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
        isError={isError}
        error={error}
        data={data}
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
        </>
      )}
    </Paper>
  );
});
