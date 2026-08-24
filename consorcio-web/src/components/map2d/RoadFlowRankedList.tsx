/**
 * RoadFlowRankedList — the ranked road-crossing panel (flujo-caminos, D6).
 *
 * Reads the SAME `RoadFlowCrossingsResponse` object the map layer consumes
 * (`useRoadFlowCrossings` → `syncRoadFlowLayers`). One payload, two surfaces:
 * RFA-R2's "the two views do not disagree" is a structural property here, not a
 * convention somebody has to maintain.
 *
 * Three rules this component exists to keep:
 *
 *   1. **M is the `flujo_natural` counter** (Law 7). Ranks read `N.º de M` with
 *      M taken from `total_flujo_natural`, NEVER from `features.length` — the
 *      collection also carries the unranked canal candidates, and a denominator
 *      that moved with canal coverage would be arithmetically meaningless.
 *   2. **Canal candidates are a separate, unranked companion set.** They are
 *      culvert/bridge candidates, not competitors in the ranking.
 *   3. **Low confidence is marked, never demoted.** A `confianza='baja'` row
 *      keeps its rank and its place; the marker is what stops a coin-toss angle
 *      from being read as a finding.
 *
 * No volume, rate, depth, cuneta size or return period appears anywhere here,
 * because none exists in the response. The capability derives a DIRECTION and a
 * RELATIVE ORDER.
 */

import { Badge, Box, Button, Group, Stack, Text, UnstyledButton } from '@mantine/core';
import type { ReactNode } from 'react';

import {
  ROAD_FLOW_KINDS,
  type RoadFlowCrossingFeature,
  type RoadFlowCrossingsResponse,
} from '../../lib/api/roadFlow';
import { RoadFlowDisclaimer } from './RoadFlowDisclaimer';

/** The marker a low-confidence row carries, in both surfaces. */
export const ROAD_FLOW_BAJA_MARKER = 'orientación aproximada';

function formatDegrees(value: number | null): string {
  if (value === null || !Number.isFinite(value)) return '—';
  return `${value.toLocaleString('es-AR', { maximumFractionDigits: 0 })}°`;
}

function formatHectares(value: number | null): string {
  if (value === null || !Number.isFinite(value)) return '—';
  return `${value.toLocaleString('es-AR', {
    minimumFractionDigits: 1,
    maximumFractionDigits: 1,
  })} ha`;
}

function formatCalculadaEn(iso: string | null): string {
  if (!iso) return 'Sin fecha de cálculo';
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return 'Sin fecha de cálculo';
  const fecha = date.toLocaleDateString('es-AR', {
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
  });
  const hora = date.toLocaleTimeString('es-AR', { hour: '2-digit', minute: '2-digit' });
  return `Calculado el ${fecha} ${hora}`;
}

/**
 * The low-confidence marker. The REASON is the server's `nota`, verbatim: the
 * D8 quantization band and the shared-alignment note are the backend's facts
 * about that row, and re-deriving either one here would be a second copy of a
 * rule this frontend does not own.
 */
function ConfianzaMarker({ id, nota }: { readonly id: string; readonly nota: string | null }) {
  return (
    <Badge
      size="xs"
      variant="outline"
      color="gray"
      data-testid={`road-flow-confianza-${id}`}
      title={nota ?? ROAD_FLOW_BAJA_MARKER}
    >
      {ROAD_FLOW_BAJA_MARKER}
    </Badge>
  );
}

/**
 * Row chrome shared by both sets.
 *
 * With `onSelect` the row becomes a BUTTON (the map recentres on the crossing);
 * without it, it stays the plain box it has always been, so a caller that wires
 * no interaction renders exactly what it rendered before. The survey action is
 * a SEPARATE control on purpose: recentring the map and opening a form that can
 * write to the database must never be the same tap.
 */
function RowShell({
  testId,
  onSelect,
  selectLabel,
  children,
}: {
  readonly testId: string;
  readonly onSelect?: () => void;
  readonly selectLabel: string;
  readonly children: ReactNode;
}) {
  if (!onSelect) {
    return (
      <Box data-testid={testId} py={4}>
        {children}
      </Box>
    );
  }
  return (
    <UnstyledButton
      data-testid={testId}
      onClick={onSelect}
      aria-label={selectLabel}
      style={{ display: 'block', width: '100%', textAlign: 'left', paddingBlock: 4 }}
    >
      {children}
    </UnstyledButton>
  );
}

/** The per-row survey entry. Rendered only when the caller wires one. */
function SurveyAction({
  tramoRef,
  onSurvey,
}: {
  readonly tramoRef: string;
  readonly onSurvey?: (tramoRef: string) => void;
}) {
  if (!onSurvey) return null;
  return (
    <Button
      size="compact-xs"
      variant="light"
      data-testid={`road-flow-relevar-${tramoRef}`}
      aria-label={`Relevar el tramo ${tramoRef}`}
      onClick={(event) => {
        // The row itself recentres the map; this control must not do both.
        event.stopPropagation();
        onSurvey(tramoRef);
      }}
    >
      Relevar
    </Button>
  );
}

