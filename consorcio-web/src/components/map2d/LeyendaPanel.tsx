import { Box, ColorSwatch, Divider, Group, Paper, Stack, Text } from '@mantine/core';
import { memo, useState, type CSSProperties } from 'react';
import type { ConsorcioInfo } from '../../hooks/useCaminosColoreados';
import styles from '../../styles/components/map.module.css';
import { CollapsibleSection } from '../ui/CollapsibleSection';
import { CANALES_COLORS } from './canalesLayers';
import { PILAR_VERDE_COLORS } from './pilarVerdeLayers';
import { ALL_ETAPAS, type Etapa } from '../../types/canales';

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

/**
 * Renders a single color chip + a Spanish label — used by the 4 simple Pilar
 * Verde layer legends (agro_aceptada / agro_presentada / agro_zonas /
 * porcentaje_forestacion). Kept in-file to match the visual weight of the
 * existing `BPA_HISTORICO_LEGEND_CHIPS` block without introducing a public
 * component. Colors are passed by the caller from `PILAR_VERDE_COLORS` — the
 * single source of truth for the MapLibre paints.
 */
function SimpleColorLegendChip({
  color,
  label,
  testId,
}: {
  readonly color: string;
  readonly label: string;
  readonly testId: string;
}) {
  return (
    <Group gap="xs" wrap="nowrap" data-testid={testId}>
      <span
        data-color={color}
        aria-label={label}
        style={{
          display: 'inline-block',
          width: 12,
          height: 12,
          backgroundColor: color,
          border: '1px solid rgba(0, 0, 0, 0.25)',
          borderRadius: 2,
        }}
      />
      <Text size="xs">{label}</Text>
    </Group>
  );
}

/**
 * Single-row chip used by the Canales Relevados legend — solid line
 * (12×2 colored bar) + label. Visually hints at the MapLibre line layer.
 */
function CanalSolidLineChip({
  color,
  label,
  testId,
}: {
  readonly color: string;
  readonly label: string;
  readonly testId: string;
}) {
  return (
    <Group gap="xs" wrap="nowrap" data-testid={testId} data-color={color}>
      <span
        aria-label={label}
        style={{
          display: 'inline-block',
          width: 18,
          height: 3,
          backgroundColor: color,
          borderRadius: 1,
        }}
      />
      <Text size="xs">{label}</Text>
    </Group>
  );
}

/**
 * Single-row chip used by the Canales Propuestos legend — DASHED line
 * (rendered as an inline SVG with `strokeDasharray` so the dashed pattern
 * is visually unambiguous AND structurally testable via the DOM). The
 * wrapper carries `data-dashed="true"` for deterministic DOM assertions.
 */
function CanalDashedLineChip({
  color,
  label,
  testId,
}: {
  readonly color: string;
  readonly label: string;
  readonly testId: string;
}) {
  return (
    <Group
      gap="xs"
      wrap="nowrap"
      data-testid={testId}
      data-color={color}
      data-dashed="true"
    >
      <svg
        width={18}
        height={3}
        role="img"
        aria-label={label}
        style={{ display: 'inline-block' }}
      >
        <line
          x1={0}
          y1={1.5}
          x2={18}
          y2={1.5}
          stroke={color}
          strokeWidth={2}
          strokeDasharray="4,2"
        />
      </svg>
      <Text size="xs">{label}</Text>
    </Group>
  );
}

/**
 * Color + label pairs for the propuestos legend — ordered by priority
 * (Alta → Largo plazo) to match the map paint and the filter UI.
 */
const PROPUESTOS_LEGEND_ROWS: ReadonlyArray<{ etapa: Etapa; color: string }> =
  ALL_ETAPAS.map((etapa) => {
    switch (etapa) {
      case 'Alta':
        return { etapa, color: CANALES_COLORS.propuestoAlta };
      case 'Media-Alta':
        return { etapa, color: CANALES_COLORS.propuestoMediaAlta };
      case 'Media':
        return { etapa, color: CANALES_COLORS.propuestoMedia };
      case 'Opcional':
        return { etapa, color: CANALES_COLORS.propuestoOpcional };
      case 'Largo plazo':
        return { etapa, color: CANALES_COLORS.propuestoLargoPlazo };
    }
  });

