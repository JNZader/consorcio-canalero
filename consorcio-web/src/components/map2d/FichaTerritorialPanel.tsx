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
 *   - result   → one table per dataset (tables are the contract, JD-A-012);
 *   - the per-dataset `sin_cobertura` / low-confidence handling lives inside the
 *     dataset components.
 *
 * The monthly precipitation chart is deliberately NOT rendered here — it ships
 * in B2 (`PrecipChart`), which also fills `precipitacion_mensual` server-side.
 */

import { Alert, CloseButton, Divider, Group, Loader, Paper, Stack, Text, Title } from '@mantine/core';
import { memo } from 'react';

import type { FichaResponse, FichaTipo } from '../../lib/api/ficha';
import { FichaApiError } from '../../lib/api/ficha';
import type { BpaEnrichedFile } from '../../types/pilarVerde';
import styles from '../../styles/components/map.module.css';
import { FichaResumen } from './FichaResumen';
import { PilarVerdeBadges } from './PilarVerdeBadges';
import { RiesgoBins } from './RiesgoBins';
import { SuelosBreakdown } from './SuelosBreakdown';

export interface FichaTerritorialPanelProps {
  /** Whether an area of interest is currently selected. When false, nothing renders. */
  readonly active: boolean;
  readonly tipo: FichaTipo;
  /** Clicked parcel account, for the client-side BPA join. `null` for other tipos. */
  readonly nroCuenta: string | null;
  readonly bpaEnriched: BpaEnrichedFile | null | undefined;
  readonly isLoading: boolean;
  readonly isError: boolean;
  readonly error: FichaApiError | Error | null;
  readonly data: FichaResponse | undefined;
  readonly onClose: () => void;
}

function errorMessage(error: FichaApiError | Error | null): string {
  // The server ships an actionable Spanish `detail` for every ficha failure;
  // `FichaApiError.message` IS that detail. A bare network error has none.
  if (error instanceof FichaApiError) return error.message;
  if (error instanceof Error && error.message) return error.message;
  return 'No se pudo completar el análisis. Reintentá en unos instantes.';
}

function PanelBody({
  tipo,
  nroCuenta,
  bpaEnriched,
  isLoading,
  isError,
  error,
  data,
}: Omit<FichaTerritorialPanelProps, 'active' | 'onClose'>) {
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
      <RiesgoBins label="Riesgo de inundación" dataset={data.flood_risk} testId="ficha-flood-risk" />
      <Divider />
      <RiesgoBins
        label="Necesidad de drenaje"
        dataset={data.drainage_need}
        testId="ficha-drainage-need"
      />
      <Divider />
      <PilarVerdeBadges tipo={tipo} nroCuenta={nroCuenta} bpaEnriched={bpaEnriched} />
    </Stack>
  );
}

export const FichaTerritorialPanel = memo(function FichaTerritorialPanel({
  active,
  tipo,
  nroCuenta,
  bpaEnriched,
  isLoading,
  isError,
  error,
  data,
  onClose,
}: FichaTerritorialPanelProps) {
  if (!active) return null;

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
      <PanelBody
        tipo={tipo}
        nroCuenta={nroCuenta}
        bpaEnriched={bpaEnriched}
        isLoading={isLoading}
        isError={isError}
        error={error}
        data={data}
      />
    </Paper>
  );
});
