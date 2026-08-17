import {
  ActionIcon,
  Button,
  Checkbox,
  Group,
  Paper,
  Select,
  Stack,
  Text,
  Tooltip,
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
import { IconArrowLeft, IconArrowRight, IconCloudRain, IconRefresh } from '../ui/icons';

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

interface HazardControlsProps {
  readonly basin: string | null;
  readonly setBasin: (id: string | null) => void;
  readonly riskClasses: RiskClass[];
  readonly setRiskClasses: (classes: RiskClass[]) => void;
  readonly precipMonth: PrecipMonth;
  readonly setPrecipMonth: (month: PrecipMonth) => void;
  readonly resetToDefaults: () => void;
  readonly panelOpen: boolean;
  readonly setPanelOpen: (open: boolean) => void;
  readonly basins: FeatureCollection | null | undefined;
}

const GLASS_BG = 'light-dark(rgba(255,255,255,0.94), rgba(36,36,36,0.94))';

export function HazardControls({
  basin,
  setBasin,
  riskClasses,
  setRiskClasses,
  precipMonth,
  setPrecipMonth,
  resetToDefaults,
  panelOpen,
  setPanelOpen,
  basins,
}: HazardControlsProps) {
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

  const allRiskClassesSelected = useMemo(
    () => RISK_CLASS_LABELS.length === riskClasses.length,
    [riskClasses.length]
  );

  const toggleRiskClass = (label: RiskClass) => {
    const next = riskClasses.includes(label)
      ? riskClasses.filter((c) => c !== label)
      : [...riskClasses, label];
    setRiskClasses(next.length > 0 ? next : [...HAZARD_DEFAULT_RISK_CLASSES]);
  };

  return (
    <Paper
      shadow="md"
      p="sm"
      radius="md"
      style={{
        background: GLASS_BG,
        backdropFilter: 'blur(6px)',
        width: panelOpen ? 280 : 44,
        minHeight: 44,
      }}
      data-testid="hazard-controls-desktop"
    >
      <Stack gap="sm">
        <Group justify="space-between" wrap="nowrap">
          <Group gap="xs" wrap="nowrap">
            <IconCloudRain size={18} />
            {panelOpen && (
              <Text size="sm" fw={600}>
                Multi-Hazard
              </Text>
            )}
          </Group>
          <Group gap={4} wrap="nowrap">
            {panelOpen && (
              <Tooltip label="Restablecer vista">
                <ActionIcon
                  variant="subtle"
                  size="sm"
                  color="gray"
                  aria-label="Restablecer vista multi-hazard"
                  onClick={resetToDefaults}
                  data-testid="hazard-reset-button"
                >
                  <IconRefresh size={16} />
                </ActionIcon>
              </Tooltip>
            )}
            <Tooltip label={panelOpen ? 'Colapsar panel' : 'Expandir panel'}>
              <ActionIcon
                variant="subtle"
                size="sm"
                color="gray"
                aria-label={panelOpen ? 'Colapsar panel multi-hazard' : 'Expandir panel multi-hazard'}
                onClick={() => setPanelOpen(!panelOpen)}
                data-testid="hazard-toggle-panel"
              >
                {panelOpen ? <IconArrowLeft size={16} /> : <IconArrowRight size={16} />}
              </ActionIcon>
            </Tooltip>
          </Group>
        </Group>

        {panelOpen && (
          <>
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
                data-testid="hazard-basin-select"
              />
            </Stack>

            <Stack gap={4}>
              <Group justify="space-between" wrap="nowrap">
                <Text size="xs" fw={600} c="dimmed">
                  Clases de riesgo
                </Text>
                {!allRiskClassesSelected && (
                  <Text size="9px" c="orange" data-testid="hazard-risk-filter-hint">
                    Algunas clases ocultas
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
                  data-testid={`hazard-risk-class-${label.toLowerCase()}`}
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
                onChange={(value) => setPrecipMonth((value as PrecipMonth) ?? HAZARD_DEFAULT_PRECIP_MONTH)}
                data={MONTH_OPTIONS}
                data-testid="hazard-precip-month-select"
              />
            </Stack>

            <Button
              variant="light"
              size="xs"
              fullWidth
              leftSection={<IconRefresh size={14} />}
              onClick={resetToDefaults}
              data-testid="hazard-reset-full"
            >
              Restablecer vista
            </Button>
          </>
        )}
      </Stack>
    </Paper>
  );
}
