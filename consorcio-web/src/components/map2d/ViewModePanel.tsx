import { Center, Paper, SegmentedControl, Stack, Text, Tooltip } from '@mantine/core';
import { type ReactNode, memo, useMemo } from 'react';
import { IconGitCompare, IconLayers, IconPhoto } from '../ui/icons';

export const MAP_VIEW_MODE = {
  BASE: 'base',
  SINGLE: 'single',
  COMPARISON: 'comparison',
} as const;

export type ViewMode = (typeof MAP_VIEW_MODE)[keyof typeof MAP_VIEW_MODE];

interface ViewModePanelProps {
  readonly viewMode: ViewMode;
  readonly onViewModeChange: (mode: ViewMode) => void;
  readonly hasSingleImage: boolean;
  readonly hasComparison: boolean;
  readonly singleImageInfo?: { sensor: string; date: string } | null;
  readonly comparisonInfo?: { leftDate: string; rightDate: string } | null;
}

export const ViewModePanel = memo(function ViewModePanel({
  viewMode,
  onViewModeChange,
  hasSingleImage,
  hasComparison,
  singleImageInfo,
  comparisonInfo,
}: ViewModePanelProps) {
  const options = useMemo(() => {
    const items: Array<{ value: string; label: ReactNode }> = [
      {
        value: MAP_VIEW_MODE.BASE,
        label: (
          <Tooltip label="Solo mapa base" position="bottom" withArrow>
            <Center style={{ gap: 6 }}>
              <IconLayers size={14} />
              <Text size="xs">Base</Text>
            </Center>
          </Tooltip>
        ),
      },
    ];

    if (hasSingleImage) {
      items.push({
        value: MAP_VIEW_MODE.SINGLE,
        label: (
          <Tooltip
            label={
              singleImageInfo
                ? `${singleImageInfo.sensor} - ${singleImageInfo.date}`
                : 'Imagen satelital'
            }
            position="bottom"
            withArrow
          >
            <Center style={{ gap: 6 }}>
              <IconPhoto size={14} />
              <Text size="xs">Imagen</Text>
            </Center>
          </Tooltip>
        ),
      });
    }

    if (hasComparison) {
      items.push({
        value: MAP_VIEW_MODE.COMPARISON,
        label: (
          <Tooltip
            label={
              comparisonInfo
                ? `Comparar: ${comparisonInfo.leftDate} vs ${comparisonInfo.rightDate}`
                : 'Comparacion'
            }
            position="bottom"
            withArrow
          >
            <Center style={{ gap: 6 }}>
              <IconGitCompare size={14} />
              <Text size="xs">Comparar</Text>
            </Center>
          </Tooltip>
        ),
      });
    }

    return items;
  }, [comparisonInfo, hasComparison, hasSingleImage, singleImageInfo]);

  if (!hasSingleImage && !hasComparison) return null;

  return (
    <Paper
      shadow="md"
      p="xs"
      radius="md"
      style={{
        background: 'light-dark(rgba(255,255,255,0.94), rgba(36,36,36,0.94))',
        backdropFilter: 'blur(6px)',
      }}
    >
      <Stack gap={4}>
        <Text size="xs" fw={600} c="dimmed">
          Vista satelital
        </Text>
        <SegmentedControl
          size="xs"
          fullWidth
          value={viewMode}
          onChange={(value) => onViewModeChange(value as ViewMode)}
          data={options}
        />
      </Stack>
    </Paper>
  );
});
