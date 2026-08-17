import {
  ActionIcon,
  Button,
  Checkbox,
  Group,
  Paper,
  Select,
  Stack,
  Text,
} from '@mantine/core';
import type { FeatureCollection } from 'geojson';
import { useMemo } from 'react';
import {
  HAZARD_DEFAULT_PRECIP_MONTH,
  HAZARD_DEFAULT_RISK_CLASSES,
  type PrecipMonth,
  RISK_CLASS_LABELS,
  type RiskClass,
} from '../../hooks/useHazardUrlState';
import { IconChevronDown, IconChevronUp, IconCloudRain, IconRefresh } from '../ui/icons';

const MONTH_OPTIONS: { value: PrecipMonth; label: string }[] = [
  { value: 'anual', label: 'Anual' },
  { value: '01', label: 'Enero' },
  { value: '02', label: 'Febrero' },
  { value: '03', label: 'Marzo' },
  { value: '04', label: 'Abril' },
  { value: '05', label: 'Mayo' },
  { value: '06', label: 'Junio' },
  { value: '07', label: 'Julio' },
  { value: '08', label: 'Agosto' },
  { value: '09', label: 'Septiembre' },
  { value: '10', label: 'Octubre' },
  { value: '11', label: 'Noviembre' },
  { value: '12', label: 'Diciembre' },
];

interface HazardControlsMobileProps {
  readonly basin: string | null;
  readonly setBasin: (id: string | null) => void;
  readonly riskClasses: RiskClass[];
  readonly setRiskClasses: (classes: RiskClass[]) => void;
  readonly precipMonth: PrecipMonth;
  readonly setPrecipMonth: (month: PrecipMonth) => void;
  readonly resetToDefaults: () => void;
  readonly expanded: boolean;
  readonly setExpanded: (expanded: boolean) => void;
  readonly basins: FeatureCollection | null | undefined;
}

const SHEET_BG = 'light-dark(rgba(255,255,255,0.97), rgba(36,36,36,0.97))';

export function HazardControlsMobile({
  basin,
  setBasin,
  riskClasses,
  setRiskClasses,
  precipMonth,
  setPrecipMonth,
  resetToDefaults,
  expanded,
  setExpanded,
  basins,
}: HazardControlsMobileProps) {
  const basinOptions = useMemo(() => {
    const options = (basins?.features ?? [])
      .map((feature) => {
        const id = String(feature.properties?.id ?? feature.id ?? '');
        const name = String(feature.properties?.nombre ?? feature.properties?.name ?? id);
        return { value: id, label: name };
      })
      .filter((opt) => opt.value !== '');
    return [{ value: '', label: 'Mostrar todo' }, ...options];
  }, [basins]);

  const allRiskClassesSelected = riskClasses.length === RISK_CLASS_LABELS.length;

  const toggleRiskClass = (label: RiskClass) => {
    const next = riskClasses.includes(label)
      ? riskClasses.filter((c) => c !== label)
      : [...riskClasses, label];
    setRiskClasses(next.length > 0 ? next : [...HAZARD_DEFAULT_RISK_CLASSES]);
  };

  if (!expanded) {
    return (
      <Paper
        shadow="md"
        p="xs"
        radius="md"
        style={{
          background: SHEET_BG,
          backdropFilter: 'blur(6px)',
        }}
        data-testid="hazard-controls-mobile-chip"
      >
        <Button
          variant="light"
          size="sm"
          leftSection={<IconCloudRain size={18} />}
          rightSection={<IconChevronUp size={16} />}
          onClick={() => setExpanded(true)}
          fullWidth
          data-testid="hazard-mobile-expand"
        >
          Multi-Hazard
        </Button>
      </Paper>
    );
  }

  return (
    <Paper
      shadow="md"
      p="sm"
      radius="md"
      style={{
        background: SHEET_BG,
        backdropFilter: 'blur(6px)',
        maxHeight: '60vh',
        display: 'flex',
        flexDirection: 'column',
      }}
      data-testid="hazard-controls-mobile-sheet"
    >
      <Stack gap="sm">
        <Group justify="space-between" wrap="nowrap">
          <Group gap="xs" wrap="nowrap">
            <IconCloudRain size={18} />
            <Text size="sm" fw={600}>
              Multi-Hazard
            </Text>
          </Group>
          <ActionIcon
            variant="subtle"
            size="sm"
            color="gray"
            aria-label="Colapsar panel multi-hazard"
            onClick={() => setExpanded(false)}
            data-testid="hazard-mobile-collapse"
          >
            <IconChevronDown size={16} />
          </ActionIcon>
        </Group>

        <Stack gap={4}>
          <Text size="xs" fw={600} c="dimmed">
            Cuenca
          </Text>
          <Select
            size="xs"
            aria-label="Seleccionar cuenca"
            placeholder="Todas las cuencas"
            value={basin ?? ''}
            onChange={(value) => setBasin(value || null)}
            data={basinOptions}
            data-testid="hazard-basin-select-mobile"
          />
        </Stack>

        <Stack gap={4}>
          <Group justify="space-between" wrap="nowrap">
            <Text size="xs" fw={600} c="dimmed">
              Clases de riesgo
            </Text>
            {!allRiskClassesSelected && (
              <Text size="9px" c="orange" data-testid="hazard-risk-filter-hint-mobile">
                Algunas ocultas
              </Text>
            )}
          </Group>
          {RISK_CLASS_LABELS.map((label) => (
            <Checkbox
              key={label}
              size="xs"
              label={label}
              checked={riskClasses.includes(label)}
              onChange={() => toggleRiskClass(label)}
              data-testid={`hazard-risk-class-mobile-${label.toLowerCase()}`}
            />
          ))}
        </Stack>

        <Stack gap={4}>
          <Text size="xs" fw={600} c="dimmed">
            Precipitación CHIRPS
          </Text>
          <Select
            size="xs"
            aria-label="Seleccionar mes de precipitación"
            value={precipMonth}
            onChange={(value) =>
              setPrecipMonth((value as PrecipMonth) ?? HAZARD_DEFAULT_PRECIP_MONTH)
            }
            data={MONTH_OPTIONS}
            data-testid="hazard-precip-month-select-mobile"
          />
        </Stack>

        <Button
          variant="light"
          size="xs"
          fullWidth
          leftSection={<IconRefresh size={14} />}
          onClick={resetToDefaults}
          data-testid="hazard-reset-mobile"
        >
          Restablecer vista
        </Button>
      </Stack>
    </Paper>
  );
}
