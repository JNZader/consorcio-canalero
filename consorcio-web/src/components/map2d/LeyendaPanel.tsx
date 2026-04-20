import { Box, ColorSwatch, Divider, Group, Paper, Stack, Text } from '@mantine/core';
import { memo, useState } from 'react';
import type { ConsorcioInfo } from '../../hooks/useCaminosColoreados';
import styles from '../../styles/components/map.module.css';
import { PILAR_VERDE_COLORS } from './pilarVerdeLayers';

interface LegendItem {
  color: string;
  label: string;
  type: string;
}

function LegendItemIndicator({ item }: { item: LegendItem }) {
  if (item.type === 'border') {
    return (
      <Box className={styles.legendItemBorder} style={{ border: `2px solid ${item.color}` }} />
    );
  }
  if (item.type === 'line') {
    return <Box className={styles.legendItemLine} style={{ backgroundColor: item.color }} />;
  }
  return <ColorSwatch color={item.color} size={16} withShadow={false} />;
}

/**
 * Color chips for the "Años en BPA" gradient (años_bpa 1..7).
 * Colors MUST match the MapLibre paint expression in
 * `buildBpaHistoricoFillPaint()` exactly — single source of truth is
 * `PILAR_VERDE_COLORS.bpaHistoricoStop{1,3,5,7}`.
 */
const BPA_HISTORICO_LEGEND_CHIPS = [
  { label: '1', color: PILAR_VERDE_COLORS.bpaHistoricoStop1 },
  { label: '3', color: PILAR_VERDE_COLORS.bpaHistoricoStop3 },
  { label: '5', color: PILAR_VERDE_COLORS.bpaHistoricoStop5 },
  { label: '7', color: PILAR_VERDE_COLORS.bpaHistoricoStop7 },
] as const;

interface LeyendaPanelProps {
  readonly consorcios?: ConsorcioInfo[];
  readonly customItems?: LegendItem[];
  readonly floating?: boolean;
  /**
   * Render the "Años en BPA" color-scale section. Enable when the
   * `pilar_verde_bpa_historico` layer is visible so the map gradient has a
   * matching legend.
   */
  readonly pilarVerdeBpaHistoricoVisible?: boolean;
}

export const LeyendaPanel = memo(function LeyendaPanel({
  consorcios = [],
  customItems = [],
  floating = true,
  pilarVerdeBpaHistoricoVisible = false,
}: LeyendaPanelProps) {
  const [showConsorcios, setShowConsorcios] = useState(false);

  const legendItems =
    customItems.length > 0 ? customItems : [{ color: '#FF0000', label: 'Zona Consorcio', type: 'border' }];

  return (
    <Paper
      shadow="md"
      p="sm"
      radius="md"
      className={floating ? styles.legendPanel : undefined}
      style={
        floating
          ? { maxHeight: '80vh', overflowY: 'auto' }
          : {
              maxHeight: '80vh',
              overflowY: 'auto',
              background: 'light-dark(rgba(255,255,255,0.94), rgba(36,36,36,0.94))',
              backdropFilter: 'blur(6px)',
            }
      }
    >
      <Text fw={600} size="sm" mb="xs">
        Leyenda
      </Text>
      <Stack gap={4}>
        {legendItems.map((item) => (
          <Group key={item.label} gap="xs">
            <LegendItemIndicator item={item} />
            <Text size="xs">{item.label}</Text>
          </Group>
        ))}
        {consorcios.length > 0 && (
          <>
            <Divider my={4} />
            <Group
              gap="xs"
              style={{ cursor: 'pointer' }}
              onClick={() => setShowConsorcios(!showConsorcios)}
            >
              <Text fw={600} size="xs" c="dimmed">
                Red Vial ({consorcios.length} consorcios)
              </Text>
              <Text size="xs" c="dimmed">
                {showConsorcios ? '▼' : '►'}
              </Text>
            </Group>
            {showConsorcios && (
              <Stack gap={2} pl="xs">
                {consorcios.map((consorcio) => (
                  <Group key={consorcio.codigo} gap="xs" wrap="nowrap">
                    <Box
                      style={{
                        width: 16,
                        height: 3,
                        backgroundColor: consorcio.color,
                        borderRadius: 1,
                      }}
                    />
                    <Text
                      size="xs"
                      truncate
                      style={{ maxWidth: 150 }}
                      title={`${consorcio.nombre} - ${consorcio.longitud_km} km`}
                    >
                      {consorcio.codigo} ({consorcio.longitud_km.toFixed(0)} km)
                    </Text>
                  </Group>
                ))}
              </Stack>
            )}
          </>
        )}
        {pilarVerdeBpaHistoricoVisible && (
          <>
            <Divider my={4} />
            <Text size="xs" c="dimmed" fw={500}>
              Años en BPA:
            </Text>
            <Group gap="xs" wrap="nowrap" data-testid="bpa-historico-legend">
              {BPA_HISTORICO_LEGEND_CHIPS.map((chip) => (
                <Group key={chip.label} gap={4} wrap="nowrap">
                  <span
                    data-color={chip.color}
                    aria-label={`${chip.label} años`}
                    style={{
                      display: 'inline-block',
                      width: 12,
                      height: 12,
                      backgroundColor: chip.color,
                      border: '1px solid #166534',
                      borderRadius: 2,
                    }}
                  />
                  <Text size="xs">{chip.label}</Text>
                </Group>
              ))}
            </Group>
          </>
        )}
      </Stack>
    </Paper>
  );
});
