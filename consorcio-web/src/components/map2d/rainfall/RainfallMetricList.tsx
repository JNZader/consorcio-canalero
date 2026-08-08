/**
 * RainfallMetricList.tsx (Lluvia v2 — Phase 3)
 *
 * Metric groups of one snapshot as state-badged rows with full provenance,
 * plus the annual TEXTUAL comparison that serves as the chart's accessible
 * equivalent (design: "charts have textual equivalents"). Nominal grid
 * resolution is stated as such — never as parcel-level accuracy (spec
 * "Metric Provenance and State Metadata").
 */

import { Badge, Group, Stack, Text } from '@mantine/core';

import type { RainfallAnalysisSnapshot, RainfallMetric } from '../../../lib/api/rainfall';
import { describeMetricState, formatMetricValue, metricLabel } from './rainfallFormat';

const STATE_COLORS: Record<RainfallMetric['state'], string> = {
  available: 'green',
  partial: 'yellow',
  suppressed: 'orange',
  unavailable: 'gray',
};

const GROUP_TITLES: ReadonlyArray<{ key: 'annual' | 'antecedents' | 'intensity'; title: string }> =
  [
    { key: 'annual', title: 'Anual' },
    { key: 'antecedents', title: 'Antecedentes' },
    { key: 'intensity', title: 'Intensidad y evento' },
  ];

function MetricRow({ name, metric }: { readonly name: string; readonly metric: RainfallMetric }) {
  const provenance = metric.provenance;
  return (
    <Stack gap={2} data-testid={`rainfall-metric-${name}`}>
      <Group gap="xs" wrap="nowrap" justify="space-between">
        <Text size="xs">{metricLabel(name)}</Text>
        <Group gap={4} wrap="nowrap">
          {metric.temporal_state === 'provisional' && (
            <Badge size="xs" variant="outline" color="violet">
              Provisional
            </Badge>
          )}
          {metric.fallback_used && (
            <Badge size="xs" variant="outline" color="cyan">
              Fallback
            </Badge>
          )}
          <Badge size="xs" variant="light" color={STATE_COLORS[metric.state]}>
            {describeMetricState(metric)}
          </Badge>
          <Text size="xs" fw={600}>
            {formatMetricValue(metric)}
          </Text>
        </Group>
      </Group>
      <Text size="xs" c="dimmed">
        {`Fuente: ${provenance.source_id} · Resolución nominal: ${provenance.nominal_resolution} · Cobertura: ${Math.round(metric.coverage * 100)}% · Revisión: ${metric.revision}`}
      </Text>
    </Stack>
  );
}

/** Textual annual comparison — the chart's accessible equivalent. */
function AnnualText({ snapshot }: { readonly snapshot: RainfallAnalysisSnapshot }) {
  const selected = snapshot.annual?.selected;
  const normal = snapshot.annual?.normal;
  if (!selected && !normal) return null;
  const parts: string[] = [];
  if (selected) parts.push(`Año ${snapshot.year}: ${formatMetricValue(selected)}`);
  if (normal) parts.push(`Normal ${snapshot.baseline}: ${formatMetricValue(normal)}`);
  return (
    <Text size="sm" fw={600} data-testid="rainfall-annual-text">
      {parts.join(' · ')}
    </Text>
  );
}

export function RainfallMetricList({ snapshot }: { readonly snapshot: RainfallAnalysisSnapshot }) {
  return (
    <Stack gap="xs" data-testid="rainfall-metrics">
      <AnnualText snapshot={snapshot} />
      {GROUP_TITLES.map(({ key, title }) => {
        const group = snapshot[key];
        if (!group || Object.keys(group).length === 0) return null;
        return (
          <Stack key={key} gap={4}>
            <Text size="xs" fw={600} c="dimmed">
              {title}
            </Text>
            {Object.entries(group).map(([name, metric]) => (
              <MetricRow key={name} name={name} metric={metric} />
            ))}
          </Stack>
        );
      })}
      {typeof snapshot.summary === 'string' && snapshot.summary.length > 0 && (
        <Text size="xs" fs="italic" data-testid="rainfall-summary">
          {snapshot.summary}
        </Text>
      )}
    </Stack>
  );
}