interface LeyendaPanelProps {
  readonly consorcios?: ConsorcioInfo[];
  readonly customItems?: LegendItem[];
  readonly floating?: boolean;
  /**
   * When `true`, the panel renders WITHOUT the `.legendPanel` absolute-
   * positioning class and WITHOUT the `floating` inline background — the
   * parent container owns layout and positioning.
   *
   * Use this when composing the panel inside another flex container
   * (e.g. the side-by-side top-left stack in `MapUiPanels`). This flag
   * overrides `floating` — if `embedded={true}`, `floating` has no effect.
   *
   * Default: `false` (backwards compatible — the existing `floating` logic
   * continues to apply).
   */
  readonly embedded?: boolean;
  /** Optional fixed width in pixels for embedded mode. */
  readonly width?: number;
  /** Optional extra inline style overrides (merged last). */
  readonly style?: CSSProperties;
  /** Optional `data-testid` forwarded to the root Paper element. */
  readonly 'data-testid'?: string;
  /**
   * Render the "Años en BPA" color-scale section. Enable when the
   * `pilar_verde_bpa_historico` layer is visible so the map gradient has a
   * matching legend.
   */
  readonly pilarVerdeBpaHistoricoVisible?: boolean;
  /** Render the agro-aceptada (green / compliant) single-chip legend. */
  readonly pilarVerdeAgroAceptadaVisible?: boolean;
  /** Render the agro-presentada (red / non-compliant) single-chip legend. */
  readonly pilarVerdeAgroPresentadaVisible?: boolean;
  /** Render the agroforestal zonas (cyan / context) single-chip legend. */
  readonly pilarVerdeAgroZonasVisible?: boolean;
  /**
   * Render the porcentaje forestación legend. Three violet chips correspond
   * to the categorized `step` paint expression (Baja / Media / Alta) — the
   * zone data only spans 2.1–2.88% so the buckets match the real
   * distribution, not the provincial 2–5% range.
   */
  readonly pilarVerdePorcentajeForestacionVisible?: boolean;
  /**
   * Render the "Canales Relevados" block (3 solid blue chips). Enable when
   * the `canales_relevados` master toggle is ON so the legend mirrors what
   * the map actually paints.
   */
  readonly pilarAzulCanalesRelevadosVisible?: boolean;
  /**
   * Render the "Canales Propuestos" block (5 dashed chips, one per etapa).
   * Enable when the `canales_propuestos` master toggle is ON.
   */
  readonly pilarAzulCanalesPropuestosVisible?: boolean;
}

