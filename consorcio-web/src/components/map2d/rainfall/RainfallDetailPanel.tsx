/**
 * RainfallDetailPanel.tsx (Lluvia v2 — Phase 3)
 *
 * Authenticated Rainfall v2 technical detail, mounted in the ficha's Lluvia
 * tab under the public PrecipChart (untouched). RENDER GATE only — the backend
 * is the authorization boundary; anonymous visitors and non-staff never see
 * the control (anti-flash criterion as `useAnalysisToolsGate`). A queued (202)
 * answer is a LABELLED pending state that polls with a bounded budget; once
 * the budget is exhausted the panel shows an honest terminal "no disponible
 * aún" state with a manual retry — never an auto-update promise that cannot be
 * kept (RESILIENCE-001/002). All state changes go through an aria-live region;
 * parcel-originated results keep the "Estimación regional" label (spec
 * "Supported Analysis Scope and Parcel Semantics").
 */

import {
  Alert,
  Badge,
  Button,
  Group,
  Loader,
  NativeSelect,
  SegmentedControl,
  Stack,
  Text,
} from '@mantine/core';
import { useEffect, useState } from 'react';

import { useRainfallAnalysis, useRainfallScopes } from '../../../hooks/useRainfallAnalysis';
import {
  type RainfallScopeChoice,
  downloadRainfallCsv,
  downloadRainfallXlsx,
} from '../../../lib/api/rainfall';
import { useCanAccess } from '../../../stores/authStore';
import { RainfallAccumulationChart } from './RainfallAccumulationChart';
import { RainfallMetricList } from './RainfallMetricList';
import { RAINFALL_SCOPE_LABELS } from './rainfallFormat';

const CURRENT_YEAR = new Date().getFullYear();
const YEAR_OPTIONS = Array.from({ length: CURRENT_YEAR - 1990 }, (_, i) =>
  String(CURRENT_YEAR - i)
);

function scopeKey(scope: RainfallScopeChoice): string {
  return `${scope.kind}:${scope.id}:${scope.version}`;
}

function LoadingRow({ label }: { readonly label: string }) {
  return (
    <Group gap="xs">
      <Loader size="xs" />
      <Text size="xs" c="dimmed">
        {label}
      </Text>
    </Group>
  );
}

