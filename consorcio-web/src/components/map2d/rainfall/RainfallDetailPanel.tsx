/**
 * RainfallDetailPanel.tsx (Lluvia v2 — Phase 3)
 *
 * Authenticated Rainfall v2 technical detail, mounted in the ficha's Lluvia
 * tab under the public PrecipChart (untouched). RENDER GATE only — the backend
 * is the authorization boundary; anonymous visitors and non-staff never see
 * the control (anti-flash criterion as `useAnalysisToolsGate`). A queued (202)
 * answer is a LABELLED pending state that polls; all state changes go through
 * an aria-live region; parcel-originated results keep the "Estimación
 * regional" label (spec "Supported Analysis Scope and Parcel Semantics").
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
import { type RainfallScopeChoice, downloadRainfallCsv } from '../../../lib/api/rainfall';
import { useCanAccess } from '../../../stores/authStore';
import { RainfallMetricList } from './RainfallMetricList';

const CURRENT_YEAR = new Date().getFullYear();
const YEAR_OPTIONS = Array.from({ length: CURRENT_YEAR - 1990 }, (_, i) =>
  String(CURRENT_YEAR - i)
);

const SCOPE_LABELS: Record<RainfallScopeChoice['kind'], string> = {
  zone: 'Zona',
  basin: 'Cuenca',
};

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

export function RainfallDetailPanel({ nomenclatura }: { readonly nomenclatura: string }) {
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

  const analysis = useRainfallAnalysis(canAccess ? selected : null, year);
  const snapshot = analysis.data?.type === 'ready' ? analysis.data.snapshot : null;

  const [announcement, setAnnouncement] = useState('');
  useEffect(() => {
    if (analysis.data?.type === 'queued') {
      setAnnouncement(`Análisis en preparación: ${analysis.data.queued.labels.join(', ')}`);
    } else if (snapshot) {
      setAnnouncement(
        `Análisis de lluvia disponible para ${SCOPE_LABELS[snapshot.scope.kind]} ${year}`
      );
    } else if (analysis.isError) {
      setAnnouncement('No se pudo obtener el análisis de lluvia.');
    }
  }, [analysis.data, snapshot, analysis.isError, year]);

  const [exporting, setExporting] = useState(false);
  const [exportError, setExportError] = useState<string | null>(null);
  async function exportCsv(revisionId: string) {
    setExporting(true);
    setExportError(null);
    try {
      await downloadRainfallCsv(revisionId);
    } catch (error) {
      setExportError(error instanceof Error ? error.message : 'No se pudo exportar el CSV.');
    } finally {
      setExporting(false);
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
            label: SCOPE_LABELS[choice.kind],
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
        <Text size="xs" c="red">
          {analysis.error?.message ?? 'No se pudo obtener el análisis de lluvia.'}
        </Text>
      )}

      {/* Queued (202): LABELLED pending state with its reason; the query keeps
          polling and this block resolves itself. Never a bare spinner. */}
      {analysis.data?.type === 'queued' && (
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

      {snapshot && (
        <>
          <RainfallMetricList snapshot={snapshot} />
          <Button
            size="xs"
            variant="light"
            loading={exporting}
            onClick={() => void exportCsv(snapshot.analysis_revision_id)}
            data-testid="rainfall-export-csv"
          >
            Exportar CSV
          </Button>
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
