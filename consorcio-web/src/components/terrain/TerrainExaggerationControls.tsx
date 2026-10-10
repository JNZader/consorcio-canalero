import { Box, Button, Group, Slider, Text, Tooltip } from '@mantine/core';

import { TERRAIN_EXAGGERATION_PRESETS } from './terrainExaggeration';

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
              size="compact-xs"
              variant={value === preset.value ? 'filled' : 'default'}
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
          label={(val) => `${val}x`}
          marks={[
            { value: 1, label: '1x' },
            { value: 100, label: '100x' },
            { value: 200, label: '200x' },
          ]}
          aria-label="Exageración vertical"
        />
      </Box>
    </Group>
  );
}
