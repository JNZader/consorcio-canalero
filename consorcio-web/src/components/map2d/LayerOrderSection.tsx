/**
 * LayerOrderSection
 *
 * map-redesign Fase 3 — Tanda B (task 3.5).
 *
 * A drag-to-reorder "Orden de capas" control for the reorderable UI layers.
 * The list ALWAYS renders the FULL set of `RENDERABLE_UI_LAYER_IDS` (active
 * AND inactive, the latter dimmed) so every write to `onLayerOrderChange` is a
 * COMPLETE bottom→top ordering — the contract `applyLayerOrder` depends on (a
 * partial list would hoist its members above unrelated layers). See the
 * JSDoc CONTRACT on `applyLayerOrder` in `layerRenderRegistry.ts`.
 *
 * Display convention: TOP of the list = TOP of the map. The store keeps the
 * order BOTTOM→TOP (`orderByLayer`), so we reverse for display and reverse
 * back before writing.
 *
 * React Compiler is active → no manual `useMemo`/`useCallback`/`memo`.
 */

import {
  DndContext,
  type DragEndEvent,
  PointerSensor,
  closestCenter,
  useSensor,
  useSensors,
} from '@dnd-kit/core';
import { SortableContext, useSortable, verticalListSortingStrategy } from '@dnd-kit/sortable';
import { CSS } from '@dnd-kit/utilities';
import { ActionIcon, Box, Group, Stack, Text, Tooltip } from '@mantine/core';

import { IconArrowsSort, IconGripVertical } from '../ui/icons';
import {
  DEFAULT_LAYER_ORDER,
  RENDERABLE_UI_LAYER_IDS,
  type RenderableUiLayerId,
} from './layerRenderRegistry';

/**
 * Human-readable fallback labels for the reorderable layers. When a matching
 * entry exists in `layerItems` (passed from the panel), that label wins — this
 * map only covers ids that may NOT appear in `layerItems` (canales masters,
 * escuelas) and gives everything a sensible Spanish default.
 */
const LAYER_ORDER_LABELS: Record<RenderableUiLayerId, string> = {
  basins: 'Subcuencas',
  approved_zones: 'Zonas aprobadas',
  waterways: 'Hidrografía',
  roads: 'Red vial',
  soil: 'Suelos',
  catastro: 'Catastro',
  puntos_conflicto: 'Puntos de conflicto',
  precip_normal: 'Precipitación CHIRPS',
  pilar_verde_bpa_historico: 'BPA histórico',
  pilar_verde_agro_aceptada: 'Agroforestal aceptada',
  pilar_verde_agro_presentada: 'Agroforestal presentada',
  pilar_verde_agro_zonas: 'Agroforestal zonas',
  pilar_verde_porcentaje_forestacion: '% Forestación',
  canales_relevados: 'Canales relevados',
  canales_propuestos: 'Canales propuestos',
  escuelas: 'Escuelas rurales',
};

/**
 * PURE reorder helper — moves `activeId` to `overId`'s slot inside `currentIds`
 * (arrayMove semantics). Returns a NEW array; the input is never mutated.
 *
 * Extracted + exported so the reorder contract can be unit-tested without
 * simulating a pointer drag (jsdom cannot fire @dnd-kit's pointer sequence).
 * Direction-agnostic: it operates on whatever ordering the caller passes, so
 * the component uses it on the DISPLAY list (top→bottom) and reverses the
 * result for the store.
 *
 * No-op guarantees: identical ids, or an id not present in the list, return a
 * shallow copy of the original order (order unchanged).
 */
export function reorderLayerIds(
  currentIds: readonly string[],
  activeId: string,
  overId: string
): string[] {
  const from = currentIds.indexOf(activeId);
  const to = currentIds.indexOf(overId);
  if (from === -1 || to === -1 || from === to) return [...currentIds];
  const next = [...currentIds];
  const [moved] = next.splice(from, 1);
  next.splice(to, 0, moved);
  return next;
}

/**
 * Resolve the effective BOTTOM→TOP order for display. Guarantees the FULL set:
 *   - empty override → `DEFAULT_LAYER_ORDER`.
 *   - non-empty override → keep the user's order but drop unknown/duplicate
 *     ids and re-INSERT any renderable id missing from it at its DEFAULT slot
 *     (FF-B2). A newly-registered layer therefore lands where it belongs in
 *     the canonical z-order (e.g. a missing `roads` sinks to the bottom)
 *     instead of surfacing topmost — while still preserving the full-set
 *     invariant even if the override was persisted before that layer existed.
 */
export function resolveEffectiveBottomToTop(
  orderByLayer: readonly string[]
): RenderableUiLayerId[] {
  const valid = new Set<string>(RENDERABLE_UI_LAYER_IDS);
  if (orderByLayer.length === 0) return [...DEFAULT_LAYER_ORDER];

  const seen = new Set<RenderableUiLayerId>();
  const kept: RenderableUiLayerId[] = [];
  for (const id of orderByLayer) {
    if (valid.has(id) && !seen.has(id as RenderableUiLayerId)) {
      kept.push(id as RenderableUiLayerId);
      seen.add(id as RenderableUiLayerId);
    }
  }

  // FF-B2: re-insert each missing id at its DEFAULT_LAYER_ORDER index (clamped
  // to the current length). Walking DEFAULT ascending means every lower-ranked
  // missing id is placed before higher-ranked ones, so a new bottommost layer
  // (`roads`, idx 0) sinks to the bottom and a new topmost one appends on top —
  // instead of everything piling up at the end. The kept ids keep their custom
  // relative order (a high-default id the user dragged low STAYS low).
  const result: RenderableUiLayerId[] = [...kept];
  for (let defaultIdx = 0; defaultIdx < DEFAULT_LAYER_ORDER.length; defaultIdx++) {
    const id = DEFAULT_LAYER_ORDER[defaultIdx];
    if (seen.has(id)) continue;
    result.splice(Math.min(defaultIdx, result.length), 0, id);
    seen.add(id);
  }
  return result;
}

