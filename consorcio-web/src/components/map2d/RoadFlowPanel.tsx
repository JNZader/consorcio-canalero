/**
 * RoadFlowPanel — the host surface of the ranked road crossings
 * (flujo-caminos, S4 wiring).
 *
 * ⚠️ THE ENTRY POINT IS THE LAYER TOGGLE. ⚠️
 * Ticking "Cruces de camino" in the layer selector paints the two circle layers
 * AND opens this panel; unticking it closes the panel and hides the layers. One
 * control, one mental model — the alternative (a layer you can see plus a panel
 * you have to find somewhere else) was the shape that left the whole capability
 * unreachable in the first place.
 *
 * What it hosts, in this order:
 *   1. the kind FILTER (`flujo_natural` / `canal` / both) — a `setFilter` on the
 *      two ml layers, never an unmount, so hiding one kind cannot lose the other
 *      (RFA-R3, `applyRoadFlowKindFilter`);
 *   2. `RoadFlowRankedList`, which mounts `RoadFlowDisclaimer` above itself and
 *      is fed the SAME response object the map source consumes (RFA-R2);
 *   3. `RelevamientoCobertura`, the three counters that are never summed
 *      (RSS-R4).
 *
 * It is a `MapPanelShell` like every other map panel: floating card on desktop,
 * bottom sheet on a narrow viewport, minimize-to-pill in both. Nothing new was
 * invented for it — including the scroller (`.panelCardBody`), which is what
 * keeps a long ranked list scrollable inside a `pointer-events: none` card.
 */

import { Alert, Loader, SegmentedControl, Stack, Text } from '@mantine/core';

import type { CoberturaResponse } from '../../lib/api/relevamiento';
import type { RoadFlowCrossingFeature } from '../../lib/api/roadFlow';
import type { UseRoadFlowCrossingsResult } from '../../hooks/useRoadFlowCrossings';
import styles from '../../styles/components/map.module.css';
import { MapPanelShell } from './MapPanelShell';
import { RelevamientoCobertura } from './RelevamientoCobertura';
import { RoadFlowRankedList } from './RoadFlowRankedList';
import type { RoadFlowKindVisibility } from './roadFlowLayers';

/** The filter's three positions. `ambos` is the default: nothing hidden. */
export const ROAD_FLOW_KIND_FILTER = {
  AMBOS: 'ambos',
  FLUJO: 'flujo_natural',
  CANAL: 'canal',
} as const;

export type RoadFlowKindFilter = (typeof ROAD_FLOW_KIND_FILTER)[keyof typeof ROAD_FLOW_KIND_FILTER];

/** Filter position → the visibility pair `applyRoadFlowKindFilter` consumes. */
export function kindFilterToVisibility(filter: RoadFlowKindFilter): RoadFlowKindVisibility {
  return {
    flujo_natural: filter !== ROAD_FLOW_KIND_FILTER.CANAL,
    canal: filter !== ROAD_FLOW_KIND_FILTER.FLUJO,
  };
}

/** The inverse, so the control can render the caller's state without a copy. */
export function visibilityToKindFilter(visibility: RoadFlowKindVisibility): RoadFlowKindFilter {
  if (visibility.flujo_natural && !visibility.canal) return ROAD_FLOW_KIND_FILTER.FLUJO;
  if (!visibility.flujo_natural && visibility.canal) return ROAD_FLOW_KIND_FILTER.CANAL;
  return ROAD_FLOW_KIND_FILTER.AMBOS;
}

export interface RoadFlowPanelProps {
  /** Bottom-sheet shape on a narrow viewport, floating card otherwise. */
  readonly sheet: boolean;
  readonly crossings: UseRoadFlowCrossingsResult;
  readonly cobertura?: CoberturaResponse;
  readonly kinds: RoadFlowKindVisibility;
  readonly onKindsChange: (kinds: RoadFlowKindVisibility) => void;
  /** Recentre the map on one crossing. */
  readonly onSelectCrossing: (feature: RoadFlowCrossingFeature) => void;
  /** Open the field-survey sheet for one segment. */
  readonly onSurveyTramo: (tramoRef: string) => void;
  /** Turns the layer OFF — closing the panel and hiding the layer are one act. */
  readonly onClose: () => void;
  readonly minimized: boolean;
  readonly onToggleMinimize: () => void;
}

export function RoadFlowPanel({
  sheet,
  crossings,
  cobertura,
  kinds,
  onKindsChange,
  onSelectCrossing,
  onSurveyTramo,
  onClose,
  minimized,
  onToggleMinimize,
}: RoadFlowPanelProps) {
  const { data, isLoading, isError, error, sinCobertura } = crossings;

  return (
    <MapPanelShell
      sheet={sheet}
      floatingClassName={styles.roadFlowPanel}
      pillClassName={styles.roadFlowPanelPill}
      testId="road-flow-panel"
      sheetLabel="cruces de camino"
      closeLabel="Cerrar cruces de camino"
      onClose={onClose}
      minimized={minimized}
      onToggleMinimize={onToggleMinimize}
      pillLabel={data ? `Cruces de camino · ${data.total_flujo_natural}` : 'Cruces de camino'}
      initialStage="medio"
      resetKey={data?.calculada_en ?? null}
    >
      <Stack gap="sm">
        <Text fw={600} size="sm">
          Cruces de camino
        </Text>

        <SegmentedControl
          size="xs"
          fullWidth
          aria-label="Filtrar por tipo de cruce"
          data-testid="road-flow-kind-filter"
          value={visibilityToKindFilter(kinds)}
          onChange={(value) => onKindsChange(kindFilterToVisibility(value as RoadFlowKindFilter))}
          data={[
            { value: ROAD_FLOW_KIND_FILTER.AMBOS, label: 'Ambos' },
            { value: ROAD_FLOW_KIND_FILTER.FLUJO, label: 'Flujo natural' },
            { value: ROAD_FLOW_KIND_FILTER.CANAL, label: 'Canal' },
          ]}
        />

        {isLoading ? <Loader size="sm" data-testid="road-flow-loading" /> : null}

        {/* A 404 here is a COVERAGE STATE, not a failure: the area has no
            registered DEM footprint, so there is nothing to have computed. An
            operator told "todavía no se calculó" knows what to do next; one
            shown "Error 404" does not. */}
        {sinCobertura ? (
          <Alert color="gray" data-testid="road-flow-sin-cobertura">
            Todavía no se calcularon los cruces para esta área.
          </Alert>
        ) : null}

        {isError && !sinCobertura ? (
          <Alert color="red" data-testid="road-flow-error">
            {error?.message ?? 'No se pudieron leer los cruces de camino.'}
          </Alert>
        ) : null}

        {data ? (
          <RoadFlowRankedList data={data} onSelect={onSelectCrossing} onSurvey={onSurveyTramo} />
        ) : null}

        {cobertura ? <RelevamientoCobertura cobertura={cobertura} /> : null}
      </Stack>
    </MapPanelShell>
  );
}
