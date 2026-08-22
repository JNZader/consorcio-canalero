import {
  ActionIcon,
  Button,
  Checkbox,
  Divider,
  Group,
  Paper,
  Select,
  Stack,
  Text,
} from '@mantine/core';
import { useEffect, useRef } from 'react';

import {
  HAZARD_RISK_CLASSES,
  PRECIPITATION_PERIOD,
  type HazardControlsProps,

  type PrecipitationPeriod,
} from './hazardControls.types';

const GLASS_STYLE = {
  background: 'light-dark(rgba(255,255,255,0.94), rgba(36,36,36,0.94))',
  backdropFilter: 'blur(6px)',
} as const;

const MONTH_OPTIONS = [
  { value: PRECIPITATION_PERIOD.ANNUAL, label: 'Anual' },
  { value: PRECIPITATION_PERIOD.JANUARY, label: 'Enero' },
  { value: PRECIPITATION_PERIOD.FEBRUARY, label: 'Febrero' },
  { value: PRECIPITATION_PERIOD.MARCH, label: 'Marzo' },
  { value: PRECIPITATION_PERIOD.APRIL, label: 'Abril' },
  { value: PRECIPITATION_PERIOD.MAY, label: 'Mayo' },
  { value: PRECIPITATION_PERIOD.JUNE, label: 'Junio' },
  { value: PRECIPITATION_PERIOD.JULY, label: 'Julio' },
  { value: PRECIPITATION_PERIOD.AUGUST, label: 'Agosto' },
  { value: PRECIPITATION_PERIOD.SEPTEMBER, label: 'Septiembre' },
  { value: PRECIPITATION_PERIOD.OCTOBER, label: 'Octubre' },
  { value: PRECIPITATION_PERIOD.NOVEMBER, label: 'Noviembre' },
  { value: PRECIPITATION_PERIOD.DECEMBER, label: 'Diciembre' },
];

export function HazardControls({
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
      <Paper
        shadow="md"
        p="xs"
        radius="md"
        role="region"
        aria-label="Controles de riesgos"
        data-testid="hazard-controls-desktop-collapsed"
        style={{ ...GLASS_STYLE, left: 16, position: 'absolute', top: 96, zIndex: 3 }}
      >
        <Button
          size="compact-sm"
          variant="subtle"
          aria-label="Expandir controles de riesgos"
          onClick={() => onCollapsedChange(false)}
        >
          Riesgos
        </Button>
      </Paper>
    );
  }

  return (
    <Paper
      shadow="md"
      p="sm"
      radius="md"
      role="region"
      aria-label="Controles de riesgos"
      data-testid="hazard-controls-desktop"
      style={{ ...GLASS_STYLE, left: 16, maxWidth: 280, position: 'absolute', top: 96, zIndex: 3 }}
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
            ‹
          </ActionIcon>
        </Group>

        <Select
          size="xs"
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
              size="xs"
              label={riskClass}
              checked={visibleRiskClasses.includes(riskClass)}
              onChange={(event) => onRiskClassChange(riskClass, event.currentTarget.checked)}
            />
          ))}
        </Stack>

        <Select
          size="xs"
          label="Precipitación normal"
          aria-label="Periodo de precipitación"
          value={precipitationPeriod}
          onChange={(value) => {
            if (value) onPrecipitationPeriodChange(value as PrecipitationPeriod);
          }}
          data={MONTH_OPTIONS}
        />

        <Button size="compact-sm" variant="light" onClick={onReset}>
          Restablecer
        </Button>
      </Stack>
    </Paper>
  );
}
