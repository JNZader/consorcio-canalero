import { ActionIcon, Badge, Button, Group, Slider, Text, Tooltip } from '@mantine/core';
import type { CanalToggleEntry } from '../shared/canalesGrouping';
import { IconRefresh } from '../ui/icons';
import type { LayerHealth } from './layerHealth';
import { type LayerCategory, normalizeSearchText } from './map2dDerived';

/**
 * Filter canal entries by label for the search box. A `leaf` matches on
 * its own label; a `group` is kept whole when the group label or any child
 * label matches.
 *
 * `query` must already be normalized by `normalizeSearchText`.
 */
export function filterCanalEntries(
  entries: readonly CanalToggleEntry[] | undefined,
  query: string
): CanalToggleEntry[] {
  if (!entries) return [];
  return entries.filter((entry) => {
    if (entry.kind === 'leaf') return normalizeSearchText(entry.label).includes(query);
    return (
      normalizeSearchText(entry.label).includes(query) ||
      entry.children.some((child) => normalizeSearchText(child.label).includes(query))
    );
  });
}

/** Compact per-layer opacity slider. Value is the 0..100 view of a 0..1 multiplier. */
export function LayerOpacityControl({
  layerId,
  label,
  multiplier,
  onChange,
}: {
  layerId: string;
  label: string;
  multiplier: number;
  onChange: (layerId: string, multiplier: number) => void;
}) {
  const percent = Math.round(multiplier * 100);
  return (
    <Group gap={6} wrap="nowrap" pl={26} pr={4} data-testid={`layer-opacity-${layerId}`}>
      <Slider
        flex={1}
        min={0}
        max={100}
        step={1}
        value={percent}
        onChange={(value) => onChange(layerId, value / 100)}
        label={(value) => `${value}%`}
        thumbLabel={`Opacidad de ${label}`}
      />
      <Text size="xs" c="dimmed" w={28} ta="right">
        {percent}%
      </Text>
      <Tooltip label="Restablecer opacidad" withArrow>
        <ActionIcon
          variant="subtle"
          size="sm"
          color="gray"
          aria-label={`Restablecer opacidad de ${label}`}
          data-testid={`layer-opacity-reset-${layerId}`}
          onClick={() => onChange(layerId, 1)}
        >
          <IconRefresh size={12} />
        </ActionIcon>
      </Tooltip>
    </Group>
  );
}

export function LayerHealthErrorRow({
  testId,
  message,
  onRetry,
}: {
  testId: string;
  message: string;
  onRetry?: (() => void) | null;
}) {
  return (
    <Group gap={6} wrap="nowrap" align="center">
      <Text size="xs" c="red" data-testid={testId} flex={1}>
        {message}
      </Text>
      {onRetry && (
        <Button
          size="xs"
          variant="subtle"
          color="red"
          leftSection={<IconRefresh size={12} />}
          onClick={onRetry}
        >
          Reintentar
        </Button>
      )}
    </Group>
  );
}

/**
 * Pilar Verde keeps its legacy contract: while `pilarVerdeLayersError` is set
 * it wins over the registry, so its historical copy and test id survive.
 */
export function resolveFamilyHealthRow(
  category: LayerCategory,
  isPilarVerde: boolean,
  pilarVerdeLayersError: string | null,
  layerHealth: LayerHealth | undefined
): { testId: string; message: string; onRetry: (() => void) | null } | null {
  const entry = layerHealth?.byCategory[category] ?? null;
  if (isPilarVerde && pilarVerdeLayersError) {
    return {
      testId: 'pilar-verde-layers-error',
      message: 'No se pudieron cargar las capas — reintentá',
      onRetry: entry?.reload ?? null,
    };
  }
  if (!entry?.message) return null;
  return {
    testId: isPilarVerde ? 'pilar-verde-layers-error' : `layer-health-error-${category}`,
    message: entry.message,
    onRetry: entry.reload,
  };
}

export function LayerProvenanceLine({ category, text }: { category: LayerCategory; text: string }) {
  return (
    <Text size="xs" c="dimmed" data-testid={`layer-provenance-${category}`}>
      {text}
    </Text>
  );
}

export function FamilyControlLabel({ label, count }: { label: string; count: number }) {
  return (
    <Group gap="xs" justify="space-between" wrap="nowrap" flex={1}>
      <Text size="xs" fw={600}>
        {label}
      </Text>
      {count > 0 && (
        <Badge size="xs" variant="light" color="blue">
          {count}
        </Badge>
      )}
    </Group>
  );
}
