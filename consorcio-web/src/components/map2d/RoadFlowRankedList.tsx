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

import { Badge, Box, Group, Stack, Text } from '@mantine/core';

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

function RankedRow({
  feature,
  total,
}: {
  readonly feature: RoadFlowCrossingFeature;
  readonly total: number;
}) {
  const p = feature.properties;
  return (
    <Box data-testid={`road-flow-rank-${p.id}`} py={4}>
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
    </Box>
  );
}

function CanalRow({ feature }: { readonly feature: RoadFlowCrossingFeature }) {
  const p = feature.properties;
  return (
    <Box data-testid={`road-flow-canal-${p.id}`} py={4}>
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
    </Box>
  );
}

interface RoadFlowRankedListProps {
  readonly data: RoadFlowCrossingsResponse;
}

export function RoadFlowRankedList({ data }: RoadFlowRankedListProps) {
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
            <RankedRow key={f.properties.id} feature={f} total={total} />
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
            <CanalRow key={f.properties.id} feature={f} />
          ))}
        </Stack>
      ) : null}
    </Stack>
  );
}
