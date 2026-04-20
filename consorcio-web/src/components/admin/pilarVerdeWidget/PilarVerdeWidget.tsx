/**
 * PilarVerdeWidget.tsx
 *
 * Five-KPI Pilar Verde card mounted inside `AdminDashboard.tsx`. The widget is
 * PROP-DRIVEN so it's trivial to render in Storybook, snapshot tests, and
 * Playwright without pulling TanStack Query into the render tree.
 *
 * An ambient `PilarVerdeWidgetConnected` wrapper (below) calls `usePilarVerde()`
 * and threads the slice into `<PilarVerdeWidget />`. AdminDashboard imports the
 * connected variant; tests import the raw one with inline props.
 *
 * Layout (per spec § "AdminDashboard Pilar Verde Widget"):
 *   Title         "Pilar Verde · Suelo y Agroforestal"
 *   KPI 1 & 2     Ley Forestal two-track: cumplen / no cumplen (parcelas + ha)
 *   KPI 3         BPA activos: explotaciones + superficie
 *   KPI 4         Top práctica adoptada (humanized ES label + %)
 *   KPI 5         Top práctica NO adoptada
 *   Histórico     ONE-LINER — "Histórico BPA: N (pct) · Abandonaron: M · Nunca: K"
 *   Footer        "Datos: IDECor 2025"
 *   CTA           <Anchor href="/mapa?pilarVerde=1">Ver mapa Pilar Verde →</Anchor>
 *
 * `?pilarVerde=1` is read ONCE at mount by `MapaMapLibre.tsx` which flips the
 * 5 Pilar Verde layers to visible via the `useMapLayerSyncStore`.
 *
 * Loading / error branches:
 *   isLoading && !aggregates → <Loader /> (skeleton-equivalent)
 *   otherwise (!aggregates)  → <Alert>Datos no disponibles</Alert>
 */

import { Alert, Anchor, Loader, Paper, Stack, Text, Title } from '@mantine/core';
import { memo } from 'react';

import { usePilarVerde } from '../../../hooks/usePilarVerde';
import type { AggregatesFile } from '../../../types/pilarVerde';
import {
  computeBpaKpis,
  computeHistoricalKpis,
  computeLeyForestalKpis,
  humanizePracticaLabel,
} from './computeKpis';
import { fmt } from './fmt';

export interface PilarVerdeWidgetProps {
  /** Aggregates payload — `undefined` triggers the loader / alert branches. */
  readonly aggregates?: AggregatesFile;
  /** True while the parent hook is fetching — shows a Mantine `<Loader>`. */
  readonly isLoading?: boolean;
  /** True when the parent hook surfaced an error — shows the alert branch. */
  readonly isError?: boolean;
}

// ---------------------------------------------------------------------------
// Presentational widget — prop-driven, no hooks inside
// ---------------------------------------------------------------------------

export const PilarVerdeWidget = memo(function PilarVerdeWidget({
  aggregates,
  isLoading,
  isError,
}: PilarVerdeWidgetProps) {
  if (!aggregates) {
    if (isLoading) {
      return (
        <Paper withBorder p="md" radius="md" data-testid="pilar-verde-widget">
          <Stack align="center" gap="xs" data-testid="pilar-verde-widget-loader">
            <Loader size="sm" />
            <Text size="sm" c="dimmed">
              Cargando Pilar Verde…
            </Text>
          </Stack>
        </Paper>
      );
    }
    return (
      <Paper withBorder p="md" radius="md" data-testid="pilar-verde-widget">
        <Alert color={isError ? 'red' : 'yellow'} title="Datos no disponibles">
          {isError
            ? 'No se pudieron cargar los agregados de Pilar Verde. Reintentá más tarde.'
            : 'Los agregados de Pilar Verde aún no están publicados.'}
        </Alert>
      </Paper>
    );
  }

  const ley = computeLeyForestalKpis(aggregates.ley_forestal);
  const bpa = computeBpaKpis(aggregates.bpa);
  const hist = computeHistoricalKpis(aggregates.bpa);
  const topAdoptadaLabel = humanizePracticaLabel(bpa.topAdoptada?.nombre);
  const topNoAdoptadaLabel = humanizePracticaLabel(bpa.topNoAdoptada?.nombre);
  const topAdoptadaPct = bpa.topAdoptada ? bpa.topAdoptada.pct : null;
  const topNoAdoptadaPct = bpa.topNoAdoptada ? bpa.topNoAdoptada.pct : null;

  return (
    <Paper withBorder p="md" radius="md" data-testid="pilar-verde-widget">
      <Stack gap="xs">
        <Title order={5}>Pilar Verde · Suelo y Agroforestal</Title>

        <Text size="sm" data-testid="kpi-ley-cumplen">
          <Text component="span" fw={600}>
            Ley Forestal (cumplen):
          </Text>{' '}
          {fmt(ley.cumplen.parcelas, 'parcelas')} ({fmt(ley.cumplen.superficie_ha, 'ha')})
        </Text>

        <Text size="sm" data-testid="kpi-ley-no-cumplen">
          <Text component="span" fw={600}>
            Ley Forestal (no cumplen):
          </Text>{' '}
          {fmt(ley.noCumplen.parcelas, 'parcelas')} ({fmt(ley.noCumplen.superficie_ha, 'ha')})
        </Text>

        <Text size="sm" data-testid="kpi-bpa-activos">
          <Text component="span" fw={600}>
            BPA activos:
          </Text>{' '}
          {fmt(bpa.activas, 'explotaciones')} ({fmt(bpa.superficieHa, 'ha')})
        </Text>

        <Text size="sm" data-testid="kpi-top-adoptada">
          <Text component="span" fw={600}>
            Top práctica adoptada:
          </Text>{' '}
          {topAdoptadaLabel} ({fmt(topAdoptadaPct, '%')})
        </Text>

        <Text size="sm" data-testid="kpi-top-no-adoptada">
          <Text component="span" fw={600}>
            Top práctica NO adoptada:
          </Text>{' '}
          {topNoAdoptadaLabel} ({fmt(topNoAdoptadaPct, '%')})
        </Text>

        <Text size="sm" data-testid="kpi-historico">
          <Text component="span" fw={600}>
            Histórico BPA:
          </Text>{' '}
          {fmt(hist.historicaCount, 'parcelas')} ({fmt(hist.historicaPct, '%')}) · Abandonaron:{' '}
          {fmt(hist.abandonaronCount)} · Nunca: {fmt(hist.nuncaCount)}
        </Text>

        <Text size="xs" c="dimmed">
          Datos: IDECor 2025
        </Text>

        <Anchor href="/mapa?pilarVerde=1" size="sm">
          Ver mapa Pilar Verde →
        </Anchor>
      </Stack>
    </Paper>
  );
});

// ---------------------------------------------------------------------------
// Connected wrapper — consumed by AdminDashboard
// ---------------------------------------------------------------------------

/**
 * Thin adapter that wires `usePilarVerde()` to the presentational widget. Keeps
 * `AdminDashboard.tsx` free of Pilar Verde fetch concerns.
 */
export function PilarVerdeWidgetConnected() {
  const { data, loading, error } = usePilarVerde();
  return (
    <PilarVerdeWidget
      aggregates={data?.aggregates ?? undefined}
      isLoading={loading}
      isError={error !== null}
    />
  );
}
