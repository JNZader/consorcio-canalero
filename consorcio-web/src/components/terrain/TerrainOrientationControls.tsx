import { Button, Group, Text, Tooltip } from '@mantine/core';

interface TerrainOrientationControlsProps {
  readonly onNorth: () => void;
  readonly onNadir: () => void;
  readonly onReset: () => void;
}

export function TerrainOrientationControls({
  onNorth,
  onNadir,
  onReset,
}: TerrainOrientationControlsProps) {
  return (
    <Group gap="xs" align="center" wrap="wrap">
      <Text size="xs" c="dimmed">
        Cámara:
      </Text>
      <Tooltip label="Norte arriba (N)" withArrow>
        <Button size="compact-xs" variant="default" onClick={onNorth}>
          Norte
        </Button>
      </Tooltip>
      <Tooltip label="Vista cenital (U)" withArrow>
        <Button size="compact-xs" variant="default" onClick={onNadir}>
          Cenital
        </Button>
      </Tooltip>
      <Tooltip label="Norte + cenital (R)" withArrow>
        <Button size="compact-xs" variant="default" onClick={onReset}>
          Reset
        </Button>
      </Tooltip>
    </Group>
  );
}
