import { Box, Button, Group, Slider, Text, Tooltip } from '@mantine/core';

import { formatExaggerationMultiplier, TERRAIN_EXAGGERATION_PRESETS } from './terrainExaggeration';

interface TerrainExaggerationControlsProps {
  readonly value: number;
  readonly onChange: (value: number) => void;
  readonly min: number;
  readonly max: number;
}

export function TerrainExaggerationControls({
  value,
  onChange,
  min,
  max,
}: TerrainExaggerationControlsProps) {
  return (
    <Group gap="xs" align="center" wrap="wrap">
      <Text size="xs" c="dimmed">
        Exageración vertical:
      </Text>
      <Button.Group>
        {TERRAIN_EXAGGERATION_PRESETS.map((preset) => (
          <Tooltip key={preset.value} label={preset.tooltip} withArrow>
            <Button
              size="xs"
              variant={value === preset.value ? 'filled' : 'default'}
              aria-pressed={value === preset.value}
              onClick={() => onChange(preset.value)}
            >
              {preset.label}
            </Button>
          </Tooltip>
        ))}
      </Button.Group>
      <Box w={140}>
        <Slider
          value={value}
          onChange={onChange}
          min={min}
          max={max}
          step={1}
          size="xs"
          label={(val) => formatExaggerationMultiplier(val)}
          marks={[
            { value: 1, label: formatExaggerationMultiplier(1) },
            { value: 100, label: formatExaggerationMultiplier(100) },
            { value: 200, label: formatExaggerationMultiplier(200) },
          ]}
          aria-label="Exageración vertical"
        />
      </Box>
    </Group>
  );
}