interface SortableLayerRowProps {
  readonly id: RenderableUiLayerId;
  readonly label: string;
  readonly active: boolean;
}

function SortableLayerRow({ id, label, active }: SortableLayerRowProps) {
  const { attributes, listeners, setNodeRef, transform, transition, isDragging } = useSortable({
    id,
  });

  return (
    <Group
      ref={setNodeRef}
      data-testid={`layer-order-item-${id}`}
      gap={6}
      wrap="nowrap"
      px={6}
      py={4}
      style={{
        transform: CSS.Transform.toString(transform),
        transition,
        opacity: isDragging ? 0.6 : active ? 1 : 0.45,
        borderRadius: 4,
        background: 'light-dark(rgba(0,0,0,0.03), rgba(255,255,255,0.04))',
        cursor: 'grab',
      }}
    >
      <ActionIcon
        variant="subtle"
        size="sm"
        color="gray"
        aria-label={`Arrastrar ${label}`}
        style={{ cursor: 'grab', touchAction: 'none' }}
        {...attributes}
        {...listeners}
      >
        <IconGripVertical size={14} />
      </ActionIcon>
      <Text size="xs" style={{ flex: 1 }}>
        {label}
      </Text>
      {!active && (
        <Text
          size="9px"
          c="dimmed"
          title="Capa oculta — se muestra para mantener el orden completo"
        >
          oculta
        </Text>
      )}
    </Group>
  );
}

export interface LayerOrderSectionProps {
  /** Current BOTTOM→TOP override from the store (empty = hardcoded default). */
  readonly orderByLayer: readonly string[];
  /** Write a FULL bottom→top order (empty array = reset to default). */
  readonly onLayerOrderChange: (orderedIds: string[]) => void;
  /** Visibility map — drives the dimmed "oculta" styling of inactive rows. */
  readonly vectorVisibility: Record<string, boolean>;
  /** Optional label overrides sourced from the panel's `layerItems`. */
  readonly labelById?: Record<string, string>;
}

export function LayerOrderSection({
  orderByLayer,
  onLayerOrderChange,
  vectorVisibility,
  labelById,
}: LayerOrderSectionProps) {
  // Small activation constraint so a plain click on the grip doesn't start a
  // drag before the pointer actually moves (keeps the ActionIcon tappable).
  const sensors = useSensors(useSensor(PointerSensor, { activationConstraint: { distance: 4 } }));

  const bottomToTop = resolveEffectiveBottomToTop(orderByLayer);
  // Display TOP→BOTTOM (top of list = top of map).
  const displayIds = [...bottomToTop].reverse();

  const handleDragEnd = (event: DragEndEvent) => {
    const { active, over } = event;
    if (!over || active.id === over.id) return;
    const newDisplay = reorderLayerIds(displayIds, String(active.id), String(over.id));
    // Store keeps bottom→top → reverse the display order back before writing.
    onLayerOrderChange([...newDisplay].reverse());
  };

  const resetButton = (
    <ActionIcon
      variant="subtle"
      size="sm"
      color="gray"
      aria-label="Restablecer orden"
      data-testid="layer-order-reset"
      onClick={(event) => {
        event.stopPropagation();
        // FF-B1: write the EXPLICIT default set (bottom→top), NOT `[]`. Writing
        // `[]` would only reset the LIST (`resolveEffectiveBottomToTop([])` →
        // DEFAULT) while leaving the MAP on the previous custom stacking —
        // `applyLayerOrder(map, [])` is a no-op and never UNDOES the persistent
        // `moveLayer` mutations. Writing the full default set makes
        // `applyLayerOrder` re-hoist every layer to the canonical order so the
        // map matches the list. Still honors the full-set contract.
        onLayerOrderChange([...DEFAULT_LAYER_ORDER]);
      }}
    >
      <IconArrowsSort size={14} />
    </ActionIcon>
  );

  return (
    <Box data-testid="layer-order-section">
      <Group justify="space-between" wrap="nowrap" mb={4}>
        <Text size="xs" fw={600} c="dimmed">
          Orden de capas
        </Text>
        <Tooltip label="Restablecer orden" withArrow>
          {resetButton}
        </Tooltip>
      </Group>
      <Text size="9px" c="dimmed" mb={6}>
        Arrastrá para reordenar. Arriba = se dibuja encima.
      </Text>
      <DndContext sensors={sensors} collisionDetection={closestCenter} onDragEnd={handleDragEnd}>
        <SortableContext items={displayIds} strategy={verticalListSortingStrategy}>
          <Stack gap={2}>
            {displayIds.map((id) => (
              <SortableLayerRow
                key={id}
                id={id}
                label={labelById?.[id] ?? LAYER_ORDER_LABELS[id]}
                active={vectorVisibility[id] === true}
              />
            ))}
          </Stack>
        </SortableContext>
      </DndContext>
    </Box>
  );
}
