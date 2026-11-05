import { Box, Button, Group, Slider, Stack, Text, Tooltip } from '@mantine/core';

import { formatExaggerationMultiplier, TERRAIN_EXAGGERATION_PRESETS } from './terrainExaggeration';

interface TerrainExaggerationControlsProps {
  readonly value: number;
  readonly onChange: (value: number) => void;
  readonly min: number;
  readonly max: number;
  /** En el panel móvil los presets y el slider ocupan el ancho y el pulgar llega a 44px. */
  readonly layout?: 'inline' | 'touch';
}

export function TerrainExaggerationControls({
  value,
  onChange,
  min,
  max,
  layout = 'inline',
}: TerrainExaggerationControlsProps) {
  const touch = layout === 'touch';
  const presetButtons = TERRAIN_EXAGGERATION_PRESETS.map((preset) => (
    <Tooltip key={preset.value} label={preset.tooltip} withArrow>
      <Button
        size={touch ? 'sm' : 'xs'}
        variant={value === preset.value ? 'filled' : 'default'}
        aria-pressed={value === preset.value}
        onClick={() => onChange(preset.value)}
      >
        {preset.label}
      </Button>
    </Tooltip>
  ));
  const presets = touch ? (
    <Group gap="xs" wrap="wrap">
      {presetButtons}
    </Group>
  ) : (
    <Button.Group>{presetButtons}</Button.Group>
  );
  const slider = (
    <Box w={touch ? '100%' : 140}>
      <Slider
        value={value}
        onChange={onChange}
        min={min}
        max={max}
        step={1}
        size={touch ? 'md' : 'xs'}
        thumbSize={touch ? 44 : undefined}
        label={(val) => formatExaggerationMultiplier(val)}
        marks={[
          { value: 1, label: formatExaggerationMultiplier(1) },
          { value: 100, label: formatExaggerationMultiplier(100) },
          { value: 200, label: formatExaggerationMultiplier(200) },
        ]}
        aria-label="Exageración vertical"
      />
    </Box>
  );

  if (touch) {
    return (
      <Stack gap="xs">
        <Text size="xs" c="dimmed">
          Exageración vertical:
        </Text>
        {presets}
        {slider}
      </Stack>
    );
  }

  return (
    <Group gap="xs" align="center" wrap="wrap">
      <Text size="xs" c="dimmed">
        Exageración vertical:
      </Text>
      {presets}
      {slider}
    </Group>
  );
}