export const LeyendaPanel = memo(function LeyendaPanel({
  consorcios = [],
  customItems = [],
  floating = true,
  embedded = false,
  width,
  style: styleOverride,
  'data-testid': dataTestId,
  pilarVerdeBpaHistoricoVisible = false,
  pilarVerdeAgroAceptadaVisible = false,
  pilarVerdeAgroPresentadaVisible = false,
  pilarVerdeAgroZonasVisible = false,
  pilarVerdePorcentajeForestacionVisible = false,
  pilarAzulCanalesRelevadosVisible = false,
  pilarAzulCanalesPropuestosVisible = false,
}: LeyendaPanelProps) {
  const [showConsorcios, setShowConsorcios] = useState(false);

  const legendItems =
    customItems.length > 0 ? customItems : [{ color: '#FF0000', label: 'Zona Consorcio', type: 'border' }];

  const hasSimplePilarVerdeLegends =
    pilarVerdeAgroAceptadaVisible ||
    pilarVerdeAgroPresentadaVisible ||
    pilarVerdeAgroZonasVisible ||
    pilarVerdePorcentajeForestacionVisible;

  // `embedded` wins over `floating`: when the panel is composed inside an
  // external layout container (e.g. the side-by-side top-left stack in 2D),
  // we must NOT apply the `.legendPanel` absolute-positioning class — it
  // would fight the parent's flex layout.
  const useLegendPanelClass = floating && !embedded;

  const baseStyle: CSSProperties = useLegendPanelClass
    ? { maxHeight: '80vh', overflowY: 'auto' }
    : {
        maxHeight: '80vh',
        overflowY: 'auto',
        background: 'light-dark(rgba(255,255,255,0.94), rgba(36,36,36,0.94))',
        backdropFilter: 'blur(6px)',
        ...(width !== undefined ? { width } : {}),
      };

  return (
    <Paper
      shadow="md"
      p="sm"
      radius="md"
      className={useLegendPanelClass ? styles.legendPanel : undefined}
      data-testid={dataTestId}
      style={{ ...baseStyle, ...(styleOverride ?? {}) }}
    >
      <CollapsibleSection title="Leyenda" testId="leyenda" titleSize="sm" titleWeight={600}>
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
        {hasSimplePilarVerdeLegends && <Divider my={4} />}
        {/*
          Order mirrors `PILAR_VERDE_Z_ORDER` intuition (most specific → most
          contextual):
            1. agro_aceptada       (green — compliant)
            2. agro_presentada     (red — non-compliant)
            3. agro_zonas          (cyan — zonas agroforestales)
            4. porcentaje_forestacion (violet — mandatory 2-5%)
        */}
        {pilarVerdeAgroAceptadaVisible && (
          <SimpleColorLegendChip
            color={PILAR_VERDE_COLORS.agroAceptadaFill}
            label="Cumplen ley forestal"
            testId="pilar-verde-agro-aceptada-legend"
          />
        )}
        {pilarVerdeAgroPresentadaVisible && (
          <SimpleColorLegendChip
            color={PILAR_VERDE_COLORS.agroPresentadaFill}
            label="No cumplen ley forestal"
            testId="pilar-verde-agro-presentada-legend"
          />
        )}
        {pilarVerdeAgroZonasVisible && (
          <Stack gap={2} data-testid="pilar-verde-agro-zonas-legend">
            <Text fw={500} size="xs">
              Zonas agroforestales
            </Text>
            <SimpleColorLegendChip
              color={PILAR_VERDE_COLORS.agroZonaRioTercero}
              label="Río Tercero Este"
              testId="pilar-verde-agro-zonas-legend-rio-tercero"
            />
            <SimpleColorLegendChip
              color={PILAR_VERDE_COLORS.agroZonaCarcarana}
              label="Río Carcarañá"
              testId="pilar-verde-agro-zonas-legend-carcarana"
            />
            <SimpleColorLegendChip
              color={PILAR_VERDE_COLORS.agroZonaTortugas}
              label="Arroyo Tortugas Este"
              testId="pilar-verde-agro-zonas-legend-tortugas"
            />
          </Stack>
        )}
        {pilarVerdePorcentajeForestacionVisible && (
          <Stack gap={2} data-testid="pilar-verde-porcentaje-forestacion-legend">
            <Text fw={500} size="xs">
              Forestación obligatoria
            </Text>
            <SimpleColorLegendChip
              color={PILAR_VERDE_COLORS.porcentajeForestacionBaja}
              label="Baja (≤ 2,3%)"
              testId="pilar-verde-porcentaje-forestacion-baja"
            />
            <SimpleColorLegendChip
              color={PILAR_VERDE_COLORS.porcentajeForestacionMedia}
              label="Media (2,4 – 2,6%)"
              testId="pilar-verde-porcentaje-forestacion-media"
            />
            <SimpleColorLegendChip
              color={PILAR_VERDE_COLORS.porcentajeForestacionAlta}
              label="Alta (≥ 2,7%)"
              testId="pilar-verde-porcentaje-forestacion-alta"
            />
          </Stack>
        )}
        {(pilarAzulCanalesRelevadosVisible || pilarAzulCanalesPropuestosVisible) && (
          <Divider my={4} />
        )}
        {pilarAzulCanalesRelevadosVisible && (
          <Stack gap={2} data-testid="canales-relevados-legend">
            <Text fw={500} size="xs">
              Canales Relevados
            </Text>
            <CanalSolidLineChip
              color={CANALES_COLORS.relevadoSinObra}
              label="Sin obra"
              testId="canal-relevado-chip-sin-obra"
            />
            <CanalSolidLineChip
              color={CANALES_COLORS.relevadoReadec}
              label="Readecuación"
              testId="canal-relevado-chip-readec"
            />
            <CanalSolidLineChip
              color={CANALES_COLORS.relevadoAsociada}
              label="Asociada"
              testId="canal-relevado-chip-asociada"
            />
          </Stack>
        )}
        {pilarAzulCanalesPropuestosVisible && (
          <Stack gap={2} data-testid="canales-propuestos-legend">
            <Text fw={500} size="xs">
              Canales Propuestos
            </Text>
            {PROPUESTOS_LEGEND_ROWS.map(({ etapa, color }) => (
              <CanalDashedLineChip
                key={etapa}
                color={color}
                label={etapa}
                testId={`canal-propuesto-chip-${etapa}`}
              />
            ))}
          </Stack>
        )}
        </Stack>
      </CollapsibleSection>
    </Paper>
  );
});