export function RainfallDetailPanel({
  nomenclatura,
  pollIntervalMs,
  maxQueuedPolls,
}: {
  readonly nomenclatura: string;
  /** Test seam: forwarded to `useRainfallAnalysis` (see the hook options). */
  readonly pollIntervalMs?: number;
  /** Test seam: forwarded to `useRainfallAnalysis` (see the hook options). */
  readonly maxQueuedPolls?: number;
}) {
  const canAccess = useCanAccess(['admin', 'operador']);
  const scopes = useRainfallScopes(canAccess ? nomenclatura : null);
  const choices =
    scopes.data?.kind === 'choices'
      ? scopes.data.choices
      : scopes.data?.kind === 'scope'
        ? [scopes.data.scope]
        : [];
  const regionalEstimate = scopes.data?.regional_estimate === true;

  const [selectedKey, setSelectedKey] = useState<string | null>(null);
  const [year, setYear] = useState(CURRENT_YEAR);
  const selected = choices.find((c) => scopeKey(c) === selectedKey) ?? choices[0] ?? null;

  const analysis = useRainfallAnalysis(canAccess ? selected : null, year, {
    pollIntervalMs,
    maxQueuedPolls,
  });
  const snapshot = analysis.data?.type === 'ready' ? analysis.data.snapshot : null;

  const [announcement, setAnnouncement] = useState('');
  useEffect(() => {
    if (analysis.data?.type === 'queued') {
      if (analysis.gaveUp) {
        setAnnouncement('Análisis no disponible aún. Puede reintentar manualmente.');
      } else {
        setAnnouncement(`Análisis en preparación: ${analysis.data.queued.labels.join(', ')}`);
      }
    } else if (snapshot) {
      setAnnouncement(
        `Análisis de lluvia disponible para ${RAINFALL_SCOPE_LABELS[snapshot.scope.kind]} ${year}`
      );
    } else if (analysis.isError) {
      setAnnouncement('No se pudo obtener el análisis de lluvia.');
    }
  }, [analysis.data, analysis.gaveUp, analysis.isError, snapshot, year]);

  // One in-flight export at a time, tracked by FORMAT: two independent
  // booleans would let both buttons spin at once and a shared one would spin
  // the wrong button.
  const [exportingFormat, setExportingFormat] = useState<'csv' | 'xlsx' | null>(null);
  const [exportError, setExportError] = useState<string | null>(null);
  async function exportAnalysis(revisionId: string, format: 'csv' | 'xlsx') {
    setExportingFormat(format);
    setExportError(null);
    try {
      await (format === 'csv' ? downloadRainfallCsv(revisionId) : downloadRainfallXlsx(revisionId));
    } catch (error) {
      setExportError(
        error instanceof Error
          ? error.message
          : `No se pudo exportar el ${format === 'csv' ? 'CSV' : 'Excel'}.`
      );
    } finally {
      setExportingFormat(null);
    }
  }

  if (!canAccess) return null;

  return (
    <Stack gap="xs" data-testid="rainfall-detail">
      {/* Every state change is announced, so queued → ready is perceivable
          without watching the panel. */}
      <Text size="xs" c="dimmed" aria-live="polite" data-testid="rainfall-live">
        {announcement}
      </Text>
      <Group gap="xs" justify="space-between" wrap="nowrap">
        <Text size="sm" fw={600}>
          Detalle técnico de lluvia
        </Text>
        {regionalEstimate && (
          <Badge size="xs" variant="light" color="blue" data-testid="rainfall-regional-estimate">
            Estimación regional
          </Badge>
        )}
      </Group>

      {scopes.isLoading && <LoadingRow label="Resolviendo ámbito regional…" />}
      {scopes.isError && (
        <Text size="xs" c="red">
          {scopes.error?.message ?? 'No se pudo resolver el ámbito regional.'}
        </Text>
      )}

      {choices.length > 1 && (
        <SegmentedControl
          size="xs"
          fullWidth
          value={selected ? scopeKey(selected) : undefined}
          onChange={setSelectedKey}
          data={choices.map((choice) => ({
            value: scopeKey(choice),
            label: RAINFALL_SCOPE_LABELS[choice.kind],
          }))}
          aria-label="Ámbito regional"
          data-testid="rainfall-scope-switch"
        />
      )}

      {selected && (
        <NativeSelect
          size="xs"
          label="Año de análisis"
          aria-label="Año de análisis"
          value={String(year)}
          onChange={(event) => setYear(Number(event.currentTarget.value))}
          data={YEAR_OPTIONS}
          data-testid="rainfall-year-select"
        />
      )}

      {analysis.isLoading && <LoadingRow label="Consultando análisis…" />}
      {analysis.isError && (
        <Stack gap="xs">
          <Text size="xs" c="red">
            {analysis.error?.message ?? 'No se pudo obtener el análisis de lluvia.'}
          </Text>
          <Button
            size="xs"
            variant="light"
            onClick={() => analysis.retry()}
            data-testid="rainfall-retry"
          >
            Reintentar
          </Button>
        </Stack>
      )}

      {/* Queued (202): LABELLED pending state with its reason; the query polls
          with a bounded budget and this block resolves itself. Never a bare
          spinner. Once the budget is exhausted the terminal state below takes
          over — no auto-update promise after polling has stopped. */}
      {analysis.data?.type === 'queued' && !analysis.gaveUp && !analysis.isError && (
        <Alert color="blue" variant="light" data-testid="rainfall-queued">
          <Text size="xs">
            Análisis en preparación
            {analysis.data.queued.labels.length > 0
              ? `: ${analysis.data.queued.labels.join(', ')}`
              : ''}
            . Se actualiza automáticamente.
          </Text>
        </Alert>
      )}

      {/* Terminal: polling gave up without a ready snapshot. Honest labelled
          failure with a manual retry that re-runs the fetch with a fresh
          budget — auto-refresh is over and the UI never promises it. */}
      {analysis.gaveUp && (
        <Alert color="yellow" variant="light" data-testid="rainfall-unavailable">
          <Text size="xs">
            Análisis no disponible aún. Se agotó el tiempo de espera automático.
          </Text>
          <Button
            size="xs"
            variant="light"
            mt="xs"
            onClick={() => analysis.retry()}
            data-testid="rainfall-retry"
          >
            Reintentar
          </Button>
        </Alert>
      )}

      {snapshot && (
        <>
          <RainfallMetricList snapshot={snapshot} />
          {/* The year-vs-normal comparison the owner asked for. Mounted here
              rather than inside the metric list because it owns its own
              request (`/series`) and its own disclosures; `AnnualText` above
              stays its textual equivalent. */}
          <RainfallAccumulationChart snapshot={snapshot} />
          <Group gap="xs" wrap="nowrap">
            <Button
              size="xs"
              variant="light"
              loading={exportingFormat === 'csv'}
              onClick={() => void exportAnalysis(snapshot.analysis_revision_id, 'csv')}
              data-testid="rainfall-export-csv"
            >
              Exportar CSV
            </Button>
            <Button
              size="xs"
              variant="light"
              loading={exportingFormat === 'xlsx'}
              onClick={() => void exportAnalysis(snapshot.analysis_revision_id, 'xlsx')}
              data-testid="rainfall-export-xlsx"
            >
              Exportar Excel
            </Button>
          </Group>
          {exportError && (
            <Text size="xs" c="red" data-testid="rainfall-export-error">
              {exportError}
            </Text>
          )}
        </>
      )}
    </Stack>
  );
}