function RankedRow({
  feature,
  total,
  onSelect,
  onSurvey,
}: {
  readonly feature: RoadFlowCrossingFeature;
  readonly total: number;
  readonly onSelect?: (feature: RoadFlowCrossingFeature) => void;
  readonly onSurvey?: (tramoRef: string) => void;
}) {
  const p = feature.properties;
  return (
    <Group gap="xs" wrap="nowrap" align="flex-start">
      <RowShell
        testId={`road-flow-rank-${p.id}`}
        selectLabel={`Centrar el mapa en el cruce ${p.orden_ranking ?? ''} del tramo ${p.tramo_ref}`}
        onSelect={onSelect ? () => onSelect(feature) : undefined}
      >
        <Group gap="xs" wrap="wrap">
          <Text fw={600} size="sm">
            {`${p.orden_ranking}.º de ${total}`}
          </Text>
          <Text size="sm">{p.tramo_ref}</Text>
          {p.confianza === 'baja' ? <ConfianzaMarker id={p.id} nota={p.nota} /> : null}
        </Group>
        <Text size="xs" c="dimmed">
          {`Flujo ${formatDegrees(p.direccion_flujo_deg)} · camino ${formatDegrees(
            p.rumbo_camino_deg
          )} · aporte ${formatHectares(p.area_aporte_ha)}`}
        </Text>
      </RowShell>
      <SurveyAction tramoRef={p.tramo_ref} onSurvey={onSurvey} />
    </Group>
  );
}

function CanalRow({
  feature,
  onSelect,
  onSurvey,
}: {
  readonly feature: RoadFlowCrossingFeature;
  readonly onSelect?: (feature: RoadFlowCrossingFeature) => void;
  readonly onSurvey?: (tramoRef: string) => void;
}) {
  const p = feature.properties;
  return (
    <Group gap="xs" wrap="nowrap" align="flex-start">
      <RowShell
        testId={`road-flow-canal-${p.id}`}
        selectLabel={`Centrar el mapa en el cruce de canal del tramo ${p.tramo_ref}`}
        onSelect={onSelect ? () => onSelect(feature) : undefined}
      >
        <Group gap="xs" wrap="wrap">
          <Text size="sm">{p.tramo_ref}</Text>
          <Text size="sm" c="dimmed">
            {p.canal_ref ?? '—'}
          </Text>
          {p.confianza === 'baja' ? <ConfianzaMarker id={p.id} nota={p.nota} /> : null}
        </Group>
        <Text size="xs" c="dimmed">
          {`Cruce de canal · flujo ${formatDegrees(p.direccion_flujo_deg)} · camino ${formatDegrees(
            p.rumbo_camino_deg
          )}`}
        </Text>
      </RowShell>
      <SurveyAction tramoRef={p.tramo_ref} onSurvey={onSurvey} />
    </Group>
  );
}

interface RoadFlowRankedListProps {
  readonly data: RoadFlowCrossingsResponse;
  /**
   * Recentre the map on this crossing. Optional: without it the rows render as
   * plain boxes, exactly as they did before any wiring existed.
   */
  readonly onSelect?: (feature: RoadFlowCrossingFeature) => void;
  /**
   * Open the field-survey sheet for a segment. Optional for the same reason.
   */
  readonly onSurvey?: (tramoRef: string) => void;
}

export function RoadFlowRankedList({ data, onSelect, onSurvey }: RoadFlowRankedListProps) {
  const features = data.features?.features ?? [];
  const ranked = features
    .filter((f) => f.properties.tipo === ROAD_FLOW_KINDS.FLUJO_NATURAL)
    .sort((a, b) => (a.properties.orden_ranking ?? 0) - (b.properties.orden_ranking ?? 0));
  const canales = features.filter((f) => f.properties.tipo === ROAD_FLOW_KINDS.CANAL);

  // M — the run's own count of ranked crossings. NOT `ranked.length`, and
  // emphatically not `features.length` (Law 7).
  const total = data.total_flujo_natural;

  return (
    <Stack gap="xs" data-testid="road-flow-ranked-list">
      {/* Always mounted, never inside a fold — RFA-R4. */}
      <RoadFlowDisclaimer surface="lista" />

      <Text size="xs" c="dimmed" data-testid="road-flow-calculada-en">
        {formatCalculadaEn(data.calculada_en)}
      </Text>

      {data.desactualizado ? (
        <Text size="xs" c="orange" data-testid="road-flow-desactualizado">
          El modelo de elevación cambió después de este cálculo: el orden puede estar
          desactualizado.
        </Text>
      ) : null}

      {ranked.length === 0 && canales.length === 0 ? (
        <Text size="sm" c="dimmed" data-testid="road-flow-empty">
          No hay cruces calculados para esta área.
        </Text>
      ) : null}

      {ranked.length > 0 ? (
        <Stack gap={2} data-testid="road-flow-ranked-section">
          {ranked.map((f) => (
            <RankedRow
              key={f.properties.id}
              feature={f}
              total={total}
              onSelect={onSelect}
              onSurvey={onSurvey}
            />
          ))}
        </Stack>
      ) : null}

      {canales.length > 0 ? (
        <Stack gap={2} data-testid="road-flow-canal-section">
          <Text size="xs" fw={600}>
            {`Cruces de canal (${data.total_canal})`}
          </Text>
          <Text size="xs" c="dimmed">
            Candidatos a alcantarilla o puente. No entran en el orden.
          </Text>
          {canales.map((f) => (
            <CanalRow key={f.properties.id} feature={f} onSelect={onSelect} onSurvey={onSurvey} />
          ))}
        </Stack>
      ) : null}
    </Stack>
  );
}
