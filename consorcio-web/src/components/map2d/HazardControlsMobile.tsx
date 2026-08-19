import { ActionIcon, Button, Checkbox, Divider, Group, Paper, Select, Stack, Text } from '@mantine/core';
import { useEffect, useRef } from 'react';

import {
  HAZARD_RISK_CLASSES,
  PRECIPITATION_PERIOD,
  type HazardControlsProps,
  type PrecipitationPeriod,
} from './hazardControls.types';

const MONTH_OPTIONS = [
  { value: PRECIPITATION_PERIOD.ANNUAL, label: 'Anual' },
  ...Array.from({ length: 12 }, (_, index) => {
    const month = String(index + 1).padStart(2, '0') as PrecipitationPeriod;
    return { value: month, label: `Mes ${month}` };
  }),
];

const SHEET_STYLE = {
  background: 'light-dark(rgba(255,255,255,0.97), rgba(36,36,36,0.97))',
  backdropFilter: 'blur(10px)',
  bottom: 12,
  left: 12,
  maxHeight: '60vh',
  overflowY: 'auto',
  position: 'fixed',
  right: 12,
  zIndex: 4,
} as const;

export function HazardControlsMobile({
  basins,
  selectedBasinId,
  onBasinChange,
  visibleRiskClasses,
  onRiskClassChange,
  precipitationPeriod,
  onPrecipitationPeriodChange,
  onReset,
  collapsed,
  onCollapsedChange,
  fichaOpen = false,
  onFichaMinimize,
}: HazardControlsProps) {
  const fichaWasOpen = useRef(false);

  useEffect(() => {
    if (fichaOpen && !fichaWasOpen.current) onFichaMinimize?.();
    fichaWasOpen.current = fichaOpen;
  }, [fichaOpen, onFichaMinimize]);

  const effectiveCollapsed = collapsed || fichaOpen;
  const basinOptions = [
    { value: 'all', label: 'Mostrar todo' },
    ...basins.map((basin) => ({ value: basin.id, label: basin.label })),
  ];

  if (effectiveCollapsed) {
    return (
      <Button
        radius="xl"
        variant="filled"
        data-testid="hazard-controls-mobile-chip"
        aria-label="Expandir controles de riesgos"
        style={{ bottom: 16, left: 16, position: 'fixed', zIndex: 4 }}
        onClick={() => onCollapsedChange(false)}
      >
        Riesgos
      </Button>
    );
  }

  return (
    <Paper
      shadow="xl"
      p="md"
      radius="lg"
      role="region"
      aria-label="Controles de riesgos móviles"
      data-testid="hazard-controls-mobile-sheet"
      style={SHEET_STYLE}
    >
      <Stack gap="sm">
        <Group justify="space-between" wrap="nowrap">
          <div>
            <Text fw={600} size="sm">
              Riesgos
            </Text>
            <Text c="dimmed" size="xs">
              Análisis por cuenca
            </Text>
          </div>
          <ActionIcon
            variant="subtle"
            color="gray"
            aria-label="Contraer controles de riesgos"
            onClick={() => onCollapsedChange(true)}
          >
            ↓
          </ActionIcon>
        </Group>
        <Select
          size="sm"
          label="Cuenca"
          aria-label="Seleccionar cuenca"
          value={selectedBasinId ?? 'all'}
          onChange={(value) => onBasinChange(!value || value === 'all' ? null : value)}
          data={basinOptions}
        />
        <Divider />
        <Stack gap={4}>
          <Text fw={500} size="xs">
            Clases de riesgo
          </Text>
          {HAZARD_RISK_CLASSES.map((riskClass) => (
            <Checkbox
              key={riskClass}
              label={riskClass}
              checked={visibleRiskClasses.includes(riskClass)}
              onChange={(event) => onRiskClassChange(riskClass, event.currentTarget.checked)}
            />
          ))}
        </Stack>
        <Select
          size="sm"
          label="Precipitación normal"
          aria-label="Periodo de precipitación"
          value={precipitationPeriod}
          onChange={(value) => {
            if (value) onPrecipitationPeriodChange(value as PrecipitationPeriod);
          }}
          data={MONTH_OPTIONS}
        />
        <Button variant="light" onClick={onReset}>
          Restablecer
        </Button>
      </Stack>
    </Paper>
  );
}
